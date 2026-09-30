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
[`schemas/events/courier/**`](../schemas/events/courier) file and
[`schemas/events/identity/user/created.schema.json`](../schemas/events/identity/user/created.schema.json).

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
[`schemas/events/courier/notification/suppressed.schema.json`](../schemas/events/courier/notification/suppressed.schema.json)
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