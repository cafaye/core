# REPORT — core-reserved-tombstone-01b

**Branch** `worker/core-reserved-tombstone-01` · **Head** `e8a9bfc` ·
**Suite** `265/265 passed` · **`bin/prime`** green · **Nothing pushed, nothing
merged.**

The packet this continues asked for eight things. Seven are done and measured.
One is not, and it is named in the first section rather than in a footnote.

---

## What I inherited, and what was actually true of it

The brief said the checker's four findings all worked. **They did** — every one
of them fires on its own fixture and the control is green. That is worth
recording plainly because the alternative was to have assumed it and been wrong
in the other direction.

```
conforming     OK      cross-service  FAIL reserved.cross-service
reintroduced   FAIL reserved.reintroduced
stale          FAIL reserved.surface-missing
unreadable     FAIL reserved.declaration-unreadable
```

**Deliverable 2's two halves were therefore already implemented**, which the
brief did not expect:

1. *a tombstone no schema uses is reported, not skipped* — **existed**, as
   `reserved.surface-missing`;
2. *a name reserved in one service and live in another is a failure naming both*
   — **existed**, as `reserved.cross-service`.

The rule was falsifiable: the fixtures make it red. I did not add either half.
What I did add is the proof (below), the wiring, and the green control — which
is how the two halves turned out to have a defect in common.

---

## The green control, and the two defects only it could find

The brief asked for this and it is the most valuable thing in the packet.
`reserved-check .` over core's own tree, before any fix:

**8 findings.** Not 8 defects in core — 3 in the checker. Committed unedited as
`measurement-reserved.out`.

**Defect 1 — a path-form surface could not be checked at all.**
`contracts_by_surface` keyed each payload schema by its path *relative to
`schemas/events/`*, while `surface_path` accepts a path *relative to the root*
and confirms it exists. So core's own valid example **resolved** and was then
reported as a reservation against a contract this checker could not read. Two
spellings of one surface, and each half of the check only knew one of them.

This is worse than a missing check. It is a check that reports a *failure* on
core's own example — a false positive on the one file that demonstrates the
feature — and a false positive on a valid example is the kind that gets a
checker disabled rather than fixed.

**Defect 2 — the checker read its own fixtures as fleet members.** Four of the
eight findings were `harness/tests/fixtures/` files broken *on purpose*, and two
were `harness/tests/fixtures/unsupported-yaml/cafaye.yml`, which belongs to
`tenancy_check`. A checker that complains about its own test data is a checker
nobody runs.

Both fixed. `manifest_paths` now skips the `tests` + `fixtures` **pair** — not
the name `fixtures`, so a service with a real top-level `fixtures/` is still
read — and decides it **relative to the root**, so pointing the checker straight
at a fixture directory still reads it, which is what lets the red proof drive it
at all. The skip is the first entry in `notEnforced`, because a path a checker
silently does not read is the one nobody goes looking at.

**After: `OK .: 0 failure(s)` over core's own tree.** That is the answer to
"does my repository pass?", and until this run the checker had never been asked.

**Defect 3 — the inventory cites a test that does not exist.**
`harness/reserved_findings.json` names
`test_every_reserved_finding_the_checker_can_emit_is_declared`. There is no such
function. Its `$comment` claims the two sets are asserted equal in both
directions, and nothing asserts it — the same defect `gate.yml` calls "a
requirement satisfied by a file that does not exist". **Not fixed; first item in
the handoff.** Written badly in the time available would have been worse than
reported.

---

## Wiring, and the three red tests it turned up

`bin/prime` runs the checker in **two halves**:

- **the green control** — `reserved-check .` beside the gate declaration check,
  because it is not a test, it is a check applied to this tree;
- **the red proof** — `harness/tests/reserved_self_test.sh` at the bottom with
  the gate checker's, under the same three rules: its failure fails the gate, it
  cannot skip, **its report is read**.

Preconditions were proved, not asserted: deleting the red-proof script leaves
`bin/prime` exiting non-zero naming the missing precondition.

Three existing tests went red. **Two of them were right and I changed the code,
not the assertion.**

**`test_the_harness_yaml_reader_reads_every_document_in_this_repository`** — the
predecessor's unreadable fixture genuinely broke it. Fixed by naming **both**
refusal fixtures rather than skipping every `tests/fixtures` path, because
skipping more is how "the reader reads everything" gets met — and by asserting
the second fixture is *still refused*, so the exclusion cannot become a hole. The
four reserved fixtures that ARE readable stay in the walk.

**`test_bin_prime_runs_the_gate_checkers_red_proof`** — asserted exactly one
invocation *over the whole file*. That is not the invariant. The invariant is one
invocation **per red proof**, and there are now two. Resolved deliberately rather
than by lowering the number: grouped by enclosing function, both functions
required present, each required exactly once. Its **ordering** assertion was
reading the `bash "$red_proof"` lines inside the function *bodies* — which sit
above the suite because a shell function must exist before it is called — so it
now reads the **call sites**, which is what the claim was ever about.

**A phrase drift, caught by the gate itself.** `bin/prime`'s `count_line` matches
`^  <label>: <number>$`; I pointed it at the footer's summary *sentence*. The
text matched, the shape filter threw it away, the count came back empty — and
`bin/prime` raised "exited 0 without reporting its counts" **on a proof that had
in fact passed**. The error was correct and the bug was mine: a guard that cannot
find its target is not a guard.

---

## The red proof: 6 breakages, 2 controls, 12 assertions

Each breakage asserts **the exit code is 1** (not merely non-zero — an exit 2
means "could not happen" and is the number a gate retries), **the report names
its finding**, and **a `fix:` line exists**. Both controls run **first**, the
first over **core's own tree** — because a control after a breakage controls
nothing, and because core's own tree is the question a reader actually has.

Breakages 3 and 5 are the same-service decision in **both** spellings (event type
and path); breakages 4 and 6 are cross-service in both. Two green rows assert
the rules **stay silent** where they should — which is what makes the red rows
mean something, since a rule that fires on every reservation passes every red
case. Plus the exit-2 half and `--explain` covering every id.

---

## The tiers row: `reserved-no-delete` is TRUE, and was not changed

The brief asked me to check whether SOURCE + JSON and "delete-and-say-nothing is
not wire-safe" overclaims what is implementable. **It does not overclaim, and I
changed nothing.**

- *SOURCE* — a generated struct carries the field name, so a reuse compiles
  cleanly and reads a different field. Implemented, `reserved.reintroduced`.
- *JSON* — the serialized document's field names are what round-trip. Implemented,
  the same finding; the two tiers are separated by
  `test_two_rules_whose_answers_differ_for_the_same_selection_exist`.
- *WIRE deliberately absent* — the row says why, and it is right: an OpenAPI
  property has a name and **no ordinal**, so buf's number-reservation half has
  nothing to reserve. Core ships no binary encoding derived from a contract, so a
  WIRE break has nothing to break for.

So the sentence is now true **because something implements it**, rather than
because it was aspirational. `core-breaking-tiers-01` left the question open on
purpose; the answer is that it did not need correcting, and the pin
`test_the_published_table_is_the_go_table_and_they_cannot_drift` is untouched.

---

## `gate.yml`'s floor

Measured, not summed: `tests/test_specs.py` prints **265/265**, and the floor was
already **265** — raised to that number by `9aeeffe`, which added two tests, and
this packet added none, so no ratchet was owed and the pin is satisfied.

The two changes to existing tests above were **extensions to their assertions,
not new test functions**, which is the same accounting core-24 and core-25 used.

---

## What is NOT done

1. **`test_every_reserved_finding_the_checker_can_emit_is_declared` does not
   exist.** The inventory claims the two sets are asserted equal in both
   directions and nothing asserts it. First item in the handoff.
2. **No CI step for the reserved self-test.** `bin/prime` runs it, so the gate
   covers it, but the other three red proofs each have a step of their own for
   the log. The handoff carries it.
3. **`docs/reserved-properties.md` does not exist**, and
   `harness/bin/reserved-check`'s own header and one `remediate` string cite it —
   a pointer to a page that does not exist, which is the defect `gate.yml` names
   for its own `external.requirements`. Flagged in the handoff.
4. **No new test for the same-service decision.** It is tested in both
   directions — as breakages 3, 5 and the two green rows — but by the shell
   red proof, not by `tests/test_specs.py`. Defensible, and stated rather than
   glossed.

**Not pushed, not merged, no agents spawned.** `worker/core-reserved-tombstone-01`
only.