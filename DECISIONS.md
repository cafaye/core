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
