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
| 10 | `telemetry.endpointVariable: muse-otel-endpoint` | `pattern` | The one contract a self-hoster is told to set is `<SERVICE>_OTEL_ENDPOINT` — **uppercase**. A lower-case or hyphenated spelling is an environment variable nothing reads, and six services each spelling it their own way is the exact failure core's observability spec exists to prevent. |
| 11 | `telemetry.signals[1]: telepatry` | `enum` | Not one of the three OTel signals. A closed enum is what lets `caf contract lint` tell a service which signals a collector config has to accept, and a typo here would otherwise be a signal nobody configures. |
| 12 | `telemetry.probes: maybe` | `type` | Not a boolean. Whether a service serves HTTP is a fact with two answers, and `maybe` is how "nobody has checked" gets written down. |

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

<!-- telemetry block: added by the observability packet -->

Added by the observability packet. Every file here is a mistake the directive
names, and the reason each one matters is in [docs/observability.md](../../docs/observability.md).

## `examples/invalid/telemetry/span-naming.identifier.invalid.json`

Rejected by [`schemas/telemetry/span-naming.schema.json`](../../schemas/telemetry/span-naming.schema.json).
A span name with a user id interpolated into the last segment — the mistake that
reads as diligence in a code review.

| # | Field | Keyword | Why it is rejected |
| --- | --- | --- | --- |
| 1 | `name: "muse.user.usr_01j9z8qk5m4n7p2r3t6v8w9x0a"` | `pattern` | A span name is `<service>.<operation>[.<target>]`, and a segment is at most fifteen characters. `usr_01j9z8qk5m4n7p2r3t6v8w9x0a` is thirty-two. The length bound is doing the work, not a cafaye-id pattern: a name that interpolates a value is one span per value, and a trace backend is a search engine whose index stops being useful well before anyone reports an error. |
| 2 | `target: "usr_01j9z8qk5m4n7p2r3t6v8w9x0a"` | `pattern` | Same value in the field that exists to disambiguate the operation. A target is a *class* of thing (`provider`, `db`, `queue`), never an instance of one. |

## `examples/invalid/telemetry/metric.tenant-id-measurement.invalid.json`

Rejected by [`schemas/telemetry/metrics.schema.json`](../../schemas/telemetry/metrics.schema.json).
The failure mode the whole prohibition exists for, in the shape a well-meaning
engineer writes on a Friday.

| # | Field | Keyword | Why it is rejected |
| --- | --- | --- | --- |
| 1 | `measurementAttributes.tenant_id` | `not` | **The specific failure the directive names.** OpenTelemetry caps a metric stream at 2000 distinct attribute combinations and, on overflow, folds everything into one `otel.metric.overflow=true` point and **drops every measurement attribute**. Totals stay correct and every per-dimension breakdown silently undercounts — the dashboard renders, the total looks right, the breakdown is wrong, and nothing anywhere reports an error. `tenant_id` is on the resource list, which is exempt from the cap and survives on the overflow point; the prohibition is a prohibition *with a destination*. |
| 2 | `measurementAttributes.tenant_id` | `additionalProperties` | Refused twice on purpose. It is absent from the allowlist *and* named in a `not`, so adding it to the allowlist later does not quietly succeed. A rule enforced once is a rule a well-meaning commit can undo. |

The rest of the document is legal — the same metric with
`measurementAttributes: {http.route: /v1/users/{id}}` validates, which
`test_a_tenant_id_measurement_attribute_is_rejected` asserts, so this example is
about `tenant_id` and not about the metric being malformed.

## `examples/invalid/telemetry/redaction.prompt-attribute.invalid.json`

Rejected by [`schemas/telemetry/redaction.schema.json`](../../schemas/telemetry/redaction.schema.json).
An allowlist with a prompt attribute on it — the single hardest rule in the
packet, in the shape it actually arrives.

| # | Field | Keyword | Why it is rejected |
| --- | --- | --- | --- |
| 1 | `allowed[2]: "llm.prompt"` | `not` | The redaction boundary is encoded as an **allowlist**, default-deny, so a span attribute that is not on the list is not emitted. "Don't log prompts" in prose has been tried across this fleet and does not hold; the realistic leak is not an attacker, it is a well-meaning `llm.prompt` added in six months by someone debugging a routing decision, in a service whose prompts are other customers' data. The whole file is a valid policy except this one name, which is the point: a policy is not safe because its author was careful. |

Note the other half: the same example still declares the correct
`llmCallAttributes` — model, token counts, latency, finish reason. The positive
side is in the schema because a policy that only says what may **not** be
recorded is not implementable; somebody debugging a routing decision needs to
know what to reach for instead.

## `examples/invalid/telemetry/otel-endpoint.buffered.invalid.json`

Rejected by [`schemas/telemetry/otel-endpoint.schema.json`](../../schemas/telemetry/otel-endpoint.schema.json).
A "disabled" exporter that is not actually disabled.

| # | Field | Keyword | Why it is rejected |
| --- | --- | --- | --- |
| 1 | `noOp.buffering: "ring"` | `const` | A queue that accepts spans and retains them is a memory leak with a telemetry-shaped trigger: requests succeed normally while the heap fills with spans nobody will ever read. A disabled path that still dials out is worse than no telemetry support at all. |
| 2 | `noOp.retry: "exponential-backoff"` | `const` | A retry loop against an endpoint that is not there is a thread waking on a timer for the life of the process — and it is invisible in every dashboard, because nothing is being recorded. |
| 3 | `noOp.warnings: "per-attempt"` | `const` | A warning per export attempt fills the service's own log store with the news that telemetry is off. That is how a self-hoster discovers turning telemetry off is unsupported, which is the exact opposite of what an escape hatch is for. |
| 4 | `noOp.startupCost: "dial"` | `const` | A dial at boot makes a service's availability depend on a component that ships with the product rather than with the deployment. |
| 5 | `disabledBy` | `minItems` | Only three entries, and `OTEL_LOGS_EXPORTER` is missing. The floor exists so a declaration cannot document a no-op that covers only some signals — a service that still phones home for metrics is a failure discovered by a customer's invoice rather than by a test. |

## `examples/invalid/telemetry/probes.empty-readyz.invalid.json`

Rejected by [`schemas/telemetry/probes.schema.json`](../../schemas/telemetry/probes.schema.json).
A `readyz` that checks nothing — the failure the probes schema exists to
prevent, and the one that is invisible because the endpoint returns 200.

| # | Field | Keyword | Why it is rejected |
| --- | --- | --- | --- |
| 1 | `readyz.checks: []` | `minItems` | `readyz` **actually checks dependencies**. Without it a load balancer cheerfully routes traffic into a service whose database is gone, and every health dashboard shows green. darkroom is the pattern to standardise on: `/healthz` never touches a dependency, `/readyz` really runs `select 1`. |
| 2 | `healthz.checks: []` | — | **Valid, and deliberately.** Liveness is *unconditional*: a liveness probe that fails on a dependency tells the orchestrator to restart a process that is fine, turning a database outage into a fleet-wide crash loop and destroying the evidence needed to diagnose it. The schema pins this with `maxItems: 0`, so a `healthz` that starts consulting the database cannot validate either. |

## `examples/invalid/telemetry/error-type.undeclared.invalid.json`

Rejected by [`schemas/telemetry/traces.schema.json`](../../schemas/telemetry/traces.schema.json).
**The example this whole vocabulary exists for.** A span that is correct in every
other respect, whose error class is well-shaped and not in the fleet's list.

| # | Field | Keyword | Why it is rejected |
| --- | --- | --- | --- |
| 1 | `attributes.error.type: "user_42_email_invalid"` | `enum` | `user_42_email_invalid` is snake_case, is twenty-two characters, and satisfies the pattern and the length cap perfectly — which is exactly why it is the right example. It is a class with a **user's id interpolated into it**, and on the metric side that is one series per user against the same 2000-combination cap `tenant_id` blows, with the same silent undercount and the same rendering dashboard. Nothing about the *shape* of a value can catch this; only a closed set can. `test_a_well_shaped_but_undeclared_error_class_is_rejected` asserts the value passes the shape and the cap **before** asserting the rejection, so it cannot pass because the pattern caught it — it passes only if the vocabulary did. |

## `examples/invalid/telemetry/metric.error-type-undeclared.invalid.json`

Rejected by [`schemas/telemetry/metrics.schema.json`](../../schemas/telemetry/metrics.schema.json).
The same undeclared class, on the signal where it actually does the damage. Traces
survive an unbounded value as an expensive index; a metric does not.

| # | Field | Keyword | Why it is rejected |
| --- | --- | --- | --- |
| 1 | `measurementAttributes.error.type: "user_42_email_invalid"` | `enum` | Byte-identical `enum` to the traces and logs signals. They have to be: a class that means one thing on traces and another on metrics is three taxonomies wearing one name, and it is also what makes the semconv rule that `error.type` is *identical* on a span and on its metric for the same operation enforceable — no JSON Schema can compare two documents, so the coupling has to be structural. |

## `examples/invalid/telemetry/span.error-status-no-type.invalid.json`

Rejected by [`schemas/telemetry/traces.schema.json`](../../schemas/telemetry/traces.schema.json).
`status.code: "error"` with no class — the claim with nothing behind it.

| # | Field | Keyword | Why it is rejected |
| --- | --- | --- | --- |
| 1 | *(absent)* `attributes.error.type` | `required` | A status of `error` is a claim that the operation failed, and the fleet-wide "is this an error" filter reads that claim. A span that makes it without saying what went wrong is counted by every error-rate query and cannot be explained by any of them — the wall of ungrouped text the user asked whether cafaye could avoid. core-04 stated this obligation in a `description`; with the attribute deleted, `span.muse.json` still validated, so this is a constraint now rather than a sentence. |

## `examples/invalid/telemetry/span.success-with-error-class.invalid.json`

Rejected by [`schemas/telemetry/traces.schema.json`](../../schemas/telemetry/traces.schema.json).
A successful span carrying an error class — the other direction of the same rule.

| # | Field | Keyword | Why it is rejected |
| --- | --- | --- | --- |
| 1 | `attributes.error.type: "timeout"` with `status.code: "ok"` | `const` | **The absence is the load-bearing marker, not an omission.** On a duration histogram the samples carrying the class are the errors and every other sample is a success; that is how error rate is computable without putting a message in a label. So a success that carries one does not add noise — it moves the **numerator**, and the error rate becomes a number nobody can trust. |

## `examples/invalid/telemetry/span.status-mirror-disagrees.invalid.json`

Rejected by [`schemas/telemetry/traces.schema.json`](../../schemas/telemetry/traces.schema.json).
`otel.status_code: "ERROR"` on a span whose own status says `ok`.

| # | Field | Keyword | Why it is rejected |
| --- | --- | --- | --- |
| 1 | `attributes.otel.status_code: "ERROR"` with `status.code: "ok"` | `const` | `otel.status_code` exists so a log-indexed query can filter without parsing the span, and `status.code` is the field of record. The moment the mirror can disagree with the field, a query that reads the mirror answers a different question from the predicate the fleet-wide view uses — and nothing anywhere reports that they differ. This is not a separate rule: without it the obligation in the row above is about a span with two statuses, which has no status to be obliged. |

<!-- SLO block: added by the SLO and error-budget packet -->

Added by the SLO packet. Each file is one mistake the rulings name, and each
one differs from its valid sibling in as few lines as the mistake takes — see
[docs/slo.md](../../docs/slo.md).

## `examples/invalid/telemetry/slo.perfect.invalid.yaml`

Rejected by [`schemas/telemetry/slo.schema.json`](../../schemas/telemetry/slo.schema.json).
The SLO nobody can keep: an objective of 100% and a thirty-day period. Both are
the same mistake — a number chosen to look safe rather than chosen to be met —
and both are the numbers a service reaches for by accident, because they are
what a template's defaults usually are.

| # | Field | Keyword | Why it is rejected |
| --- | --- | --- | --- |
| 1 | `objective: 100` | `exclusiveMaximum` | An objective of 100% has an error budget of **zero**, so no burn rate is worth interrupting anyone for and the alert can only ever be *reacted to* — noticed after the fact rather than paged before it. `exclusiveMaximum`, not `maximum`, is the whole rule (R8); with a comment instead of a keyword, deleting the comment deletes it. |
| 2 | `period: 30d` | `const` | Thirty days contains 4.3 weekends, so the same weekend maintenance costs a different fraction of the budget every month and the error budget stops being comparable to itself (R3). 28 days is integral weeks: always four weekends. A period nobody wrote down is a period somebody assumed, and Sloth's own default is `30d`, so the assumption has to be refused rather than inherited. |

## `examples/invalid/telemetry/slo.page-on-low-tier.invalid.yaml`

Rejected by [`schemas/telemetry/slo.schema.json`](../../schemas/telemetry/slo.schema.json).
A `low` SLO that pages. **Nothing else about this document is wrong** — which is
what makes it the example: the mistake that reaches production is the one made
in the one field nobody reads carefully.

| # | Field | Keyword | Why it is rejected |
| --- | --- | --- | --- |
| 1 | `tier: low` with `page_alert.disable: false` | `const` | **The tier alone decides whether a page is generated**, and the schema derives the switch rather than letting the service choose it (R4). The cost is not the page: the self-hoster who has to mute a 3am page about a twenty-user deployment has also muted the `critical` SLO on the same service, and the whole instrument is gone in one gesture. |

## `examples/invalid/telemetry/slo.window-override.invalid.yaml`

Rejected by [`schemas/telemetry/slo.schema.json`](../../schemas/telemetry/slo.schema.json).
A service that carries its own burn-rate windows. Sloth accepts
`--slo-period-windows-path` precisely so a project can, and the resulting rules
look completely ordinary — which is the problem: two dashboards that both say
"error budget" and disagree about the threshold.

| # | Field | Keyword | Why it is rejected |
| --- | --- | --- | --- |
| 1 | `windows:` | `additionalProperties` | The window catalog is pinned **once, in core** (R2), for the whole fleet, and a per-service override is how the fleet ends up with two definitions of a burn rate. `additionalProperties: false` rather than a bespoke rule, because an undeclared key is exactly what this object refuses everywhere else. |

## `examples/invalid/telemetry/slo-metrics.denylisted.invalid.json`

Rejected by [`schemas/telemetry/slo-metrics.schema.json`](../../schemas/telemetry/slo-metrics.schema.json).
The catalogue with an infrastructure metric in it — `node_memory_usage_bytes`
counted as the invoice SLI's denominator.

| # | Field | Keyword | Why it is rejected |
| --- | --- | --- | --- |
| 1 | `slis.invoice_computed.totalMetric: "node_memory_usage_bytes"` | `const` | Not the metric this SLI counts. The whole catalogue is `const` per field, so a service cannot invent a numerator. |
| 2 | the same field | `not` | **Refused twice on purpose**, as `metrics.schema.json` refuses `tenant_id` twice: the `const` says it is not this SLI's metric and the `not` says it is not *any* SLI's metric. A rule enforced once is a rule a well-meaning commit undoes — adding an entry for "CPU headroom" would otherwise validate on the strength of a `const` nobody re-read. An SLO on a CPU is not an SLO on behaviour (R6). |

The second denylist — the unbounded dimensions — is the other half of the same
`not`, and it is why the two lists are separate properties with separate
reasons: `metrics.schema.json` already bars `tenant`, `user_id`, `account_id`
and `request_id` on the 2000-combination-cap grounds, and the reasons a reader
needs are *different*. See
[`docs/slo.md`](../../docs/slo.md#two-denylists-because-there-are-two-reasons).

## Adding a negative case

A new `examples/invalid/` file needs, in the same commit: the file itself, its
row in the table above, and an `assert_keywords` entry in
`tests/test_specs.py` — a negative example that no test asserts is a comment,
and a table row that no file backs is a rule nobody is enforcing.
