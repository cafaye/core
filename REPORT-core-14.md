# REPORT-core-14 — the local gate is weaker than CI, and nothing says so

Branch `worker/core-14-localgate`, base `master` (`c63af27`, core-12 and core-13
both merged). No schema changed. No other repository touched. Nothing pushed.

## What changed

| File | What |
| --- | --- |
| `bin/prime` | runs `harness/tests/gate_self_test.sh`; preconditions, exit-code propagation, report parsing, pass/skip counts |
| `harness/tests/gate_self_test.sh` | per-category counters measured where the case runs; three missing counts rows; corrected header |
| `tests/test_specs.py` | **6 new tests (173 → 179)** |
| `gate.yml` | proof floor 173 → **179**, same commit, per the ratchet |
| `docs/gate.md` | new section **The third thing `bin/prime` runs, and why it is not the recursion**; the red-proof section rewritten with real numbers |
| `CHANGELOG.md` | a **Fixed** entry — core's own gate, not an adopter contract change |
| `README.md`, `AGENTS.md`, `.github/workflows/ci.yml` | the three places that said the opposite |

`harness/gate_check.py`, `harness/gate_findings.json`, `harness/rules.json`,
`schemas/` and every `examples/` file are **untouched**. No finding was added, so
`gate_findings.json` and its two-way assertion did not need to move.

## The measurement, re-measured

The packet's numbers are correct and I confirmed both halves on this tree:

```
$ grep -n "gate_self_test" bin/prime        # before this branch
(no output — bin/prime never ran it)
$ grep -rn "gate_self_test" .github/workflows/
.github/workflows/ci.yml:227:  bash harness/tests/gate_self_test.sh 2>&1 | tee ...
```

**The defect, demonstrated rather than argued.** I took `master` at `c63af27` into
a scratch directory and neutered `gate.ci-missing` — the smallest possible
mutation, one that leaves the finding **declared** in `gate_check.FINDINGS`, so
every inventory assertion in the suite still passes, and only the one line that
emits it changes:

```python
# harness/gate_check.py, check_ci()
-  return [finding("gate.ci-missing", f"gate.ci.workflow names {workflow!r}, …")]
+  return found          # the finding is declared and can never be emitted
```

| | suite alone | `bin/prime` |
| --- | --- | --- |
| **master `c63af27`** | **173/173 passed** | **exit 0** |
| **this branch** | 179/179 passed | **exit 1** |

On master the local gate reported a full green over a checker that had lost one of
its twenty-two checks, and nothing in the output said otherwise. CI's red-proof
step caught it:

```
FAIL gate_self_test: a declaration naming a CI workflow that is not in this
  repository — expected exit 1, got 0
FAIL: gate_self_test — 1 of 25 breakages … the gate checker did not get right.
```

On this branch the same mutation is caught by the same command a developer runs,
and the failure names the case.

**A second, bigger mutation** — replacing the whole of `check()` with a
`Report(findings=[])` — makes the suite itself go red (169/179) on **both**
branches, because nine suite tests call the checker directly. So the packet's
framing is right for a *surgical* loss of a check, which is the realistic one;
a wholesale replacement was already caught locally. That is worth stating plainly
rather than letting the packet's stronger claim stand unqualified.

## The recursion worry, and why it does not apply

`bin/prime`'s load-bearing comment says the static half is the only half it runs:
`--prove` runs the declared gate, the declared gate is `bin/prime`, and a gate
that proves itself by running itself terminates. **That reasoning is correct, is
unchanged, and the `--prove` prohibition is still asserted** by
`test_core_ci_runs_the_gate_checkers_proving_phase`, which I did not touch.

The red proof is a different thing in kind, and the difference is mechanical
rather than a matter of arrangement:

| | `--prove` | the red proof |
| --- | --- | --- |
| runs | **the declared gate** — for core, `bin/prime` | **fixture repositories** — `harness/tests/fixtures/gates/conforming`, gate is `echo "3/3 passed"` |
| reads core's own tree | yes | no: `fresh_copy` copies the fixture into `mktemp -d`, and nothing else is read |
| asks | did *this* gate run, and did it say so | could the checker have said **no** about anything at all |

Nothing in the script runs `bin/prime`, so there is no cycle for the termination
to travel round. And the questions are different in the direction that matters:
**`--prove` structurally cannot catch a checker that can only say yes.** It looks
at one run and asks whether the proof appeared — and a checker that always
answers green looks exactly like a passing gate. Catching it requires asking the
checker about a repository that should be red.

I have written this argument in three places, because a future reader hits the
same worry at each one: `bin/prime`'s header, the red proof's own header, and
`docs/gate.md`.

## The skip question

The project's rule — a check that quietly does not run reads exactly like a check
that passed, after guard's live-Redis tier, muse's `MUSE_CORE_SCHAMAS`, identity's
`TEST_DATABASE_URL` and darkroom's `--ignored` — is enforced in four layers:

**1. Preconditions are named, and each is a non-zero exit.** No script, no `bash`
on `PATH`, or an interpreter older than 3.11 each exit 1 with a message saying
which one is missing and the sentence "a red proof that did not run is not a
pass." Never the word "skipped".

**2. The interpreter is pinned.** The script prefers `CAFAYE_GATE_PYTHON` and
otherwise scans `PATH`. That scan is right for a script a service copies out of
core and wrong inside core's own gate: the local gate would depend on the
machine, so a laptop whose system Python is 3.9 fails a checkout CI is green on.
`bin/prime` exports the venv interpreter — the same pinned one the suite runs on —
and the log line says which interpreter answered.

**3. The report is read, not the exit code.** This is the part the exit code
cannot do. `bin/prime` parses the counts block and requires:

- all nine rows present and numeric (a missing row ⇒ red, naming the row);
- `SKIPPED` **exactly 0** — a non-zero is a red gate naming the number;
- the control count exactly 1, **and** a real `PASS …: the control` line in the
  log, so the row and the run cannot come apart;
- logged `PASS` case lines ≥ the sum of the counts, so a case that silently
  stopped running is a shortfall rather than a smaller number.

**4. The literal `0` is backed by an assertion.** `SKIPPED : 0` in the script is
a constant, and a constant in a summary is a claim about the machine. So
`test_the_red_proof_counts_every_case_it_runs` asserts the *mechanism* instead:
every category is incremented inside the function that runs its case; the counts
block prints that variable rather than a literal; **every case call is unindented
and unchained** (no `if`, `for`, `while`, `until`, `&&`, `||`), which is what
"nothing here skips" means in a shell; and every case kind has a row, so a new
kind of case cannot run uncounted.

## The miscount I found, and fixed

While reading the counts to wire up layer 3, the footer turned out to be wrong:

```
$ grep -c "^PASS gate_self_test: breakage" harness/tests/gate_self_test.sh   # 18
$ … footer:  breakages that went RED and named their finding : 25
```

**The footer claimed 25 reds; 18 cases went red.** `breakages` is a
hand-incremented **case label** — incremented before each red-proof case so
printed lines can be referred to by the same number the comments use ("breakage
7", "breakage 8") — and it counts the seven **warning** cases too, which by
construction stayed green. It was being printed as though it were a tally.

This matters more than a cosmetic number: the packet's own measurement inherits
it ("25 specific breakages each go red, 7 warning cases stay green" — 25+7 > the
18+7 that exist), and it is the one number a reader of that script has most
reason to trust.

Fixed rather than worked around, because requirement 3 asks `bin/prime` to report
these counts and shipping a report built on a false one would have made the new
step lie. Each category is now counted inside the function that runs it
(`red_cases`, `leak_cases` are new), and the three case kinds with **no** counts
row at all — the colour greens, the colour reds, the leak case — got one. A case
kind with no number is a case kind nobody can tell stopped running.

Measured now: **18 red · 7 warning-green · 3 colour-green · 2 colour-red · 12
spellings accepted · 4 extractor assertions · 1 leak case · 1 control · 0
skipped.**

## The proof that deleting the step goes red

Requirement 5 asked for this explicitly. I deleted the step — the call and both
helpers it needs, 8662 bytes, as a careless edit would — and ran the suite:

```
FAIL test_bin_prime_is_not_a_pass_when_the_red_proof_says_nothing_or_skips
FAIL test_bin_prime_is_red_when_the_red_proof_is
FAIL test_bin_prime_runs_the_gate_checkers_red_proof
FAIL test_bin_prime_runs_the_red_proof_on_the_pinned_interpreter
175/179 passed
```

Then I restored it and got `179/179`.

**Four of the six new tests go red, and they go red for four different reasons** —
a missing textual step, a red proof that no longer fails the gate, a red proof that
says nothing and is no longer caught, and the interpreter never being chosen
because the code that chooses it was deleted. The other two
(`…_counts_every_case_it_runs`, `…_cannot_satisfy_the_gate_s_own_proof`) correctly
stayed green: they assert properties of `gate_self_test.sh` and `gate.yml`, which
the deleted step never touched. A test that fails for the wrong reason would have
been worse than no proof.

The four red ones are **behavioural, not textual**. Each copies this repository —
`bin/`, `harness/`, `gate.yml`, `mise.toml`, `.github/`, and a stub suite — into a
temp directory, writes its own `gate_self_test.sh` there, and runs the copy's
`bin/prime` as a process:

| Case | Written red proof | `bin/prime` |
| --- | --- | --- |
| complete and unskipped | full counts block, 0 skipped | **exit 0**, reports the interpreter it used |
| red proof is red | `exit 1` with a FAIL line | **exit 1**, "red proof FAILED … neither is this gate" |
| silent | `exit 0`, prints nothing | **exit 1**, "exited 0 without reporting its counts" |
| reports skips | complete report, `SKIPPED : 2` | **exit 1**, "reported 2 skipped cases" |

The copy is what makes this affordable — **1.2 s** per case against 58 s for the
real thing — and `set -euo pipefail` and the static declaration check run for
real in it, so a broken fixture could not pass quietly. Nothing outside the temp
directory is touched and no committed file is modified, which is the same promise
the red proof makes about itself.

## Tests were watched red first

Beyond the step deletion, the new tests were each watched failing for their own
reason before the implementation existed:

- `test_the_gate_floor_is_not_below_the_suite_core_claims_to_have` failed with
  "promises a floor of 173 and this suite has 179" until `gate.yml` moved, which
  is the ratchet doing its job.
- `test_the_red_proof_counts_every_case_it_runs` errored on `_counts_block`
  (undefined) and then failed on the `25`-vs-`18` row until the counters moved.
  Its `--prove` flag exclusion was caught by the same test — it was comparing 6
  warning cases against a count of 7, which is a test quietly not counting the
  thing it exists to count.
- `test_the_red_proof_cannot_satisfy_the_gate_s_own_proof` **failed me twice
  before it worked**, in both cases by being too eager in a way that would have
  hidden a real collision: it first flagged the fixture's own heredoc
  `echo "3/3 passed"` lines, and then — after I excluded those — it passed with a
  deliberately planted `printf '%s/%s passed\n'` still sitting in the script,
  because collapsing `\n` to a space had left a trailing space that no `…$`
  pattern could match. Both are described under "A sharp edge" below. A guard that
  cannot find its target is not a guard, and neither version was one.
- The three behavioural tests each went red against a `bin/prime` that did not
  have the step, per the table above.

No sleeps, no retries, no loosened assertions. Every subprocess call has no
timeout, which is a note rather than a promise: the copy's red proofs are written
by the test and exit immediately, and the fixture's own gates are three lines.

## A sharp edge this introduces, and the test that closes it

`gate.proof` is matched against **everything `bin/prime` prints** —
`gate_check.py --prove` captures stdout and stderr and applies the pattern to the
lot, with the floor reading the **last** match. Before core-14 the only thing
printing there was the suite. Now a second program is, and a line shaped like a
proof printed by the red proof could satisfy the gate's proof, or be read as the
floor's number.

`test_the_red_proof_cannot_satisfy_the_gate_s_own_proof` closes it: it takes every
literal `printf`/`echo` **in the red proof's own shell code** (**60** of them, with
a floor of 40 so the extraction cannot go vacuous), fills each conversion spec with
`999`, splits on the literal `\n` into the output *lines* it would produce, and
requires every one to fail to match every pattern `gate.yml` declares — compiled by
the checker's own `_compile`, so the test cannot pass while the checker matches
differently.

Two exclusions, both of which I got wrong first and fixed after watching the test
misbehave:

- **Heredoc bodies.** Roughly a quarter of that script is fixture *source* written
  into throwaway repositories. Three of those lines are literally
  `echo "3/3 passed"` — the fixture's declared gate being written to a file, which
  never reaches the red proof's stdout. Reading them as commands made the test red
  on three strings that are not the red proof printing anything. `_outside_heredocs`
  now tracks `<<EOF`, `<<'EOF'`, `<<"EOF"` and `<<-`, and an unterminated block takes
  the rest of the file, which is what a shell does.
- **The trailing newline.** A template is a set of output *lines*, not one string.
  Collapsing `\n` to a space left a trailing space and made every `…$` pattern
  unmatchable — so the test passed with a deliberately planted
  `printf '%s/%s passed\n'` still in the script.

**Proved able to fail, by planting the exact defect.** I added one line to the
red proof's counts block:

```bash
printf '%s/%s passed\n' "$red_cases" "$red_cases"
```

```
FAIL test_the_red_proof_cannot_satisfy_the_gate_s_own_proof
     harness/tests/gate_self_test.sh prints '%s/%s passed\n', whose line
     '999/999 passed' matches core's own gate.proof pattern
     '^([0-9]+)/[0-9]+ passed$'. …          178/179
```

Then removed it and got `179/179`. Nothing the red proof prints is of that shape
today; that was an accident waiting to be edited into, and it is now a test.

## Judgement calls, and why

**Ordering: red proof last, after the suite.** Both orders gate identically;
running it first would cost a developer iterating on a red suite forty seconds of
unrelated work per attempt. Asserted by
`test_bin_prime_runs_the_gate_checkers_red_proof` so it cannot be reshuffled
silently.

**Cost is not gated.** `bin/prime` goes from ~20 s to ~58 s warm. `timeoutSeconds`
is 900, so CI has room, and the packet asks for the step rather than asking about
the cost. Stated in `bin/prime`, `docs/gate.md` and `CHANGELOG.md`, because a cost
nobody mentions is a cost the next person rediscovers.

**`harness/tests/self_test.sh` stays CI-only.** The contract harness's 28
breakages are a different checker on a different schedule, and adding them would
add their ~12 s to every local run for a claim `bin/prime` does not make about
itself. The asymmetry is now argued in `docs/gate.md`, `AGENTS.md`, `README.md`
and the workflow comment, so it reads as a decision rather than an oversight.

**`logged >= claimed`, not `==`.** Same rule and same reason as the check CI
already applies to `harness/tests/self_test.sh`'s log: a new kind of case adds a
line without lowering the tally, and the step should not need editing for that. A
shortfall — the direction that matters — is a hard failure. The strict equality
lives in the *test* instead, which is where a drift should be caught.

**`--pytest` runs the red proof too.** An assertion a developer only meets under
one spelling of the gate is an assertion one of the two spellings does not have,
and CI exercises both.

**`breakages` stays as the case label.** The comments refer to "breakage 7" and
"breakage 8", so renumbering would break those cross-references. It is now
documented as a label rather than a tally, and the counts come from
`red_cases`.

## Gate results — pass and skip counted separately

**`bin/prime` — PASS, exit 0.**

- suite: **179/179 passed**, 0 skipped (from 173)
- red proof: **18 red** naming their finding, **7 warning** stayed green, **3
  colour-green**, **2 colour-red**, **12 spellings accepted**, **4 extractor
  assertions**, **1 leak case** (report clean, log held the value), **control
  green**, **0 skipped**
- wall clock: ~58 s warm (suite ~20 s, red proof ~37 s)

**`bin/prime --pytest` — PASS**, `179 passed in 24.04s`, then the same red proof
summary and exit 0.

**`bash harness/tests/self_test.sh` — PASS**, 28 breakages, unbroken tree green.
Unchanged by this branch.

**`harness/gate_check.py --prove .` on core — exit 0**, 0 failures, 1 warning
(`gate.requirement-unproven`, the tri-state case, unchanged). The gate log
contains `179/179 passed`, so the proof matched and the floor of 179 was met.

**Baseline counts did not move except where they were wrong**: 25 reds were
reported and 18 happened; 18 now. Everything else — 7 warnings, 12 shapes, 4
extractor assertions, 3 colour greens, 2 colour reds, control green — is the same
number before and after.

## What I found and did NOT fix

**1. `harness/tests/self_test.sh` prints `printfPASS:` — a missing newline.**
The footer's `printf` has no `\n` and the next line's output is concatenated onto
it. Cosmetic, and it is in the *other* self-test, which this packet is not about.
It is left alone deliberately: touching it changes CI's log-grep behaviour on a
file whose step has its own "reads its own log" guard, and that is a separate
change with its own proof.

**2. Eight findings have no direct test in the suite — only the self-test
exercises them.** `gate.ci-missing`, `gate.declaration-missing`,
`gate.declaration-unreadable`, `gate.entrypoint-not-executable`, `gate.nonzero`,
`gate.proof-invalid`, `gate.requirement-path-missing`, `gate.task-config-missing`
and `gate.task-unreadable` appear in `gate_check.FINDINGS` and in the red proof's
breakages, but the strings never appear in `tests/test_specs.py`.

**This is the same class of defect as the packet's, one level down, and it is
bigger.** The `gate.ci-missing` mutation above is *exactly* one of these: a
finding with no suite test, provable only by the red proof, which until core-14
ran only in CI. Nine such findings means the local gate's coverage of the checker
was nine checks thinner than CI's, and this packet closes the *mechanism* (the
local gate now runs the red proof, so all nine are covered locally again) without
adding any suite test for them. Cost of closing it properly: roughly nine tests,
each needing a fixture repository with a specific defect — the same shape as the
`accepts_whole` cases the red proof already carries. That belongs in its own
packet.

**3. `harness/tests/self_test.sh` has no skip instrumentation at all.** It prints
a footer claiming every breakage went red and nothing else; there is no skip
count, no per-category count, and no caller reading its report except CI's
`grep`-based step, which compares a claimed footer against logged assertion lines
using `logged >= claimed` with a comment admitting the looseness. The gate
checker's red proof now has nine counted categories and a caller that parses them;
the contract harness's does not. Not fixed here — same reason as (1), and it is
the stronger argument for leaving it CI-only for now.

**4. `harness/gate_check.py` is 1377 lines and `harness/cafaye_contract.py` is
106 KB.** No opinion, no measurement, mentioned because the packet asked for
anything worse that I did not fix and I have none that is about *this*.

**5. Nothing measured `bin/prime`'s wall clock**, before or after, on a cold
checkout or on CI's ubuntu runner. My ~58 s is one warm run on a laptop. The
900 s floor has ample room either way, but the number in `docs/gate.md` is one
machine's.

## One measurement I did not make

**The red proof's wall clock was not measured on CI's ubuntu runner, and not on a
cold checkout.** Every number in this report is one warm run on one laptop:
suite ~20 s, red proof ~37 s, `bin/prime` ~58 s. `gate.timeoutSeconds` is 900 and
CI's job timeout is 20 minutes, so there is an order of magnitude of headroom and
the step cannot plausibly time the build out — but the *marginal* cost on the fleet's
actual runners is unmeasured. It is a one-line addition to the CI step to print
`$SECONDS` around it if anyone wants the real figure.

## Open list

**No open decision, and no `D` number.** The direction — put the red proof in
`bin/prime` — is the packet's ruling, and the judgement calls above are
mechanical (ordering, tolerance shape, where the asymmetry is argued) rather than
genuine spec questions. Following `REPORT-core-13.md`, I recorded it in
`CHANGELOG.md` under **Fixed** rather than opening a core `D`: core's `D` numbers
are the *open*-decision list, `test_open_decision_callouts_remain_in_the_docs`
fails a merged doc carrying a callout, and the settled numbers must stay below
every open one. If the manager wants the asymmetric treatment of the two self-tests
promoted to a numbered decision — it is the one thing here with a defensible
alternative (put **both** red proofs in `bin/prime`, at ~70 s) — that is a
manager's call to make, and it is a one-line change to whichever way it goes.

## Reproducing the claims

```bash
bin/prime                                   # 179/179, then the red proof, exit 0

# the defect, on master:
#   neuter gate_check.py's gate.ci-missing emission, then run bin/prime
#   -> 173/173 passed, exit 0

# the fix, on this branch, same mutation:
#   -> 179/179 passed, then FAIL gate_self_test: …, exit 1

# the step deletion:
#   delete the gate_red_proof call and both helpers from bin/prime
#   -> 175/179, four named FAILs
```