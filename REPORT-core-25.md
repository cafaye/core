# core-25 — the examples were fiction, and nothing checked

**Branch:** `worker/core-25-examples`
**Gate:** `bin/prime` green at **236/236** (was 230); red proof 18/18, 0 skipped.
Both entry points agree — `tests/.venv/bin/python tests/test_specs.py` prints
`236/236 passed` and `bin/prime --pytest` collects 236.

---

## The finding, and it was worse than reported

Twenty-one examples carried a prefixed ULID. The packet asked me to correct them
to the shape services emit and to check whether a schema *requires* the prefix.
Both done, and the second answer is the important one:

> **No schema requires the prefix. There was no launch blocker.** `tenant_id` and
> `account_id` are `{"type": "string", "maxLength": 64}` and nothing else —
> verified by walking every `pattern` in every file under `schemas/`.

So this was a doc/example fix. But reading the producers turned up **two defects
the prefix was only a symptom of**, and both were invisible to the rule that
existed:

1. **`tenant_id` is not an id at all.** It is an operator-set environment variable
   copied verbatim onto the resource and never parsed —
   `IDENTITY_TENANT_ID` (`identity/internal/telemetry/telemetry.go:537`),
   `COURIER_TENANT_ID` (`courier/lib/courier/telemetry.ex:285`),
   `BILLING_TENANT_ID` (`billing/lib/kit/telemetry.rb:64`). The producers' own
   tests give it `"acme"` and `"tenant-abc"`. Typing it as a uuid would have been
   wrong in the other direction — the next operator to choose a non-uuid name
   would be rejected by core. It is now an **operator label with no underscore**,
   which is the one character nobody typing `acme` produces.

2. **`account_id` on a telemetry resource is emitted by nobody.** It appears
   **zero** times across identity's `telemetry.go`, courier's `telemetry.ex`,
   billing's `kit/telemetry.rb` and muse's `telemetry.py`. identity appends
   service.name/version/instance/environment/`tenant_id`; courier does
   `maybe_put(:deployment)` and `maybe_put(:tenant_id)`; muse's `_resource/1`
   sets `service.name` and `service.namespace` **only**. Meanwhile the same field
   on an event *payload* is a bare uuid in four places. So it is **removed** from
   the resource examples, not respelled — respelling would have taught a
   plausible fiction, which is what a denylist can never catch.

**muse's examples were fiction by another route**: they carried a `tenant_id`,
which muse does not emit either. Removed.

## The smoking gun for the packet's central claim

`billing.payment.succeeded.checkout`'s `client_reference_id` was
`acc_01J9Z8RR7B2QK3M4N5P6Q7R8S9T`. The publisher says otherwise:

- **Production** (`StripeClient#create_checkout_session`,
  `app/services/processor/stripe_client.rb:88`): `client_reference_id:
  customer_reference` — billing's own customer id, a **bare uuid**, asserted as
  `11111111-1111-4111-8111-111111111111` in billing's own production test.
- **Webhook test fixture**: `acc_01J9Z8RR7B2QK3M4N5P6Q7R8S9T`.

The example had the **test fixture's** value, not the code's. That is the packet's
hypothesis, confirmed from both ends, and it is why a denylist was never going to
catch it: the fixture was already in the cafaye shape by accident.

## Why core-24's rule stayed green — two independent reasons

`test_nothing_core_ships_carries_an_id_no_publisher_in_the_fleet_mints` was
correct about everything it looked at.

1. **It never looked at `examples/valid/telemetry/`.** `valid_payload_documents()`
   globs `VALID_PAYLOADS` (`examples/valid/events/`) and stops. Sixteen files,
   invisible, for the whole of core-24.
2. **`IDENTIFIER_FIELD` was `^(?:[a-z][a-z0-9]*_)?ids?$|^subject$`.** The prefix
   segment admits **one** underscore; `client_reference_id` has **two**. So
   billing's `acc_…` in a *valid* example was invisible to the rule written to
   catch exactly that.

Both fixed. A test now asserts the two walkers **between them cover every valid
JSON example in the tree**, so the next directory nobody looks at is a failing
assertion rather than a silent blind spot.

## The deliverable: a positive check, tied to producers

A denylist can only catch what it is pointed at. So: each producer's id type is
transcribed into `PRODUCER_ID_SHAPES` from **a named file at a named commit**, each
identifier field is assigned one of those shapes, and **every identifier value in
every valid example must match the shape recorded for that field of the service
that emits that example**.

Four design points that are the reason it works:

- **Telemetry resource attributes get their own table**
  (`RESOURCE_ATTRIBUTE_SHAPES`). A resource attribute and a payload field under
  the same name are different populations of values — `account_id` is real on one
  and emitted by nobody on the other — and no rule keyed on the field name can
  tell them apart.
- **The walk is in both directions.** A recorded shape no example exercises is a
  fault too. Without that, the ledger is a list, and lists rot.
- **Attribution reads the document, not the path.** `metric.json` is identity's,
  `log.json` is courier's, `span.muse.json` is muse's — all in one directory.
- **A service core has read nothing about is reported, not passed** (`guard` is
  the standing witness), and **a document with no identifier at all is not
  reported**, because a rule that emits unfalsifiable noise is a rule nobody reads.

I recorded `not-emitted` as a shape that matches nothing. That is how the ledger
says "the producers were read and this is not among the things they emit", which
is a different statement from "core has not looked" — and it is what lets the
rule reject an `account_id` on a resource without core knowing in advance what a
tenant's ids look like.

## Red proofs — done, not assumed

Every rule below was shown going red **on this repository's own files**, naming
the exact schema, then restored.

| Defect reintroduced | What went red, and what it said |
|---|---|
| `tnt_01J9Z8R4T7Y2U6K3W8Q5N0P1DG` into `metric.json` | `test_no_example_carries_an_id_shape_its_own_producer_cannot_emit`: *"/resourceAttributes/tenant_id = 'tnt_…' is not identity's operator-label (read from internal/platform/id/id.go): it does not match `^[A-Za-z0-9][A-Za-z0-9.-]*$`"* |
| `acc_…` back into `client_reference_id` | same rule: *"is not billing's uuid (read from app/lib/identifiers.rb)"* |
| an **incidental** prefixed id in an invalid example | `test_a_prefixed_id_may_only_survive_in_an_example_whose_rejection_IS_the_id`, naming the file and saying the value is incidental |

Three bugs in my own work were caught this way rather than shipped:

- `IDENTIFIER_FIELD` missed `client_reference_id` (above).
- My first `operator-label` was `[A-Za-z0-9._-]*`, which **includes the
  underscore and therefore matched the fiction it exists to reject**. The witness
  caught it by failing on a defect it was supposed to name. A shape that accepts
  the fiction is worse than no shape — it reports green on exactly the thing it
  was bought for.
- My `processor-id` pattern admitted one underscore segment and so rejected
  Stripe's real `cs_test_…`, which billing's own fake API builds
  (`format("cs_test_%014d", …)`). Same class of error as `IDENTIFIER_FIELD`: a
  rule that refuses a true fact gets switched off.

## The five uncited schemas — four were citable, and one is a real finding

Both publishers are readable at the commits `fleet.yml` already records: courier's
`a8f15cc` is a reachable ancestor of its HEAD, and **billing's tree was verifiably
AT `7251993`** (clean, HEAD is that commit). So core-25 re-read them.

**The five the packet named were never the interesting subset.** There were
**thirteen** uncited payload schemas. core-25 read and cited **all thirteen** —
courier's five and billing's eight — because citing one billing schema and leaving
seven would be the worst of both worlds.

- **`courier.email.queued` is cited with the fact that its publisher does not
  exist.** `lib/courier/events.ex` at `a8f15cc` has `delivered/1`, `bounced/1`,
  `complained/1`, `suppressed/1` — and **no `queued/1`**. The citation says that
  in the file itself rather than letting it look like provenance.
- **`courier.notification.suppressed`'s builder exists and has no caller**, which
  is a different fact and is recorded as one.
- **`billing.payment.succeeded` is the one that taught core a fictional id** —
  the whole `client_reference_id` story above, now written into that schema's
  `$comment` so the next reader meets the evidence where they need it.
- **muse's one schema stays exempt.** core-25 did not read `metering.py` at muse's
  recorded commit, and citing it would be inventing provenance to satisfy a
  checker — the exact failure D35 was. It is not owed by accident: muse's payload
  has no identifier field, so the id rules have nothing to say about it.

## Three prefixed ids deliberately survive

All under `examples/invalid/`, because there **the fiction is the thing being
rejected**: `format: uuid` refusing `usr_01J9Z8QK5M4N7P2R3T6V8W9X0A` is the entire
demonstration of D35's case, and it is what `examples/invalid/README.md` calls
"the exact value the old pattern required".

Four *other* invalid examples that were rejected only on a **field name** or an
**absence** got their values corrected — `plan_id`, a missing `subject`, an
undeclared `account_id` are rejected whatever the value is, so a prefixed ULID
there was incidental and only taught the fleet fiction. That distinction is now a
**test**, not a judgement call: it asks the schema whether the rejection is
attributable to the id's own shape.

---

## Reported, not fixed — outside this packet

**`billing`'s subscription payloads disagree with core's schemas about two
fields.** Read at billing's recorded commit,
`Subscriptions::Lifecycle#core_payload` (`app/services/subscriptions/lifecycle.rb:353`)
emits `"plan_id" => plan.id` and `"account_id" => customer.owner_id`, and billing's
own tests assert both (`test/services/subscriptions/lifecycle_test.rb:237-238,
268`). **Neither field is in core's
`schemas/events/billing/subscription/started.schema.json`**, and
`examples/invalid/README.md` row 2 for `subscription/started` says billing "has no
`sub_…`, `pln_…` or `acc_…` to send (**D10**)".

So core's schemas reject fields billing emits, and core's invalid example cites a
rule billing violates. That is a real schema-vs-publisher disagreement, but it is
about billing's **payload shape**, not about example id shapes, and resolving it
means deciding what billing's contract is — which is not a call this packet should
make inside a fix for fabricated examples. It is the kind of thing that wants its
own re-read. **Flagging it for the manager rather than resolving it quietly.**

**`service.namespace` on a resource is emitted by muse and refused by core.**
`muse/src/muse/telemetry.py:387` sets it; `traces.schema.json`'s resource
allowlist is closed and does not include it. I found this while correcting the
muse examples, removed my speculative edit, and left it named rather than changing
a contract with six publishers.

---

## Decisions

**[D37](DECISIONS.md#d37-how-does-core-check-that-an-examples-ids-are-the-ids-its-producer-mints)**
is decided and documented with its alternatives, the evidence, and the cost of
flipping. `docs/event-naming.md` now lists four checks instead of three, and
`docs/observability.md` carries the `tenant_id` / `account_id` facts beside the
prohibition they sit under.

### Open decisions

**None new.** No `> DECISION NEEDED (Dn):` callouts were added, and the two items
above are reported for the manager rather than silently resolved — the first needs
a decision about billing's contract, the second about a shared schema, and neither
is core's to make unilaterally inside this packet.

## What I did not do

- **Did not push, merge to `master`, or tag.** Committed to
  `worker/core-25-examples` only.
- **Edited nothing outside `core`.** `identity`, `courier`, `billing` and `muse`
  were read; `git show` at the recorded commits where the working tree had moved.
- **Loosened no assertion.** The gate floor went **up** (230 → 236), and no test
  was skipped or relaxed to reach green. The two rules that would have gone red on
  true facts — `processor-id` and `IDENTIFIER_FIELD` — were fixed in the *rules*,
  which is the opposite of moving the goalposts.
