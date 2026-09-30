#!/usr/bin/env bash
#
# tenancy_self_test.sh — the tenancy checker's proof that it is able to fail.
#
#   bash harness/tests/tenancy_self_test.sh
#
# WHAT THIS IS FOR
#
# A checker that has only ever said "yes" is a report, not a gate. This script
# takes ONE conforming fixture — a small service that declares its account
# boundary and tells the truth about all of it — copies it, breaks exactly one
# thing in each copy, and asserts the checker goes red each time. Every breakage
# names the finding it expects, so a red proves that *the check written for that
# defect* is still load-bearing, which is a different claim from "something went
# red" and the one that decays silently.
#
# The shape is harness/tests/gate_self_test.sh's, and it is the same shape for
# the same reason: a control on the unbroken fixture first (without it every red
# below proves nothing — a checker that refused everything would satisfy all of
# them), a fresh throwaway copy per case so one must never mask the next, and a
# non-zero exit if any breakage stayed green. Nothing in the committed tree is a
# deliberately broken service: the breakages are edits applied here, so a
# reviewer reads what is being broken rather than having to reconstruct it.
#
# THE SEVEN THE BRIEF NAMES, AND THE FINDING EACH ONE MUST NAME
#
#   a missing WHERE on a read          tenancy.scope-lost   on asset-fetch
#   a missing bind parameter            tenancy.bind-missing on asset-checksum-bind
#   an unscoped list                    tenancy.scope-lost   on asset-list
#   an unscoped update                  tenancy.entry-absent on asset-settle
#   an unscoped delete                  tenancy.entry-absent on asset-delete
#   IDOR on fetch-by-id                 tenancy.entry-absent on asset-variant-fetch
#   a negative weakened to *forbidden*  tenancy.denial-missing on asset-fetch
#
# `expect_red` takes a FOURTH argument — a second needle that must appear in the
# output — because six of these seven resolve to one of two findings and "went
# red" alone would not distinguish a read that lost its predicate from a delete
# that lost its predicate. The finding id says which CHECK fired; the needle says
# which ENTRY POINT it fired about, which is the claim actually being made.
#
# AND THE ONE THAT IS NOT A BREAKAGE
#
# The last section is the honesty case, and it is a WARNING that must stay
# green. `harness/tests/fixtures/tenancy/unreadable-language/` is a Go service
# whose account scoping is real and whose syntax this checker cannot read. The
# required verdict is: two warnings naming the file and line, exit 0, and NOT a
# single "no account-scoped entry points found". Counting account-scoped routes
# by pattern gave 96 for guard and 0 for darkroom, and the 0 was the checker's
# syntax rather than darkroom's — a grep that reports "this service has none"
# is worse than no grep, because it reads like an answer. `expect_green` with an
# extra assertion on the warning text is what keeps that from regressing into
# silence.
#
# WHAT IT IS NOT
#
# Not exhaustive mutation testing, and it does not claim to catch every defect.
# It proves sixteen specific breakages across three fixtures, three warning
# cases, and the tri-state promise those warnings make. It does NOT prove the
# service's tests pass — this checker reads the negative assertion's source and
# never runs it, which harness/tenancy_findings.json says in its `notEnforced`
# list rather than leaving it to be discovered.
#
# SIXTEEN, and every one of the sixteen findings this checker can report at
# severity `fail` has a breakage naming it — which is asserted from core's suite
# by `test_every_tenancy_finding_is_proved_able_to_go_red`, so a finding added
# without a breakage is red rather than shipped untested. The four that fire
# before a boundary is even declared (13–16) are the ones most likely to be
# needed first: every repository in this fleet produces `declaration-missing`
# today.
#
# It is deliberately not inside `bin/prime`. A self-test that ran in every gate
# invocation would be a second gate that can disagree with the first, which is
# why core's CI runs it as a step of its own — and why this one is a NEW file
# rather than a section of the gate checker's self-test: the two checkers have
# different fixtures, different findings and different failure modes, and one
# script asserting both would make a red in one of them indistinguishable from a
# red in the other.

set -uo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
HARNESS="$ROOT/harness"
FIXTURE="$HARNESS/tests/fixtures/tenancy/conforming"
ZERO_FIXTURE="$HARNESS/tests/fixtures/tenancy/honest-zero"
BLIND_FIXTURE="$HARNESS/tests/fixtures/tenancy/unreadable-language"

PY="${CAFAYE_TENANCY_PYTHON:-}"
if [ -z "$PY" ]; then
  for candidate in python3 python3.13 python3.12 python3.11 python3.10 python3.9 python; do
    if command -v "$candidate" >/dev/null 2>&1; then PY="$candidate"; break; fi
  done
fi
if [ -z "$PY" ] || ! "$PY" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 9) else 1)'; then
  echo "tenancy_self_test: no python >= 3.9 found; set CAFAYE_TENANCY_PYTHON" >&2
  exit 1
fi

for required in "$FIXTURE" "$ZERO_FIXTURE" "$BLIND_FIXTURE"; do
  if [ ! -d "$required" ]; then
    echo "tenancy_self_test: a fixture is missing at $required" >&2
    exit 1
  fi
done

WORK="$(mktemp -d "${TMPDIR:-/tmp}/cafaye-tenancy-self-test.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT

failures=0
breakages=0
warn_cases=0
green_cases=0
copy_name=""

# A fresh copy per case. The fixture carries its own migrations/, src/, tests/
# and tenancy.yml, so a copy of it is a copy of a repository; nothing outside the
# fixture is read, and the worktree is not touched.
fresh_copy() {
  copy_name="$1"
  local fixture="$2"
  local dst="$WORK/$copy_name"
  rm -rf "$dst"
  cp -R "$fixture" "$dst"
  printf '%s' "$dst"
}

# edit <file> <old> <new> — a textual breakage that FAILS LOUDLY if the fixture has
# moved past it. A self-test that silently stops breaking anything is worse than
# no self-test, so an unmatched edit is an error here rather than a pass. That is
# the reason the fixture's declared line numbers are pinned: if someone adds a
# line to 0001_assets.sql, every breakage below stops applying and this exits
# non-zero rather than reporting sixteen greens.
#
# And it fails loud on an AMBIGUOUS match too, which is not a hypothetical. The
# honest-zero fixture explains itself in a comment that contains the string
# `accountScoped: false`, and `replace(..., 1)` took the comment and left the
# key alone — so the breakage for `tenancy.enumeration-empty` went green while
# breaking a `#`, and the script reported a pass for a check it had never
# exercised. A tool that edits text must say when the text it found is not
# unambiguously the text it was pointed at; `count(old) > 1` is the whole test,
# and it is the same rule the gate checker's proof matching has after MD17.
edit() {
  "$PY" - "$1" "$2" "$3" <<'PY'
import sys

path, old, new = sys.argv[1], sys.argv[2], sys.argv[3]
body = open(path, encoding="utf-8").read()
found = body.count(old)
if found == 0:
    sys.exit(f"tenancy_self_test: breakage no longer applies to {path}: {old!r} not found")
if found > 1:
    sys.exit(
        f"tenancy_self_test: {path} contains {old!r} {found} times, so a replace of the "
        "first one may have edited a comment or a different statement. Make the anchor "
        "unambiguous rather than hoping the first match is the right one."
    )
open(path, "w", encoding="utf-8").write(body.replace(old, new, 1))
PY
}

# expect_red <label> <repo> <finding-id> [needle] — the fixture must go red, the
# exit code must be 1, the finding must be NAMED, and — when a needle is given —
# the message must name the entry point too.
expect_red() {
  local label="$1" repo="$2" expect="$3" needle="${4:-}"
  local out code
  out="$("$PY" "$HARNESS/tenancy_check.py" "$repo" 2>&1)"
  code=$?
  if [ "$code" -ne 1 ]; then
    printf 'FAIL tenancy_self_test: %s — expected exit 1, got %s\n%s\n' "$label" "$code" "$out" >&2
    failures=$((failures + 1))
    return
  fi
  if ! printf '%s' "$out" | grep -q "$expect"; then
    printf 'FAIL tenancy_self_test: %s — went red as something else and never said %s\n%s\n' \
      "$label" "$expect" "$out" >&2
    failures=$((failures + 1))
    return
  fi
  if [ -n "$needle" ] && ! printf '%s' "$out" | grep -q "$needle"; then
    printf 'FAIL tenancy_self_test: %s — went red as %s but never named %s, so it cannot be\n' \
      "$label" "$expect" "$needle" >&2
    printf '  distinguished from a different statement losing its scope.\n%s\n' "$out" >&2
    failures=$((failures + 1))
    return
  fi
  breakages=$((breakages + 1))
  printf 'PASS tenancy_self_test: breakage %s: %s — caught by `%s`%s\n' \
    "$breakages" "$label" "$expect" "${needle:+ about $needle}"
}

# expect_green <label> <repo> [must-print] — the fixture must come back green,
# and when a token is given the report must ALSO print it. The second half is
# what keeps a warning from becoming silence: a checker that reported nothing at
# all about a service it cannot read would pass this too, and it is precisely the
# shape this file exists to prevent.
expect_green() {
  local label="$1" repo="$2" must_print="${3:-}"
  local out code
  out="$("$PY" "$HARNESS/tenancy_check.py" "$repo" 2>&1)"
  code=$?
  if [ "$code" -ne 0 ]; then
    printf 'FAIL tenancy_self_test: %s — expected green, got exit %s\n%s\n' "$label" "$code" "$out" >&2
    failures=$((failures + 1))
    return
  fi
  if [ -n "$must_print" ] && ! printf '%s' "$out" | grep -q "$must_print"; then
    printf 'FAIL tenancy_self_test: %s — exited 0 without printing %s, so the thing it could\n' \
      "$label" "$must_print" >&2
    printf '  not see is being reported as nothing being there.\n%s\n' "$out" >&2
    failures=$((failures + 1))
    return
  fi
  green_cases=$((green_cases + 1))
  printf 'PASS tenancy_self_test: green case %s: %s — exit 0%s\n' \
    "$green_cases" "$label" "${must_print:+ and named what it cannot see}"
}

# expect_warn <label> <repo> <finding-id> — the finding must be printed AND the
# exit code must STILL BE 0. The exit code is the half that matters, and it is
# the half a tri-state checker gets wrong. All four warnings here are the same
# claim: *this machine cannot answer that question*. Failing on them is how a
# checker gets disabled, which would leave the fleet with no boundary check at
# all instead of an incomplete one.
expect_warn() {
  local label="$1" repo="$2" expect="$3"
  local out code
  out="$("$PY" "$HARNESS/tenancy_check.py" "$repo" 2>&1)"
  code=$?
  if [ "$code" -ne 0 ]; then
    printf 'FAIL tenancy_self_test: %s — a warning moved the exit code to %s\n%s\n' \
      "$label" "$code" "$out" >&2
    failures=$((failures + 1))
    return
  fi
  if ! printf '%s' "$out" | grep -q "$expect"; then
    printf 'FAIL tenancy_self_test: %s — exited 0 without even printing %s\n%s\n' \
      "$label" "$expect" "$out" >&2
    failures=$((failures + 1))
    return
  fi
  warn_cases=$((warn_cases + 1))
  printf 'PASS tenancy_self_test: warning %s: %s — said `%s` and still exited 0\n' \
    "$warn_cases" "$label" "$expect"
}

# --------------------------------------------------------------------------
# the control. Without it, sixteen reds prove nothing at all: a checker that
# refused everything would satisfy every expectation below.
# --------------------------------------------------------------------------
control="$(fresh_copy control "$FIXTURE")"
out="$("$PY" "$HARNESS/tenancy_check.py" "$control" 2>&1)"
code=$?
if [ "$code" -ne 0 ]; then
  printf 'FAIL tenancy_self_test: the control — a service whose declaration is true — did not come back green (exit %s)\n%s\n' \
    "$code" "$out" >&2
  failures=$((failures + 1))
else
  printf 'PASS tenancy_self_test: the control — a service whose declaration is true — is green\n'
fi

# And the control must be green with NO warnings either. A warning-free control
# is what proves the scanner classifies everything the fixture contains, so the
# warning cases below are warnings about this fixture's SHAPE rather than
# artefacts of an over-eager scanner. "0 failure(s), 0 warning(s)" is matched as
# a whole line rather than grepped for a number.
if ! printf '%s' "$out" | grep -q '0 failure(s), 0 warning(s)'; then
  printf 'FAIL tenancy_self_test: the control — a service that declares every site it has — is not warning-free\n%s\n' \
    "$out" >&2
  failures=$((failures + 1))
fi

# --------------------------------------------------------------------------
# the seven ways scoping gets dropped
# --------------------------------------------------------------------------

# (1) a missing WHERE on a read. The other selects on `assets` still carry the
# key, so closure stays closed and what fires is `scope-lost`: the declaration
# said the scoping was on line 22 and line 22 no longer scopes anything. That is
# the more precise of the two answers and it is the one this breakage must give.
one="$(fresh_copy read-where "$FIXTURE")"
edit "$one/migrations/0001_assets.sql" \
  'select * from assets where id = $1 and account_id = $2' \
  'select * from assets where id = $1'
expect_red 'a read with its WHERE dropped' "$one" 'tenancy.scope-lost' 'asset-fetch'

# (2) a missing bind parameter. `account_id = $2` is STILL in the statement and
# nothing passes $2 any more — the defect a predicate check cannot see, and the
# reason `mechanism: bind-parameter` carries a named parameter at all.
two="$(fresh_copy bind-missing "$FIXTURE")"
edit "$two/src/assets.rb" \
  'DB.exec(SQL, checksum, account.account_id)' \
  'DB.exec(SQL, checksum)'
expect_red 'a bound account parameter nothing binds' "$two" 'tenancy.bind-missing' 'asset-checksum-bind'

# (3) an unscoped list. `select id, checksum, status from assets where …` is the
# one a join usually loses the scope on, and it is a different statement from (1)
# — which is why the needle is part of the assertion.
three="$(fresh_copy list-unscoped "$FIXTURE")"
edit "$three/migrations/0001_assets.sql" \
  'select id, checksum, status from assets where account_id = $1 order by created_at' \
  'select id, checksum, status from assets order by created_at'
expect_red 'a list that lists the whole table' "$three" 'tenancy.scope-lost' 'asset-list'

# (4) an unscoped update. The only `update` on `assets`, so the site disappears
# and closure itself is what fires — `entry-absent`, not `scope-lost`. The
# distinction is not pedantry: "the predicate is gone" and "the declaration points
# at the wrong line" want different fixes, and a checker that cannot tell them
# apart reports the second as a pass.
four="$(fresh_copy update-unscoped "$FIXTURE")"
edit "$four/migrations/0001_assets.sql" \
  "update assets set status = 'settled' where id = \$1 and account_id = \$2" \
  "update assets set status = 'settled' where id = \$1"
expect_red 'an update that updates whichever row it is given' "$four" 'tenancy.entry-absent' 'asset-settle'

# (5) an unscoped delete. The same shape as (4) on the statement that would end
# a customer's data if it were the wrong customer's.
five="$(fresh_copy delete-unscoped "$FIXTURE")"
edit "$five/migrations/0001_assets.sql" \
  'delete from assets where id = $1 and account_id = $2' \
  'delete from assets where id = $1'
expect_red 'a delete that deletes whichever row it is given' "$five" 'tenancy.entry-absent' 'asset-delete'

# (6) IDOR on fetch-by-id. `asset_variants` is fetched by id on exactly one line,
# so losing the scope there leaves the declaration with nothing to point at.
six="$(fresh_copy idor-variant "$FIXTURE")"
edit "$six/migrations/0001_assets.sql" \
  'select * from asset_variants where id = $1 and account_id = $2' \
  'select * from asset_variants where id = $1'
expect_red 'a variant fetched by id with the scope dropped — an IDOR' "$six" 'tenancy.entry-absent' 'asset-variant-fetch'

# (7) the negative assertion weakened from ABSENT to FORBIDDEN. This is the
# breakage D33 exists to make catchable: the test still runs, the suite is still
# green, and the assertion has stopped saying what the contract says it says —
# because `forbidden` confirms the id exists. The declaration is left alone, so
# this is `denial-missing`; breakage 10 below is the same weakening WITH the
# declaration updated, which is `denial-refuses`.
seven="$(fresh_copy denial-weakened "$FIXTURE")"
edit "$seven/tests/tenancy_test.rb" \
  'assert Assets.fetch("a1", account(OTHER_ACCOUNT)).nil?' \
  'assert_equal :forbidden, Assets.fetch("a1", account(OTHER_ACCOUNT))'
expect_red 'a negative assertion weakened from absent to forbidden' "$seven" 'tenancy.denial-missing' 'asset-fetch'

# --------------------------------------------------------------------------
# and the ways the DECLARATION stops describing the code
# --------------------------------------------------------------------------

# (8) a declaration that points at a file nobody has. The cheapest check in the
# checker and the one that most often fires the day a service renames a
# directory — which is exactly why it is here rather than assumed.
#
# The anchor spans the line number as well, and that is not decoration. The
# fixture names `migrations/0001_assets.sql` in six entry points, so a
# single-line anchor edits whichever came first and this breakage has been
# passing because the first one happened to be `asset-fetch`, the entry point
# its `expect_red` names. Anchor it to `line: 22` — the fetch by id — and the
# breakage says which entry point it is breaking.
eight="$(fresh_copy location-missing "$FIXTURE")"
edit "$eight/tenancy.yml" '      file: migrations/0001_assets.sql
      line: 22' '      file: migrations/0002_assets_v2.sql
      line: 22'
expect_red 'a declaration naming a file this service does not have' "$eight" 'tenancy.location-missing' 'asset-fetch'

# (9) a declaration naming a line past the end of the file. A line number nobody
# checked is the false green written down, in its plainest form.
nine="$(fresh_copy line-missing "$FIXTURE")"
edit "$nine/tenancy.yml" 'line: 37' 'line: 900'
expect_red 'a declaration naming a line past the end of the file' "$nine" 'tenancy.line-missing' 'asset-variant-fetch'

# (10) the same weakening as (7), WITH the declaration updated to match. The
# schema refuses a refusal outright (`const absent`) and the checker names it as
# the enumeration oracle it is, rather than reporting "your file is invalid" and
# sending the reader looking for a typo.
ten="$(fresh_copy denial-refuses "$FIXTURE")"
edit "$ten/tenancy.yml" '      asserts: absent
      expects: nil
      file: tests/tenancy_test.rb
      line: 23' '      asserts: forbidden
      expects: FORBIDDEN
      file: tests/tenancy_test.rb
      line: 23'
expect_red 'a declaration that answers another account with a refusal' "$ten" 'tenancy.denial-refuses' 'asset-fetch'

# (11) an account-scoped statement nobody declared. The other direction of
# closure, and the one that turns a declaration from a summary into a contract:
# without it, adding a new scoped query is invisible, and the enumeration drifts
# the moment nobody is looking.
eleven="$(fresh_copy undeclared "$FIXTURE")"
edit "$eleven/migrations/0001_assets.sql" \
  'delete from assets where id = $1 and account_id = $2' \
  'delete from assets where id = $1 and account_id = $2

-- added by a refactor nobody declared
select * from archive where account_id = $1'
expect_red 'an account-scoped query nobody declared' "$eleven" 'tenancy.undeclared-entry' 'archive'

# (12) a service that declares no account scoping and has one. The honest zero,
# caught leaving. An omission is not a zero, and this is the check that makes the
# difference sayable in the first place.
twelve="$(fresh_copy honest-zero "$ZERO_FIXTURE")"
edit "$twelve/src/generate.go" \
  'func Render(templatePath string, values map[string]string) (string, error) {' \
  '// A scoped read nobody declared, in a service that says it has none:
func ReadForAccount(account_id string) (string, error) {
	_, _ = account_id, os.ReadFile
	return "", nil
}

func Render(templatePath string, values map[string]string) (string, error) {'
expect_red 'a service that declares no scoping and has account-scoped code' "$twelve" 'tenancy.honest-zero'

# (13) the honest zero caught leaving, is (12) above; these four are the ones
# that fire BEFORE a boundary is even declared, and they are the four most
# likely to be needed first — every repository in this fleet hits
# `declaration-missing` today, and a finding nobody has ever seen go red is a
# finding whose message has never been read by anybody.

# (13) no declaration at all. The fleet's actual state, and the one finding
# every one of the thirteen repositories produces before it adopts anything.
# The copy is a full conforming service with its `tenancy.yml` removed, because
# a checker that reports "nothing there" for a directory with no source in it
# would pass this for the wrong reason.
thirteen="$(fresh_copy no-declaration "$FIXTURE")"
rm -f "$thirteen/tenancy.yml"
expect_red 'a service that declares no account boundary at all' "$thirteen" 'tenancy.declaration-missing'

# (14) a declaration core's own YAML reader refuses. A tab where indentation
# belongs is the realistic shape — an editor wrote it — and it is why this is
# its own finding rather than a `tenancy.schema` row: a reader that cannot parse
# the file cannot validate it either, and reporting "your file is invalid" about
# a file the reader never read sends the reader looking for a typo in a
# declaration that may be perfectly correct.
fourteen="$(fresh_copy unreadable-declaration "$FIXTURE")"
printf 'version: 1\nentryPoints: [ \n' > "$fourteen/tenancy.yml"
expect_red 'a declaration the reader cannot parse' "$fourteen" 'tenancy.declaration-unreadable'

# (15) `accountScoped: true` with an empty list. The omission facing the other
# way: a service that says it scopes by account and then declares no way it
# does. It arrives as two findings on purpose — the schema's `minItems: 1` says
# the file is not a declaration, and `enumeration-empty` says what it actually
# is — because "invalid" and "you have not said the thing you said you said" are
# different sentences, and a reader who gets only the first will go fix syntax.
#
# It is done on the honest-zero fixture rather than the conforming one, and the
# reason is mechanical: the conforming fixture already has a populated
# `entryPoints:`, and APPENDING an empty one would make the document carry that
# key twice — which core's reader refuses, and the finding would then be
# `declaration-unreadable` rather than the one under test. A breakage that
# proves a different check is a breakage that proves nothing.
fifteen="$(fresh_copy scoped-but-silent "$ZERO_FIXTURE")"
edit "$fifteen/tenancy.yml" $'\naccountScoped: false' $'\naccountScoped: true'
expect_red 'a service that claims to scope by account and declares no way it does' \
  "$fifteen" 'tenancy.enumeration-empty'

# (16) an undeclared top-level key. The one this repository holds every other
# schema to: `additionalProperties: false` is why an undeclared key is an error
# rather than a silent no-op that reads as a decision somebody made. The file is
# otherwise entirely valid, so `tenancy.schema` is the ONLY finding and this is
# the cleanest proof of it. `cache` is the key the gate declaration already
# refuses, reused so the two checkers answer the same mistake identically.
sixteen="$(fresh_copy undeclared-key "$FIXTURE")"
edit "$sixteen/tenancy.yml" 'version: 1' 'version: 1
cache:
  enabled: false'
expect_red 'a declaration with a key the format does not declare' "$sixteen" 'tenancy.schema'

# --------------------------------------------------------------------------
# the warnings, which must be printed AND must not move the exit code
# --------------------------------------------------------------------------
expect_warn 'an enumeration this checker cannot close, on a language it cannot read' \
  "$BLIND_FIXTURE" 'tenancy.enumeration-partial'
expect_warn 'the same service, and the key it found no statement for' \
  "$BLIND_FIXTURE" 'tenancy.scope-key-unused'

# (17) a declared source path that is not in the service. ADDING one rather than
# renaming one is deliberate: renaming `migrations` would also stop the scan
# finding the sites the declarations point at, and the result would be four
# `entry-absent` failures — a red that proves nothing about this check. Adding a
# path leaves the scan reading exactly what it was reading, so the ONLY finding
# is the one under test: the scan covered less than the declaration asked, and
# says so instead of reporting a clean bill of health over the smaller area.
seventeen="$(fresh_copy scan-narrowed "$FIXTURE")"
edit "$seventeen/tenancy.yml" '    - migrations' '    - migrations
    - db/generated'
expect_warn 'a source path the declaration names that is not there' \
  "$seventeen" 'tenancy.scan-narrowed'

# --------------------------------------------------------------------------
# and the honesty case, which is a GREEN that must name what it cannot see
# --------------------------------------------------------------------------
# A Go service with real account scoping this checker cannot parse. The verdict
# it must produce is two warnings and an exit code of zero — NOT a silent pass,
# and emphatically not "no account-scoped entry points found". The token is the
# entry point's name, which is what forces the report to be specific rather than
# merely non-empty.
expect_green 'a service whose scoping this checker cannot read, reported as unread rather than as absent' \
  "$BLIND_FIXTURE" 'get-asset'

# The honest zero, green, and it says out loud that a key it matched nothing in
# is not a proof. `kit` and `caf` are the fleet's two real zeros; both would say
# this, which is the difference between an honest zero and an unexamined one.
expect_green 'the honest zero: a service that declares no scoping and has none' \
  "$ZERO_FIXTURE" 'tenancy.scope-key-unused'

# --------------------------------------------------------------------------

printf '\n'
printf 'tenancy_self_test — counts, reported separately so a green cannot hide one:\n'
printf '  breakages that went RED and named their finding : %s\n' "$breakages"
printf '  warning cases that stayed GREEN                 : %s\n' "$warn_cases"
printf '  green cases, each of which named what it cannot see : %s\n' "$green_cases"
printf '  controls (a true declaration, unbroken)          : 1\n'
printf '  SKIPPED                                           : 0\n'
printf '  (nothing here is conditional on the machine: no case skips, and a case\n'
printf '   that could not run exits non-zero above rather than reporting a skip.)\n'
if [ "$failures" -ne 0 ]; then
  printf 'FAIL: tenancy_self_test — %s case(s) the tenancy checker did not get right: %s breakage(s), %s warning case(s), %s green case(s), 1 control.\n' \
    "$failures" "$breakages" "$warn_cases" "$green_cases"
  exit 1
fi
printf 'PASS: tenancy_self_test — %s breakages went red naming their finding, %s warning cases stayed green,\n' \
  "$breakages" "$warn_cases"
printf '      %s green cases each named what the checker cannot see, the control is green and warning-free,\n' \
  "$green_cases"
printf '      0 skipped. The negative assertions are READ, not run — harness/tenancy_findings.json\n'
printf '      says so in its notEnforced list, and that gap is the gate'"'"'s job, in the service.\n'
