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

# The observability spec (PLAN.md §7b). Seven schemas, and they are seven
# different rules rather than seven views of one, which is why they are seven
# files: span naming, the three per-signal attribute allowlists, the redaction
# boundary, the *OTEL_ENDPOINT contract with its no-op path, and the
# healthz/readyz split. See docs/observability.md.
TELEMETRY_SCHEMAS = SCHEMAS / "telemetry"
SPAN_NAMING_SCHEMA_PATH = TELEMETRY_SCHEMAS / "span-naming.schema.json"
TRACES_SCHEMA_PATH = TELEMETRY_SCHEMAS / "traces.schema.json"
METRICS_SCHEMA_PATH = TELEMETRY_SCHEMAS / "metrics.schema.json"
LOGS_SCHEMA_PATH = TELEMETRY_SCHEMAS / "logs.schema.json"
REDACTION_SCHEMA_PATH = TELEMETRY_SCHEMAS / "redaction.schema.json"
ENDPOINT_SCHEMA_PATH = TELEMETRY_SCHEMAS / "otel-endpoint.schema.json"
PROBES_SCHEMA_PATH = TELEMETRY_SCHEMAS / "probes.schema.json"

VALID_EXAMPLES = EXAMPLES / "valid"
INVALID_EXAMPLES = EXAMPLES / "invalid"
VALID_PAYLOADS = VALID_EXAMPLES / "events"
INVALID_PAYLOADS = INVALID_EXAMPLES / "events"
VALID_TELEMETRY = VALID_EXAMPLES / "telemetry"
INVALID_TELEMETRY = INVALID_EXAMPLES / "telemetry"

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
OBSERVABILITY_DOC = DOCS / "observability.md"
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

# --- observability (PLAN.md §7b) -------------------------------------------

# The identifiers that are prohibited as a *measurement* attribute. This list is
# the failure mode the rule exists for, written out rather than described:
# OpenTelemetry folds a metric stream into one `otel.metric.overflow=true` point
# at 2000 distinct attribute combinations and drops every measurement attribute
# on the way, so totals stay right and every breakdown undercounts. The three
# named in the directive — tenant_id, user_id, account_id, request_id — plus
# trace_id and the request-scoped ids that are unbounded for the same reason.
PROHIBITED_MEASUREMENT_ATTRIBUTES = (
    "tenant_id",
    "user_id",
    "account_id",
    "request_id",
    "trace_id",
    "span_id",
    "session_id",
    "message_id",
    "notification_id",
    "email",
)

# Where those go instead. Resource attributes are not per-measurement, so the
# 2000-combination cap does not apply to them and they stay queryable on the
# overflow point — which is the entire reason the rule says "move it" rather
# than "drop it".
RESOURCE_IDENTITY_ATTRIBUTES = (
    "tenant_id",
    "account_id",
    "service.name",
    "service.version",
    "service.instance.id",
    "deployment.environment",
)

# Content words that must never appear in an allowlisted attribute name. This is
# muse's canary promoted to a spec: the house test at
# muse/tests/test_trace_propagation.py asserts no allowlisted name contains any
# of them, and asserts the rendered payload separately so truncation cannot be
# what makes it pass. The word list is the same one, so the fleet cannot
# reintroduce the leak under a new attribute name.
FORBIDDEN_ATTRIBUTE_NAME_WORDS = (
    "prompt",
    "completion",
    "message",
    "content",
    "text",
    "body",
    "header",
    "input",
    "output",
    "arguments",
    "instructions",
    "transcript",
    "query",
)

# Span names the grammar accepts. Low-cardinality by construction: a bounded
# segment vocabulary, no interpolation, and a length cap — because
# `muse.user.usr_01J9Z8QK5M4N7P2R3T6V8W9X0A` is a cardinality bomb that looks
# like diligence in a code review.
ACCEPTED_SPAN_NAMES = (
    "muse.request",
    "muse.route",
    "muse.provider.call",
    "identity.db.query",
    "billing.payment.capture",
    "courier.email.deliver",
    "darkroom.asset.transform",
    "guard.request.authorize",
    "muse.queue.publish",  # a service name may contain a dash
)

REJECTED_SPAN_NAMES = (
    "GET /users/:id",                          # the HTTP verb and the raw route
    "get_user",                                # a function name
    "users.GET",                               # a path and a verb
    "muse.user.usr_01J9Z8QK5M4N7P2R3T6V8W9X0A",  # an interpolated identifier, as cafaye mints them
    # Lower-case, so that case is NOT what refuses it. This entry is the only
    # one in the list that the fifteen-character segment cap is solely
    # responsible for rejecting, which makes it the one that keeps the cap
    # honest: without it, widening the cap to 63 would leave this test green
    # while the grammar quietly stopped refusing identifiers. Found by
    # mutating the cap and watching the suite stay green.
    "muse.user.usr_01j9z8qk5m4n7p2r3t6v8w9x0a",
    "muse.request.4bf92f3577b34da6a3ce929d0e0e4736",  # a trace id in the name
    "request",                                 # no service prefix
    "MUSE.REQUEST",                            # not lowercase
    "muse..request",                           # empty segment
    "muse.request.",                           # trailing separator
    "muse.1request",                            # segment starts with a digit
    "muse.a.b.c.d.e",                          # five segments: the grammar caps at four
    "muse-provider.call!",                     # punctuation
)

# Per-signal allowlists. The traces, metrics and logs schemas each enumerate
# exactly what may be recorded; this asserts none of them names content, and
# that the four signals do not quietly grow the same attribute with different
# names. The identity of a signal's allowlist is a list of names, so the
# assertion is a name assertion.
SIGNAL_ALLOWLISTS = {
    "traces": (
        "http.request.method",
        "http.response.status_code",
        "http.route",
        "db.system",
        "db.operation",
        "messaging.system",
        "messaging.operation",
        "otel.status_code",
        "error.type",
    ),
    "metrics": (
        "http.request.method",
        "http.route",
        "http.response.status_code_class",
        "db.system",
        "db.operation",
        "messaging.system",
        "error.type",
    ),
    "logs": (
        "log.severity",
        "service.name",
        "error.type",
    ),
}

# The endpoint contract. `*_OTEL_ENDPOINT` is the only contract (PLAN.md §7b),
# the shipped collector is only a default value, and unsetting it must be a free
# no-op — so the schema pins all three: the variable's name, the fact that
# unset means no-op, and the four properties ("no buffering, no retry loop
# against a dead endpoint, no warning spam") that make "free" checkable rather
# than aspirational.
REQUIRED_ENDPOINT_TOPICS = (
    "_otel_endpoint",
    "no-op",
    "no buffering",
    "no retry",
    "no warning",
    "otel_sdk_disabled",
    "otel_traces_exporter",
    "default",
    "bring your own",
    "readiness",
)

# The redaction boundary. Whatever the enforcement point turns out to be, the
# doc has to say it, and this is the list of things it has to say them about.
REQUIRED_REDACTION_TOPICS = (
    "prompt",
    "completion",
    "allowlist",
    "default-deny",
    "collector",
    "chokepoint",
    "defence in depth",
    "error.message",
    "error.type",
    "token count",
    "model",
    "finish reason",
)

# healthz vs readyz. A `readyz` that checks nothing is the failure the rule
# exists to prevent, and darkroom is the pattern: `/healthz` never touches a
# dependency, `/readyz` really runs `select 1`.
REQUIRED_HEALTH_TOPICS = (
    "healthz",
    "readyz",
    "unconditional",
    "dependency",
    "restart loop",
    "liveness",
    "readiness",
    "exempt from authentication",
)

# healthz vs readyz, as a machine-checked shape: the probe contract is a
# document, so a service declares it and a linter reads it. This is the schema
# side of the fleet-wide rule, and its negative case is a `readyz` with an
# empty `checks` list.
PROBE_EXAMPLE = VALID_TELEMETRY / "probes.json"
INVALID_PROBE_EXAMPLE = INVALID_TELEMETRY / "probes.empty-readyz.invalid.json"


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
            ("pattern", "services/0/telemetry/endpointVariable"),  # not UPPER_SNAKE
            ("enum", "services/0/telemetry/signals/1"),           # not an OTel signal
            ("type", "services/0/telemetry/probes"),              # not a boolean
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


# --------------------------------------------------------------------------
# 8. observability (PLAN.md §7b)
# --------------------------------------------------------------------------


def telemetry_schema_paths() -> list[Path]:
    return sorted(TELEMETRY_SCHEMAS.glob("*.schema.json"))


def span_naming_pattern() -> str:
    """The one machine-checked form of the span-name grammar."""
    return load_schema(SPAN_NAMING_SCHEMA_PATH)["$defs"]["spanName"]["pattern"]


def measurement_attribute_names() -> set[str]:
    """The metric schema's `measurementAttributes` property names, as a set."""
    return set(load_schema(METRICS_SCHEMA_PATH)["$defs"]["measurementAttributes"]["properties"])


def resource_attribute_names() -> set[str]:
    return set(load_schema(METRICS_SCHEMA_PATH)["$defs"]["resourceAttributes"]["properties"])


#: Where each signal's attribute allowlist lives inside its schema. The metrics
#: schema names its two maps after what they MEAN — `measurementAttributes` and
#: `resourceAttributes` — rather than after the signal, because the
#: measurement/resource split is the distinction that schema exists to draw and
#: naming it after the signal would obscure it. The other two are a single
#: allowlist each. Keyed here so a schema that renames one produces a clear
#: failure rather than a KeyError.
ALLOWLIST_DEF = {
    "traces": ("traces.schema.json", "tracesAttributes"),
    "metrics": ("metrics.schema.json", "measurementAttributes"),
    "logs": ("logs.schema.json", "logsAttributes"),
}


def signal_allowlist(signal: str) -> set[str]:
    filename, definition = ALLOWLIST_DEF[signal]
    schema = load_schema(TELEMETRY_SCHEMAS / filename)
    return set(schema["$defs"][definition]["properties"])


def test_telemetry_schemas_declare_draft_2020_12() -> None:
    """Every observability schema is a legal, self-describing draft 2020-12 schema.

    Seven files that core does not meta-validate are seven files a service CI
    can load and get a confusing `SchemaError` from, so this is the observability
    half of `test_schemas_declare_draft_2020_12` and it is not optional.
    """
    found = telemetry_schema_paths()
    assert {path.name for path in found} == {
        "span-naming.schema.json",
        "traces.schema.json",
        "metrics.schema.json",
        "logs.schema.json",
        "redaction.schema.json",
        "otel-endpoint.schema.json",
        "probes.schema.json",
    }, f"the observability schema set changed; add the new file to this test: {found}"
    for path in found:
        schema = load_schema(path)
        assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema", path
        assert schema.get("$id"), f"{path} needs a stable $id"
        assert schema.get("title"), f"{path} needs a title"
        assert schema.get("description"), f"{path} needs a description"
        jsonschema.Draft202012Validator.check_schema(schema)


def test_no_telemetry_schema_has_an_unreferenced_def() -> None:
    """A `$defs` entry nothing `$ref`s looks load-bearing and validates nothing.

    Found by mutation: probes.schema.json carried a `probeBase` holding the `auth`
    rule and its reasoning, which no probe actually referenced. A test asserting
    the *example* said `exempt` passed, and so did a test asserting `probeBase`
    said `const: exempt`, while the two concrete probes — the ones that do the
    validating — could have been widened to `["exempt", "bearer"]` and the whole
    suite stayed green. An orphan in a schema is a rule that is not a rule, which
    is the one thing this repository exists to prevent.
    """
    for path in telemetry_schema_paths():
        raw = path.read_text(encoding="utf-8")
        schema = load_schema(path)
        for name in schema.get("$defs", {}):
            assert f"#/$defs/{name}" in raw, (
                f"{path.name} defines $defs/{name} but nothing references it. "
                "Either $ref it from the branch that validates, or delete it — an "
                "unreferenced definition is a rule that enforces nothing while "
                "looking like one."
            )


# --- 8.1 span naming -------------------------------------------------------


def test_span_name_examples_validate() -> None:
    for path in sorted(VALID_TELEMETRY.glob("span-naming.*.json")):
        found = failures_for(load_document(path), load_schema(SPAN_NAMING_SCHEMA_PATH))
        assert not found, f"{path.name} must validate:\n  " + "\n  ".join(str(f) for f in found)


def test_span_names_are_low_cardinality_by_construction() -> None:
    """One scheme, six languages, and a name that cannot carry an identifier.

    The rejected list is the point. `GET /users/:id` and `get_user` are what a
    fleet produces when nobody has said what a span is called, and
    `muse.user.usr_01J9Z8QK5M4N7P2R3T6V8W9X0A` is worse: it is a cardinality
    bomb that reads as diligence in review, and it only fails once something
    aggregates on it.
    """
    pattern = span_naming_pattern()
    for accepted in ACCEPTED_SPAN_NAMES:
        assert re.fullmatch(pattern, accepted), f"{accepted} must be a legal span name"
    for rejected in REJECTED_SPAN_NAMES:
        assert not re.fullmatch(pattern, rejected), (
            f"{rejected!r} must be rejected by the span-name grammar"
        )


def test_the_span_name_grammar_is_lowercase_dotted_snake() -> None:
    """`<service>.<operation>[.<target>]` — the same shape as an event type.

    The prefix is mandatory and is the service's own name, so a span aggregates
    fleet-wide without a join and a span name is never ambiguous about which
    service produced it. Same rule as `<service>.<entity>.<action>`, and for the
    same reason: an unprefixed name says what happened and not who did it.
    """
    pattern = span_naming_pattern()
    assert pattern.count("\\.") >= 1, "the grammar must allow a dotted name"
    for two_segment in ("muse.request", "guard.request.authorize"):
        assert re.fullmatch(pattern, two_segment), two_segment
    for unprefixed in ("provider.call", "db.query"):
        # Indistinguishable from a prefixed two-segment name by shape — only the
        # service vocabulary separates `muse.route` from `courier.route` — so this
        # asserts they are legal *shapes*. The check that a name really names a
        # real service is test_span_names_name_a_service_the_fleet_has.
        assert re.fullmatch(pattern, unprefixed), (
            f"{unprefixed!r} is a legal span-name shape; if this fails the grammar "
            "has changed and ACCEPTED/REJECTED_SPAN_NAMES need re-reading"
        )
    for unprefixed in ("request", "route", "call", "query", "deliver", "publish"):
        assert not re.fullmatch(pattern, unprefixed), (
            f"{unprefixed!r} has no service prefix; every span names its service "
            "first, so a query never has to guess which of six services to "
            "attribute it to"
        )
    # A segment never starts with a digit or a dash, and never contains a run of
    # characters that could be an id: the grammar cannot tell `usr_01J9Z8` from
    # `muse` by shape, so it excludes digits after the first character instead.
    for numeric in ("muse.1request", "muse.request.2", "guard.2026.request"):
        assert not re.fullmatch(pattern, numeric), (
            f"{numeric!r} embeds a number where the grammar wants a word"
        )


def test_span_names_name_a_service_the_fleet_has() -> None:
    """The prefix is a cafaye service name, not a word that looks like one.

    The grammar cannot tell `muse.route` from `courier.route` — both are two
    legal dotted words — so the check that the prefix is a *real* service is a
    cross-reference against fleet.yml, the same way `test_published_event_types_
    carry_their_own_service_prefix` checks an event's first segment. Without it,
    a span named `apiserver.request` would validate and be invisible to every
    fleet-wide query, which is the failure this whole rule exists to prevent.
    """
    known = set(fleet_published())
    for path in sorted(VALID_TELEMETRY.glob("span-naming.*.json")):
        document = load_document(path)
        service = document["service"]
        assert service in known, (
            f"{path.name} names service {service!r}, which fleet.yml does not "
            f"declare. Known: {sorted(known)}"
        )
        assert document["name"].split(".")[0] == service, (
            f"{path.name}: {document['name']} must start with its own service name "
            f"({service}.…)"
        )


def test_span_name_length_is_bounded() -> None:
    """A name long enough to hold an id is a name that will.

    120 characters is generous for `<service>.<operation>.<target>` — the longest
    legal name here is 28 — and it is a cap rather than a convention because a
    convention is what a code review enforces, and a code review does not count
    characters.
    """
    schema = load_schema(SPAN_NAMING_SCHEMA_PATH)["$defs"]["spanName"]
    assert schema["maxLength"] == 120, f"the span-name cap moved: {schema['maxLength']}"


def test_the_span_name_pattern_is_shared_with_the_traces_schema() -> None:
    """A span name the traces schema would accept and the naming schema would
    not is a span name core contradicts itself about."""
    naming = load_schema(SPAN_NAMING_SCHEMA_PATH)["$defs"]["spanName"]["pattern"]
    traces = load_schema(TRACES_SCHEMA_PATH)["$defs"]["spanName"]["pattern"]
    assert naming == traces, (
        "the span-name pattern is duplicated in span-naming.schema.json and "
        "traces.schema.json; change one, change both"
    )


def test_a_non_conforming_span_name_is_rejected() -> None:
    """The negative example, and it fails for the reason the README lists."""
    schema = load_schema(SPAN_NAMING_SCHEMA_PATH)
    for path in sorted(INVALID_TELEMETRY.glob("span-naming.*.json")):
        found = failures_for(load_document(path), schema)
        assert found, f"{path.name} is supposed to be rejected by the schema"
        # A span name with a value interpolated into it. The rejection is a
        # `pattern`, and it is a pattern because the length bound in the grammar
        # is what refuses a 32-character id — core has no cafaye-id pattern to
        # reach for and must not grow one.
        assert_keywords(found, (("pattern", "name"),))


# --- 8.2 the attribute allowlist, per signal -------------------------------


def test_every_signal_declares_an_allowlist() -> None:
    for signal, expected in SIGNAL_ALLOWLISTS.items():
        allowlist = signal_allowlist(signal)
        assert allowlist == set(expected), (
            f"the {signal} attribute allowlist changed.\n"
            f"  expected: {sorted(expected)}\n"
            f"  found:    {sorted(allowlist)}\n"
            "A new attribute is a spec change: add it to the schema, the doc table "
            "and this list in the same commit, and say why it cannot carry content."
        )


def test_no_allowlisted_attribute_name_carries_content() -> None:
    """The redaction boundary, as a property of the allowlist itself.

    This is muse's canary promoted to a spec-level assertion. `muse/tests/
    test_trace_propagation.py` checks that no name in muse's
    `ALLOWED_SPAN_ATTRIBUTES` contains any of these words; core asserts the same
    for the fleet, and for all three signals rather than one service's. The
    realistic leak is not an attacker — it is a well-meaning `muse.prompt` added
    in six months by someone debugging a routing decision, in a service whose
    prompts are other customers' data.
    """
    for signal in ("traces", "metrics", "logs"):
        for name in sorted(signal_allowlist(signal)):
            lowered = name.lower()
            found = [word for word in FORBIDDEN_ATTRIBUTE_NAME_WORDS if word in lowered]
            assert not found, (
                f"{signal} allowlists {name!r}, whose name contains {found}. An "
                "attribute whose *name* names content is one a caller can put "
                "content in, and the collector cannot tell which values are safe "
                "without a schema it does not have."
            )


def test_the_three_signals_do_not_spell_one_attribute_three_ways() -> None:
    """The same fact is the same attribute name on every signal.

    `http.route` on a trace and `route` on a metric is a query that returns
    nothing, and nothing detects it — the same shape of failure as courier's
    two-segment event types, so it gets the same kind of check. The assertion is
    deliberately about attributes that appear on *more than one* signal:
    `db.operation` and `messaging.operation` are two different facts that happen
    to share a last word, which is fine, and conflating them would be a test
    that cries wolf.
    """
    shared: dict[str, dict[str, str]] = {}
    for signal in ("traces", "metrics", "logs"):
        for name in signal_allowlist(signal):
            shared.setdefault(name, {})[signal] = name
    on_more_than_one = {name: where for name, where in shared.items() if len(where) > 1}
    assert on_more_than_one, "no attribute is shared between signals, so the check is vacuous"
    for name, where in sorted(on_more_than_one.items()):
        # A shared attribute is spelled identically everywhere by construction of
        # the dict keys — this asserts the intent rather than the accident, and
        # it is what fails if someone adds `http.route` to metrics as `route`.
        assert set(where.values()) == {name}, (
            f"{name} is carried by {where} — a fact on two signals must have one "
            "name, or a cross-signal query returns nothing and nothing reports it"
        )


# --- 8.3 the measurement-attribute prohibition ----------------------------


def test_prohibited_identifiers_are_not_measurement_attributes() -> None:
    """The rule with teeth: tenant_id on a metric is a failing test, not a note.

    OpenTelemetry caps a metric stream at 2000 distinct attribute combinations
    and, on overflow, folds everything into one `otel.metric.overflow=true` point
    and drops every measurement attribute. Totals stay correct; every
    per-dimension breakdown undercounts. That is the worst shape a bug can have,
    and the only defence is never putting an unbounded value on a measurement.
    """
    prohibited = set(measurement_attribute_names())
    for name in PROHIBITED_MEASUREMENT_ATTRIBUTES:
        assert name not in prohibited, (
            f"{name} is allowlisted as a measurement attribute. It is unbounded: "
            "one series per value, against a 2000-combination cap that then "
            "silently drops the attributes. It belongs on a resource attribute."
        )


def test_a_tenant_id_measurement_attribute_is_rejected() -> None:
    """The exact failure the directive names, asserted end to end on a document.

    Not a lint note: a real metric document with `tenant_id` on the measurement
    is rejected, and the rejection is asserted by keyword so a schema that
    stopped constraining it fails this test rather than passing quietly.
    """
    schema = load_schema(METRICS_SCHEMA_PATH)
    document = load_document(INVALID_TELEMETRY / "metric.tenant-id-measurement.invalid.json")
    found = failures_for(document, schema)
    assert found, "a tenant_id measurement attribute must be rejected"
    # Two independent violations, and the test asserts both: the name is not on
    # the allowlist (additionalProperties) and it is named in a `not` so that
    # adding it to the allowlist later does not quietly succeed. A rule enforced
    # once is a rule a well-meaning commit can undo.
    assert_keywords(
        found,
        (("not", "measurementAttributes"), ("additionalProperties", "measurementAttributes")),
    )
    # ... and the same document without the prohibited attribute is legal, so
    # this is a test about tenant_id and not about the metric being malformed.
    allowed = {**document, "measurementAttributes": {"http.route": "/v1/route"}}
    assert not failures_for(allowed, schema), (
        "the same metric with a bounded measurement attribute must validate"
    )


def test_every_prohibited_identifier_fails_the_measurement_schema() -> None:
    """The prohibition is a list, so the whole list is tested, not one member.

    A hand-written table of negative cases is the kind of list that rots: a name
    is added to the prohibition and nothing tests that it is actually rejected.
    """
    schema = load_schema(METRICS_SCHEMA_PATH)
    base = load_document(VALID_TELEMETRY / "metric.json")
    for name in PROHIBITED_MEASUREMENT_ATTRIBUTES:
        document = {**base, "measurementAttributes": {**base["measurementAttributes"], name: "x"}}
        found = failures_for(document, schema)
        assert found, f"{name} as a measurement attribute must be rejected"
        assert any(
            failure.path.endswith(name) or name in failure.message for failure in found
        ), f"{name} must be rejected for being {name}: {[str(f) for f in found]}"


def test_identity_lives_on_resource_attributes_which_are_exempt_from_the_cap() -> None:
    """The other half of the rule: the prohibition says *move it*, so say where.

    Resource attributes are attached once per process, not once per measurement,
    so the 2000-combination cap does not apply to them and they survive on the
    overflow point. That is the correct home for identity — and it is why the
    rule is a prohibition with a destination rather than a prohibition with a
    shrug.
    """
    resources = resource_attribute_names()
    for name in ("tenant_id", "account_id"):
        assert name in resources, (
            f"{name} must be an allowlisted resource attribute — the prohibition "
            "tells a service where the value goes, and this is where it goes"
        )
    assert resources & measurement_attribute_names() == set(), (
        "an attribute cannot be both a resource and a measurement attribute; "
        f"{sorted(resources & measurement_attribute_names())} is on both lists"
    )


def test_resource_attributes_cannot_be_put_on_a_measurement() -> None:
    """The asymmetry is the mechanism, so it is asserted rather than explained.

    Identity is queryable on every point *because* it is on the resource and not
    the measurement. Moving it to the measurement to get a per-tenant breakdown
    is the exact mistake that produces a dashboard which looks right and is
    wrong, so the schema refuses it rather than the doc warning about it.
    """
    schema = load_schema(METRICS_SCHEMA_PATH)
    for name in sorted(resource_attribute_names()):
        document = {
            "name": "http.server.request.duration",
            "unit": "s",
            "measurementAttributes": {name: "example"},
        }
        found = failures_for(document, schema)
        assert found, (
            f"{name} is a resource attribute and must not be accepted as a "
            "measurement attribute"
        )


def test_the_metric_schema_states_the_2000_combination_cap() -> None:
    """The number is in the schema, not only in the prose.

    A limit that lives in a README is a limit nobody checks, and this one is the
    reason the whole prohibition exists. The schema says it; the doc repeats it;
    `test_observability_doc_covers_every_required_topic` says it is not dropped.
    """
    text = METRICS_SCHEMA_PATH.read_text(encoding="utf-8")
    assert "2000" in text, "metrics.schema.json must state the 2000-combination cap"
    assert "otel.metric.overflow" in text, (
        "metrics.schema.json must name the overflow point the SDK folds into, so a "
        "reader who has never seen the failure still knows what is being prevented"
    )


# --- 8.4 the redaction boundary -------------------------------------------


def test_the_redaction_boundary_is_a_schema() -> None:
    """The boundary is a document, so kit's collector config and a service's SDK
    setup can both be checked against the same file.

    This is the shape the packet asks for: the allowlist is the spec, and the
    enforcement point is declared rather than implied, so "the collector is the
    chokepoint" is something a linter reads instead of something a reader
    believes.
    """
    document = load_document(VALID_TELEMETRY / "redaction.json")
    found = failures_for(document, load_schema(REDACTION_SCHEMA_PATH))
    assert not found, "the valid redaction policy must validate:\n  " + "\n  ".join(
        str(f) for f in found
    )
    assert document["enforcedAt"] == "collector", (
        "PLAN.md §7b puts enforcement at the collector as one chokepoint; a policy "
        "that disagrees with the plan has to argue for it in DECISIONS.md"
    )
    assert document["default"] == "deny", "the boundary is default-deny, not default-allow"


def test_the_redaction_policy_never_allowlists_a_content_attribute() -> None:
    schema = load_schema(REDACTION_SCHEMA_PATH)
    policy = load_document(VALID_TELEMETRY / "redaction.json")
    for allowed in policy["allowed"]:
        for word in FORBIDDEN_ATTRIBUTE_NAME_WORDS:
            assert word not in allowed.lower(), (
                f"the redaction policy allowlists {allowed!r}, which names content"
            )
    # ... and the policy's own negative case is a prompt-content attribute, which
    # is the leak the packet exists to prevent.
    found = failures_for(
        load_document(INVALID_TELEMETRY / "redaction.prompt-attribute.invalid.json"), schema
    )
    assert found, "a prompt-content attribute must be rejected by the redaction policy"
    # Matched on the name rather than on an index: which slot `llm.prompt` sits in
    # is an editorial choice, and a test that breaks when the list is reordered
    # is a test that gets "fixed" by deleting the attribute.
    assert any(
        failure.keyword == "not" and "llm.prompt" in failure.message for failure in found
    ), f"llm.prompt must be rejected by name: {[str(f) for f in found]}"


def test_the_redaction_policy_separates_the_may_record_from_the_may_not() -> None:
    """Both halves are in the file, because an allowlist with no stated subject is
    a list somebody has to guess the meaning of.

    The may-record side is the packet's own list: token counts, model id,
    latency, status, finish reason. A redaction policy that only says "not
    content" is a policy nobody can implement, because it does not say what
    replaces the thing they wanted to record.
    """
    policy = load_document(VALID_TELEMETRY / "redaction.json")
    recorded = {tuple(entry) for entry in policy["llmCallAttributes"]}
    for required in (
        ("llm.model", "string"),
        ("llm.tokens_in", "int"),
        ("llm.tokens_out", "int"),
        ("llm.latency_ms", "number"),
        ("llm.finish_reason", "string"),
    ):
        assert required in recorded, (
            f"the redaction policy must state what may be recorded about an LLM "
            f"call; {required[0]} is missing"
        )
    for entry in policy["prohibited"]:
        # `prohibited` is a list of attribute NAMES and `neverRecord` is a list of
        # SUBJECTS, so they cannot be equal — `gen_ai.prompt` and `prompt` are the
        # same prohibition in two vocabularies. What must hold is that every
        # prohibited name is a spelling of something neverRecord names, or the two
        # lists drift into disagreeing about what is forbidden. Plurals are folded,
        # because `llm.messages` and "message content" are one subject and not two.
        def stem(word: str) -> str:
            return word[:-1] if len(word) > 3 and word.endswith("s") else word

        words = {stem(word) for word in re.split(r"[^a-z0-9]+", entry.lower())} - {""}
        subjects = [
            {stem(word) for word in re.split(r"[^a-z0-9]+", item.lower())}
            for item in policy["neverRecord"]
        ]
        assert any(words & subject for subject in subjects), (
            f"{entry!r} is named as prohibited but names no subject in neverRecord, "
            f"so the two lists can disagree. neverRecord: {policy['neverRecord']}"
        )


def test_error_message_is_not_on_any_allowlist() -> None:
    """`error.message` is the one attribute that could carry a prompt.

    A vendor's content-policy rejection quotes the offending content back at
    you, so the error text is third-party text that may contain a customer's
    prompt. `error.type` answers "what kind of failure" with no content in it.
    muse already made this call and its canary asserts it end to end; core
    states it so all six services make the same one.
    """
    for signal in ("traces", "metrics", "logs"):
        assert "error.message" not in signal_allowlist(signal), (
            f"error.message is allowlisted on {signal}. A provider's error text "
            "quotes the offending content back, so it is a prompt by another route."
        )
        assert "error.type" in signal_allowlist(signal) or signal == "logs", (
            f"{signal} must carry error.type instead — the class, never the message"
        )


def test_error_type_is_a_bounded_vocabulary() -> None:
    """The grouping key for every error in the fleet, so it has to be a class.

    The user asked whether there is one place to see all errors for the whole
    system (PLAN.md §7b); the answer is yes, and this is the part of the spec
    that makes it true. `error.type` is a low-cardinality class — never a
    message, never a stack trace, never an interpolated value.
    """
    for signal in ("traces", "metrics"):
        filename, definition = ALLOWLIST_DEF[signal]
        schema = load_schema(TELEMETRY_SCHEMAS / filename)
        error_type = schema["$defs"][definition]["properties"]["error.type"]
        assert error_type["maxLength"] == 64, (
            "error.type is a class, not a sentence; the cap is what makes it one"
        )
        assert "enum" in error_type or "pattern" in error_type, (
            "error.type must be constrained to a class shape, not left as a free "
            "string — a free string here is a cardinality bomb on the metric side"
        )
    document = load_document(VALID_TELEMETRY / "span.muse.json")
    assert document["attributes"]["error.type"] == "provider_auth", (
        "the valid example must use a class, not a message"
    )


def test_observability_doc_covers_every_required_topic() -> None:
    doc = OBSERVABILITY_DOC.read_text(encoding="utf-8").lower()
    for topics, label in (
        (REQUIRED_ENDPOINT_TOPICS, "endpoint"),
        (REQUIRED_REDACTION_TOPICS, "redaction"),
        (REQUIRED_HEALTH_TOPICS, "health"),
    ):
        missing = [topic for topic in topics if topic not in doc]
        assert not missing, f"docs/observability.md dropped from its {label} section: {missing}"


# --- 8.5 the endpoint contract and the no-op path --------------------------


def test_the_endpoint_contract_is_valid_and_closed() -> None:
    schema = load_schema(ENDPOINT_SCHEMA_PATH)
    found = failures_for(load_document(VALID_TELEMETRY / "otel-endpoint.json"), schema)
    assert not found, "the valid endpoint declaration must validate:\n  " + "\n  ".join(
        str(f) for f in found
    )


def test_unsetting_the_endpoint_declares_a_free_no_op() -> None:
    """The escape hatch is first-class, and "free" is four checkable properties.

    A disabled path that still dials out is worse than no telemetry support at
    all (PLAN.md §7b), so the schema does not accept the word "disabled": it
    accepts a declaration that says what does *not* happen. buffering, retry,
    warnings and startup cost are each `none`, and the shipped collector is a
    `default`, which is the only thing a default can be.

    Both halves are asserted — the *example* says `none` and the *schema* pins
    it to `none`. Asserting only the example would pass the moment someone
    widened the schema to an enum of `none` and `ring`, which is exactly the
    mutation that broke this test the first time it ran.
    """
    document = load_document(VALID_TELEMETRY / "otel-endpoint.json")
    no_op = document["noOp"]
    pinned = load_schema(ENDPOINT_SCHEMA_PATH)["properties"]["noOp"]["properties"]
    for key in ("buffering", "retry", "warnings", "startupCost"):
        assert no_op[key] == "none", (
            f"the no-op path must declare noOp.{key}: none. A disabled exporter "
            "that buffers, retries or logs is not a no-op, it is an outage with "
            "extra steps."
        )
        assert pinned[key] == {"const": "none", "description": pinned[key]["description"]}, (
            f"otel-endpoint.schema.json must pin noOp.{key} to const 'none', not "
            f"offer a choice: it currently declares {sorted(pinned[key])}"
        )
    assert document["endpoint"]["default"] == "http://otel-collector:4317", (
        "the shipped collector is the default *value* of the variable — the "
        "variable is the contract, and a self-hoster's Datadog is one env away"
    )
    assert document["endpoint"]["variable"] == "MUSE_OTEL_ENDPOINT", (
        "the variable name is <SERVICE>_OTEL_ENDPOINT, uppercase, and it is the "
        "only contract a self-hoster has to know"
    )


def test_the_endpoint_is_never_required() -> None:
    """The `const: false` that separates on-by-default from mandatory.

    Asserted on the schema, not only on the example. This is the field that
    makes a self-hoster's first question — "what does this look like when it
    breaks" — answerable without installing four more services first
    (PLAN.md §7b), and a schema that merely permits `false` is a schema where
    one service will eventually declare `true`.
    """
    required = load_schema(ENDPOINT_SCHEMA_PATH)["properties"]["endpoint"]["properties"]["required"]
    assert required.get("const") is False, (
        f"endpoint.required must be const: false, not {required!r} — observability "
        "is on by default and optional in fact"
    )


def test_an_endpoint_declaration_that_is_not_a_free_no_op_is_rejected() -> None:
    """The negative case: buffering, retrying and warning on the disabled path."""
    schema = load_schema(ENDPOINT_SCHEMA_PATH)
    found = failures_for(
        load_document(INVALID_TELEMETRY / "otel-endpoint.buffered.invalid.json"), schema
    )
    assert found, "a disabled exporter that buffers must be rejected"
    assert_keywords(
        found,
        (("const", "noOp/buffering"), ("const", "noOp/retry"), ("const", "noOp/warnings")),
    )


def test_the_no_op_path_uses_the_standards_own_switches() -> None:
    """`OTEL_SDK_DISABLED` is the OTel spec's own kill switch, and using it is
    what makes the no-op genuinely free in six languages.

    Re-implementing "disabled" in each language is how six services get six
    different definitions of it, and the difference between them is a background
    retry loop somebody finds in production. The spec defines the switch once:
    OTEL_SDK_DISABLED=true, plus per-signal OTEL_{TRACES,METRICS,LOGS}_EXPORTER=none.
    """
    text = ENDPOINT_SCHEMA_PATH.read_text(encoding="utf-8")
    for variable in ("OTEL_SDK_DISABLED", "OTEL_TRACES_EXPORTER", "OTEL_METRICS_EXPORTER"):
        assert variable in text, (
            f"{variable} must be named in otel-endpoint.schema.json — the no-op path "
            "is the OTel spec's own switch, not a cafaye invention"
        )
    # The schema pins the switch, not merely mentions it. An enum that also
    # accepted a cafaye-specific switch would let a service re-implement
    # "disabled", which is the whole thing this rule exists to prevent.
    implemented_by = load_schema(ENDPOINT_SCHEMA_PATH)["properties"]["noOp"]["properties"][
        "implementedBy"
    ]
    assert implemented_by.get("const") == "OTEL_SDK_DISABLED", (
        f"noOp.implementedBy must be const OTEL_SDK_DISABLED, not {implemented_by!r}"
    )
    disabled_by = load_schema(ENDPOINT_SCHEMA_PATH)["properties"]["disabledBy"]
    assert set(disabled_by["required"]) == {"global", "traces", "metrics", "logs"}, (
        f"disabledBy must require all four switches, got {sorted(disabled_by['required'])}"
    )
    document = load_document(VALID_TELEMETRY / "otel-endpoint.json")
    assert document["noOp"]["implementedBy"] == "OTEL_SDK_DISABLED", (
        "the no-op must be implemented by the standard switch, so a service that "
        "sets it gets the spec's behaviour rather than ours"
    )


def test_every_signal_has_an_exporter_switch() -> None:
    """Unsetting the endpoint is the documented path; the switches are the
    belt-and-braces one, and both have to exist for all three signals.

    A no-op that only covers traces is a service that still phones home for
    metrics, which is the failure that gets discovered by a customer's bill
    rather than by a test.
    """
    document = load_document(VALID_TELEMETRY / "otel-endpoint.json")
    assert sorted(document["signals"]) == ["logs", "metrics", "traces"], (
        "all three signals are in scope; a service that exports one and disables "
        "another is the case this list exists to catch"
    )
    for signal in document["signals"]:
        assert signal in document["disabledBy"], (
            f"{signal} has no documented way to turn it off"
        )


# --- 8.6 healthz vs readyz ------------------------------------------------


def test_the_probe_contract_is_valid() -> None:
    found = failures_for(load_document(PROBE_EXAMPLE), load_schema(PROBES_SCHEMA_PATH))
    assert not found, "the valid probe declaration must validate:\n  " + "\n  ".join(
        str(f) for f in found
    )


def test_a_readyz_that_checks_nothing_is_rejected() -> None:
    """The rule the packet names, asserted as a failing test.

    darkroom is the pattern (`/healthz` never touches a dependency, `/readyz`
    really runs `select 1`), and without the schema a `readyz` that returns a
    constant 200 is a load balancer cheerfully routing traffic into a service
    whose database is gone.
    """
    found = failures_for(
        load_document(INVALID_PROBE_EXAMPLE), load_schema(PROBES_SCHEMA_PATH)
    )
    assert found, "a readyz with no dependency checks must be rejected"
    assert_keywords(found, (("minItems", "readyz/checks"),))


def test_healthz_is_unconditional_and_readyz_is_not() -> None:
    """The split, as a shape: `healthz.checks` is empty and `readyz.checks` is not.

    Asserted on the valid example in both directions, because the interesting
    failure is the symmetric one — a `healthz` that consults the database turns
    an outage into a restart loop, which is worse than the outage. And asserted
    on the *schema* as well as the example, because a schema that stops pinning
    liveness to an empty list still accepts this example unchanged.
    """
    document = load_document(PROBE_EXAMPLE)
    assert document["healthz"]["checks"] == [], (
        "healthz is unconditional liveness. A dependency check here means a dead "
        "database restarts every container that depends on it."
    )
    assert document["readyz"]["checks"], (
        "readyz must actually check something; an empty checks list is the failure "
        "the probes schema exists to reject"
    )
    for check in document["readyz"]["checks"]:
        assert check["dependency"], f"a readiness check of {check['name']} checks nothing"
    defs = load_schema(PROBES_SCHEMA_PATH)["$defs"]
    assert defs["livenessProbe"]["properties"]["checks"]["maxItems"] == 0, (
        "probes.schema.json must pin healthz.checks to maxItems: 0, so a liveness "
        "probe that starts consulting a dependency cannot validate"
    )
    assert defs["readinessProbe"]["properties"]["checks"]["minItems"] == 1, (
        "probes.schema.json must pin readyz.checks to minItems: 1, so a readiness "
        "probe that checks nothing cannot validate"
    )


def test_both_probes_are_exempt_from_authentication() -> None:
    """darkroom's lesson, in its README: a `/healthz` behind the auth middleware
    returns 401, every instance is marked unhealthy, and the deploy rolls back
    with no indication why. Asserted because it is a fleet-wide trap — and
    asserted on the schema, since an example that says `exempt` survives a schema
    that stopped requiring it."""
    document = load_document(PROBE_EXAMPLE)
    for probe in ("healthz", "readyz"):
        assert document[probe]["auth"] == "exempt", (
            f"{probe} must be exempt from authentication by an explicit allow-list, "
            "not by route ordering"
        )
    defs = load_schema(PROBES_SCHEMA_PATH)["$defs"]
    for probe in ("livenessProbe", "readinessProbe"):
        auth = defs[probe]["properties"]["auth"]
        assert auth.get("const") == "exempt", (
            f"{probe}.auth must be const 'exempt', not {auth!r} — a probe behind the "
            "auth middleware returns 401 and the deploy rolls back with no "
            "indication why"
        )


# --- 8.7 fleet-wide consistency -------------------------------------------


def test_fleet_services_declare_their_telemetry_signals() -> None:
    """fleet.yml records what a service exports, so the endpoint variable is
    checkable fleet-wide.

    A service whose manifest is silent about telemetry is not thereby forbidden
    from exporting it, so this asserts the weaker and more useful thing: every
    service that ships a `cafaye.yml` and serves HTTP declares the probe
    contract, so "which services have observability" has one answer.
    """
    for service in load_fleet()["services"]:
        name = service["name"]
        telemetry = service.get("telemetry")
        assert telemetry is not None, (
            f"fleet.yml: {name} declares no telemetry block. Every service that "
            "serves HTTP owes the probe contract and the endpoint variable name; "
            "record it here so the fleet answer to 'what is instrumented' is one read."
        )
        assert telemetry["endpointVariable"] == f"{name.upper()}_OTEL_ENDPOINT", (
            f"fleet.yml: {name} must use {name.upper()}_OTEL_ENDPOINT — one variable "
            "name across the fleet, whatever the service is called"
        )
        for signal in telemetry.get("signals", []):
            assert signal in ("traces", "metrics", "logs"), (
                f"fleet.yml: {name} declares unknown signal {signal!r}"
            )


def test_observability_is_on_by_default_but_turning_it_off_is_documented() -> None:
    """The directive, both halves, as a checkable pair.

    "On by default and worked on in dev" and "unsetting it is a tested no-op"
    are in tension unless the default is a *value* rather than a requirement,
    which is exactly what the schema pins: the shipped collector is the default
    endpoint, and nothing requires it.
    """
    document = load_document(VALID_TELEMETRY / "otel-endpoint.json")
    assert document["endpoint"]["required"] is False, (
        "observability is on by default and optional in fact; a declaration that "
        "makes the endpoint required turns the default into a requirement"
    )
    assert document["endpoint"]["default"], (
        "there is a shipped default, so a developer sees real traces without "
        "turning anything on (PLAN.md §7b)"
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
