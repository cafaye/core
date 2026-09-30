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

import ast
import copy
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
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

# The gate declaration (core-09). One file per repository at its root, the
# schema the fleet writes it against, the checker that compares the declaration
# to the repository, and the red proof that the checker is able to fail. See
# docs/gate.md — and for the two alternatives that were measured
# and rejected — a mise task alone cannot be checked, and a CI workflow alone
# lets the local gate and the CI gate drift apart. The harness constants are
# spelled `REPO / "harness"` rather than `HARNESS` because the harness's own
# constant block sits further down this file, and a constant reading a name
# defined later in the module is a module that only imports on a good day.
GATE_SCHEMA_PATH = SCHEMAS / "gate.schema.json"
GATE_DECLARATION = REPO / "gate.yml"
GATE_DOC = DOCS / "gate.md"
GATE_CHECK = REPO / "harness" / "gate_check.py"
GATE_WRAPPER = REPO / "harness" / "bin" / "gate-check"
GATE_FINDINGS = REPO / "harness" / "gate_findings.json"
GATE_SELF_TEST = REPO / "harness" / "tests" / "gate_self_test.sh"
GATE_FIXTURE = REPO / "harness" / "tests" / "fixtures" / "gates" / "conforming"

VALID_GATES = (VALID_EXAMPLES / "gate.self-contained.yml", VALID_EXAMPLES / "gate.external.yml")
INVALID_GATES = {
    "gate.no-proof.yml": (("minItems", "gate/proof"),),
    "gate.shell-string.yml": (("not", "gate/command/0"),),
    "gate.requirement-without-command.yml": (
        ("required", "external/requirements/0/satisfy"),
    ),
    "gate.undeclared-key.yml": (("additionalProperties", ""),),
}

# The checker's exit codes. Named here so a change to the contract is a change
# to a test, exactly as the harness's are. `EXIT_COULD_NOT_RUN` is the one that
# matters most: a check that could not read the declaration has not checked the
# gate, and reporting that as 0 is the defect this whole section exists to end.
GATE_EXIT_OK = 0
GATE_EXIT_FAIL = 1
GATE_EXIT_COULD_NOT_RUN = 2

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

# The error CLASS vocabulary (D14, ratified by the manager). Twelve classes plus
# the OTel well-known fallback, and the closed set is the rule: a `pattern` is a
# SHAPE, and a shape admits `user_42_email_invalid`, which is the cardinality
# bomb the attribute exists to prevent. This list is asserted against all three
# schemas, against the examples, and against the docs table, so a class cannot be
# added in one place and forgotten in the others.
#
# A class earns its place when its rate is worth an alert on its own — which is
# the test D14 sets, and which is why there are twelve and not sixty. What timed
# out, which provider, which table: those are span names and attributes, never
# part of the class. "Around a dozen" is a bound the suite enforces, because a
# vocabulary that grows one class per incident stops grouping anything.
ERROR_CLASSES = (
    "_OTHER",
    "cancelled",
    "circuit_open",
    "conflict",
    "connection_failed",
    "dependency_unavailable",
    "internal_error",
    "invalid_request",
    "policy_denied",
    "provider_auth",
    "provider_rejected",
    "rate_limited",
    "timeout",
)

#: How many classes the vocabulary may hold. D14 asks for "around a dozen" and
#: says "do not pad it", which is a judgement nobody makes twice the same way
#: under deadline — so it is a bound. Adding a class is a spec change with
#: alternatives and a cost, which is what DECISIONS.md is for.
MIN_ERROR_CLASSES = 10
MAX_ERROR_CLASSES = 16

#: The shape every class but `_OTHER` is, byte-identical on all three signals.
#: Kept alongside the enum rather than instead of it: the enum is the rule and
#: this is the second line, and a rule enforced once is a rule a well-meaning
#: commit can undo. It cannot reject a value the enum accepts, so it can never
#: cause a false rejection.
ERROR_CLASS_SHAPE = "^([a-z][a-z0-9]*(_[a-z0-9]+)*|_OTHER)$"

# Words that would name a *handled* or *retried* attempt. The semconv rule is
# SHOULD NOT — handled and retried errors are not recorded at all, because a
# retry that succeeded is not an error and recording it makes the error rate a
# lie. `SHOULD NOT` cannot be a schema keyword, so it is encoded as the thing
# that makes it unrepresentable: there is no attribute on any signal on which a
# service could say "this attempt failed and I recovered", so there is nothing
# to set to a true value. Same shape as the content-word rule, and for the same
# reason — the realistic violation is a well-meaning `error.handled: true` added
# in six months, not an attacker.
FORBIDDEN_ERROR_LIFECYCLE_WORDS = (
    "retry",
    "retried",
    "retriable",
    "attempt",
    "handled",
    "recovered",
    "suppressed",
)

# The rules the research behind PLAN.md §7b established and that core-04
# described without encoding. If a doc edit drops one of these the suite says so,
# because a rule that lives only in a paragraph is a wish (AGENTS.md).
REQUIRED_ERROR_RECORDING_TOPICS = (
    "absent on success",
    "identical on the span and on the metric",
    "not recorded at all",
    "a retry that succeeded",
    "obliges",
    "span status",
    "_other",
    "not classified its own errors",
    "service.name filter",
    "never a global grouping key",
    "recording-errors.md",
)

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

# --------------------------------------------------------------------------
# the contract-test harness (PLAN.md §4, Phase 0)
# --------------------------------------------------------------------------

# core-07 built the harness PLAN.md §4 Phase 0 named and that no packet had
# built: a service validating itself against core's contracts using something
# core ships. It lives in `harness/`, it runs offline against a checkout or a
# pinned ref of core, it exits non-zero rather than skipping when it cannot find
# the contract, and it is proved able to fail by `harness/tests/self_test.sh`.
#
# The harness is executable code in a specification repository, which is the line
# AGENTS.md draws — so the tests in section 7 are mostly about the two ways that
# can go wrong. A harness that cannot fail converts an unknown into a green
# badge, and a hand-written JSON Schema reader that disagrees with the real one
# makes core enforce something other than what it published. Both are checkable,
# so both are checked.
HARNESS = REPO / "harness"
HARNESS_MODULE = HARNESS / "cafaye_contract.py"
HARNESS_WRAPPER = HARNESS / "bin" / "cafaye-contract"
HARNESS_RULES = HARNESS / "rules.json"
HARNESS_SELF_TEST = HARNESS / "tests" / "self_test.sh"
HARNESS_FIXTURES = HARNESS / "tests" / "fixtures"
HARNESS_DOC = DOCS / "contract-harness.md"

# Exit codes the harness promises. `0` is the only one that means "conforms",
# and the whole point of the section is that a run which could not happen is not
# one of them. Named here so a change to the contract is a change to a test.
HARNESS_EXIT_CONFORMS = 0
HARNESS_EXIT_VIOLATIONS = 1
HARNESS_EXIT_REFUSED = 2

# The digest format: a sha256 over the contract surface, hex, lowercase.
HARNESS_DIGEST_PATTERN = re.compile(r"^[0-9a-f]{64}$")

# Every rule the harness reports on a non-conforming manifest. Asserted as an
# exact set, not a superset: a harness that reports three of four and exits 0 is
# the failure this whole section exists to prevent, and "at least these" is the
# assertion shape that would let it through.
NONCONFORMING_CONVENTION_RULES = frozenset(
    {
        "event.own-prefix",
        "event.unknown-consumed",
        "event.unknown-published",
        "event.payload-schema-missing",
        "manifest.api-file-missing",
    }
)

# The four OpenAPI rules a single document can break, from the fixture that
# breaks all four at once.
NONCONFORMING_OPENAPI_RULES = frozenset(
    {
        "openapi.document-is-31",
        "openapi.info-version",
        "openapi.paths-are-versioned",
        "openapi.one-version-prefix",
    }
)

# Keywords whose value is a *map of name to schema*. The distinction matters
# for `_collect_keywords`: without it a schema walk counts property names as
# keywords, and the harness is then "missing" a keyword called `team`.
SCHEMA_MAP_KEYWORDS = frozenset({"properties", "patternProperties", "$defs", "dependentSchemas"})

# Keywords whose value is a single schema.
SUBSCHEMA_KEYWORDS = frozenset(
    {"items", "additionalProperties", "not", "if", "then", "contains", "propertyNames"}
)

# Keywords whose value is a list of schemas.
SUBSCHEMA_LIST_KEYWORDS = frozenset({"allOf", "anyOf", "oneOf", "prefixItems"})

# The module names the harness may import. `core`'s rule is that this repository
# has no dependencies, and the harness is the piece of executable code where
# that rule is easiest to break by accident: a `pip install` that makes one
# check pass locally and 404 in a Go service's container.
HARNESS_STDLIB_ONLY = frozenset(
    {
        "argparse", "dataclasses", "hashlib", "json", "os", "pathlib", "re",
        "shutil", "subprocess", "sys", "typing", "unicodedata", "uuid",
    }
)

# --------------------------------------------------------------------------
# 9. the SLO and error-budget spec (PLAN.md §7b)
# --------------------------------------------------------------------------

# What an SLO *is* in cafaye is three schemas and one document. The declaration
# a service commits (slo.schema.json), the burn-rate window catalog that is pinned
# once in core and may not be overridden per service (slo-windows.schema.json),
# and the SLI allowlist that replaces a shared client library across six
# languages (slo-metrics.schema.json). See docs/slo.md.
SLO_SCHEMA_PATH = TELEMETRY_SCHEMAS / "slo.schema.json"
SLO_WINDOWS_SCHEMA_PATH = TELEMETRY_SCHEMAS / "slo-windows.schema.json"
SLO_METRICS_SCHEMA_PATH = TELEMETRY_SCHEMAS / "slo-metrics.schema.json"
SLO_DOC = DOCS / "slo.md"

VALID_SLO = VALID_TELEMETRY / "slo.yaml"
VALID_SLO_WINDOWS = VALID_TELEMETRY / "slo-windows.yaml"

INVALID_SLO_PERFECT = INVALID_TELEMETRY / "slo.perfect.invalid.yaml"
INVALID_SLO_PAGE_ON_LOW = INVALID_TELEMETRY / "slo.page-on-low-tier.invalid.yaml"
INVALID_SLO_WINDOW_OVERRIDE = INVALID_TELEMETRY / "slo.window-override.invalid.yaml"
INVALID_SLO_DENYLISTED = INVALID_TELEMETRY / "slo-metrics.denylisted.invalid.json"

#: R4. What the tier decides, and the only thing it decides: whether a page is
#: generated. `(page_alert.disable, ticket_alert.disable)`, and the test builds
#: both the conforming document and its two inversions for every tier rather
#: than asserting the table is in the schema — a test that reads a table back out
#: of the file it is testing proves the file can spell itself.
SLO_TIER_ALERTS = {
    "critical": (False, False),
    "high": (False, False),
    "low": (True, False),
    "none": (True, True),
}

#: R2. The SRE workbook's windows, in the order Sloth consumes them: short window
#: then long window, four pairs. **14.4 is not 15** — it is 2% of a 28-day budget
#: measured in hours — and `test_the_window_catalog_is_the_workbooks_numbers`
#: recomputes that arithmetic rather than quoting the number.
SLO_WINDOW_CATALOG = (
    ("5m", 14.4), ("1h", 14.4),
    ("30m", 6.0), ("6h", 6.0),
    ("2h", 3.0), ("1d", 3.0),
    ("6h", 1.0), ("3d", 1.0),
)
SLO_BUDGET_FRACTION = 0.02
SLO_PERIOD = "28d"
SLO_PERIOD_HOURS = 28 * 24
#: The budget the workbook's factors were derived against, which is **not** the
#: period above. 14.4 is 2% of 720 hours, and 720 hours is thirty days; under the
#: 28-day period R3 mandates, 2% of the budget is 13.44. Both numbers are in the
#: schema and the difference is the direction it errs in, so the test asserts
#: the discrepancy rather than papering over it — see D27.
SLO_WORKBOOK_HOURS = 30 * 24
SLO_WINDOW_TOKEN = "{{.window}}"

#: R6. The SLIs a service may declare, and the four candidates the spec ships
#: already written out: the HTTP base every one is built on, authentication, the
#: outbox, the email and the invoice. Named after the *operation*, never after a
#: service — a catalogue entry that said "identity" would be an SLO for identity
#: written by a packet that was told not to write one.
SLO_CATALOG_ENTRIES = (
    "http_server_availability",
    "authentication_succeeds",
    "event_accepted_into_outbox",
    "email_dispatched",
    "invoice_computed",
)

#: The two denylists, which are two prohibitions and not one list. Unbounded
#: dimensions are barred because metrics.schema.json bars them on the
#: 2000-combination cap; infrastructure signals are barred because an SLO on a
#: CPU is not an SLO on behaviour. A single merged list would lose the second
#: reason, and the reason is the one a reader has when they are about to add one.
SLO_UNBOUNDED_DIMENSIONS = ("tenant", "user_id", "account_id", "request_id")
SLO_INFRASTRUCTURE_SIGNALS = ("cpu", "memory", "pod", "restart")

#: The OTel -> Prometheus translation, as the exporter performs it: dots become
#: underscores, the UCUM unit is appended in the Prometheus spelling, and the
#: metric type is appended last. Declared here so the test that every catalogue
#: metric is the *normalization* of its OTel name is a derivation rather than a
#: second copy of the catalogue.
PROMETHEUS_UNIT_SUFFIXES = ("", "_seconds", "_milliseconds", "_bytes")
PROMETHEUS_TYPE_SUFFIXES = ("", "_total", "_count", "_bucket", "_sum")

#: The harness's SLO rules, and the fixture that breaks every one of them at
#: once. An exact set, for the reason `NONCONFORMING_CONVENTION_RULES` is: a
#: harness that reports six of eight and exits 0 has turned an unknown into a
#: pass, which is the one defect this whole repository exists to prevent.
NONCONFORMING_SLO_RULES = frozenset(
    {
        "slo.duplicate-name",
        "slo.no-infrastructure-slo",
        "slo.no-unbounded-dimension",
        "slo.schema",
        "slo.sli-canonical",
        "slo.unknown-metric",
        "slo.window-override",
        "slo.window-token",
    }
)

#: What `docs/slo.md` has to say, as the questions a reader arrives with. Each
#: one is a claim the schemas cannot make on their own: the artifact, the
#: arithmetic behind the threshold, the tier table, the multi-tenancy answer, the
#: spanmetrics migration, and the statement that there is no SLA.
SLO_DOC_TOPICS = (
    "prometheus/v1",
    "sloth",
    "{{.window}}",
    "error budget",
    "28 days",
    "14.4",
    "good events",
    "total events",
    "critical",
    "tier",
    "openslo",
    "template",
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
    for path in (
        MANIFEST_SCHEMA_PATH, ENVELOPE_SCHEMA_PATH, FLEET_SCHEMA_PATH, GATE_SCHEMA_PATH, *payload_schemas()
    ):
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


#: Which key each signal's example document carries its attributes under. Traces
#: and logs both call it `attributes`, so the discriminator has to be the schema a
#: file is registered against — deciding by reading the document is a document
#: that can be read two ways, and `log.json` is exactly that.
ATTRIBUTE_HOLDER = {
    TRACES_SCHEMA_PATH: "attributes",
    LOGS_SCHEMA_PATH: "attributes",
    METRICS_SCHEMA_PATH: "measurementAttributes",
}


def signal_allowlist(signal: str) -> set[str]:
    filename, definition = ALLOWLIST_DEF[signal]
    schema = load_schema(TELEMETRY_SCHEMAS / filename)
    return set(schema["$defs"][definition]["properties"])


def error_type_definition(signal: str) -> dict:
    """One signal's `error.type` constraint, as the schema states it.

    Not a hard-coded path per signal: `ALLOWLIST_DEF` already knows where each
    signal keeps its attributes, and a second table of paths is a second thing
    that can be wrong.
    """
    filename, definition = ALLOWLIST_DEF[signal]
    schema = load_schema(TELEMETRY_SCHEMAS / filename)
    return schema["$defs"][definition]["properties"]["error.type"]


#: Which schema each valid telemetry example is checked against. Keyed by file
#: name so an example nobody validates is a FAILING test rather than a file that
#: quietly stops being true: an unvalidated example is documentation nobody
#: checks, and two of these were orphaned when this table was written
#: (`log.json` and `metric.outbox.json` were read by no test at all).
TELEMETRY_EXAMPLE_SCHEMAS = {
    "span-naming.muse-provider-call.json": SPAN_NAMING_SCHEMA_PATH,
    "span-naming.muse-request.json": SPAN_NAMING_SCHEMA_PATH,
    "span-naming.identity-db-query.json": SPAN_NAMING_SCHEMA_PATH,
    "span.muse.json": TRACES_SCHEMA_PATH,
    "metric.json": METRICS_SCHEMA_PATH,
    "metric.outbox.json": METRICS_SCHEMA_PATH,
    "metric.error-type.json": METRICS_SCHEMA_PATH,
    "log.json": LOGS_SCHEMA_PATH,
    "redaction.json": REDACTION_SCHEMA_PATH,
    "otel-endpoint.json": ENDPOINT_SCHEMA_PATH,
    "probes.json": PROBES_SCHEMA_PATH,
    # YAML, because the artifact the brief makes the checked one is a Sloth
    # `prometheus/v1` file: `sloth validate -i <dir>` walks a directory of YAML,
    # so an SLO example in any other format would be an example of something
    # nobody validates.
    "slo.yaml": SLO_SCHEMA_PATH,
    "slo-windows.yaml": SLO_WINDOWS_SCHEMA_PATH,
    # One span per class in the error vocabulary, so the vocabulary is a
    # directory a reviewer can read rather than a list they have to imagine:
    # `ls examples/valid/telemetry/error-type.*` is the whole set. `_OTHER` is
    # filed as `other.json` because a filename may not be mistaken for the value
    # it carries — the class is read out of each document by
    # test_every_declared_error_class_has_a_valid_example, never from the name,
    # so a misleading filename cannot hide a missing class.
    "error-type.invalid-request.json": TRACES_SCHEMA_PATH,
    "error-type.policy-denied.json": TRACES_SCHEMA_PATH,
    "error-type.provider-auth.json": TRACES_SCHEMA_PATH,
    "error-type.provider-rejected.json": TRACES_SCHEMA_PATH,
    "error-type.rate-limited.json": TRACES_SCHEMA_PATH,
    "error-type.timeout.json": TRACES_SCHEMA_PATH,
    "error-type.connection-failed.json": TRACES_SCHEMA_PATH,
    "error-type.circuit-open.json": TRACES_SCHEMA_PATH,
    "error-type.dependency-unavailable.json": TRACES_SCHEMA_PATH,
    "error-type.conflict.json": TRACES_SCHEMA_PATH,
    "error-type.cancelled.json": TRACES_SCHEMA_PATH,
    "error-type.internal-error.json": TRACES_SCHEMA_PATH,
    "error-type.other.json": TRACES_SCHEMA_PATH,
}


def test_every_valid_telemetry_example_is_validated_against_its_schema() -> None:
    """The positive half of the five-part rule, enforced as a set rather than per file.

    The per-file tests below assert more than validity — that `enforcedAt` is the
    collector, that the no-op is four `none`s — so they stay. This one answers
    the question none of them can: is there an example no test looks at? Found by
    grepping for each example's name in this file and finding two orphans.
    """
    present = {
        path.name
        for path in VALID_TELEMETRY.iterdir()
        if path.is_file() and path.suffix in {".json", ".yaml", ".yml"}
    }
    assert present == set(TELEMETRY_EXAMPLE_SCHEMAS), (
        "examples/valid/telemetry/ and TELEMETRY_EXAMPLE_SCHEMAS disagree.\n"
        f"  examples with no test: {sorted(present - set(TELEMETRY_EXAMPLE_SCHEMAS))}\n"
        f"  tests with no example: {sorted(set(TELEMETRY_EXAMPLE_SCHEMAS) - present)}"
    )
    for name, schema_path in sorted(TELEMETRY_EXAMPLE_SCHEMAS.items()):
        found = failures_for(
            load_document(VALID_TELEMETRY / name), load_schema(schema_path)
        )
        assert not found, (
            f"{name} must satisfy {schema_path.name}:\n  "
            + "\n  ".join(str(f) for f in found)
        )


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
        "slo.schema.json",
        "slo-windows.schema.json",
        "slo-metrics.schema.json",
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

    The `or "pattern" in error_type` this assertion used to allow is the exact
    hole this packet closes: a pattern constrains the SHAPE of the value and says
    nothing about the VOCABULARY, so `user_42_email_invalid` validated cleanly —
    snake_case, twenty-two characters, and precisely the cardinality bomb the
    attribute exists to prevent. It now requires an `enum`, on every signal.
    """
    for signal in ("traces", "metrics", "logs"):
        error_type = error_type_definition(signal)
        assert error_type.get("maxLength") == 64, (
            f"{signal}: error.type is a class, not a sentence; the cap is what "
            f"makes it one, and it is now {error_type.get('maxLength')}"
        )
        assert "enum" in error_type, (
            f"{signal}: error.type must be a CLOSED vocabulary, not a pattern. A "
            "pattern constrains the shape of the value and not the set of values, "
            "so a service that emits user_42_email_invalid passes — one series per "
            "value, against the same 2000-combination cap tenant_id blows. See D14."
        )
    document = load_document(VALID_TELEMETRY / "span.muse.json")
    assert document["attributes"]["error.type"] == "provider_auth", (
        "the valid example must use a class, not a message"
    )


def test_the_error_class_vocabulary_is_one_closed_enum_on_every_signal() -> None:
    """The same class means the same thing on traces and on metrics.

    A vocabulary that is three lists is three taxonomies, which is the thing D14
    exists to prevent: `ProviderAuthError` in Python and `ErrProviderAuth` in Go
    are one failure in two spellings, and "one place to see all errors" becomes
    six places that need a mapping table to join. It also makes the semconv rule
    that `error.type` is *identical* on a span and on its corresponding metric
    enforceable at all — if the two sides could name the same failure differently
    there would be nothing to compare.
    """
    for signal in ("traces", "metrics", "logs"):
        declared = tuple(error_type_definition(signal).get("enum", ()))
        assert set(declared) == set(ERROR_CLASSES), (
            f"{signal} declares a different set of error classes from the "
            f"vocabulary in this file.\n  declared here only: "
            f"{sorted(set(declared) - set(ERROR_CLASSES))}\n  "
            f"declared in the schema only: {sorted(set(ERROR_CLASSES) - set(declared))}"
        )
        assert len(declared) == len(set(declared)), f"{signal}: a class is listed twice"


def test_the_error_class_vocabulary_is_narrow_and_closed() -> None:
    """Around a dozen, narrow on purpose, and every member a class rather than a
    sentence.

    D14 says a narrow vocabulary means a class is worth alerting on, and a broad
    one means every value gets its own alert and the grouping key stops
    grouping. That is a judgement call, and judgement calls made twice under
    deadline come out different — so the bound is a bound.
    """
    classes = set(ERROR_CLASSES)
    assert MIN_ERROR_CLASSES <= len(classes) <= MAX_ERROR_CLASSES, (
        f"the error vocabulary holds {len(classes)} classes, outside "
        f"[{MIN_ERROR_CLASSES}, {MAX_ERROR_CLASSES}]. D14 asks for around a dozen "
        "and says do not pad it. Widening it is a spec change: write down the "
        "class, the responder it is for, and what it collapses with (see D18)."
    )
    pattern = re.compile(ERROR_CLASS_SHAPE)
    for name in sorted(classes - {"_OTHER"}):
        assert pattern.fullmatch(name), (
            f"{name!r} does not match the class shape {ERROR_CLASS_SHAPE}"
        )
        assert len(name) <= 64, f"{name!r} is not a class, it is a sentence"
        assert name == name.lower(), (
            f"{name!r} is not lowercase. Exactly one member of the vocabulary is "
            "allowed to be upper case and it is the OTel fallback, spelled as the "
            "ecosystem spells it (D19)."
        )
    assert "_OTHER" in classes, (
        "the OTel well-known fallback must be in the vocabulary. A closed enum "
        "with no escape hatch gets widened under pressure the first time a real "
        "failure does not fit, and a widened enum is how `_OTHER` becomes a "
        "permanent value nobody reads. See D19."
    )
    assert pattern.fullmatch("_OTHER"), (
        f"_OTHER must still match the declared shape {ERROR_CLASS_SHAPE} — it is "
        "the one member the shape exists to accommodate, and a shape that does not "
        "accommodate it is a shape that has to be widened for the next value too"
    )


def test_the_error_class_shape_is_byte_identical_on_every_signal() -> None:
    """Duplicated rather than `$ref`d, and the duplication is asserted.

    Same rule as the span-name pattern: a service's SDK setup reads one schema
    file alone, so a cross-file `$ref` would make the file un-loadable without a
    resolver. That is a real constraint and it obliges a test, because a
    duplicated constraint nobody compares is two constraints.
    """
    shapes = {signal: error_type_definition(signal).get("pattern") for signal in
              ("traces", "metrics", "logs")}
    assert set(shapes.values()) == {ERROR_CLASS_SHAPE}, (
        f"the error-class shape is duplicated on all three signals; change one, "
        f"change both.\n  declared: {shapes}"
    )


def test_a_well_shaped_but_undeclared_error_class_is_rejected() -> None:
    """The example that matters most, on both signals that carry the class.

    `user_42_email_invalid` is snake_case, is twenty-two characters, and is what a
    well-meaning service emits when it interpolates the thing that went wrong into
    the class. Under the previous pattern-only schema it validated on traces,
    metrics and logs. On metrics that is `tenant_id` on a measurement wearing a
    different name: one series per value, and an error rate nobody can draw.

    The positive control matters as much as the negative: the value is asserted to
    satisfy the shape and the length cap FIRST, so this test cannot pass because
    the pattern caught it. It passes only if the vocabulary did.
    """
    undeclared = "user_42_email_invalid"
    assert re.fullmatch(ERROR_CLASS_SHAPE, undeclared), (
        f"{undeclared!r} must be well SHAPED — the point of this example is a "
        "value the old schema accepted"
    )
    assert len(undeclared) <= 64
    assert undeclared not in ERROR_CLASSES

    cases = (
        ("error-type.undeclared.invalid.json", TRACES_SCHEMA_PATH, "attributes"),
        (
            "metric.error-type-undeclared.invalid.json",
            METRICS_SCHEMA_PATH,
            "measurementAttributes",
        ),
    )
    for name, schema_path, holder in cases:
        document = load_document(INVALID_TELEMETRY / name)
        schema = load_schema(schema_path)
        found = failures_for(document, schema)
        assert found, f"{name} must be rejected"
        assert_keywords(found, (("enum", f"{holder}/error.type"),))
        # Exactly one violation, and it is the enum. Two would mean the pattern
        # also objected — which is the failure this whole example exists to rule
        # out, since "the shape caught it" is precisely what did not happen under
        # the previous pattern-only schema.
        assert len(found) == 1, (
            f"{name} must be rejected for being UNDECLARED and nothing else; the "
            f"shape should accept it. Violations: {[str(f) for f in found]}"
        )
        # ... and the identical document with a declared class validates, so this
        # is a test about the vocabulary and not about the document being broken.
        repaired = json.loads(json.dumps(document).replace(undeclared, "invalid_request"))
        repaired_failures = failures_for(repaired, schema)
        assert not repaired_failures, (
            f"{name} is about the vocabulary: the same document with a declared "
            "class must validate, and it does not\n  "
            + "\n  ".join(str(f) for f in repaired_failures)
        )


def test_span_status_error_obliges_an_error_class() -> None:
    """`status.code: "error"` is a claim, and a claim has to be classifiable.

    core-04 stated this in a `description` and nowhere else: with the attribute
    deleted, `span.muse.json` still validated. A description is a wish; this is
    the obligation. An unclassified error span is a span a fleet-wide view
    counts and cannot explain, which is the outcome the whole attribute exists
    to prevent.
    """
    document = load_document(VALID_TELEMETRY / "span.muse.json")
    assert document["status"]["code"] == "error"
    document["attributes"].pop("error.type")
    found = failures_for(document, load_schema(TRACES_SCHEMA_PATH))
    assert found, (
        "a span with status error and no error.type must be rejected: the status "
        "obliges the class"
    )
    assert_keywords(found, (("required", "attributes"),))

    # The negative example says the same thing, so a reader who never runs the
    # suite still has the shape in front of them.
    example = load_document(INVALID_TELEMETRY / "span.error-status-no-type.invalid.json")
    found = failures_for(example, load_schema(TRACES_SCHEMA_PATH))
    assert found, "span.error-status-no-type.invalid.json must be rejected"
    assert_keywords(found, (("required", "attributes"),))


def test_an_error_class_is_absent_on_success() -> None:
    """Its absence is the load-bearing "not an error" marker, not an omission.

    This is what makes error rate computable on a duration histogram without a
    message in a label: the samples with the attribute are the errors and the
    samples without it are everything else. A success that carries a class
    therefore does not just add noise — it moves the numerator, and the error rate
    becomes a number nobody can trust.
    """
    schema = load_schema(TRACES_SCHEMA_PATH)
    document = load_document(VALID_TELEMETRY / "span.muse.json")
    document["status"] = {"code": "ok"}
    found = failures_for(document, schema)
    assert found, "a successful span must not carry an error class"
    assert_keywords(found, (("const", "status/code"),))

    # The positive control: the same successful span without the class validates,
    # so success is a thing a span can be rather than a thing a class forbids.
    del document["attributes"]["error.type"]
    assert not failures_for(document, schema), (
        "a successful span with no error.type must validate\n  "
        + "\n  ".join(str(f) for f in failures_for(document, schema))
    )


def test_a_span_cannot_contradict_its_own_status_mirror() -> None:
    """`status.code` is the field of record, and a mirror may not overrule it.

    `otel.status_code` exists so a log-indexed query can filter on it. The moment
    it can disagree with `status.code`, a query that reads the mirror answers a
    different question from the predicate the fleet-wide view uses — and nothing
    reports the disagreement. The obligation in the rule above is only meaningful
    if the span has one status, so this closes that hole rather than adding a
    separate rule.
    """
    schema = load_schema(TRACES_SCHEMA_PATH)
    document = load_document(VALID_TELEMETRY / "span.muse.json")
    document["status"] = {"code": "ok"}
    document["attributes"]["otel.status_code"] = "ERROR"
    # The class is removed on purpose. The rule above — an error class obliges a
    # failed status — would otherwise also fire on this document, and then
    # `assert found` would pass even with the mirror rule deleted. Found by
    # mutation: deleting the mirror rule left this test green.
    del document["attributes"]["error.type"]
    found = failures_for(document, schema)
    assert found, (
        "otel.status_code: ERROR with status.code: ok must be rejected — two "
        "spellings of one fact that disagree is the failure this repo exists to "
        "prevent"
    )
    assert_keywords(found, (("const", "status/code"),))

    # The negative example carries the same mistake with a class on it, so a
    # reader who never runs the suite still has the shape in front of them.
    example = load_document(INVALID_TELEMETRY / "span.status-mirror-disagrees.invalid.json")
    assert failures_for(example, schema), (
        "span.status-mirror-disagrees.invalid.json must be rejected"
    )


def test_span_status_codes_are_exactly_the_three_the_ecosystem_defines() -> None:
    """The status enum is the predicate, so it is closed and it is asserted.

    `status.code` is what the fleet-wide "this is an error" filter reads. A
    fourth value invented by one service is a dashboard that silently misses it,
    which the schema's own description promises cannot happen and nothing tested.
    Found by mutation: adding `critical` to the enum left the suite green.
    """
    code = load_schema(TRACES_SCHEMA_PATH)["properties"]["status"]["properties"]["code"]
    assert code["enum"] == ["unset", "ok", "error"], (
        f"the span-status enum moved: {code['enum']}"
    )


def test_every_signal_allowlist_is_closed() -> None:
    """`additionalProperties: false` at the attribute level, on every signal.

    Default-deny is the redaction boundary in its structural form: an attribute
    nobody declared is dropped rather than shipped. It was the one thing about
    the allowlists that was described everywhere and asserted nowhere — found by
    mutation: deleting `additionalProperties` from the traces allowlist left the
    suite green, which meant the strongest structural claim in the spec was
    resting on a schema nobody checked.
    """
    for signal, (filename, definition) in ALLOWLIST_DEF.items():
        allowlist = load_schema(TELEMETRY_SCHEMAS / filename)["$defs"][definition]
        assert allowlist.get("additionalProperties") is False, (
            f"the {signal} attribute allowlist must be closed "
            f"(additionalProperties: false) so an attribute nobody declared is a "
            f"failure rather than a silent export"
        )


def test_every_declared_error_class_has_a_valid_example() -> None:
    """The vocabulary and the examples are the same set, in both directions.

    A class nobody has ever seen in a document is a class no service knows how to
    emit, and an example using a class the schema does not declare is an
    example that validates for the wrong reason. The class is read out of each
    document rather than parsed from its filename, so a misleading filename
    cannot hide either.
    """
    used: set[str] = set()
    for name, schema_path in sorted(TELEMETRY_EXAMPLE_SCHEMAS.items()):
        if schema_path not in ATTRIBUTE_HOLDER:
            continue  # a span-naming, redaction, endpoint or probe document
        document = load_document(VALID_TELEMETRY / name)
        holder = document[ATTRIBUTE_HOLDER[schema_path]]
        if "error.type" not in holder:
            continue
        found = failures_for(document, load_schema(schema_path))
        assert not found, (
            f"{name} uses error.type={holder['error.type']!r} and must "
            "validate:\n  " + "\n  ".join(str(f) for f in found)
        )
        used.add(holder["error.type"])
    declared = set(ERROR_CLASSES)
    assert used == declared, (
        "the error classes used by the valid examples and the classes the schemas "
        "declare are different sets.\n  examples only: "
        f"{sorted(used - declared)}\n  schemas only: {sorted(declared - used)}"
    )


def test_a_span_and_its_metric_carry_the_same_error_class() -> None:
    """The cross-signal identity rule, demonstrated rather than asserted.

    `error.type` is identical on a span and on its corresponding metric for the
    same operation. No single JSON Schema can compare two documents, so what is
    checkable is (a) that both sides draw from one closed list, asserted by
    test_the_error_class_vocabulary_is_one_closed_enum_on_every_signal, and (b)
    that the shipped pair agrees — which is this test. The pairing is found by
    prefix rather than hard-coded, and the test refuses to pass if no pair exists,
    because a cross-signal rule with no pair to check is a rule nothing checks.
    """
    metric = load_document(VALID_TELEMETRY / "metric.error-type.json")
    spans = {
        load_document(path)["name"]: load_document(path)
        for path in sorted(VALID_TELEMETRY.glob("error-type.*.json"))
    }
    operation = metric["name"].removesuffix(".duration")
    assert operation in spans, (
        f"{metric['name']} names no example span, so the identity rule has no pair "
        f"to check. Known spans: {sorted(spans)}"
    )
    span = spans[operation]
    span_class = span["attributes"]["error.type"]
    metric_class = metric["measurementAttributes"]["error.type"]
    assert span_class == metric_class, (
        f"the span {operation} records error.type={span_class!r} and its metric "
        f"{metric['name']} records {metric_class!r}. The same operation must "
        "report the same class on both signals, or the two cannot be joined and "
        "the error rate is computed from two different taxonomies."
    )
    # The class a service would actually invent in order to diverge is not
    # expressible on either signal. This is the half of the identity rule that is
    # a schema rather than a comparison: one closed list on both sides means the
    # span cannot say `timeout` while its metric says `provider_timeout`.
    divergent = (
        (
            TRACES_SCHEMA_PATH,
            "attributes",
            {**span, "attributes": {**span["attributes"], "error.type": "provider_timeout"}},
        ),
        (
            METRICS_SCHEMA_PATH,
            "measurementAttributes",
            {
                **metric,
                "measurementAttributes": {
                    **metric["measurementAttributes"],
                    "error.type": "provider_timeout",
                },
            },
        ),
    )
    for schema_path, holder, document in divergent:
        found = failures_for(document, load_schema(schema_path))
        assert found, (
            f"a per-service class name must be rejected on {schema_path.name}, or "
            "the span and its metric can disagree about one failure"
        )
        assert_keywords(found, (("enum", f"{holder}/error.type"),))


def test_no_signal_can_record_a_handled_or_retried_error() -> None:
    """`SHOULD NOT` encoded as unrepresentable rather than as prose.

    Handled and retried errors are not recorded at all: a retry that succeeded is
    not an error, and recording it makes the error rate a lie. `SHOULD NOT` has
    no schema keyword, so the rule is enforced the only way it can be — there is
    no attribute on any signal a service could set to say "this attempt failed
    and I recovered", so there is nothing to set. Same structural argument as
    `error.message`, which is prohibited by name because a tracing SDK adds it by
    default; a rule only a discipline can enforce is a rule a well-meaning commit
    removes.
    """
    for signal in ("traces", "metrics", "logs"):
        for name in sorted(signal_allowlist(signal)):
            lowered = name.lower()
            found = [
                word for word in FORBIDDEN_ERROR_LIFECYCLE_WORDS if word in lowered
            ]
            assert not found, (
                f"the {signal} allowlist carries {name!r}, whose name contains "
                f"{found}. That is an attribute for recording a handled or "
                "retried attempt, which is exactly what must not be recorded: a "
                "retry that succeeded is not an error."
            )
    for name in sorted(set(ERROR_CLASSES) - {"_OTHER"}):
        found = [w for w in FORBIDDEN_ERROR_LIFECYCLE_WORDS if w in name]
        assert not found, (
            f"the class {name!r} names a handled or retried attempt ({found}). "
            "The vocabulary may say how an operation ended, never how it was "
            "saved."
        )


def test_the_doc_lists_exactly_the_declared_error_classes() -> None:
    """A doc and its schema are the same contract written twice (AGENTS.md).

    The vocabulary table in `docs/observability.md` and the `enum` in three
    schemas drift apart the moment nobody compares them, and the drift is
    invisible: a class in the table that the schema rejects breaks a service that
    believed the documentation, and a class in the schema that the table does not
    explain is a class nobody knows when to emit. Same shape as
    test_event_catalog_in_docs_matches_the_schema, and for the same reason — the
    doc is the thing a service reads, so the doc has to be the thing that is
    true.
    """
    doc = section(OBSERVABILITY_DOC.read_text(encoding="utf-8"), "## `error.type`")
    # `[A-Za-z_]` rather than `[a-z_]` because `_OTHER` is the one member that is
    # not lower case; a dotted name like `service.name` cannot match, so the
    # can/cannot-aggregate table below is not swept in by accident.
    listed = set(re.findall(r"^\|\s*`([A-Za-z_]+)`\s*\|", doc, flags=re.MULTILINE))
    declared = set(ERROR_CLASSES)
    assert listed == declared, (
        "the class table in docs/observability.md and the enum the schemas "
        f"declare disagree.\n  doc only: {sorted(listed - declared)}\n"
        f"  schema only: {sorted(declared - listed)}"
    )


def test_the_observability_doc_states_the_error_recording_rules() -> None:
    """The four rules the research established and core-04 left in prose.

    Absent on success, identical across signals, handled-and-retried not
    recorded, status-error obliges the class — plus the two things that are easy
    to get wrong and that the doc now has to say plainly: the predicate is span
    status, not `error.type`, and `error.type` is never a global grouping key.
    """
    doc = OBSERVABILITY_DOC.read_text(encoding="utf-8").lower()
    missing = [topic for topic in REQUIRED_ERROR_RECORDING_TOPICS if topic not in doc]
    assert not missing, (
        f"docs/observability.md dropped from the error recording rules: {missing}. "
        "Each is a semconv rule core encodes or a distinction the research "
        "settled; a doc edit that removes one has to argue for it in "
        "DECISIONS.md first."
    )


def test_the_error_rules_mark_their_stability_honestly() -> None:
    """Stable where semconv is Stable, Development where it is not.

    `error.type` and the trace status rules are Stable; the cross-signal coupling
    document, `recording-errors.md`, is **Development**. A schema that encodes a
    Development rule without saying so implies the whole model has frozen, and
    the next reader trusts a coupling that is allowed to change.
    """
    for path in (TRACES_SCHEMA_PATH, METRICS_SCHEMA_PATH, LOGS_SCHEMA_PATH):
        text = path.read_text(encoding="utf-8")
        assert "recording-errors.md" in text, (
            f"{path.name} encodes the cross-signal coupling without naming the "
            "document that defines it, so a reader cannot tell the rules are not "
            "yet stable"
        )
        assert "development" in text.lower(), (
            f"{path.name} must say which of the rules it encodes come from a "
            "Development-stability document"
        )
    doc = OBSERVABILITY_DOC.read_text(encoding="utf-8").lower()
    assert "stable" in doc, "docs/observability.md must state the stability of what it encodes"


def test_observability_doc_covers_every_required_topic() -> None:
    doc = OBSERVABILITY_DOC.read_text(encoding="utf-8").lower()
    for topics, label in (
        (REQUIRED_ENDPOINT_TOPICS, "endpoint"),
        (REQUIRED_REDACTION_TOPICS, "redaction"),
        (REQUIRED_HEALTH_TOPICS, "health"),
        (REQUIRED_ERROR_RECORDING_TOPICS, "error recording"),
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
# 6. how core is gated
# --------------------------------------------------------------------------

# core adopted kit's reusable workflow in core-06. The two tests in this section
# exist because of one defect class that a spec repository is unusually exposed
# to: a *build* claim is a claim, and nothing in a suite of schema tests can see
# it go stale. kit shipped its workflow at `workflows/ci.reusable.yml`, where
# GitHub cannot resolve it, for the whole life of kit-02 — and no repository in
# the fleet was calling it, because a `uses:` line that resolves to nothing looks
# exactly like one that resolves. A layout bug and a documentation bug agree with
# each other perfectly, which is the only reason either survived.
#
# So the adoption is asserted from this side, where nothing else asserts it.
CI_WORKFLOW = REPO / ".github/workflows/ci.yml"

# The string kit documents in its README and its AGENTS.md, and the only one
# GitHub resolves: a reusable workflow is looked up at
# `{owner}/{repo}/.github/workflows/{file}@{ref}` and GitHub documents that
# **subdirectories of the workflows directory are not supported**. The
# kit-02 spelling — `cafaye/kit/workflows/ci.reusable.yml@master` — is a valid
# looking string that fails at run time on the adopting repository's first push.
KIT_USES = "cafaye/kit/.github/workflows/ci.reusable.yml@master"

# Root-level files that would make this repository look like a service to any
# packaging tool, and therefore make one of kit's seven language jobs applicable.
# `tests/requirements.txt` is deliberately absent: it is the gate's dependency
# list and has never been a project manifest, and the test below only looks at
# the repository root.
SERVICE_MANIFESTS = (
    "pyproject.toml",
    "setup.py",
    "setup.cfg",
    "uv.lock",
    "Pipfile",
)


def test_the_ci_workflow_calls_kit_at_the_path_kit_documents() -> None:
    """core's CI calls kit's reusable workflow, at a path that resolves.

    The assertion is exact-match on the cross-repository `uses:` rather than a
    substring search, because a substring search is what let the stale path
    through: `cafaye/kit/workflows/ci.reusable.yml@master` *contains* every
    interesting token, and it is the string that does not work. Matching the
    whole line means a future edit has to be deliberate to break it, and a
    reformatted workflow that stops matching fails loudly instead of quietly
    agreeing.

    It also asserts `language: 'none'`, because that value is only honest while
    `test_core_declares_no_service_manifest` holds. The two are the same claim
    seen from two directions: `none` is kit's documented option for a repository
    with **no service manifest at all**, and core has none.
    """
    assert CI_WORKFLOW.is_file(), (
        f"{CI_WORKFLOW.relative_to(REPO)} does not exist. core adopted kit's reusable "
        "workflow in core-06, and the call has to live in the tree for the build to "
        "be anything other than a claim."
    )
    text = CI_WORKFLOW.read_text(encoding="utf-8")

    # `uses:` also names actions (`actions/checkout@v7`), so filter to the
    # cross-repository kit call rather than reading the first `uses:`.
    kit_calls = re.findall(r"^\s*uses:\s*(\S+)\s*$", text, flags=re.MULTILINE)
    kit_calls = [value for value in kit_calls if value.startswith("cafaye/kit/")]
    assert kit_calls == [KIT_USES], (
        f"the cross-repository kit call must be exactly [{KIT_USES!r}] and appear once; "
        f"found {kit_calls}. A `uses:` that does not resolve is a red build on the first "
        "push, and GitHub documents that subdirectories of `.github/workflows` are not "
        "supported — so `cafaye/kit/workflows/ci.reusable.yml@master` is not an option."
    )

    assert re.search(r"^\s*language:\s*'none'\s*$", text, flags=re.MULTILINE), (
        "core declares no service manifest, so the language must be 'none'. The seven "
        "language jobs each open by reading a manifest they cannot find: `python` runs "
        "`uv sync --frozen`, which exits 2 with 'No pyproject.toml found'. If core ever "
        "grows a manifest this is the test that says so, together with "
        "test_core_declares_no_service_manifest."
    )


def test_core_declares_no_service_manifest() -> None:
    """core is a specification repository and stays one.

    Not tidiness. kit's reusable workflow offers seven language jobs, and every
    one of them opens by reading a service manifest and then installing from it —
    `uv sync --frozen`, `bundle install`, `go mod download`, `npm ci`,
    `bun install --frozen-lockfile`. A repository with a manifest and no runtime
    is a repository whose CI is now running a package installer over a
    specification, and whose coverage gate is measuring a test file: a number
    that goes up when the tests get shorter.

    AGENTS.md already draws the line — "core is schemas + docs + validators; if a
    change needs a runtime, it belongs in `caf`, not here" — so this asserts an
    existing rule rather than making one.

    **If this fails, that is not a bug to work around.** Either delete the
    manifest, or keep it and change the `language:` value in
    `.github/workflows/ci.yml` in the same commit, having decided whether
    `bin/prime` or kit's job is now the gate. Both are legitimate; drifting
    between them silently is not.
    """
    found = [name for name in SERVICE_MANIFESTS if (REPO / name).exists()]
    assert not found, (
        f"{found} at the repository root makes core look like a Python/Node project to "
        "every packaging tool in the org, and makes one of kit's seven language jobs "
        "applicable for the first time. Delete it, or keep it and change the `language:` "
        "in .github/workflows/ci.yml in the same commit — and re-read which of `bin/prime` "
        "and kit's job is the gate afterwards."
    )


# --------------------------------------------------------------------------
# 7. the contract-test harness
# --------------------------------------------------------------------------

# PLAN.md §4 Phase 0 named four deliverables for core v0. Three shipped; the
# contract-test harness did not, and four services each wrote their own version
# of it instead — muse's pinned-SHA byte comparison, darkroom's copy, courier's
# document-against-router test and pantry's drift test. This section is the
# statement that the harness now exists, and — far more to the point — that it
# is capable of failing.
#
# The tests are ordered so the two claims that matter come first and the
# refactors come last. `test_the_harness_fails_loudly_when_core_is_absent` and
# `test_the_harness_evaluator_agrees_with_jsonschema_on_every_example` are the
# two ways this could have been a green badge over nothing: a harness that
# cannot find the contract and reports success, and a hand-written JSON Schema
# reader that quietly disagrees with the one core publishes.


def harness_module():
    """Import `harness/cafaye_contract.py`, or say why it could not.

    The import is lazy and its failure is an assertion rather than an
    ImportError at module scope, so a missing harness is one failing test with
    one sentence in it rather than a collection error that hides the other
    hundred.
    """
    assert HARNESS_MODULE.is_file(), (
        f"{HARNESS_MODULE.relative_to(REPO)} does not exist. PLAN.md §4 Phase 0 names a "
        "contract-test harness as a core deliverable, core-07 is the packet that builds it, "
        "and a service cannot validate itself against core's contracts without it."
    )
    if str(HARNESS) not in sys.path:
        sys.path.insert(0, str(HARNESS))
    import cafaye_contract  # noqa: PLC0415 - lazy on purpose, see above

    return cafaye_contract


def harness_runs(service: Path, *, core: Path | None = None, **kwargs):
    """Run the harness in-process and return its `Result`."""
    module = harness_module()
    return module.run(service_root=service, core_root=core or REPO, **kwargs)


def harness_rules_by_id() -> dict:
    """`harness/rules.json`, the rule inventory, keyed by id."""
    with HARNESS_RULES.open(encoding="utf-8") as handle:
        return {rule["id"]: rule for rule in json.load(handle)["rules"]}


def test_the_harness_validates_core_against_itself() -> None:
    """The first run a harness deserves: this repository, with core's own manifest.

    core is a `language: spec` repository whose manifest omits `exposes`
    entirely, so this is also the shape a service with no HTTP surface takes.
    A harness that only ever sees `exposes: {api: ...}` has not been tested
    against the fleet's other legal manifest.
    """
    result = harness_runs(REPO)
    assert result.exit_code == HARNESS_EXIT_CONFORMS, (
        f"core's own cafaye.yml must pass the harness (exit {HARNESS_EXIT_CONFORMS}), got "
        f"{result.exit_code}:\n  "
        + "\n  ".join(f"{f.rule} {f.path}: {f.message}" for f in result.findings)
    )


def test_the_harness_accepts_the_conforming_fixture() -> None:
    result = harness_runs(HARNESS_FIXTURES / "conforming")
    assert result.exit_code == HARNESS_EXIT_CONFORMS, (
        "the conforming fixture must pass, or every red below proves nothing:\n  "
        + "\n  ".join(f"{f.rule} {f.path}: {f.message}" for f in result.findings)
    )
    assert result.findings == (), "a conforming run reports no findings at all"


def test_the_harness_stops_at_the_manifest_schema_and_says_so() -> None:
    """A document whose fields are the wrong type has no trustworthy cross-fields.

    `caf`'s linter made the same call — schema first, conventions only on a
    document that passed — and the reason is not tidiness: every cross-field
    rule reads two fields and compares them, and run first they report a
    comparison against a field that is not there.

    The assertion is that the *conventions* are absent from the run **and** that
    the run explains itself, because a harness that silently drops half its
    checks is indistinguishable from a harness that found nothing.
    """
    result = harness_runs(HARNESS_FIXTURES / "nonconforming")
    rules = {finding.rule for finding in result.findings}
    assert rules == {"manifest.schema"}, (
        f"a schema-rejected manifest must report only manifest.schema, got {sorted(rules)}"
    )
    assert result.stopped_after_schema is True, (
        "the run must record that it stopped, so the caller can tell 'nothing else is "
        "wrong' from 'nothing else was checked'"
    )
    # The three fixture defects are named, not summarised. A schema failure that
    # says "manifest invalid" sends a person to the schema file.
    text = "\n".join(f.message for f in result.findings)
    for field in ("name", "language", "core"):
        assert field in text, f"the schema failure must name the {field} it rejected:\n{text}"


def test_the_harness_reports_every_convention_rule_one_manifest_breaks() -> None:
    """The exact set, not a superset. See `NONCONFORMING_CONVENTION_RULES`.

    This is the assertion shape that matters. "Reports at least these five" is
    satisfied by a harness that reports one of them and silently drops four —
    and a dropped rule is the one defect in a conformance tool that looks
    exactly like success.
    """
    result = harness_runs(HARNESS_FIXTURES / "nonconforming-conventions")
    assert result.exit_code == HARNESS_EXIT_VIOLATIONS, (
        f"a non-conforming manifest must exit {HARNESS_EXIT_VIOLATIONS}, got {result.exit_code}"
    )
    rules = {finding.rule for finding in result.findings}
    assert rules == NONCONFORMING_CONVENTION_RULES, (
        f"expected exactly {sorted(NONCONFORMING_CONVENTION_RULES)}, got {sorted(rules)}; "
        "a harness that reports a subset of what it can see is a harness that has turned "
        "an unknown into a pass"
    )


def test_the_harness_reports_every_openapi_rule_one_document_breaks() -> None:
    result = harness_runs(HARNESS_FIXTURES / "nonconforming-openapi")
    rules = {finding.rule for finding in result.findings}
    assert rules == NONCONFORMING_OPENAPI_RULES, (
        f"expected exactly {sorted(NONCONFORMING_OPENAPI_RULES)}, got {sorted(rules)}"
    )


def test_an_openapi_document_with_no_paths_is_a_finding_not_a_pass() -> None:
    """Two empty sets agree, so an empty one must never be a pass.

    A reader that finds no paths and returns an empty collection lets a service
    delete its entire HTTP contract and see a green build, because "no path
    violates the `/v1` rule" and "there is no path" are the same sentence.
    courier's `OpenAPIPaths` is the precedent; this is the assertion.
    """
    result = harness_runs(HARNESS_FIXTURES / "nonconforming-openapi-empty")
    assert "openapi.has-paths" in {finding.rule for finding in result.findings}, (
        f"a document whose paths are empty must be rejected, got "
        f"{[f.rule for f in result.findings]}"
    )


def test_the_harness_fails_loudly_when_core_is_absent() -> None:
    """The rule that has bitten this fleet four times, asserted directly.

    guard's live-Redis tier, muse's `MUSE_CORE_SCHEMAS` tier, identity's
    `TEST_DATABASE_URL` tier and darkroom's `--ignored` tests are the same
    defect: a check that could not run, exiting 0. A contract check that cannot
    find the contract and reports success is *worse* than no contract check,
    because it converts an unknown into a green badge.

    So: empty environment (nothing inherited that could point at a core
    checkout), a working directory that is not a core checkout, and no `--core`.
    The assertion is that the exit code is the refusal code and **not** the
    conforms code — and that the message says where it looked, because "core not
    found" with no list is the version nobody can act on.
    """
    module = harness_module()
    with tempfile.TemporaryDirectory() as empty:
        completed = subprocess.run(
            [sys.executable, str(HARNESS_MODULE), "--core", empty, "."],
            cwd=empty,
            env={},
            capture_output=True,
            text=True,
            check=False,
        )
    assert completed.returncode == HARNESS_EXIT_REFUSED, (
        f"a run with no core checkout must exit {HARNESS_EXIT_REFUSED} (refused) and never "
        f"{HARNESS_EXIT_CONFORMS} (conforms); it exited {completed.returncode}.\n"
        f"stdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
    )
    assert completed.returncode != HARNESS_EXIT_CONFORMS, (
        "this is the assertion the whole test exists for"
    )
    message = completed.stdout + completed.stderr
    assert module.REFUSALS["core.absent"] in message or "cafaye.manifest.schema.json" in message, (
        f"the refusal must name what it could not find:\n{message}"
    )
    assert "cafaye-contract" not in message.split("\n")[-2:], "sanity: message parsed"


def test_the_harness_fails_loudly_when_a_service_manifest_is_absent() -> None:
    """A path with no `cafaye.yml` has not been validated.

    `caf`'s linter returns an error rather than an empty report for exactly
    this: an empty report's `OK` is indistinguishable from the `OK` of a
    repository that was never looked at.
    """
    module = harness_module()
    with tempfile.TemporaryDirectory() as empty:
        result = module.run(service_root=Path(empty), core_root=REPO)
    assert result.exit_code == HARNESS_EXIT_REFUSED, (
        f"a service root with no cafaye.yml must be refused, got {result.exit_code}"
    )
    assert [f.rule for f in result.findings] == ["service.manifest-absent"], (
        f"the refusal must be named, got {[f.rule for f in result.findings]}"
    )


def test_the_harness_fails_loudly_when_core_is_not_a_core_checkout() -> None:
    """A directory that exists is not a core checkout.

    The difference matters because `--core ../core` on a laptop and a CI step
    that exports the wrong path are the same event, and only the second one has
    a red build afterwards.
    """
    module = harness_module()
    with tempfile.TemporaryDirectory() as empty:
        (Path(empty) / "schemas").mkdir()
        (Path(empty) / "README.md").write_text("not core\n", encoding="utf-8")
        result = module.run(service_root=HARNESS_FIXTURES / "conforming", core_root=Path(empty))
    assert result.exit_code == HARNESS_EXIT_REFUSED, (
        f"a directory with no manifest schema must be refused, got {result.exit_code}"
    )
    assert [f.rule for f in result.findings] == ["core.not-a-checkout"], (
        f"the refusal must be named, got {[f.rule for f in result.findings]}"
    )


def test_the_harness_digest_is_the_pin_and_it_notices_a_changed_schema() -> None:
    """The pinning answer, proved: one digest, checked, on a laptop and in CI alike.

    The harness is given a **directory**, and the pin is that directory's
    content — a sha256 over every file under `schemas/`, sorted by path. The
    same core ref produces the same digest in a developer's worktree and in a CI
    runner; a schema edit produces a different one. `--expect-digest` is the
    opt-in that turns "different" into a red build, and it is the same code path
    in both environments because there is no second one.
    """
    module = harness_module()
    service = HARNESS_FIXTURES / "conforming"
    baseline = module.contract_digest(REPO)
    assert HARNESS_DIGEST_PATTERN.fullmatch(baseline), (
        f"the contract digest must be a 64-character lowercase sha256, got {baseline!r}"
    )
    assert module.contract_digest(REPO) == baseline, "the digest is not stable across calls"

    with tempfile.TemporaryDirectory() as work:
        copied = Path(work) / "core"
        shutil.copytree(REPO / "schemas", copied / "schemas")
        shutil.copytree(REPO / "docs", copied / "docs")
        assert module.contract_digest(copied) == baseline, (
            "a copy of core's contract surface must digest identically, or the pin is "
            "sensitive to something other than the contract"
        )
        # One byte in one schema — the smallest possible drift, and the one a
        # re-vendor fan-out would produce.
        target = copied / "schemas" / "cafaye.manifest.schema.json"
        target.write_text(
            target.read_text(encoding="utf-8") + "\n", encoding="utf-8"
        )
        drifted = module.contract_digest(copied)
        assert drifted != baseline, "a changed schema must change the digest"
        result = module.run(
            service_root=service, core_root=copied, expect_digest=baseline
        )
        assert result.exit_code == HARNESS_EXIT_VIOLATIONS, (
            f"a drifted contract must be a violation, got {result.exit_code}"
        )
        assert "core.digest-mismatch" in {f.rule for f in result.findings}, (
            f"the drift must be named, got {[f.rule for f in result.findings]}"
        )
        # And the un-pinned run over the same tree is otherwise a pass, which is
        # the point: the digest is opt-in, and the checks are the same either way.
        unpinned = module.run(service_root=service, core_root=copied)
        assert unpinned.exit_code == HARNESS_EXIT_CONFORMS, (
            "without --expect-digest a drifted core is still a core; the pin is the "
            "consumer's call, not the harness's"
        )


def test_the_harness_refuses_yaml_it_does_not_understand() -> None:
    """A subset reader must refuse, never guess.

    The fixture is a legal multi-line plain scalar. Guessing what it folds to
    means validating a document nobody wrote, and a schema error printed against
    a guessed document is worse than no answer because it names a real field.
    """
    module = harness_module()
    result = module.run(
        service_root=HARNESS_FIXTURES / "unsupported-yaml", core_root=REPO
    )
    assert result.exit_code == HARNESS_EXIT_REFUSED, (
        f"an unsupported YAML construct must be refused (exit {HARNESS_EXIT_REFUSED}), got "
        f"{result.exit_code}: {[f.rule for f in result.findings]}"
    )
    assert result.exit_code != HARNESS_EXIT_CONFORMS, (
        "this is the assertion the test exists for: unreadable is not conforming"
    )
    refusal = [f for f in result.findings if f.rule == "yaml.unsupported"]
    assert len(refusal) == 1, f"expected exactly one refusal, got {result.findings}"
    assert re.search(r"unsupported-yaml/cafaye\.yml:\d+$", refusal[0].path), (
        f"a refusal must name the file and the line, got {refusal[0].path!r}"
    )


def harness_refusal(module, call):
    """Run `call` and return the `Refusal` it must raise, or fail saying why not.

    Deliberately not `pytest.raises`. This file runs two ways — under pytest and
    as a plain script through `bin/prime` — and the script runner is the one
    `kit`'s `none` job and the CI `gate` job call. Importing pytest at module
    scope to save four lines would put a second way in front of a file that
    exists precisely so there is only one.
    """
    try:
        call()
    except module.Refusal as refusal:
        return refusal
    raise AssertionError(
        "the harness accepted a document it declares it refuses; a subset reader's "
        "honesty is entirely in what it refuses"
    )


def test_the_harness_yaml_reader_reads_every_document_in_this_repository() -> None:
    """Every YAML file core owns, read, and agreeing with PyYAML.

    This subsumes the narrower manifest-only comparison it replaces, and the "a
    named list of what the reader cannot read" test before that. `fleet.yml` and
    the invalid fleet example were the two documents the reader used to refuse,
    and a test that names what a reader cannot do accepts the limitation quietly.
    Both are read now, and the whole tree is asserted rather than a list.

    The reader used to refuse eight of the eleven real service repositories, so
    "reads everything in this repository" is a claim worth making rather than a
    formality. The single deliberate exception is the fixture that exists to be
    refused, and it is asserted refused below — so the claim cannot be met by
    refusing less.
    """
    module = harness_module()
    unsupported = HARNESS_FIXTURES / "unsupported-yaml"
    unreadable = {}
    documents = 0
    for path in sorted(REPO.rglob("*")):
        if not path.is_file() or path.suffix not in {".yml", ".yaml"}:
            continue
        if "tests/.venv" in path.as_posix() or unsupported in path.parents:
            continue
        documents += 1
        text = path.read_text(encoding="utf-8")
        try:
            found = module.read_yaml(text, path)
        except module.Refusal as refusal:
            unreadable[path.relative_to(REPO).as_posix()] = refusal.detail
            continue
        expected = yaml.safe_load(text)
        if path.name == "ci.yml" and path.parent.name == "workflows":
            # The one document in this tree the two readers must disagree on.
            # PyYAML implements YAML 1.1, where the bare word `on` is the boolean
            # `True`; the harness implements the 1.2 core schema, where it is the
            # string "on" — which is what GitHub Actions means and what every
            # other document core owns needs. Asserted rather than excluded,
            # because "the harness agrees with PyYAML everywhere" is a claim that
            # should have exactly one visible exception and no silent ones.
            assert True in expected and "on" in found, (
                "PyYAML no longer resolves `on:` to a boolean; this exception is dead and "
                "should be deleted"
            )
            continue
        assert found == expected, (
            f"the harness reader and PyYAML disagree on {path.relative_to(REPO)}"
        )
    assert documents >= 15, f"only found {documents} YAML documents in the repository"
    assert not unreadable, (
        f"the harness's reader cannot read {sorted(unreadable)}, and every YAML document core "
        "owns is one it should be able to read. Reasons: "
        + "; ".join(f"{name}: {why}" for name, why in sorted(unreadable.items()))
    )
    # And the one document that *is* meant to be refused is refused, by name, so
    # "the reader reads everything" cannot be achieved by refusing less.
    refusal = harness_refusal(
        module,
        lambda: module.read_yaml(
            (unsupported / "cafaye.yml").read_text(encoding="utf-8"),
            unsupported / "cafaye.yml",
        ),
    )
    assert refusal.rule == "yaml.unsupported", (
        f"the unsupported-YAML fixture is no longer refused, so the reader has started "
        f"accepting {refusal.rule} and the refusal list is behind it"
    )


def test_the_harness_yaml_reader_refuses_only_what_it_declares() -> None:
    """Every construct the reader refuses, as a list, with a reason.

    A subset reader's honesty is entirely in what it refuses. A reader that
    refuses a legal document is annoying; a reader that accepts an illegal one
    is a second, silent source of truth — so the refusals are enumerated here,
    in the test, where adding one is a deliberate act.

    Each probe is a whole document rather than a fragment, because a reader can
    refuse a fragment for a reason that has nothing to do with the construct.
    """
    module = harness_module()
    probes = {
        "anchor": "name: x\nowner: &team core\n",
        "alias": "name: x\nowner: *team\n",
        "tag": "name: x\nowner: !!str core\n",
        "directive": "%YAML 1.2\nname: x\n",
        "merge key": "name: x\n<<: base\n",
        "nested flow": "name: x\ntags: [[a]]\n",
        "trailing comma": "name: x\ntags: [a,]\n",
        "mismatched flow": "name: x\ntags: [a}\n",
        "scalar continued into a mapping": "name: x\nother: a value\n  key: 1\n",
        "tab indent": "name: x\nowner:\n\tteam: core\n",
        "duplicate key": "name: x\nname: y\n",
        "second document": "name: x\n---\nname: y\n",
    }
    for construct, reason in module.YAML_REFUSALS.items():
        assert reason, f"a refusal with no reason: {construct!r}"
    for label, text in probes.items():
        refusal = harness_refusal(module, lambda t=text: module.read_yaml(t, Path("probe.yml")))
        assert str(refusal), f"the {label} refusal has no message"
        assert refusal.rule == "yaml.unsupported", (
            f"the {label} refusal is {refusal.rule!r}, not yaml.unsupported"
        )
        assert re.search(r"probe\.yml:\d+$", refusal.path), (
            f"the {label} refusal must name the file and the line, got {refusal.path!r}"
        )


def test_the_harness_yaml_reader_reads_what_the_fleet_writes() -> None:
    """The subset is the one the fleet writes, because the first one was not.

    The first version of this reader refused block scalars, flow collections and
    continued plain scalars. It was then pointed at the eleven real service
    repositories in the cafaye workspace and **eight of eleven refused** — six on
    a `description:`, two on a leading `---`, the rest on `tags: [users]`. A
    harness that cannot read the documents it exists to check is a demonstration.

    So the three constructs are in, and this test is what says so: each one is
    read to the value PyYAML gives it. The refusal list shrank to what no real
    document needed, and the test above says exactly what is left.
    """
    module = harness_module()
    documents = {
        "block scalar": "name: x\ndescription: |\n  two\n  lines\n",
        "block scalar, strip": "name: x\ndescription: |-\n  two\n  lines\n",
        "block scalar, keep": "name: x\ndescription: |+\n  two\n\n",
        "folded scalar": "name: x\ndescription: >-\n  two\n  lines\n",
        "folded with a blank line": "name: x\ndescription: >-\n  two\n\n  three\n",
        "indentation indicator": "name: x\ndescription: |2\n    two\n",
        "continued plain scalar": "name: x\ndescription: two\n  lines\n",
        "continued with a blank": "name: x\ndescription: two\n\n  three\n",
        "document start marker": "---\nname: x\n",
        "flow sequence": "name: x\ntags: [a, b, c]\n",
        "flow sequence across lines": "name: x\nrequired: [a, b,\n  c, d]\n",
        "flow sequence with a quoted comma": 'name: x\ntags: [a, "b, c"]\n',
        "flow mapping": "name: x\nschema: { $ref: '#/components/schemas/Thing' }\n",
        "flow mapping, several": "name: x\nexample: { a: 1, b: two }\n",
        "empty collections": "name: x\na: []\nb: {}\n",
        "block sequence of mappings": "name: x\nitems:\n  - name: one\n    version: ^0.1.0\n  - name: two\n",
        "comment after a value": "name: x # the name\ndescription: two  # trailing\n",
    }
    for label, text in documents.items():
        expected = yaml.safe_load(text)
        found = module.read_yaml(text, Path("probe.yml"))
        assert found == expected, (
            f"the {label} construct:\n  pyyaml:  {expected!r}\n  harness: {found!r}"
        )


def test_the_harness_yaml_reader_agrees_with_pyyaml_on_every_fold() -> None:
    """The fold is the riskiest thing in the reader, so it gets its own test.

    Everything else in the reader either reads a construct or refuses it. A fold
    can be *almost* right, and an almost-right fold of a `description:` produces
    a document nobody wrote and then reports it as if it did. So YAML's three
    folding rules are each probed: one line break becomes a space, a blank line
    becomes a newline, and a more-indented line keeps its break.

    Kept apart from the construct matrix because that one is about *coverage* of
    what the fleet writes and this is about *correctness* of the one function
    that guesses. `muse`'s 405 description is the shape in the first row.
    """
    module = harness_module()
    documents = {
        "one break is a space": "d: two\n  lines\n",
        "a blank line is a newline": "d: two\n\n  three\n",
        "two blank lines are two newlines": "d: two\n\n\n  three\n",
        "a more indented line keeps its break": "d: two\n    three\n",
        "more indented after ordinary": "d: two\n  three\n    four\n",
        "two more indented lines": "d: two\n    three\n    four\n",
        "three lines": "d: one\n  two\n  three\n",
        "a break then a dedent": "d: one\n  two\nname: x\n",
        "a blank then a dedent": "d: one\n\nname: x\n",
        "a continued scalar then a sequence": "d: one\n  two\nitems:\n  - a\n",
    }
    for label, text in documents.items():
        expected = yaml.safe_load(text)
        found = module.read_yaml(text, Path("probe.yml"))
        assert found == expected, f"{label}:\n  pyyaml:  {expected!r}\n  harness: {found!r}"


def test_the_harness_evaluator_agrees_with_jsonschema_on_every_example() -> None:
    """The load-bearing check on the hand-written evaluator.

    `harness/cafaye_contract.py` evaluates the keywords core's schemas use,
    with nothing but the standard library, so that a Go service in CI needs no
    Python package to check its manifest. That is only defensible because it is
    *provably* the same answer `jsonschema` gives — and the proof is this test,
    over every example in `examples/`, in both directions: a document that
    jsonschema accepts must be accepted, and a document it rejects must produce
    the same set of violated keywords.

    Both directions matter. Agreeing on acceptance while disagreeing about
    *which* rule fired would report a real breach as some other real breach, and
    a report that names the wrong field sends a person to the wrong file.
    """
    module = harness_module()
    cases = [
        (MANIFEST_SCHEMA_PATH, list(MANIFEST_EXAMPLES) + [INVALID_MANIFEST]),
        (ENVELOPE_SCHEMA_PATH, [
            VALID_ENVELOPE, INVALID_ENVELOPE,
            INVALID_UNTAGGED_ENVELOPE, INVALID_SUBJECTLESS_ENVELOPE,
        ]),
        (FLEET_SCHEMA_PATH, [FLEET, INVALID_FLEET]),
    ]
    for schema_path in payload_schemas():
        event_type = event_type_of(schema_path)
        cases.append((schema_path, [
            VALID_PAYLOADS / (event_type.replace(".", "/") + PAYLOAD_EXAMPLE_SUFFIX),
            INVALID_PAYLOADS / (event_type.replace(".", "/") + PAYLOAD_EXAMPLE_SUFFIX),
        ]))
    # The three SLO schemas, because the harness now validates a Sloth
    # declaration against them. This is where the evaluator's newest keywords get
    # their receipt — `if`/`then` inside `prefixItems`, `const` alongside a `$ref`
    # sibling, `not` on a string — and a harness that quietly disagreed about
    # which rule fired would report a real breach under the wrong name.
    cases.append((SLO_SCHEMA_PATH, [
        VALID_SLO,
        INVALID_SLO_PERFECT,
        INVALID_SLO_PAGE_ON_LOW,
        INVALID_SLO_WINDOW_OVERRIDE,
    ]))
    cases.append((SLO_WINDOWS_SCHEMA_PATH, [VALID_SLO_WINDOWS, window_document()]))
    cases.append((SLO_METRICS_SCHEMA_PATH, [
        sli_catalogue_document(), INVALID_SLO_DENYLISTED,
    ]))
    for schema_path, documents in cases:
        schema = load_schema(schema_path)
        for document in documents:
            # A case is a path or an already-built document: the window catalog and
            # the SLI catalogue are *derived* in this test's helpers rather than
            # read from `examples/`, because their whole point is that the schema
            # declares them — so the equivalence check covers the declarations.
            instance = load_document(document) if isinstance(document, Path) else document
            expected = sorted({failure.keyword for failure in failures_for(instance, schema)})
            found = sorted({f.keyword for f in module.evaluate(instance, schema)})
            label = (
                f"{document.relative_to(REPO) if isinstance(document, Path) else '<derived>'} "
                f"against {schema_path.relative_to(REPO)}"
            )
            assert found == expected, (
                f"the harness evaluator and jsonschema disagree on {label}\n"
                f"  jsonschema: {expected}\n"
                f"  harness:    {found}"
            )


def test_the_harness_implements_every_keyword_core_schemas_use() -> None:
    """So the evaluator cannot quietly fall behind a schema that grows a keyword.

    A keyword the reader does not implement is a rule the harness does not
    enforce, and an unenforced rule reads exactly like an upheld one. So the
    keyword set is compared in both directions: nothing in `schemas/` may be
    unimplemented, and nothing may be implemented without a user, because dead
    code in a conformance tool is a rule that will be wrong the day it is used.
    """
    module = harness_module()
    used: set[str] = set()
    _collect_keywords(load_schema(MANIFEST_SCHEMA_PATH), used)
    for path in payload_schemas():
        _collect_keywords(load_schema(path), used)
    _collect_keywords(load_schema(ENVELOPE_SCHEMA_PATH), used)
    _collect_keywords(load_schema(FLEET_SCHEMA_PATH), used)
    _collect_keywords(load_schema(GATE_SCHEMA_PATH), used)
    for path in sorted(TELEMETRY_SCHEMAS.glob("*.json")):
        _collect_keywords(load_schema(path), used)

    implemented = set(module.IMPLEMENTED_KEYWORDS)
    unimplemented = sorted(used - implemented)
    assert not unimplemented, (
        f"core's schemas use {unimplemented} and harness/cafaye_contract.py does not "
        "implement them, so the harness would accept a document the schema rejects. "
        "Implement the keyword, or stop using it in schemas/ — do not leave the gap."
    )
    unused = sorted(implemented - used)
    assert not unused, (
        f"the harness implements {unused}, which no schema in core uses. Each one is a "
        "rule with no user and no test; delete it or add the example that exercises it."
    )


def test_the_harness_checks_the_format_vocabulary_core_uses() -> None:
    """`format` is a keyword that only asserts when a checker is installed.

    `tests/requirements.txt` already carries a note saying exactly this about
    `date-time`, and core pins `rfc3339-validator` because of it. This is the
    same rule applied to the harness: the formats a schema names are formats the
    harness must actually decide, because a `format` no one checks is a comment.
    """
    module = harness_module()
    used: set[str] = set()
    for path in sorted(SCHEMAS.rglob("*.json")):
        _collect_formats(load_schema(path), used)
    assert used, "no schema in core uses `format`, which would make this test vacuous"
    unchecked = sorted(used - set(module.CHECKED_FORMATS))
    assert not unchecked, (
        f"core's schemas name format {sorted(used)} and the harness decides "
        f"{sorted(module.CHECKED_FORMATS)}; {unchecked} would be assertions nobody makes. "
        "See tests/requirements.txt for why this is a real gap in core's own suite too."
    )


def test_the_harness_imports_nothing_outside_the_standard_library() -> None:
    """Static proof, because the runtime proof has a hole.

    `test_the_harness_runs_with_site_packages_disabled` proves the harness works
    with nothing installed. This proves why: the only modules it may import are
    the standard library's, and the check is an AST walk rather than a grep, so a
    `from x import y` in a function body is caught as readily as one at the top.
    """
    tree = ast.parse(HARNESS_MODULE.read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0 and node.module:
                imported.add(node.module.split(".")[0])
    # `__future__` is a compiler directive, not an import.
    imported.discard("__future__")
    outside = sorted(imported - HARNESS_STDLIB_ONLY)
    assert not outside, (
        f"harness/cafaye_contract.py imports {outside}. core has one dependency list "
        "(tests/requirements.txt) and the harness must not add a second: a check that "
        "needs a package is a check a Go service's CI cannot run."
    )


def test_the_harness_runs_with_site_packages_disabled() -> None:
    """The runtime half of the same claim, and the one that would fail first.

    `python -I -S` is the interpreter with user site-packages, `PYTHONPATH` and
    the site module all out of the way, so a harness that had grown a
    third-party import dies here rather than in a service's container.
    """
    completed = subprocess.run(
        [sys.executable, "-I", "-S", str(HARNESS_MODULE),
         "--core", str(REPO), str(HARNESS_FIXTURES / "conforming")],
        cwd=str(REPO),
        env={},
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == HARNESS_EXIT_CONFORMS, (
        f"the harness must run on the standard library alone, exited "
        f"{completed.returncode}\n{completed.stdout}\n{completed.stderr}"
    )


def test_the_harness_reaches_no_network_and_no_ambient_environment() -> None:
    """A contract check that needs the network is a contract check nobody runs.

    The proof is that the same directory gives the same answer with a full
    environment and with an empty one. A harness that read a proxy setting, a CI
    token, a `*_CORE_*` variable, a colour preference or a `$HOME` would differ,
    and each of those is a way for a developer's green to become a CI red that
    nobody can reproduce.
    """
    module = harness_module()
    service = HARNESS_FIXTURES / "conforming"
    with_env = module.run(service_root=service, core_root=REPO)
    completed = subprocess.run(
        [sys.executable, str(HARNESS_MODULE), "--core", str(REPO), str(service)],
        cwd=str(REPO),
        env={},
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == with_env.exit_code == HARNESS_EXIT_CONFORMS
    # `.rstrip` because `print` adds a newline and `render` does not: the
    # comparison is about the *answer*, not about how a process ends a line.
    assert completed.stdout.rstrip("\n") == module.render(with_env).rstrip("\n"), (
        "the harness's answer must not depend on the environment it was given:\n"
        f"empty: {completed.stdout!r}\n  full: {module.render(with_env)!r}"
    )
    # And nothing in the module can reach the network or run a command. Checked
    # on the AST rather than by grepping the text, because a grep cannot tell a
    # mention in prose from a call — and a test that fails on this module's own
    # docstrings is a test that gets deleted instead of fixed.
    tree = ast.parse(HARNESS_MODULE.read_text(encoding="utf-8"))
    called = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        parts = []
        target = node.func
        while isinstance(target, ast.Attribute):
            parts.append(target.attr)
            target = target.value
        if isinstance(target, ast.Name):
            parts.append(target.id)
        called.add(".".join(reversed(parts)))
    # Dotted, not bare: `re.compile` is not `compile`, and a bare attr match
    # would have failed on the module's own regex tables before it ever reached
    # anything dangerous — a test that fires on the wrong thing is a test that
    # gets deleted.
    for banned in (
        "os.system", "os.popen", "os.spawn", "os.execv", "os.fork", "os.forkpty",
        "eval", "exec", "compile", "__import__", "subprocess.run", "subprocess.Popen",
    ):
        assert banned not in called, (
            f"harness/cafaye_contract.py calls {banned}(). core is offline by contract, and a "
            "harness whose answer can depend on a process outside it is a harness whose "
            "answer depends on the day"
        )


def test_every_rule_the_harness_can_emit_is_declared_in_the_inventory() -> None:
    """The inventory is load-bearing, not documentation.

    Two hand-maintained lists — the ids in `harness/cafaye_contract.py` and the
    ids in `harness/rules.json` — that must be the same set. The tempting
    weakening is "every emitted id is declared", which is satisfied by a harness
    that emits two rules and an inventory of forty; the reverse direction is what
    catches a rule the inventory describes and the harness cannot reach.
    """
    module = harness_module()
    declared = set(harness_rules_by_id())
    emitted = set(module.RULE_IDS)
    assert emitted == declared, (
        f"the harness can emit {sorted(emitted - declared) or 'nothing extra'}, and "
        f"harness/rules.json declares {sorted(declared - emitted) or 'nothing extra'}; "
        "the two lists are the same rule inventory stated twice and must agree"
    )


def test_the_rule_inventory_says_where_every_rule_lives() -> None:
    """**This is the question core's own rule turns on, made mechanical.**

    core's one rule is that a rule not in `schemas/` is not a cafaye rule. The
    honest answer for the harness is that *some* rules are in a schema and some
    are in `docs/` and therefore in the harness's own source — and a reader of
    the README is owed that sentence field by field, not as a summary.

    So every rule declares an `enforcedBy` with a kind, and:
      * `schema` names a file under `schemas/` that exists;
      * `doc` names a file under `docs/` **and a heading in it** that exists —
        because a convention with no document is a rule in code, and saying
        `doc` is how that would be hidden;
      * `harness` names a function in the harness module, and that function is
        where the rule actually is.
    """
    module = harness_module()
    for rule_id, rule in sorted(harness_rules_by_id().items()):
        assert rule.get("claim"), f"{rule_id} has no claim: a rule nobody can state is not a rule"
        enforced = rule.get("enforcedBy") or {}
        kind = enforced.get("kind")
        assert kind in {"schema", "doc", "harness"}, f"{rule_id} has enforcedBy.kind={kind!r}"
        if kind == "schema":
            target = REPO / enforced["file"]
            assert target.is_file(), f"{rule_id} claims schema {enforced['file']}, which is not in the tree"
            assert target.is_relative_to(SCHEMAS), (
                f"{rule_id} claims a schema outside schemas/ ({enforced['file']}); core's rule "
                "is that the machine-readable contract lives there"
            )
        elif kind == "doc":
            target = DOCS / enforced["file"]
            assert target.is_file(), f"{rule_id} claims doc {enforced['file']}, which is not in the tree"
            text = target.read_text(encoding="utf-8")
            assert enforced["heading"] in text, (
                f"{rule_id} claims the heading {enforced['heading']!r} in {enforced['file']}, "
                "which the document does not have"
            )
        else:
            function = getattr(module, enforced["function"], None)
            assert callable(function), (
                f"{rule_id} claims the harness function {enforced['function']!r}, which does "
                "not exist — the rule is described and not implemented"
            )
        assert rule.get("doc"), f"{rule_id} does not cite the document that explains it"


def test_the_contract_harness_doc_and_the_inventory_agree() -> None:
    """A doc and an inventory are the same rule list written twice.

    core's doctrine — a document and its schema are the same contract stated
    twice, and the test is the enforcement — applied to the harness's own rule
    list. The table in `docs/contract-harness.md` is what a human reads; the
    inventory is what the harness and CI see.
    """
    assert HARNESS_DOC.is_file(), (
        f"{HARNESS_DOC.relative_to(REPO)} does not exist. A harness that ships with no "
        "document is exactly the 'a convention that lives only in the source' case core "
        "exists to prevent, and a reader has no way to learn what it does not check."
    )
    text = HARNESS_DOC.read_text(encoding="utf-8")
    documented = set(re.findall(r"^\|\s*`([a-z][a-z0-9.-]+)`\s*\|", text, flags=re.MULTILINE))
    declared = set(harness_rules_by_id())
    assert declared <= documented, (
        f"the harness enforces {sorted(declared - documented)}, which the document does not "
        "list. Either the document is behind the code or the code enforces a rule nobody "
        "was told about; both are the same defect."
    )
    assert documented == declared, (
        f"the document lists {sorted(documented - declared)}, which the harness does not "
        "enforce. A reader would believe a rule is checked when it is not."
    )


def test_the_contract_harness_doc_states_what_it_does_not_check() -> None:
    """The smaller harness must say out loud that the larger one is owed.

    A README that describes only what a tool does is read as a description of
    everything it does. The harness validates a repository's *declared*
    contracts; it does not validate live responses against the event payload
    schemas, and until a document says so a service owner will assume it does.
    """
    doc = HARNESS_DOC.read_text(encoding="utf-8").lower()
    for topic in ("does not", "live response", "payload schema", "owed"):
        assert topic in doc, (
            f"docs/contract-harness.md does not say {topic!r}; a harness that overstates "
            "itself is worse than a smaller one that does not"
        )


def test_the_harness_is_reachable_by_one_command() -> None:
    """`harness/bin/cafaye-contract` is what a service's CI calls.

    It is a wrapper, not a second implementation, and the assertion is that it
    *works* — the same defect class as core-06's `uses:` line, where a path that
    does not resolve looks exactly like one that does.
    """
    assert HARNESS_WRAPPER.is_file(), f"{HARNESS_WRAPPER.relative_to(REPO)} does not exist"
    assert os.access(HARNESS_WRAPPER, os.X_OK), (
        f"{HARNESS_WRAPPER.relative_to(REPO)} is not executable; a service's CI would get "
        "permission denied, which is not a message anybody can act on"
    )
    completed = subprocess.run(
        [str(HARNESS_WRAPPER), "--core", str(REPO), str(HARNESS_FIXTURES / "conforming")],
        cwd=str(REPO),
        env={},
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == HARNESS_EXIT_CONFORMS, (
        f"the wrapper must run the harness, exited {completed.returncode}\n"
        f"{completed.stdout}\n{completed.stderr}"
    )


def test_the_harness_proves_it_can_fail_by_breaking_itself() -> None:
    """core's own rule, applied to the harness: N breakages, N reds.

    This does not run `harness/tests/self_test.sh` — it runs the harness against
    the non-conforming fixtures, which is the cheap half of the same proof, and
    the script is the thorough half. What is asserted here is that the script
    exists, is executable, and names the breakages it makes, because a
    self-test that is not wired to anything is a self-test that has never run.
    """
    assert HARNESS_SELF_TEST.is_file(), f"{HARNESS_SELF_TEST.relative_to(REPO)} does not exist"
    assert os.access(HARNESS_SELF_TEST, os.X_OK), "the self-test is not executable"
    text = HARNESS_SELF_TEST.read_text(encoding="utf-8")
    count = text.count("expect_red")
    assert count >= 10, (
        f"the self-test makes {count} expect_red calls; kit's precedent is one deliberate "
        "breakage per check, and fewer than ten is not a proof that the checks are "
        "independent"
    )
    assert "unbroken tree" in text, "the control must run first, or the breakages prove nothing"
    for name in ("core.digest-mismatch", "yaml.unsupported", "core.absent"):
        assert name in text, f"the self-test does not break {name}, so that rule is unproved"


def test_every_rule_the_harness_can_emit_is_proved_able_to_go_red() -> None:
    """One breakage per rule, by name — the stronger form of the count above.

    `test_the_harness_proves_it_can_fail_by_breaking_itself` asserts the script
    makes *some* number of breakages. This asserts the number is not arbitrary:
    every id the harness can emit appears in the self-test, so a rule nobody
    broke is a rule nobody has watched fail, and a rule that can only fire on a
    document no fixture produces is a rule that has never fired at all.
    """
    module = harness_module()
    text = HARNESS_SELF_TEST.read_text(encoding="utf-8")
    missing = [rule for rule in module.RULE_IDS if rule not in text]
    assert not missing, (
        f"the self-test does not break {missing}. A rule with no breakage is a rule nobody "
        "has tested — add the mutation that makes the harness go red, and name the rule in "
        "the expectation so a red caught by the wrong check cannot read as a pass."
    )


def _collect_keywords(node, found: set[str]) -> None:
    """Every JSON Schema **keyword** appearing anywhere in a schema document.

    Schema-shaped, not a generic walk. A generic walk that recursed into every
    value would add every *property name* it saw — `name`, `language`, `core` —
    to the keyword set, and the harness would then be "missing" a keyword called
    `team`. The three keyword groups below are the ones whose values are
    schemas, which is the only place the distinction matters.
    """
    annotations = {
        "$schema", "$id", "$comment", "title", "description", "default",
        "examples", "deprecated", "readOnly", "writeOnly",
    }
    if not isinstance(node, dict):
        return
    for key, value in node.items():
        if key in annotations:
            continue
        found.add(key)
        if key in SCHEMA_MAP_KEYWORDS and isinstance(value, dict):
            for nested in value.values():
                _collect_keywords(nested, found)
        elif key in SUBSCHEMA_KEYWORDS:
            _collect_keywords(value, found)
        elif key in SUBSCHEMA_LIST_KEYWORDS and isinstance(value, list):
            for nested in value:
                _collect_keywords(nested, found)


def _collect_formats(node, found: set[str]) -> None:
    """Every `format` value named anywhere in a schema, via the same walk."""
    if not isinstance(node, dict):
        return
    if isinstance(node.get("format"), str):
        found.add(node["format"])
    for key, value in node.items():
        if key in SCHEMA_MAP_KEYWORDS and isinstance(value, dict):
            for nested in value.values():
                _collect_formats(nested, found)
        elif key in SUBSCHEMA_KEYWORDS:
            _collect_formats(value, found)
        elif key in SUBSCHEMA_LIST_KEYWORDS and isinstance(value, list):
            for nested in value:
                _collect_formats(nested, found)


# --------------------------------------------------------------------------
# 9. the SLO and error-budget spec (PLAN.md §7b)
# --------------------------------------------------------------------------

# The failure modes this section exists to make impossible to write by accident:
# an SLO nobody is paged for, an SLO on cpu rather than on behaviour, a per-tenant
# SLI, a burn-rate threshold that is 14.4 or 15 or 14 for no stated reason, an
# SLO at 100%, and an "SLA" for a tier the platform team does not operate. Each
# one is a schema constraint plus a test plus a paragraph in docs/slo.md.


def slo_entry(document: dict) -> dict:
    """The first SLO of a declaration, for a test that mutates one field."""
    return document["slos"][0]


def slo_document(**changes) -> dict:
    """A fresh copy of the worked example with `changes` applied to its SLO."""
    document = copy.deepcopy(load_document(VALID_SLO))
    slo_entry(document).update(changes)
    return document


def slo_alerting(tier: str, page: bool, ticket: bool) -> dict:
    """The worked example, moved to `tier` with the alerts the tier implies.

    The alerts move with the tier on purpose: `tier: critical` over a `low`'s
    `page_alert.disable: true` is itself a violation, so a helper that set the
    tier alone would report every tier as broken and the test would prove
    nothing about the derivation.
    """
    return slo_document(
        tier=tier,
        alerting={
            "name": "ExampleServiceHttpAvailability",
            "annotations": {
                "summary": "example-service is failing widget requests",
                "runbook_url": (
                    "https://runbooks.cafaye.com/example-service/"
                    "example-service-http-availability"
                ),
            },
            "page_alert": {"disable": page},
            "ticket_alert": {"disable": ticket},
        },
    )


def window_document() -> dict:
    """The normative window catalog, as a document."""
    return {
        "version": "prometheus/v1",
        "windows": [{"window": window, "factor": factor} for window, factor in SLO_WINDOW_CATALOG],
    }


def sli_catalogue() -> dict:
    """The SLI catalogue the metrics schema declares, keyed by logical name."""
    schema = load_schema(SLO_METRICS_SCHEMA_PATH)
    return schema["properties"]["slis"]["properties"]


def sli_catalogue_document() -> dict:
    """The catalogue as the document it also validates.

    Built from the schema's own `const` and `enum` values rather than written out
    a second time, so the positive example and the schema cannot drift — and so
    the assertion that the catalogue is *satisfiable* is about the schema alone.
    """
    def consts(entry: dict, names: tuple[str, ...]) -> dict:
        return {name: entry["properties"][name]["const"] for name in names}

    schema = load_schema(SLO_METRICS_SCHEMA_PATH)
    return {
        "slis": {
            name: {
                **consts(entry, ("otelName", "errorOtelName", "totalMetric", "errorMetric")),
                "errorSelector": entry["properties"]["errorSelector"]["default"],
                "labels": entry["properties"]["labels"]["items"]["enum"],
                "requiredLabels": entry["properties"]["requiredLabels"]["default"],
                "description": entry["properties"]["description"]["const"],
            }
            for name, entry in sorted(sli_catalogue().items())
        },
        "allowedLabels": schema["properties"]["allowedLabels"]["items"]["enum"],
        "forbidden": {
            "unboundedDimensions": schema["properties"]["forbidden"]["properties"]
            ["unboundedDimensions"]["items"]["enum"],
            "infrastructureSignals": schema["properties"]["forbidden"]["properties"]
            ["infrastructureSignals"]["items"]["enum"],
        },
    }


def prometheus_suffix(metric: str, otel_name: str) -> tuple[str, str] | None:
    """`(unit suffix, type suffix)` if `metric` is `otel_name` normalized, else None.

    The exporter's translation, as a derivation: `http.server.request.duration`
    becomes `http_server_request_duration` and then takes `_seconds` (the UCUM
    unit `s` in Prometheus's spelling) and `_count` (the count series of a
    histogram). Written out here so the test below asks the same question the
    catalogue exists to answer — *is this the OTel name, normalized, or something
    a hand-written string got wrong?* — rather than comparing a list to a list.
    """
    base = otel_name.replace(".", "_")
    if not metric.startswith(base):
        return None
    tail = metric[len(base):]
    for unit in PROMETHEUS_UNIT_SUFFIXES:
        for kind in PROMETHEUS_TYPE_SUFFIXES:
            if unit + kind == tail:
                return unit, kind
    return None


def test_the_slo_examples_validate() -> None:
    """The positive half. Both documents are read by the harness's YAML reader too.

    `test_the_harness_yaml_reader_reads_every_document_in_this_repository` walks
    every YAML file core owns, so a Sloth spec example that the harness cannot
    read would be an artifact no service's CI could check.
    """
    for document, schema in (
        (VALID_SLO, SLO_SCHEMA_PATH),
        (VALID_SLO_WINDOWS, SLO_WINDOWS_SCHEMA_PATH),
    ):
        found = failures_for(load_document(document), load_schema(schema))
        assert not found, (
            f"{document.relative_to(REPO)} must satisfy {schema.name}:\n  "
            + "\n  ".join(str(f) for f in found)
        )


def test_an_slo_at_one_hundred_percent_is_rejected() -> None:
    """R8, in the schema rather than in a comment.

    An objective of 100% is an SLO that can only ever be *reacted to*: the budget
    is zero, so there is no rate at which burning it is worth a page, and the
    alert either never fires or fires on the first bad minute of the quarter. The
    example it comes from also carries the other half of "an SLO nobody can keep",
    a 30-day period, because both are the same mistake — a number written to look
    safe.
    """
    schema = load_schema(SLO_SCHEMA_PATH)
    found = failures_for(load_document(INVALID_SLO_PERFECT), schema)
    assert_keywords(found, (
        ("exclusiveMaximum", "slos/0/objective"),
        ("const", "slos/0/period"),
    ))
    # And the control: the same document with a reachable objective and the
    # 28-day period validates, so the rejection cannot be passing for a reason.
    healed = copy.deepcopy(load_document(INVALID_SLO_PERFECT))
    healed["slos"][0]["objective"] = 99.9
    healed["slos"][0]["period"] = SLO_PERIOD
    assert not failures_for(healed, schema), (
        "the invalid SLO example is also wrong for another reason, so the two "
        "assertions above would pass on the wrong defect:\n  "
        + "\n  ".join(str(f) for f in failures_for(healed, schema))
    )


def test_the_tier_alone_decides_whether_a_page_is_generated() -> None:
    """R4, and the single most important rule in the packet.

    A page-level burn alert per SLO across seven services is textbook alert
    fatigue: the self-hoster mutes them within a week, and muting them costs the
    whole instrument. So the tier decides, the schema enforces the decision, and
    both directions are checked for every tier — a rule that only refuses the bad
    half would accept a service that pages nothing.
    """
    schema = load_schema(SLO_SCHEMA_PATH)
    for tier, (page, ticket) in sorted(SLO_TIER_ALERTS.items()):
        assert not failures_for(slo_alerting(tier, page, ticket), schema), (
            f"a tier: {tier} SLO with page_alert.disable={page} and "
            f"ticket_alert.disable={ticket} must validate"
        )
        for alert, wanted in (("page_alert", page), ("ticket_alert", ticket)):
            document = slo_alerting(tier, page, ticket)
            document["slos"][0]["alerting"][alert]["disable"] = not wanted
            assert_keywords(
                failures_for(document, schema),
                (("const", f"slos/0/alerting/{alert}/disable"),),
            )

    # And the derivation is *in* the schema, one branch per tier, rather than
    # implied by the enum. A behavioural test alone is satisfied by an SLO schema
    # that happened to refuse the four cases above and nothing else.
    branches = load_schema(SLO_SCHEMA_PATH)["$defs"]["slo"]["allOf"]
    derived = {}
    for branch in branches:
        condition = branch["if"]["properties"]["tier"]
        tiers = [condition["const"]] if "const" in condition else list(condition["enum"])
        alert = branch["then"]["properties"]["alerting"]["properties"]
        for tier in tiers:
            derived[tier] = (
                alert["page_alert"]["properties"]["disable"]["const"],
                alert["ticket_alert"]["properties"]["disable"]["const"],
            )
    assert derived == SLO_TIER_ALERTS, (
        f"the schema derives {derived}, so the tier decides something other than the two "
        "alert switches. Every tier must have a branch, or a tier nobody thought about "
        "falls through with both alerts enabled."
    )


def test_an_slo_needs_a_description_and_a_runbook() -> None:
    """An SLO nobody can read is a chart rather than a contract, and an alert with
    no runbook is a page with no first move.

    The example is the worked SLO with both deleted, which is the shape a hurried
    service ships: the numbers are there and nothing says what they promise.
    """
    schema = load_schema(SLO_SCHEMA_PATH)
    document = slo_document()
    del document["slos"][0]["description"]
    # `required` reports against the object that is missing the key, not against
    # a path that does not exist yet — so the assertion names `slos/0`.
    assert_keywords(failures_for(document, schema), (("required", "slos/0"),))
    assert any(
        "description" in failure.message
        for failure in failures_for(document, schema)
    ), "the rejection has to name the field it rejected, or it sends a reader to the schema"
    document = slo_document()
    del document["slos"][0]["alerting"]["annotations"]["runbook_url"]
    assert_keywords(
        failures_for(document, schema),
        (("required", "slos/0/alerting/annotations"),),
    )


def test_an_slo_may_not_carry_the_word_an_sla_would() -> None:
    """R5, refused in the declaration rather than promised against in prose.

    A self-hosted deployment gets an SLO describing intended behaviour on
    adequate hardware, measured by the operator. The string an SLA would carry is
    not a thing this schema can express, and a description that contains it is a
    service telling its customers it has promised something the platform team
    does not operate.
    """
    schema = load_schema(SLO_SCHEMA_PATH)
    assert_keywords(
        failures_for(slo_document(description="99.9% availability, SLA-backed."), schema),
        (("not", "slos/0/description"),),
    )


def test_the_window_catalog_is_the_workbooks_numbers() -> None:
    """R2, as arithmetic rather than as a number in a comment.

    `14.4` is `0.02 x 720h`: the factor at which the **one-hour** window consumes
    2% of the budget the workbook derived it against. Rounded to 15 it fires
    *before* 2% of the budget is gone, which is the question every self-hoster
    asks and the reason the arithmetic is in the spec rather than the number
    alone.

    And the arithmetic does not agree with the period, which is the finding: 720
    hours is thirty days, and R3 mandates twenty-eight. So the catalog's 14.4 is
    ~7% conservative under a 28-day budget — the fast-burn alert fires slightly
    earlier than the workbook intends. That is implemented as ruled and asserted
    here in the direction it errs, so a future flip to 13.44 is a deliberate
    one-line change with a test saying so (**D27**).
    """
    schema = load_schema(SLO_WINDOWS_SCHEMA_PATH)
    assert not failures_for(window_document(), schema), "the normative catalog must validate"

    declared = [
        (item["properties"]["window"]["const"], item["properties"]["factor"]["const"])
        for item in schema["properties"]["windows"]["prefixItems"]
    ]
    assert declared == list(SLO_WINDOW_CATALOG), (
        f"the window catalog is {declared}, not {list(SLO_WINDOW_CATALOG)}"
    )
    assert schema["properties"]["windows"]["minItems"] == len(SLO_WINDOW_CATALOG)
    assert schema["properties"]["windows"]["maxItems"] == len(SLO_WINDOW_CATALOG)
    assert schema["properties"]["windows"].get("items") is False, (
        "exactly the catalog's windows are allowed — `items: false` is what refuses a ninth"
    )

    fast = dict(SLO_WINDOW_CATALOG)[SLO_WINDOW_CATALOG[0][0]]
    assert fast == SLO_BUDGET_FRACTION * SLO_WORKBOOK_HOURS, (
        f"the fast-burn factor is {fast}, and 2% of the 720-hour budget the workbook "
        f"derived it against is {SLO_BUDGET_FRACTION * SLO_WORKBOOK_HOURS}. 14.4 is not 15: "
        "rounded up, the alert fires before 2% of the budget is gone."
    )
    under_this_period = SLO_BUDGET_FRACTION * SLO_PERIOD_HOURS
    assert fast > under_this_period, (
        f"the catalog's {fast} against a 28-day budget's {under_this_period}: the workbook's "
        "factors are derived from a 30-day budget, so under R3's 28-day period they fire "
        f"{(fast / under_this_period - 1) * 100:.0f}% early. That is the conservative "
        "direction, it is implemented as ruled, and flipping it is D27 — not a quiet edit "
        "to a number nobody recomputed."
    )

    # A ninth window, and a swapped factor, are both refused — and the position
    # matters, because Sloth consumes these in short/long pairs.
    extra = window_document()
    extra["windows"].append({"window": "1w", "factor": 1})
    assert_keywords(failures_for(extra, schema), (("maxItems", "windows"),))
    swapped = window_document()
    swapped["windows"][2]["factor"] = 15.0
    assert_keywords(failures_for(swapped, schema), (("const", "windows/2/factor"),))


def test_a_service_may_not_override_the_window_catalog() -> None:
    """R2's other half: the catalog is pinned once, in core.

    Sloth takes `--slo-period-windows-path` precisely so a project can carry its
    own, and a project that does is a project whose burn alerts mean something
    other than the workbook's. The declaration is closed, so the override is an
    undeclared key rather than a judgement call.
    """
    found = failures_for(
        load_document(INVALID_SLO_WINDOW_OVERRIDE), load_schema(SLO_SCHEMA_PATH)
    )
    assert_keywords(found, (("additionalProperties", "slos/0"),))
    assert not failures_for(slo_document(), load_schema(SLO_SCHEMA_PATH)), (
        "the worked example must not carry the override the invalid one does, or the "
        "assertion above passes for the wrong reason"
    )


def test_the_slo_catalog_declares_r6s_candidates_and_normalizes_every_name() -> None:
    """R6 and the reason `slo-metrics.schema.json` exists.

    Six languages each writing `http_server_request_duration_seconds_bucket` by
    hand is six chances to write `http_server_request_duration_seconds` instead,
    and the mistake is invisible until a query returns nothing at 3am. So every
    catalogue metric is asserted to be the *normalization* of the OpenTelemetry
    name beside it, and the check is a derivation rather than a second list.
    """
    schema = load_schema(SLO_METRICS_SCHEMA_PATH)
    entries = sli_catalogue()
    assert set(entries) == set(SLO_CATALOG_ENTRIES), (
        f"the catalogue declares {sorted(entries)}; R6's candidates are "
        f"{sorted(SLO_CATALOG_ENTRIES)}"
    )
    for name, entry in sorted(entries.items()):
        for role, name_field in (
            ("totalMetric", "otelName"),
            ("errorMetric", "errorOtelName"),
        ):
            otel_name = entry["properties"][name_field]["const"]
            metric = entry["properties"][role]["const"]
            suffix = prometheus_suffix(metric, otel_name)
            assert suffix is not None, (
                f"{name}.{role} is {metric!r}, which is not {otel_name!r} normalized "
                "(dots to underscores, then the UCUM unit, then the series type). Either "
                "the metric or the OTel name it came from is wrong."
            )
            assert suffix[1] != "", (
                f"{name}.{role} is {metric!r} with no series suffix. An SLI counts events, "
                "so it reads a `_count` or a `_total`; without one it is a name, not a "
                "series."
            )
    assert not failures_for(sli_catalogue_document(), schema), (
        "the catalogue the schema declares must satisfy the schema it is declared in:\n  "
        + "\n  ".join(str(f) for f in failures_for(sli_catalogue_document(), schema))
    )


def test_the_two_denylists_are_two_prohibitions_and_the_schema_refuses_each() -> None:
    """The denylist, as two lists with two reasons, and refused twice.

    Unbounded dimensions are already barred by `metrics.schema.json` on the
    2000-combination cap; infrastructure signals are barred here because an SLO
    on a CPU is not an SLO on behaviour (R6). One merged list would keep the
    enforcement and lose the reason, and the reason is what a reader has when
    they are about to add one — so the lists are separate properties, and the
    schema's `not` is asserted to be exactly their union.
    """
    schema = load_schema(SLO_METRICS_SCHEMA_PATH)
    forbidden = schema["properties"]["forbidden"]["properties"]
    assert set(forbidden) == {"unboundedDimensions", "infrastructureSignals"}, (
        f"the two prohibitions are {sorted(forbidden)}; they are two prohibitions "
        "because they have two different reasons"
    )
    assert forbidden["unboundedDimensions"]["items"]["enum"] == list(SLO_UNBOUNDED_DIMENSIONS)
    assert forbidden["infrastructureSignals"]["items"]["enum"] == list(SLO_INFRASTRUCTURE_SIGNALS)
    assert not set(SLO_UNBOUNDED_DIMENSIONS) & set(SLO_INFRASTRUCTURE_SIGNALS), (
        "a substring in both lists belongs to one prohibition or the other, not both"
    )
    for group, values in (
        ("unboundedDimensions", forbidden["unboundedDimensions"]),
        ("infrastructureSignals", forbidden["infrastructureSignals"]),
    ):
        assert values.get("description"), f"{group} has to say why, not only what"

    alternatives = set(
        schema["$defs"]["metricName"]["not"]["pattern"].split("|")
    )
    assert alternatives == set(SLO_UNBOUNDED_DIMENSIONS) | set(SLO_INFRASTRUCTURE_SIGNALS), (
        f"the schema's `not` refuses {sorted(alternatives)}, which is not the union of the "
        "two lists — so the lists describe something the schema does not enforce"
    )

    # And every substring really is refused, both in the catalogue and in a
    # declaration that carries one. Refused twice on purpose: the `const` says it
    # is not the metric this SLI uses, the `not` says it is not a metric any SLI
    # may use, and a rule enforced once is a rule a well-meaning commit undoes.
    for denylisted in ("node_memory_usage_bytes", "http_tenant_requests_total"):
        document = sli_catalogue_document()
        document["slis"]["invoice_computed"]["totalMetric"] = denylisted
        found = failures_for(document, schema)
        assert_keywords(found, (
            ("const", "slis/invoice_computed/totalMetric"),
            ("not", "slis/invoice_computed/totalMetric"),
        ))
    assert_keywords(
        failures_for(load_document(INVALID_SLO_DENYLISTED), schema),
        (
            ("const", "slis/invoice_computed/totalMetric"),
            ("not", "slis/invoice_computed/totalMetric"),
        ),
    )


def test_every_catalogue_label_is_one_the_metric_spec_allows() -> None:
    """The allowlist is the measurement attributes, Postgres-normalized.

    `service.name` -> `service_name`, `http.response.status_code_class` ->
    `http_response_status_code_class`: the same attribute, in the spelling the
    collector writes. An SLI filtering on `http.route` rather than
    `http_http_route` measures nothing and says nothing, and which spelling is
    right is exactly the thing six languages get wrong by hand.
    """
    schema = load_schema(SLO_METRICS_SCHEMA_PATH)
    allowed = set(schema["properties"]["allowedLabels"]["items"]["enum"])
    measured = {
        "service_name",  # service.name, the resource attribute
        *(name.replace(".", "_") for name in measurement_attribute_names()),
    }
    assert measured <= allowed, (
        f"the metric schema allows {sorted(measured - allowed)} and the SLI allowlist does "
        "not. Every dimension an SLO may filter on is a dimension a metric may carry."
    )
    for forbidden in (*SLO_UNBOUNDED_DIMENSIONS, *SLO_INFRASTRUCTURE_SIGNALS):
        assert not any(forbidden in label for label in allowed), (
            f"{forbidden!r} is on the SLI label allowlist"
        )
    for name, entry in sorted(sli_catalogue().items()):
        labels = set(entry["properties"]["labels"]["items"]["enum"])
        assert labels <= allowed, f"{name} filters on labels outside the allowlist: {labels - allowed}"
        assert set(entry["properties"]["requiredLabels"]["items"]["enum"]) <= labels, (
            f"{name} requires a label it does not list as usable"
        )
        assert "service_name" in labels, (
            f"{name} does not list service_name. An SLI that does not scope itself to its own "
            "service is the fleet-wide ratio, which is the failure mode R6 rules out."
        )


def test_the_two_denylists_cover_the_queries_and_not_only_the_catalogue() -> None:
    """The prohibitions reach the queries a service commits.

    A catalogue that names no CPU is not enough: the query is the thing Prometheus
    evaluates, so the harness refuses a denylisted label in one and refuses it in
    the catalogue. This asserts the rule ids exist and that the conforming
    fixture's queries carry none of the eight substrings, which is the receipt
    that the check is running at all.
    """
    text = load_document(VALID_SLO)["slos"][0]["sli"]["events"]
    for query in text.values():
        for value in (*SLO_UNBOUNDED_DIMENSIONS, *SLO_INFRASTRUCTURE_SIGNALS):
            assert value not in query, f"the worked example filters on {value!r}"


def test_the_slo_doc_covers_every_topic_the_rulings_require() -> None:
    """The document and the schemas are the same contract written twice.

    Each string is a claim that has to be *in the document* for the reader who
    arrives with the question it answers — which is most of what a spec is for.
    """
    assert SLO_DOC.is_file(), (
        f"{SLO_DOC.relative_to(REPO)} does not exist. Three schemas with no document is the "
        "'a convention that lives only in the source' case core exists to prevent."
    )
    text = SLO_DOC.read_text(encoding="utf-8").lower()
    for topic in SLO_DOC_TOPICS:
        assert topic.lower() in text, (
            f"docs/slo.md does not cover {topic!r}. A spec a self-hoster cannot answer "
            "'why 14.4' from is a spec with a number in it and no reason."
        )


def test_the_slo_doc_publishes_the_arithmetic_and_the_exclusion_list() -> None:
    """Why 14.4 is not 15, and what an SLO here does not cover.

    Both halves are the self-hoster's first two questions, and the second one is
    the one a service-level *agreement* would be obliged to answer with a
    contract. An SLO answers it with a measurement, an operator and a list.
    """
    text = SLO_DOC.read_text(encoding="utf-8")
    assert "0.02" in text and "720" in text, (
        "docs/slo.md must publish the arithmetic behind 14.4 (0.02 x 720h), not the number"
    )
    assert "no sla" in text.lower(), (
        "docs/slo.md must say in its own words that there is no SLA and what stands in its place"
    )
    for excluded in ("adequate hardware", "exclusion"):
        assert excluded in text.lower(), (
            f"docs/slo.md must state the {excluded!r} half of what an SLO does not promise"
        )


def test_the_slo_doc_says_where_multi_tenant_answers_come_from() -> None:
    """The multi-tenancy question, answered before a reader has to ask it.

    A per-tenant SLI at one private product and twenty users is unaffordable and
    guarantees alert fatigue; a per-tenant *dimension* on a metric is already
    prohibited by `metrics.schema.json` on the 2000-combination cap, while
    `tenant_id` on `resourceAttributes` is required and exempt from that cap. So
    the honest answer is not a choice between the two: the metric is aggregate,
    and attribution is a logs-and-traces question over the resource attributes.
    """
    text = SLO_DOC.read_text(encoding="utf-8").lower()
    for topic in ("aggregate", "recording rule", "resourceattribute", "logs and traces", "2000"):
        assert topic in text, (
            f"docs/slo.md does not say {topic!r}. The next reader will ask whether an SLO is "
            "per-tenant, and 'the schema already prohibits it' is the answer."
        )


def test_the_slo_doc_requires_native_instrumentation_and_a_pinned_collector() -> None:
    """The spanmetrics migration, and why the collector is what moves.

    If a service derives RED metrics through the `spanmetrics` connector, the
    connector's unit default is migrating from `ms` to `s`, which renames
    `traces_span_metrics_duration_milliseconds_bucket` to `..._seconds_bucket`
    and breaks every latency query in every service at once — between the service
    and Prometheus, where no service-level test can see it. So: native OTel HTTP
    instrumentation over spanmetrics-derived metrics, and a collector version
    pinned in the kit templates whose bumps are breaking changes.
    """
    text = SLO_DOC.read_text(encoding="utf-8").lower()
    for topic in (
        "spanmetrics",
        "native",
        "http.server.request.duration",
        "collector",
        "pinned",
        "breaking change",
    ):
        assert topic in text, f"docs/slo.md does not say {topic!r}"
    assert "stable" in text, (
        "the reason native instrumentation is available must be stated: "
        "http.server.request.duration is Stable, with recommended bucket boundaries"
    )


def test_no_sla_token_appears_in_a_schema_or_an_example() -> None:
    """R5, checked over the machine-readable half of the repository.

    "No SLA. Anywhere." is checkable for the artifacts and only arguable for
    prose: a schema's `const`, `enum` or `default` is a value a machine reads
    into a document, and a value that could say it is a vocabulary cafaye does
    not have. `pattern` is deliberately *not* walked — the one pattern in core
    that names it is `$defs/noSla`'s, which exists to refuse it, and a check
    that refused the refusal would be a check against its own mechanism. The
    examples are walked whole, because an example is a declaration.
    """
    def machine_values(node, found: set[str]) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if key in {"const", "enum", "default", "examples"}:
                    found.update(
                        item for item in (value if isinstance(value, list) else [value])
                        if isinstance(item, str)
                    )
                machine_values(value, found)
        elif isinstance(node, list):
            for item in node:
                machine_values(item, found)

    offenders = []
    for path in sorted(SCHEMAS.rglob("*.json")):
        values: set[str] = set()
        machine_values(load_schema(path), values)
        if any("SLA" in value for value in values):
            offenders.append(path.relative_to(REPO).as_posix())
    for path in sorted(EXAMPLES.rglob("*")):
        if not path.is_file() or path.suffix not in {".json", ".yml", ".yaml"}:
            continue
        if "SLA" in path.read_text(encoding="utf-8"):
            offenders.append(path.relative_to(REPO).as_posix())
    assert not offenders, (
        f"{offenders} carry the acronym a service-level agreement would carry. A "
        "self-hosted deployment gets an SLO: intended behaviour on adequate hardware, "
        "measured by the operator, with the exclusions published."
    )
    # And the mechanism that refuses it is itself a schema constraint, not a
    # reminder — this is the assertion that would fail if `noSla` were deleted.
    assert_keywords(
        failures_for(slo_document(description="99.9% availability, SLA-backed."), load_schema(SLO_SCHEMA_PATH)),
        (("not", "slos/0/description"),),
    )


def test_no_slo_example_declares_a_real_fleet_service() -> None:
    """The packet boundary, as an assertion rather than as a promise.

    "Do not write SLOs for the seven services" is a sentence in a brief; this is
    the test that keeps it true. An example that named `courier` *would be*
    courier's SLO, with a threshold nobody chose and an alert nobody paged — and
    the next packet would have to either keep it or contradict it. So the worked
    examples name a service that is not a service.
    """
    real = {service["name"] for service in load_fleet()["services"]}
    assert len(real) >= 5, f"fleet.yml looks truncated: {sorted(real)}"
    document = load_document(VALID_SLO)
    assert document["service"] not in real, (
        f"{VALID_SLO.relative_to(REPO)} declares service {document['service']!r}, which is a "
        f"real service in fleet.yml. Declaring an SLO for a real service is the next "
        "packet's work: the metrics do not exist yet and nobody has chosen the objective."
    )


def test_the_slo_harness_rules_are_all_reachable_from_one_document() -> None:
    """One fixture, every SLO rule, and the exact set.

    The assertion shape is the one `test_the_harness_reports_every_convention_rule_
    one_manifest_breaks` uses, for the same reason: "reports at least these eight"
    is satisfied by a harness that reports one and silently drops seven, and a
    dropped rule reads exactly like an upheld one.
    """
    result = harness_runs(HARNESS_FIXTURES / "nonconforming-slos")
    assert result.exit_code == HARNESS_EXIT_VIOLATIONS, (
        f"a service whose SLOs break eight rules must exit {HARNESS_EXIT_VIOLATIONS}, "
        f"got {result.exit_code}"
    )
    found = {finding.rule for finding in result.findings}
    assert found == NONCONFORMING_SLO_RULES, (
        f"expected exactly {sorted(NONCONFORMING_SLO_RULES)}, got {sorted(found)}:\n  "
        + "\n  ".join(f"{f.rule} {f.path}: {f.message}" for f in result.findings)
    )


def test_the_harness_checks_a_service_slo_declarations() -> None:
    """The control: a service whose SLOs are canonical reports nothing.

    Without this the eight rules above could all pass on a fixture that is
    rejected by the schema for an unrelated reason, which is how a conformance
    tool ends up refusing every document and looking busy.
    """
    result = harness_runs(HARNESS_FIXTURES / "conforming")
    assert result.findings == (), (
        "the conforming fixture's SLOs must pass every SLO rule:\n  "
        + "\n  ".join(f"{f.rule} {f.path}: {f.message}" for f in result.findings)
    )
    assert sorted((HARNESS_FIXTURES / "conforming" / "slos").glob("*.yaml")), (
        "the conforming fixture carries no SLO declaration, so the SLO rules are never "
        "exercised on the accepting side"
    )


def test_a_service_with_no_slos_directory_is_not_a_refusal() -> None:
    """Absence is not a failure, and the reason is the precedent, not a shrug.

    `worker-only.cafaye.yml` declares no `exposes.api` and is a valid manifest, so
    a repository with no HTTP contract is checked on no HTTP rules and still
    passes. The same shape applies to SLOs: the harness validates declared
    contracts, and a directory it never wrote declares nothing. What it may not
    do is convert the absence into a green badge for the SLOs it *has* — which is
    what the refusal rules are for, and what `rules.json` records as not yet
    enforced.
    """
    result = harness_runs(HARNESS_FIXTURES / "nonconforming-conventions")
    for fixture in ("nonconforming-conventions", "nonconforming-openapi"):
        assert not (HARNESS_FIXTURES / fixture / "slos").exists(), (
            f"the {fixture} fixture must declare no slos/, or the SLO rules would fire on it"
        )
        run = harness_runs(HARNESS_FIXTURES / fixture)
        assert not any(finding.rule.startswith("slo.") for finding in run.findings), (
            f"a service that declares no slos/ is checked on no SLO rules, and the "
            f"{fixture} fixture must show that: {[f.rule for f in run.findings]}"
        )
    assert result.exit_code == HARNESS_EXIT_VIOLATIONS
    not_enforced = json.loads(HARNESS_RULES.read_text(encoding="utf-8"))["notEnforced"]
    assert any("slos/" in entry.get("why", "") for entry in not_enforced), (
        "harness/rules.json must record, in notEnforced, that a service with no slos/ "
        "directory is checked by nothing — the one honest statement about an optional "
        "declaration, and the one that stops the absence from reading as a pass"
    )


# --------------------------------------------------------------------------
# 10. the gate declaration (core-09)
# --------------------------------------------------------------------------
#
# A gate that is discovered by getting it wrong is not a gate, and this fleet
# has five spellings of "run the gate" across fifteen repositories. The
# declaration is `gate.yml`, the format is `schemas/gate.schema.json`, the
# checker is `harness/gate_check.py`, and the argument for that shape instead
# of mise-tasks-alone or a CI workflow is in docs/gate.md.
#
# The tests below are in four groups, and the order is the argument:
#
#   1. the format is well-formed — the schema, the examples, and the checker's
#      re-implementation of the schema reaching the same answer;
#   2. core's own declaration is TRUE — the checker is green on core, the floor
#      is not behind the suite, the mise task is the fleet's spelling;
#   3. the checker can FAIL — the three red proofs the packet names, in
#      `tests/test_specs.py` itself, so `bin/prime` goes red if any of them
#      stops being caught and not only when somebody remembers to run the
#      self-test;
#   4. the checker's own promises — the tri-state, the inventory, the stdlib,
#      the no-secrets property, and the `PIPESTATUS` line in the doc.


def gate_module():
    """`harness/gate_check.py`, imported in-process.

    In-process rather than by subprocess so a test can assert on the `Report`
    the checker returns instead of on the text it printed. The subprocess
    proofs exist too, where the claim is about the process rather than about
    the answer.
    """
    if str(HARNESS) not in sys.path:
        sys.path.insert(0, str(HARNESS))
    import gate_check  # noqa: PLC0415 - a sibling module, imported on demand

    return gate_check


def gate_fixture_repo(work: Path) -> Path:
    """A throwaway copy of the conforming gate fixture, and nothing else.

    The fixture is one small repository that declares its gate and tells the
    truth about all of it. Every red proof below is that repository with one
    thing changed, so a red proves *this check* is load-bearing rather than
    that something went red.
    """
    target = work / "repo"
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(GATE_FIXTURE, target)
    # `shutil.copytree` preserves the mode, but a fixture that reached a
    # checkout through a tool that did not would arrive non-executable, and
    # every red would then be about that instead of about the breakage.
    (target / "bin" / "gate").chmod(0o755)
    return target


def gate_check_runs(work: Path, *, prove: bool = False, **files: str):
    """Run the checker over a copy of the fixture, with `files` written over it."""
    repo = gate_fixture_repo(work)
    for name, body in files.items():
        path = repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
    return gate_module().check(repo, prove_it=prove, log_dir=work / "log")


def gate_declaration_text(**replacements: str) -> str:
    """The conforming fixture's declaration, with `old` -> `new` substitutions.

    Raises if a substitution does not apply. A red proof that silently stops
    breaking anything is worse than no red proof, and the failure has to be
    loud: it is a test that has stopped testing.
    """
    body = (GATE_FIXTURE / "gate.yml").read_text(encoding="utf-8")
    for old, new in replacements.items():
        if old not in body:
            raise AssertionError(f"the gate fixture no longer contains {old!r}")
        body = body.replace(old, new, 1)
    return body


# -- 1. the format --------------------------------------------------------


def test_the_valid_gate_examples_validate() -> None:
    """Two examples, because `selfContained` is an `if`/`then` and both arms need one.

    A single self-contained example would leave the `minItems: 1` arm of the
    schema's conditional untested, and an untested arm of a conditional is a
    conditional nobody knows what it does. The second example is also the only
    place the format's two-proofs shape is exercised, and that shape is how a
    database tier stays separately countable instead of being folded into one
    number with everything else.
    """
    schema = load_schema(GATE_SCHEMA_PATH)
    for path in VALID_GATES:
        found = failures_for(load_document(path), schema)
        assert not found, f"{path.name} must be valid:\n  " + "\n  ".join(str(f) for f in found)


def test_the_invalid_gate_examples_are_rejected_for_the_reason_they_document() -> None:
    """Exact `(keyword, path)` pairs, so an example cannot be rejected by accident.

    A negative example that is rejected for the *wrong* reason is a lie in a
    comment: the file says "this is a shell string" and the suite is satisfied
    by it being too long. This is the assertion shape every other negative case
    in this repository uses, for the same reason.
    """
    schema = load_schema(GATE_SCHEMA_PATH)
    for name, expected in sorted(INVALID_GATES.items()):
        path = INVALID_EXAMPLES / name
        assert path.is_file(), f"examples/invalid/{name} is missing"
        found = failures_for(load_document(path), schema)
        assert found, f"examples/invalid/{name} must be REJECTED by {GATE_SCHEMA_PATH.name}"
        assert_keywords(found, expected)


def test_the_gate_checker_and_the_schema_agree_on_every_example() -> None:
    """`harness/gate_check.py` re-implements the schema, and that is a risk.

    The checker is stdlib-only so a Go service's CI can run it with nothing
    installed, and `jsonschema` is not stdlib — so the checker carries its own
    copy of the well-formedness rules. A second copy of a contract is exactly
    the drift core exists to prevent, and the honest way to hold it is to run
    BOTH over every example core ships and require the same accept/reject
    answer. Then a constraint added to the schema and forgotten in the checker
    is a red here, the day the example that exercises it lands.
    """
    module = gate_module()
    schema = load_schema(GATE_SCHEMA_PATH)
    corpus: dict[str, Path] = {path.name: path for path in VALID_GATES}
    corpus.update({name: INVALID_EXAMPLES / name for name in INVALID_GATES})
    corpus[GATE_DECLARATION.name] = GATE_DECLARATION
    for name, path in sorted(corpus.items()):
        document = load_document(path)
        by_schema = bool(failures_for(document, schema))
        by_checker = bool(module.validate(document))
        assert by_schema == by_checker, (
            f"{name}: schemas/gate.schema.json says {'reject' if by_schema else 'accept'} and "
            f"harness/gate_check.py says {'reject' if by_checker else 'accept'}.\n"
            f"  schema: {[str(f) for f in failures_for(document, schema)]}\n"
            f"  checker: {module.validate(document)}"
        )
    # And the top-level key sets are the same, so a field added to the schema
    # and never taught to the checker is caught even before an example uses it.
    required = set(schema["required"]) | set(schema["properties"])
    assert required <= set(module.TOP_LEVEL_KEYS) | set(schema["properties"]), (
        "the checker's idea of a declaration's keys and the schema's disagree"
    )
    assert set(module.TOP_LEVEL_KEYS) == set(schema["properties"]), (
        f"the checker knows {sorted(module.TOP_LEVEL_KEYS)} and the schema has "
        f"{sorted(schema['properties'])}; add the new key to gate_check.TOP_LEVEL_KEYS"
    )


def test_the_gate_schema_refuses_a_shell_string_in_any_command() -> None:
    """The constraint that would have caught the one false green this fleet has.

    Not a keyword-pair assertion on a file — a property over the whole refused
    set, because the set is the rule and an example is one sample of it. The
    characters that are ALLOWED are asserted too: a schema that refused `=`,
    `,`, `:` or a space would be refused by every real gate, and a constraint
    that everything trips is a constraint everybody works around.
    """
    schema = load_schema(GATE_SCHEMA_PATH)
    refused = re.compile(schema["$defs"]["argv"]["items"]["not"]["pattern"])
    for character in "|;&<>()$`\\'\"*?{}[]#~\n\r":
        assert refused.search(character), (
            f"a gate argument containing {character!r} must be refused: a shell would act on it"
        )
    for argument in (
        "bin/prime", "./bin/prime", "mise", "-d", "--frozen-lockfile", "3.14",
        "postgres://u:p@localhost:5432/db", "KEY=VALUE", "a path with spaces",
    ):
        assert not refused.search(argument), (
            f"{argument!r} is an ordinary gate argument and must be accepted"
        )


# -- 2. core's own declaration -------------------------------------------


def test_core_declares_its_own_gate() -> None:
    """The control, and the first thing a reader of this repository should be able to do."""
    found = failures_for(load_document(GATE_DECLARATION), load_schema(GATE_SCHEMA_PATH))
    assert not found, (
        f"{GATE_DECLARATION.name} must satisfy {GATE_SCHEMA_PATH.name}:\n  "
        + "\n  ".join(str(f) for f in found)
    )


def test_the_gate_checker_is_green_on_core() -> None:
    """`bin/prime` runs this, so a red here is a red gate.

    The static phase only. The proving phase runs `bin/prime`, and `bin/prime`
    runs this, so the proving phase is not reachable from here and must not be
    attempted: it would recurse. core's CI runs the proving half as a step of
    its own, and `test_core_ci_runs_the_gate_checkers_proving_phase` says so.
    """
    report = gate_module().check(REPO)
    assert report.exit_code == GATE_EXIT_OK, (
        f"core's own gate declaration must check clean, got exit {report.exit_code}:\n"
        + "\n".join(f.render() for f in report.findings)
    )


def test_the_gate_floor_is_not_below_the_suite_core_claims_to_have() -> None:
    """The ratchet, and the reason `minimum` is a number rather than a boolean.

    `minimum: 140` is a decrease-detector: a suite that lost forty tests cannot
    report itself as passing. But a floor nobody raises decays into a lie in the
    other direction, so the assertion also runs the other way — the floor may
    not be BELOW the number of tests the suite actually contains. Every test
    added to this file therefore fails here until the floor in `gate.yml` is
    raised in the same commit, which is the property that makes it a floor rather
    than a snapshot.
    """
    declaration = load_document(GATE_DECLARATION)
    floors = {
        item["id"]: item["minimum"]
        for item in declaration["gate"]["proof"]
        if isinstance(item, dict) and "minimum" in item
    }
    assert floors, "gate.yml declares no floor, so a shrinking suite would report itself as passing"
    declared = max(floors.values())
    tests = [
        name for name, obj in globals().items()
        if name.startswith("test_") and callable(obj) and getattr(obj, "__module__", None) == __name__
    ]
    assert declared >= len(tests), (
        f"gate.yml promises a floor of {declared} and this suite has {len(tests)} tests. "
        "Raise the floor in gate.yml in the same commit as the tests you added — a floor "
        "behind the suite is a floor that will be behind it forever."
    )


def test_core_s_mise_task_is_the_fleet_s_spelling_and_test_is_an_alias() -> None:
    """The one change this packet made outside the checker, asserted not promised.

    Nine of the fleet's fifteen repositories answer to `mise run prime`, so "run
    prime" is the spelling a manager reaches for, and core's was `test`. A task
    that exists under both names — with `depends`, so there is still one command
    — is the cheapest path, and this test is what stops the alias from quietly
    becoming a second `run` string that can drift.
    """
    import tomllib

    with (REPO / "mise.toml").open("rb") as handle:
        tasks = tomllib.load(handle)["tasks"]
    assert "prime" in tasks, "core must answer to `mise run prime`"
    assert "test" in tasks, "core must keep `mise run test` working; something already depends on it"
    assert tasks["test"].get("depends") == ["prime"] and "run" not in tasks["test"], (
        "mise run test must be an ALIAS — a `depends` on prime and no `run` of its own. "
        "A second `run` string would be a second gate, and two gates can disagree."
    )
    assert tasks["prime"]["run"] == load_document(GATE_DECLARATION)["gate"]["entrypoint"], (
        "the mise task and the declaration must name the same file; that agreement is what "
        "`gate.task-unresolvable` exists to check, and this is core checking itself"
    )


# -- 3. the checker can fail ---------------------------------------------


def test_the_gate_checker_rejects_a_command_that_does_not_exist() -> None:
    """Red proof one: the packet's first case, and a string match.

    Not the interesting one. It is here because it is the case that would still
    be caught by a checker that only compared strings, and a red proof has to
    say which of its reds are load-bearing for which claim.
    """
    with tempfile.TemporaryDirectory() as name:
        report = gate_check_runs(
            Path(name),
            **{"gate.yml": gate_declaration_text(**{
                "command: [bin/gate]": "command: [bin/absent]",
                "entrypoint: bin/gate": "entrypoint: bin/absent",
            })},
        )
    assert report.exit_code == GATE_EXIT_FAIL, report.render()
    found = [f.id for f in report.findings]
    assert "gate.command-missing" in found, report.render()
    assert "gate.entrypoint-missing" in found, report.render()


def gate_workflow_text(gate_step: str) -> str:
    """A one-job workflow whose gate step is spelled exactly as `gate_step`.

    Everything above the step is the same in every call, so what varies between
    one case and the next is the SPELLING and nothing else. A shape test that
    changed two things at once would prove neither, and the bug this pins was
    invisible precisely because the fixture changed only one thing — to the one
    spelling the checker happened to understand.
    """
    return (
        "name: ci\n\non: [push]\n\njobs:\n  gate:\n    runs-on: ubuntu-latest\n"
        "    steps:\n      - uses: actions/checkout@v7\n      - name: the gate\n" + gate_step + "\n"
    )


def test_the_gate_checker_sees_the_gate_in_every_run_spelling_this_fleet_writes() -> None:
    r"""The regression, at the level `bin/prime` can see.

    `gate.ci-disagrees` used to read `run:` through a pattern anchored `\s*$`, so
    `run: |` matched and `run: ./bin/prime` did not — and every other spelling
    along with it. Two repositories in this fleet write the gate that way
    (guard/ci.yml:65, parlor/ci.yml:81) and both were reported as not running
    the gate. A check that cries wolf on correct code is the same defect as one
    that stays quiet on broken code: both teach the reader to ignore it, and
    this one taught it on the first repository that adopted the standard.

    So this asserts the ACCEPTANCE side, from the spellings that occur in real
    workflows rather than from shapes invented here. 139 `run:` keys across the
    twelve workflow trees this standard was written for: 101 block scalars and 38
    one-liners. The 38 were the invisible ones.
    """
    spellings = {
        "the block scalar, 101 of 139 keys in this fleet": "        run: |\n          bin/gate",
        "a one-line run, which is guard/ci.yml:65": "        run: bin/gate",
        "a one-line run with a leading ./, which is parlor/ci.yml:81": "        run: ./bin/gate",
        "a one-line run with arguments and a quoted variable, which is kit:349": (
            '        run: bin/gate --fail-under "$COVERAGE_FAIL_UNDER"'
        ),
        "a one-line run with a trailing comment, which is core:186": (
            '        run: bin/gate 2>&1 | tee "$RUNNER_TEMP/gate.log"  # the gate'
        ),
        "the sequence-item spelling, which this fleet has not written yet": "        - run: bin/gate",
        "a bare run: whose value is on the lines below": "        run:\n          bin/gate",
    }
    for label, step in spellings.items():
        with tempfile.TemporaryDirectory() as name:
            report = gate_check_runs(
                Path(name), **{".github/workflows/ci.yml": gate_workflow_text(step)}
            )
        assert report.exit_code == GATE_EXIT_OK, (
            f"{label}: a workflow that plainly runs the gate was rejected.\n{report.render()}"
        )
        assert not [f for f in report.findings if f.id.startswith("gate.ci-")], (
            f"{label}: accepted, but with a finding.\n{report.render()}"
        )


def test_the_gate_checker_does_not_read_a_comment_as_a_command() -> None:
    """The other half of that fix, and the one a looser pattern breaks quietly.

    Admitting `run: ./bin/prime` also admits `run: # TODO: wire up bin/prime`.
    PyYAML reads that value as None — there is no command on the line at all —
    so treating the comment as one is a green badge on a workflow that runs
    nothing, which is the false green reached from the false red.

    Asserted against the extractor rather than the verdict, because "the
    repository is still red" and "the comment did not become a command" are
    different claims and only the second is the one that can rot unnoticed. The
    pair is what makes this a test rather than a promise: the comment is not a
    command, and a real command that merely has a comment after it is one.
    """
    module = gate_module()
    with tempfile.TemporaryDirectory() as name:
        work = Path(name)

        def run_lines(step: str) -> str:
            repo = gate_fixture_repo(work / "case")
            workflow = repo / ".github/workflows/ci.yml"
            workflow.write_text(gate_workflow_text(step), encoding="utf-8")
            return "\n".join(module.workflow_run_lines(repo, ".github/workflows/ci.yml"))

        for comment in ("        run: # TODO: wire up bin/gate",
                        "        run: #bin/gate belongs here"):
            assert "bin/gate" not in run_lines(comment), (
                f"{comment!r} carries no command, and the comment must not become one"
            )
        for real in ("        run: bin/gate",
                     '        run: bin/gate --verbose  # add --verbose once the suite is quieter'):
            assert "bin/gate" in run_lines(real), f"{real!r} does call the gate and must be read as one"


def test_gate_ci_multi_invocation_and_indirect_invocation_have_a_stated_policy() -> None:
    """How many times, and through what — the three answers, asserted.

    docs/gate.md states the policy and this pins it, because a policy that lives
    only in prose decays the first time nobody remembers writing it. The shapes:

    MULTIPLE invocations PASS. `invokes` claims the gate is REACHABLE from CI,
    not how often it is reached, and core's own workflow runs `bin/prime` and
    `bin/prime --pytest`. A checker that read multiplicity as drift would fire on
    the repository that wrote the rule.

    INDIRECT through the task the declaration names PASSES, because
    check_task has already proven that task resolves to the declared entrypoint —
    nothing is taken on trust.

    INDIRECT through a wrapper nobody declared WARNS. This checker reads no
    Makefile, so a `make gate` target and an emptied one are the same text to it;
    failing there is the false red this packet exists to kill and staying silent
    is the false green. The leak is named rather than hidden — an unrelated task
    call warns too — and it is a warning, so the exit code stays 0.
    """
    # Twice in one workflow: a pass, and the case core/ci.yml is.
    twice = (
        "name: ci\n\non: [push]\n\njobs:\n  gate:\n    runs-on: ubuntu-latest\n"
        "    steps:\n      - name: the gate\n        run: |\n          bin/gate\n"
        "      - name: the pytest entry point\n        run: |\n          bin/gate --pytest\n"
    )
    with tempfile.TemporaryDirectory() as name:
        report = gate_check_runs(Path(name), **{".github/workflows/ci.yml": twice})
    assert report.exit_code == GATE_EXIT_OK, (
        f"running the gate twice is a pass; multiplicity is not drift.\n{report.render()}"
    )

    # Through the task gate.yml names: a pass, and it is a provable one.
    via_task = gate_workflow_text("        run: mise run prime")
    with tempfile.TemporaryDirectory() as name:
        report = gate_check_runs(Path(name), **{".github/workflows/ci.yml": via_task})
    assert report.exit_code == GATE_EXIT_OK, report.render()

    # Through a make target: a warning, and the exit code is the half that matters.
    via_make = gate_workflow_text("        run: make gate")
    with tempfile.TemporaryDirectory() as name:
        report = gate_check_runs(Path(name), **{".github/workflows/ci.yml": via_make})
    assert report.exit_code == GATE_EXIT_OK, (
        f"a warning must not move the exit code.\n{report.render()}"
    )
    unproven = next((f for f in report.findings if f.id == "gate.ci-unproven"), None)
    assert unproven is not None, report.render()
    # ...and it must say what it could not do, or it is a shrug.
    assert "Makefile" in unproven.message, unproven.render()

    # And the failure is still a failure: a workflow that gates through nothing.
    with tempfile.TemporaryDirectory() as name:
        report = gate_check_runs(
            Path(name), **{".github/workflows/ci.yml": gate_workflow_text("        run: npm ci")}
        )
    assert report.exit_code == GATE_EXIT_FAIL, report.render()
    assert "gate.ci-disagrees" in [f.id for f in report.findings], report.render()


def test_the_gate_checker_rejects_a_mise_task_that_is_not_in_the_config() -> None:
    """Red proof two: also a string match, and here for the same reason."""
    with tempfile.TemporaryDirectory() as name:
        report = gate_check_runs(
            Path(name), **{"gate.yml": gate_declaration_text(**{"miseTask: prime": "miseTask: verify"})}
        )
    assert report.exit_code == GATE_EXIT_FAIL, report.render()
    assert "gate.task-missing" in [f.id for f in report.findings], report.render()
    # And the finding says which task it wanted, so the reader does not have to
    # diff a mise config by hand to find out what the declaration claimed.
    task_missing = next(f for f in report.findings if f.id == "gate.task-missing")
    assert "verify" in task_missing.message, task_missing.render()


def test_the_gate_checker_rejects_a_gate_that_exits_zero_without_running_anything() -> None:
    """Red proof three, and the one the other two are not.

    Every string in this repository's declaration is TRUE: the command exists,
    it is executable, `mise run prime` resolves to it, the CI workflow calls it.
    The gate runs, exits 0, and does nothing at all. A checker that only read
    files would call that a clean bill of health, and it is the shape this fleet
    has already shipped once — a gate that reports success and has not run the
    hard part.

    So this test runs the gate. That is the whole difference between a checker
    of declarations and a declaration.
    """
    with tempfile.TemporaryDirectory() as name:
        report = gate_check_runs(
            Path(name),
            prove=True,
            **{"bin/gate": "#!/usr/bin/env bash\n# exits 0, runs nothing, says nothing\nexit 0\n"},
        )
    assert report.exit_code == GATE_EXIT_FAIL, report.render()
    assert "gate.proof-missing" in [f.id for f in report.findings], report.render()
    missing = next(f for f in report.findings if f.id == "gate.proof-missing")
    assert "suite" in missing.message, (
        f"the finding must name WHICH proof was absent, not only that one was: {missing.render()}"
    )
    # And nothing else is blamed. A false green caught by an unrelated
    # complaint is a red for the wrong reason, which is the same mistake as a
    # green for the wrong reason.
    assert [f.id for f in report.findings] == ["gate.proof-missing"], (
        f"only the absent proof should be reported, got {[f.id for f in report.findings]}"
    )


def test_the_gate_checker_rejects_a_gate_that_ran_a_smaller_suite_than_it_promised() -> None:
    """The floor, which is the other half of the proof.

    A proof with no `minimum` cannot tell "3/3 passed" from "1/1 passed", so a
    suite that quietly lost two thirds of itself is still a green. This is the
    same shape as MD12's floors, and it is a decrease-detector because a floor
    above the real number is the only direction worth failing in.
    """
    with tempfile.TemporaryDirectory() as name:
        report = gate_check_runs(
            Path(name),
            prove=True,
            **{
                "gate.yml": gate_declaration_text(**{"minimum: 3": "minimum: 400"}),
                "bin/gate": "#!/usr/bin/env bash\nset -euo pipefail\necho '1/1 passed'\n",
            },
        )
    assert report.exit_code == GATE_EXIT_FAIL, report.render()
    assert "gate.floor" in [f.id for f in report.findings], report.render()
    floor = next(f for f in report.findings if f.id == "gate.floor")
    assert "1" in floor.message and "400" in floor.message, floor.render()


def test_the_gate_checker_never_says_green_when_it_could_not_look() -> None:
    """Exit 2, and the wrapper, which is what a CI job actually calls.

    A checker pointed at nothing has not checked anything. Reporting 0 there is
    how a missing checkout becomes a green badge, and it is the same defect as a
    skipped test: the answer is unknown and the badge says yes.
    """
    module = gate_module()
    with tempfile.TemporaryDirectory() as name:
        absent = module.check(Path(name) / "no-such-directory")
    assert absent.exit_code == GATE_EXIT_COULD_NOT_RUN, absent.render()
    assert absent.could_not_run, "a refusal must say why it refused"
    completed = subprocess.run(
        [str(GATE_WRAPPER), str(REPO / "does-not-exist")],
        capture_output=True, text=True, check=False, cwd=str(REPO),
    )
    assert completed.returncode == GATE_EXIT_COULD_NOT_RUN, (
        f"gate-check on a missing directory must exit 2, got {completed.returncode}:\n"
        f"{completed.stdout}{completed.stderr}"
    )
    assert (module.EXIT_OK, module.EXIT_FAIL, module.EXIT_COULD_NOT_RUN) == (
        GATE_EXIT_OK, GATE_EXIT_FAIL, GATE_EXIT_COULD_NOT_RUN
    )


# -- 4. the checker's own promises ---------------------------------------


def test_a_warning_never_moves_the_gate_checkers_exit_code() -> None:
    """The tri-state contract of MD13, as a test rather than a comment.

    A gate built on booleans forces a choice between "fail on warnings" (noisy,
    gets disabled) and "ignore them" (the report is a lie). Four warnings are
    provoked at once below, the exit code is asserted to be 0, and the ids are
    asserted — so a warning that quietly became a failure, or one that stopped
    being reported at all, is a red rather than a surprise on somebody's laptop.
    """
    with tempfile.TemporaryDirectory() as name:
        report = gate_check_runs(
            Path(name),
            **{
                "gate.yml": gate_declaration_text(**{
                    "  miseTask: prime\n": "",
                    "command: [bin/gate]": "command: [definitely-not-installed-anywhere]",
                    "  selfContained: true\n  requirements: []":
                        "  selfContained: false\n  requirements:\n"
                        "    - kind: toolchain\n      name: a command on PATH nobody ran\n"
                        "      satisfy:\n        command: [definitely-not-installed-anywhere]",
                    "ci:\n  workflow: .github/workflows/ci.yml\n  invokes: [bin/gate]\n": "",
                }),
                "mise.toml": (GATE_FIXTURE / "mise.toml").read_text(encoding="utf-8").replace(
                    'run = "bin/gate"', 'run = "bin/gate | tee /dev/null"'
                ),
            },
        )
    warnings = [f.id for f in report.of("warn")]
    assert report.exit_code == GATE_EXIT_OK, (
        "a warning must not move the exit code, or the checker is red on a laptop and green "
        f"on CI:\n{report.render()}"
    )
    assert not report.of("fail"), report.render()
    assert set(warnings) == {
        "gate.command-unknown", "gate.task-undeclared", "gate.ci-undeclared",
        "gate.requirement-unproven",
    }, f"expected four warnings and got {warnings}"
    assert "warnings do not move the exit code" in report.render()
    # Every severity in the inventory is one of the two that reach a caller, and
    # each id has exactly one. An id that is sometimes fatal and sometimes
    # advisory is two findings wearing one name, and a caller cannot branch on it.
    module = gate_module()
    for identifier, (severity, _claim, _remediate) in sorted(module.FINDINGS.items()):
        assert severity in ("warn", "fail"), f"{identifier} has severity {severity!r}"


def test_the_gate_checker_never_prints_a_value_read_from_the_environment() -> None:
    """MD10, applied to this file's own output.

    No off-the-shelf tool detects a secret *leaked at runtime* into a log or an
    error string — 0 of 268 Semgrep rules intersect CWE-532, gosec has no
    `ast.CallExpr` case, Bandit is `ast.Constant`-only. So the checker's own
    report must never carry a value that came out of the gate's environment, or
    it is a new place a credential lands. A gate that prints a connection string
    the way a failing assertion does is the realistic shape, and the checker's
    report is what a person reads and what a CI log keeps.
    """
    secret = "postgres://gate:should-never-be-printed@localhost:5432/gate"
    leaky = (
        "#!/usr/bin/env bash\n"
        "set -uo pipefail\n"
        'echo "could not reach ${DATABASE_URL:-unset}"\n'
        "echo '2/3 passed'\n"
        "exit 1\n"
    )
    with tempfile.TemporaryDirectory() as name:
        work = Path(name)
        repo = gate_fixture_repo(work)
        gate = repo / "bin" / "gate"
        gate.write_text(leaky, encoding="utf-8")
        gate.chmod(0o755)
        report = gate_module().check(repo, prove_it=True, log_dir=work / "log")
        # Read inside the `with`: the log lives in the temporary directory, and
        # reading it after the context has cleaned up would assert nothing.
        log = (work / "log" / "gate.log")
        assert report.exit_code == GATE_EXIT_FAIL, "the leaky gate should be red for failing, and nothing else"
        assert secret not in report.render(), (
            "the checker copied a value out of the gate's environment into its own report. "
            "Print the command string, never its expansion, and leave the gate's output in the "
            "log file where the operator put it."
        )
        assert log.is_file() and "2/3 passed" in log.read_text(encoding="utf-8"), (
            "the gate's own output must still be written somewhere: not printing it is the "
            "property, destroying it would be a different tool's job"
        )


def test_every_gate_finding_the_checker_can_emit_is_declared() -> None:
    """The inventory, in both directions, like `harness/rules.json`.

    A finding the inventory does not describe is a finding nobody was told
    about. An inventory entry the checker cannot reach is a promise nobody keeps,
    and it is the worse of the two: it is a rule that reads as upheld and is not,
    which is the exact shape of the false green this section is about.
    """
    module = gate_module()
    declared = {
        entry["id"]: entry
        for entry in json.loads(GATE_FINDINGS.read_text(encoding="utf-8"))["findings"]
    }
    emitted = set(module.FINDINGS)
    assert emitted == set(declared), (
        f"the checker can emit {sorted(emitted - set(declared)) or 'nothing extra'} and "
        f"harness/gate_findings.json declares "
        f"{sorted(set(declared) - emitted) or 'nothing extra'}"
    )
    for identifier, entry in sorted(declared.items()):
        severity, claim, remediate = module.FINDINGS[identifier]
        assert entry["severity"] == severity, f"{identifier}: inventory and code disagree on severity"
        assert entry["claim"] == claim, f"{identifier}: inventory and code disagree on the claim"
        assert entry["remediate"] == remediate, f"{identifier}: inventory and code disagree on the fix"


def test_every_gate_finding_carries_the_exact_command_that_fixes_it() -> None:
    """MD13's most transferable finding about yamine, made an assertion.

    "Every check message carries the exact remediation command" is the single
    most valuable thing in a 7,000-line file the fleet decided not to copy. A
    check that says only "not ok" makes the reader go and look, and the reader
    who does not look is why it is still broken next week.
    """
    module = gate_module()
    for identifier, (_severity, claim, remediate) in sorted(module.FINDINGS.items()):
        assert claim and claim.endswith("."), f"{identifier}: the claim must be a sentence"
        assert remediate and len(remediate) > 20, f"{identifier}: no remediation, or a useless one"
        assert "\n" not in remediate, f"{identifier}: a multi-line fix is not a fix"
    inventory = json.loads(GATE_FINDINGS.read_text(encoding="utf-8"))
    assert inventory["notEnforced"], (
        "harness/gate_findings.json must record what the gate checker does NOT prove. A "
        "checker with no notEnforced list reads as covering everything, and a gate check "
        "that claims to prove the database tier was hit means only the first thing."
    )
    for entry in inventory["notEnforced"]:
        assert entry["why"] and entry["doc"], f"a notEnforced entry with no reason: {entry}"


def test_every_gate_finding_is_proved_able_to_go_red() -> None:
    """`harness/tests/gate_self_test.sh` must be able to fail, and CI must run it.

    The check is textual and it is the check core already applies to
    `harness/tests/self_test.sh`: a finding with no breakage is a finding nobody
    has tested, and a finding nobody has tested is a finding that will be wrong
    the first time somebody needs it. Reading the script rather than running it
    is deliberate — running twenty-two breakages inside every `bin/prime` would
    be a second gate that can disagree with the first, which is why core's CI
    runs the script as a step of its own and this test makes sure that step
    exists.
    """
    script = GATE_SELF_TEST.read_text(encoding="utf-8")
    module = gate_module()
    for identifier in sorted(module.FINDINGS):
        assert identifier in script, (
            f"{identifier} has no breakage in harness/tests/gate_self_test.sh. Add one that "
            f"expects this exact id, or delete the finding — a finding nothing exercises is "
            f"a finding that will be wrong the first time it is needed."
        )
    for construction in ("expect_red", "expect_warn", "expect_no_leak", "fresh_copy", "exit 1"):
        assert construction in script, f"the red proof lost its {construction}"
    assert "set -uo pipefail" in script, (
        "harness/tests/gate_self_test.sh must set pipefail. A red proof that loses a failure "
        "to a pipe reports a green, which is the defect the whole packet is about."
    )
    ci = (REPO / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "harness/tests/gate_self_test.sh" in ci, (
        "core's CI must run the gate checker's red proof as a step of its own. PLAN.md §1 is "
        "explicit that a second tier is only real if CI invokes it, and a comment claiming CI "
        "runs the self-test is not CI running it."
    )


def test_the_gate_checker_needs_nothing_core_does_not_ship() -> None:
    """Stdlib only, and the sibling reader is the ONE YAML dialect.

    The contract harness is held to this and so is this: a service's CI should
    be able to run `gate-check` with nothing installed, which is the same reason
    `harness/cafaye_contract.py` may not import `jsonschema`. The static half is
    an AST walk, so a `from x import y` inside a function body is caught as
    readily as one at the top; the runtime half is `-I -S`, the interpreter with
    user site-packages, `PYTHONPATH` and the site module all out of the way.
    """
    tree = ast.parse(GATE_CHECK.read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            imported.add(node.module.split(".")[0])
    imported.discard("__future__")
    siblings = {"cafaye_contract"}
    outside = sorted(imported - HARNESS_STDLIB_ONLY - siblings - gate_module().EXTRA_STDLIB)
    assert not outside, (
        f"harness/gate_check.py imports {outside}. core has one dependency list and the gate "
        "checker must not add a second: a check that needs a package is a check a Go service's "
        "CI cannot run."
    )
    # The extra list is a hand-maintained list, and hand-maintained lists drift.
    # `sys.stdlib_module_names` is the interpreter's own answer to "what is the
    # standard library", so the three names this file adds are checked against
    # the definition rather than against my memory of it.
    not_stdlib = sorted(
        (HARNESS_STDLIB_ONLY | gate_module().EXTRA_STDLIB)
        - set(sys.stdlib_module_names)
        - siblings
    )
    assert not not_stdlib, (
        f"{not_stdlib} are in the gate checker's allowlist and are not in "
        f"sys.stdlib_module_names on {sys.version_info[:2]}. Either the allowlist names a "
        "package, or this interpreter's standard library is smaller than the pin assumes."
    )
    assert "cafaye_contract" in imported, (
        "harness/gate_check.py must read YAML with the harness's own reader. A second YAML "
        "dialect in core is the four-way drift core exists to end, and it is worse here than "
        "anywhere else, because a declaration one reader accepts and another refuses is a "
        "declaration whose validity depends on who asked."
    )
    # The fixture, NOT core. `--prove` runs the declared gate, and core's gate
    # is `bin/prime`, which is the suite this assertion is inside — pointing it
    # at core recurses, and a test that hangs the gate is worse than no test.
    # The fixture's gate is three lines and its proof is real, so the runtime
    # claim is the same one and it costs nothing.
    completed = subprocess.run(
        [sys.executable, "-I", "-S", str(GATE_CHECK), "--prove", str(GATE_FIXTURE)],
        cwd=str(REPO), env={}, capture_output=True, text=True, check=False,
    )
    assert completed.returncode == GATE_EXIT_OK, (
        f"the gate checker must run on the standard library alone, exited "
        f"{completed.returncode}\n{completed.stdout}\n{completed.stderr}"
    )
    # And core itself, statically, with an empty environment: the checker's
    # answer must not depend on who is asking, which is the claim
    # `cafaye_contract.py` is held to and this file is held to as far as it
    # goes without running a gate.
    on_core = subprocess.run(
        [sys.executable, "-I", "-S", str(GATE_CHECK), str(REPO)],
        cwd=str(REPO), env={}, capture_output=True, text=True, check=False,
    )
    assert on_core.returncode == GATE_EXIT_OK, (
        f"core's own gate declaration must check clean on the standard library alone, exited "
        f"{on_core.returncode}\n{on_core.stdout}\n{on_core.stderr}"
    )


def test_the_gate_checker_reaches_no_network_and_reads_no_environment() -> None:
    """The two ways this file could stop being a checker and become a process.

    `cafaye_contract.py` is held to "answer the same with a full environment and
    with an empty one". The gate checker cannot be: it runs the gate, and the
    gate needs `PATH`, `HOME` and a dozen other things. So the claim is narrowed
    to the part that is actually true of it, and the part that would be a bug is
    asserted instead — the AST names every way this module could reach outside
    itself, there is no networking one, and the single process call is the one
    the whole tool exists for.
    """
    source = GATE_CHECK.read_text(encoding="utf-8")
    tree = ast.parse(source)
    called: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        parts: list[str] = []
        target = node.func
        while isinstance(target, ast.Attribute):
            parts.append(target.attr)
            target = target.value
        if isinstance(target, ast.Name):
            parts.append(target.id)
        called.add(".".join(reversed(parts)))
    for banned in (
        "os.system", "os.popen", "os.spawn", "os.fork", "eval", "exec", "compile",
        "__import__", "urllib.request.urlopen", "socket.socket", "http.client",
    ):
        assert banned not in called, (
            f"harness/gate_check.py calls {banned}(). The gate checker reads a tree and runs "
            "one command; it fetches nothing, and a checker whose answer depends on the "
            "network is a checker whose answer depends on the day."
        )
    assert "subprocess.run" in called, (
        "the gate checker is supposed to RUN the declared gate — that is the whole difference "
        "between it and a file that compares strings. If this fails it has stopped doing its "
        "job, and the false green is back."
    )
    assert "os.environ" not in source and "getenv" not in source, (
        "harness/gate_check.py reads no environment variable of its own. Its answer depends "
        "on the repository, not on who is asking. (The gate's own environment is another "
        "matter and is passed through untouched — a gate that needs PATH needs PATH.)"
    )


def test_core_ci_runs_the_gate_checkers_proving_phase() -> None:
    """The recursion has to be broken somewhere, and this says where.

    `bin/prime` runs the STATIC half, because the proving half would run
    `bin/prime`. So the proving half — the half that can catch a false green —
    has to run somewhere else, and "somewhere else" is a CI step that somebody
    can delete. This is the test that notices.
    """
    ci = (REPO / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "gate_check.py" in ci or "gate-check" in ci, (
        "core's CI must run the gate checker; bin/prime runs only its static half"
    )
    assert "--prove" in ci, (
        "core's CI must run the gate checker's PROVING phase. The static half cannot tell a "
        "gate that ran from a gate that exited 0, and that is the defect this packet exists "
        "to close — a check nothing invokes is documentation of a wish."
    )
    # The COMMANDS, not the whole file: `bin/prime` explains in a comment why it
    # does not pass --prove, and an assertion over the whole file would be
    # satisfied by deleting the explanation and fail on the explanation.
    prime = (REPO / "bin" / "prime").read_text(encoding="utf-8")
    commands = [
        line for line in prime.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    assert any("gate_check.py" in line for line in commands), "bin/prime must run the gate check"
    assert not any("--prove" in line for line in commands), (
        "bin/prime runs the static half of the gate check and must not run the proving half: "
        "a gate that proves itself by running itself proves nothing and terminates"
    )
    assert "set -euo pipefail" in prime, "bin/prime keeps pipefail at the top, as every script here does"


def test_the_gate_doc_states_the_rule_the_false_green_was_built_from() -> None:
    """`PIPESTATUS`, `pipefail`, and bash — asserted, because they get deleted.

    The one recorded false green in this fleet is `… | tail -45; echo "PRIME
    EXIT=$?"` under zsh, which has no `PIPESTATUS` and therefore reported
    `tail`'s exit code. The fix is one line in a document, which is the easiest
    line in a repository to lose to an edit six months from now. So the line is
    a test.
    """
    doc = GATE_DOC.read_text(encoding="utf-8")
    assert "${PIPESTATUS[0]}" in doc, (
        "docs/gate.md must show the PIPESTATUS spelling for reading a gate's exit code through "
        "a pipe. Without it a reader reinvents the false green."
    )
    assert "set -o pipefail" in doc, "docs/gate.md must show pipefail"
    assert "zsh" in doc, "docs/gate.md must say WHY: zsh has no PIPESTATUS"
    for topic in (
        "mise tasks alone", "CI", "argv", "selfContained", "proof", "minimum",
        "warn", "gate.yml", "schemas/gate.schema.json", "harness/gate_check.py",
        "not a task runner",
    ):
        assert topic in doc, f"docs/gate.md never mentions {topic!r}"
    assert "DECISION NEEDED" not in doc, (
        "a spec on master must read as decided; an open question belongs in DECISIONS.md"
    )


def test_the_gate_doc_names_both_alternatives_it_measured() -> None:
    """A ruling is only a ruling if the rejected option is written down.

    The packet asked for the choice to be justified against the alternatives
    actually tested, and a document that states only its own conclusion is
    indistinguishable from a document that picked something at random. So the
    incumbent (mise tasks alone) and the CI-only declaration are named as
    headings, which means a later reader can disagree with the ruling instead of
    having to reverse-engineer it.
    """
    doc = GATE_DOC.read_text(encoding="utf-8")
    for heading in (
        "## Why not mise tasks alone",
        "## Why not a CI-only declaration",
        "## Why not a second task runner",
    ):
        assert heading in doc, f"docs/gate.md is missing the section {heading!r}"
    for alternative in ("mise tasks", "GitHub Actions", "ci.reusable.yml", "drift"):
        assert alternative in doc, f"docs/gate.md never names {alternative!r}"


# --------------------------------------------------------------------------
# 11. the gate declaration is matched against colour-free bytes (core-13)
# --------------------------------------------------------------------------
#
# A colourising test runner writes a proof line as
#
#     \x1b[2m      Tests \x1b[22m \x1b[1m\x1b[32m377 passed\x1b[39m\x1b[22m …
#
# and a declaration written by a person reading a terminal is written against
# what the terminal SHOWS. So `^[ ]*Tests[ ]+([0-9]+) passed` — correct for the
# rendered line — cannot match, because the captured line begins with an escape
# rather than a space. That is not a declaration bug; it is a checker bug, and
# it fires on the first repository that adopts the format with `vitest`.
#
# The ruling (MD17): the checker strips ANSI before applying any `proof[].match`.
# Not `NO_COLOR=1` in the gate, and not a per-repository tolerant regex — both
# make the gate or the declaration carry the cost of a defect in the checker.
#
# The interesting half is not that stripping fixes the false red. It is whether
# stripping can WEAKEN a pattern, which is measured below rather than asserted.

#: The bytes MD17 quotes from a real `vitest` log. Copied verbatim rather than
#: reconstructed, because a paraphrase of a byte sequence is how a regression
#: test stops reproducing the thing it was written for.
VITEST_TESTS_LINE = (
    "\x1b[2m      Tests \x1b[22m \x1b[1m\x1b[32m377 passed\x1b[39m\x1b[22m \x1b[90m(377)\x1b[39m"
)

#: The pattern `core-10-parlor` declared, verbatim. It is correct.
PARLOR_TESTS_PATTERN = r"^[ ]*Tests[ ]+([0-9]+) passed"


def _is_subsequence(smaller: str, larger: str) -> bool:
    """Whether `smaller` is a subsequence of `larger` — the deletion test.

    The property that makes stripping safe to rule on is that it only ever
    DELETES: every character it removes was an escape, and it never inserts or
    reorders one. That is a weaker and more honest claim than "stripping cannot
    weaken a pattern", which is false — see
    `test_stripping_cannot_weaken_a_proof_and_the_two_ways_it_tries`.
    """
    iterator = iter(larger)
    return all(character in iterator for character in smaller)


def test_a_proof_is_matched_against_output_with_the_colour_stripped() -> None:
    """The false red itself: 377 tests ran, and the checker called it a missing proof.

    This is the packet's reason for existing. The suite really printed
    `Tests  377 passed`; the checker captured bytes that begin with an escape,
    so the declared pattern could not match, and it answered `gate.proof-missing`
    about a gate that had just proved, in the same log, that it ran 377 tests.

    Asserted against the real bytes and the real declared pattern, so this test
    cannot pass by agreeing with a weakened fixture.
    """
    module = gate_module()
    assert not module._compile(PARLOR_TESTS_PATTERN).search(VITEST_TESTS_LINE), (
        "the premise of this test has changed: the declared pattern now matches the raw "
        f"bytes {VITEST_TESTS_LINE!r}. Either the stripper leaked into the test, or the "
        "bytes are no longer the ones MD17 recorded."
    )
    with tempfile.TemporaryDirectory() as name:
        report = gate_check_runs(
            Path(name),
            prove=True,
            **{
                "gate.yml": gate_declaration_text(
                    **{
                        "match: '^([0-9]+)/[0-9]+ passed$'": (
                            f"match: '{PARLOR_TESTS_PATTERN}'"
                        ),
                        "minimum: 3": "minimum: 377",
                    }
                ),
                "bin/gate": (
                    "#!/usr/bin/env bash\n"
                    "# A colourising runner, which is the shape this whole packet is about.\n"
                    "# `%b` and not `%s`: printf only expands backslash escapes for %b,\n"
                    "# and writing %s here would emit the two characters \\ and x and this\n"
                    "# test would pass without a single escape ever reaching the checker.\n"
                    "set -euo pipefail\n"
                    "printf '%b\\n' '" + VITEST_TESTS_LINE.replace("\x1b", "\\033") + "'\n"
                ),
            },
        )
    assert report.exit_code == GATE_EXIT_OK, (
        "a gate that really ran 377 tests must not be reported as missing its proof:\n"
        + report.render()
    )


def test_the_gate_checker_strips_every_escape_sequence_it_declares_it_handles() -> None:
    """The sequence types, each on its own, and the record of which are handled.

    CSI (`ESC [ … m`) is what `vitest` emits and it is the only one a naive
    stripper knows. OSC (`ESC ] … BEL`/`ST`) is emitted by some tools, and a
    regex written only for CSI leaves it in place — so the line still starts with
    an escape and the proof still misses. A stripper that silently mangles is
    worse than none, so every class below is asserted on its own, and the class
    that is deliberately NOT handled is asserted to SURVIVE, which is the only
    way a reader can tell the difference between "handled" and "lost".
    """
    module = gate_module()
    strip = module.strip_ansi
    handled = {
        # Leading spaces SURVIVE. Stripping removes escapes, not whitespace, and a
        # pattern that counted on `^[ ]*` still counts on it.
        "SGR colour (CSI)": ("\x1b[2m      Tests \x1b[22m 377 passed", "      Tests  377 passed"),
        "256-colour index (CSI)": ("\x1b[38;5;208mTests\x1b[0m 377 passed", "Tests 377 passed"),
        "cursor erase (CSI, non-m final)": ("\x1b[2KTests 377 passed\x1b[1A", "Tests 377 passed"),
        "private mode (CSI with ?)": ("\x1b[?25lTests 377 passed\x1b[?25h", "Tests 377 passed"),
        "8-bit CSI": ("\x9b2mTests 377 passed\x9b0m", "Tests 377 passed"),
        "OSC 0 title, BEL-terminated": ("\x1b]0;vitest\x07Tests 377 passed", "Tests 377 passed"),
        # OSC 8 wraps a LINK. The wrapper goes and the link text stays, because
        # the link text is content the terminal renders and a proof may
        # legitimately live in it. Stripping must not delete what was displayed.
        "OSC 8 hyperlink, ST-terminated": (
            "\x1b]8;;https://x.dev\x1b\\Tests 377 passed\x1b]8;;\x1b\\",
            "Tests 377 passed",
        ),
        "8-bit OSC": ("\x9d0;vitest\x07Tests 377 passed", "Tests 377 passed"),
        "DCS": ("\x1bP1$r0m\x1b\\Tests 377 passed", "Tests 377 passed"),
        "charset selection": ("\x1b(BTests 377 passed", "Tests 377 passed"),
    }
    for label, (raw, expected) in handled.items():
        assert strip(raw) == expected, (
            f"{label}: the stripper produced {strip(raw)!r}, not {expected!r}. Every sequence "
            "class the docs claim to handle has to be listed in exactly one place, and this "
            "one is claimed there."
        )
    # What is NOT handled, and why leaving it is the safe answer: an unterminated
    # OSC. A stripper that consumes to end-of-input on a sequence with no
    # terminator would delete every line after it — including the proof — and a
    # checker that silently eats evidence is the defect this packet exists to end.
    # So an unterminated sequence survives, and the words on its own line survive.
    unterminated = "INFO start\n\x1b]0;title-never-terminated\nTests  377 passed\n"
    assert "Tests  377 passed" in strip(unterminated), (
        "an unterminated OSC must not swallow the rest of the log. A stripper that "
        f"runs to end-of-input deleted the proof line: {strip(unterminated)!r}"
    )
    assert strip(unterminated).startswith("INFO start\n"), (
        "lines before an unterminated sequence must be untouched"
    )
    # The load-bearing invariant behind every `^` and `$` in this fleet: stripping
    # must not change how many LINES the output has. A stripper that could span a
    # newline would join two lines, and then `^[ ]*Tests` would be able to match a
    # pattern straddling a line boundary — a pattern matching across lines is not
    # a pattern matching a summary line.
    for raw in (
        VITEST_TESTS_LINE,
        unterminated,
        "a\n\x1b]0;x\nb\n",
        "a\n\x1bPfoo\nb\n",
        "\x1b[2Kone\x1b[1Atwo\nthree\n",
    ):
        assert strip(raw).count("\n") == raw.count("\n"), (
            f"stripping changed the line count of {raw!r} -> {strip(raw)!r}; a stripper "
            "that spans a newline joins two lines and breaks ^ and $ for every pattern"
        )


def test_stripping_cannot_weaken_a_proof_and_the_two_ways_it_tries() -> None:
    """The half that is not a formality: can stripping BROADEN a pattern?

    It can, and it is worth being exact about how, because "colour carries no
    assertion" is only reassuring until you know the mechanism. Two cases, both
    measured against the real matching code rather than reasoned about:

    1. **An anchored pattern can reach a line it could not reach.** `^` binds to
       the start of the line. With the escape present, `^[ ]*Tests` cannot match
       `\x1b[2m Tests`; stripped, it can. So a declaration may match MORE lines
       than it did. This is the direction that looks like a strengthening and is
       in fact the risk — and because `minimum` reads the LAST match, a
       broadened pattern can move the number the ratchet sees.

    2. **`.` counts escape bytes.** A pattern that positions itself with a fixed
       number of `.` sees different bytes before and after stripping, so
       `^.{6}Tests` matches one line raw and a different line stripped.

    Neither is a new false green on its own — stripping removes bytes, so a
    pattern needs the REMOVED bytes to have matched before, and the tests above
    already prove the fixed case. But the claim "cannot weaken a pattern" is not
    true as stated, and docs/gate.md says so rather than leaving it implied.
    """
    module = gate_module()
    strip = module.strip_ansi
    compile_ = module._compile

    # Case 1, measured: the anchored pattern reaches a second line only once the
    # escapes are gone, and the floor — which reads the LAST match — changes.
    log = "      Tests  377 passed\n\x1b[2m      Tests \x1b[22m \x1b[1m\x1b[32m2 passed\x1b[39m\x1b[22m\n"
    found_raw = [m.group(1) for m in compile_(PARLOR_TESTS_PATTERN).finditer(log)]
    found_stripped = [m.group(1) for m in compile_(PARLOR_TESTS_PATTERN).finditer(strip(log))]
    assert found_raw == ["377"], f"the raw bytes must reach only the plain line, got {found_raw}"
    assert found_stripped == ["377", "2"], (
        f"stripping must broaden the anchored pattern to reach the coloured line, got {found_stripped}"
    )

    # Case 2, measured: `.` counts different bytes on each side of the change.
    line = "\x1b[2m      Tests \x1b[22m 377 passed"
    fixed = r"^.{6}Tests"
    assert compile_(fixed).search(line) is None and compile_(fixed).search(strip(line)), (
        "`^.{6}Tests` counts escape bytes raw and visible bytes stripped, so it names a "
        "different line on each side. Documented in docs/gate.md; asserted here so the "
        "consequence is a fact rather than a worry."
    )

    # The property that IS unconditional, and the reason the ruling is still
    # right: stripping only ever DELETES. It cannot insert a byte, so it cannot
    # fabricate a match out of nothing — every character in the stripped text was
    # in the original, in order.
    for raw in (VITEST_TESTS_LINE, log, line, "no escapes at all"):
        assert _is_subsequence(strip(raw), raw), (
            f"stripping {raw!r} produced text that is not a subsequence of it, so it "
            "INVENTED or reordered content rather than only removing escapes"
        )


def test_a_floor_can_no_longer_be_satisfied_by_digits_inside_an_escape() -> None:
    """The inverse false green, which this fix removes and which is easy to miss.

    Every account of this defect has been a false RED — a pattern that could not
    match. The mirror image is worse and quieter: a capture group that lands on
    digits belonging to an escape sequence reads them as the count.

    `\x1b[38;5;208m` is a 256-colour index. A gate that ran **3** tests and
    printed `\x1b[38;5;208m3 passed` matches `^.*?([0-9]+).* passed$` with
    group(1) == `38` — so a declaration with `minimum: 38` was GREEN over a suite
    that ran three. Stripping cannot introduce that reading; it is the only
    outcome in which the number in the log is the number the gate printed.
    """
    module = gate_module()
    pattern = r"^.*?([0-9]+).* passed$"
    compiled = module._compile(pattern)
    colour = "\x1b[38;5;208m3 passed"
    raw_group = compiled.search(colour).group(1)
    stripped_group = compiled.search(module.strip_ansi(colour)).group(1)
    assert raw_group == "38", (
        f"the premise changed: the raw capture group is {raw_group!r}, so this test is "
        "no longer demonstrating that an escape's parameters can satisfy a floor"
    )
    assert stripped_group == "3", (
        f"after stripping the capture group must be the count the gate printed, got {stripped_group!r}"
    )
    # And the same thing end to end, through the checker, with a real floor.
    with tempfile.TemporaryDirectory() as name:
        report = gate_check_runs(
            Path(name),
            prove=True,
            **{
                "gate.yml": gate_declaration_text(
                    **{
                        "match: '^([0-9]+)/[0-9]+ passed$'": f"match: '{pattern}'",
                        "minimum: 3": "minimum: 38",
                    }
                ),
                "bin/gate": (
                    "#!/usr/bin/env bash\n"
                    "set -euo pipefail\n"
                    "printf '%s\\n' '\\033[38;5;208m3 passed'\n"
                ),
            },
        )
    assert report.exit_code == GATE_EXIT_FAIL, (
        "a gate that printed 3 against a floor of 38 must go red; the 38 in the log is a "
        "colour index, not a test count:\n" + report.render()
    )
    assert "gate.floor" in [f.id for f in report.findings], report.render()


def test_a_proof_that_is_genuinely_absent_still_goes_red_after_stripping() -> None:
    """The other half of the fix: the stripper must not swallow evidence.

    A stripper that deleted anything it did not understand — or a gate whose
    proof line is *only* an escape sequence — would make this green. The check
    is that stripping changes WHERE the pattern is applied and never WHETHER a
    genuinely absent proof is reported. The fixture here prints a near miss
    ("2/4 passed", not the declared `N/N passed`) and must still be caught.
    """
    with tempfile.TemporaryDirectory() as name:
        report = gate_check_runs(
            Path(name),
            prove=True,
            **{
                "bin/gate": (
                    "#!/usr/bin/env bash\n"
                    "set -euo pipefail\n"
                    "# Colour everywhere, and the declared proof genuinely absent.\n"
                    "printf '\\033[1;32m2\\033[0m/4 \\033[33msomething else\\033[0m\\n'\n"
                    "exit 0\n"
                ),
            },
        )
    assert report.exit_code == GATE_EXIT_FAIL, (
        "colour in the output must not make an absent proof look present:\n" + report.render()
    )
    assert "gate.proof-missing" in [f.id for f in report.findings], report.render()


def test_the_stripper_runs_in_exactly_one_place_and_only_on_proof_matching() -> None:
    """One function, one call site — the shape the packet rules on.

    Four checks apply `proof[].match`, and four call sites to strip would be
    four places to drift. So the stripper is called once, where the output is
    read, before any pattern sees it. This asserts it structurally rather than by
    reading the code: one call site, inside `prove`, and the raw bytes are still
    what gets written to the log.

    That last part matters. The log is the operator's evidence — it is where a
    human goes to see what the gate actually printed — so the log keeps the
    escapes. Stripping the log too would be two call sites and would make the
    evidence disagree with the output.
    """
    source = GATE_CHECK.read_text(encoding="utf-8")
    calls = re.findall(r"\bstrip_ansi\s*\(", source)
    # One is the definition; the rest must all be inside `prove`.
    assert len(calls) == 2, (
        f"strip_ansi is referenced {len(calls)} times (one definition + one call site "
        "expected). Stripping in each check is four call sites that will drift."
    )
    prove_body = source.split("def prove(", 1)[1].split("\ndef ", 1)[0]
    assert "strip_ansi(" in prove_body, (
        "the single strip call must be in prove(), where the output is read and before "
        "any pattern is applied"
    )
    assert prove_body.index("strip_ansi(") < prove_body.index("finditer("), (
        "stripping must happen BEFORE any pattern sees the output"
    )
    with tempfile.TemporaryDirectory() as name:
        report = gate_check_runs(
            Path(name),
            prove=True,
            **{
                "bin/gate": (
                    "#!/usr/bin/env bash\n"
                    "set -euo pipefail\n"
                    "printf '%b\\n' '\\033[32m3/3 passed\\033[0m'\n"
                )
            },
        )
        # Read INSIDE the temporary directory's lifetime. The path comes from the
        # report rather than a guess — the log's location is the checker's
        # decision — and a test that hardcoded it would test nothing about the log.
        assert report.log is not None, "a proving run must report where it wrote the log"
        log = report.log.read_text(encoding="utf-8")
    assert "\x1b[32m" in log, (
        "the log must keep the gate's own bytes — it is the operator's evidence, and "
        "stripping it would make the log disagree with the output it records"
    )
    assert report.exit_code == GATE_EXIT_OK, report.render()


def test_the_gate_doc_says_the_output_is_matched_colour_free() -> None:
    """The docs are what an adopter reads before writing a pattern.

    The packet's fifth item is this assertion. A format whose documentation does
    not say the output is colour-free produces a colour-bearing pattern, and that
    pattern is then either wrong or right by accident of which runner the gate
    happened to use that day.
    """
    doc = GATE_DOC.read_text(encoding="utf-8")
    assert "colour-free" in doc or "color-free" in doc, (
        "docs/gate.md must state that the gate's output is matched colour-free"
    )
    for topic in ("ANSI", "escape", "OSC", "CSI"):
        assert topic in doc, f"docs/gate.md never mentions {topic!r} when describing what is stripped"
    # And the weakening caveat has to be written down rather than discovered in
    # somebody's repository, which is the instruction the packet gives for it.
    for topic in ("weaken", "broaden", "last match"):
        assert topic in doc, (
            f"docs/gate.md must say what stripping does to a pattern ({topic!r}); a caveat "
            "that lives only in a worker's report is a caveat the next adopter does not get"
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
