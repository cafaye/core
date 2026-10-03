# MEASUREMENT — fleet-test-truncate-audit-01, part 1

Raw numbers taken while answering "does darkroom's defect exist anywhere else?".
Kept as a separate file from `REPORT-fleet-test-truncate-audit-01.md` because these
are the measurements and that file is what they are for.

## The packet's survey is wrong, and the way it is wrong matters

The packet supplied this table as "a survey of the tree — treat this as a starting
point, not as the answer":

```
billing   2 test files mention truncate     (Ruby, ExUnit)
courier   4 test files mention truncate     (Elixir, ExUnit)
muse      5 test files mention truncate     (Go)
pantry    1 test file  mentions truncate    (Python, pytest)
identity  0                               (Go)
guard     0
```

It invited me to confirm it, and it does not survive confirmation. **The count it
reports is `grep -rlni truncate` over the test trees, and that grep matches prose
as readily as SQL.** Measured, per service, restricted to test files:

| service | packet says | `grep -rlni truncate` (what the packet ran) | files containing a **SQL `TRUNCATE`** |
|---|---|---|---|
| billing | 2 (Ruby, ExUnit) | 2 | **0** |
| courier | 4 (Elixir, ExUnit) | 4 | **0** |
| muse | 5 (**Go**) | 5 | **0** |
| pantry | 1 (**Python**, pytest) | 1 | **0** |
| identity | 0 | 9 | **0** |
| guard | 0 | 1 | **0** |
| darkroom | (fixed) | — | **0** |

Two separate errors, and they pull in opposite directions, which is why neither
is visible from the packet's table alone.

**Every one of the fleet's `truncate` hits is a truncated STRING, not a truncated
TABLE.** The hits are `String#truncate` in billing's `app/models/processor_webhook.rb`,
`DateTime.truncate(:second, …)` in courier's `lib/courier/events.ex`, and comments
in test files that happen to contain the word — for example
`muse/tests/test_telemetry.py:249`, `test_a_long_value_is_truncated_to_the_attribute_ceiling`,
and `courier/test/courier/telemetry_canary_test.exs:245`, *"that 'ignore' must not
mean 'truncate and keep the usable part'"*. Both are prose about the word and about
log truncation. Not one is `TRUNCATE TABLE`.

**The languages are wrong too, in both directions.** The packet says muse is Go
and pantry is Python. Measured from each repository's own manifest:
`muse/pyproject.toml` is a `[project]` with `requires-python = ">=3.14"` and a
`pytest>=9.1.1` dev dependency, and its tests are `muse/tests/*.py`.
`pantry/Cargo.toml` is a Rust crate and its tests are `pantry/tests/*.rs`. So the
packet's Go/pytest concurrency rules — `t.Parallel()`, `pytest-xdist` — apply to
the wrong two repositories, and neither of those services has a database at all
(§2).

**identity's row is the one worth pausing on: the packet says 0, and the same
grep that over-reported every other service reports 9 here.** Every one is a
comment. `internal/platform/dbtest/dbtest.go:12` reads *"there is deliberately no
TRUNCATE helper called from ordinary tests: a global truncate from
internal/users would delete internal/sessions' fixtures mid-run, and the failure
looks like a non-deterministic bug in the code under test rather than in the
harness."* That sentence is this packet's own argument, written down in the right
place by somebody who had already reasoned it out — and the packet's grep, run
over the same tree, scored the file that contains it as a hit.

## Method for "SQL TRUNCATE", so the zero above is checkable

`grep -rlniE '\bTRUNCATE\b'` over test files, then read every hit. The word has
to appear as a SQL verb to count; `TRUNCATE` in a comment, in a `String#truncate`
call, or in a test *name* does not. Across all thirteen repositories — including
`core` and `kit`, which own the cross-service checks and the gate respectively —
the count is **0**.

The identity case is the one that would have been a false positive, and it is
worth being precise about why: `dbtest.Reset` at `dbtest.go:119-128` *does*
contain a real 16-table `TRUNCATE … CASCADE`. **It has no callers.** Measured:

```
$ grep -rn 'dbtest\.Reset' identity --include='*.go' | grep -v dbtest.go
(no output)
```

A hazard available but uninvoked is not a defect; it is the hazard sitting behind
a door, and the file that holds it says so in the first paragraph of its own
package comment. The guard added by this packet (§4) is what keeps the door shut.

## What this does not license

A `TRUNCATE` grep is not the question. The question is whether two tests in one
suite can delete each other's fixtures, and a suite can do that with `DELETE
FROM`, `delete_all`, `Repo.delete_all`, `destroy_all` or a fixture rollback that
was turned off. `courier` is the proof that the grep is not the question:
**zero** `TRUNCATE` in the repository, and it is nevertheless the service with the
most aggressive database testing in the fleet — 20 `async: true` modules, several
of them `Courier.DataCase`, which means Ecto SQL Sandbox in shared mode.
Measured verdicts per service are in `REPORT-fleet-test-truncate-audit-01.md`.