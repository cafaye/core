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

## D6: where do open decisions live?

Raised while reconciling the payload schemas. Affects
[`docs/event-naming.md`](docs/event-naming.md) and
`tests/test_specs.py::test_no_open_decision_callouts_remain_in_the_docs`.

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