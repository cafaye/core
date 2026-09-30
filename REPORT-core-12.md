# REPORT core-12 — `run:` spellings, and the policy that was missing

Branch `worker/core-12-runkey`, base `71d01fd`. Not pushed, not merged.

**Verdict: fix, do not remove.** The argument for removal is at the end, because
it is the wrong one and I want the reasoning on the record rather than the
absence of an argument.

---

## 1. The bug, reproduced before it was fixed

I did not take the brief's table on trust. I reproduced it against `cafaye-rb`
at `a45c35c` with its workaround reverted, on the checker as it stood:

```
FAIL gate.ci-disagrees: .github/workflows/ci.yml never runs ./bin/prime
exit 1
```

on a workflow whose only gate step is `run: ./bin/prime`. After the fix, the same
tree with the same step restored is `OK … 0 failure(s)`, exit 0 — and deleting
the step again still gives `FAIL gate.ci-disagrees`, exit 1. Both directions
tested, because a checker that stops complaining is not a fix.

**The part I did not expect, and it is worse than the brief says.** Two
repositories in this fleet write the gate as a one-liner *right now*:

| repository | line | step |
| --- | --- | --- |
| `guard/.github/workflows/ci.yml` | 65 | `run: bin/prime` |
| `parlor/.github/workflows/ci.yml` | 81 | `run: ./bin/prime` |

Both are true workflows that run the gate, and both would be reported as not
running it. `cafaye-rb` was not the first adopter to hit this; it was the one
that said so. Its workaround is a block scalar with a comment explaining why,
still in that tree — a permanent shape chosen to satisfy a checker bug.

**Root cause, and it was not only the anchor.** The caller already had this
branch:

```python
if not matched.group("block"):
    # `run: <command>` on one line.
    lines.append(raw.split("run:", 1)[1].strip())
```

It was **dead code**. The `\s*$` anchor meant no input could ever reach it, so
the author had already thought about one-line `run:` and written the handling for
it — and the pattern made it unreachable. That is the signature of a checker
written against one fixture: the fixture spelled its gate `run: |`, the code
handled the other shape, and nothing ever told the two apart.

---

## 2. The shapes, read out of the fleet rather than invented

`grep` over `.github/workflows/` in `core`, `kit`, `identity`, `billing`,
`courier`, `cafaye-rb`, `docs`, `guard`, `darkroom`, `muse`, `parlor`:

```
139 `run:` keys total
  101  run: |                block scalar
   38  run: <one-line command>     <-- all 38 invisible to the old pattern
    0  - run: ...            sequence-item form
    0  run: # comment        null value
```

38 one-liners, 33 distinct commands. Every shape below is either in that count
or is an absence I state as an absence:

| shape | in the fleet? | where |
| --- | --- | --- |
| `run: \|` | yes, 101× | everywhere |
| `run: bin/prime` | yes | `guard/ci.yml:65` |
| `run: ./bin/prime` | yes | `parlor/ci.yml:81`, `cafaye-rb` pre-workaround |
| `run: <cmd> "$VAR"` | yes | `kit/ci.reusable.yml:349`, `darkroom/ci.yml:172` |
| `run: <cmd> 2>&1 \| tee "$X"` | yes | `core/ci.yml:186` |
| `run: <cmd> --flag` | yes | `parlor/ci.yml:133`, `courier/ci.yml:183` |
| `run: >`, `run: \|-`, `run: \|2` | **no** | block variants the old pattern already claimed |
| `- run: <cmd>` | **no, zero** | standard Actions, absent here |
| `run:` + value on following lines | **no** | valid YAML — I checked with PyYAML, not from memory |
| `run: # comment` | **no** | the shape the fix had to refuse |

Three things worth flagging:

- **`run:` with the value on the next line is valid YAML.** I assumed it was not
  and was wrong: PyYAML returns `'bin/gate'`. The old code matched the bare key,
  then reset its indent state in the same breath, so it read *nothing*. That is a
  second latent bug of the same family, found while fixing the first.
- **`- run:` occurs zero times**, so per the brief I had to decide. It is in the
  pattern, not the caller: it is the same key in the same position, and splitting
  it would make a reader check two places. A shape absent from today's tree is
  not a shape that should be invisible — that reasoning is what the anchor got
  wrong, in the other direction.
- **No workflow in this fleet has a trailing comment on a `run:` line**, so that
  case is a guard, not a reproduction. It is tested anyway, because the fix
  changes behaviour there.

---

## 3. What changed

**`harness/gate_check.py` — `RUN_KEY`.** Three parts, each load-bearing:

```python
RUN_KEY = re.compile(
    r"^(?P<indent>\s*)"
    r"(?:-\s+)?run:"
    r"(?:\s+(?P<block>[|>][+-]?\d*)?(?P<inline>\S.*?)?)?"
    r"\s*$"
)
```

- `(?:-\s+)?` — the sequence-item form.
- `[|>][+-]?\d*` — block scalars, plus the explicit indent indicator `|2`.
- `inline` — `\S.*?`, not `\S+`, because a command with arguments and a quoted
  variable is the common case (`kit:349`).

The caller now decides what a comment-only `inline` means, because only the
caller knows a comment is not a command — and that judgement is kept out of the
pattern deliberately.

**The guard the brief asked for.** `run:` followed by something that is not a
command must not silently become one. PyYAML reads `run: # TODO: wire up
bin/gate` as `None`, so I do too: an inline value that starts with `#` is not a
command. A trailing comment on a line that *does* carry a command is kept, because
stripping it would truncate the only part that matters.

Asserted from **both** sides, so neither half can rot: the comment is not read as
a command, and `run: bin/gate --verbose  # add --verbose once the suite is quieter`
is. These are extractor-level assertions, not verdict-level ones — "the repository
is still red" and "the comment did not become a command" are different claims,
and only the second is what a looser anchor breaks quietly.

**Also fixed:** the caller used `raw.split("run:", 1)[1]`, which cannot tell this
key from any line containing `run:`. It now uses the captured group.

---

## 4. The policy: how many times, and through what

Written into `docs/gate.md` (§ *How many times, and through what*), pinned by
`test_gate_ci_multi_invocation_and_indirect_invocation_have_a_stated_policy`, and
implemented — a documented tier that cannot fire is a wish.

**A PASS in three shapes.**

1. **Every element of `invokes` appears — once, or any number of times.**
   `invokes` claims the gate is *reachable* from CI, not how often. This is not
   hypothetical: **core's own workflow invokes the gate twice**, `bin/prime` at
   ci.yml:186 and `bin/prime --pytest` at ci.yml:338, with a step asserting both
   report the same test count. A checker reading multiplicity as drift would fire
   on the repository that wrote the rule. (This was already the behaviour and
   already in the schema's `invokes` description — it was nowhere in `docs/gate.md`
   and nowhere tested. Now it is in both.)
2. **The workflow calls the mise task the declaration names** — `mise run prime`,
   where `mise.toml`'s `[tasks.prime]` resolves to the declared `entrypoint`. A
   pass because it is *provable*: `check_mise_task` has already made that
   resolution for `gate.task-unresolvable`, and this reuses the proof. Nothing is
   taken on trust.
3. **A reusable-workflow job beside a step that runs the gate** — `guard` and
   `parlor`. Needs no special case: a `uses:` line is not a `run:` body, so it is
   not read, and the step that is one is.

**A WARNING — `gate.ci-unproven`, new — when the gate is behind a wrapper nobody
declared.** `make gate`, `./scripts/ci.sh`, a task the declaration does not name.
This checker reads no Makefile and no shell script, so a wrapper that calls the
gate and a wrapper whose target was emptied are *the same text* to it. Failing
there is the false red this packet exists to kill; staying silent is the false
green. It prints what it cannot see and exits 0.

**Its leak, named rather than hidden.** The warning fires on any task-runner step,
so a workflow whose only task call is unrelated also warns instead of failing —
meaning deleting the gate step from such a repository costs a warning, not a red.
That is a real price. I took it deliberately: the alternative was measured, not
assumed, and it is the thing that made this standard harder to adopt than the
thing it standardises. The signal is deliberately narrow — anchored to the start
of a `run:` line, so `mise` or `make` in prose, in a comment, or inside a path
cannot turn a failure into a warning. **Anyone who wants the strict reading back
deletes one `if` in `check_ci`.**

**A FAILURE when the run bodies contain nothing that gates at all.** Unchanged,
and unchanged deliberately: the warning tier is narrow precisely so that a plain
workflow which lost its gate step still goes red, which is the case the check
exists for.

**What I chose *not* to build, and why.** The obvious alternative is a declared
`ci.indirect` list, so a repository names its own wrapper and gets a straight
pass. I did not build it this packet. The standard is being adopted *right now*,
and asking every adopting repository to learn a new key on day one to dodge a
false red is a worse migration than a warning that explains itself. The one-line
path is recorded rather than left in a discussion: an optional string array in the
`ci` block of `schemas/gate.schema.json`, plus three lines in `check_ci`. If the
manager would rather have it, it is cheap.

---

## 5. Tests first, watched red

`harness/tests/gate_self_test.sh` gained positive-case machinery
(`accepts`, `accepts_whole`, `extracted`) — the script could previously only
prove the checker fails, which is how a checker can be wrong and green at the
same time. Two new sections: **12 real spellings asserted ACCEPTED**, and **4
extractor assertions**.

Against the unfixed `RUN_KEY`:

```
FAIL shape 2: a one-line run with no ./ — guard/ci.yml:65 spells the gate exactly this way
FAIL shape 3: a one-line run with a leading ./ — parlor/ci.yml:81 …
FAIL shape 4: a one-line run carrying arguments and a quoted variable — kit:349 …
FAIL shape 5: a one-line run with a trailing comment — core:186
FAIL shape 6: the sequence-item spelling, - run:
FAIL shape 7: a bare run: key whose value is on the lines below it
FAIL shape 8: guard/ci.yml: a kit reusable-workflow job, and the gate as a one-liner
FAIL shape 9: parlor/ci.yml: the same shape, the gate spelled with a leading ./
FAIL extractor 3: did not read bin/gate out of it
→ 9 assertions failed
```

Shapes 1 and 10 (block scalar; two invocations) passed before and after — as
expected, and useful: they are the control on the control.

The policy tests were written before the policy existed and watched red too
(`mise run prime` wrongly `FAIL`ed; both `gate.ci-unproven` warnings were
unfindable → 3 assertions failed).

**Three tests also went into `tests/test_specs.py`**, because the self-test is a
CI step and `bin/prime` would otherwise ship a regressed `RUN_KEY` green:

- `test_the_gate_checker_sees_the_gate_in_every_run_spelling_this_fleet_writes`
- `test_the_gate_checker_does_not_read_a_comment_as_a_command`
- `test_gate_ci_multi_invocation_and_indirect_invocation_have_a_stated_policy`

The ratchet fired as designed: `gate.yml`'s floor went **163 → 166** in the same
commit. No sleeps, no retries, no loosened assertions.

---

## 6. Gate results — pass and skip reported separately

```
bin/prime                  : 166/166 passed      (was 163/163; +3 tests, floor raised to match)
  gate_check.py (static)   : OK — 0 failures, 1 warning
                            (the warning is gate.requirement-unproven, pre-existing,
                             by design, and does not move the exit code)
bash harness/tests/gate_self_test.sh : exit 0
  breakages that went RED and named their finding : 25   (was 23)
  warning cases that stayed GREEN                  : 7    (was 5)
  real-workflow shapes ACCEPTED                    : 12   (was 0 — none existed)
  extractor assertions (must / must-not)           : 4
  the control                                      : 1
  SKIPPED                                          : 0
```

**Zero skips.** Nothing in the self-test is conditional on the machine: a case
that could not run exits non-zero rather than reporting a skip. The summary
prints the counts separately precisely so a green cannot hide one.

The 25 breakages all still go red, naming their findings — the fix did not
quieten a single one.

---

## 7. What I could not verify

- **I did not run the fleet.** `guard`, `parlor`, `kit` and the rest were read,
  never executed; their verdicts here come from the checker, not from their CI.
- **`--prove` was not run against a sibling repository.** It runs the gate, which
  for Ruby/Go/Elixir repos means building their toolchains here. I verified the
  static half everywhere and the proving half only against core's own fixture.
- **The fleet inventory is a snapshot** of 2026-09-30. The counts (139 / 101 / 38)
  are stated as measurements of these twelve trees, not as a fleet invariant; a
  new spelling appearing tomorrow will not be covered until someone reads it in.
- **`TASK_RUNNER_CALL` is a heuristic** (`mise` / `make` / `just` at the start of
  a `run:` line). I chose narrow over broad deliberately, but the boundary between
  "wrapper" and "something else" is a judgement, not a proof.
- **I did not exercise GitHub Actions.** Everything here is about workflow *text*;
  whether a `run:` body is reached at all — event filters, path filters, `if:`
  conditions, a job that does not run on this branch — remains `notEnforced` and
  is still what core's CI runs `--prove` for.
- **`run: >` folded scalars** are matched but no workflow in this fleet uses one;
  the case is a guard, not a reproduction.

### One new hole I opened, and did not paper over

Fixing the anchor introduces a vector the broken pattern did not have: a line
reading `run: bin/gate` **nested under another mapping** (an `env:` value, a
`with:` input) is now read as a command, because `workflow_run_lines` tracks
indentation inside a `run:` block and nothing else.

I measured it rather than guessing: across all 139 `run:` keys in the twelve
trees, **every one** is a direct child of a step's `- name:` / `- uses:`. Not one
is nested. Closing it properly means parsing the workflow, which is the second
YAML dialect this file exists to avoid, so it is recorded in
`harness/gate_findings.json` `notEnforced` and in `docs/gate.md` rather than
half-fixed. The realistic cost is nil: it needs a file to contain the literal
text `run: <gate>` somewhere other than where it runs the gate — and anyone who
wanted to fool this checker could write it where it belongs.

---

## 8. The `cafaye-rb` restoration — owed, and mechanical

Not done here: the brief says do not edit `cafaye-rb` from this worktree, and I
did not touch it (read-only throughout). Verified against a throwaway copy at
`a45c35c`: applying this and running the fixed checker gives **exit 0**, and
deleting the step afterwards still gives `FAIL gate.ci-disagrees`, exit 1.

**File:** `cafaye-rb/.github/workflows/ci.yml`. Delete the workaround comment at
**lines 59–68** (10 lines) and collapse the step at **lines 69–71** from three
lines to two:

```diff
-      # A block scalar rather than `run: ./bin/prime` on one line, and the
-      # command is byte-identical either way — this is not a behaviour change.
-      #
-      # It is here because core's gate declaration is checked by
-      # harness/gate_check.py, whose RUN_KEY regular expression only matches a
-      # `run:` key that is bare or carries a `|`/`>` block scalar. A one-line
-      # `run: ./bin/prime` is invisible to it, so `gate.ci-disagrees` reports
-      # that this workflow never runs the gate when it plainly does. Written this
-      # way the step is readable, and the check that exists to catch CI drift is
-      # actually looking at it. See REPORT-core-10.md.
       - name: bin/prime
-        run: |
-          ./bin/prime
+        run: ./bin/prime
```

Result: the step is byte-identical in behaviour to `run: ./bin/prime`, which is
what `gate.yml` already declares (`invokes: [./bin/prime]`), so **`gate.yml`
needs no change**. `REPORT-core-10.md` in that repository documents the
workaround; that paragraph is now stale and is the manager's to amend — I did not
edit it.

**Flagging to the manager as a one-line follow-up:** this is the last thing
holding `cafaye-rb` in a shape chosen to satisfy a bug, and it should land
immediately after this merges, before another repository copies it.

---

## 9. Why not remove the check

The brief allows for this conclusion; I reached the opposite one, and the
argument belongs here so the manager can disagree with evidence.

`gate.ci-disagrees` did fire falsely, but the defect was **its pattern, not its
premise**. The question it asks — *does CI still run the gate?* — is the right
question, and it is the only automated thing standing between a repository and a
green badge on a pipeline that stopped testing. Removing it would trade a checker
that is right about its job and wrong about 38 spellings for no checker at all.

Removing it would also have been cheaper and would have looked responsible. The
two tests that caught this — twelve accepted spellings and the extractor pair —
only exist because the brief insisted on a checker proven on its *correct*
inputs. That is the transferable part: **a checker proven only on its red cases
is a checker proven only on the inputs somebody already disliked.** The twenty-five
breakages were all green while this check cried wolf, because every one of them
was a red.

What I would accept as an argument for removal: if `ci.invokes` turns out to be
a field nobody fills truthfully, the check becomes noise. It is filled truthfully
today — in core, cafaye-rb, courier, muse and four other worktrees in this fleet —
and the checker now reads the shapes those repositories actually use.

---

## Files changed

| file | what |
| --- | --- |
| `harness/gate_check.py` | `RUN_KEY`; caller rewritten; `check_ci` policy + `gate.ci-unproven`; `_invokes_declared_task`, `TASK_RUNNER_CALL` |
| `harness/tests/gate_self_test.sh` | positive-case helpers; 12 accepted spellings; 4 extractor assertions; 2 warning cases; counts reported separately; 0 skips |
| `tests/test_specs.py` | 3 tests, so `bin/prime` itself catches a regression |
| `gate.yml` | ratchet floor 163 → 166 |
| `harness/gate_findings.json` | `gate.ci-unproven` entry; 2 `notEnforced` entries |
| `docs/gate.md` | the policy; the spellings; the new hole |
| `REPORT-core-12.md` | this |

**Not touched:** `cafaye-rb` and every other sibling, read-only. No push, no
merge, no remote, `master` untouched.
