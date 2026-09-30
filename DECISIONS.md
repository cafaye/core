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