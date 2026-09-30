# REPORT-core-13 — a proof is matched against bytes that still carry terminal colour

Branch `worker/core-13-ansi`, base `master` (71d01fd), one commit: `1626722`.
Implements MD17 as ruled. No schema changed. No other repository touched.

## What changed

| File | What |
| --- | --- |
| `harness/gate_check.py` | `ANSI_ESCAPE` + `strip_ansi()`, called **once**, in `prove()` |
| `harness/tests/gate_self_test.sh` | 3 green cases + 2 colour reds, plus `expect_green` / `expect_colour_red` |
| `tests/test_specs.py` | 7 new tests (163 → 170) |
| `docs/gate.md` | new section **The output is matched colour-free** |
| `gate.yml` | floor 163 → **170**, in the same commit, per the ratchet |
| `CHANGELOG.md` | a **Fixed** entry, because adopters must re-read their patterns |

**One function, one call site.** `strip_ansi` is referenced twice in
`gate_check.py` — the definition and a single call inside `prove()`, where the
output is read, before any pattern sees it. `test_the_stripper_runs_in_exactly_one_place_and_only_on_proof_matching`
asserts that *structurally* (it counts references and checks the call sits inside
`prove` and before the first `finditer`), because the shape is the point: four
checks apply `proof[].match`, and four strip calls would be four sites that drift.

**The log keeps the raw bytes.** Stripping is for matching only. The log is the
operator's evidence, and a log that disagreed with the output it records would be
a worse lie than the false red being fixed. Asserted both ways in the same test.

## Which sequences are handled, and which are not

**Handled** — each asserted on its own in `test_the_gate_checker_strips_every_escape_sequence_it_declares_it_handles`:

- **CSI** `ESC [ … final`, and 8-bit `0x9b`. SGR colour, cursor moves, erase-line, private modes (`ESC[?25l`). What `vitest`, `cargo test`, `pytest`, `go test` and colour-enabled `mix test` emit.
- **OSC** `ESC ] … BEL` or `… ST`, and 8-bit `0x9d`. Window titles (OSC 0/2), hyperlinks (OSC 8).
- **DCS** `ESC P … ST`, plus SOS/PM/APC.
- **Two-character escapes** — charset selection, keypad mode (`ESC ( B`, `ESC 7`, …).

**Not handled, deliberately: an unterminated sequence.** It is left in place
rather than consumed to end-of-input. The tempting alternative deletes every line
after it — the proof included — and turns an absent proof into a green, which is
exactly the class of defect this packet exists to end. **Consequence, stated:** a
gate whose runner leaves a sequence unterminated will have its proof pattern
matched against bytes that still contain that sequence, so an anchored pattern can
still miss. The fix belongs in the gate's runner flags, not in a wider regex. A
malformed gate is allowed to fail loudly. Covered by a green self-test case where
a proof sits on the line *after* an unterminated OSC.

**Two properties that keep `^` and `$` meaningful**, both asserted:

- The OSC/DCS bodies exclude `\n`, so **stripping never changes the line count**. A stripper that can span a newline joins two lines, and then `^[ ]*Tests` can match a pattern straddling a line boundary.
- Stripping **only ever deletes** — asserted character-by-character as a subsequence property over the real inputs, not as a claim in a comment.

A naive `ESC \[ … m`-only stripper fails the OSC cases (verified before writing
them: `\x1b]0;vitest run\x07\x1b[2mTests\x1b[22m 3/3 passed` still does not match
`^Tests` after CSI-only stripping, because the OSC is still there). A greedy
`ESC\[.*m` was the truncation hazard and is not what ships.

## The weakening analysis (packet item 2)

**Stripping CAN weaken a pattern.** The ruling's phrasing — "colour carries no
assertion, so the fix cannot weaken a pattern" — is true of *what the escapes
contain* and false of *what a pattern can match*. Two mechanisms, both measured
against the real matching code rather than reasoned about:

**1. An anchored pattern can reach a line it could not reach — and the floor
reads the LAST match.** `^` binds to the start of a line. With the escape
present, `^[ ]*Tests` cannot match `\x1b[2m Tests`; stripped, it can. Measured,
with the real declared pattern and the real vitest bytes:

```
log: "      Tests  377 passed\n" + "\x1b[2m      Tests \x1b[22m … 2 passed …\n"
raw matches      : ['377']        stripped matches: ['377', '2']
floor reads      : 377            floor reads     : 2
```

With `minimum: 3` the raw bytes **pass** and the stripped bytes go **red**. So
stripping can move the ratchet's number in the failing direction, and that is the
direction the packet's instinct ("stripping only removes noise") does not
predict. Documented in `docs/gate.md` with the mitigation: *anchor the whole
line, and do not let one pattern cover two different summary lines.*

**2. `.` counts different bytes on each side.** `^.{6}Tests` does not match
`\x1b[2m      Tests…` (escape bytes) and does match the stripped line (visible
bytes) — verified. It names a different line on each side. Documented with the
mitigation: *do not count characters to find a position; match the words.*

**What IS unconditional**, and what the ruling actually rests on: stripping only
ever **deletes**. It never inserts or reorders a byte, so it cannot fabricate a
match out of nothing.

**The inverse false green this also removes.** Every account of this defect in
MD17 is a false *red*. The mirror is quieter and is now a test: `\x1b[38;5;208m`
is a 256-colour **index**, so a gate that ran **3** tests and printed
`\x1b[38;5;208m3 passed` matches `^.*?([0-9]+).* passed$` with `group(1) == "38"`
— `minimum: 38` was green over a suite of three. Asserted both as a unit fact and
end-to-end through the checker as `gate.floor`.

## Gate results — pass and skip counted separately

**`bash harness/tests/gate_self_test.sh` — PASS**

- **23 breakages** went red, each naming the finding it expects
- **5 warning cases** stayed green (exit 0 asserted)
- **3 green cases** matched a colour-bearing gate
- **2 colour reds** still went red
- **the control is green** (asserted explicitly, per D13 — not merely unmentioned)
- 1 leak case: the report stayed clean and the log held the value
- **0 skips, 0 failures**

**`tests/.venv/bin/python tests/test_specs.py` (what `bin/prime` runs) — PASS,
170/170, 0 skips, 0 failures.**

**`bash harness/tests/self_test.sh` — PASS**, 28 breakages, unbroken tree green.

**`harness/gate_check.py --prove .` on core — exit 0**, 0 failures, 1 warning
(`gate.requirement-unproven`, the tri-state case, unchanged).

Baseline before the change was 23 breakages / 5 warnings / control green; the
counts did not move.

**Tests were watched red first.** Before the fix: 3 self-test colour cases failed
(2 expected-green, 1 wrong-finding), and in the suite 4 tests FAILed and 3 ERRORed
on `module has no attribute 'strip_ansi'` — 163/170. After: 170/170.

**I also verified the colour cases genuinely depend on the fix** by reverting
only the call site (`matchable = output`) while keeping `strip_ansi` defined: 3 of
the colour cases went red again. A test that passes with and without the fix
proves nothing, and the fixture's use of `printf '%b'` (not `'%s'`, which would
have emitted a literal `\x` and no escapes at all) is commented so it cannot
quietly stop testing that.

## What I could not verify

- **`cargo test`, `pytest`, `go test`, `mix test` were not run.** MD17 lists them
  as the same shape; I handled the sequence classes generically and asserted them
  as byte strings, but no real log from any of them was captured, so their actual
  byte output is unverified. `vitest` is the only one confirmed against real bytes.
- **I did not confirm `darkroom`'s `test result: ok\. ([1-9][0-9]*) passed` still
  matches.** It looks colour-free already, but `cargo test` emits colour under a
  TTY and I have no real `cargo` log. Worth a look once someone runs one.
- **No 8-bit (C1) sequence from a real tool** — `0x9b`/`0x9d` are asserted from
  the spec's byte values, not from captured output.
- **The OSC-8 hyperlink case strips the wrapper and keeps the link text.** That is
  the intended reading (the link text is what the terminal renders), but a gate
  that emits a link *inside* its proof line will see the text joined, not removed.
  Flagged rather than solved, because the alternative — deleting rendered text —
  is the mangling failure.
- **`--prove` on a colourising gate was not run against the real `core-10-parlor`
  worktree.** I reproduced its exact declared pattern against the exact bytes MD17
  quotes, in a throwaway fixture, and it exits 0 — but I did not run that
  repository's own `bin/gate`.
- **No performance measurement** on an 8 MB capture. The regex is linear and
  non-backtracking per alternative; the OSC/DCS alternatives can backtrack within
  a line, which is bounded by line length. Not measured, so not claimed.

## The exact `cafaye-rb` restoration edit

**Do not apply until `core-12` (D12, `RUN_KEY`) has landed** — this is the debt
DEBT.md records as owed *in the same commit as the fix*.

`cafaye-rb/.github/workflows/ci.yml`, current (from `a45c35c`), lines 59–71:

```yaml
      # A block scalar rather than `run: ./bin/prime` on one line, and the
      # command is byte-identical either way — this is not a behaviour change.
      #
      # It is here because core's gate declaration is checked by
      # harness/gate_check.py, whose RUN_KEY regular expression only matches a
      # `run:` key that is bare or carries a `|`/`>` block scalar. A one-line
      # `run: ./bin/prime` is invisible to it, so `gate.ci-disagrees` reports
      # that this workflow never runs the gate when it plainly does. Written this
      # way the step is readable, and the check that exists to catch CI drift is
      # actually looking at it. See REPORT-core-10.md.
      - name: bin/prime
        run: |
          ./bin/prime
```

becomes exactly:

```yaml
      - name: bin/prime
        run: ./bin/prime
```

That is the whole edit: **delete the 10-line comment block and the two-line block
scalar, replace with one line.** The command (`./bin/prime`) is byte-identical
either way, so this is not a behaviour change — it removes a permanent workaround
for a bug in core that `core-12` fixes. Once `core-12` lands, the comment is a
lie (it describes a `RUN_KEY` limitation that no longer exists), which is why
AGENTS.md treats the mitigation as owed rather than as a cleanup.

**Not applied from this worktree**, per the packet. Applying it is mechanical
once `core-12` is merged.

## Open list

**No open decision.** MD17's direction was ruled and not re-opened; the shape
followed it (one function, one call site, log stays raw) and is written down in
`harness/gate_check.py` and `docs/gate.md`. I recorded it in `CHANGELOG.md` under
its **Fixed** section rather than as a `## Dn:` entry: core's `D` numbers are the
*open*-decision list (`test_open_decisions_are_numbered_and_complete` requires
four paragraphs and a citation from a document), and MD17 is a manager-owned
ruling that lives in the workspace `DECISIONS.md`. I tried adding it as `D33` first
and the suite correctly rejected it — settled numbers must stay below every open
one, and D6 is open. Flagging the reasoning in case the manager wants it promoted
to a numbered core decision; that is a manager call, not mine.