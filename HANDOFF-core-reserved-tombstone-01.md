# HANDOFF — core-reserved-tombstone-01

Read `REPORT-core-reserved-tombstone-01.md` first; this file is what is owed and
what to watch.

**State:** `worker/core-reserved-tombstone-01`, HEAD `e8a9bfc`, `265/265 passed`,
`bin/prime` green, working tree clean. **Not pushed, not merged.**

---

## In order of how much they matter

### 1. `test_every_reserved_finding_the_checker_can_emit_is_declared` does not exist

`harness/reserved_findings.json` names it in its own `$comment` and claims the
two sets are asserted equal **in both directions**. Nothing asserts it. This is
inherited — the predecessor wrote the comment and not the test — and it is the
repository's own named defect: *a requirement satisfied by a file that does not
exist is a pointer to a page that does not exist*.

Write it as its two siblings are written:

- `test_every_reserved_finding_the_checker_can_emit_is_declared` — the four ids
  in `reserved_findings.json` are exactly `reserved_check.FINDINGS`, asserted
  **both ways**, so neither an undescribed finding nor an unreachable inventory
  entry can survive.
- Match severity per id and `remediate` non-empty, or the inventory can describe
  a finding at a severity the module cannot emit.
- **Show it failing** by adding a fifth id to `FINDINGS` alone.

Note the comment also says the set is asserted against
`harness/rules.json` / `gate_findings.json` — **it is not, and must not be.**
Those are the contract rules and the gate findings; a reserved id in either
breaks the assertion that each of those is the same set as the module it mirrors.
The comment is right to separate them and the test should say so.

### 2. `docs/reserved-properties.md` does not exist

`harness/bin/reserved-check:43` ends "See docs/reserved-properties.md", and the
`reserved.reintroduced` remediation points at
`DECISIONS-reserved-tombstone-01.md` (which now exists). One citation points at
nothing.

It should carry, briefly: the hazard in five steps, the four findings, **why all
four are `fail` and there are no warnings** (the wrapper already argues this —
do not restate it at length), and the **two controls**, because the first is over
core's own tree and that is unusual enough to say out loud. Two pages, per the
`openapi-conventions.md` precedent.

### 3. No CI step for the reserved red proof

`bin/prime` runs it, so the gate covers it — but gate, tenancy and harness each
have a CI step of their own, for the log and for a grep one step away instead of
buried in the gate's output. Add it after the tenancy step, and add the
count-reading step after it, copying the tenancy one. **Grep the phrase the footer
actually prints** (`breakages that went RED naming their finding`, in the counts
**block**) — that is the drift `bin/prime` hit on its first run, and
`test_the_ci_selferved_step_reads_the_phrase_the_footer_prints` should pin it the
way `test_the_ci_self_test_step_reads_the_phrase_the_footer_prints` pins the
harness one. That pin does not exist yet either.

### 4. The same-service decision is tested only in the shell red proof

`DECISIONS-reserved-tombstone-01.md` D44 requires it tested in both directions,
and it is — breakages 3 and 5 plus the two green rows in
`harness/tests/reserved_self_test.sh`. But `tests/test_specs.py` has no test
function for it, so `bin/prime`'s suite alone does not know it. A shell red proof
is a real proof; this is stated rather than hidden.

---

## Deliberate, and do not "fix" it without reading why

- **`bin/prime` runs TWO red proofs**, and
  `test_bin_prime_runs_the_gate_checkers_red_proof` asserts one **per function**,
  not one per file. The invariant is one invocation *per red proof*; two
  invocations of the same one is two gates that can disagree. Do not collapse it
  back to `== 1` over the whole file — that fails the day a third red proof is
  added, on a gate whose behaviour is correct.
- **Its ordering assertion reads the CALL SITES**, not the `bash "$red_proof"`
  lines in the function bodies. Both functions are *defined* above the suite
  because a shell function must exist before it is called; reading the bodies
  made the assertion fail on correct execution order.
- **`manifest_paths` skips the `tests` + `fixtures` PAIR**, not the name
  `fixtures`. A service with a real top-level `fixtures/` must still be read, and
  the skip is decided **relative to the root** so the red proof can point the
  checker straight at a fixture directory.
- **`reserved_self_test.sh` prints a counts BLOCK and a summary line with
  different wording**, on purpose. `count_line` matches
  `^  <label>: <number>$`; pointing it at the summary sentence finds text the
  shape filter discards. This exact drift made `bin/prime` report a passing proof
  as having no counts.
- **The reserved red proof is in `bin/prime`** while the harness's and tenancy's
  are not. D47 argues it; `docs/gate.md` argues the other two. This does not
  move either of them.

---

## Watch for

- **`reserved.surface-missing` fires on a *valid* example if the two path
  spellings ever come apart again.** That is what the green control caught, and
  it is the shape this checker fails in: a false failure on core's own example
  is how a checker gets disabled rather than fixed. `reserved-check .` over core
  **must** print `OK .: 0 failure(s)`; if it does not, believe the checker.
- **A path-form surface outside `schemas/events/` has no publisher**, so the
  cross-service half cannot fire from it. In `notEnforced` with its reason.
  D46 rejected the fix (a manifest-schema change at `version: 1`).
- **Core's tree is now load-bearing for this checker.** Any new example manifest
  with a tombstone is checked by `bin/prime`. A stale `removedFrom` in an
  example is a red gate, which is the point — but it means editing an example now
  needs `reserved-check .` run with it.

## Facts, measured

| | |
|---|---|
| findings | 4, all `fail` |
| breakages in the red proof | 6 |
| controls | 2 (core's own tree, then the conforming fixture) |
| `reserved-check .` over core | `OK .: 0 failure(s)` |
| unfixed defects in the checker | 0 |
| unfixed gaps in the enforcement around it | 4, listed above |

**Not pushed. Not merged. `DECISIONS.md` untouched** — no `Dnn` was added there;
the four decisions are in `DECISIONS-reserved-tombstone-01.md`, following the
`DECISIONS-breaking-tiers-01.md` precedent.