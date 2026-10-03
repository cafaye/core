# HANDOFF — core-numeric-01

**State:** five commits on `worker/core-numeric-01`, base `d49e14c`, worktree
green at **259/259**, `bin/prime` exits 0, its own red proof still passes at 18.
Nothing pushed; nothing outside this worktree touched.

## The successor's FIRST MOVE, in one command

```console
$ cd /Users/kaka/Code/any/moon/cafaye/wt-m39-core-numeric-01
$ CAFAYE_NUMERIC_PYTHON=tests/.venv/bin/python ./harness/bin/numeric-check ../*/openapi/v1.yaml
```

That prints **6 failures** and exits **1**, all `numeric.float64-unsafe`, all
unbounded integers on identity-named fields. **Those 6 are the packet's real
output** and they are unfixed on purpose, because each is a change to a *service's*
contract rather than to core's checker. The list is in
[`REPORT-core-numeric-01.md`](REPORT-core-numeric-01.md) §5.

If you take exactly one thing from this packet, take that number: **6 real
cross-language defects in the fleet's own OpenAPI documents, found by reading
files, with no service and no database.**

## What exists now, and is load-bearing

| file | what it is |
| --- | --- |
| `harness/numeric_check.py` | the checker. `--survey`, `--explain`, `--json`, or paths |
| `harness/bin/numeric-check` | the wrapper. Exit 2 when the check cannot happen, never `|| true` |
| `harness/tests/numeric_self_test.sh` | 9 cases, 4 breakages RED. CI step of its own, floor 4 |
| `harness/tests/fixtures/numeric/` | one conforming fixture; every breakage edits exactly one field |
| `docs/numeric-conventions.md` | the rules, the identity names, the scaled-integer convention |
| `bin/prime` | runs the check on `schemas/`, on a **pinned** interpreter |
| `gate.yml` | floor **259**, measured — 254 → 259 |
| D43 | the severities, the alternatives that lost, the cost of flipping |

## The three things you are most likely to get wrong

1. **Do not weaken a severity to make something green.** The whole packet rests on
   one measured fact: `numeric.float64-unsafe` fires on **zero** of core's 31
   positions, which is the only reason it can be a failure. If it ever fires on a
   core schema,
   `test_the_numeric_checker_goes_red_only_on_the_float64_range_and_only_where_the_ceiling_is_reachable`
   fails **on purpose**. That red is a finding about a schema, not a broken test.
   Read the field, then fix the field.

2. **`harness/` may not take a dependency.** The first version of this checker
   imported PyYAML and the stdlib test was red on the commit that added it. YAML
   comes from `cafaye_contract.read_yaml` — the reader `tenancy_check.py` already
   uses. If you add an import, `test_bin_prime_checks_the_numeric_surface_and_the_check_needs_nothing_core_does_not_ship`
   and `test_the_harness_imports_nothing_outside_the_standard_library` will both
   catch it.

3. **Adding a test means raising the floor.** `gate.proof[].minimum` in `gate.yml`
   is the ratchet; a new test in `tests/test_specs.py` fails
   `test_the_gate_floor_is_not_below_the_suite_core_claims_to_have` until it is
   raised **in the same commit**. 259 is measured, not summed.

## What is owed, and by whom

- **The 6 service findings.** One line per service: a string, or a `maximum` under
  9007199254740991. Not core's to change.
- **`slo.objective` → `objective_milli`.** The convention is written down in
  `docs/numeric-conventions.md`; the rewrite of `slo.schema.json` and
  `slo-windows.schema.json` is **not done**, deliberately, because both are
  published under `version: 1` with the fleet's adopters reading them. D43 says
  so and says what promoting `numeric.float` to a failure would cost.
- **`numeric.unsigned`.** First in the `notEnforced` ledger with its measured
  count. The rule is only enforceable in a **service's own language types** — Go
  has no unsigned JSON and TypeScript has no unsigned number, so this is the one
  of the four that no document can carry.

## The known gap, admitted rather than papered over

`IDENTITY_NAME_TOKENS` matches a field **name**, so it is this fleet's spelling.
Of the 6 adopter findings, 4 were caught because their names are on the list
(`byte_size`, `iat`, `exp`, `last_used_at`) and 2 because `created` happens to be
on it too. A service calling the same field `size_bytes` or `expires` gets
nothing. This is the **same admitted gap** `REPORT-core-negative-01.md` §5 records
for the tenancy vocabulary, and the reason it is stated rather than smoothed over:
the rule catches a fleet whose vocabulary it knows. Widening the list is a
**hazard**, not a chore — a token that matches a harmless counter starts failing
real contracts, and a failing-everywhere rule is disabled.

If you widen it, the three things to do in the same commit: add the token to
`docs/numeric-conventions.md` (a test asserts every token is there), add a case
to `harness/tests/numeric_self_test.sh`, and re-measure the survey.

## The one-line orientation

`bin/prime` runs the check; CI runs its red proof. That asymmetry is deliberate,
dated, and argued in `bin/prime`'s own header and in `docs/gate.md`. **Do not
"fix" it by moving either one.**