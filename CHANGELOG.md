# Changelog

All notable changes to the cafaye **spec** are recorded here. This repository
is schemas, docs and validators, so "notable" means *a rule changed or a
document was clarified* — not a release of code. Bump guidance lives in
[README.md](README.md#spec-versioning).

Consumers pin a spec range in their manifest (`core: ^0.2.0`), so the
**breaking** section below is the one that matters when a service CI fails to
resolve.

## [Unreleased]

The payload reconciliation. One rule added, twelve payload schemas shipped, and
the check that would have caught courier's event types before they reached
master.

### Added

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

- **Twelve per-event payload schemas** for events the fleet already publishes
  but core had never described. See the payload table in
  [docs/event-naming.md](docs/event-naming.md#payload-schemas): courier's five,
  `muse.tokens.consumed`, and billing's seven more. The root cause of the gap was
  the same as the root cause of courier's violation — nothing compared a real
  service's manifest against core's catalog — so the schemas and the check land
  together.

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

- Twelve payload schemas still absent, for catalogued types no service publishes
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
