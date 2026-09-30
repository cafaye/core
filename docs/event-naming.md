# Event naming

Every event in cafaye travels in the envelope defined by
[`schemas/event-envelope.schema.json`](../schemas/event-envelope.schema.json).
This document is the human half of that contract: the grammar, the reasoning
behind the rules, and the catalog of events that exist today.

The machine-checked form of the grammar is the `eventType` pattern in the
schema. `tests/test_specs.py` fails if this document and that pattern ever
disagree.

> DECISION NEEDED (D1): the packet specified `<service>.<entity>.<action>` but the
> packet's own catalog is two segments (`user.created`). This draft accepts
> **both** forms and requires the service prefix only for generic entities. The
> alternative — one canonical three-segment form (`identity.user.created`) — is
> more machine-parseable and unambiguous, at the cost of verbosity in every
> subscription. Manager decides; flipping to canonical three-segment is a
> one-line pattern change plus a catalog rename.

## Envelope

```json
{
  "specversion": "1.0",
  "id": "0198f1c2-7a41-7c3b-9d55-2f0b6a1e4c88",
  "type": "user.created",
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
| `source` | Publishing service — must equal `name` in that service's `cafaye.yml`. CloudEvents' URI form is `/cafaye/<service>`. |
| `subject` | The entity the event is *about*, not the actor. Entity id, e.g. `usr_01J9Z8…`. |
| `time` | RFC3339 UTC, when the state change happened — not when the message was queued. |
| `data` | Opaque to core. Owned by the publisher (see D3). |

Undeclared envelope attributes are rejected: `additionalProperties` is `false`.
Transport metadata (trace id, hop count, delivery attempt) travels in transport
headers, never in the envelope.

> DECISION NEEDED (D2): `subject` is **required** in this draft, with the literal
> string `platform` as the escape hatch for events that have no single entity
> (e.g. a billing nightly reconciliation). CloudEvents makes `subject` optional.
> Making it optional is a one-word change to `required`.

> DECISION NEEDED (D3): where does a per-event `data` payload schema live? Three
> candidates: (a) next to the publisher's OpenAPI document in the publishing
> repository — best locality, but the publisher can then break its own
> consumers' contract tests; (b) here in core, one schema per event type — the
> contract has a single home, but core churns on every payload change; (c) a
> `contracts/` repository, payload schemas split from both. This draft says only
> "the publisher owns it" and deliberately ships **no** payload schema, so core
> cannot validate `data` in v0. Recommendation: (c), with core holding the
> catalog row that points at it. Manager decides before the first packet that
> needs one.

## Grammar

```
type    := <entity> "." <action>                          # 2 segments
         | <service> "." <entity> "." <action>            # 3 segments
segment := lowercase snake_case, starts with a letter     # [a-z][a-z0-9]*(_[a-z0-9]+)*
```

1. **Two segments by default.** `<entity>` is the aggregate the event is about,
   singular, lowercase snake_case. `<action>` is what happened to it.
2. **Three segments when the entity is generic.** Add the service prefix when the
   bare entity name is one another cafaye service could plausibly own: `key`,
   `token`, `event`, `file`, `job`, `config`, `webhook`, `asset`, `secret`.
   `identity.api_key.created` yes; `payment.succeeded` no. When you add the
   prefix, the prefix must be the publisher's own name — enforced by
   `tests/test_specs.py`.
3. **Actions are past tense or state, never commands.** `created`, `deleted`,
   `invited`, `started`, `succeeded`, `bounced`, `past_due`, `revoked`.
   Never `on_user_created`, `user_create`, `UserCreated`, `users`, `is_active`.
4. **One event, one fact.** If you need `and`, you need two events.
5. **Immutability.** A published type never changes meaning. `type` is not a
   version field; `specversion` and the data schema carry evolution.

## Action vocabulary

Stick to this list for v0; anything else is a manager decision.

`created` · `updated` · `deleted` · `verified` · `enabled` · `disabled` ·
`revoked` · `regenerated` · `invited` · `joined` · `removed` · `role_changed` ·
`started` · `updated` · `canceled` · `past_due` · `succeeded` · `failed` ·
`refunded` · `recorded` · `queued` · `delivered` · `bounced` · `complained` ·
`suppressed` · `requested` · `completed`

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

## Delivery

- At-least-once. `id` is the dedupe key; every consumer stores it and makes its
  handler idempotent before it goes to production.
- Ordering is per-entity only, never global. If a consumer needs two events in
  order, it correlates on `subject`.
- A consumer that cannot process an event must not block the queue: park it,
  alert, keep going.

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
| `user.created` | the user | Signup completes, before email verification. |
| `user.email_verified` | the user | The verification link is redeemed. |
| `account.created` | the account | A new account/tenant is provisioned. |
| `member.invited` | the account | An invitation is sent. `data.invitation_id` is the thing to act on. |
| `member.joined` | the account | An invitation is accepted. |
| `member.removed` | the account | A member is removed or declines. |
| `member.role_changed` | the account | A role is granted or revoked. `data` carries old and new role. |
| `mfa.enabled` | the user | TOTP enrolled and confirmed. |
| `mfa.disabled` | the user | MFA turned off by the user. |
| `session.revoked` | the user | Password change, "sign out everywhere", or admin revocation. |
| `identity.api_key.created` | the api key | A scoped API token is issued. Long form: `key` is a generic entity (rule 2). |
| `identity.api_key.revoked` | the api key | A scoped API token is revoked or expired. |

### billing

Emitted by `billing`. Listed in `examples/valid/ruby-api.cafaye.yml`.

| Event type | Subject | Emitted when |
| --- | --- | --- |
| `customer.created` | the customer | A billing customer is created for an account. |
| `subscription.started` | the subscription | A subscription becomes active (trial counts as started). |
| `subscription.updated` | the subscription | Plan, quantity, or interval changes. |
| `subscription.canceled` | the subscription | Cancellation takes effect, not when requested. |
| `subscription.past_due` | the subscription | A payment attempt fails; the grace period starts. |
| `payment.succeeded` | the payment | A charge settles. **Money events only; integer minor units.** |
| `payment.failed` | the payment | A charge attempt is declined or errors. |
| `payment.refunded` | the payment | A refund settles, full or partial. |
| `invoice.created` | the invoice | A finalized invoice exists. |
| `usage.recorded` | the account | Metered usage is accepted for a period; `data` carries quantity + window. |

### courier

Emitted by `courier`. Listed in `examples/valid/worker.cafaye.yml`.

| Event type | Subject | Emitted when |
| --- | --- | --- |
| `email.queued` | the notification | A message is accepted for delivery. Emitted on acceptance, not on send, so a queue backlog is visible. |
| `email.delivered` | the notification | The provider accepts the message. |
| `email.bounced` | the notification | The destination hard-bounces. Suppresses further sends to that address. |
| `email.complained` | the notification | The recipient marked it as spam. Suppresses the address immediately. |
| `notification.suppressed` | the recipient | A send was skipped: preference off, address suppressed, or rate limited. The audit trail for a message that was never sent. |

## Registering a new event

1. Pick the type from the grammar and the action vocabulary.
2. Add it to the publisher's `cafaye.yml` `exposes.events`.
3. Add a row to the publisher's catalog sub-section above, with its payload
   fields. Steps 2 and 3 are the same fact stated twice — the suite fails if
   only one of them happens, so land them in one commit.
4. Add the payload schema where D3 says it lives.
5. Add a contract test: the emitted envelope validates against the envelope
   schema, and the payload against the payload schema.
