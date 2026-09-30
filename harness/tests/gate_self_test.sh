#!/usr/bin/env bash
#
# gate_self_test.sh — the gate checker's proof that it is able to fail.
#
#   bash harness/tests/gate_self_test.sh
#
# WHAT THIS IS FOR
#
# A checker that has only ever said "yes" is a report, not a gate. This script
# takes ONE conforming fixture — a small repository that declares its gate and
# tells the truth about all of it — copies it twenty-three times, breaks exactly
# one thing in each copy, and asserts the checker goes red each time. Every
# breakage names the finding it expects, so a red proves that *the check
# written for that defect* is still load-bearing, which is a different claim
# from "something went red" and the one that decays silently.
#
# The shape is harness/tests/self_test.sh's, and it is the same shape for the
# same reason: a control on the unbroken fixture first (without it twenty-three
# reds prove nothing), a fresh throwaway copy per breakage (one must never mask
# the next), and a non-zero exit if any breakage stayed green. Nothing in the
# committed tree is a deliberately broken repository — the breakages are diffs
# applied here, so a reviewer reads what is being broken rather than having to
# reconstruct it.
#
# THE ONE THAT MATTERS IS BREAKAGE 7
#
# Twelve of these breakages are a checker string-matching: the command names a
# file that is not there, the task is not in the config, the workflow does not
# call the gate. A checker that did nothing but compare strings would pass all
# twelve. Breakage 8 is a repository whose declaration is **well formed and
# completely true about a gate that exits 0 without having run anything**, and
# it is the whole reason `gate.proof` exists. It is also the shape this fleet
# has already shipped once: `… | tail -45; echo "PRIME EXIT=$?"` under zsh,
# where `$?` is `tail`'s, read as "PRIME EXIT=0" over a log that said FAIL.
#
# THE WARNINGS ARE TESTED TOO, AND SO IS THE PROMISE THEY MAKE
#
# Five breakages produce a `warn`, and `expect_warn` asserts the **exit code is
# still 0** in every one of them. That is the tri-state contract of MD13 made
# mechanical: a warning is a claim this machine could not settle, it is printed
# and counted separately, and it never moves the verdict. A checker that turned
# a warning into a failure would be one that is red on a laptop and green on CI,
# which is the same defect in a new place.
#
# WHAT IT IS NOT
#
# Not exhaustive mutation testing, and it does not claim to catch every defect.
# It proves twenty-three specific things, plus that the checker does not launder
# a secret out of a gate's output into its own report. It does not prove the
# gate's tests touched what they claim to — that is MD12's collect-then-run
# machinery, owed in `caf`, and harness/gate_findings.json names it.
#
# It is deliberately not inside `bin/prime`. A self-test that ran in every gate
# invocation would be a second gate that can disagree with the first, which is
# why core's CI runs it as a step of its own. The three breakages the packet
# names — the missing command, the missing task, and the false green — are
# *also* in tests/test_specs.py, so the gate itself is red if those three stop
# being caught; this script is the wider net.

set -uo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
HARNESS="$ROOT/harness"
FIXTURE="$HARNESS/tests/fixtures/gates/conforming"

PY="${CAFAYE_GATE_PYTHON:-}"
if [ -z "$PY" ]; then
  for candidate in python3 python3.13 python3.12 python3.11 python; do
    if command -v "$candidate" >/dev/null 2>&1; then PY="$candidate"; break; fi
  done
fi
if [ -z "$PY" ] || ! "$PY" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)'; then
  echo "gate_self_test: no python >= 3.11 found; set CAFAYE_GATE_PYTHON" >&2
  exit 1
fi

if [ ! -d "$FIXTURE" ]; then
  echo "gate_self_test: the conforming fixture is missing at $FIXTURE" >&2
  exit 1
fi

WORK="$(mktemp -d "${TMPDIR:-/tmp}/cafaye-gate-self-test.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT

failures=0
breakages=0
warn_cases=0
copy_name=""

# A fresh copy of the conforming fixture per breakage. The fixture carries its
# own mise.toml, bin/ and .github/, so a copy of the fixture is a copy of a
# repository; nothing outside the fixture is read, and the worktree is not
# touched.
fresh_copy() {
  copy_name="$1"
  local dst="$WORK/$copy_name"
  rm -rf "$dst"
  cp -R "$FIXTURE" "$dst"
  chmod +x "$dst/bin/gate"
  printf '%s' "$dst"
}

# edit <file> <old> <new> — a textual breakage that FAILS LOUDLY if the fixture
# has moved past it. A self-test that silently stops breaking anything is worse
# than no self-test, so an unmatched edit is an error here rather than a pass.
edit() {
  "$PY" - "$1" "$2" "$3" <<'PY'
import sys

path, old, new = sys.argv[1], sys.argv[2], sys.argv[3]
body = open(path, encoding="utf-8").read()
if old not in body:
    sys.exit(f"gate_self_test: breakage no longer applies to {path}: {old!r} not found")
open(path, "w", encoding="utf-8").write(body.replace(old, new, 1))
PY
}

# write <file> <content-on-stdin> — for a breakage that replaces a whole file,
# such as the gate that exits zero without running anything.
write() {
  cat > "$1"
}

# expect_red <label> <repo> <finding-id> — the fixture must go red, the exit
# code must be 1, and the finding must be NAMED. "Something went red" is not
# the claim; "this check is still the one that catches this defect" is.
expect_red() {
  local label="$1" repo="$2" expect="$3"
  local out
  out="$("$PY" "$HARNESS/gate_check.py" --prove --log-dir "$repo/.log" "$repo" 2>&1)"
  local code=$?
  if [ "$code" -ne 1 ]; then
    printf 'FAIL gate_self_test: %s — expected exit 1, got %s\n%s\n' "$label" "$code" "$out" >&2
    failures=$((failures + 1))
    return
  fi
  if ! printf '%s' "$out" | grep -q "$expect"; then
    printf 'FAIL gate_self_test: %s — went red as %s but never said %s\n%s\n' \
      "$label" "something else" "$expect" "$out" >&2
    failures=$((failures + 1))
    return
  fi
  printf 'PASS gate_self_test: breakage %s: %s — caught by `%s`\n' "$breakages" "$label" "$expect"
}

# expect_warn [--prove] <label> <repo> <finding-id> — the fixture must print the
# finding AND STILL EXIT 0. The exit code is the half that matters, and it is
# the half a tri-state checker gets wrong.
expect_warn() {
  local prove_it=""
  if [ "${1:-}" = "--prove" ]; then prove_it="--prove"; shift; fi
  local label="$1" repo="$2" expect="$3"
  local out
  # shellcheck disable=SC2086
  out="$("$PY" "$HARNESS/gate_check.py" $prove_it --log-dir "$repo/.log" "$repo" 2>&1)"
  local code=$?
  if [ "$code" -ne 0 ]; then
    printf 'FAIL gate_self_test: %s — a warning moved the exit code to %s\n%s\n' \
      "$label" "$code" "$out" >&2
    failures=$((failures + 1))
    return
  fi
  if ! printf '%s' "$out" | grep -q "$expect"; then
    printf 'FAIL gate_self_test: %s — exited 0 without even printing %s\n%s\n' \
      "$label" "$expect" "$out" >&2
    failures=$((failures + 1))
    return
  fi
  warn_cases=$((warn_cases + 1))
  printf 'PASS gate_self_test: warning %s: %s — said `%s` and still exited 0\n' \
    "$warn_cases" "$label" "$expect"
}

# expect_no_leak <label> <repo> <secret> — a gate whose output contains a value
# read from its environment. The checker's REPORT must not contain it, and its
# log file must: the report is what a person reads and what a CI log keeps, and
# the log is the gate's own output, which is the operator's to read.
expect_no_leak() {
  local label="$1" repo="$2" secret="$3"
  local out log
  out="$(DATABASE_URL="$secret" "$PY" "$HARNESS/gate_check.py" \
    --prove --log-dir "$repo/.log" "$repo" 2>&1)"
  local code=$?
  log="$(cat "$repo/.log/gate.log" 2>/dev/null || true)"
  if [ "$code" -ne 1 ]; then
    printf 'FAIL gate_self_test: %s — expected the leaky gate to be red, got %s\n' "$label" "$code" >&2
    failures=$((failures + 1))
  elif printf '%s' "$out" | grep -qF "$secret"; then
    printf 'FAIL gate_self_test: %s — the checker copied a value out of the gate environment into its own report\n' \
      "$label" >&2
    failures=$((failures + 1))
  elif ! printf '%s' "$log" | grep -qF "$secret"; then
    printf 'FAIL gate_self_test: %s — the gate log should hold the gate output; it does not, so the check above proved nothing\n' \
      "$label" >&2
    failures=$((failures + 1))
  else
    printf 'PASS gate_self_test: the gate that leaked at runtime: the report stayed clean and the log held it\n'
  fi
}

# --------------------------------------------------------------------------
# the control. Without it, twenty-three reds prove nothing at all: a checker that
# refused everything would satisfy every expectation below.
# --------------------------------------------------------------------------
control="$(fresh_copy control)"
out="$("$PY" "$HARNESS/gate_check.py" --prove --log-dir "$control/.log" "$control" 2>&1)"
code=$?
if [ "$code" -ne 0 ]; then
  printf 'FAIL gate_self_test: the control — a repository whose declaration is true — did not come back green (exit %s)\n%s\n' \
    "$code" "$out" >&2
  failures=$((failures + 1))
else
  printf 'PASS gate_self_test: the control — a repository whose declaration is true — is green in both phases\n'
fi

# --------------------------------------------------------------------------
# the breakages
# --------------------------------------------------------------------------

breakages=$((breakages + 1))
one="$(fresh_copy no-declaration)"
rm -f "$one/gate.yml"
expect_red 'a repository that declares no gate at all' "$one" 'gate.declaration-missing'

breakages=$((breakages + 1))
two="$(fresh_copy command-missing)"
edit "$two/gate.yml" 'command: [bin/gate]' 'command: [bin/absent]'
expect_red 'a gate command naming a file this repository does not have' "$two" 'gate.command-missing'

breakages=$((breakages + 1))
two_a="$(fresh_copy entrypoint-missing)"
edit "$two_a/gate.yml" 'entrypoint: bin/gate' 'entrypoint: bin/absent'
expect_red 'a gate entrypoint this repository does not have, while the command still does' \
  "$two_a" 'gate.entrypoint-missing'

breakages=$((breakages + 1))
three="$(fresh_copy entrypoint-not-executable)"
chmod -x "$three/bin/gate"
expect_red 'a gate nobody is allowed to execute' "$three" 'gate.entrypoint-not-executable'

breakages=$((breakages + 1))
four="$(fresh_copy task-missing)"
edit "$four/gate.yml" 'miseTask: prime' 'miseTask: verify'
expect_red 'a mise task that is not in the mise config' "$four" 'gate.task-missing'

breakages=$((breakages + 1))
five="$(fresh_copy task-unresolvable)"
edit "$five/mise.toml" 'run = "bin/gate"' 'run = "bin/something-else"'
expect_red 'a mise task that resolves to a different file than the declaration names' \
  "$five" 'gate.task-unresolvable'

breakages=$((breakages + 1))
six="$(fresh_copy task-config-missing)"
rm -f "$six/mise.toml"
expect_red 'a mise task named in a repository that has no mise config' \
  "$six" 'gate.task-config-missing'

# ------------------------------------------------------------------ 8 of 23
# The one that is not string matching. Everything above is a checker reading
# two files and disagreeing; this is a declaration that is entirely TRUE — the
# command exists, it is runnable, the task is in the config, CI calls it — about
# a gate that exits 0 and does nothing at all. Nothing about the declaration is
# wrong. The only thing that catches it is asking the gate to say what it did.
breakages=$((breakages + 1))
seven="$(fresh_copy false-green)"
write "$seven/bin/gate" <<'SH'
#!/usr/bin/env bash
# A well-formed gate that runs nothing and says nothing, and exits 0.
# This is the false green, reproduced deliberately: every string in the
# declaration about this repository is true, and the repository is ungated.
exit 0
SH
chmod +x "$seven/bin/gate"
expect_red 'a declaration that is entirely true about a gate that exited 0 without running anything' \
  "$seven" 'gate.proof-missing'

breakages=$((breakages + 1))
eight="$(fresh_copy floor)"
edit "$eight/gate.yml" 'minimum: 3' 'minimum: 40'
expect_red 'a gate that proves one test where the declaration promised forty' "$eight" 'gate.floor'

breakages=$((breakages + 1))
nine="$(fresh_copy nonzero)"
write "$nine/bin/gate" <<'SH'
#!/usr/bin/env bash
# Runs, proves itself, and fails. The proof is there and the gate is still red,
# which is the other half of the contract: `gate.proof-missing` on its own would
# accept a gate that never printed anything AND exited zero.
set -euo pipefail
echo "2/3 passed"
echo "FAIL test_the_third_thing" >&2
exit 1
SH
chmod +x "$nine/bin/gate"
expect_red 'a gate that ran the suite, printed its proof, and failed' "$nine" 'gate.nonzero'

breakages=$((breakages + 1))
ten="$(fresh_copy ci-disagrees)"
edit "$ten/.github/workflows/ci.yml" 'bin/gate' 'echo "nothing here"'
expect_red 'a CI workflow that never runs the gate' "$ten" 'gate.ci-disagrees'

breakages=$((breakages + 1))
eleven="$(fresh_copy proof-uncompilable)"
edit "$eleven/gate.yml" "match: '^([0-9]+)/[0-9]+ passed\$'" "match: '^([0-9]+/[0-9]+ passed\$'"
# Caught at the SHAPE layer, not the proving layer, and that is the better
# answer: a pattern that does not compile is refused by the schema check
# without the gate being run at all. The alternative — noticing it only after
# spending the gate's whole runtime — is what this packet's first false green
# looked like.
expect_red 'a proof whose pattern does not compile, which would otherwise read as "no proof required"' \
  "$eleven" 'gate.schema'

breakages=$((breakages + 1))
twelve="$(fresh_copy requirement-empty)"
edit "$twelve/gate.yml" '  selfContained: true' '  selfContained: false'
expect_red 'a gate that says it is not self-contained and names no way to satisfy what it needs' \
  "$twelve" 'gate.schema'

breakages=$((breakages + 1))
thirteen="$(fresh_copy requirement-path-missing)"
edit "$thirteen/gate.yml" '  selfContained: true
  requirements: []' '  selfContained: false
  requirements:
    - kind: toolchain
      name: a venv builder that this repository does not carry
      satisfy:
        command: [bin/absent-setup]'
expect_red 'an external requirement satisfied by a file that is not in this repository' \
  "$thirteen" 'gate.requirement-path-missing'

breakages=$((breakages + 1))
fourteen="$(fresh_copy declaration-unreadable)"
edit "$fourteen/gate.yml" 'name: gate-fixture' 'name: &anchor gate-fixture'
expect_red 'a declaration using a YAML construct core'"'"'s reader refuses' \
  "$fourteen" 'gate.declaration-unreadable'

breakages=$((breakages + 1))
fifteen="$(fresh_copy command-unknown)"
edit "$fifteen/gate.yml" 'command: [bin/gate]' 'command: [gate-check-not-on-any-path]'
expect_warn 'a gate command that is a bare name this machine does not have' \
  "$fifteen" 'gate.command-unknown'

breakages=$((breakages + 1))
sixteen="$(fresh_copy task-unreadable)"
edit "$sixteen/mise.toml" 'run = "bin/gate"' 'run = "bin/gate | tee /dev/null"'
expect_warn 'a mise task whose run string is a pipeline, so only a shell could say what it runs' \
  "$sixteen" 'gate.task-unreadable'

breakages=$((breakages + 1))
seventeen="$(fresh_copy task-undeclared)"
edit "$seventeen/gate.yml" '  miseTask: prime
' ''
expect_warn 'a repository with mise tasks and a declaration that names none of them' \
  "$seventeen" 'gate.task-undeclared'

breakages=$((breakages + 1))
eighteen="$(fresh_copy ci-missing)"
edit "$eighteen/gate.yml" 'workflow: .github/workflows/ci.yml' 'workflow: .github/workflows/nope.yml'
expect_red 'a declaration naming a CI workflow that is not in this repository' \
  "$eighteen" 'gate.ci-missing'

breakages=$((breakages + 1))
nineteen="$(fresh_copy ci-undeclared)"
edit "$nineteen/gate.yml" 'ci:
  workflow: .github/workflows/ci.yml
  invokes: [bin/gate]
' ''
expect_warn 'a declaration that says nothing about CI' "$nineteen" 'gate.ci-undeclared'

breakages=$((breakages + 1))
twenty="$(fresh_copy requirement-unproven)"
edit "$twenty/gate.yml" '  selfContained: true
  requirements: []' '  selfContained: false
  requirements:
    - kind: toolchain
      name: a command on PATH that this checker deliberately did not run
      satisfy:
        command: [mise, install]'
expect_warn --prove 'an external requirement nobody ran, which is reported and never acted on' \
  "$twenty" 'gate.requirement-unproven'

breakages=$((breakages + 1))
twentyone="$(fresh_copy timeout)"
edit "$twentyone/gate.yml" 'timeoutSeconds: 60' 'timeoutSeconds: 1'
write "$twentyone/bin/gate" <<'SH'
#!/usr/bin/env bash
# A gate that provably outlives its one-second budget, and WITHOUT a sleep.
#
# `sleep 5` would be a guess about timing wearing a test's clothes: it makes the
# result depend on the scheduler rather than on the checker. This is a
# three-second CPU-bound wait, so the only way it can finish inside a one-second
# budget is for the clock to have lied. It also ends by itself, so a checker
# that failed to stop it makes this script slow rather than hung.
set -euo pipefail
python3 - <<'PY'
import time

end = time.monotonic() + 3.0
while time.monotonic() < end:
    pass
PY
echo "3/3 passed"
SH
chmod +x "$twentyone/bin/gate"
expect_red 'a gate that outlived the budget its own declaration gave it' "$twentyone" 'gate.timeout'

# ------------------------------------------------------------------ 22 of 22
# The other half of `gate.proof-invalid`, and the one that only the PROVING
# phase can see: the pattern compiles, the declaration is well formed, and the
# floor it promises is read from a capture group that is not there. A checker
# that silently treated that as "no floor" would accept a suite of any size,
# which is the same false green with one more step around it.
breakages=$((breakages + 1))
twentytwo="$(fresh_copy proof-unmeasurable)"
edit "$twentytwo/gate.yml" "match: '^([0-9]+)/[0-9]+ passed\$'" "match: '^[0-9]+/[0-9]+ passed\$'"
expect_red 'a proof with a floor and no capture group to read the floor from' \
  "$twentytwo" 'gate.proof-invalid'

# --------------------------------------------------------------------------
# the hygiene case. Not a finding id, because it is not a finding: it is the
# property that no finding may ever be one.
# --------------------------------------------------------------------------
leak="$(fresh_copy secret-output)"
write "$leak/bin/gate" <<'SH'
#!/usr/bin/env bash
# A gate that leaks a value out of its own environment into its output, the way
# a failing assertion that formats a connection string does. No off-the-shelf
# tool detects this: 0 of 268 Semgrep rules intersect CWE-532, gosec has no
# ast.CallExpr case, Bandit is ast.Constant-only. So the checker's own report
# must not carry the value, and that is a test rather than a promise.
set -uo pipefail
echo "could not reach ${DATABASE_URL:-unset}"
echo "2/3 passed"
exit 1
SH
chmod +x "$leak/bin/gate"
expect_no_leak 'the gate that leaked at runtime' "$leak" \
  'postgres://gate:should-never-be-printed@localhost:5432/gate'

# --------------------------------------------------------------------------

printf '\n'
if [ "$failures" -ne 0 ]; then
  printf 'FAIL: gate_self_test — %s of %s breakages and %s warning cases the gate checker did not get right.\n' \
    "$failures" "$breakages" "$warn_cases"
  exit 1
fi
printf 'PASS: gate_self_test — all %s breakages went red, all %s warning cases stayed green, the control is green, and the report carried no secret.\n' \
  "$breakages" "$warn_cases"
