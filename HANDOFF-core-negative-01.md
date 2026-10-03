# HANDOFF — core-negative-01

**For the successor.** Worktree `/Users/kaka/Code/any/moon/cafaye/wt-m39-core-negative-01`,
branch `worker/core-negative-01`, base `acf6d11`, four commits, green at
`254/254`. Nothing pushed, nothing outside the worktree committed. Full reasoning
in `REPORT-core-negative-01.md`.

---

## Your first move

**Migrate the three shapes from core's checker into kit's live proof, per
RLS'd table — do NOT start with pgTAP.**

The reference proposal (pure pgTAP, one `.sql` file per RLS'd table, identical for
all six languages, with `cafaye/tests/_helpers.sql` and `set local role` +
`set local request.jwt.claim.sub`) is the destination. But the **cheapest next
move that changes a real fleet outcome** is much smaller, and you should do it
first:

> **kit's `templates/database/tenancy/isolation.sql` proves the SUBSTRATE on a
> fixture table (`pg_temp.cafaye_probe_things`). It does not prove any service's
> REAL RLS'd table.** Every service that adopts the substrate gets the mechanism
> and none of the proof.

So: give `isolation.sql` a second mode that runs the same assertion set against
tables named in the **service's** `tenancy.yml` `rls.tables[]` rather than against
a table the script creates. The assertion vocabulary already exists (39 named
assertions in `assertions.txt`, all three shapes covered, the write side already
paired). What is missing is that the **table under test is a fixture**.

That is a bounded, high-value change in `kit`, it needs no service migration, and
it closes the same gap core's checker cannot reach — core reads text, it cannot
prove a database.

**Then** the pgTAP work: `_helpers.sql`, one `.sql` per table, six drivers thin.

### Three facts you need before you start

1. **The live proof is already good.** Read
   `kit/templates/database/tenancy/isolation.sql` before writing anything. It
   covers all three shapes, and its write side is paired correctly — including the
   half implementations get wrong: the intactness read runs as the **victim's**
   role, because "the denied write changed nothing" is only observable by somebody
   who can see the row. Do not rewrite it.
2. **identity embeds a copy** (`internal/tenancy/isolation.sql`, 21
   `cafaye_assert` call sites; `migrations/00017` refreshed a function in it
   today). Any change to the mechanism must state explicitly what a copy in a
   service will and will not pick up. **This packet changed no mechanism**, so
   that question was moot here — it will not be for you.
3. **identity is the only service in the fleet with a `tenancy.yml`.** Eight of
   the nine account-scoped services have none. The checker being green on one
   adopter is not evidence about the other eight.

## What was ruled out, and why — do not re-litigate these

- **A schema `enum` for `expects`.** Refused on purpose by
  `test_the_three_way_denial_shape_is_required_on_every_entry_point`: `expects` is
  a pattern because "the vocabulary of six languages is not core's to close". An
  enum is that closure, done badly, in a published format at `version: 1`.
- **The helpers in core.** `pg_temp.cafaye_as` / `cafaye_observed` already exist
  in kit. A second copy in `harness/` is the four-way drift `harness/` exists to
  end — and `harness/` may not take a dependency or open a connection, so
  core's own harness could not run them anyway.
- **Doc-only.** The measurement table was ALREADY in `docs/tenancy.md` and was not
  enforced. That is core's one rule: a rule that is not in `schemas/` or the
  harness is a wish.
- **A closed vocabulary of correct tokens.** Would fire only on
  English-language identifiers, gets disabled within one release, and leaves the
  fleet with no check rather than an incomplete one. The vocabularies that shipped
  are closed lists of what the checker **knows** is wrong.

## The two open threads, both recorded not resolved

1. **`operation: call` gets no shape check.** A service declaring every entry
   point as `call` is unproved, because the checker cannot see which clause denies
   a method call. **D42** has the one-enum fix and its cost. My recommendation is
   to fold it into the pgTAP migration, not give it its own packet — a `call` entry
   point's shape needs its *test to run*, which is the service gate's job.
2. **A denied `update` arm declared as a bare `assert_equal 0` is still accepted.**
   It counts zero rows, so it does not prove the row is intact. First entry in
   `harness/tenancy_findings.json`'s `notEnforced` list, quoted with its measured
   consequence in `docs/tenancy.md`. The enforced direction is the one with no
   good spelling in any language: every ABSENCE token is refused on a denied
   write, so the "lie about a row that exists" case is caught in all six at once.

## What is now enforced in core, so you do not rebuild it

`tenancy.denial-shape` and `tenancy.denial-unpaired`, both decided from the
declaration plus the one line it names:

| fault | refused |
| --- | --- |
| a `select`/`update`/`delete` denial arm naming a raising token | `tenancy.denial-shape` |
| the `own-account` arm naming a liveness token (`lives_ok`, …) | `tenancy.denial-shape` |
| a denied write answered with an absent token (`nil`, `[]`, …) | `tenancy.denial-unpaired` |

Each has three red proofs — `harness/tests/tenancy_self_test.sh` (39 breakages),
the in-process table in `test_every_behavioural_check_…`, and the vocabulary
contract test. **Adding a fourth shape means all three, plus the findings JSON
entry, or the suite is red.** That is the house rule working; do not route around
it.

## Commands the successor will want

```sh
# the three shapes, in-process, with a control asserted finding-free first
python3 -m pytest tests/test_specs.py -k denial_arm -v
# the three shapes as shell breakages, each editing file AND declaration
bash harness/tests/tenancy_self_test.sh
# the whole gate — the red proof is step four and its output must be READ
bin/prime
# the one real adopter, to prove a rule did not make a legal declaration illegal
cd ../identity && python3 ../wt-m39-…/harness/tenancy_check.py .
```

## House rules this packet ran into, worth knowing

- **`gate.yml`'s `minimum` is a ratchet.** Adding one test to
  `tests/test_specs.py` fails `test_the_gate_floor_is_not_below_the_suite_core_
  claims_to_have` until the floor is raised. It fired here (253 → 254) and the
  answer is to raise the number, never the assertion.
- **`harness/tests/tenancy_self_test.sh`'s `edit` fails loudly on an AMBIGUOUS
  anchor**, not only a missing one. Both new breakages needed three-line anchors
  because `expects: assert_unchanged` appears on more than one entry point — and a
  self-test that silently edits the wrong line is the defect that file exists to
  stop.
- **Run the checker from the worktree, not `cafaye/core`.** They are different
  checkouts on different branches; I spent part of Q1 measuring against `master`
  and the results were real but from the wrong tree.