# Changelog

All notable changes to the cafaye **spec** are recorded here. This repository
is schemas, docs and validators, so "notable" means *a rule changed or a
document was clarified* — not a release of code. Bump guidance lives in
[README.md](README.md#spec-versioning).

Consumers pin a spec range in their manifest (`core: ^0.2.0`), so the
**breaking** section below is the one that matters when a service CI fails to
resolve.

## [Unreleased]

The payload reconciliation, and the observability spec.

### Changed — `error.type` is a closed vocabulary, and the status error obliges it

**BREAKING for a service that emits a class, and for kit-03, which is reading
these schemas in parallel.** muse is the only service that emits one today and it
is **not** migrated here — see "not migrated" below.

- **`error.type` is an `enum`, not a `pattern`, on all three signals.** The
  twelve classes plus `_OTHER`, byte-identical in
  [`traces`](schemas/telemetry/traces.schema.json),
  [`metrics`](schemas/telemetry/metrics.schema.json) and
  [`logs`](schemas/telemetry/logs.schema.json).

  **Why.** The previous constraint was a `pattern` and a 64-character cap, which
  bound the **shape** of the value and not the **vocabulary** — so
  `error.type = "user_42_email_invalid"` validated cleanly on every signal.
  Snake_case, twenty-two characters, a series per value. On metrics that is
  `tenant_id` on a measurement under a name that sounds like a classification:
  the same 2000-combination cap, the same silent undercount, the same dashboard
  that renders and is wrong. The description promised a bounded vocabulary and
  the schema did not have one, and a rule the schema does not enforce is not a
  cafaye rule (**D14**, ratified, now implemented). The `pattern` and the cap
  stay alongside the `enum` as the second line — they cannot reject a value the
  `enum` accepts — and a test asserts all three copies are byte-identical.

  One `enum` on all three signals is not tidiness. It is what makes the semconv
  rule that `error.type` is **identical** on a span and on its metric for the
  same operation enforceable at all: no JSON Schema can compare two documents, so
  the coupling has to be structural.

- **Four semconv rules encoded rather than described.** core-04 stated these and
  enforced none of them; with `error.type` deleted from `span.muse.json` the file
  still validated. They are constraints now, with negative examples.

  - **Span status `error` obliges `error.type`, and `error.type` obliges a failed
    status.** The biconditional is the point: the class is present exactly when
    the span failed, so its **absence is the load-bearing not-an-error marker**
    rather than an omission. On a duration histogram the samples carrying the
    class are the errors; a success that carries one moves the numerator and
    makes the error rate a number nobody can trust.
  - **`otel.status_code` may not contradict `status.code`.** Not a fifth rule —
    without it the first one is about a span with two statuses, which has no
    status to be obliged.
  - **Handled and retried errors are not recorded at all.** `SHOULD NOT` has no
    schema keyword, so it is encoded as **unrepresentable**: no signal allowlists
    an attribute a service could use to say "this attempt failed and I
    recovered", and no class in the vocabulary names one. The realistic
    violation is a well-meaning `error.handled: true` added in six months, and it
    now fails the suite.
  - **`error.type` is required on the operation duration histogram and absent on
    success** — the doc states it and the first rule above encodes the
    success half of it.

- **`error.message` stays absent, and its reasoning is kept in full.** It is
  `NOT RECOMMENDED` for metrics and spans: unbounded cardinality, and it
  duplicates span status. More concretely it is the one attribute already on a
  natural allowlist — every tracing SDK adds it by default — and the one that
  could carry a prompt, because a provider's content-policy rejection quotes the
  offending content back. That refusal is now recorded as `provider_rejected`,
  which says what happened with no content in it.

- **Two structural claims that were described everywhere and asserted nowhere,
  now asserted.** Found by mutation against core-04: deleting
  `additionalProperties` from the traces allowlist left the suite **green**, and
  adding `critical` to the span-status enum left it **green**. The status enum is
  the fleet-wide error predicate, so a fourth value invented by one service is a
  dashboard that silently misses it — which is exactly what the schema's own
  description promised could not happen.

- **Two new decisions**, both four paragraphs: **D18** (which twelve classes, and
  the test — is this class's rate worth an alert on its own? — rather than the
  list) and **D19** (whether semconv's `_OTHER` belongs in a snake_case
  vocabulary; it is the one documented exception, because a closed enum with no
  escape hatch gets widened under pressure and an alert on `_OTHER` is an alert
  that this service has not classified its own errors).

- **Stability marked honestly.** `error.type` and the trace status rules are
  **Stable**; the cross-signal coupling document, `recording-errors.md`, is
  **Development**. Where core encodes that coupling, each schema says so rather
  than implying the whole model has frozen.

- **The fleet-wide predicate is span status `Error`, not `error.type`** — stated
  plainly in [`docs/observability.md`](docs/observability.md#errortype) rather
  than left to be implied by the schema's shape. Partition by `service.name`,
  filter on status `error`, use `error.type` as a drill-down **inside** a
  service, and **never as a global grouping key**.

- **Not migrated, deliberately: muse.** It emits `error.type =
  "ProviderAuthError"` and `"CircuitOpen"`, and
  `tests/test_trace_propagation.py` asserts both. That is D14's stated cost of
  flipping and it is a separate packet; this one changes the contract. The
  file-by-file mapping a cold author needs is a table in
  [`docs/observability.md`](docs/observability.md#what-is-not-migrated-yet).

- **Fourteen new tests, and fifteen more examples** — one valid span per class,
  so `ls examples/valid/telemetry/error-type.*` is the whole vocabulary, plus
  five negative examples including the one that matters most: a well-shaped,
  snake_case, under-64-characters value that is not in the vocabulary, on traces
  and on metrics. The test asserts that value passes the shape and the cap
  **before** asserting the rejection, so it cannot pass because the pattern
  caught it — only the vocabulary can.

### Added — the observability spec

- **[`schemas/telemetry/`](schemas/telemetry/) and
  [`docs/observability.md`](docs/observability.md)** — the observability spec
  (PLAN.md §7b), as seven schemas and 33 tests. Core owns the event envelope the
  same way, so this is a contract and not a README paragraph: a rule that is not
  in `schemas/` is not a cafaye rule, and six services in six languages would each
  otherwise invent their own span names and their own idea of which attributes
  are safe.

  - **`span-naming.schema.json`** — one scheme, all six languages:
    `<service>.<operation>[.<target>]`, the same *shape* as the event grammar's
    `<service>.<entity>.<action>` and for the same reason. Low-cardinality **by
    construction**: a segment is at most fifteen characters, which is what
    refuses `muse.user.usr_01J9Z8QK5M4N7P2R3T6V8W9X0A` without core growing a
    cafaye-id pattern to recognise one. `GET /users/:id`, `get_user` and
    `users.GET` are all rejected, and `get_user` and `users.GET` are what a
    fleet ships when nobody has said. **D15** records the alternatives, including
    the OTel HTTP convention (`{method} {route}`), which is rejected for putting
    the route in the name.

  - **`metrics.schema.json`** — the part with teeth, and the reason this packet
    exists. OpenTelemetry caps a metric stream at **2000 distinct attribute
    combinations**; on overflow the SDK folds everything into a single
    `otel.metric.overflow=true` point and drops every measurement attribute.
    Totals stay correct, per-dimension breakdowns silently undercount, and
    nothing anywhere reports an error. So `tenant_id`, `user_id`, `account_id`,
    `request_id`, `trace_id` and eight more are **prohibited** as measurement
    attributes and **required** on `resourceAttributes` instead, which are
    attached once per process, exempt from the cap, and survive on the overflow
    point — so a per-tenant total stays answerable when the measurement has
    folded. The prohibition is enforced twice (absent from the allowlist *and*
    named in a `not`, so adding it to the allowlist later does not quietly
    succeed), the two lists are disjoint by construction, and a test asserts that
    a resource name is *rejected* when submitted as a measurement attribute.
    That last one is the mechanism: moving identity onto the measurement to get
    a per-tenant breakdown is what produces a dashboard that looks right and is
    wrong.

  - **`redaction.schema.json`** — prompt and completion content must never appear
    in a telemetry span, encoded as an **allowlist, default-deny**, because
    "don't log prompts" in prose has been tried across this fleet and does not
    hold. The realistic leak is not an attacker; it is a well-meaning
    `muse.prompt` added in six months by someone debugging a routing decision, in
    a service whose prompts are other customers' data. No allowlisted name on
    any of the three signals contains a word that names content — muse's canary
    at `muse/tests/test_trace_propagation.py`, promoted to a spec assertion.
    `error.message` is prohibited *by name* because a tracing SDK adds it by
    default and a content-policy rejection quotes the offending content back, so
    it is a prompt by another route. The may-record side is in the schema too
    (token counts, model id, latency, status, finish reason), because a policy
    that only says what may **not** be recorded is not implementable.
    `enforcedAt` is an enum with `collector` as the only value a cafaye policy may
    carry, so kit's collector config and a service's SDK setup are both checked
    against one file. **D13** argues the enforcement point with evidence.

  - **`otel-endpoint.schema.json`** — `*_OTEL_ENDPOINT` is the contract, the
    shipped collector is only its **default value**, and `required` is a
    `const: false`, which is the field that separates on-by-default from
    mandatory. The no-op path is four negative properties — **no buffering, no
    retry, no warning spam, no dial at boot** — each pinned to `none`, so a
    declaration that admits any of them does not validate. It is implemented by
    the OTel spec's own `OTEL_SDK_DISABLED`, not a cafaye invention, because
    re-implementing "disabled" in six languages is how six services acquire six
    definitions of it. `disabledBy` is keyed by signal and requires all four, so
    a declaration cannot document a no-op that covers only traces — a service
    still phoning home for metrics is discovered by a customer's invoice.

  - **`probes.schema.json`** — `healthz` gets `maxItems: 0` and `readyz` gets
    `minItems: 1`, so **a `readyz` that checks nothing fails the schema** and a
    `healthz` that starts consulting the database cannot validate. The second is
    the restart loop: a liveness probe that fails on a dependency restarts a
    process that is fine, turning a database outage into a fleet-wide crash loop
    and destroying the evidence needed to diagnose it. darkroom is the pattern
    (`/healthz` never touches a dependency, `/readyz` really runs `select 1`),
    and both probes are `auth: exempt` by explicit path allow-list, because a
    probe behind the auth middleware returns 401, every instance is marked
    unhealthy, and the rollback says nothing about authentication.

  - **`traces.schema.json` / `logs.schema.json`** — the other two per-signal
    allowlists, with the same rules applied. Logs are the smallest by design
    (`maxProperties: 12`, well under OTel's default 128): every log attribute is
    a candidate for a Loki label, every label is a stream, and streams are what a
    log store runs out of.

- **`error.type` as the fleet's error grouping key.** The user asked whether
  there is one place to see all errors for the whole system; this is the part of
  the spec that makes the answer yes rather than a wall of ungrouped text. It is
  a low-cardinality class — snake_case, ≤ 64 characters, the same shape on every
  signal — and never a message, a stack trace, or a per-service exception class
  name, because `ProviderAuthError` (Python), `ErrProviderAuth` (Go) and
  `ProviderAuthError` (Elixir) are one failure in three taxonomies, and three
  taxonomies means six places rather than one. **D14** has the alternatives and
  the cost, including the fact that flipping it touches a muse test.

- **`fleet.yml` gains a required `telemetry` block per service** — which
  signals it exports today, which `*_OTEL_ENDPOINT` variable points at it, and
  whether it serves HTTP. Required, so "what is instrumented across the fleet"
  has one answer rather than six, and so a service dropped from the declaration
  is a service nobody checks. Every service currently declares `signals: []`
  except muse, which is the honest record rather than claiming instrumentation
  that is not there.

- **Five new numbered decisions**, all with the four paragraphs AGENTS.md asks
  for: **D13** the redaction enforcement point, **D14** `error.type` granularity,
  **D15** the span-name form, **D16** the endpoint variable name, and **D17** a
  divergence this packet found rather than fixed.

### Fixed

- **A cross-repo drift the observability spec made visible.** `muse` reads
  `MUSE_OTEL_EXPORTER_OTLP_ENDPOINT` — the OpenTelemetry standard spelling,
  which is what `muse/tests/test_resilience_config.py` asserts — while
  `muse/tests/test_telemetry.py` and PLAN.md §7b both call it
  `MUSE_OTEL_ENDPOINT`. Three places, three spellings, and the code agrees with
  neither document. Core specifies `<SERVICE>_OTEL_ENDPOINT` (**D16**), `fleet.yml`
  records the divergence, and **D17** carries it as an open decision with the
  alternative (adopt the OTel standard names, in which case muse is already
  conforming and the divergence disappears) rather than leaving it only in a
  commit message. No service was modified: muse is a read-only reference here.

### Added — the payload reconciliation

- **[`fleet.yml`](fleet.yml) and
  [`schemas/fleet.schema.json`](schemas/fleet.schema.json)** — a machine-readable
  record, per service repository, of what that service's own `cafaye.yml`
  declares on `master`, with the full 40-character commit each one was read at
  and the day it was read. Per service, three lists: `events` (published today,
  in the conforming three-segment form), `cataloguedOnly` (a catalog row nobody
  publishes yet — a promise, not a claim), and `manifestViolations` (types a
  manifest spells in a way that breaks the grammar, transcribed verbatim).

  **Why.** The catalog was asserted only against core's own
  `examples/valid/*.cafaye.yml`, which core also writes, so the assertion could
  only ever catch core disagreeing with itself. A service could advertise
  anything. courier did: five types in the two-segment form v0.2 froze away
  reached master and are still there. `fleet.yml` is the missing other side of
  that comparison, and it gives `caf contract lint` one file to consume instead
  of a re-derivation of the catalog that can disagree with this one.

  It is a record of other repositories, so it is versioned as one: `sourceCommit`
  and `readOn` are required, and `manifestViolations` entries are deleted when
  the publisher corrects its manifest.

- **Thirteen new per-event payload schemas**, plus one rewritten, for events the
  fleet already publishes but core had never described. See the payload table in
  [docs/event-naming.md](docs/event-naming.md#payload-schemas): courier's five,
  `muse.tokens.consumed`, and billing's seven more. Fifteen of the catalog's
  thirty rows now have a schema; the other fifteen belong to types no service
  publishes yet. The root cause of the gap was the same as the root cause of
  courier's violation — nothing compared a real service's manifest against core's
  catalog — so the schemas and the check land together.

  **courier's five**, `courier.email.queued`, `.delivered`, `.bounced`,
  `.complained` and `courier.notification.suppressed`. Four carry the four fields
  `Courier.Deliver` builds, which is `message_id`, `user_id`, `notification_type`
  and `email` — and nothing from the caller's payload, because the envelope goes
  to every subscriber on the bus and a verification token in there is a credential
  leak into a fan-out. `courier.notification.suppressed` has **no** `message_id`,
  because nothing was rendered, addressed or sent: the entity is the recipient,
  so the payload is `user_id`, `notification_type`, `email` and a `reason`. No
  provider diagnostic appears in the bounced or complained payloads, because
  courier has no webhook receiver yet and a field no publisher emits is a contract
  that lies.

  Two fields are deliberately absent across all five, each recorded in
  [DECISIONS.md](DECISIONS.md): a provider message id (real — courier's own test
  fixture carries `provider_id`, its `Deliver` module does not), and a recipient
  key the fleet can join on (**D7** — courier uses a bare uuid, identity
  publishes `usr_…`, and no schema can reconcile that).

  **`muse.tokens.consumed`**, exactly the five fields `muse/metering.py` builds:
  `model`, `provider`, `tokens_in`, `tokens_out`, `cost_micros`. No account, no
  request id, no price — a payload schema is closed, and a field added now is one
  a future schema carries forever. The negative example is the price table: the
  per-1k rates really are in the publisher's `Price` object and really do move,
  so an event carrying them would say the cost and the price were true at the same
  instant. `muse` gets a catalog section and
  `examples/valid/muse.cafaye.yml` to go with it.

  **`consumed` joins the action vocabulary.** muse has published this type since
  it existed and `consumed` was not on the list, which the vocabulary itself
  says is a manager decision (**D9**). `muse.usage.recorded` was the alternative
  and is rejected in D9: it already means a different fact on a different subject.
  The call is reversible in one word plus a deprecation cycle, and it is recorded
  rather than made quietly.

  **billing's seven more** — `billing.customer.created`, `billing.plan.created`,
  `billing.plan.updated`, `billing.subscription.updated`,
  `billing.subscription.canceled`, `billing.payment.succeeded`,
  `billing.payment.failed` — plus the rewrite above. Two of them earned their keep
  on their own.

  `billing.payment.succeeded` **has two shapes**: billing emits it from an
  invoice (`invoice_id`, `subscription_id`, `attempt_count`,
  `next_payment_attempt`) *and* from a one-time Checkout session
  (`checkout_session_id`, `client_reference_id`). Rather than flatten them into
  an optional-everything schema, the schema declares a `oneOf` — exactly one
  shape, never both, never neither — and both are covered by a valid example,
  checked by a new `test_payload_schema_variant_examples_validate` so neither is
  assumed (**D11**). The negative example claims to be both at once, which is the
  mistake `oneOf` exists to make impossible.

  `billing.payment.failed`'s `amount` is **what could not be collected** — the
  amount due, never the amount paid. Its negative example carries a second
  `amount_paid: 0` field, because on a failed charge that zero is truthy and
  reads as "nothing was collected" to a consumer that wants the charge size.
  billing's own source comment names this exact bug.

  `billing.customer.created`'s `metadata` is **the one deliberately open object in
  the repository** (**D12**): it is a free-form `jsonb` bag, and closing it would
  make the field permanently `{}`. Every other object in every schema here is
  closed, and that field's own description says it is the exception.

- **Every published event type now has a catalog row and a payload schema, checked
  against the services' real manifests.** `fleet.yml` is the input;
  `test_every_published_fleet_event_has_a_catalog_row_and_a_payload_schema` is
  the assertion, and it is the check courier's five types would have failed the
  day they were declared — the one with no equivalent anywhere else. Proven by
  hiding courier's payload schemas and watching it fail with all five named.

### Breaking

- **`billing.subscription.started`'s payload schema was rewritten.** The v0.2
  version required `subscription_id`, `plan_id` and `account_id` as
  `sub_…`/`pln_…`/`acc_…` — a world in which billing holds cafaye-prefixed ids.
  billing has no subscriptions table and cannot invent ids it does not have; its
  webhooks carry the processor's `sub_…`, `cus_…` and `price_…` and its primary
  keys are bare uuids. The schema now describes what billing emits, with
  `processor` and `processor_event_id` on every payload so a consumer can tell a
  fact billing knows from a fact billing was told. **D10**, with the alternatives
  and the cost of reversing it.

  The alternative was to keep the text and write a valid example full of ids
  billing never sends — which validates, passes the suite, and fails on every
  real event. That is the outcome the rewrite exists to prevent.

### Fixed

- **`billing.plan.updated` had no catalog row.** billing has published it from
  its own manifest since it existed, and core's suite could not see it for the
  reason above. Row added; `billing.plan.created` and `billing.customer.created`
  had rows and no payload schemas, which is the same gap one layer down.

- **`muse` had no catalog section at all.** The service publishes a type and core
  had never heard of it, for the same reason. Section added, and an example
  manifest so the bidirectional assertion covers the new publisher rather than
  skipping it.

- **The `eventType` and `serviceName` patterns now have a third copy to keep in
  step** (`schemas/fleet.schema.json`), and the parity test covers all three. A
  pattern that appears once is a rule; a pattern that appears three times with
  two assertions is still one rule, but the assertions have to name all three.

### Changed

- **Open decisions are tracked in [DECISIONS.md](DECISIONS.md), not as callouts
  in `docs/`.** `docs/` stays free of undecided callouts because
  `test_no_open_decision_callouts_remain_in_the_docs` is a merge gate: a spec on
  `master` must read as decided. A worker branch that opens a real question
  would trip it, and the tempting fix — weakening or skipping that test — is how
  a spec silently stops being enforced. So open questions are numbered in one
  file at the repository root, linked from the doc that raises them, and
  asserted well-formed by `test_open_decisions_are_numbered_and_complete`.

### Known gaps

- Fifteen payload schemas still absent, for catalogued types no service publishes
  yet: identity's other eleven, `billing.subscription.past_due`,
  `billing.payment.refunded`, `billing.invoice.created`,
  `billing.usage.recorded`. `fleet.yml` marks each as `cataloguedOnly` so the
  difference between a promise and a fact is mechanical rather than a judgement.

## [0.2.0] — 2026-09-30

The event grammar, the payload-schema home, and the OpenAPI versioning rule are
all decided. One of them breaks an existing manifest, so this is a spec major.

### Breaking

- **Event types are `<service>.<entity>.<action>`. Three segments, always
  prefixed, no exceptions.** v0.1 accepted a two-segment `user.created` and only
  required the prefix for generic entities (`identity.api_key.created`); that
  exception is gone.

  | v0.1 | v0.2 |
  | --- | --- |
  | `user.created` | `identity.user.created` |
  | `subscription.started` | `billing.subscription.started` |
  | `identity.api_key.created` | unchanged — it was already the canonical form |

  The service segment is a service name, so it is kebab-case and may contain a
  dash (`email-sender.email.queued`); an underscore in the first segment is now a
  schema violation. The entity and action segments stay lowercase snake_case.

  **Downstream action.** Every published and consumed event type in every
  `cafaye.yml` must be renamed to its three-segment form, and every
  subscription, route, SDK constant and dashboard filter keyed on a two-segment
  type must follow it. This is a follow-up packet per service: core's own
  examples are updated here, the service repositories are not. Bump `core` to
  `^0.2.0` in the same commit as the rename — a service pinned to `^0.1.0`
  cannot resolve this release and will fail CI rather than silently accept the
  old format.
- **`subject` is required on the envelope.** It was already documented as
  required and was in fact optional in the schema. Entity-less events use the
  literal `platform`; there is no absent-`subject` case any more.

### Added

- **`schemas/events/<service>/<entity>/<action>.schema.json`** — per-event
  `data` payload schemas, in core. Two ship as the pattern:
  [`identity/user/created`](schemas/events/identity/user/created.schema.json)
  and
  [`billing/subscription/started`](schemas/events/billing/subscription/started.schema.json).
  A payload schema is a promise to other services, so it has one home with one
  release cadence rather than a copy in each publisher's repository. Core churns
  on every payload change; that is the cost, paid in review instead of in a
  consumer breaking on a Tuesday.
- **`docs/event-outbox.md`** — the transactional outbox convention: the
  `outbox_events` table, the insert in the same transaction as the domain write,
  the publisher loop (`for update skip locked`, ack before `published_at`,
  `attempts` with exponential backoff), at-least-once and therefore mandatory
  consumer idempotency, retention, and a sequence diagram. A convention only:
  each service implements it in its own language, and there is deliberately no
  shared outbox library.
- **`billing.plan.created`** to the billing catalog (11 events, up from 10).
- **Negative examples** for the tightened grammar (`event-envelope.untagged.invalid.json`),
  for the now-required `subject` (`event-envelope.subjectless.invalid.json`), and
  for both payload schemas. A negative example now needs a row in
  `examples/invalid/README.md` keyed by repo-relative path, and the suite fails on
  any negative file that is not documented.

### Changed

- **`docs/openapi-conventions.md`** — `/v1` path prefix **and** `info.version` are
  both required, with the sync rule (breaking change bumps both together, a
  non-breaking change bumps only `info.version`) and a note that a future
  `caf contract lint` will enforce it.
- **`docs/manifest-conventions.md`** — the semver mini-grammar stays. Full npm
  semver is out of scope: resolution belongs to a future `caf contract`, and
  `>=1.0.0` against a `0.x` service is a range that lies. Added a sixth
  cross-field rule: a consumed event type must exist in the core catalog.
- **`docs/event-naming.md`** — the grammar section, the catalog and the envelope
  table are rewritten around the three-segment rule, with the reasoning for
  making `subject` required. The new [Payload schemas](docs/event-naming.md#payload-schemas)
  section states the path convention and lists every payload schema in core.
- **`examples/valid/event-envelope.json`** — `data.user_id` was a 27-character id
  and did not match `subject`; the account id in the same payload was also 27
  characters. Both are 26-character ULIDs now, and the payload example is the one
  `schemas/events/identity/user/created.schema.json` validates.

### Open decisions

None. D1–D5 are decided:

| # | Decision |
| --- | --- |
| D1 | One canonical form: `<service>.<entity>.<action>`, always prefixed. |
| D2 | `subject` stays required; `platform` is the escape hatch for entity-less events. |
| D3 | Payload schemas live in core, one per event type, at a path derived from the type. |
| D4 | Both `/v1` and `info.version` are required, with the sync rule documented. |
| D5 | The semver mini-grammar is kept; `caf contract` resolves it. |

### Known gaps

- The reserved service-name list (`cafaye`, `caf`, `kit`, `core`, `docs`,
  `pantry`) is a review rule, not a schema constraint — core's own manifest is
  `name: core`, so encoding the list would make core fail its own schema.
- Only 2 of the 28 catalogued events have a payload schema. Each lands with the
  packet that first needs one; the suite fails on a payload schema that is not
  listed, or a listed path that does not exist.
- No OpenAPI document is shipped. `core` supplies the conventions a service's
  own `openapi/openapi.yaml` must agree with, not the documents themselves, and
  `caf contract lint` does not exist yet.
- The outbox convention is a document, not a schema: the column list is asserted
  out of the SQL block in `docs/event-outbox.md`, and nothing here checks a
  service's actual migration.

## [0.1.0] — 2026-09-30

> Superseded by [0.2.0](#020--2026-09-30), which changed the event type format.
> This section is the record of what 0.1.0 said, including the decisions that
> were still open when it shipped; all five were decided in 0.2.0.

First cut of the cafaye contract substrate. Everything below is a new rule, so
nothing here can break an existing service; a service pinned to `^0.1.0` may
move to any `0.1.x` without review.

### Added

- **`schemas/cafaye.manifest.schema.json`** — draft 2020-12 schema for
  `cafaye.yml`: `name` (cafaye namespace rules), `language` enum, the `core`
  spec constraint, `exposes` (OpenAPI path + published event types),
  `consumes`, `dependencies`, `repository` (SSH remotes, `master` default
  branch), and `owner`. Closed with `additionalProperties: false` at every
  level.
- **`schemas/event-envelope.schema.json`** — the envelope every event travels
  in: `id` (UUID), `type` (`<entity>.<action>` or
  `<service>.<entity>.<action>`), `source` (the publishing service), `subject`,
  `time` (RFC3339), opaque `data`, and `specversion`. CloudEvents 1.0 attribute
  names; `specversion` pins the dialect.
- **`docs/event-naming.md`** — the event grammar, the action vocabulary, the
  delivery guarantees, and the initial catalog for **identity** (12 events),
  **billing** (10) and **courier** (5).
- **`docs/openapi-conventions.md`** — the `application/problem+json` error
  envelope, cursor pagination, `/v1` versioning, the `Idempotency-Key` rule,
  JWT auth via identity with a JWKS URL, and the deprecation policy.
- **`docs/manifest-conventions.md`** — manifest shape, namespace rules, the
  core semver mini-grammar, and the five cross-field rules JSON Schema cannot
  express.
- **`examples/`** — four valid manifests (Go API, Ruby API, event-publishing
  worker, worker-only), a valid envelope, and one invalid document per schema
  with the expected failure documented field by field in
  [`examples/invalid/README.md`](examples/invalid/README.md).
- **`tests/`** — the contract suite: every valid example validates, every
  invalid example is rejected for its documented reasons, and the docs are
  checked against the schemas. `bin/prime` runs it; `tests/setup.sh` builds the
  venv. The catalog and the example manifests are asserted to agree in both
  directions, so an event cannot be published without being documented or
  documented without being published.
- **`cafaye.yml`** — core's own manifest, `language: spec`, validated against
  core's own schema on every test run.
- **`README.md`**, **`AGENTS.md`**, **`mise.toml`**, **`.gitignore`**.

### Open decisions

Numbered as in the docs. Each was drafted with a default so nothing was blocked.
**All five were decided in [0.2.0](#020--2026-09-30)**; the outcomes are in that
release's "Open decisions" table, and the drafted defaults below are the record
of what shipped in 0.1.0, not a statement of the spec today.

| # | Question | Drafted default |
| --- | --- | --- |
| D1 | two- or three-segment event types | both accepted; service prefix required only for generic entities |
| D2 | is `subject` required? | required, with `platform` as the no-single-entity escape hatch |
| D3 | where does a per-event `data` payload schema live? | none in v0 — the publisher owns it; recommends a future `contracts/` repo |
| D4 | `/v1` path prefix vs. document version | both required, with the sync footgun noted |
| D5 | cafaye's semver mini-grammar vs. full npm semver | keep the mini-grammar, resolve it in `caf contract` |

### Known gaps

- The reserved service-name list (`cafaye`, `caf`, `kit`, `core`, `docs`,
  `pantry`) is a review rule, not a schema constraint — core's own manifest is
  `name: core`, so encoding the list would make core fail its own schema.
- No per-event `data` payload schemas, by design pending D3. Contract tests
  validate the envelope; payload tests are the publisher's.
- No OpenAPI document is shipped. `core` supplies the conventions a service's
  own `openapi/openapi.yaml` must agree with, not the documents themselves.

[Unreleased]: https://cafaye.com/changelog/core
[0.2.0]: https://cafaye.com/changelog/core/v0.2.0
[0.1.0]: https://cafaye.com/changelog/core/v0.1.0
