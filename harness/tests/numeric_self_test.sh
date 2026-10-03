#!/usr/bin/env bash
#
# numeric_self_test.sh — the numeric checker's proof that it is able to fail.
#
#   bash harness/tests/numeric_self_test.sh
#
# WHAT THIS IS FOR
#
# A checker that has only ever said "yes" is a report, not a gate. This script
# takes ONE conforming fixture — a small contract surface where every numeric
# position is one this checker is content with — copies it, breaks exactly one
# thing in each copy, and asserts the checker goes red each time. Every
# breakage names the finding it expects, so a red proves that *the check written
# for that defect* is still load-bearing, which is a different claim from
# "something went red" and the one that decays silently.
#
# The shape is harness/tests/tenancy_self_test.sh's, and it is the same shape for
# the same reason: a control on the unbroken fixture FIRST (without it every red
# below proves nothing — a checker that refused everything would satisfy all of
# them), a fresh throwaway copy per case so one must never mask the next, and a
# non-zero exit if any breakage stayed green. Nothing in the committed tree is a
# deliberately broken contract: the breakages are edits applied here, to copies,
# so a reviewer reads what is being broken rather than reconstructing it.
#
# THE FOUR RULES, AND WHAT EACH ONE MUST BE PROVED ABLE TO DO
#
#   numeric.float64-unsafe  FAILURE. An integer whose declared maximum reaches
#                           the float64 exact range, or an unbounded integer on
#                           a field named like an identity. It must be a string.
#   numeric.float           WARNING. `type: number`. It is a ratio, and a ratio
#                           that cannot be a whole number is not a rounding bug.
#   numeric.enum            WARNING. Codegen turns it into a closed union.
#   numeric.unsigned        NOT ENFORCED, and this script proves the SHAPE of
#                           that decision rather than its absence: a bare
#                           `minimum: 0` must stay GREEN, and the report must
#                           say out loud that unsignedness is unenforced. A rule
#                           examined and excluded on purpose is a decision; the
#                           same rule excluded silently is the defect.
#
# WHY numeric.unsigned IS NOT A BREAKAGE HERE
#
# Because there is no unsigned integer type in JSON at all. Go has no unsigned
# JSON, TypeScript has no unsigned number, and Python's bool IS an int, so the
# fact is not in any document this checker reads — it is in a service's own
# types. A rule that fired on the fleet's 45 `minimum: 0` positions would fire
# on every field of a passing contract, and a gate like that is switched off
# within one release, which leaves the fleet with NO check rather than an
# incomplete one. So the green case below is the proof: it stays green, it names
# why, and the notEnforced ledger carries the measured count.
#
# AND THE CASE THAT IS NOT ABOUT A FINDING AT ALL
#
# `unreadable/` is a malformed document. The required verdict is: a warning that
# NAMES the file, and an exit code of zero. A checker that answered "no numeric
# problems" over a file it could not parse would be converting an unknown into a
# green badge — the fourth repository to be told about that defect is identity's
# TEST_DATABASE_URL, and the rule in AGENTS.md is that a run which could not
# happen is reported, never folded into a pass.
#
# WHAT IT IS NOT
#
# It does NOT run against a real service checkout, and it does NOT prove the
# fleet's own surfaces are clean — that is a separate claim, measured in
# REPORT-core-numeric-01.md §5 from static facts only, because `harness/` may
# not take a dependency or open a connection. Nor does it prove that any of the
# six languages reads these fields correctly: this checker reads documents, and a
# service's own typed client is what proves that a Go int64 became a TypeScript
# number. What it proves is narrower and is the thing this packet exists for:
# that the CONTRACT did not invite it.
#
# THE `# (NN)` labels below are a reading aid and NOT an index. The number to
# trust is the one this script PRINTS in the counts block, because that one is
# produced by the counter rather than by a human counting.
#
# It is deliberately NOT inside `bin/prime`. A self-test that ran in every gate
# invocation would be a second gate that can disagree with the first, which is
# why core's CI runs harness/tests/self_test.sh and tenancy_self_test.sh as steps
# of their own — and why `bin/prime` still runs gate_self_test.sh, which is a
# different checker (see bin/prime's own header for why that asymmetry is
# deliberate and dated).

set -uo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
HARNESS="$ROOT/harness"
FIXTURES="$HARNESS/tests/fixtures/numeric"
CONFORMING="$FIXTURES/conforming"
NONCONFORMING="$FIXTURES/nonconforming"
UNREADABLE="$FIXTURES/unreadable"

PY="${CAFAYE_NUMERIC_PYTHON:-}"
if [ -z "$PY" ]; then
  for candidate in python3 python3.13 python3.12 python3.11 python3.10 python3.9 python; do
    if command -v "$candidate" >/dev/null 2>&1; then PY="$candidate"; break; fi
  done
fi
if [ -z "$PY" ] || ! "$PY" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 9) else 1)'; then
  echo "numeric_self_test: no python >= 3.9 found; set CAFAYE_NUMERIC_PYTHON" >&2
  exit 1
fi

for required in "$CONFORMING" "$NONCONFORMING" "$UNREADABLE"; do
  if [ ! -d "$required" ]; then
    echo "numeric_self_test: a fixture is missing at $required" >&2
    exit 1
  fi
done

WORK="$(mktemp -d "${TMPDIR:-/tmp}/cafaye-numeric-self-test.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT

failures=0
breakages=0
warn_cases=0
green_cases=0
not_enforced_cases=0

run_check() { "$PY" "$HARNESS/numeric_check.py" "$@"; }

# fresh_copy <name> <fixture> — a fresh throwaway copy per case, so one breakage
# can never mask the next. Nothing outside the fixture is read and the worktree
# is not touched.
fresh_copy() {
  # Two `local` statements, not one. `local name=$1 dst=$WORK/$name` expands
  # `$name` before the first assignment has taken effect under this shell's
  # `set -u`, so the copy lands at `/openapi.json` and every case below it fails
  # on a path that does not exist rather than on the thing under test.
  local name="$1"
  local fixture="$2"
  local dst="$WORK/$name"
  rm -rf "$dst"
  cp -R "$fixture" "$dst"
  printf '%s' "$dst"
}

# edit <file> <old> <new> — a textual breakage that FAILS LOUDLY if the fixture
# has moved past it, and on an AMBIGUOUS match as well as on no match. A
# self-test that silently stops breaking anything is worse than no self-test:
# it reports a pass for a check it had never exercised. `count(old) > 1` is the
# whole test, and it is the same rule harness/tests/tenancy_self_test.sh states.
edit() {
  "$PY" - "$1" "$2" "$3" <<'PY'
import sys

path, old, new = sys.argv[1], sys.argv[2], sys.argv[3]
body = open(path, encoding="utf-8").read()
found = body.count(old)
if found == 0:
    sys.exit(f"numeric_self_test: breakage no longer applies to {path}: {old!r} not found")
if found > 1:
    sys.exit(
        f"numeric_self_test: {path} contains {old!r} {found} times, so a replace of the "
        "first one may have edited a different field. Make the anchor unambiguous rather "
        "than hoping the first match is the right one."
    )
open(path, "w", encoding="utf-8").write(body.replace(old, new, 1))
PY
}

# expect_red <label> <repo> <finding-id> [needle] — the copy must go red, the exit
# code must be 1, the finding must be NAMED, and when a needle is given the
# message must name the FIELD too. The finding id says which CHECK fired; the
# needle says which POSITION it fired about, which is the claim actually being
# made — a red on `byte_size` and a red on `expires_at` are both
# `numeric.float64-unsafe`, and a proof that could not tell them apart would
# survive a rule that had grown a bug in one of the two.
expect_red() {
  local label="$1" repo="$2" expect="$3" needle="${4:-}"
  local out code
  out="$(run_check "$repo" 2>&1)"
  code=$?
  if [ "$code" -ne 1 ]; then
    printf 'FAIL numeric_self_test: %s — expected exit 1, got %s\n%s\n' "$label" "$code" "$out" >&2
    failures=$((failures + 1))
    return
  fi
  if ! printf '%s' "$out" | grep -q "$expect"; then
    printf 'FAIL numeric_self_test: %s — went red as something else and never said %s\n%s\n' \
      "$label" "$expect" "$out" >&2
    failures=$((failures + 1))
    return
  fi
  if [ -n "$needle" ] && ! printf '%s' "$out" | grep -q "$needle"; then
    printf 'FAIL numeric_self_test: %s — went red as %s but never named %s, so it cannot be\n' \
      "$label" "$expect" "$needle" >&2
    printf '  told apart from a different position losing the same property.\n%s\n' "$out" >&2
    failures=$((failures + 1))
    return
  fi
  breakages=$((breakages + 1))
  printf 'PASS numeric_self_test: breakage %s: %s — caught by `%s`%s\n' \
    "$breakages" "$label" "$expect" "${needle:+ about $needle}"
}

# expect_warn <label> <repo> <finding-id> — the finding must be printed AND the
# exit code must STILL BE zero. The exit code is the half that matters, and it
# is the half a checker gets wrong: 4 of core's own positions and 1 numeric enum
# are warnings today, so a warning that moved the exit code would make
# `bin/prime` red on a contract nobody has broken.
expect_warn() {
  local label="$1" repo="$2" expect="$3"
  local out code
  out="$(run_check "$repo" 2>&1)"
  code=$?
  if [ "$code" -ne 0 ]; then
    printf 'FAIL numeric_self_test: %s — a warning moved the exit code to %s\n%s\n' "$label" "$code" "$out" >&2
    failures=$((failures + 1))
    return
  fi
  if ! printf '%s' "$out" | grep -q "$expect"; then
    printf 'FAIL numeric_self_test: %s — exited 0 without printing %s\n%s\n' "$label" "$expect" "$out" >&2
    failures=$((failures + 1))
    return
  fi
  warn_cases=$((warn_cases + 1))
  printf 'PASS numeric_self_test: warning case %s: %s — named, and exit 0\n' "$warn_cases" "$label"
}

# expect_green <label> <repo> [must-print] — must come back green, and when a
# token is given the report must ALSO print it. The second half is what keeps a
# warning from becoming silence: a checker that reported nothing at all about a
# surface it could not read would pass this too, and that is precisely the shape
# this file exists to prevent.
expect_green() {
  local label="$1" repo="$2" must_print="${3:-}"
  local out code
  out="$(run_check "$repo" 2>&1)"
  code=$?
  if [ "$code" -ne 0 ]; then
    printf 'FAIL numeric_self_test: %s — expected green, got exit %s\n%s\n' "$label" "$code" "$out" >&2
    failures=$((failures + 1))
    return
  fi
  if [ -n "$must_print" ] && ! printf '%s' "$out" | grep -q "$must_print"; then
    printf 'FAIL numeric_self_test: %s — exited 0 without printing %s, so the thing it could\n' \
      "$label" "$must_print" >&2
    printf '  not check is being reported as nothing being there.\n%s\n' "$out" >&2
    failures=$((failures + 1))
    return
  fi
  green_cases=$((green_cases + 1))
  printf 'PASS numeric_self_test: green case %s: %s — exit 0%s\n' \
    "$green_cases" "$label" "${must_print:+ and named what it cannot check}"
}

# expect_not_enforced <label> <repo> <rule-id> — the surface must come back
# green, the report must name the rule, and the rule must appear in the
# notEnforced ledger. This is the proof for a rule DELIBERATELY not enforced:
# the honest half is that the ledger names it with a reason, and the mechanical
# half is that a surface the rule would have fired on still passes. Both halves
# are asserted, because a ledger entry with nothing behind it is documentation of
# a wish.
expect_not_enforced() {
  local label="$1" repo="$2" rule="$3"
  local out code
  out="$(run_check "$repo" 2>&1)"
  code=$?
  if [ "$code" -ne 0 ]; then
    printf 'FAIL numeric_self_test: %s — %s is declared not-enforced and still went red\n%s\n' \
      "$label" "$rule" "$out" >&2
    failures=$((failures + 1))
    return
  fi
  if ! printf '%s' "$out" | grep -q "$rule"; then
    printf 'FAIL numeric_self_test: %s — a surface %s would have fired on came back green\n' \
      "$label" "$rule" >&2
    printf '  WITHOUT the report ever naming %s, so the silence is indistinguishable from an\n' "$rule" >&2
    printf '  unexamined surface. The ledger is what makes this green honest.\n' >&2
    failures=$((failures + 1))
    return
  fi
  if ! "$PY" -c "
import sys
sys.path.insert(0, '$HARNESS')
import numeric_check
sys.exit(0 if '$rule' in numeric_check.NOT_ENFORCED else 1)
"; then
    printf 'FAIL numeric_self_test: %s — %s is not in numeric_check.NOT_ENFORCED\n' "$label" "$rule" >&2
    failures=$((failures + 1))
    return
  fi
  not_enforced_cases=$((not_enforced_cases + 1))
  printf 'PASS numeric_self_test: not-enforced case %s: %s — stayed green, and the rule is in the ledger\n' \
    "$not_enforced_cases" "$label"
}

# --------------------------------------------------------------------------
# THE CONTROL. FIRST, on the unbroken fixture, and warning-free.
# --------------------------------------------------------------------------
# Every red below is worth nothing without it: a checker that refused everything
# would satisfy all of them. It must also be warning-free rather than merely
# green, because a control that arrives already complaining cannot tell a
# conforming surface from one the checker has an opinion about.
control_out="$(run_check "$CONFORMING" 2>&1)"
control_code=$?
if [ "$control_code" -ne 0 ]; then
  printf 'FAIL numeric_self_test: the control — the conforming fixture must be green, got exit %s\n%s\n' \
    "$control_code" "$control_out" >&2
  failures=$((failures + 1))
elif printf '%s' "$control_out" | grep -qE '^numeric\.(float|enum|float64-unsafe)[[:space:]]'; then
  printf 'FAIL numeric_self_test: the control is green but not WARNING-FREE, so it cannot tell a\n' >&2
  printf '  conforming surface from one this checker has an opinion about.\n%s\n' "$control_out" >&2
  failures=$((failures + 1))
else
  printf 'PASS numeric_self_test: the control — the conforming surface is green and warning-free\n'
fi

# --------------------------------------------------------------------------
# THE BREAKAGES. Each one edits EXACTLY ONE field of the conforming fixture, so
# a red can name the position it fired about — and a checker that had grown a
# second trigger would still pass the case whose field it did not touch.
# --------------------------------------------------------------------------

# (1) An integer whose DECLARED maximum reaches the float64 exact range. The
# document already says the value gets that big, so this is a bug today rather
# than a possibility. The maximum is set to exactly the limit rather than far
# past it, because "at or past" is half the rule and a proof that only ever used
# an absurd value would not have exercised the boundary at all.
one="$(fresh_copy declared-maximum "$CONFORMING")"
edit "$one/openapi.json" '"maximum": 1000000' '"maximum": 9007199254740992'
expect_red 'an integer declaring a maximum AT the float64 exact range' \
  "$one" 'numeric.float64-unsafe' 'quantity'

# (2) One integer further on. 2**53 + 1 is the first value a binary64 cannot
# hold: it parses back as 2**53, so the number a Go service wrote and the number
# a TypeScript client read are different, and nothing logs.
two="$(fresh_copy one-past-the-limit "$CONFORMING")"
edit "$two/openapi.json" '"maximum": 1000000' '"maximum": 9007199254740993'
expect_red 'an integer declaring a maximum ONE PAST the float64 exact range' \
  "$two" 'numeric.float64-unsafe' 'quantity'

# (3) A ceiling just BELOW the limit, on a field nothing else about. The
# complement of (1): a rule that fired on any large maximum would fail here, and
# a rule that refused every bounded integer would fail the control. The green is
# the point — this is the boundary asserted from the other side.
three="$(fresh_copy just-below-the-limit "$CONFORMING")"
edit "$three/openapi.json" '"maximum": 1000000' '"maximum": 9007199254740991'
expect_green 'an integer whose maximum stops one short of the float64 exact range' \
  "$three"

# (4) An UNBOUNDED integer whose name says it carries an identity. Unbounded is
# only alarming where the ceiling is reachable: an int64 byte count can reach
# 2**53 and nothing but the writer bounds it. The name is what makes this one
# different from the retry count three lines away, which stays green below.
four="$(fresh_copy unbounded-identity "$CONFORMING")"
edit "$four/openapi.json" '"description": "A small non-negative integer with a ceiling well under 2**53. The breakages below rename this field and retype it; the ceiling is what makes it safe here.",
      "type": "integer",
      "minimum": 0,
      "maximum": 100' '"description": "A byte count with no maximum at all. Unbounded is only alarming where the ceiling is reachable, and an int64 file size reaches 2**53 with nothing but the writer bounding it.",
      "type": "integer",
      "minimum": 0'
edit "$four/openapi.json" '"version": {' '"byte_size": {'
expect_red 'an unbounded integer named like a byte count' \
  "$four" 'numeric.float64-unsafe' 'byte_size'

# (5) The same shape, a different identity name, and the ONLY thing that can
# fire is "unbounded AND named like an identity". A rule that had quietly grown
# a second trigger — one that fired on any unbounded integer — would still pass
# (4) and fail here, because retry_count right below is unbounded too and stays
# green. That is the direction that matters, and it is why there are two.
five="$(fresh_copy identity-name-alone "$CONFORMING")"
edit "$five/openapi.json" '"version": {' '"expires_at": {'
edit "$five/openapi.json" '"maximum": 100
    },' '"minimum": 0
    },'
expect_red 'a JWT exp claim, unbounded, where only the name makes it an identity' \
  "$five" 'numeric.float64-unsafe' 'expires_at'

# --------------------------------------------------------------------------
# THE TWO WARNINGS, each of which must be NAMED and must NOT move the exit code
# --------------------------------------------------------------------------

# (6) A bare `type: number`. The reference says floats cannot be reliably
# round-tripped, and this one is read exactly once in TypeScript as a binary64
# and printed back differently. It is a WARNING because core's own two positions
# are SLO ratios — see DECISIONS.md D43 for why the honest verdict is "warn, and
# say what to do instead" rather than "fail the fleet's ratios".
six="$(fresh_copy a-bare-number "$CONFORMING")"
edit "$six/openapi.json" '"description": "A small non-negative integer with a ceiling well under 2**53. The breakages below rename this field and retype it; the ceiling is what makes it safe here.",
      "type": "integer",
      "minimum": 0,
      "maximum": 100' '"description": "A bare number with nothing else about it.",
      "type": "number",
      "minimum": 0,
      "maximum": 1'
expect_warn 'a bare `type: number`' "$six" 'numeric.float'

# (7) A numeric enum, on the same surface. Codegen closes it into a union in
# every language at once, so adding a value is a breaking change in six of them
# — and the reference calls numeric enums out for exactly that, adding one is
# NOT a compatible change.
seven="$(fresh_copy numeric-enum "$CONFORMING")"
edit "$seven/openapi.json" '"type": "string",
      "enum": ["pending", "settled", "failed"]' '"type": "integer",
      "enum": [200, 503]'
expect_warn 'a numeric enum where a closed set of words belongs' "$seven" 'numeric.enum'

# --------------------------------------------------------------------------
# THE NOT-ENFORCED CASES. Green, named, and in the ledger.
# --------------------------------------------------------------------------

# (8) `numeric.unsigned`. `retry_count` in the fixture IS the surface this rule
# would have fired on — an unbounded non-negative integer whose name says
# nothing about identity — and it is in the CONTROL, so this rule being off is
# what makes the control green. 45 such positions exist across core's schemas
# and the seven service specs, every one a count, an amount in minor units, or a
# status code, so a rule that fired here would fire on nearly half of all numeric
# positions and would be disabled within one release.
expect_not_enforced 'an unbounded unsigned integer whose name says nothing about identity' \
  "$CONFORMING" 'numeric.unsigned'

# (9) The same rule against core's OWN surface, unmodified, and not a fixture.
# `harness/` may not take a dependency or open a connection, so a static walk is
# the only adopter-shaped evidence this script can produce — and it is the claim
# that matters: a check green only on a fixture it was written beside is a check
# that has never seen a real contract. Core's own 31 positions come back green.
expect_not_enforced "core's own schemas, unmodified" "$ROOT/schemas" 'numeric.unsigned'

# --------------------------------------------------------------------------
# AND THE CASE THAT IS NOT ABOUT A FINDING
# --------------------------------------------------------------------------
# A malformed document. The verdict must be: a warning that NAMES the file, and
# an exit code of zero. A checker that reported nothing at all about a surface it
# could not parse would pass this too, and "no numeric problems found" over a
# file it never read is how an unknown becomes a green badge.
expect_green 'a malformed document, reported as unread rather than as clean' \
  "$UNREADABLE" 'unreadable'

# --------------------------------------------------------------------------

printf '\n'
printf 'numeric_self_test — counts, reported separately so a green cannot hide one:\n'
printf '  breakages that went RED and named their finding : %s\n' "$breakages"
printf '  warning cases that stayed GREEN                 : %s\n' "$warn_cases"
printf '  green cases, each of which named what it cannot check : %s\n' "$green_cases"
printf '  not-enforced cases that stayed GREEN and in the ledger : %s\n' "$not_enforced_cases"
printf '  controls (a conforming surface, unbroken)        : 1\n'
printf '  SKIPPED                                           : 0\n'
printf '  (nothing here is conditional on the machine: no case skips, and a case\n'
printf '   that could not run exits non-zero above rather than reporting a skip.)\n'
if [ "$failures" -ne 0 ]; then
  printf 'FAIL: numeric_self_test — %s case(s) the numeric checker did not get right: %s breakage(s), %s warning case(s), %s green case(s), %s not-enforced case(s).\n' \
    "$failures" "$breakages" "$warn_cases" "$green_cases" "$not_enforced_cases"
  exit 1
fi
printf 'PASS: numeric_self_test — %s breakages went red naming their finding, %s warning cases stayed green,\n' \
  "$breakages" "$warn_cases"
printf '      %s green cases and %s not-enforced cases, the control green and warning-free, 0 skipped.\n' \
  "$green_cases" "$not_enforced_cases"
printf '      The six languages are NOT read here — this proves the CONTRACT did not\n'
printf '      invite the bug, and a service'"'"'s own typed client is what proves the reader.\n'
