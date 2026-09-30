# Invalid examples — expected failures

One negative example per rule that constrains, per schema. Every file here is
**supposed to fail** validation: the errors below are the contract, not
accidents. If one of these files starts validating, either a schema got looser
or an example stopped being a real mistake — both are review events.

`tests/test_specs.py` asserts the exact `(keyword, path)` pairs listed here, so
the tables cannot drift from the schemas silently. It also walks this directory
and fails on any file whose repo-relative path is missing from this document,
which is what keeps a new negative example from landing as an unreviewed
comment.

Reproduce with:

```
bin/prime                                  # every file here must be reported as rejected
```

or, to see the raw validator output:

```
tests/.venv/bin/python - <<'PY'
import sys; sys.path.insert(0, "tests")
import test_specs as t
for schema, doc in ((t.MANIFEST_SCHEMA_PATH, t.INVALID_MANIFEST),
                    (t.ENVELOPE_SCHEMA_PATH, t.INVALID_ENVELOPE),
                    (t.ENVELOPE_SCHEMA_PATH, t.INVALID_UNTAGGED_ENVELOPE),
                    (t.ENVELOPE_SCHEMA_PATH, t.INVALID_SUBJECTLESS_ENVELOPE)):
    print(doc.name)
    for f in t.failures_for(t.load_document(doc), t.load_schema(schema)):
        print("   ", f)
PY
```

## `examples/invalid/manifest.cafaye.invalid.yml`

Rejected by [`schemas/cafaye.manifest.schema.json`](../../schemas/cafaye.manifest.schema.json).
It is a realistic bad manifest — the mistakes a service actually ships with,
all at once — not a single deliberate typo.

| # | Field | Keyword | Why it is rejected |
| --- | --- | --- | --- |
| 1 | `name: Billing_Service` | `pattern` | Names are lowercase kebab-case. The `name` is also the repo name, the event `source` and the routing prefix, so it cannot carry case or underscores. |
| 2 | `language: python3` | `enum` | Not a cafaye language. The enum is `go`, `ruby`, `elixir`, `python`, `typescript`, `rust`, `spec`. |
| 3 | `core: ^0.1` | `pattern` | A core constraint must be a full `MAJOR.MINOR.PATCH`. A missing patch version silently widens the range. |
| 4 | `exposes.api: ./openapi.yaml` | `pattern` | Must be a repository-relative path with no `./` prefix, no absolute path and no URL — the path is resolved inside the repo by `caf` and by contract tests. |
| 5 | `exposes.events[0]: user.Created` | `pattern` | Two violations in one value. The type is **two** segments, and the grammar is exactly `<service>.<entity>.<action>`; and `Created` is not lowercase snake_case, which would fork the topic away from every existing `identity.user.created` subscription. |
| 6 | `repository.url: https://github.com/…` | `pattern` | SSH remotes only, for anything cafaye or anywaye owns (PLAN.md §1). |
| 7 | `repository.defaultBranch: main` | `const` | The cafaye primary branch is `master` everywhere. |
| 8 | `ports:` | `additionalProperties` | Undeclared top-level key. Manifests are closed on purpose: a key core does not know about cannot be validated, and cannot be enforced. Ports are deployment configuration, not contract surface. |

## `examples/invalid/event-envelope.invalid.json`

Rejected by [`schemas/event-envelope.schema.json`](../../schemas/event-envelope.schema.json).
JSON has no comment syntax, so this table is the expected-failure note for
this file.

| # | Field | Keyword | Why it is rejected |
| --- | --- | --- | --- |
| 1 | *(absent)* `specversion` | `required` | The envelope dialect is not optional. A consumer that cannot tell which envelope it is reading cannot decode the rest. |
| 2 | `id: "usr-01J9Z8QK5M4N7P2R3T6V8W9X0A"` | `format` | `id` is a UUID, not a business id. Consumers dedupe on `id`, and business ids are reused across entities — they belong in `subject`/`data`. |
| 3 | `type: "identity.user.account.created"` | `pattern` | Four segments. The grammar is exactly three: there is no room for a container level. |
| 4 | `subject: "user usr_01J9Z8QK5M4N7P2R3T6V8W9X0A"` | `pattern` | `subject` is a bare identifier, never prose. A space also breaks per-entity ordering guarantees, which correlate on this value. |
| 5 | `time: "2026-13-45T99:99:00Z"` | `format` | Not a valid RFC3339 timestamp (month 13, hour 99). |
| 6 | `trace_id: "0af7651916cd43dd8448eb211c80319c"` | `additionalProperties` | Undeclared envelope attribute. The envelope is closed: transport metadata travels in transport headers, so a producer that needs it added must go through a spec change, not a private field. |

## `examples/invalid/event-envelope.untagged.invalid.json`

Rejected by [`schemas/event-envelope.schema.json`](../../schemas/event-envelope.schema.json).
Every field is legal except the `type`, which is the mistake the file exists to
pin down — the pre-v0.2 short form, still in every subscription from before the
grammar change.

| # | Field | Keyword | Why it is rejected |
| --- | --- | --- | --- |
| 1 | `type: "user.created"` | `pattern` | Two segments. There is no short form: the publisher's own name is the first segment of every event type, because an unprefixed type says what changed and not who changed it. `identity.user.created`, not `user.created`. |

## `examples/invalid/event-envelope.subjectless.invalid.json`

Rejected by [`schemas/event-envelope.schema.json`](../../schemas/event-envelope.schema.json).
A well-formed envelope that simply forgot `subject` — the failure mode of
writing the field from an optional CloudEvents mental model.

| # | Field | Keyword | Why it is rejected |
| --- | --- | --- | --- |
| 1 | *(absent)* `subject` | `required` | `subject` is required, not optional. It is the correlation key that carries per-entity ordering, and an event with no single entity uses the literal `platform` — a required field with a reserved value, never a missing one. |

## `examples/invalid/events/identity/user/created.data.json`

Rejected by [`schemas/events/identity/user/created.schema.json`](../../schemas/events/identity/user/created.schema.json).
A payload with a field the schema never declared and one it requires, missing.
This is the shape of a payload that grew in the publisher's code and never came
back to core.

| # | Field | Keyword | Why it is rejected |
| --- | --- | --- | --- |
| 1 | *(absent)* `email` | `required` | The address is not optional — a consumer that cannot send verification mail has nothing to do with this event. |
| 2 | `favourite_colour` | `additionalProperties` | Undeclared payload field. Payload schemas are closed, so an unknown field is a contract difference to resolve in core, not something a publisher adds in a hurry. |

## `examples/invalid/events/billing/subscription/started.data.json`

Rejected by [`schemas/events/billing/subscription/started.schema.json`](../../schemas/events/billing/subscription/started.schema.json).
The tenancy field is missing and a money field arrived that no schema declares.

| # | Field | Keyword | Why it is rejected |
| --- | --- | --- | --- |
| 1 | *(absent)* `account_id` | `required` | Without the account, the subscription cannot be correlated with the identity-side account, and every query downstream needs a lookup that will not exist. |
| 2 | `amount_minor` | `additionalProperties` | Undeclared money field. Amounts belong to the charge that is actually attempted, which is `billing.payment.succeeded`; a price here would be a second, competing source of truth for what a plan costs. |

Note on the `format` assertions: `jsonschema` silently skips `format` checks
unless a format implementation is installed. `tests/requirements.txt` pins
`rfc3339-validator` precisely so the RFC3339 assertion above cannot pass
vacuously — without it, row 5 would report no violation and this example would
look valid. The `date` format in the fleet case below is checked by
`jsonschema` itself, so it needs nothing extra; the same would not be true of an
RFC3339 assertion, which is why that one is pinned.

## `examples/invalid/fleet.invalid.yml`

Rejected by [`schemas/fleet.schema.json`](../../schemas/fleet.schema.json).
A fleet declaration written by a human, with the mistakes a human makes: the
namespace rule, the wrong manifest path, the wrong branch, a short sha, the
two-segment event types courier shipped, an undeclared key and a read date that
is not a date.

| # | Field | Keyword | Why it is rejected |
| --- | --- | --- | --- |
| 1 | `spec: "0.1"` | `const` | Transcribed against the wrong spec. The field exists so a reader can tell how stale the numbers are, and a wrong value answers that confidently and wrongly. |
| 2 | `readOn: "not-a-date"` | `format` | The one thing that makes `fleet.yml` checkable rather than a claim is that it says when it was true. A value that is not a date has no truth to check. |
| 3 | `name: Billing_Service` | `pattern` | Names are lowercase kebab-case. A fleet entry's name is matched against the first segment of every type the service publishes, so an underscore here silently disables that comparison instead of failing it. |
| 4 | `manifest: manifest.yml` | `const` | Every cafaye service names its manifest `cafaye.yml`. A linter resolving a service's declaration needs one pinned path, not a convention it has to know. |
| 5 | `branch: main` | `const` | The cafaye primary branch is `master` everywhere (PLAN.md §1). A declaration read from any other branch is not a declaration about the fleet. |
| 6 | `sourceCommit: "5475352"` | `pattern` | A short sha is enough to read by and not enough to re-read. The point of recording a commit is that the next reader can re-read the exact bytes the claim was made from. |
| 7 | `events[0]: billing.customer.Created` | `pattern` | `Created` is not lowercase snake_case, which forks the topic away from every existing subscription to the type. |
| 8 | `events[1]: plan.created` | `pattern` | Two segments: no service prefix. This is courier's mistake five times over, and it is the reason `fleet.yml` exists rather than a checklist — the difference between catching it here and shipping it to master. |
| 9 | `publishes:` | `additionalProperties` | Undeclared key. A fleet declaration is closed for the same reason a manifest is: a key the schema does not know about cannot be validated, and a linter that ignores it reports a clean fleet. |

## `examples/invalid/events/courier/email/queued.data.json`

Rejected by [`schemas/events/courier/email/queued.schema.json`](../../schemas/events/courier/email/queued.schema.json).
The notification id is missing and a credential leaked into a fan-out. Both are
real: courier's own `Courier.DeliverTest` asserts the second (`refute "url" in
Map.keys(event.data)`), which is why the shape is here rather than left to
review.

| # | Field | Keyword | Why it is rejected |
| --- | --- | --- | --- |
| 1 | *(absent)* `message_id` | `required` | A queued message with no notification id cannot be joined to its `courier.email.delivered`, which is the entire reason the event exists: measuring how long a message waited. |
| 2 | `url` | `additionalProperties` | A verification link is a credential, and this envelope goes to every subscriber on the bus. It is in the caller's payload, not in the event. |

## `examples/invalid/events/courier/email/delivered.data.json`

Rejected by [`schemas/events/courier/email/delivered.schema.json`](../../schemas/events/courier/email/delivered.schema.json).
The recipient is missing and a provider's own message id turned up — the field
that exists in courier's test fixture and in no line of courier's code.

| # | Field | Keyword | Why it is rejected |
| --- | --- | --- | --- |
| 1 | *(absent)* `user_id` | `required` | Without the recipient, a consumer cannot answer "who got this?" without asking courier, and cannot correlate the send with anything identity knows about. |
| 2 | `provider_id` | `additionalProperties` | A field the publisher never emits. `Courier.EventsTest` carries `provider_id` in its fixture map, but `Courier.Deliver` builds the payload from four values and one of them is not this. Declaring it in core would be a contract that promises a value no message carries. |

## `examples/invalid/events/courier/email/bounced.data.json`

Rejected by [`schemas/events/courier/email/bounced.schema.json`](../../schemas/events/courier/email/bounced.schema.json).
The address that bounced is missing, and a provider's SMTP diagnostic arrived
anyway.

| # | Field | Keyword | Why it is rejected |
| --- | --- | --- | --- |
| 1 | *(absent)* `email` | `required` | The hard-bounce suppression list is keyed on the address. A bounce without one is an event nobody can act on, which is the worst kind. |
| 2 | `smtp_response` | `additionalProperties` | The provider's diagnostic is real and belongs in the payload eventually — but courier has no receiver for it yet, and core does not declare a field no publisher emits. It arrives with the webhook handler, and a new optional field is a patch. |

## `examples/invalid/events/courier/email/complained.data.json`

Rejected by [`schemas/events/courier/email/complained.schema.json`](../../schemas/events/courier/email/complained.schema.json).
The recipient's display name is in a fan-out payload, and the message type is
gone.

| # | Field | Keyword | Why it is rejected |
| --- | --- | --- | --- |
| 1 | *(absent)* `notification_type` | `required` | A complaint suppresses every type immediately, so the type is not what a consumer acts on — it is what they tell the user they objected to. Without it the event says a person was angry and not about what. |
| 2 | `name` | `additionalProperties` | The display name comes from the mail payload, and `Courier.DeliverTest` asserts it is not in the event. It is the recipient's name on every subscriber's bus, for a message about a complaint they did not raise. |

## `examples/invalid/events/courier/notification/suppressed.data.json`

Rejected by [`schemas/events/courier/notification/suppressed.schema.json`](../../schemas/events/courier/notification/suppressed.schema.json).
A `message_id` on an event about a send that never happened — the payload is the
`delivered` one with a `reason` bolted on.

| # | Field | Keyword | Why it is rejected |
| --- | --- | --- | --- |
| 1 | *(absent)* `reason` | `required` | The whole event is the reason. A suppression with no reason is indistinguishable from a delivery that was lost, and the two want opposite responses. |
| 2 | `message_id` | `additionalProperties` | Nothing was rendered, addressed or sent, so there is no notification and no id for one. This is the mistake the catalog's subject row exists to prevent — the entity is the recipient — and it is why this payload is not the `delivered` payload with one more field. |

## `examples/invalid/events/muse/tokens/consumed.data.json`

Rejected by [`schemas/events/muse/tokens/consumed.schema.json`](../../schemas/events/muse/tokens/consumed.schema.json).
A nameless model, and the price table that produced the cost travelling with it.

| # | Field | Keyword | Why it is rejected |
| --- | --- | --- | --- |
| 1 | `model: ""` | `minLength` | A blank model id is not a model. Every consumer of this event groups spend by model, and a blank groups every unrouted call together with nothing. |
| 2 | `input_micros`, `output_micros` | `additionalProperties` | The per-1k price is real, it is in the publisher's own `Price` object, and it is deliberately **not** in the event: a price moves, and a payload that carries one says the cost and the price were true at the same instant. The cost is already here. A price in the payload is a field every consumer would read as authoritative and that is wrong the next time the price table changes. |

## `examples/invalid/events/billing/customer/created.data.json`

Rejected by [`schemas/events/billing/customer/created.schema.json`](../../schemas/events/billing/customer/created.schema.json).
The owner is gone and a flat `account_id` turned up in its place — the shape a
consumer would ask for, and one billing cannot produce.

| # | Field | Keyword | Why it is rejected |
| --- | --- | --- | --- |
| 1 | *(absent)* `owner` | `required` | `owner` is the only field on the payload that says who pays. Without it a customer cannot be attached to a user or an account, and no other field fills the gap. |
| 2 | `account_id` | `additionalProperties` | A cafaye account id, flat. The owner is `{type, id}` and the id is a uuid, because the owner may be a `User` as well as an `Account` and the payload has to say which. A flat `account_id` is the third vocabulary in a fleet that already has two (**D7**), and it is not one billing emits. |

## `examples/invalid/events/billing/plan/created.data.json`

Rejected by [`schemas/events/billing/plan/created.schema.json`](../../schemas/events/billing/plan/created.schema.json).
Money at the top level instead of inside `price` — the flattening that turns a
price into two fields nobody can require together.

| # | Field | Keyword | Why it is rejected |
| --- | --- | --- | --- |
| 1 | *(absent)* `price` | `required` | Without a price the plan is a name and a cadence. Splitting it into `amount_minor` and `currency` at the top level is how a consumer ends up reading a price with no currency attached. |
| 2 | `amount_minor`, `currency` | `additionalProperties` | Undeclared money fields at the root. A currency is not a property of a plan; it is a property of an amount, and nesting it is what stops `1900` from ever being read as dollars, yen or anything else. |

## `examples/invalid/events/billing/plan/updated.data.json`

Rejected by [`schemas/events/billing/plan/updated.schema.json`](../../schemas/events/billing/plan/updated.schema.json).
The plan's own id is missing and the payload carries a diff — the shape most
tempting for an `updated` event, and the one that makes a consumer merge state.

| # | Field | Keyword | Why it is rejected |
| --- | --- | --- | --- |
| 1 | *(absent)* `id` | `required` | The plan. Without it the event cannot be attributed, and a `billing.plan.updated` nobody can attach to a plan is a plan that changed somewhere. |
| 2 | `changed_fields` | `additionalProperties` | A list of what moved. The payload is the plan's whole current state and there is no diff: a consumer replaces its copy, and a `changed_fields` list would make it merge one — into state that can drift from the publisher's on every field the list forgot. The publisher also only emits this event when something really changed, so the list is redundant as well as wrong. |

## `examples/invalid/events/billing/subscription/started.data.json`

Rejected by [`schemas/events/billing/subscription/started.schema.json`](../../schemas/events/billing/subscription/started.schema.json).
The subscription is gone, and the cafaye-prefixed ids that core's previous
version of this schema *required* are in its place. This is the schema rewrite
recorded as **D10**, and this file is the mistake it exists to prevent.

| # | Field | Keyword | Why it is rejected |
| --- | --- | --- | --- |
| 1 | *(absent)* `subscription_id` | `required` | The subscription, and the envelope's `subject`. Without it there is nothing to correlate, nothing to join a later `updated` or `canceled` to, and nothing a consumer can act on. |
| 2 | `plan_id`, `account_id` | `additionalProperties` | The two fields v0.2's shipped schema required. billing has no subscriptions table, so it has no `sub_…`, `pln_…` or `acc_…` to send — and a schema that requires them describes a world billing does not live in. `price_id` and `customer_id` are the values it does send (**D10**). |

## `examples/invalid/events/billing/subscription/updated.data.json`

Rejected by [`schemas/events/billing/subscription/updated.schema.json`](../../schemas/events/billing/subscription/updated.schema.json).
The customer is missing and a delta arrived instead — the second half of the
same merge trap as `plan.updated`.

| # | Field | Keyword | Why it is rejected |
| --- | --- | --- | --- |
| 1 | *(absent)* `customer_id` | `required` | A change nobody is charged. Without the customer, an update cannot be attributed to a subscription's owner, which is the only reason anyone would want to know the quantity changed. |
| 2 | `delta` | `additionalProperties` | `{quantity: 1}` — what moved, not where it is now. Applying a delta to state the consumer may not have (replay, out-of-order delivery, a consumer that started reading halfway) silently produces a wrong quantity. The payload is the processor's current state; there is nothing to merge. |

## `examples/invalid/events/billing/subscription/canceled.data.json`

Rejected by [`schemas/events/billing/subscription/canceled.schema.json`](../../schemas/events/billing/subscription/canceled.schema.json).
The final status is missing, and the moment somebody *asked* for the cancellation
turned up next to the moment it happened.

| # | Field | Keyword | Why it is rejected |
| --- | --- | --- | --- |
| 1 | *(absent)* `status` | `required` | The subscription's final state. This type exists to say a cancellation took effect, and `canceled_at` alone says when without saying what the subscription then was. |
| 2 | `cancel_requested_at` | `additionalProperties` | The request, not the effect — and the whole distinction this event is named for. A consumer that acts on a request stops serving a subscription that is still running and still paid for; the catalog row for this type says so in one clause. If the platform wants the request time it belongs in a request, not smuggled into the effect. |

## `examples/invalid/events/billing/payment/succeeded.data.json`

Rejected by [`schemas/events/billing/payment/succeeded.schema.json`](../../schemas/events/billing/payment/succeeded.schema.json).
Three faults in one: the amount is gone, a cafaye plan id turned up, and the
payload claims to be *both* source shapes at once — which is the mistake the
`oneOf` exists to make impossible.

| # | Field | Keyword | Why it is rejected |
| --- | --- | --- | --- |
| 1 | *(absent)* `amount` | `required` | The money. A settled charge with no amount is an event a consumer can log and not reconcile, which is the same as an event that was never published. |
| 2 | `plan_id` | `additionalProperties` | A cafaye plan id, which billing does not have (**D10**). The processor's is `price_id` on a subscription payload; on a payment there is no plan to name. |
| 3 | `invoice_id` *and* `checkout_session_id` | `oneOf` | A charge is either invoice-backed or Checkout-backed, never both. Flattening the two shapes lets this through, and then every consumer has to work out which it got — by checking for a field that may be present and may be null, which is the ambiguity `oneOf` removes (**D11**). |

## `examples/invalid/events/billing/payment/failed.data.json`

Rejected by [`schemas/events/billing/payment/failed.schema.json`](../../schemas/events/billing/payment/failed.schema.json).
The invoice is missing, and a second amount arrived — the one that says zero.

| # | Field | Keyword | Why it is rejected |
| --- | --- | --- | --- |
| 1 | *(absent)* `invoice_id` | `required` | The invoice whose collection failed. Without it a decline cannot be attributed to a charge, retried, or escalated — and a failed payment with no identity is a failed payment with no follow-up. |
| 2 | `amount_paid` | `additionalProperties` | A second money field, and the dangerous one: on a failed charge it is `0`, which is truthy and reads as "nothing was collected" to a consumer that wants the charge size. The publisher's own comment names this exact bug — the naive `amount_paid \|\| amount_due` fallback reports a declined 29.00 as a settled 0.00. `amount` is the amount due; there is no second amount. |

## Adding a negative case

A new `examples/invalid/` file needs, in the same commit: the file itself, its
row in the table above, and an `assert_keywords` entry in
`tests/test_specs.py` — a negative example that no test asserts is a comment,
and a table row that no file backs is a rule nobody is enforcing.
