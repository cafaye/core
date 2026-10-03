#!/usr/bin/env bash
#
# db_isolation_self_test.sh — the guard's proof that it is able to fail.
#
#   bash harness/tests/db_isolation_self_test.sh
#
# WHAT THIS IS FOR
#
# A guard that has only ever said "clean" is not a guard; it is a comment with a
# shebang. This script is the counterweight, and it matters more here than for
# core's other self-tests because this checker's whole output on the fleet as it
# stands is `0 failure(s)` — seven services with database tests, none of them
# wrong, and nothing in that line distinguishable from a checker that cannot
# fail.
#
# So: take fixtures with a KNOWN shape, copy each, break exactly one thing in
# each copy, and assert the checker goes red each time. Every breakage names the
# finding it expects, so a red proves *the check written for that defect* is
# load-bearing, which is a different claim from "something went red" and the one
# that decays silently.
#
# The shape is harness/tests/tenancy_self_test.sh's, for the same reasons: a
# control on the unbroken fixture FIRST (without it every red below proves
# nothing, because a checker that refused everything would satisfy all of them),
# a fresh throwaway copy per case so one can never mask the next, and a non-zero
# exit if any breakage stayed green. Nothing committed is a deliberately broken
# service; the breakages are edits applied here.
#
# ------------------------------------------------------------------------------
# THREE FIXTURES, AND WHY ONE WAS NOT ENOUGH
#
# The first version of this had ONE fixture — the safe one — and planted each
# hazard by adding a cleanup to it. All four reds came back CLEAN, and the
# checker was RIGHT: the safe fixture stamps a per-test `search_path` onto every
# connection, so a truncate written next to it resolves inside that schema and is
# genuinely bounded.
#
# That is the most useful thing this self-test found about itself, so it is the
# first thing stated here: **a hazard is a property of a suite's shape, not of
# one line added to it.** Planting into a safe suite tests nothing.
#
#   isolated_service  (rust)  the CONTROL. Per-test schema, safe, must stay clean.
#   shared_service    (rust)  one shared set of tables, no search_path, no
#                             sandbox. cargo's parallelism is the DEFAULT, so
#                             this shape plus any blanket cleanup is the full
#                             hazard — cases 1, 2 and 4.
#   serial_service    (go)    shared database, but NO `t.Parallel()`, so
#                             sequential. This is `db-isolation.latent`, and it
#                             needs a language whose concurrency is opt-in: a
#                             Rust base would be concurrent by construction and
#                             could never express "two of three".
#
# ------------------------------------------------------------------------------
# THE CASES, AND WHY EACH IS A REAL DEFECT RATHER THAN A REGEX EXERCISE
#
#   control            NOT red   the safe fixture, unbroken
#   1. shared truncate  hazard    darkroom's pre-fix shape, and this packet
#                                 MEASURED it in the real repository rather than
#                                 only here: `cargo test -- --ignored` exited
#                                 101 on three consecutive runs with 14, 17 and
#                                 16 distinct failures, a DIFFERENT SET EACH
#                                 RUN, and one assertion read `left: 5,
#                                 right: 1` — a test counting five assets of
#                                 which it created one. Reverting the plant
#                                 returned the suite to exit 0.
#   2. table-wide DELETE hazard    the spelling most of this fleet uses and the
#                                 one `grep -i truncate` will never see.
#   3. no opt-in       latent      two of three conditions. No service in the
#                                 fleet is in this state, which is exactly why
#                                 it needs its own case.
#   4. WHERE-narrowed   NOT red    identity's entire suite is written this way
#                                 and was measured green three times out of
#                                 three. A checker that flagged it would send a
#                                 reader to fix a working repository.
#   5. prose            NOT red    the packet's own false positive, in shape:
#                                 `grep -rlni truncate` over this fleet's test
#                                 trees hits nine repositories and every hit
#                                 outside darkroom is a truncated STRING or a
#                                 sentence. A guard that reported those would be
#                                 switched off, and being switched off is how
#                                 case 1 gets through next time.
#   6. per-test schema  NOT red    the control again, seen from the other side:
#                                 the SAME truncate that is a hazard in case 1
#                                 is safe here, and that difference is the whole
#                                 reason the checker reads a suite rather than
#                                 grepping for a word.
# ------------------------------------------------------------------------------

set -uo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# NOT the nested one-liner core="$(dirname "$(dirname "$here")")". That form is a
# parse error on the bash this fleet's macOS runners ship -- 3.2.57 -- and it
# names the wrong line entirely:
#
#     line 71: unexpected EOF while looking for matching `)'
#
# which reads like an unbalanced paren somewhere BELOW rather than like the two
# lines above it. Measured by bisection: `bash -n` on lines 1-70 exits 0 and on
# lines 1-71 exits 2, so the nesting is the whole of it. Two steps instead of
# one nests nothing, and this file is run by /bin/sh on a developer machine.
harness_dir="$(dirname "$here")"
core="$(dirname "$harness_dir")"
checker="$core/harness/db_isolation_check.py"
fixtures="$here/fixtures"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

python="$(command -v python3 || true)"
if [ -z "$python" ]; then
  echo "db_isolation_self_test.sh: python3 not found on PATH — cannot run the checker" >&2
  exit 2
fi

pass=0
fail=0

note() { printf '\n--- %s\n' "$1"; }

# expect_red <label> <expected-finding>
expect_red() {
  local label="$1" expect="$2" output status
  output="$("$python" "$checker" "$work/$label" 2>&1)"
  status=$?
  if [ "$status" -eq 0 ]; then
    printf '  RED EXPECTED, GOT CLEAN  %s\n' "$label"
    printf '%s\n' "$output" | sed 's/^/    /'
    fail=$((fail + 1))
    return
  fi
  if ! printf '%s' "$output" | grep -q "$expect"; then
    printf '  WRONG FINDING            %s (wanted %s)\n' "$label" "$expect"
    printf '%s\n' "$output" | sed 's/^/    /'
    fail=$((fail + 1))
    return
  fi
  printf '  red, and named           %s -> %s\n' "$label" "$expect"
  pass=$((pass + 1))
}

# expect_clean <label>
expect_clean() {
  local label="$1" output status
  output="$("$python" "$checker" "$work/$label" 2>&1)"
  status=$?
  if [ "$status" -ne 0 ]; then
    printf '  CLEAN EXPECTED, GOT RED  %s\n' "$label"
    printf '%s\n' "$output" | sed 's/^/    /'
    fail=$((fail + 1))
    return
  fi
  printf '  clean                    %s\n' "$label"
  pass=$((pass + 1))
}

# fresh <base> <label> — a throwaway copy, so one case can never mask the next.
fresh() {
  rm -rf "$work/$2"
  cp -R "$fixtures/$1" "$work/$2"
}

for required in isolated_service shared_service serial_service double_service; do
  if [ ! -d "$fixtures/$required" ]; then
    echo "db_isolation_self_test.sh: the fixture $fixtures/$required is missing." >&2
    echo "  Without a known shape to break, every red below proves nothing: a" >&2
    echo "  checker that refused everything would satisfy all of them." >&2
    exit 2
  fi
done

note "control: the safe fixture, unbroken, which must be CLEAN"
fresh isolated_service control
expect_clean control

note "case 1: darkroom's pre-fix shape — a shared database and a blanket truncate"
fresh shared_service shared_truncate
cat > "$work/shared_truncate/tests/cleanup.rs" <<'RS'
#[tokio::test]
async fn a_test_that_cleans_up_after_itself() {
    let pool = common::shared_pool().await;
    sqlx::query("truncate assets, asset_variants cascade")
        .execute(&pool)
        .await
        .unwrap();
}
RS
expect_red shared_truncate "db-isolation.hazard"

note "case 2: a table-wide DELETE, which no grep for truncate will ever see"
fresh shared_service table_wide_delete
cat > "$work/table_wide_delete/tests/cleanup.rs" <<'RS'
#[tokio::test]
async fn every_test_deletes_the_same_table() {
    let pool = common::shared_pool().await;
    sqlx::query("DELETE FROM users")
        .execute(&pool)
        .await
        .unwrap();
}
RS
expect_red table_wide_delete "db-isolation.hazard"

note "case 3: two of three — shared database, blanket cleanup, no opt-in (LATENT)"
fresh serial_service latent_two_of_three
cat > "$work/latent_two_of_three/tests/cleanup_test.go" <<'GO'
package tests

import (
	"context"
	"os"
	"testing"
)

// No t.Parallel() anywhere: go test runs a package's tests in sequence unless
// one asks otherwise, so this suite is NOT the hazard yet.
func TestACleanupThatWouldDeleteAnotherTestsRows(t *testing.T) {
	dsn := os.Getenv("TEST_DATABASE_URL")
	if dsn == "" {
		t.Skip("TEST_DATABASE_URL is not set")
	}
	ctx := context.Background()
	pool := Pool(ctx)
	if _, err := pool.Exec(ctx, "TRUNCATE TABLE users CASCADE"); err != nil {
		t.Fatalf("truncating: %v", err)
	}
}
GO
expect_red latent_two_of_three "db-isolation.latent"

note "case 4 (negative control): a WHERE-narrowed delete must stay CLEAN"
fresh shared_service narrowed_delete
cat > "$work/narrowed_delete/tests/cleanup.rs" <<'RS'
#[tokio::test]
async fn cleanup_keys_on_this_tests_own_row() {
    let pool = common::shared_pool().await;
    sqlx::query("delete from users where id = $1")
        .bind(self_id())
        .execute(&pool)
        .await
        .unwrap();
}
RS
expect_clean narrowed_delete

note "case 5 (negative control): prose about truncate must stay CLEAN"
fresh shared_service prose_only
cat > "$work/prose_only/tests/prose.rs" <<'RS'
// A long value is truncated to the attribute ceiling: a truncated leak is still a
// leak, and truncation must never be mistaken for "keep the usable part".
#[tokio::test]
async fn a_truncated_string_is_still_reported() {
    assert_eq!(clip("x".repeat(9000)), 4096);
}
RS
expect_clean prose_only

note "case 6 (negative control): the SAME truncate is safe behind a per-test schema"
fresh isolated_service schema_scoped_truncate
cat > "$work/schema_scoped_truncate/tests/cleanup.rs" <<'RS'
#[tokio::test]
async fn the_same_truncate_as_case_1() {
    let pool = common::test_pool().await;
    sqlx::query("truncate assets, asset_variants cascade")
        .execute(&pool)
        .await
        .unwrap();
}
RS
expect_clean schema_scoped_truncate

note "case 7 (negative control): a test DOUBLE cannot share a database"
fresh double_service double_database
expect_clean double_database

printf '\n%s passed, %s failed\n' "$pass" "$fail"
[ "$fail" -eq 0 ]