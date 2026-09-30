#!/usr/bin/env python3
"""Contract tests for the cafaye core specs.

Every rule that core declares lives in exactly one place: a JSON Schema in
``schemas/``. This suite is the executable statement of those rules.

It runs two ways, with identical coverage:

    pytest tests/            # canonical
    python tests/test_specs.py   # dependency-light fallback (what bin/prime uses)

Test doctrine: tests are written before the schemas they check. A rule with no
test here is not a cafaye rule.
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

import jsonschema
import yaml

REPO = Path(__file__).resolve().parent.parent
SCHEMAS = REPO / "schemas"
EXAMPLES = REPO / "examples"
DOCS = REPO / "docs"

MANIFEST_SCHEMA_PATH = SCHEMAS / "cafaye.manifest.schema.json"
ENVELOPE_SCHEMA_PATH = SCHEMAS / "event-envelope.schema.json"

VALID_EXAMPLES = EXAMPLES / "valid"
INVALID_EXAMPLES = EXAMPLES / "invalid"

MANIFEST_EXAMPLES = sorted(VALID_EXAMPLES.glob("*.cafaye.yml"))
WORKER_EXAMPLE = VALID_EXAMPLES / "worker.cafaye.yml"
WORKER_ONLY_EXAMPLE = VALID_EXAMPLES / "worker-only.cafaye.yml"
VALID_ENVELOPE = VALID_EXAMPLES / "event-envelope.json"
INVALID_MANIFEST = INVALID_EXAMPLES / "manifest.cafaye.invalid.yml"
INVALID_ENVELOPE = INVALID_EXAMPLES / "event-envelope.invalid.json"

EVENT_NAMING_DOC = DOCS / "event-naming.md"
OPENAPI_DOC = DOCS / "openapi-conventions.md"
INVALID_NOTES = INVALID_EXAMPLES / "README.md"

MIN_VALID_MANIFEST_EXAMPLES = 3
FORMAT_CHECKER = jsonschema.FormatChecker()

REQUIRED_OPENAPI_TOPICS = (
    "problem+json",
    "idempotency-key",
    "jwks",
    "/v1",
    "deprecat",
    "cursor",
)


@dataclass(frozen=True)
class Failure:
    """One schema violation, flattened for readable assertions."""

    keyword: str
    path: str
    message: str

    def __str__(self) -> str:
        where = self.path or "<root>"
        return f"{where}: {self.message} [{self.keyword}]"


# --------------------------------------------------------------------------
# loading helpers
# --------------------------------------------------------------------------


def load_schema(path: Path) -> dict:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def load_document(path: Path):
    """Load a spec example. Manifests are YAML; the wire envelope is JSON."""
    text = path.read_text(encoding="utf-8")
    if path.suffix in {".yml", ".yaml"}:
        return yaml.safe_load(text)
    return json.loads(text)


def validator_for(schema: dict) -> jsonschema.Draft202012Validator:
    return jsonschema.Draft202012Validator(schema, format_checker=FORMAT_CHECKER)


def failures_for(instance, schema: dict) -> list[Failure]:
    found = []
    for error in validator_for(schema).iter_errors(instance):
        path = "/".join(str(part) for part in error.absolute_path)
        found.append(Failure(keyword=error.validator, path=path, message=error.message))
    return found


def assert_keywords(failures: list[Failure], expected: tuple[tuple[str, str], ...]) -> None:
    """Assert every (keyword, path) pair shows up among the failures."""
    seen = {(failure.keyword, failure.path) for failure in failures}
    missing = [pair for pair in expected if pair not in seen]
    assert not missing, (
        "expected violations not produced: "
        + ", ".join(f"{keyword}@{path or '<root>'}" for keyword, path in missing)
        + "\nactual: "
        + ("\n         ".join(str(f) for f in failures) or "<none>")
    )


# --------------------------------------------------------------------------
# 1. the schemas themselves
# --------------------------------------------------------------------------


def test_schemas_declare_draft_2020_12() -> None:
    for path in (MANIFEST_SCHEMA_PATH, ENVELOPE_SCHEMA_PATH):
        schema = load_schema(path)
        assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema", path
        assert schema.get("$id"), f"{path} needs a stable $id"
        assert schema.get("title"), f"{path} needs a title"
        # meta-validation: the schema must be a legal draft 2020-12 schema
        jsonschema.Draft202012Validator.check_schema(schema)


def test_every_example_manifest_is_covered_by_the_manifest_schema() -> None:
    assert len(MANIFEST_EXAMPLES) >= MIN_VALID_MANIFEST_EXAMPLES, (
        f"core owes >= {MIN_VALID_MANIFEST_EXAMPLES} valid manifest examples, "
        f"found {len(MANIFEST_EXAMPLES)}"
    )
    schema = load_schema(MANIFEST_SCHEMA_PATH)
    for path in MANIFEST_EXAMPLES:
        found = failures_for(load_document(path), schema)
        assert not found, f"{path.name} must be valid:\n  " + "\n  ".join(str(f) for f in found)


def test_core_dogfoods_its_own_manifest() -> None:
    schema = load_schema(MANIFEST_SCHEMA_PATH)
    found = failures_for(load_document(REPO / "cafaye.yml"), schema)
    assert not found, "core/cafaye.yml must satisfy core's own manifest schema:\n  " + "\n  ".join(
        str(f) for f in found
    )


# --------------------------------------------------------------------------
# 2. event envelope
# --------------------------------------------------------------------------


def test_valid_event_envelope_example_validates() -> None:
    schema = load_schema(ENVELOPE_SCHEMA_PATH)
    found = failures_for(load_document(VALID_ENVELOPE), schema)
    assert not found, "valid event envelope must validate:\n  " + "\n  ".join(
        str(f) for f in found
    )


def test_invalid_event_envelope_example_fails() -> None:
    schema = load_schema(ENVELOPE_SCHEMA_PATH)
    found = failures_for(load_document(INVALID_ENVELOPE), schema)
    assert found, f"{INVALID_ENVELOPE.name} is supposed to be rejected by the schema"
    assert_keywords(
        found,
        (
            ("required", ""),          # specversion missing
            ("format", "id"),          # id is not a uuid
            ("format", "time"),        # time is not RFC3339
            ("pattern", "type"),       # four dot-separated segments
            ("pattern", "subject"),    # subject contains a space
            ("additionalProperties", ""),  # unknown envelope field
        ),
    )


def test_envelope_type_and_source_patterns_match_the_manifest() -> None:
    envelope = load_schema(ENVELOPE_SCHEMA_PATH)
    manifest = load_schema(MANIFEST_SCHEMA_PATH)
    assert envelope["$defs"]["eventType"]["pattern"] == manifest["$defs"]["eventType"]["pattern"]
    assert envelope["$defs"]["serviceName"]["pattern"] == manifest["$defs"]["serviceName"]["pattern"]


# --------------------------------------------------------------------------
# 3. invalid manifest example
# --------------------------------------------------------------------------


def test_invalid_manifest_example_fails() -> None:
    schema = load_schema(MANIFEST_SCHEMA_PATH)
    found = failures_for(load_document(INVALID_MANIFEST), schema)
    assert found, f"{INVALID_MANIFEST.name} is supposed to be rejected by the schema"
    assert_keywords(
        found,
        (
            ("pattern", "name"),                   # not a cafaye namespace name
            ("enum", "language"),                  # language outside the enum
            ("pattern", "core"),                   # semver constraint without a patch
            ("pattern", "exposes/api"),            # ./ prefixed, not a repo-relative path
            ("pattern", "exposes/events/0"),       # upper-case in an event type
            ("pattern", "repository/url"),         # https remote, not ssh
            ("const", "repository/defaultBranch"),  # main, not master
            ("additionalProperties", ""),          # undeclared top-level key
        ),
    )


def test_invalid_examples_document_their_expected_failure() -> None:
    notes = INVALID_NOTES.read_text(encoding="utf-8")
    for path in (INVALID_MANIFEST, INVALID_ENVELOPE):
        assert path.name in notes, f"examples/invalid/README.md must explain {path.name}"


# --------------------------------------------------------------------------
# 4. cross-field rules JSON Schema cannot express
# --------------------------------------------------------------------------


def test_worker_only_example_exposes_no_api() -> None:
    manifest = load_document(WORKER_ONLY_EXAMPLE)
    exposes = manifest.get("exposes", {})
    assert "api" not in exposes, "the worker-only example must not declare an OpenAPI document"
    assert not exposes.get("events"), "the worker-only example publishes no events"


def test_published_long_event_types_carry_their_service_prefix() -> None:
    """3-segment published types (<service>.<entity>.<action>) must name their own service.

    Consuming a long-form type is not checked here: its prefix names the publisher,
    which this repository has no way of knowing.
    """
    three_segments = re.compile(r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$")
    for path in MANIFEST_EXAMPLES:
        manifest = load_document(path)
        name = manifest["name"]
        for event_type in manifest.get("exposes", {}).get("events", []):
            if three_segments.match(event_type):
                assert event_type.split(".")[0] == name, (
                    f"{path.name}: {event_type} is a long form type and must start with "
                    f"its own service name ({name}.…)"
                )


def test_worker_example_publishes_events_without_serving_http() -> None:
    manifest = load_document(WORKER_EXAMPLE)
    exposes = manifest["exposes"]
    assert "api" not in exposes, "the worker example serves no HTTP API"
    assert exposes["events"], "a background worker usually still publishes events"


def test_services_do_not_consume_their_own_events() -> None:
    for path in MANIFEST_EXAMPLES:
        manifest = load_document(path)
        published = set(manifest.get("exposes", {}).get("events", []))
        consumed = set(manifest.get("consumes", []))
        overlap = published & consumed
        assert not overlap, f"{path.name} both publishes and consumes {sorted(overlap)}"


def section(text: str, heading: str) -> str:
    """Return one '## ' section of a markdown document, heading included."""
    start = text.find(heading)
    assert start != -1, f"{heading!r} section is missing"
    rest = text[start + len(heading) :]
    end = rest.find("\n## ")
    return text[start : start + len(heading) + (len(rest) if end == -1 else end)]


def test_event_catalog_in_docs_matches_the_schema() -> None:
    """Every event in the identity + billing catalog must satisfy the type pattern."""
    envelope = load_schema(ENVELOPE_SCHEMA_PATH)
    pattern = envelope["$defs"]["eventType"]["pattern"]
    catalog = section(EVENT_NAMING_DOC.read_text(encoding="utf-8"), "## Catalog")
    types = re.findall(r"^\|\s*`([a-z][a-z0-9_.]+)`\s*\|", catalog, flags=re.MULTILINE)
    assert len(types) >= 10, f"event-naming.md catalog looks truncated ({len(types)} rows)"
    for event_type in types:
        assert re.fullmatch(pattern, event_type), (
            f"catalog event {event_type} violates {pattern} — fix the doc or the schema"
        )
    assert set(types) >= {
        "user.created",
        "account.created",
        "member.invited",
        "subscription.started",
        "payment.succeeded",
    }, "the packet's named events must appear in the catalog"


def catalog_by_service() -> dict[str, set[str]]:
    """Parse the '## Catalog' section of event-naming.md into {publisher: {types}}.

    Each '### <service>' sub-section is one publisher, and the backticked first
    column of its table is that publisher's event list.
    """
    text = EVENT_NAMING_DOC.read_text(encoding="utf-8")
    catalog = section(text, "## Catalog")
    by_service: dict[str, set[str]] = {}
    for chunk in re.split(r"^### ", catalog, flags=re.MULTILINE)[1:]:
        heading, _, rows = chunk.partition("\n")
        by_service[heading.strip()] = set(
            re.findall(r"^\|\s*`([a-z][a-z0-9_.]+)`\s*\|", rows, flags=re.MULTILINE)
        )
    return by_service


def published_by_manifest() -> dict[str, set[str]]:
    return {
        manifest["name"]: set(manifest.get("exposes", {}).get("events", []))
        for manifest in (load_document(path) for path in MANIFEST_EXAMPLES)
    }


def test_catalog_and_manifest_agree_in_both_directions() -> None:
    """A published event type and a catalog row are the same fact, stated twice.

    The catalog is what a consumer reads to learn what exists; `exposes.events`
    is what `caf` and the contract tests read. If they drift, one of the two is
    lying to whoever generates an SDK from it.
    """
    catalog = catalog_by_service()
    published = published_by_manifest()

    undeclared = {
        service: sorted(types - catalog.get(service, set()))
        for service, types in published.items()
        if types - catalog.get(service, set())
    }
    assert not undeclared, (
        f"published in exposes.events but absent from the catalog in "
        f"{EVENT_NAMING_DOC.name}: {undeclared}"
    )

    unpublished = {
        service: sorted(types - published.get(service, set()))
        for service, types in catalog.items()
        if types - published.get(service, set())
    }
    assert not unpublished, (
        f"in the {EVENT_NAMING_DOC.name} catalog but not published by any example "
        f"manifest: {unpublished}"
    )


def test_openapi_conventions_doc_covers_every_required_topic() -> None:
    doc = OPENAPI_DOC.read_text(encoding="utf-8").lower()
    missing = [topic for topic in REQUIRED_OPENAPI_TOPICS if topic not in doc]
    assert not missing, f"docs/openapi-conventions.md dropped: {missing}"


# --------------------------------------------------------------------------
# standalone runner
# --------------------------------------------------------------------------


def main() -> int:
    tests = [
        (name, obj)
        for name, obj in sorted(globals().items())
        if name.startswith("test_") and callable(obj)
    ]
    failed = 0
    for name, test in tests:
        try:
            test()
        except AssertionError as error:
            failed += 1
            print(f"FAIL {name}\n     {error}")
        except Exception as error:  # noqa: BLE001 - report, do not mask
            failed += 1
            print(f"ERROR {name}\n      {type(error).__name__}: {error}")
        else:
            print(f"pass {name}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
