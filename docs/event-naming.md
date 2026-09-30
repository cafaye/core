# Event naming

Every event in cafaye travels in the envelope defined by
[`schemas/event-envelope.schema.json`](../schemas/event-envelope.schema.json).
This document is the human half of that contract: the grammar, the reasoning
behind the rules, and the catalog of events that exist today.

The machine-checked form of the grammar is the `eventType` pattern in the
schema. `tests/test_specs.py` fails if this document and that pattern ever
disagree.

## Envelope

```json
{
  "specversion": "1.0",
  "id": "0198f1c2-7a41-7c3b-9d55-2f0b6a1e4c88",
  "type": "identity.user.created",
  "source": "identity",
  "subject": "usr_01J9Z8QK5M4N7P2R3T6V8W9X0A",
  "time": "2026-09-30T04:19:00Z",
  "data": { "user_id": "usr_01J9Z8QK5M4N7P2R3T6V8W9X0A", "email": "kaka@example.com" }
}
```

| Field | Rule |
| --- | --- |
| `specversion` | Envelope dialect. `1.0` = CloudEvents 1.0 attribute names, cafaye's required subset. Breaking envelope change = new major. |
| `id` | UUID, unique per emission. **Never reused**, including for a retry of the same logical event. Consumers dedupe on this. |
| `type` | The name below. Immutable once published. |
| `source` | Publishing service — must equal `name` in that service's `cafaye.yml`, and the first segment of `type`. CloudEvents' URI form is `/cafaye/<service>`. |
| `subject` | **Required.** The entity the event is *about*, not the actor. Entity id, e.g. `usr_01J9Z8…`, or the literal `platform` for an event with no single entity. |
| `time` | RFC3339 UTC, when the state change happened — not when the message was queued. |
| `data` | The payload. Its shape is `schemas/events/<service>/<entity>/<action>.schema.json`, keyed by `type` — see [Payload schemas](#payload-schemas). |

Undeclared envelope attributes are rejected: `additionalProperties` is `false`.
Transport metadata (trace id, hop count, delivery attempt) travels in transport
headers, never in the envelope.

### Why `subject` is required

CloudEvents makes `subject` optional. cafaye does not, because `subject` is what
carries **per-entity ordering**: a consumer that needs two events about the same
thing in order correlates on this value and nothing else. An absent `subject` is
a correlation key that silently disappeared, and the resulting bug is a state
machine that only fails under replay.

An event with no single entity — a nightly billing reconciliation, a fleet-wide
config reload — is not exempt from the field; it uses the literal `platform`.
A required field with a reserved value is a value a consumer can always read, a
missing field is a null check every consumer has to remember to write.

## Grammar

Every event type is `<service>.<entity>.<action>` — three segments, always
prefixed, no exceptions.

```
type    := <service> "." <entity> "." <action>             # exactly 3 segments
segment := lowercase snake_case, starts with a letter      # [a-z][a-z0-9]*(_[a-z0-9]+)*
service := cafaye namespace name — kebab-case, may contain a dash
```

1. **Three segments, always prefixed.** `<service>` is the publishing service and
   must equal the envelope's `source` and the manifest's `name`.
   `<entity>` is the aggregate the event is about, singular, lowercase
   snake_case. `<action>` is what happened to it. There is no short form:
   `identity.api_key.created`, not `api_key.created`.
2. **The prefix is not optional, and that is the point.** An unprefixed type
   says only what changed, never who changed it, so every consumer — a
   subscription, a `guard` route, an SDK's generated constant, a human reading a
   log line at 3am — has to join it against a table of publishers. Prefixing
   every type makes the publisher part of the name, which is what lets a type be
   routed, generated and fanned out from the string alone. The verbosity is the
   price and it is worth paying once per type rather than at every subscription.
3. **Segment casing is not uniform, and that is deliberate.** The service segment
   is a service name, so it is kebab-case like `name` in a manifest
   (`email-sender.email.queued`); the entity and action segments are snake_case
   (`identity.api_key.created`). A service name never contains an underscore, so
   an underscore in the first segment is always a mistake.
4. **Actions are past tense or state, never commands.** `created`, `deleted`,
   `invited`, `started`, `succeeded`, `bounced`, `past_due`, `revoked`.
   Never `on_user_created`, `user_create`, `UserCreated`, `users`, `is_active`.
5. **One event, one fact.** If you need `and`, you need two events.
6. **Immutability.** A published type never changes meaning. `type` is not a
   version field; `specversion` and the payload schema carry evolution.


## Action vocabulary

Stick to this list for v0; anything else is a manager decision.

`created` · `updated` · `deleted` · `verified` · `enabled` · `disabled` ·
`revoked` · `regenerated` · `invited` · `joined` · `removed` · `role_changed` ·
`started` · `updated` · `canceled` · `past_due` · `succeeded` · `failed` ·
`refunded` · `recorded` · `queued` · `delivered` · `bounced` · `complained` ·
`suppressed` · `requested` · `completed` · `consumed`

## Evolution

| Change | Move |
| --- | --- |
| New optional `data` field | Same `type`. Preferred; consumers must ignore unknown fields. |
| New required `data` field | Same `type` only if consumers can tolerate it missing; otherwise a new `type`. |
| Field renamed, removed, or semantics changed | **New `type`.** Publish both, deprecate the old one, never repurpose it. |
| Breaking envelope change | Bump `specversion`. |

Deprecation is announced in the catalog below with a `deprecated` row and a
removal date, at least **6 months** out — the same window as the HTTP API
([openapi-conventions.md](openapi-conventions.md)).

Because a payload schema lives in core, evolving one is a core release, and it
follows [README.md's bump table](README.md#spec-versioning): a new optional
field is a patch, a new required field is a minor, and a removed or retyped field
is a major. A publisher that wants to make a breaking payload change ships a new
`type` and deprecates the old one; it does not edit the schema in place and hope
the consumers read the diff.

## The fleet declaration

The catalog is only as true as the thing it is compared against. Until
[`fleet.yml`](../fleet.yml) landed, that thing was core's own
`examples/valid/*.cafaye.yml` — which core also writes, so the assertion could
only ever catch core disagreeing with itself. A real service could advertise any
event type at all.

`fleet.yml` is the other side of the comparison: a machine-readable record, per
service repository, of what that service's own `cafaye.yml` declares on `master`,
with the full commit each one was read at and the day it was read. It is
validated by [`schemas/fleet.schema.json`](../schemas/fleet.schema.json), and
`tests/test_specs.py` asserts, for every entry:

- the service is named (dropping one fails, rather than silencing the checks)
- every published type satisfies the grammar and starts with its own service name
- every catalog row for a shipped service is either published or listed as
  `cataloguedOnly`
- every `manifestViolations` entry is recorded verbatim, from a manifest that
  still breaks the grammar

Once a payload schema exists for every published type — see
[Payload schemas](#payload-schemas) — one more assertion applies: every
published type has a catalog row **and** a payload schema.

That `manifestViolations` list is courier's five two-segment types. They are
transcribed, not catalogued: naming a non-conforming type in the catalog would
not make it valid, and the fix belongs to the publisher. Delete the entry when
the publisher's manifest is corrected — that deletion is the acknowledgement.
The correction is five strings in courier's `cafaye.yml` and one `@types` list in
`Courier.Events`, in one commit; the conforming spellings are the catalog rows
below.

`events` and `cataloguedOnly` are different lists on purpose. A catalog row is a
promise and a manifest entry is a claim; identity's catalog names twelve types
and its manifest declares one. Collapsing the two would either empty the catalog
of promises or make every promise a lie.

**`caf contract lint` reads this file** rather than re-deriving the catalog, so
there is one answer to "what does the fleet publish" rather than two derivations
that can disagree.

## Delivery

- At-least-once. `id` is the dedupe key; every consumer stores it and makes its
  handler idempotent before it goes to production. Duplicates are not an edge
  case to be tolerated, they are the normal case.
- Ordering is per-entity only, never global. If a consumer needs two events in
  order, it correlates on `subject`.
- A consumer that cannot process an event must not block the queue: park it,
  alert, keep going.
- Publishing is a transactional outbox, not a best-effort `PUBLISH` in a request
  handler. The table, the publisher loop and the retry rules are in
  [event-outbox.md](event-outbox.md).

## Catalog

Every event that exists today. A type becomes real when it has a row here and
an entry in its publisher's `exposes.events` — the two are asserted to agree in
both directions by `tests/test_specs.py`, so a row without a publisher entry (or
the reverse) fails the suite. Registering a new one is a five-step checklist at
the bottom of this document.

### identity

Emitted by `identity`. Listed in `examples/valid/go-api.cafaye.yml`.

| Event type | Subject | Emitted when |
| --- | --- | --- |
| `identity.user.created` | the user | Signup completes, before email verification. |
| `identity.user.email_verified` | the user | The verification link is redeemed. |
| `identity.account.created` | the account | A new account/tenant is provisioned. |
| `identity.member.invited` | the account | An invitation is sent. `data.invitation_id` is the thing to act on. |
| `identity.member.joined` | the account | An invitation is accepted. |
| `identity.member.removed` | the account | A member is removed or declines. |
| `identity.member.role_changed` | the account | A role is granted or revoked. `data` carries old and new role. |
| `identity.mfa.enabled` | the user | TOTP enrolled and confirmed. |
| `identity.mfa.disabled` | the user | MFA turned off by the user. |
| `identity.session.revoked` | the user | Password change, "sign out everywhere", or admin revocation. |
| `identity.api_key.created` | the api key | A scoped API token is issued. The entity `api_key` is generic, but so is the prefix — every type carries one. |
| `identity.api_key.revoked` | the api key | A scoped API token is revoked or expired. |

### billing

Emitted by `billing`. Listed in `examples/valid/ruby-api.cafaye.yml`.

| Event type | Subject | Emitted when |
| --- | --- | --- |
| `billing.plan.created` | the plan | A plan is published and becomes billable. |
| `billing.customer.created` | the customer | A billing customer is created for an account. |
| `billing.subscription.started` | the subscription | A subscription becomes active (trial counts as started). |
| `billing.subscription.updated` | the subscription | Plan, quantity, or interval changes. |
| `billing.subscription.canceled` | the subscription | Cancellation takes effect, not when requested. |
| `billing.subscription.past_due` | the subscription | A payment attempt fails; the grace period starts. |
| `billing.payment.succeeded` | the payment | A charge settles. **Money events only; integer minor units.** |
| `billing.payment.failed` | the payment | A charge attempt is declined or errors. |
| `billing.payment.refunded` | the payment | A refund settles, full or partial. |
| `billing.invoice.created` | the invoice | A finalized invoice exists. |
| `billing.usage.recorded` | the account | Metered usage is accepted for a period; `data` carries quantity + window. |

### courier

Emitted by `courier`. Listed in `examples/valid/worker.cafaye.yml`.

| Event type | Subject | Emitted when |
| --- | --- | --- |
| `courier.email.queued` | the notification | A message is accepted for delivery. Emitted on acceptance, not on send, so a queue backlog is visible. |
| `courier.email.delivered` | the notification | The provider accepts the message. |
| `courier.email.bounced` | the notification | The destination hard-bounces. Suppresses further sends to that address. |
| `courier.email.complained` | the notification | The recipient marked it as spam. Suppresses the address immediately. |
| `courier.notification.suppressed` | the recipient | A send was skipped: preference off, address suppressed, or rate limited. The audit trail for a message that was never sent. No `message_id` in the payload, because there was no message — see [D8](../DECISIONS.md#d8-what-is-the-subject-of-couriernotificationsuppressed). |

All five are the conforming spellings. courier's own manifest says `email.queued`
and four siblings, which core v0.2's frozen grammar rejects; see
[`fleet.yml`](../fleet.yml) for the transcription and
[the fleet declaration](#the-fleet-declaration) for why they are recorded rather
than catalogued.

Every courier payload keys its recipient on a bare uuid, because that is what
courier emits — while `identity.user.created` publishes a `usr_`-prefixed id.
The two do not join, which is [D7](../DECISIONS.md#d7-courier-keys-a-user-by-uuid-and-identity-publishes-a-usr_-id)
and not something either schema can fix.

### muse

Emitted by `muse`. Listed in `examples/valid/muse.cafaye.yml`.

| Event type | Subject | Emitted when |
| --- | --- | --- |
| `muse.tokens.consumed` | `platform` | One routed completion is metered. The subject is core's reserved literal rather than an id: a call belongs to one request, and muse's v1 auth stub does not read a token, so there is no account to name. See [D9](../DECISIONS.md#d9-consumed-is-not-in-the-action-vocabulary-and-the-payload-has-no-account). |

## Payload schemas

Every event's `data` has a schema, and it lives in **core**, not in the
publishing repository. The path is the event type with dots turned into
directory separators, so a type needs no index to be found:

```
identity.user.created  ->  schemas/events/identity/user/created.schema.json
```

Core owns the single home because a payload schema is a promise to *other*
services. The moment a publisher can change it in a commit nobody downstream
sees, the contract is whatever the publisher's tests happen to assert, and every
consumer's SDK generator is reading a file with a different lifetime. A schema
that lives in core is versioned, diffed and released with the event catalog it
belongs to, which is what makes `identity.user.created` a citable contract
rather than a moving target.

The cost is churn: core gains a commit every time a payload changes. That is the
cost of a contract being a contract, and it is paid in review rather than in
debugging a consumer that broke on a Tuesday.

Each payload schema is a standalone draft 2020-12 document, closed with
`additionalProperties: false` like every other schema here, and it validates the
`data` object — not the envelope around it. The envelope is validated separately
by [`schemas/event-envelope.schema.json`](../schemas/event-envelope.schema.json);
a contract test does both, in that order.

Shipped so far:

| Event type | Payload schema |
| --- | --- |
| `identity.user.created` | [`schemas/events/identity/user/created.schema.json`](../schemas/events/identity/user/created.schema.json) |
| `billing.subscription.started` | [`schemas/events/billing/subscription/started.schema.json`](../schemas/events/billing/subscription/started.schema.json) |
| `courier.email.queued` | [`schemas/events/courier/email/queued.schema.json`](../schemas/events/courier/email/queued.schema.json) |
| `courier.email.delivered` | [`schemas/events/courier/email/delivered.schema.json`](../schemas/events/courier/email/delivered.schema.json) |
| `courier.email.bounced` | [`schemas/events/courier/email/bounced.schema.json`](../schemas/events/courier/email/bounced.schema.json) |
| `courier.email.complained` | [`schemas/events/courier/email/complained.schema.json`](../schemas/events/courier/email/complained.schema.json) |
| `courier.notification.suppressed` | [`schemas/events/courier/notification/suppressed.schema.json`](../schemas/events/courier/notification/suppressed.schema.json) |
| `muse.tokens.consumed` | [`schemas/events/muse/tokens/consumed.schema.json`](../schemas/events/muse/tokens/consumed.schema.json) |

The rest of the catalog has no payload schema yet; each lands with the packet
that first needs it. `tests/test_specs.py` fails on a payload schema that is not
in this table, and on a table row whose file does not exist, so the two cannot
drift.

## Registering a new event

1. Pick the type from the grammar and the action vocabulary.
2. Add it to the publisher's `cafaye.yml` `exposes.events`.
3. Add a row to the publisher's catalog sub-section above, with its payload
   fields. Steps 2 and 3 are the same fact stated twice — the suite fails if
   only one of them happens, so land them in one commit.
4. Add the payload schema at
   `schemas/events/<service>/<entity>/<action>.schema.json`, with a valid
   example under `examples/valid/events/`, a negative one under
   `examples/invalid/events/` and a row in the table above.
5. Add a contract test: the emitted envelope validates against the envelope
   schema, and the payload against the payload schema.

If the payload's real shape cannot be determined — because the publisher's code
does not say, or says two things — **do not guess a field name.** A schema that
names a field nobody emits is worse than no schema: it is a contract that lies.
Leave the property out, and record the question in
[DECISIONS.md](../DECISIONS.md) as a numbered decision with a call, the
alternatives, a recommendation and the cost of flipping (see
[D6](../DECISIONS.md#d6-where-do-open-decisions-live) for why the numbering lives
there rather than in this file). A shipped schema and an open question are both
fine; a confident wrong field is neither.
