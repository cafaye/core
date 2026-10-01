# Open decisions

Every question this spec has not been told the answer to, numbered, with the call
that was made so the work could continue and the cost of making the other one.

**These live here, not in `docs/`.** AGENTS.md asks for a
`> DECISION NEEDED (Dn):` callout in the affected document, and
`test_no_open_decision_callouts_remain_in_the_docs` fails if one is there. Those
two instructions cannot both be satisfied, and the test is the one to keep: it is
a merge gate whose whole job is that a spec on `master` reads as decided. The
other way round — weakening or skipping the gate — is exactly how a spec silently
stops being enforced. So the questions are numbered here and the affected
document cites the number, which `test_open_decisions_are_referenced_from_a_document`
enforces. A settled decision moves into the [CHANGELOG](CHANGELOG.md)'s decision
table and its entry here is deleted; the number is never reused.

| # | Question | Call made |
| --- | --- | --- |
| [D6](#d6-where-do-open-decisions-live) | where do open decisions live? | `DECISIONS.md` at the repository root |
| [D7](#d7-courier-keys-a-user-by-uuid-and-identity-publishes-a-usr_-id) | courier keys a user by uuid, identity publishes a `usr_` id | each schema says what its publisher emits; the mismatch is cross-referenced, not papered over |
| [D8](#d8-what-is-the-subject-of-couriernotificationsuppressed) | what is the `subject` of `courier.notification.suppressed`? | the user id; both candidates stay in the payload |
| [D9](#d9-consumed-is-not-in-the-action-vocabulary-and-the-payload-has-no-account) | `consumed` is not in the action vocabulary, and the payload has no account | catalogue `consumed`; the missing account is muse's, not core's |
| [D10](#d10-billingsubscriptionstarteds-payload-schema-no-longer-describes-cafaye-ids) | `billing.subscription.started`'s payload schema required ids billing does not have | rewritten to the processor ids billing actually emits — a breaking change, recorded |
| [D11](#d11-billingpaymentsucceeded-has-two-payload-shapes) | `billing.payment.succeeded` is emitted from two sources with two shapes | `oneOf`, plus a rule for a payload with one type and two meanings |
| [D12](#d12-metadata-is-the-one-deliberately-open-object) | `additionalProperties: false` everywhere, but `metadata` is a free-form bag | open, and named as the only exception in the repo |
| [D13](#d13-where-is-the-redaction-boundary-enforced--the-collector-or-each-service) | is the redaction boundary enforced at the collector, or in each service? | at the collector, as one chokepoint; per-service allowlists are defence in depth |
| [D14](#d14-how-coarse-is-errortype) | how coarse is `error.type`, the fleet's error grouping key? | a bounded, fleet-wide class vocabulary — not a message, not a per-service exception class |
| [D15](#d15-the-span-name-form) | what shape is a span name? | dotted `<service>.<operation>[.<target>]` with a 15-character segment cap |
| [D16](#d16-which-variable-name-is-the-endpoint-contract) | which variable name is the endpoint contract? | `<SERVICE>_OTEL_ENDPOINT`; the collector is its default value, not a requirement |
| [D17](#d17-muses-endpoint-variable-and-the-two-names-core-now-has-for-it) | muse reads `MUSE_OTEL_EXPORTER_OTLP_ENDPOINT`; PLAN.md §7b says `MUSE_OTEL_ENDPOINT` | recorded, not papered over: muse is non-conforming to D16 and owes a one-line rename |
| [D18](#d18-which-classes-are-in-the-error-vocabulary) | D14 is ratified; which twelve classes are actually in the vocabulary? | twelve, grouped by who acts, with the test being whether a class's rate is worth an alert on its own |
| [D19](#d19-does-_other-belong-in-a-snake_case-vocabulary) | semconv's `_OTHER` fallback does not fit cafaye's snake_case shape — include it or omit it? | included, as the one documented exception; an alert on it is an alert that this service has not classified its own errors |
| [D20](#d20-kits-language-none-job-runs-the-gate-on-an-unpinned-interpreter) | kit's `language: none` job runs core's gate on an unpinned interpreter | accept the disclosure; the companion `gate` job carries the pin and asserts it |
| [D21](#d21-a-breaking-schema-change-has-no-re-vendor-fan-out-step) | a breaking schema change has no re-vendor fan-out step | record the gap; no packet should invent a mechanism that reaches into six repositories |
| [D22](#d22-should-cores-suite-assert-format-uri) | should core's suite assert `format: uri`, which no installed checker implements? | not built: no dependency added, and the gap is named in a test and here instead |
| [D23](#d23-do-the-openapi-and-cross-field-rules-become-a-schema) | do the OpenAPI conventions and the cross-field manifest rules become a JSON Schema? | not built: the harness makes sixteen rules executable, named and inventoried, and the schema question stays open |
| [D24](#d24-the-event-catalog-and-the-spec-version-are-documents-not-data) | the event catalog and the spec version are markdown and prose, not data | not built: the harness reads the document, which is right for now and is the second reader that argues against it |
| [D25](#d25-may-a-service-document-healthz-and-readyz) | may a service document `/healthz` and `/readyz` in its OpenAPI document? | not built: the harness reports what the document says, and the spec is silent |
| [D26](#d26-do-the-cafaye-fields-live-inside-the-sloth-document-or-in-a-cafaye-document-kit-converts) | do the cafaye fields live inside the Sloth document, or in a cafaye document kit converts? | inside, as landed; `additionalProperties: false` decides, and the fallback is a four-line transform in kit |
| [D27](#d27-the-burn-factors-come-from-a-30-day-budget-and-the-period-is-28-days) | the burn factors come from a 30-day budget and the period is 28 days | both as ruled, and the ~7% gap is asserted with its direction |
| [D28](#d28-may-cores-gate-take-the-sloth-dependency) | may core's gate take the `sloth` dependency? | not taken: the composition is checked in the harness, PromQL grammar is named as owed |
| [D29](#d29-which-tier-does-each-of-the-seven-services-get) | which tier does each of the seven services get? | not built and not decided: a tier with no SLO behind it is a number with nothing to page on |
<!-- The index above stops at D29, and D30-D33, D34 and D35 follow it in not
     being tabulated, rather than in being a fifth omission the next reader has
     to notice. Tabulating the recent ones and leaving the older ones out is the
     same mistake in a new place: the table stops being the index and becomes the
     list of decisions somebody happened to write down lately. -->
| [D34](#d34-how-does-the-fleet-record-a-type-core-has-not-finished-contracting-for) | how does the fleet record a type core has not finished contracting for? | a fourth constrained list, `pendingCoreContract`, and an assertion that rejects an entry core has already finished |
| [D35](#d35-identityusercreateds-payload-schema-describes-a-payload-its-only-publisher-does-not-emit) | `identity.user.created`'s schema requires a `usr_` id and three fields its only publisher does not emit | not resolved: out of scope for core-23 and a change to a shipped contract, with the fix and the test that would have caught it written out |

## D6: where do open decisions live?

Raised while reconciling the payload schemas. Affects
[`docs/event-naming.md`](docs/event-naming.md) and
[`tests/test_specs.py`](tests/test_specs.py)'s
`test_no_open_decision_callouts_remain_in_the_docs`.

**Choice:** open questions are numbered in this file at the repository root, and
the document that raises one cites the number inline. `docs/*.md` stays free of
undecided callouts, so the existing merge gate is untouched.

**Alternatives:**

1. Put `> DECISION NEEDED (Dn):` callouts in `docs/event-naming.md` as AGENTS.md
   literally says, and accept that the suite is red on the worker branch until
   the manager rules. Honest about the process, but it hands the manager a branch
   where `bin/prime` fails for a reason that is not a defect.
2. Put the callouts in `docs/` and relax
   `test_no_open_decision_callouts_remain_in_the_docs` to allow numbered ones.
   Rejected: it deletes the guarantee that a merged spec reads as decided, and a
   relaxation in a worker branch is how that guarantee is lost for good. Nothing
   else in this repository would notice.
3. Put the callouts in the doc and skip the test while they are open. Rejected for
   the same reason, and worse: a permanent skip is invisible in a diff.

**Recommendation:** option 1, as landed. It keeps the gate, keeps the decision
where a reader of the spec will find it, and makes the callout itself a citable
number — which is what AGENTS.md actually wants from a decision, and what the
`test_open_decisions_are_numbered_and_complete` assertions now check.

**Cost of flipping:** back to callouts in the doc is one commit — delete this
file, add the callouts, and decide what
`test_no_open_decision_callouts_remain_in_the_docs` should assert instead of
`not open_callouts`. Say what a *bad* state is for it (an unnumbered callout, a
duplicated number) and the gate can be rewritten to catch that without going
quiet.

## D7: courier keys a user by uuid and identity publishes a `usr_` id

Raised while writing courier's five payload schemas. Affects every
[`schemas/events/courier/`](schemas/events/courier) files and
[`schemas/events/identity/user/created.schema.json`](schemas/events/identity/user/created.schema.json).

**Choice:** `courier.*`'s `user_id` is `format: uuid`, because that is what
courier emits — `uuid` column, `priv/repo/migrations/…_create_notification_preferences.exs`
and `test/courier/deliver_test.exs:22`. `identity.user.created`'s `user_id` stays
`^usr_[0-9A-Z]{26}$`, because that is what identity emits. Both schemas name
this decision and point at it. Core does not pick a winner, and does not make
either schema accept the other's format.

> **THE PREMISE OF THE SECOND HALF IS FALSE, and [D35](#d35-identityusercreateds-payload-schema-describes-a-payload-its-only-publisher-does-not-emit)
> is the correction.** "That is what identity emits" was never read out of
> identity; it was carried over from the id vocabulary core imagined before any
> publisher's code was looked at. At identity's `a20be0f` the publisher emits a
> bare uuid, and the eight schemas core-23 wrote beside this one all say so.
> **The two halves of this decision are therefore the same fact — uuid — and the
> mismatch it describes no longer exists between these two schemas.** What remains
> is a `usr_`-prefixed id in one file against a uuid in four, which is a
> contradiction inside core rather than a divergence between services. The
> recommendation below is superseded by D35's; the alternatives are kept, because
> the reasoning about accepting both formats — or accepting neither — still holds
> for whatever replaces the prefix.

**Alternatives:**

1. One id vocabulary across the fleet. Either courier switches to `usr_…` or
   identity stops prefixing. Correct in the end, and not core's call — it is a
   change to identity's publisher and to courier's database column, in two
   repositories, and either way it is a breaking change to an emitted payload.
2. Accept both formats in both schemas (`pattern` with an alternation). Rejected:
   it converts a real, findable mismatch into a schema that agrees with everything
   and therefore detects nothing. A consumer joining these two payloads still
   has to try both spellings.
3. Say nothing and let each schema be locally true. Rejected: locally true and
   unjoinable is how a cross-service key mismatch becomes a 3am reconciliation
   bug. That is why this is written down rather than inferred.

**Recommendation:** call 1 as landed, and resolve the vocabulary in the identity
and courier repositories rather than here. Whichever way it goes, the change is a
**major** for the payload that moves (`usr_…` → uuid or the reverse), and the
alternative — a new event type, published alongside, with the old one deprecated
over six months — is available and cheaper to start than to finish.

**Cost of flipping:** in core, one line per schema (`format: uuid` ↔
`^usr_[0-9A-Z]{26}$`) plus the valid example in each. In the services, one column
type and one `Ecto`/Go cast in courier or identity, and a migration if the stored
ids are already prefixed. The expensive half is not in this repository.

## D8: what is the `subject` of `courier.notification.suppressed`?

Raised while writing the same five schemas. Affects
[`schemas/events/courier/notification/suppressed.schema.json`](schemas/events/courier/notification/suppressed.schema.json)
and the catalog row for the type in
[`docs/event-naming.md`](docs/event-naming.md).

**Choice:** the user id. The catalog calls the subject "the recipient", and both
readings of that are candidates — but the user id is the only one courier can
produce today from data it already holds, because it checks preferences by user
id before it ever looks at an address. The payload carries `user_id` and `email`,
so a consumer can join on whichever the manager picks, and switching costs a
payload-schema change and not a re-read of anyone's data.

**Alternatives:**

1. The address. Defensible: two reasons of the three (`address_suppressed`,
   `rate_limited`) are about the address, and the suppression list is keyed on it.
   Against it: an address is mutable, and `subject` is the per-entity ordering
   key, so a suppression list keyed on a value the recipient can change is a
   correlation key that moves under you.
2. courier grows a suppression-list row with its own id and the subject is that.
   Cleanest eventually, and it needs a table and a migration in courier that does
   not exist. Against it now: it invents an entity to have something to name.
3. The reserved literal `platform`. Rejected: `platform` means "no single entity
   yet", and a suppression is emphatically about one recipient. Using it would
   make every suppression correlate with every other one.

**Recommendation:** call 1 as landed, with option 2 as the destination. When
courier's suppression table lands, the subject moves to its row id, all five
courier payloads keep `user_id` and `email`, and the change is a **minor** for
the payload schema (an added required field is a minor) plus a breaking `subject`
change on every suppression event ever published — which, at the volume
suppressions happen, is a deprecation rather than an announcement.

**Cost of flipping:** to the address, change the catalog row's subject cell and
one sentence in the schema. Trivial now, and the reason it is cheap now is that
suppression volume is low; it is not cheap once real events exist, which is the
argument for deciding it before courier's receiver does. To option 2, it is a
suppression table in courier plus the subject change above, and the breaking part
is that every suppression event ever published reports a different entity.

## D9: `consumed` is not in the action vocabulary, and the payload has no account

Two questions in one, because both come from the same event and both are about
the same thing: whether `muse.tokens.consumed` is a thing the platform wants.
Affects the [action vocabulary](docs/event-naming.md#action-vocabulary), the
`muse` catalog row in [`docs/event-naming.md`](docs/event-naming.md), and
[`schemas/events/muse/tokens/consumed.schema.json`](schemas/events/muse/tokens/consumed.schema.json).

### The action

**Choice:** `consumed` joins the action vocabulary. The vocabulary is a list of
actions the platform has, not a list of verbs English has; `queued`,
`delivered`, `bounced` and `suppressed` are in it and none of them is a
"standard" eventing verb.

**Alternatives:**

1. Add `consumed`. The event is a real fact about a real spend, and the entity
   (`tokens`) names it as precisely as `plan` names a price.
2. Rename the type to `muse.usage.recorded`, which is already in the vocabulary
   and is what billing already means by usage. Against it: `recorded` is in the
   vocabulary for `billing.usage.recorded` with `subject: the account` and a
   period and a quantity. Reusing the same action for a different fact on a
   different subject is a naming collision with a real chance of being read as
   one. And muse's event is per-completion while billing's is per-period.
3. Leave the vocabulary alone and treat this as an exception. Rejected: the
   vocabulary's value is being exhaustive, and "except muse" is how it stops
   being one.

**Recommendation:** option 1. If the manager prefers option 2, the flip is one
word in `muse/src/muse/contracts.py` (`TOKENS_CONSUMED`), one in `cafaye.yml`,
one directory rename here and one catalog row — a **major**, because a published
type's name is never repurposed and the old one has to be deprecated for six
months, not renamed in place.

**Cost of flipping:** cheap in core, a deprecation cycle in every subscriber.

### The account

**Choice:** the payload stays at five fields with no account, and the envelope's
`subject` stays the reserved literal `platform`. muse's v1 auth stub does not
read a token, so there is no account to put in the payload — inventing one would
be a contract that lies in the way D7 does.

**Alternatives:**

1. Leave it. `platform` is honest: there is no single entity yet. The cost is
   real — a consumer cannot attribute the spend, so `billing` cannot invoice from
   this event as things stand.
2. Add `request_id`. The smallest field that makes aggregation possible: a
   consumer can still not say whose money it was, but it can tie cost to a
   request that guard or a caller already knows. Recommended as the *next* field,
   and a **minor** when it lands (a new required field is a minor).
3. Add `account_id`. What a consumer actually wants, and the one muse cannot
   produce today. It is muse's auth work, not core's, and a schema declaring it
   would be a schema requiring a field no publisher emits.

**Recommendation:** option 1 now, option 2 next, option 3 when muse reads a
token. Core's part is to not pretend otherwise, which is what the schema's
description says.

**Cost of flipping:** option 3 is a **minor** here and a large change in muse.

## D10: `billing.subscription.started`'s payload schema no longer describes cafaye ids

**Breaking.** Raised while writing billing's eight payload schemas. Affects
[`schemas/events/billing/subscription/started.schema.json`](schemas/events/billing/subscription/started.schema.json)
and the payload table in
[`docs/event-naming.md`](docs/event-naming.md).

**Choice:** the shipped v0.2 schema is rewritten. It required `subscription_id`
(`^sub_[0-9A-Z]{26}$`), `plan_id` (`^pln_[0-9A-Z]{26}$`) and `account_id`
(`^acc_[0-9A-Z]{26}$`) — a world in which billing holds cafaye-prefixed ids.
billing has no subscriptions table and cannot invent ids it does not have; its
webhook payloads carry the processor's `sub_…`, `cus_…` and `price_…`, and its
own primary keys are bare uuids. The schema now describes what billing emits,
with `processor` and `processor_event_id` on every payload so a consumer can tell
a fact billing knows from a fact billing was told.

**Alternatives:**

1. Rewrite it to reality, as landed. The packet's own rule — "a payload schema
   that guesses a field name the publisher never emits is worse than no schema:
   it is a contract that lies" — makes this the only option that leaves a
   *usable* schema behind. It is also a breaking change to a payload a consumer
   could have generated an SDK from in the four days since v0.2 shipped.
2. Leave the schema as it is and write the valid example with cafaye-prefixed
   ids. Rejected: that is inventing a payload. The example would validate, the
   suite would pass, and every real event billing publishes would fail the
   contract — the worst outcome in this repository, because it is invisible.
3. Loosen the patterns to accept both id vocabularies. Rejected for the same
   reason as **D7**: a schema that accepts everything detects nothing, and a
   consumer still has to try both spellings. It also hides the real decision
   instead of recording it.
4. Deprecate `billing.subscription.started` and ship a new type. Rejected as
   disproportionate: the *type* is not changing and its meaning has not changed.
   Only the payload's field vocabulary was wrong, and only for four days.

**Recommendation:** option 1, with billing told plainly that this is a spec major
and that the consumer obligation is a regenerated reader. Nothing has shipped
against v0.2's version of this schema, so the deprecation machinery exists for
events, not for a schema that was wrong on arrival. If the manager would rather
keep v0.2's text and treat the mismatch as billing's debt, that is option 2's
shape and it should be recorded in `docs/event-outbox.md`'s checklist as "validate
`data` against the payload schema where one exists and the publisher agrees with
it" — which is close to what billing's own contract test does today.

**Cost of flipping:** back to the v0.2 text is one file plus its two examples,
but it re-creates a schema no publisher satisfies. Forward, when billing grows a
subscriptions table, the shape moves again — cafaye `sub_…`/`pln_…`/`acc_…`
alongside or instead of the processor's ids — and that is a second breaking
change. The cheap way to avoid a third is for billing to decide the id question
before the table lands; that is billing's packet, not this one.

## D11: `billing.payment.succeeded` has two payload shapes

Raised while writing billing's eight payload schemas. Affects
[`schemas/events/billing/payment/succeeded.schema.json`](schemas/events/billing/payment/succeeded.schema.json)
and the `billing` catalog row in
[`docs/event-naming.md`](docs/event-naming.md).

**Choice:** the schema declares one `oneOf` over both shapes — invoice-backed
(`invoice_id` + `subscription_id`) and Checkout-backed (`checkout_session_id`) —
so exactly one is present and a consumer never has to guess. Both shapes are
covered by a valid example
(`succeeded.data.json` and `succeeded.checkout.data.json`), checked by
`test_payload_schema_variant_examples_validate` so neither is assumed.

**Alternatives:**

1. `oneOf`, as landed. The honest encoding, and it makes the distinction a
   machine-checked fact instead of a sentence in a description.
2. A new `billing.checkout.completed` type. This is what billing's own
   `cafaye.yml` asks for. It is the cleanest end state — one type, one shape,
   one normaliser — and it costs a catalog row here, one line in
   `Webhooks::StripeEvents.event_type_for`, and a decision about double
   counting: a Checkout session and an invoice for the same charge would both
   fire, so one of them has to be suppressed or a consumer counting settled
   payments counts every signup twice. billing's own DECISION NEEDED flags this
   and this packet cannot resolve it, because suppressing an invoice event is a
   revenue-path decision.
3. One flat schema with every field optional and no discriminator. Rejected:
   `invoice_id` is `null` for a one-off invoice, so "present" and "not null" are
   different questions and a consumer has to get both right. A schema that
   validates both shapes while being unable to tell them apart is the same lie
   as D7's alternative 2.

**Recommendation:** option 1 now, option 2 when billing is ready to make the
double-counting decision. The `oneOf` does not block option 2 — deleting one
branch and its fields is a patch once the type split exists, because no
subscriber has to migrate off a type that never changed.

**Cost of flipping:** option 2 is a new catalog row, a publisher change and a
revenue-path decision. Option 1 → 3 is free and worse; it is only listed because
it is what this schema would collapse into if somebody "simplified" the `oneOf`.

## D12: `metadata` is the one deliberately open object

Raised while writing
[`schemas/events/billing/customer/created.schema.json`](schemas/events/billing/customer/created.schema.json).
Affects that schema, and
[`tests/test_specs.py`](tests/test_specs.py)'s closing rule.

**Choice:** `billing.customer.created`'s `metadata` is `{"type": "object"}` with
no `additionalProperties` constraint, and its description says so in bold. Every
other object in every schema in this repository is closed.

**Alternatives:**

1. Leave it open, as landed. `metadata` is a `jsonb` bag the caller fills; the
   publisher normalises a null to `{}` and writes nothing else. Closing it would
   make the field permanently `{}`.
2. Close it. Rejected: it would be a schema requiring a field that can hold
   nothing, which is worse than an open one because it looks enforced.
3. Drop `metadata` from the schema. Rejected: the publisher emits it on every
   `billing.customer.created`, so a closed schema would reject a real payload.

**Recommendation:** option 1, and the next free-form field gets the same
treatment with the same sentence. The rule AGENTS.md states — close every level,
so an undeclared key is an error rather than a silent no-op — is right about
*known* fields and wrong about a bag whose contents are by definition unknown.
An open field that is named as open is a decision; an open field that is not
named is a hole.

**Cost of flipping:** closing it is one line, and it is a breaking change the
moment any caller puts a key in it — which is why it should not be done after
the first real customer rather than before.
## D13: where is the redaction boundary enforced — the collector, or each service?

Raised while writing
[`schemas/telemetry/redaction.schema.json`](schemas/telemetry/redaction.schema.json)
and [`docs/observability.md`](docs/observability.md). Affects the `enforcedAt`
enum, kit's collector config, and every service's SDK setup.

**Choice:** **the collector is the enforcing chokepoint**; each service's own
SDK allowlist is defence in depth, never the only line. `enforcedAt` is an enum
in the schema with `collector` as the only value a cafaye policy may carry, so
"enforce it somewhere" is not a state a config can express.

**Alternatives:**

1. The collector, as landed. One chokepoint in one process, auditable in one
   place, and a service cannot bypass it by forgetting to configure something.
2. **The service SDK.** Each service's allowlist is the enforcement point, as it
   already is in muse. Rejected as the *only* line: it is six independent
   implementations of a security control, and the failure mode of a control
   implemented six times is that one of the six is wrong and nobody finds out
   until a customer's prompt is in a log store. It also fails the moment a
   service ships an SDK that does not honour the allowlist — which is exactly
   what a self-hoster pointing `*_OTEL_ENDPOINT` at a vendor backend brings, since
   that backend's SDK knows nothing about our policy. **This is the argument that
   decided it:** the escape hatch and the chokepoint are in direct tension, and
   the chokepoint only holds if the escape hatch does not carry the redaction off
   with it.
3. **Both, with equal weight** — the collector re-checks and the service
   pre-checks, and the doc says the boundary is "the intersection". Rejected: it
   sounds stronger and is weaker to reason about. Two controls that must both pass
   have no single answer to "is this leak blocked?", and the debugging story for a
   partial failure is worse than either control alone.
4. **Neither; scrub at the exporter.** Rejected: a scrubber is downstream of the
   leak. It cannot tell a prompt from a stack trace that happens to contain one,
   and muse's own `redaction.py` argues against filters with a bypass — the same
   argument, applied to telemetry.

**Recommendation:** option 1, with the honest caveat recorded in the doc: a
collector-side policy cannot protect data that never leaves the SDK, which is
why the per-service allowlist is not redundant. They are a first line and a last
line, not one line and a spare.

**Cost of flipping:** in core, one enum value and one line in the doc. In **kit**,
it inverts the collector's role from filter to pass-through and every allowlist
moves into six per-language templates. In the services, each one has to be
trusted with the whole boundary. The expensive half is not in this repository —
the same shape as D7 and D10, and the same warning: the flip is cheap in core
and expensive everywhere else, so it is worth deciding before kit builds the
collector rather than after.

## D14: how coarse is `error.type`?

Raised while writing
[`schemas/telemetry/metrics.schema.json`](schemas/telemetry/metrics.schema.json)
and [`docs/observability.md`](docs/observability.md). Affects the `error.type`
definition on all three signals, and the answer to the user's question about one
place to see all errors for the whole system (PLAN.md §7b).

**Choice:** a **low-cardinality class in a bounded, fleet-wide vocabulary** —
snake_case, at most 64 characters, the same shape on every signal. Not a message,
not a stack trace, not a per-service exception class name.

**Alternatives:**

1. The bounded fleet vocabulary, as landed. `provider_auth`,
   `dependency_unavailable`, `rate_limited`, `timeout`, `circuit_open`.
2. **The language's own exception class name** — what muse emits today
   (`error.type = "ProviderAuthError"`). It is free: no mapping table, no
   decisions, and it is what the OTel convention literally suggests ("the
   fully-qualified class name"). Rejected for two reasons, one soft and one
   hard. Soft: it is only *low-cardinality* within one language — add a class and
   you have a new series. Hard: `ProviderAuthError` in Python, `ErrProviderAuth`
   in Go and `ProviderAuthError` in Elixir are one failure in three taxonomies,
   so "one place to see all errors for the whole system" becomes six places that
   need a mapping table to join. That is the user's actual question, and this is
   the only option that answers it.
3. **The HTTP status code.** Free, bounded, already ubiquitous. Rejected: it
   conflates a 503 from a dead provider with a 503 from a dead database, which
   are different incidents with different responders, and it is meaningless for
   an event consumer or a background job that has no status code at all.
4. **A free string.** Rejected: on the metrics side it is the same cardinality
   bomb as `tenant_id`, and on the traces side it is the wall of ungrouped text
   the user asked whether we could avoid.

**Recommendation:** option 1, and deliberately a **narrow** vocabulary — around a
dozen classes covering transport, dependency, policy and internal failures. A
narrow vocabulary means a class is worth alerting on; a broad one means every
value gets its own alert and the grouping key stops grouping.

**Cost of flipping:** in core, one definition per signal and the doc table. In
**muse**, one line: the `error.type` it sets on `muse.provider.call` is
`ProviderAuthError` today, and `tests/test_trace_propagation.py` asserts that
value — so flipping is a code change *and* a test change in another repository.
In the other five, nothing yet, which is the cheapest possible time to decide it.
The real cost is a mapping table somebody has to maintain, and that cost is only
worth paying once; paying it after six services each have their own class names
is what makes it permanent.

**Status: ratified by the manager, and implemented as a closed `enum` rather than
a pattern.** D14 promised "a bounded vocabulary"; core-04 delivered a `pattern`
and a 64-character cap, which bound the *shape* of the value and not the set of
values, so `user_42_email_invalid` validated cleanly on all three signals. The
two open questions D14's own implementation raised are **D18** (which classes)
and **D19** (whether `_OTHER` is in a snake_case vocabulary).

## D15: the span-name form

Raised while writing
[`schemas/telemetry/span-naming.schema.json`](schemas/telemetry/span-naming.schema.json).
Affects every span name in the fleet and kit's six OTel templates.

**Choice:** `<service>.<operation>[.<target>]` — dotted, lowercase, the same
*shape* as the event grammar's `<service>.<entity>.<action>`, with a mandatory
service prefix and a **fifteen-character segment cap**.

**Alternatives:**

1. The dotted cafaye form, as landed. One shape to learn for both events and
   spans; a span name always says which service produced it.
2. **The OTel HTTP convention** — `HTTP GET`, or `{method} {route}`, e.g.
   `GET /v1/users/{id}`. This is what a Grafana user expects to see and what
   every off-the-shelf OTel tool already understands. Rejected: it puts the route
   in the *name*, and a route with an id in it is a cardinality bomb with a `GET`
   attached — it is the first entry in the rejected list. It also has no room for
   a non-HTTP span, and some of the fleet's most interesting work (an outbox
   publish, a breaker decision) is not HTTP.
3. **The OpenInference dotted style** (`openinference.chain.invoke`). Same shape
   as option 1 but names a vendor, and it puts a third party's vocabulary in a
   spec core owns.
4. **A function name** — `get_user`. Rejected in one line: it is what a fleet
   produces when nobody has said, and it is unstable under refactoring, so every
   dashboard breaks when someone renames a function.

**Recommendation:** option 1, and the segment cap is the part worth defending in
review. It is what refuses an interpolated id *without core growing a cafaye-id
pattern to recognise one* — the grammar says nothing about ids, it says no
segment is longer than fifteen characters, and
`usr_01J9Z8QK5M4N7P2R3T6V8W9X0A` therefore cannot be a span name. A pattern
listing our id prefixes would need editing every time identity mints a new
prefix, and would be bypassed by an id format core had not seen.

**Cost of flipping:** every span name in the fleet, every dashboard and alert
built on one, and kit's six templates. The cheap thing about this decision is
that it is cheap *now* — there is almost nothing to rename, because the fleet has
barely started — and that is the whole argument for making it before the first
service is instrumented rather than after the sixth.

## D16: which variable name is the endpoint contract?

Raised while reading muse's `Settings.from_env` against PLAN.md §7b. Affects
[`schemas/telemetry/otel-endpoint.schema.json`](schemas/telemetry/otel-endpoint.schema.json),
`fleet.yml`'s `endpointVariable`, and every service's configuration.

**Choice:** `<SERVICE>_OTEL_ENDPOINT` — uppercase, per-service, derived from the
service name. The shipped collector is that variable's *default value*, and
`required` is a `const: false`.

**Alternatives:**

1. `<SERVICE>_OTEL_ENDPOINT`, as landed. One name to know per service; a
   self-hoster can point one service at their existing backend and leave the rest
   on the collector, which is the whole escape hatch.
2. **The OTel standard names** — `OTEL_EXPORTER_OTLP_ENDPOINT` and
   `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT`, read by every OTel SDK in every
   language for free. **This is what muse actually implements today** (see D17).
   Rejected as the *only* name for one reason: it is global, so pointing one
   service at Datadog and the rest at the collector means two process
   environments rather than one, and a self-hoster's compose file grows a
   per-service override block for every service that differs.
3. **Both**, service-specific taking precedence. The most compatible answer, and
   the one with the most to explain. Rejected because it makes the precedence
   order itself part of the contract, and a contract with a precedence order is a
   contract with a bug report.

**Recommendation:** option 1 as landed, and the drift recorded in **D17** rather
than papered over: muse reads `MUSE_OTEL_EXPORTER_OTLP_ENDPOINT`, PLAN.md §7b
says `MUSE_OTEL_ENDPOINT`, and this spec says `<SERVICE>_OTEL_ENDPOINT`. Three
spellings of one variable in three places is precisely the cross-repo drift
`fleet.yml` exists to catch, and the honest move is to record it rather than
write a spec that quietly disagrees with the one service that ships.

**Cost of flipping:** one constant per service and one line in its settings test.
Cheap in core, cheap everywhere — which is why it should be settled now rather
than by whichever service is instrumented next, since each one will otherwise
pick the spelling it finds in its own neighbourhood.

## D17: muse's endpoint variable, and the two names core now has for it

Raised while transcribing muse into
[`fleet.yml`](fleet.yml) against
[`schemas/telemetry/otel-endpoint.schema.json`](schemas/telemetry/otel-endpoint.schema.json).
Affects muse's `Settings.from_env`, D16, and PLAN.md §7b.

**The fact first, because it is the reason this is open.**
`muse/src/muse/main.py` reads `MUSE_OTEL_EXPORTER_OTLP_ENDPOINT` — the
OpenTelemetry standard spelling — which is also what
`muse/tests/test_resilience_config.py::test_the_tracing_endpoint_is_read_from_the_standard_variable`
asserts, while its neighbour `muse/tests/test_telemetry.py:269` calls it
`MUSE_OTEL_ENDPOINT` in prose. PLAN.md §7b states that "muse already honours
`MUSE_OTEL_ENDPOINT`". **It does not.** Three places, three spellings, and the
code agrees with neither document.

**Choice:** core keeps `<SERVICE>_OTEL_ENDPOINT` (D16), `fleet.yml` records
`MUSE_OTEL_ENDPOINT` for muse **with a note saying which variable muse actually
reads**, and muse is marked non-conforming rather than quietly assumed
conforming. This packet does not change muse — it is a read-only reference and
no service is instrumented here.

**Alternatives:**

1. Record the divergence and rename muse in muse's next packet, as landed.
2. **Flip D16 and adopt the OTel standard names.** muse is then already
   conforming, PLAN.md §7b turns out to have been right about the name, and core
   stops maintaining a cafaye-specific spelling at all. Rejected *here* only
   because it is D16's call and D16 argues for the per-service name on
   self-hoster ergonomics — but it is a live option, and it is the one that makes
   this divergence disappear rather than get paid off.
3. Accept both spellings, cafaye first, as an alias. Rejected: two names for one
   variable is a precedence order, and a precedence order is a bug report (D16).
4. Say nothing and let each new service pick the spelling it finds next door.
   Rejected: that is how six services end up with six names for the one variable
   a self-hoster is told to set, which is the exact failure `fleet.yml` exists to
   catch.

**Recommendation:** option 1, and rule on D16 with option 2 in view — the two
decisions are the same decision seen from two ends. If the manager prefers the
standard names, this entry closes as "not a drift" and the only work is
`fleet.yml`.

**Cost of flipping:** one string in `muse/src/muse/main.py` and one line in
`muse/tests/test_resilience_config.py`, plus this entry and `fleet.yml`'s note.
Cheap in core and cheap in muse, which is exactly why it should be settled now
rather than after three more services have copied the OTel spelling out of
muse's code.

## D18: which classes are in the error vocabulary?

Raised while implementing D14 as an `enum` in
[`schemas/telemetry/traces.schema.json`](schemas/telemetry/traces.schema.json),
[`metrics.schema.json`](schemas/telemetry/metrics.schema.json) and
[`logs.schema.json`](schemas/telemetry/logs.schema.json). Affects the same
`error.type` definition on all three signals, the table in
[`docs/observability.md`](docs/observability.md#errortype), and the class muse
maps onto.

**Choice:** twelve classes plus `_OTHER`, grouped by **who acts** rather than by
which component failed:

- *the caller* — `invalid_request`, `policy_denied`
- *a third party* — `provider_auth`, `provider_rejected`, `rate_limited`
- *the wire* — `timeout`, `connection_failed`, `circuit_open`
- *a dependency* — `dependency_unavailable`, `conflict`
- *nobody, on purpose* — `cancelled`
- *us* — `internal_error`

The test for whether a class earns its place is D14's: **is this class's rate
worth an alert on its own?** Two consequences of that test are worth naming,
because they are the two places a vocabulary usually grows without deciding to:

- **`timeout` is one class, not one per dependency.** What timed out is the
  span's name and its attributes. A class per target — `provider_timeout`,
  `database_timeout`, `vault_timeout` — is how a twelve-value list becomes a
  hundred and the grouping key stops grouping.
- **`circuit_open` is a class even though nothing failed.** It records our own
  breaker refusing to call, which is otherwise invisible, and it separates "the
  vendor is down" from "we stopped trying".

**Alternatives:**

1. The twelve as landed, grouped by responder.
2. **A class per dependency.** `provider_timeout`, `database_timeout`,
   `vault_timeout`. Rejected: it is the vocabulary version of the span-name
   mistake D15 refuses — the thing that went wrong is already on the span, and
   repeating it in the class is one more dimension multiplying against every
   other one for no new question answered. It also makes the class list a list of
   cafaye's own services, so every new service edits core.
3. **A wider list, one class per exception shape.** `configuration_error`,
   `serialization_error`, `data_invariant`, `deserialization_error`. Rejected on
   D14's own criterion: each is a few occurrences a month, each would get its own
   alert, and a class you would page on at a rate of two a month is a class you
   would stop reading. They collapse into `internal_error`, which must trend to
   zero anyway.
4. **Per-service vocabularies**, each service's own list. Rejected: it is D14's
   rejected option 2 with a different spelling. It is also unenforceable by this
   repository, which is the problem: a class list per service is a list nobody
   compares.

**Recommendation:** option 1, and the *test* rather than the list is the part
worth defending in review — "is a rate worth an alert on its own?" is answerable
in a review, "does this class feel right?" is not. The bound is asserted
(`MIN_ERROR_CLASSES`/`MAX_ERROR_CLASSES`, 10–16) because "around a dozen, do not
pad it" is a judgement nobody makes twice the same way under deadline, and an
unbounded list is a list that grows one class per incident.

**Cost of flipping:** one `enum` per signal (three copies, deliberately
duplicated so a service's SDK setup can load one file alone), the doc table, and
the muse mapping. Adding a class is the cheap direction and is deliberately
cheap; **removing** one is not, because a class that has been emitted is data
someone has already grouped by, so a rename is a broken dashboard and a silent
gap in historical comparison. That asymmetry is the argument for settling the
list before kit builds the collector rather than after the first alert fires.

## D19: does `_OTHER` belong in a snake_case vocabulary?

Raised by the same work as **D18**, from a tension in the packet: include the
OTel well-known fallback "if it fits the shape". It does not — `_OTHER` is
upper-case with a leading underscore and cafaye's shape is
`^[a-z][a-z0-9]*(_[a-z0-9]+)*$`. Affects the `pattern` in
[`schemas/telemetry/traces.schema.json`](schemas/telemetry/traces.schema.json)
and its two copies, and whether the vocabulary has an escape hatch at all.

**Choice: include it, as the one documented exception to the shape.** The shape
becomes `^([a-z][a-z0-9]*(_[a-z0-9]+)*|_OTHER)$`, so every class but the fallback
is snake_case and the fallback is spelled the way the ecosystem spells it.

**Alternatives:**

1. Include it, as landed. The argument is about what a closed enum does under
   pressure: **a closed set with no escape hatch gets widened.** The first real
   failure that does not fit — a database driver error, a language-specific
   runtime failure — arrives during an incident, and the cheapest available
   action is to add a class rather than to file a spec change. A widened enum is
   how `_OTHER` becomes a permanent value nobody reads, because by then it is
   easier to keep using it than to find the class that was added for the case in
   front of you. Carrying the fallback is how instrumentation is never forced to
   invent a class. And the value of the alert does not depend on being rare: an
   alert on `_OTHER` is an alert that **this service has not classified its own
   errors**, which is actionable, owned, and specific.
2. **Omit it.** The vocabulary stays uniformly snake_case, and a service with a
   genuinely unclassifiable failure has two bad options: drop the class, which
   makes a status-error span that fails the obligation, or add a class, which is
   the widening from option 1 with an extra step. The tidiness of the shape is
   not worth either.
3. **Rename it** — `other`, or `unclassified`. Rejected: it forks a Stable OTel
   value. A backend someone at cafaye has never heard of would show `other` and
   `_OTHER` as two different classes for the same event, which is precisely the
   six-taxonomies failure D14 rejects.
4. **A per-service escape hatch** — a cafaye-specific value outside the enum,
   permitted by a `not`-guarded escape. Rejected: it is a free string with a
   friendly name, and it is the hole this packet exists to close.

**Recommendation:** option 1. The shape compromise is real and the test asserts
it explicitly — `_OTHER` is the only member allowed to break the shape, and the
vocabulary has no other member that does — so a later commit cannot quietly add a
second exception without a test failing.

**Cost of flipping:** in core, the pattern in three files, the doc, and the
`test_the_error_class_vocabulary_is_narrow_and_closed` exemption. Elsewhere it
costs a **no-op path that is not a no-op**: every service that would have used
`_OTHER` has to pick a class at the moment it has none, which is the widening
happening per-service and untracked. That is the expensive half, and it is why
the cheap half should be decided now.

## D20: kit's `language: none` job runs the gate on an unpinned interpreter

Raised by **core-06**, which adopted kit's reusable workflow and found that
core fits none of kit's eight `language` values cleanly. `none` is the documented
option for a repository with no service manifest, and it is the only one whose
job can be green here — but its job is four steps long and **installs no
interpreter**: it is `actions/checkout`, an existence check for
`tests/validate.sh`, and `bash tests/validate.sh`. So the `kit` job in
[`.github/workflows/ci.yml`](.github/workflows/ci.yml) runs core's 92 tests on
whatever Python `ubuntu-latest` happens to ship, which is a floating build by
the letter of the rule that says a suite that passes today must not depend on
which image was cached.

The seven language jobs cannot take this repository: each opens by reading a
manifest and installing from it, and `uv sync --frozen` exits 2 with "No
pyproject.toml found" in a repository that has never had one and should not. The
gap is not that kit's jobs are wrong; it is that kit models *service* repositories
and (via `none`) *kit itself*, and core is a third shape — a repository with a
real suite and a real pin, and no service at all.

**Choice: accept the disclosure, and let `gate` carry the pin.** The `kit` job
proves two things the companion job cannot — that the `uses:` line resolves, and
that the gate bootstraps from nothing on a clean runner — and it says in its own
name that it is not the pinned claim. The `gate` job reads the pin from
`mise.toml` at run time and **asserts** the interpreter that arrived against it.
The floating interpreter is disclosed in the README, in the CHANGELOG and in the
workflow file rather than left to be inferred from a green tick.

**Alternatives:**

1. Accept the disclosure, as landed. Cheapest, and honest because the claim is
   named rather than assumed. The cost is that two jobs run the same 92 tests on
   two different interpreters, which is the kind of redundancy that invites
   "delete the redundant one" from someone who has not read why it is there.
2. **Have kit read `inputs.versions` in the `none` job.** A two-line change to
   kit — `actions/setup-python` with the pin the input already carries — and it
   makes `none` correct for every configuration-only repository, not just this
   one. It also removes the duplicate run. This is the option core would
   recommend, and it is a kit packet, not a core one.
3. **A ninth `language` value** — `spec`, for a repository with a suite, a pin
   and no manifest. Honest about the third shape, and the most work: kit's gate
   requires a Dockerfile, a `bin/prime` and a `[tools]` pin per language, and core
   ships no Dockerfile because it builds nothing.
4. **Make the gate refuse to run on an unpinned interpreter.** Rejected: the
   `kit` job would go red on every runner whose default Python is not 3.14,
   which means the adoption PR is never green and the option cannot be chosen
   without also choosing 2 or 3.

**Recommendation:** option 1 now, and open option 2 as a kit packet. Option 1 is
the only choice that can be made without blocking on another repository, and it
is fully reversible: if kit adds the `setup-python` step, core deletes nothing —
the assertion in `gate` is what makes the pin load-bearing, and it stays either
way.

**Cost of flipping:** near zero in core, and that is the point of taking it in
this order. Moving to option 2 is a kit PR plus deleting the disclosure text in
three places. Moving to option 3 means kit grows a language it must then hold a
Dockerfile and a primer for, and core would have to ship an image for a
repository that builds nothing — which is the one thing core's AGENTS.md rules
out twice.

## D21: a breaking schema change has no re-vendor fan-out step

Raised by the same packet, from the question core-06 was asked directly: core is
the repository whose schemas other services **vendor**, so if a schema changes,
services have to re-vendor. Nothing in core-06 changes a schema, so nothing
triggers it — but the honest answer to "should this packet have a fan-out step?"
is that **it should not, and no packet should invent one quietly**. Today a
breaking change lands in the CHANGELOG's breaking section and relies on each
service noticing on its own schedule.

What exists: `CHANGELOG.md` records the break under a heading that says who it
breaks and why, and `muse` has a core-parity CI job that checks its vendored copy
against a pinned `CORE_REF` — which catches drift on muse's push, not on core's.
So the detection is per-service, the trigger is per-service, and nothing tells a
service owner that a fan-out is owed. That is a real gap with no owner.

**Choice: write the gap down and do not build the mechanism here.** A fan-out
step in core would have to reach into six repositories, choose a moment to push
to each, and decide what a service does when its vendored copy no longer matches
— and every one of those is a decision this repository does not own. So this is
recorded as an open question with its alternatives argued, and the cheap first
step (a spec'd `coreSpecRef` field, or a changelog machine-readable block) is
left for the packet that is actually about releases.

The nearest thing core already owns is
[`schemas/fleet.schema.json`](schemas/fleet.schema.json), which is what makes
`fleet.yml`'s per-service `sourceCommit` checkable: core already records *what
revision of a service a fact was read at*, asserted to be a full 40-character
SHA by `test_fleet_records_a_source_commit_per_service`. That is provenance in
exactly the wrong direction — it says what core knows about each service — and
what is missing is the record of what each service knows about core.

**Alternatives:**

1. Record the gap, as landed. Nothing is invented; the question is visible and
   numbered, which is the state AGENTS.md asks for. The cost is that the gap
   stays a gap until someone is given the time to close it.
2. **A machine-readable breaking-change block in `CHANGELOG.md`** — a fenced
   block listing the changed `$id`s and the new spec version. Cheap, lives in
   core, and a service can consume it without core pushing to anything. It is
   still a fan-*out* with no fan-*in*: it tells a service what changed, not that
   it must act, so each service still needs a job that checks.
3. **core pushes the re-vendor.** Rejected outright: core would gain write
   access to six repositories, and a spec repository that can change a service's
   working tree is a runtime with opinions, which AGENTS.md rules out in the same
   sentence it uses for the collector.
4. **Nothing, indefinitely.** Rejected: it is the status quo, and "no decision"
   is the one outcome AGENTS.md calls the only real failure.

**Recommendation:** option 1, with option 2 as the first step of whichever packet
closes it. Option 2 is small and does not require cross-repository write access,
so it is reachable without the decision this one is waiting on.

**Cost of flipping:** option 2 is additive — a block in a document, and a schema
if it becomes one, with its own test. Nothing about core-06's CI work changes
either way, which is why it is safe to record rather than build.

## D22: should core's suite assert `format: uri`, which no installed checker implements?

Raised by **core-07**, by accident and then on purpose. The contract-test harness
evaluates the keywords core's schemas use with the standard library alone, and
`test_the_harness_checks_the_format_vocabulary_core_uses` asks which `format`
values the harness decides. The answer is `date`, `date-time`, `email`, `uri` and
`uuid` — and `jsonschema`, in core's own venv, registers checkers for all of
those **except** `uri`. So
[`schemas/telemetry/otel-endpoint.schema.json`](schemas/telemetry/otel-endpoint.schema.json)'s
`format: uri` on the collector's default endpoint is a constraint that
`bin/prime` does not assert, and a document that is not a URI at all passes it
today.

This is not new and it is not the harness's fault.
[`tests/requirements.txt`](tests/requirements.txt) already carries a note saying
exactly this about `date-time` — "jsonschema only checks the date-time format
when one of these is present; without it an RFC3339 assertion in the suite would
silently pass everything" — and pins `rfc3339-validator` because of it. The same
argument applies to `uri` and nobody made it. The blast radius is small: the
field sits beside `pattern: "^https?://"`, so a value that is not a URL is
usually rejected anyway. The point is not the field; it is that a rule nobody
asserts is a comment, and core's own rule says a rule not in `schemas/` is not a
cafaye rule — this one is in `schemas/` and is still not a rule.

**Choice: do not add a dependency, and make the gap a named, tested fact
instead.** `jsonschema` needs `rfc3987-validator` to assert `uri`, and
`tests/requirements.txt` is deliberately minimal — "no runtime libraries, no
services, no dependencies beyond `tests/requirements.txt`" is AGENTS.md's line
and a fifth package for one keyword is not worth arguing about. So the harness
*does* check `uri` (it costs five lines and the standard library has what it
needs), and the divergence is stated in
[`docs/contract-harness.md`](docs/contract-harness.md) and asserted here. The
harness is the stricter of the two, deliberately: it is the thing a service runs
in CI, and a service should not get a weaker check than the spec repository
gives itself.

**Alternatives:**

1. Leave it, named and tested, as landed. No dependency, and the vacuity is
   visible in two documents and in this decision rather than invisible in a
   schema. The cost is that `bin/prime` is still weaker than it reads.
2. **Add `rfc3987-validator` to `tests/requirements.txt`.** One line, and
   `format: uri` starts being asserted everywhere — in `bin/prime`, in the
   harness's equivalence test, in every service that vendors the schema. It is
   the correct fix and the only argument against it is the dependency count,
   which is a policy rather than a fact.
3. **Drop `format: uri` from the schema** and rely on the `pattern` beside it.
   The smallest change and it loses nothing today — but it deletes a constraint
   rather than enforcing one, which is the wrong direction for a repository whose
   rule is that a constraint is a rule.
4. **Replace `format: uri` with a pattern** covering the shapes a collector
   endpoint can take. No dependency, fully asserted, and a worse rule: a pattern
   for "a URL" is a worse statement of "a URL" than `format: uri` is.

**Recommendation:** option 2, in a packet about dependencies, and option 1 until
then. Option 1 is fully reversible in one line and loses nothing while it stands,
which is exactly the property that makes it safe to leave open. If the manager
decides option 2, the only change here is removing the "deliberately stricter"
sentence from [`docs/contract-harness.md`](docs/contract-harness.md) — the harness
keeps checking `uri` either way.

**Cost of flipping:** one line in
[`tests/requirements.txt`](tests/requirements.txt), and one sentence in
[`docs/contract-harness.md`](docs/contract-harness.md). Nothing in
[`harness/cafaye_contract.py`](harness/cafaye_contract.py) changes, and nothing
in a service does.

## D23: do the OpenAPI conventions and the cross-field manifest rules become a JSON Schema?

Raised by **core-07** from the thing its own rule inventory turned up. core's one
rule is that a rule not in `schemas/` is not a cafaye rule. The harness enforces
seventeen rules, and **exactly one of them** is a JSON Schema constraint. The
other sixteen are in code — five cross-field manifest rules that
[`docs/manifest-conventions.md`](docs/manifest-conventions.md) lists under "Rules
the schema cannot state", five OpenAPI conventions that
[`docs/openapi-conventions.md`](docs/openapi-conventions.md) says in its own
words are "review-enforced, like every other convention here" until a future
`caf contract lint` lands, and six that are facts about a filesystem or a pin
rather than about a document at all.

Some of the sixteen can never be a schema. A path being under a `/vN` prefix is
a property of an OpenAPI document, and there is no JSON Schema for "an OpenAPI
document" that is worth writing — one could be written, and it would be a
validator for a specification core does not own. A digest is not a document. But
the *cross-field manifest* rules are a different matter: they compare two
properties of one instance, JSON Schema cannot do that directly, and it is a real
question whether `dependentSchemas` plus `$data` (a draft-07 extension) or a
generated schema per rule is the right answer, or whether "documented, named,
inventoried and tested in one place" is the right answer and the schema would be
a worse place.

**Choice: do not decide it here, and do the step that is not the decision.** The
harness makes each of the sixteen rules **executable, named, inventoried and
tested** — `harness/rules.json` says which document each one lives in,
`test_the_rule_inventory_says_where_every_rule_lives` checks that the document
and the heading exist, and `harness/tests/self_test.sh` proves each of the
seventeen can go red. A manager can now see the sixteen as a list and decide,
which was not possible before core-07: the rules were in six documents and in
`caf`'s Go package, in two languages, and `caf` had implemented three of the six
and said so in a comment. **Turning a rule executable is a strictly smaller step
than turning it into a schema, and it is the one that unblocks the decision
rather than pre-empting it.**

**Alternatives:**

1. Leave the rules in code, inventoried and tested, as landed. Cheapest, and it
   is already the step that was missing. The cost is that a rule's home is a
   Python function, and "in `schemas/`" stays true for one rule out of seventeen.
2. **A JSON Schema for OpenAPI documents** — `schemas/openapi.schema.json`, with
   `pathPattern`, `info.version` and the prefix rules as constraints over the
   parsed document. Everything the harness checks about a document would move into
   `schemas/` and the harness would carry one rule instead of five. The cost is
   a schema for a specification core does not own, which will need updating when
   the OAS moves, and `openapi.paths-are-versioned` is awkward to express over
   *path keys* rather than values.
3. **Generate per-rule schemas** from a table, for the cross-field manifest rules
   only. The rules become data. The cost is a code generator in a repository whose
   AGENTS.md says a change needing a runtime belongs in `caf`, and a manifest
   validator that is three layers deep before it says "not this service's name".
4. **`dependentSchemas` per rule**, with each rule as a subschema guarded by the
   presence of the fields it reads. No generator, and it lands inside
   `schemas/`. The cost is that five rules that read "the manifest as a whole"
   become five conditional subschemas, and the schema stops being readable as a
   description of a manifest.

**Recommendation:** option 1 now, and option 2 as the packet that actually
reaches the question. Option 1 is not a deferral dressed as a decision: it is
the only option under which the manager can make this decision at all, because
the list did not exist a week ago. If the manager wants the OpenAPI rules in
`schemas/`, option 2 is a clean, self-contained packet and the harness gets
*smaller*, not bigger.

**Cost of flipping:** low and local. Every rule has one named function and one
inventory entry, so moving a rule is deleting a function and adding a constraint
— and the inventory is written so that "this rule now lives in a schema" is a
one-line change with a test that checks it.

## D24: the event catalog and the spec version are documents, not data

Raised by **core-07**, by the two rules the harness has to implement that nobody
had costed. core publishes the set of event types that exist as a markdown table
in [`docs/event-naming.md`](docs/event-naming.md), and its own spec version as
prose in [`CHANGELOG.md`](CHANGELOG.md). The harness therefore **parses a
markdown table** to answer "does this consumed type exist in the catalog", and
cannot answer "is this `core:` constraint satisfied by the core it is reading" at
all, because there is no version to compare against.

Parsing the document is the right call *today* — the document is the spec, and a
harness that shipped its own copy of the catalog would be a second catalog whose
drift from the first is invisible. That is the same argument as
[`docs/event-outbox.md`](docs/event-outbox.md) not shipping an implementation, and
it is why `caf` says the same thing about the catalog in its own
`internal/contract/doc.go`: "until core publishes it as a machine-readable file,
a linter can only check a repository against itself." The cost is that the
harness is now a **second reader of a markdown table**, and a reader that has to
be maintained in a spec repository is exactly the thing
`test_no_open_decision_callouts_remain_in_the_docs` exists to prevent elsewhere.

**Choice: read the document, and record the two facts as owed.** The harness
reads the table, `test_the_harness_evaluator_agrees_with_jsonschema_on_every_example`
and the reader's own tests keep it honest, and the `core:` constraint rule is
listed in `harness/rules.json` under `notEnforced` with the reason — "core
publishes no machine-readable spec version, so there is nothing on either side of
the comparison". Publishing `schemas/catalog.json` and a `specVersion` are core
changes, not harness changes, and a worker should not invent a new file in
`schemas/` while a re-vendor fan-out is still undefined
([D21](DECISIONS.md#d21-a-breaking-schema-change-has-no-re-vendor-fan-out-step)).

**Alternatives:**

1. Read the document, as landed. No new file in `schemas/`, so no re-vendor
   obligation, and the catalog cannot drift from the table because there is only
   one copy. The cost is a markdown parser in the harness and a `core:`
   constraint nobody checks.
2. **Publish `schemas/catalog.json`**, generated from `docs/event-naming.md` and
   asserted equal to it by a test — the same "a doc and its schema are the same
   contract written twice" pattern core already uses for the manifest and the
   event-type pattern. The harness reads the data file and the table stays the
   spec. The cost is a second file under `schemas/`, which every vendoring
   service now has to re-vendor, and that is precisely the fan-out
   [D21](DECISIONS.md#d21-a-breaking-schema-change-has-no-re-vendor-fan-out-step)
   says has no owner.
3. **Publish the spec version in `schemas/`** — `schemas/spec.json` with
   `{"version": "0.3.0"}` — and resolve the `core:` constraint against it. Small,
   self-contained, and it closes a real gap: a service can then check that it was
   written against the core it is being tested against, which nobody can do today
   in any language.
4. **Both, in one file.** `schemas/catalog.json` carrying the version alongside
   the types. One file to vendor rather than two, at the cost of a file that is
   neither a schema nor a document and so has no obvious home in a repository
   whose rule is that rules live in `schemas/*.schema.json`.

**Recommendation:** option 3 first, and option 2 only after
[D21](DECISIONS.md#d21-a-breaking-schema-change-has-no-re-vendor-fan-out-step) has
an owner. The spec version is one small file that closes a check nobody can
perform today, and a new file under `schemas/` should not land while the
obligation to re-vendor one is undefined — that ordering is the whole of the
recommendation. Option 2 is right and premature, and the harness reading the
document is what makes it safe to be premature.

**Cost of flipping:** the harness's `event_catalog` function becomes a `json.load`
and the `notEnforced` entry for the `core:` constraint becomes a rule. Both are
inside one function and one inventory entry each, and
`test_the_harness_yaml_reader_refuses_a_named_list_of_core_documents` stops being
the place where "we read a document instead of data" is written down.

Raised by **core-07** from the harness's first run against the real fleet, and
this is the only one of the four open decisions that came from *running* the
thing rather than from building it. Pointing
[`docs/contract-harness.md`](docs/contract-harness.md)'s subject at the eleven
real service repositories produced exactly one class of finding that turned out
not to be a service's fault:

    FAIL openapi.paths-are-versioned openapi/v1.yaml: paths -> /healthz
    FAIL openapi.paths-are-versioned openapi/v1.yaml: paths -> /readyz

in `identity`, `darkroom` and `pantry`. All three document their two probes
alongside their versioned paths. `courier` does the opposite and says why in its
document header: "`/healthz` and `/readyz` are not in the document and are not
going to be. They run before auth, routing and the rest of the platform exist,
no customer codes against them, and the document's header says so." `muse`'s
`tests/test_openapi.py` asserts the same thing as a rule: "the probe endpoints
are not in the contract".

So the fleet has two opposite, deliberate, documented practices — and
[`docs/openapi-conventions.md`](docs/openapi-conventions.md) does not say which
one is right. Its checklist says "Path under `/v1`" with no exception, and its
"Versioning" section says "Every path is prefixed". Meanwhile
[`docs/observability.md`](docs/observability.md) and
[`schemas/telemetry/probes.schema.json`](schemas/telemetry/probes.schema.json)
say a great deal about the two probes, and neither mentions the OpenAPI document
at all. **The rule the harness enforces is real and correct; the spec is silent
about the case it lands on, and the harness is reporting the silence.**

**Choice: do not decide it here, and let the harness keep reporting it.** A
worker does not get to decide whether core's HTTP contract includes health
probes — that is a spec question with a customer-visible answer, and the three
services that document them are not wrong on the evidence available to them. So
the rule stands as written, the three services are reported as non-conforming,
and the question is numbered here. The alternative — quietly widening the rule to
exempt two paths — would be resolving a manager's decision inside a harness, and
`harness/rules.json`'s `notEnforced` block exists so that anything like it is
written down rather than done.

**Alternatives:**

1. Record the gap, as landed. The rule is unchanged, three services are red
   against it, and the question is visible. The cost is that a red build in
   three repositories has no fix in core yet, which is the state that makes a
   manager want to decide.
2. **Exempt `/healthz` and `/readyz` from the prefix rule**, stated in
   `docs/openapi-conventions.md` next to the versioning section and enforced as
   a named exception in `harness/rules.json`. It matches two services and
   contradicts three. The cost is that an unversioned path is now a *sanctioned*
   one, and `guard`'s routing prefix and the SDK generators both read the same
   document — a generated client would gain a health-check method.
3. **Require the probes to be documented**, which is the other two services'
   practice, and change the two that do not. The cost is that an SDK generated
   from the document carries `/healthz`, and a customer can now depend on a probe
   that exists before auth, routing and the platform do.
4. **Leave it to each service, and say so** — no rule, no finding, and a note in
   `docs/openapi-conventions.md` that the document's contents are the service's
   decision. The cost is that the two practices stay divergent with nothing
   recording that they were chosen, which is the drift
   [`docs/event-naming.md`](docs/event-naming.md) spends its catalog preventing
   for event types.

**Recommendation:** option 2, and option 1 until it is decided. Option 2 matches
the argument `courier`'s header and `muse`'s test both make independently — a
probe is infrastructure, not contract — and an infrastructure endpoint under a
version prefix implies a stability promise about a route that runs before the
platform does. If the manager prefers option 3, it is a one-sentence change to
`docs/openapi-conventions.md` and three manifests, and nothing in the harness
changes; if option 4, the harness drops one rule and `harness/rules.json` loses
one entry.

**Cost of flipping:** one sentence in
[`docs/openapi-conventions.md`](docs/openapi-conventions.md) and one rule in the
harness — either a named exemption inside `openapi.paths-are-versioned` or its
deletion. The three services' manifests do not change under options 2 and 4, and
do under option 3.
## D26: do the cafaye fields live inside the Sloth document or in a cafaye document kit converts?

Raised while writing the SLO spec. Affects
[`schemas/telemetry/slo.schema.json`](schemas/telemetry/slo.schema.json),
[`examples/valid/telemetry/slo.yaml`](examples/valid/telemetry/slo.yaml) and
every `slos/*.yaml` a service will write.

The chosen artifact is a Sloth `prometheus/v1` file, because Sloth's validator is
a single static binary that walks a directory with no cluster and no Docker
daemon and because its SLI is two PromQL strings — the one representation all six
languages can be checked against without a Go or Rust parser. What core adds on
top of Sloth is `tier`, `period`, `labels` and `sli.catalogEntry`, and those four
fields are the question: **Sloth's YAML loader may or may not tolerate keys it
does not know, and core cannot find out offline.**

**Choice: the cafaye fields live inside the Sloth document**, and
`additionalProperties: false` decides what may appear in it. `docs/slo.md` and
the schema's own description say so.

**Alternatives:**

1. **One document, cafaye fields inside it**, as landed. The service commits one
   file, `sloth validate -i slos/` reads it, and the harness checks the same
   bytes. It relies on Sloth's loader ignoring the four keys it does not know.
2. **A cafaye document kit converts** — `slo.cafaye.yml` declares tier, period and
   labels, and kit emits `slos/<service>.yaml` for Sloth. Every field is one
   document with a schema that Sloth has never seen, and the strict-loud question
   disappears. The cost is two artifacts per service, a generator nobody has
   written, and a second copy of the SLI composition to keep in step.
3. **The cafaye fields live in a sidecar per SLO** (`slos/<service>.tier.yml`).
   Cheapest to make Sloth-compatibility certain, and it splits one fact across
   two files: an SLO with a tier in one file and an objective in the other is a
   mismatch nothing checks.

**Recommendation:** option 1, with option 2 as the fallback **only if** the first
`sloth validate` run against a real declaration reports an unknown key. The
evidence for option 1 is that Sloth resolves its spec with a non-strict
`yaml.Unmarshal` — which is how `--extra-labels` and the multi-file form work at
all — but core could not confirm it without network access, and an unverified
assumption about another project's parser is not something to bury in a spec.

**Cost of flipping:** one commit. `slo.schema.json` moves to describe a cafaye
document, the example moves with it, and kit gains a four-line transform that
strips the cafaye keys before `sloth validate`. The harness reads whichever
document the schema describes and none of the eight rules change. The window
catalog and the SLI catalogue are untouched either way.

## D27: the burn factors come from a 30-day budget and the period is 28 days

Raised by the arithmetic in packet core-08's own brief. Affects
[`schemas/telemetry/slo-windows.schema.json`](schemas/telemetry/slo-windows.schema.json),
`period` in [`schemas/telemetry/slo.schema.json`](schemas/telemetry/slo.schema.json),
and [`docs/slo.md`](docs/slo.md).

The rulings are: 14.4 / 6 / 3 / 1 at 5m+1h, 30m+6h, 2h+1d, 6h+3d, with the
arithmetic published as `14.4 = 0.02 x 720h`; and a 28-day period, not 30. **Those
two do not agree.** 720 hours is thirty days. Two percent of a 28-day (672-hour)
budget is **13.44**, so the workbook's factors — which are also Sloth's shipped
defaults — are about 7% conservative under this spec: the fast-burn alert fires
slightly *earlier* than the workbook intends.

**Choice: implement both as ruled.** 14.4 and `period: 28d`, and
`test_the_window_catalog_is_the_workbooks_numbers` asserts the workbook's
arithmetic, the 28-day arithmetic, **and the direction of the gap**, so the
inconsistency cannot quietly become a number nobody recomputed.

**Alternatives:**

1. **As landed** — the workbook's numbers, a 28-day period, ~7% conservative.
   Zero migration cost, and it matches what Sloth does by default, so an operator
   who has read the Sloth documentation sees the numbers they read.
2. **Recompute for 28 days** — 13.44 / 5.6 / 2.8 / 0.933. Each factor is
   `fraction x 672`, so every alert matches the budget it is measured against
   exactly. The cost is that the fleet's numbers differ from the published
   workbook's and from Sloth's defaults, and 0.933 is a threshold nobody can
   remember.
3. **Go back to a 30-day period.** Reverts R3, and loses the reason for it: four
   weekends in the window rather than 4.3, so the same weekend maintenance costs
   the same fraction of the budget every month.

**Recommendation:** option 1, until an operator notices. The error is 7% in the
safe direction — an alert that fires a little early rather than a little late —
and option 2's 0.933 is a number that will be "corrected" by the next person who
reads it as a typo. If the manager prefers exactness, option 2 is eight `const`
values and one paragraph, and `test_the_window_catalog_is_the_workbooks_numbers`
is the test that has to change with them.

**Cost of flipping:** eight numbers in
`slo-windows.schema.json`'s `prefixItems`, the arithmetic in `docs/slo.md`, and
the two constants in `tests/test_specs.py`. No service is affected: nothing
declares an SLO yet.

## D28: may core's gate take the `sloth` dependency?

Raised by packet core-08. Affects [`docs/slo.md`](docs/slo.md),
[`harness/rules.json`](harness/rules.json)'s `notEnforced`, and CI.

Ruling R1 makes Sloth the artifact because `sloth validate -i <dir>` is the one
validator that needs no cluster and no Docker daemon. That is true of the tool
and not of the *installation*: it is a Go binary, and core's gate would have to
fetch and build it.

**Choice: not taken.** The harness implements the checks that matter — the SLI
composition, the metric and label allowlists, the two denylists — in the standard
library, and `docs/slo.md` gives the pinned command for a service that has
network. `rules.json`'s `notEnforced` records, in the repository's own words,
what is left: PromQL *grammar*.

**Alternatives:**

1. **Not taken**, as landed. `bin/prime` stays a venv and four PyPI packages on
   first run; a Go toolchain never enters a spec repository; an air-gapped runner
   is unaffected. The cost is that a query that is the canonical *string* but
   invalid PromQL is not caught by core — `slo.sli-canonical` compares composition
   and says nothing about the grammar.
2. **Pin a released Sloth binary and download it in CI**, with the version in
   `tests/requirements.txt` next to the four PyPI packages. Real validation on
   every gate. The costs are that the gate needs the network for a tool rather
   than for a library, that the pin has to be bumped deliberately (a Sloth
   upgrade can change what "valid" means), and that every contributor's first
   `bin/prime` would depend on a Go release being reachable.
3. **A container image for the check**, run by a CI step that has Docker. It is
   the most honest gate and the least portable one, and it contradicts
   `docs/contract-harness.md`'s "no cluster, no daemon" argument for the harness.

**Recommendation:** option 1, and option 2 in a *service's* CI rather than
core's — which is where `sloth validate` already belongs, and where a network and
a Go toolchain are ordinary. Core's contribution is the composition check, which
is stricter about shape than Sloth is and is the part six languages get wrong.

**Cost of flipping:** one CI step, one line in `tests/requirements.txt`, and a
pinned version to keep in step. If the manager rules for option 2, this decision
moves to the CHANGELOG's decision table and `notEnforced` loses its third entry.

## D29: which tier does each of the seven services get?

Raised by packet core-08's boundary: the spec says the tier alone decides whether
a page is generated, and no service declares an SLO yet, so nobody has chosen a
tier. Affects every `slos/*.yaml` the next packet writes, and
[`docs/slo.md`](docs/slo.md)'s tier table.

The derivation is mechanical and tested — given a tier, the schema produces the
two alert switches. What is not decided is **which tier each of the seven
services gets**, and that is a judgement about how much of a self-hoster's
product stops working when each service stops working.

**Choice: not built, and not decided.** Packet core-08 was told not to write SLOs
for the seven services, and a tier without an SLO behind it is a number with
nothing to page on.

**Alternatives:**

1. **Decide it now, from the architecture.** `identity` and `muse` are the only
   services a private product cannot run without, so they are `high`; `billing` is
   `low` because an invoice can be recomputed tomorrow; `courier` is `low` for
   the same reason; `darkroom` and `guard` are `none` until something depends on
   them. The cost is that this is a guess about a self-hoster's product made in a
   repository that has never been installed by one.
2. **Decide it per deployment.** The tier ships as configuration in the deployed
   `cafaye.yml` rather than in the committed SLO. Honest for a self-hoster — the
   same build can be `critical` for one cafe and `none` for another — and it
   breaks the whole packet's central claim, that the tier *alone* decides and is
   machine-checked, because a value that varies per deployment is a value the
   schema cannot pin.
3. **Default every tier to `low` and let the first real incident raise it.** Every
   SLO gets a ticket and no SLO gets a page, which is the safe default for alert
   fatigue and the useless default for detection.

**Recommendation:** option 1, in the packet that writes the SLOs, with the tiers
written into each service's committed declaration and stated in
[`fleet.yml`](fleet.yml)'s telemetry block. The packet that writes them is the
first one to meet a real self-hoster's traffic, and a tier guessed from an
architecture diagram is the same shape as an objective guessed from a dashboard.

**Cost of flipping:** one `tier:` line per SLO, and the alert switches follow
from the schema. There is nothing to migrate, which is the property that makes
option 2 tempting and wrong.
## D30: the gate declaration names an argv, and the checker runs it

Raised by packet core-09. Affects [`schemas/gate.schema.json`](schemas/gate.schema.json)'s
`$defs.proof`, [`gate.yml`](gate.yml), and
[`docs/gate.md`](docs/gate.md)'s "The format" section.

The question is what a gate declaration is *for*. It could describe a gate, or it
could be the thing that decides whether a gate counts as having run.

**Choice: it is the second, and that is the whole design.** A declaration carries
`gate.proof` — one or more patterns the gate's own output must contain, with an
optional `minimum` floor read from a single capture group. A run that exits 0
without emitting a declared proof is `gate.proof-missing`, and it is a failure.

**Alternatives:**

1. **Describe only** — the declaration says what the gate is and what it needs,
   and nothing runs it. Cheaper, and a checker for it is a linter: it can catch a
   command that no longer exists and it cannot catch a gate that does nothing.
   This is the alternative the packet's own measurement argues against, and the
   false green it cannot catch is the one this fleet has already shipped once.
2. **Require a machine-readable test report** and match on that (JUnit, pytest's
   `--junitxml`, `go test -json`). Stronger — it is a count, not a line of text —
   and it is MD12's direction for the right reason. The cost is that four
   languages in this fleet produce no such report, or produce it in four
   different dialects, and a format every repository can write has to be
   writable by all of them. `match` is a regular expression, which every one of
   them can satisfy by printing one line.
3. **Require a cryptographically signed report.** Refuses a restored cache, and
   answers a question nobody asked: the problem is not that a report is forged,
   it is that a report is *about a different run*. A report restored from another
   branch is a report with the wrong number in it, and a signature over it is
   still the wrong number.

**Recommendation:** option 1 now, and option 2 as a per-repository tightening —
`match` can already be `'<testsuite ... tests="1166"'` against a JUnit XML, so a
repository that has a real reporter gets a real report with no format change.
The line that changes if the manager rules for option 2 is `gate.proof[].match`,
and nothing else in the schema, the checker or the twenty-three breakages.

**Cost of flipping:** one property name and one regular expression per proof. The
checker already requires exactly one capture group when `minimum` is set, so
adopting a JUnit-based floor is a spelling change and not a redesign.

## D31: the gate checker is stdlib-only and needs Python 3.11, where the contract harness needs 3.9

Raised by packet core-09. Affects [`harness/bin/gate-check`](harness/bin/gate-check),
[`harness/gate_check.py`](harness/gate_check.py)'s `MINIMUM_PYTHON`, and every
repository whose CI would call it. See also
[`docs/gate.md`](docs/gate.md).

`harness/gate_check.py` reads `mise.toml`, and `tomllib` is standard library
from 3.11. `harness/cafaye_contract.py` accepts 3.9 because it reads no TOML.

**Choice: `gate-check` requires 3.11 and the wrapper exits 2 with a message on
anything older.** The two minimums differ and both are named.

**Alternatives:**

1. **Shell out to `mise tasks`.** Works on 3.9, and makes the checker's answer
   depend on which `mise` is installed — and on what happens when there is none,
   which is the state of `guard`, `muse` and `kit`. A check whose answer depends
   on the day is the failure mode this packet exists to catch.
2. **Write a TOML subset reader, the way the YAML reader was written.** The YAML
   reader exists because a reader that cannot read the documents it exists to
   check is a demonstration. A TOML reader would be a second reader of a second
   language, in a repository whose rule is that a rule lives in exactly one place.
3. **Drop the mise cross-check** and verify only the entrypoint on disk. Loses
   `gate.task-missing` and `gate.task-unresolvable`, which are the two checks
   that would catch a repository's fleet spelling drifting away from its gate.

**Recommendation:** the choice as built. 3.11 is four years old, every language
in this fleet already has a newer interpreter, and the price is a refusal with a
sentence explaining it rather than a silent degradation to a green.

**Cost of flipping:** the alternative that is actually attractive is option 3,
and it costs one schema property, one code path and two of the twenty-three
breakages. If the manager rules that 3.9 support is worth more than the mise
cross-check, that is the change to make.

## D32: whether a repository with no CI is a warning or a failure

Raised by packet core-09. `docs` and `cafaye-py` have no `.github/workflows` at
all, and a `ci` block cannot be written for a file that does not exist. Affects
[`schemas/gate.schema.json`](schemas/gate.schema.json)'s `$defs.ci` and
`harness/gate_findings.json`. See also
[`docs/gate.md`](docs/gate.md)'s findings table.

**Choice: `gate.ci-undeclared` is a warning, and a warning never moves the exit
code.** A repository that gates locally and has no CI is a real state, and the
right response to it is to report it, not to fail a gate over it.

**Alternatives:**

1. **Fail it**, and require every repository to have a workflow. The strongest
   answer to "a CI job that silently skips the hard part is worse than no CI",
   and it makes the first adoption in `docs` require writing a workflow the
   packet was told not to write there.
2. **Make `ci` required with a declared `none`.** The declaration then says "this
   repository has no CI" in a machine-readable way instead of by omission. The
   cost is a value that is easy to leave in place after a workflow is added, and a
   stale `none` is a declaration quietly describing something that no longer
   exists — the exact failure mode core's own rule names.

**Recommendation:** the choice as built, with option 2 as the tightening once the
fleet has adopted the format everywhere. `none` is the one line that changes, and
`gate.ci-undeclared` becomes `gate.ci-none`, which is a smaller question than
whether CI agrees.

**Cost of flipping:** one enum value, one finding id, and the rename of one
breakage in `harness/tests/gate_self_test.sh`.

## D33: cross-tenant access is declared, never inferred, and answered as nonexistence

Raised by packet core-15. Measured across the fleet: cross-tenant negative tests
— ones asserting account A is refused account B — number 7 in identity and 19 in
courier, and **zero** in billing, cafaye-rb, cafaye-ts, guard, darkroom, pantry,
muse and cafaye-py. Six of those eight scope by account in production code.
`darkroom` is the clean case: `assets` and `asset_variants` carry `account_id
uuid not null`, every statement reads `where id = $1 and account_id = $2`, and
no test asserts any of it. Counting account-scoped routes by pattern gives 96
for guard, 76 for muse, 51 for cafaye-ts and **0** for darkroom and billing —
the last two because axum and Rails are not the syntax the pattern reads.
Affects [`schemas/tenant-isolation.schema.json`](schemas/tenant-isolation.schema.json),
[`docs/tenancy.md`](docs/tenancy.md) and `harness/tenancy_check.py`.

**Choice: cross-tenant access is DECLARED, never inferred; and it is answered as
NONEXISTENCE, never as a refusal.** A service publishes `tenancy.yml` naming
every entry point that reaches another account's data, the line at which each is
scoped, and the test that asserts account A gets nothing back for account B's
row. The checker reads that declaration against the tree. It does **not** derive
the enumeration: a checker that inferred it would answer per framework, and the
answer would be a syntax report wearing a security report's clothes.

The second half is the decision somebody will otherwise relitigate in every
service. `403`/`ErrNotAuthorized` tells an attacker the id exists; `nil`, `[]`,
`None`, `NotFound` tell them nothing. So `negative.asserts` is a `const: absent`
— not an enum with a discouraged second value — and `tenancy.denial-refuses` is
a **failure**, so a service that weakens the assertion gets a red that names the
enumeration oracle rather than a style comment.

**Alternatives:**

1. **Infer the enumeration.** Enumerate routes, queries and repository methods per
   framework and have the checker prove the boundary. Rejected on the measurement
   above: it returns 0 for darkroom and billing, and a report that says "no
   account-scoped routes" about a service with account-scoped queries against
   customer assets is **worse than no report**, because it reads like an answer.
   Any inference also has to choose a framework's syntax, and the fleet has
   axum, Rails, Ecto, sqlx and TypeScript decorators.
2. **A rule instead of a declaration** — "a query touching an account-prefixed
   table must carry an account predicate". It cannot see the join that drops the
   scope, the CTE that loses it between two `select`s, the repository method
   three layers down, or the middleware that resolves the account in the first
   place. And a rule right about 90% of sites reads as a boundary that holds.
3. **Allow `403` and document the trade-off.** Rejected: it is answerable per
   service with no cost, and the reason it keeps coming back is that "the resource
   exists but you may not have it" is a *more useful* answer to write. Naming it
   a `const` is the only thing that stops that conversation happening per
   service, which is the entire value of a contract.
4. **Require the negative assertion, say nothing about its shape.** That leaves
   `assert get(id, other) == 403` and
   `assert get(id, other) == nil` both counting as coverage, which is the
   defect the second half of this ruling exists to close.

**Recommendation:** the choice as built. The one place to revisit first is
closure for non-SQL languages: that needs a parser per language rather than a
pattern, it belongs in `caf`, and until it exists the honest answer is the
`tenancy.enumeration-partial` warning rather than a fail — which is also why the
warning exists and why it never moves the exit code.

**Cost of flipping:** to inference, the `entryPoints` array becomes computed, the
schema loses `enforced.file`/`enforced.line`/`negative` (they become check-time
conclusions rather than declarations), and `harness/tests/tenancy_self_test.sh`
loses its sixteen breakages — every one of which is a defect an inferred
enumeration would have to be *right about* to catch, which is the same argument
that has the fleet reading its own boundary from a text pattern today. To the
absence half: one `const` becomes an `enum`, one finding id disappears, one
breakage is renamed, and every service that adopted `absent` keeps it — the
schema change is cheap and the migration is the part that would take a release.

## D34: how does the fleet record a type core has not finished contracting for?

Raised by packet core-22, while correcting a registry that had been describing
yesterday's fleet. Measured at the identity repository's `master` on 2026-10-01
(`a20be0f`): its manifest declares **nine** event types in the conforming
three-segment form. `fleet.yml` recorded **one** of them as published and eleven
as `cataloguedOnly` — so eight of the eleven were, at the time of the claim,
both published by identity and marked as a promise nobody had made good. Six of
the eight have a row in `docs/event-naming.md` and no payload schema under
`schemas/events/identity/`; the two `identity.oidc_client.*` types have neither,
because no catalog row for either exists anywhere in core. The same packet found
the mirror case in courier, where a prose note denied an `exposes.api` courier
had declared since courier-05, because `fleet.schema.json` had no field to record
one in. Affects [`schemas/fleet.schema.json`](schemas/fleet.schema.json),
[`fleet.yml`](fleet.yml) and
[`tests/test_specs.py`](tests/test_specs.py)'s
`test_a_pending_core_contract_type_is_a_debt_core_really_owes`.

**Choice: the registry gains a FOURTH list, `pendingCoreContract`, and it is
constrained rather than free.** A conforming type the manifest declares and the
service publishes, for which core has not shipped both a catalog row and a
payload schema, goes in `pendingCoreContract` — never in `events`, which means
"core's contract for this type is finished" and is asserted to mean it. The list
is the exact mirror of `cataloguedOnly`: that one is a promise core made that
nobody has kept, this one is a promise a service kept that core has not answered.
And it is asserted in the direction that can be checked from inside core: an
entry that has both a row and a schema is **rejected**, because a debt with
nothing behind it is an excuse for work already done, and a registry carrying
excuses is how a reader stops believing the list that is telling the truth.

**Alternatives:**

1. **Write the eight missing payload schemas, and the two missing catalog rows,
   in this packet.** It is what `events` wants, and it is the state with no
   fourth list. Rejected on scope, not on merit: it means authoring core's
   payload contract for another repository's events — eight schemas read off
   identity's Go source, two rows invented for types core has never described —
   inside a packet whose job is a transcription. A payload schema is a promise
   to every consumer on the bus, and one written by somebody who did not ship
   the publisher is a promise made on the publisher's behalf. It is the right
   work and it is its own packet.
2. **Leave identity's `events` short of what its manifest declares, and say so
   in prose.** This is what the file did, and the cost is the whole packet: the
   reader sees `events: [identity.user.created]` against a `sourceCommit` that
   says otherwise, with nothing machine-checkable distinguishing "this service
   publishes one type" from "this registry got round to one type". Prose is not
   compared against anything, which is how courier's `exposes.api` sentence
   outlived two packets that edited the document it said did not exist.
3. **Add `pendingCoreContract` with no constraint on it.** Rejected: a list that
   means "core has not finished this" stops meaning that the first time a type in
   it is finished, and nothing would notice. This is the same defect as reading
   `signals: []` as "this service is not instrumented" — a field whose value
   teaches a reader a conclusion its absence supports.
4. **Make `events` mean "declared", and weaken the catalog assertion to exempt
   types with no row.** Rejected outright: it deletes the assertion that has
   teeth. That assertion is the reason the event types courier could not emit
   were caught at all, and an exemption keyed on "core has not got to it yet" is
   an exemption every type qualifies for.

**Recommendation:** the choice as built, and the constrained list is the part
that matters — option 3 is the same schema change with the teeth left out, and
it is the one that would rot. The cheap direction to revisit is option 1: the
day core writes identity's remaining payload schemas, every entry here moves to
`events` and the list empties, and the assertion above is what makes that move
safe to make without checking by hand.

**Cost of flipping:** to option 1, eight files under `schemas/events/identity/`
and two rows in `docs/event-naming.md`, after which `pendingCoreContract` is
empty and the list, its schema entry, its three pairwise-disjointness assertions
and this decision can all be deleted — the deletion is the acknowledgement, the
same convention `manifestViolations` follows. To option 2, the transcription
goes back to being a claim with no machine-checkable half, and this packet's
other four corrections would have had to be prose too. **What this decision does
not settle, and must not be read as settling:** whether the service really emits
each type in the list. That is `sourceCommit`'s job, it is not checkable from
inside core, and the schema's own description says so rather than implying a
check that does not exist.

**Update, core-23: the debt is paid and the list is empty, and the deletion D34
names was NOT taken in full.** Eight payload schemas and two catalog rows landed;
all nine of identity's declared types are in `fleet.yml`'s `events`; the
`pendingCoreContract` key is gone from every entry. What stayed is the schema
property, `fleet.yml`'s header and all three assertions, because the alternative
D34 priced was priced for a registry that could be deleted cleanly and this one
cannot: the next type a service declares and core has not answered needs a list
whose meaning is checkable in both directions, and a deleted list is a fourth
place to invent. D34 also priced removing the assertions, and that is where the
packet overrode it — with the list empty,
`test_a_pending_core_contract_type_is_a_debt_core_really_owes` had nothing left to
iterate and would have passed on anything, so the rule moved into
`pending_core_contract_debts` and a new test hands it a fleet carrying a type core
HAS finished. Shown red: with the schema half of the predicate removed, the new
test fails and the old one stays green, which is the entire reason it exists. The
"cost of flipping" line above is therefore still accurate about the schemas and
the rows, and wrong about the deletions.

## D35: `identity.user.created`'s payload schema describes a payload its only publisher does not emit

Raised by packet **core-23**, while writing the other eight identity payload
schemas. Read at identity's `master` on 2026-10-02, commit `a20be0f` — the same
commit `fleet.yml` already transcribes. Affects
[`schemas/events/identity/user/created.schema.json`](schemas/events/identity/user/created.schema.json),
its example at
[`examples/valid/events/identity/user/created.data.json`](examples/valid/events/identity/user/created.data.json),
and the premise of
[D7](#d7-courier-keys-a-user-by-uuid-and-identity-publishes-a-usr_-id).

**What the code says, read rather than remembered.**
`internal/outbox/envelope.go`'s `NewUserCreated(now, userID, email)` marshals a
struct of exactly two fields — `user_id` and `email` — and passes
`userID.String()`, which is `internal/platform/id/id.go`'s `String()`: RFC 4122
canonical form, eight-four-four-four-twelve lower hex, no prefix. So the shipped
schema is wrong in **four** places, not one:

| The schema says | The publisher emits |
| --- | --- |
| `user_id` matches `^usr_[0-9A-Z]{26}$` | a bare uuid, so **no value identity has ever produced satisfies this pattern** |
| `email_verified` is `false` | not present — the struct has two fields |
| `locale` is a BCP 47 tag | not present |
| `account_ids` is an array | not present |

The first is the serious one, and it is not a disagreement between two services —
it is a contradiction between two files in the same directory. core-23 wrote
`user_id` as `format: uuid` in eight schemas beside this one, with a description
saying why, and cited **D7** for it; D7's own text says the `usr_` half is "what
identity emits". One of those two sentences is false and the false one is the
older. The three absent fields are the milder version of the same defect, and
`docs/event-naming.md`'s rule — *a payload schema describes what a publisher
emits, not what it ought to emit* — is what all four violate.

**Choice: none, deliberately, and that is the decision.** core-23 shipped eight
schemas and did not touch the ninth, on three grounds. It is a change to a
**shipped** payload contract, so it belongs in a release rather than in a packet
whose brief is a debt list. It is not one of the eight types the debt was about,
and rewriting a neighbouring file to fix something nobody asked about is how a
packet stops being reviewable. And the fleet-wide question underneath it — do
cafaye ids carry a prefix, or are they uuids? — has already been answered twice
in the same direction (**D10**: billing may not invent `sub_`/`pln_` ids it does
not have; the eight new schemas: uuid, because that is what the publisher emits),
so the third answer is not this packet's to give and a fourth opinion would make
the record worse rather than better.

**Alternatives:**

1. **Rewrite it to reality, as core-23 did for the other eight.** `user_id`
   becomes `format: uuid`; the three never-emitted properties are deleted; the
   example loses `email_verified`, `locale` and `account_ids`; D7's second half
   is deleted rather than corrected, because there is no longer a divergence to
   record. The call on the version is the manager's: **README's table calls a
   removed field major**, and I would argue for a patch on the grounds that no
   consumer can depend on a field the only publisher never sent — but that is a
   statement about intent and the table is the rule, so it is a manager's call
   and not one to make quietly in a schema.
2. **Leave it and let D7's cross-reference carry the weight.** Rejected, and it
   is the option this packet took only because the alternative is out of scope:
   a schema no publisher's output can satisfy rejects 100% of real traffic, and it
   does so *green*. `docs/event-naming.md` puts the cost of exactly this in
   writing — "a schema that names a field nobody emits is worse than no schema,
   because it is a contract that lies and it lies *green*."
3. **Accept both spellings** (`pattern` with an alternation). Rejected by D7 for
   courier's case and it is worse here: there is no second spelling in existence,
   so an alternation would accept a format no publisher emits and hide the defect
   behind a pattern that looks deliberate.
4. **Ask identity to emit `usr_`-prefixed ids.** Out of the question: it is a
   migration on every id in another repository, it breaks the join with courier
   and billing that already works, and core is the wrong repository to ask.

**Recommendation: option 1, in its own packet, with the test that would have
caught it.** That test is one assertion and it is written out here so the next
packet does not have to invent it: no file under `schemas/events/**` may require
a cafaye-prefixed id, because no publisher in the fleet mints one — walk the
`pattern` and `const` values under `schemas/events/` and fail on `usr_`, `acc_`,
`sub_`, `pln_`, `inv_`. It would have gone red on this file the day core-23
landed, which is the strongest argument for adding it: **the contradiction became
visible only because a second schema was written next to the first.** That is the
generalisable form of the defect — nothing in core compared two payload schemas to
each other — and it is why the assertion belongs in core rather than in a reviewer's
memory.

**Cost of flipping:** to option 1, one pattern becomes `format: uuid`, three
properties are deleted, one example is rewritten, one `INVALID_PAYLOAD_CASES`
entry may need its expected keywords revisited, D7 loses its second half, and
README's bump table is read one more time to settle patch-versus-major. Under an
hour. To option 2, nothing, today, and a schema that rejects every event its only
publisher emits for as long as nobody looks at it.
