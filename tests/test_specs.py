#!/usr/bin/env python3
"""Contract tests for the cafaye core specs.

Every rule that core declares lives in exactly one place: a JSON Schema in
``schemas/``. The one exception is the outbox convention, which is a SQL table
rather than an instance shape, so it is asserted straight out of the SQL block
in ``docs/event-outbox.md``. This suite is the executable statement of both.

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
FLEET_SCHEMA_PATH = SCHEMAS / "fleet.schema.json"
PAYLOAD_SCHEMAS = SCHEMAS / "events"

VALID_EXAMPLES = EXAMPLES / "valid"
INVALID_EXAMPLES = EXAMPLES / "invalid"
VALID_PAYLOADS = VALID_EXAMPLES / "events"
INVALID_PAYLOADS = INVALID_EXAMPLES / "events"

MANIFEST_EXAMPLES = sorted(VALID_EXAMPLES.glob("*.cafaye.yml"))

# Open decisions live in DECISIONS.md at the repository root rather than as
# callouts in docs/, because test_no_open_decision_callouts_remain_in_the_docs is
# a merge gate: a spec on master must read as decided, and a worker branch that
# opens a real question would trip it. The tempting fix — weakening or skipping
# that gate — is how a spec silently stops being enforced. So the questions are
# numbered in one place and the affected doc points at them.
DECISIONS = REPO / "DECISIONS.md"
CHANGELOG = REPO / "CHANGELOG.md"
REQUIRED_DECISION_PARTS = ("Choice:", "Alternatives:", "Recommendation:", "Cost of flipping:")

# fleet.yml is core's record of what the real services publish. It is not an
# example manifest: it is the one file in this repository that states a fact
# about another repository, which is why it has its own schema and its own tests.
FLEET = REPO / "fleet.yml"
INVALID_FLEET = INVALID_EXAMPLES / "fleet.invalid.yml"
WORKER_EXAMPLE = VALID_EXAMPLES / "worker.cafaye.yml"
WORKER_ONLY_EXAMPLE = VALID_EXAMPLES / "worker-only.cafaye.yml"
VALID_ENVELOPE = VALID_EXAMPLES / "event-envelope.json"
INVALID_MANIFEST = INVALID_EXAMPLES / "manifest.cafaye.invalid.yml"
INVALID_ENVELOPE = INVALID_EXAMPLES / "event-envelope.invalid.json"
INVALID_UNTAGGED_ENVELOPE = INVALID_EXAMPLES / "event-envelope.untagged.invalid.json"
INVALID_SUBJECTLESS_ENVELOPE = INVALID_EXAMPLES / "event-envelope.subjectless.invalid.json"

EVENT_NAMING_DOC = DOCS / "event-naming.md"
OPENAPI_DOC = DOCS / "openapi-conventions.md"
OUTBOX_DOC = DOCS / "event-outbox.md"
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
    "info.version",
    "contract lint",
)

# Every core semver constraint form (docs/manifest-conventions.md) needs a
# manifest that uses it, or the form is untested grammar.
REQUIRED_CORE_CONSTRAINT_FORMS = ("^0.", "~0.", "0.")

# A payload schema lives at schemas/events/<service>/<entity>/<action>.schema.json
PAYLOAD_SUFFIX = ".schema.json"
PAYLOAD_EXAMPLE_SUFFIX = ".data.json"

# The services fleet.yml is a declaration about. The list is a floor, not a
# ceiling: a new service joins it when its manifest is read, and a service that
# ships nothing (guard) is still in it, because a declaration that only names
# services with events would not be a declaration about the fleet.
REQUIRED_FLEET_SERVICES = frozenset({"identity", "billing", "courier", "muse", "guard"})

# (event type, expected (keyword, path) violations) — every payload schema owes
# a negative case, exactly like every top-level schema does.
INVALID_PAYLOAD_CASES = (
    (
        "identity.user.created",
        (("required", ""), ("additionalProperties", "")),
    ),
    (
        "billing.customer.created",
        (("required", ""), ("additionalProperties", "")),
    ),
    (
        "billing.plan.created",
        (("required", ""), ("additionalProperties", "")),
    ),
    (
        "billing.plan.updated",
        (("required", ""), ("additionalProperties", "")),
    ),
    (
        "billing.subscription.started",
        (("required", ""), ("additionalProperties", "")),
    ),
    (
        "billing.subscription.updated",
        (("required", ""), ("additionalProperties", "")),
    ),
    (
        "billing.subscription.canceled",
        (("required", ""), ("additionalProperties", "")),
    ),
    (
        "billing.payment.succeeded",
        (("required", ""), ("additionalProperties", ""), ("oneOf", "")),
    ),
    (
        "billing.payment.failed",
        (("required", ""), ("additionalProperties", "")),
    ),
    (
        "courier.email.queued",
        (("required", ""), ("additionalProperties", "")),
    ),
    (
        "courier.email.delivered",
        (("required", ""), ("additionalProperties", "")),
    ),
    (
        "courier.email.bounced",
        (("required", ""), ("additionalProperties", "")),
    ),
    (
        "courier.email.complained",
        (("required", ""), ("additionalProperties", "")),
    ),
    (
        "courier.notification.suppressed",
        (("required", ""), ("additionalProperties", "")),
    ),
    (
        "muse.tokens.consumed",
        (("minLength", "model"), ("additionalProperties", "")),
    ),
)

# The outbox table is a contract, so its columns are asserted out of the SQL in
# docs/event-outbox.md rather than trusted to the prose around it.
REQUIRED_OUTBOX_COLUMNS = (
    "create table if not exists outbox_events",
    "id uuid primary key",
    "event_type text not null",
    "source text not null",
    "subject text not null",
    "time timestamptz not null",
    "data jsonb not null",
    "created_at timestamptz not null default now()",
    "published_at timestamptz null",
    "attempts int not null default 0",
    "where published_at is null",
    "for update skip locked",
    "create index if not exists",
)

REQUIRED_OUTBOX_TOPICS = (
    "outbox_events",
    "same transaction",
    "for update skip locked",
    "published_at",
    "attempts",
    "backoff",
    "nats",
    "at-least-once",
    "idempotent",
    "```mermaid",
    "sequencediagram",
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


def payload_schema_path(event_type: str) -> Path:
    """`identity.user.created` -> schemas/events/identity/user/created.schema.json."""
    return PAYLOAD_SCHEMAS / (event_type.replace(".", "/") + PAYLOAD_SUFFIX)


def event_type_of(schema_path: Path) -> str:
    """The inverse of payload_schema_path: a payload schema's file name is its type."""
    relative = schema_path.relative_to(PAYLOAD_SCHEMAS).as_posix()
    return relative[: -len(PAYLOAD_SUFFIX)].replace("/", ".")


def payload_schemas() -> list[Path]:
    return sorted(PAYLOAD_SCHEMAS.rglob(f"*{PAYLOAD_SUFFIX}"))


def event_type_pattern() -> str:
    """The one machine-checked form of the event grammar, from the envelope schema."""
    return load_schema(ENVELOPE_SCHEMA_PATH)["$defs"]["eventType"]["pattern"]


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
    for path in (MANIFEST_SCHEMA_PATH, ENVELOPE_SCHEMA_PATH, FLEET_SCHEMA_PATH, *payload_schemas()):
        schema = load_schema(path)
        assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema", path
        assert schema.get("$id"), f"{path} needs a stable $id"
        assert schema.get("title"), f"{path} needs a title"
        assert schema.get("description"), f"{path} needs a description"
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


def test_invalid_envelopes_fail_for_their_documented_reasons() -> None:
    """Every negative envelope is rejected for exactly the reasons its note lists."""
    schema = load_schema(ENVELOPE_SCHEMA_PATH)
    cases = (
        (INVALID_ENVELOPE, (
            ("required", ""),                # specversion missing
            ("format", "id"),                # id is not a uuid
            ("format", "time"),              # time is not RFC3339
            ("pattern", "type"),             # four dot-separated segments
            ("pattern", "subject"),          # subject contains a space
            ("additionalProperties", ""),    # unknown envelope field
        )),
        (INVALID_UNTAGGED_ENVELOPE, (
            ("pattern", "type"),             # two segments: no service prefix
        )),
        (INVALID_SUBJECTLESS_ENVELOPE, (
            ("required", ""),                # subject is required
        )),
    )
    for path, expected in cases:
        found = failures_for(load_document(path), schema)
        assert found, f"{path.name} is supposed to be rejected by the schema"
        assert_keywords(found, expected)


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
            ("pattern", "exposes/events/0"),       # upper-case, and two segments
            ("pattern", "repository/url"),         # https remote, not ssh
            ("const", "repository/defaultBranch"),  # main, not master
            ("additionalProperties", ""),          # undeclared top-level key
        ),
    )


def test_invalid_examples_document_their_expected_failure() -> None:
    notes = INVALID_NOTES.read_text(encoding="utf-8")
    for path in sorted(INVALID_EXAMPLES.rglob("*")):
        if not path.is_file() or path.name == INVALID_NOTES.name:
            continue
        assert path.relative_to(REPO).as_posix() in notes, (
            f"examples/invalid/README.md must explain {path.relative_to(REPO).as_posix()}"
        )


# --------------------------------------------------------------------------
# 4. cross-field rules JSON Schema cannot express
# --------------------------------------------------------------------------


def test_worker_only_example_exposes_no_api() -> None:
    manifest = load_document(WORKER_ONLY_EXAMPLE)
    exposes = manifest.get("exposes", {})
    assert "api" not in exposes, "the worker-only example must not declare an OpenAPI document"
    assert not exposes.get("events"), "the worker-only example publishes no events"


def test_event_types_are_exactly_three_segments() -> None:
    """`<service>.<entity>.<action>`, always prefixed, no exceptions.

    The service segment is a service name, so it is kebab-case like `name` in a
    manifest; the entity and action segments are lowercase snake_case.
    """
    pattern = event_type_pattern()
    for accepted in (
        "identity.user.created",
        "identity.api_key.created",
        "billing.subscription.past_due",
        "email-sender.email.queued",  # a service name may contain a dash
    ):
        assert re.fullmatch(pattern, accepted), f"{accepted} must be a legal event type"
    for rejected in (
        "user.created",                       # two segments: no service prefix
        "identity.user.account.created",      # four segments
        "identity.User.created",              # not lowercase
        "email_sender.email.queued",          # underscore in the service segment
        "identity..created",                  # empty segment
        "identity.user.",                     # empty action
    ):
        assert not re.fullmatch(pattern, rejected), (
            f"{rejected} must be rejected by the event type grammar"
        )


def test_published_event_types_carry_their_service_prefix() -> None:
    """Every published type names its own service — the grammar has no exceptions.

    Consuming a type is not checked here: its prefix names the publisher, which
    this repository has no way of knowing.
    """
    for path in MANIFEST_EXAMPLES:
        manifest = load_document(path)
        name = manifest["name"]
        for event_type in manifest.get("exposes", {}).get("events", []):
            assert event_type.split(".")[0] == name, (
                f"{path.name}: {event_type} must start with its own service name "
                f"({name}.…) — every event type is <service>.<entity>.<action>"
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
    pattern = event_type_pattern()
    catalog = section(EVENT_NAMING_DOC.read_text(encoding="utf-8"), "## Catalog")
    types = re.findall(r"^\|\s*`([a-z][a-z0-9_.-]+)`\s*\|", catalog, flags=re.MULTILINE)
    assert len(types) >= 10, f"event-naming.md catalog looks truncated ({len(types)} rows)"
    for event_type in types:
        assert re.fullmatch(pattern, event_type), (
            f"catalog event {event_type} violates {pattern} — fix the doc or the schema"
        )
    assert set(types) >= {
        "identity.user.created",
        "identity.account.created",
        "identity.member.invited",
        "billing.plan.created",
        "billing.customer.created",
        "billing.subscription.started",
        "billing.payment.succeeded",
    }, "the packet's named events must appear in the catalog"


def test_event_grammar_section_states_three_segments() -> None:
    """The prose grammar and the machine pattern are the same rule stated twice."""
    grammar = section(EVENT_NAMING_DOC.read_text(encoding="utf-8"), "## Grammar")
    assert "<service>.<entity>.<action>" in grammar, (
        "docs/event-naming.md must state the canonical three-segment form"
    )
    assert "no exceptions" in grammar.lower(), (
        "the prefix is mandatory for every type; say so in the grammar section"
    )
    # The `type` production is asserted on its own, because the canonical form
    # contains the rejected one as a substring.
    productions = [line for line in grammar.splitlines() if line.startswith("type")]
    assert len(productions) == 1, "the grammar must declare exactly one `type` production"
    rule = productions[0].partition("#")[0]
    assert "<service>" in rule, "the type production must start at the service segment"
    assert rule.count('"."') == 2, "three segments means two separators, not one or three"
    assert "|" not in rule, "there is no short form: one production, one shape"
    for stale in ("2 segments", "{1,2}"):
        assert stale not in grammar, (
            f"docs/event-naming.md still advertises {stale!r}; the grammar is exactly "
            "<service>.<entity>.<action>"
        )


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
            re.findall(r"^\|\s*`([a-z][a-z0-9_.-]+)`\s*\|", rows, flags=re.MULTILINE)
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

    Note the scope: the example manifests are core's, so this assertion can only
    catch core disagreeing with itself. The fleet-wide version — a real service's
    manifest against the catalog — is the fleet.yml section, and it is the one
    that would have caught courier.
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


def test_consumed_event_types_exist_in_the_catalog() -> None:
    """A subscription to a type nobody publishes is a typo that ships silently."""
    known: set[str] = set()
    for types in catalog_by_service().values():
        known |= types
    for path in MANIFEST_EXAMPLES:
        manifest = load_document(path)
        for event_type in manifest.get("consumes", []):
            assert event_type in known, (
                f"{path.name} consumes {event_type}, which no publisher in the "
                f"{EVENT_NAMING_DOC.name} catalog declares"
            )


def test_manifest_examples_cover_every_core_constraint_form() -> None:
    """The semver mini-grammar has three forms; all three are exercised here."""
    forms = {
        load_document(path)["core"] for path in MANIFEST_EXAMPLES
    }
    missing = [form for form in REQUIRED_CORE_CONSTRAINT_FORMS if not any(f.startswith(form) for f in forms)]
    assert not missing, (
        f"no example manifest uses the core constraint form(s) {missing} — see "
        f"docs/manifest-conventions.md"
    )


def test_openapi_conventions_doc_covers_every_required_topic() -> None:
    doc = OPENAPI_DOC.read_text(encoding="utf-8").lower()
    missing = [topic for topic in REQUIRED_OPENAPI_TOPICS if topic not in doc]
    assert not missing, f"docs/openapi-conventions.md dropped: {missing}"


def test_no_open_decision_callouts_remain_in_the_docs() -> None:
    """A merged spec reads as decided; a `DECISION NEEDED` callout blocks the merge.

    The drafting process is unchanged (AGENTS.md still asks for callouts on a
    worker branch) — this asserts the manager's decision was folded in, not that
    the process changed.
    """
    open_callouts = [
        path.name
        for path in sorted(DOCS.glob("*.md"))
        if "DECISION NEEDED" in path.read_text(encoding="utf-8")
    ]
    assert not open_callouts, (
        f"undecided spec still calls out open questions: {open_callouts} — fold in the "
        "manager's decision or mark it as a new numbered decision"
    )


# --------------------------------------------------------------------------
# 5. per-event payload schemas
# --------------------------------------------------------------------------


def test_payload_schema_paths_match_their_event_type() -> None:
    """A payload schema's path is its event type with dots as directory separators."""
    found = payload_schemas()
    assert found, "core owes at least one per-event payload schema"
    pattern = event_type_pattern()
    catalog: set[str] = set()
    for types in catalog_by_service().values():
        catalog |= types
    for path in found:
        event_type = event_type_of(path)
        assert re.fullmatch(pattern, event_type), (
            f"{path.name} does not map to a legal event type ({event_type})"
        )
        assert event_type in catalog, (
            f"{path.name} declares {event_type}, which is absent from the "
            f"{EVENT_NAMING_DOC.name} catalog"
        )
        assert payload_schema_path(event_type) == path, (
            f"{event_type} must live at {payload_schema_path(event_type).relative_to(REPO)}"
        )


def test_every_payload_schema_owes_a_negative_case() -> None:
    """A payload schema with no negative example is an unproven assertion.

    `INVALID_PAYLOAD_CASES` is a hand-written table, which is exactly the kind of
    list that rots: a new schema lands, the table is not updated, and the suite
    stays green because nothing cross-checks the two. This is that cross-check.
    """
    declared = {event_type for event_type, _ in INVALID_PAYLOAD_CASES}
    owed = {event_type_of(path) for path in payload_schemas()}
    assert owed <= declared, (
        "these payload schemas have no entry in INVALID_PAYLOAD_CASES, so nothing "
        f"asserts they reject anything: {sorted(owed - declared)}"
    )


def test_payload_schemas_are_listed_in_the_event_naming_doc() -> None:
    """Core owns the single home for payload schemas, so it has to be discoverable."""
    doc = EVENT_NAMING_DOC.read_text(encoding="utf-8")
    for path in payload_schemas():
        relative = path.relative_to(REPO).as_posix()
        assert relative in doc, (
            f"{relative} must be listed in {EVENT_NAMING_DOC.name} — a consumer has no "
            "other way to find the payload schema for a type"
        )


def test_payload_schema_variant_examples_validate() -> None:
    """A payload schema with more than one real shape gets one example per shape.

    `examples/valid/events/<service>/<entity>/<action>.<variant>.data.json` is the
    same contract checked from a second angle. Only `billing.payment.succeeded`
    has one today — it is emitted from two different sources with two different
    payload shapes — but the rule is a rule rather than a special case in a test
    that names billing, so the next multi-shaped payload needs no new test.
    """
    found = False
    for path in sorted(VALID_PAYLOADS.rglob(f"*{PAYLOAD_EXAMPLE_SUFFIX}")):
        relative = path.relative_to(VALID_PAYLOADS).as_posix()
        stem = relative[: -len(PAYLOAD_EXAMPLE_SUFFIX)]
        head, _, variant = stem.rpartition(".")
        if not head or not variant:
            continue  # the canonical example, checked above
        event_type = head.replace("/", ".")
        schema_path = payload_schema_path(event_type)
        assert schema_path.is_file(), f"{event_type} has no schema for {path.name}"
        found = True
        report = failures_for(load_document(path), load_schema(schema_path))
        assert not report, f"{path.name} must satisfy {schema_path.name}:\n  " + "\n  ".join(
            str(f) for f in report
        )
    assert found, "no variant payload example exists, so no schema is checked from two angles"


def test_payload_schema_examples_validate() -> None:
    for path in payload_schemas():
        event_type = event_type_of(path)
        example = VALID_PAYLOADS / (event_type.replace(".", "/") + PAYLOAD_EXAMPLE_SUFFIX)
        assert example.is_file(), (
            f"{event_type} owes a valid payload example at {example.relative_to(REPO)}"
        )
        found = failures_for(load_document(example), load_schema(path))
        assert not found, f"{example.name} must satisfy {path.name}:\n  " + "\n  ".join(
            str(f) for f in found
        )


def test_payload_schema_invalid_examples_fail() -> None:
    for event_type, expected in INVALID_PAYLOAD_CASES:
        schema_path = payload_schema_path(event_type)
        assert schema_path.is_file(), f"{event_type} owes a payload schema at {schema_path.name}"
        example = INVALID_PAYLOADS / (event_type.replace(".", "/") + PAYLOAD_EXAMPLE_SUFFIX)
        assert example.is_file(), (
            f"{event_type} owes a negative payload example at {example.relative_to(REPO)}"
        )
        found = failures_for(load_document(example), load_schema(schema_path))
        assert found, f"{example.name} is supposed to be rejected by {schema_path.name}"
        assert_keywords(found, expected)


def test_valid_envelope_data_validates_against_its_payload_schema() -> None:
    """End to end: the shipped example envelope's `data` is a real payload."""
    envelope = load_document(VALID_ENVELOPE)
    schema = load_schema(payload_schema_path(envelope["type"]))
    found = failures_for(envelope["data"], schema)
    assert not found, f"{VALID_ENVELOPE.name} data must satisfy the {envelope['type']} payload:\n  " + "\n  ".join(
        str(f) for f in found
    )


# --------------------------------------------------------------------------
# 6. the outbox convention
# --------------------------------------------------------------------------


def outbox_sql() -> str:
    """The SQL in docs/event-outbox.md, normalized: lower case, single spaces."""
    blocks = re.findall(r"```sql\n(.*?)```", OUTBOX_DOC.read_text(encoding="utf-8"), flags=re.DOTALL)
    assert blocks, f"{OUTBOX_DOC.name} must state the outbox table as SQL, not prose"
    return re.sub(r"\s+", " ", " ".join(blocks)).lower()


def test_event_outbox_doc_declares_the_outbox_table() -> None:
    """The outbox table is a contract; its columns are asserted out of the doc."""
    sql = outbox_sql()
    missing = [column for column in REQUIRED_OUTBOX_COLUMNS if column not in sql]
    assert not missing, f"{OUTBOX_DOC.name} is missing from its SQL: {missing}"


def test_event_outbox_doc_covers_every_required_topic() -> None:
    doc = OUTBOX_DOC.read_text(encoding="utf-8").lower()
    missing = [topic for topic in REQUIRED_OUTBOX_TOPICS if topic not in doc]
    assert not missing, f"{OUTBOX_DOC.name} dropped: {missing}"


# --------------------------------------------------------------------------
# 7. the fleet declaration
# --------------------------------------------------------------------------


def load_fleet() -> dict:
    return yaml.safe_load(FLEET.read_text(encoding="utf-8"))


def fleet_published() -> dict[str, set[str]]:
    """{service: {event types that service's manifest declares}} from fleet.yml."""
    return {
        service["name"]: set(service.get("events", []))
        for service in load_fleet()["services"]
    }


def test_fleet_declaration_matches_its_schema() -> None:
    """fleet.yml is a claim about other repositories, so it is validated like one."""
    schema = load_schema(FLEET_SCHEMA_PATH)
    found = failures_for(load_fleet(), schema)
    assert not found, f"{FLEET.name} must satisfy {FLEET_SCHEMA_PATH.name}:\n  " + "\n  ".join(
        str(f) for f in found
    )


def test_invalid_fleet_example_fails() -> None:
    schema = load_schema(FLEET_SCHEMA_PATH)
    found = failures_for(load_document(INVALID_FLEET), schema)
    assert found, f"{INVALID_FLEET.name} is supposed to be rejected by the schema"
    assert_keywords(
        found,
        (
            ("const", "spec"),                       # transcribed against the wrong spec
            ("format", "readOn"),                    # the provenance claim is not a date
            ("pattern", "services/0/name"),          # not a cafaye namespace name
            ("const", "services/0/manifest"),        # not the manifest name the schema pins
            ("const", "services/0/branch"),          # main, not master
            ("pattern", "services/0/sourceCommit"),  # a short sha, not a full commit
            ("pattern", "services/0/events/0"),      # upper case: forks the topic
            ("pattern", "services/0/events/1"),      # two segments: no service prefix
            ("additionalProperties", "services/0"),  # undeclared service key
        ),
    )


def test_fleet_covers_every_shipped_service() -> None:
    """The fleet declaration has to name the services it is a declaration about.

    Without this, dropping a service from fleet.yml silences every check below
    instead of failing one.
    """
    assert set(fleet_published()) >= REQUIRED_FLEET_SERVICES, (
        f"fleet.yml no longer names {sorted(REQUIRED_FLEET_SERVICES - set(fleet_published()))} "
        "— a service dropped from the declaration is a service nobody checks"
    )


def test_published_fleet_events_carry_their_own_service_prefix() -> None:
    """The grammar has no exceptions, and a real manifest is not exempt from it.

    This is the check core could not make before: the catalog was only ever
    compared against core's own example manifests, so a service could advertise
    whatever it liked. fleet.yml is the transcribed real thing.
    """
    pattern = event_type_pattern()
    for service, types in fleet_published().items():
        for event_type in sorted(types):
            assert re.fullmatch(pattern, event_type), (
                f"fleet.yml: {service} declares {event_type}, which violates the "
                f"event grammar {pattern}"
            )
            assert event_type.split(".")[0] == service, (
                f"fleet.yml: {event_type} must start with its own service name ({service}.…)"
            )


def test_every_published_fleet_event_has_a_catalog_row_and_a_payload_schema() -> None:
    """A published type and a shipped payload schema are the same fact, twice.

    This is the root-cause fix for courier: five event types reached master that
    no conforming consumer could parse, and nothing noticed, because the only
    comparison in the system was the catalog against core's own example
    manifests. fleet.yml is the comparison's input — this assertion is its
    point, and it is the one that has no equivalent anywhere else.
    """
    catalog = catalog_by_service()
    missing_rows: dict[str, list[str]] = {}
    missing_schemas: dict[str, list[str]] = {}
    for service, types in fleet_published().items():
        for event_type in sorted(types):
            if event_type not in catalog.get(service, set()):
                missing_rows.setdefault(service, []).append(event_type)
            if not payload_schema_path(event_type).is_file():
                missing_schemas.setdefault(service, []).append(event_type)
    assert not missing_rows, (
        f"published by a service but absent from the {EVENT_NAMING_DOC.name} catalog: "
        f"{missing_rows}"
    )
    assert not missing_schemas, (
        f"published by a service but with no payload schema in core: {missing_schemas} — "
        f"the path is {PAYLOAD_SCHEMAS.relative_to(REPO)}/<service>/<entity>/<action>"
        f"{PAYLOAD_SUFFIX}"
    )


def test_every_catalog_row_for_a_fleet_service_is_published_or_catalogued_only() -> None:
    """A catalog row is a promise; fleet.yml distinguishes a promise from a fact.

    `events` is what a service's manifest declares today. `cataloguedOnly` is a
    catalog row nobody publishes yet — real, and owed a payload schema when its
    packet lands, but not a claim about a repository. Without the distinction
    this test would force the catalog to be empty of promises, and the other
    direction would let a catalog row for a shipped service go undeclared.
    """
    fleet = load_fleet()
    catalog = catalog_by_service()
    for service in fleet["services"]:
        name = service["name"]
        if name not in catalog:
            continue  # a service with no catalog section publishes nothing yet
        published = set(service.get("events", []))
        promised = set(service.get("cataloguedOnly", []))
        both = published & promised
        assert not both, (
            f"fleet.yml: {name} lists {sorted(both)} as both published and catalogued-only"
        )
        unaccounted = catalog[name] - published - promised
        assert not unaccounted, (
            f"{EVENT_NAMING_DOC.name} has {name} rows that no repository declares and "
            f"fleet.yml does not mark catalogued-only: {sorted(unaccounted)}"
        )
        stale = promised - catalog.get(name, set())
        assert not stale, (
            f"fleet.yml marks {sorted(stale)} catalogued-only for {name} but there is no "
            f"catalog row for them"
        )


def open_decisions() -> list[tuple[int, str]]:
    """The `## Dn` sections of DECISIONS.md, as (number, body) pairs."""
    text = DECISIONS.read_text(encoding="utf-8")
    return [
        (int(number), body)
        for number, body in re.findall(
            r"^## D(\d+):[^\n]*\n(.*?)(?=^## |\Z)", text, flags=re.MULTILINE | re.DOTALL
        )
    ]


def test_open_decisions_are_numbered_and_complete() -> None:
    """A decision number is a citation, so it must be unique, ascending and unused.

    A reused number is a broken cross-reference, and a reference to a number that
    does not exist is worse than no reference at all. Every open decision also
    owes the same four paragraphs, because "here is my call" without the
    alternatives and the cost of flipping is how a worker resolves a design
    question silently — which AGENTS.md forbids and which the manager cannot
    review if it is not written down.
    """
    decisions = open_decisions()
    numbers = [number for number, _ in decisions]
    assert numbers, "DECISIONS.md has no decisions, which cannot be true of a spec mid-reconciliation"
    assert numbers == sorted(numbers), f"decision numbers are out of order: {numbers}"
    assert len(set(numbers)) == len(numbers), f"a decision number is reused: {numbers}"

    settled = {
        int(number)
        for number in re.findall(
            r"^\| D(\d+) \|", CHANGELOG.read_text(encoding="utf-8"), flags=re.MULTILINE
        )
    }
    assert settled, "the changelog records no settled decisions, so the numbering floor is unknown"
    assert min(numbers) > max(settled), (
        f"D{min(numbers)} reuses a number the changelog already settled (D1-D{max(settled)})"
    )

    for number, body in decisions:
        missing = [part for part in REQUIRED_DECISION_PARTS if part not in body]
        assert not missing, f"D{number} is missing {missing} — see AGENTS.md"
        assert re.search(r"\]\((?!#)[^)]*/[^)]*\)", body), (
            f"D{number} must link the files it affects; a decision with no stated "
            "surface is a decision nothing implements"
        )


def test_open_decisions_are_referenced_from_a_document() -> None:
    """A numbered decision is only useful if something points at it.

    AGENTS.md asks for the callout to sit in the affected doc. The numbering
    moved to DECISIONS.md, so this is what stands in for that: every open
    decision has to be cited from a file a reader of this spec will open.
    """
    corpus = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (*sorted(DOCS.glob("*.md")), REPO / "README.md", FLEET)
    )
    referenced = {int(number) for number in re.findall(r"\bD(\d+)\b", corpus)}
    open_numbers = {number for number, _ in open_decisions()}
    missing = sorted(open_numbers - referenced)
    assert not missing, (
        f"DECISIONS.md opens {missing} but no document cites them, so a reader of the "
        "spec has no way to know a question is open"
    )


def test_fleet_records_a_source_commit_per_service() -> None:
    """A declaration with no provenance cannot be refreshed by the next reader."""
    for service in load_fleet()["services"]:
        assert re.fullmatch(r"[0-9a-f]{40}", service["sourceCommit"]), (
            f"fleet.yml: {service['name']} needs the full 40-character commit its "
            "cafaye.yml was read at"
        )
        assert service.get("branch") == "master", (
            f"fleet.yml: {service['name']} was not read from the primary branch"
        )


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
