# REPORT — core-negative-01

**Packet:** core-negative-01 · **Repo:** `cafaye/core` · **Branch:**
`worker/core-negative-01` · **Base:** `acf6d11` · **Four commits**, worktree green
at `254/254`.

Read this first if you have not seen the packet. It has two halves: **what the
fleet proves today, measured**; and **two findings that close three of the four
open shapes** in core's checker, each proved able to go red.

---

## 1. The three shapes, and why the third one is a trap

Postgres denies a cross-tenant access three ways, and they raise different
things:

| denied by | Postgres | assert with |
| --- | --- | --- |
| a missing grant | raises `42501` | an exception assertion |
| a `with check` violation | raises `42501` | an exception assertion |
| **a `using` clause filtering the row out** | **raises NOTHING, matches zero rows** | **an empty result, paired with a read of the victim's row** |

The third is the common one and it is silent. A suite that asserts only "it
threw" passes on it while isolation is completely broken — because a table with
**no policy at all** raises exactly the privilege error such a suite waits for.

The same source adds a fourth clause that is the same silence in a different hat:
never prove an allowed write with `lives_ok`, because it passes when the write
matched zero rows.

## 2. THE GAP — what the fleet actually proves, measured

Not assumed. Every row below was produced by copying
`harness/tests/fixtures/tenancy/conforming/` four times, breaking exactly one
thing in each copy, and running `harness/tenancy_check.py` on it. The
reproduction command is in the commit message for `27bc021`.

### 2a. In core's checker — the gap this packet closes

| # | what a service writes | denied by | should be | checker said | now |
| --- | --- | --- | --- | --- | --- |
| 1 | a `select` denial arm as `assert_raises` | `using` — raises nothing | an absent result | **0 failures, exit 0** | `tenancy.denial-shape` |
| 2 | an `update` denial arm as a bare `assert_equal 0` | `using` — raises nothing | zero rows **and** the row intact | 0 failures, exit 0 | **still accepted — see §5** |
| 3 | an `own-account` write arm proven with `lives_ok` | — | the row's own value | **0 failures, exit 0** | `tenancy.denial-shape` |
| 4 | an `own-account` arm proven with `nil` | — | the row's own value | refused | was already refused |
| 5 | a denied `update` answered with `nil` | `using` — raises nothing | `assert_unchanged` | **0 failures, exit 0** | `tenancy.denial-unpaired` |

**Three of the five were open, and the one that was closed was the positive arm.**
So what core enforced was *"do not claim absence where you claim presence"*, and
what it did not enforce was *"match the assertion to the clause that denies you"*
— which is the `using` shape, the silent one, the common one.

### 2b. In kit and identity — where the shapes ARE covered

**The live Postgres proof already covers all three shapes, and the write side is
already paired.** This is kit's `templates/database/tenancy/isolation.sql`, and
it is genuinely good — it is the reason the gap in §2a mattered:

| shape | where it is proved | asserted as | paired with |
| --- | --- | --- | --- |
| `using` → zero rows | `login/{no-identity,another-tenants}-rows-read-as-none`, `owner/…` (10 spine assertions) | a row count | the positive control `login/own-rows-are-visible` |
| `using` → zero rows, on a WRITE | `login/update-of-another-tenants-row-affects-no-rows`, `…/delete-…` | `get diagnostics … row_count` = 0 | **`login/denied-writes-left-the-other-tenants-rows-intact`** — read back AS ALPHA, scoped to `account_id = alpha`, comparing `string_agg(label)` |
| `with check` → `42501` | `login/insert-into-another-tenants-account-is-refused` | `sqlstate` via `cafaye_observed` | `login/insert-into-its-own-account-is-allowed` |
| missing grant → `42501` | `login-role/cannot-disable-row-level-security`, `login-role/cannot-drop-a-policy` | `sqlstate` | `login-role/is-not-the-table-owner` |

**That is 39 assertions, every shape, and the pairing clause already done
properly** — including the subtle half most implementations get wrong: the
intactness read runs as the **victim's** role, not the attempter's, because "the
denied write changed nothing" is only observable by somebody who can see the row.

**So the finding is narrower and sharper than "the fleet does not cover the
shapes".** The mechanism's proof is complete; what was missing is that **a
service's own `tenancy.yml` was free to declare a denial in a shape that proves
nothing, and the checker believed it.** `kit/tests/tenancy_test.sh` proves
`isolation.sql`; nothing proved the *declaration*. identity embeds a copy of
`isolation.sql` (21 `cafaye_assert` call sites) and `migrations/00017` refreshed
a function in it today — so identity's live proof is current, and its
`tenancy.yml` — the only one in the fleet — was exposed to exactly this gap.

**The two are complementary, not competing.** `isolation.sql` proves the
**substrate** (kit's `protect_table` writes four policies, `FORCE`, and the right
clauses). The checker proves the **declaration** (a service's own entry points
are asserted in a shape that can fail). A service with a correct substrate and a
declaration proving nothing has the gap §2a closes.

## 3. What I added

### `tenancy.denial-shape` — two faults

1. A `select`/`update`/`delete` denial arm naming a **RAISING** token. Those
   three are denied by `using`, which filters the row out and raises nothing, so
   an exception assertion is asserting a *privilege* failure — exactly what a
   table with no policy raises.
2. The `own-account` arm naming a **LIVENESS** token (`lives_ok`,
   `does_not_raise`, …). `lives_ok` passes when the write matched zero rows.

### `tenancy.denial-unpaired` — one fault

A denied `update`/`delete` arm naming an **ABSENCE** token. An empty result is a
lie about a row that exists — the victim's row is still there, and nothing came
back because nothing was *matched*, not because nothing was there. A row count of
zero is also what a write that found nothing to do returns, so without the read
the assertion cannot tell a refusal from a no-op.

**All three are decided from the declaration plus the one line it names.** That is
why they are findings and not a paragraph, and it is why no Postgres is needed —
`harness/` may not take a dependency or open a connection.

### The files

| file | what changed |
| --- | --- |
| `harness/tenancy_check.py` | `RAISING_TOKENS` (28), `LIVENESS_TOKENS` (15), `USING_DENIED_OPERATIONS`, `WRITE_OPERATIONS`, `_denial_shape_fault`, both findings |
| `harness/tenancy_findings.json` | two entries; a **new first `notEnforced` row** for the residual gap |
| `harness/tests/tenancy_self_test.sh` | three breakages; 36 → **39** |
| `tests/test_specs.py` | three rows in the in-process table; one **new test** for the duplicated constraint |
| `schemas/tenant-isolation.schema.json` | `expects`' description says what it may **not** be, beside what it is |
| `docs/tenancy.md` | the measurement table; a section on what the new findings do not prove; counts 24→26, 28→30 |
| `AGENTS.md`, `DECISIONS.md`, `gate.yml` | the rule, **D42**, floor 253 → **254** |

### The vocabularies

They live in the checker, not the schema, for `ABSENCE_TOKENS`'s stated reason:
they are facts about the **service's test file**, and no JSON Schema can ask
whether a line in another language contains `assert_raises`. That makes each a
duplicated constraint, and core's rule makes each a test — which is what the new
test asserts, along with the fact that the raising and liveness lists are
**disjoint**. `throws_ok` is deliberately in neither: it is a liveness assertion
written to look like a raise, and putting it in both would have one declaration
refused for whichever arm was read first.

## 4. Proof it can fail — in the repo's existing idiom

Both new findings have **three** red proofs, each editing **both the file and the
declaration** — a breakage that edited only one would be caught by
`denial-missing` first and would prove the wrong check.

| proof | where | count |
| --- | --- | --- |
| the three shapes | `harness/tests/tenancy_self_test.sh` (7c, 7d, 7e) | 39 breakages, **all red, naming their finding** |
| the same three, in-process | `test_every_behavioural_check_the_checker_has_is_proved_load_bearing` | 3 of 26 findings |
| the vocabulary contract | `test_a_denial_arm_may_not_be_asserted_in_the_shape_the_clause_does_not_deny_in` | control asserted finding-free **first** |

The gate: `bin/prime` **254/254**, red proof green. The self-test: **39
breakages**, 4 warnings, 6 green cases, 0 skipped. `harness/tests/self_test.sh`'s
rule — "a new rule with no breakage is a rule nobody has tested" — is satisfied by
the counts block, which is produced by a counter and not by a human counting.

**The control is unchanged and stays green**, which is the claim that matters for
a rule that could have made legal declarations illegal: a conforming service
declares `assert_unchanged` on its writes and `checksum`/`status`/`id` on its
positive arms, and neither vocabulary contains any of those.

**Adopter check:** `identity` — the only service in the fleet with a
`tenancy.yml` — still reports **0 failures, 1 warning** under the new checker.

## 5. What I did NOT finish, and why

**Row 2 of §2a: an `update` denial arm declared as a bare `assert_equal 0` is
still accepted.** It counts zero rows, so it is not proof the row is intact, and
the checker cannot tell it from `rows_affected_zero` without owning the vocabulary
of six languages' assertion libraries — which
`test_the_three_way_denial_shape_is_required_on_every_entry_point` refuses *on
purpose*. I chose the admitted gap over a rule that fires only on
English-language identifiers, because that rule gets disabled within one release
and leaves the fleet with no check at all rather than an incomplete one.

What **is** enforced is the direction with no good spelling in any language:
**every ABSENCE token is refused on a denied write**, in all six at once, because
"nothing came back" is a claim about a row that exists and no language phrases
that claim better. Row 2 is the first entry in `tenancy_findings.json`'s
`notEnforced` list, quoted in `docs/tenancy.md` with its measured consequence, and
in D42.

**`operation: call` gets no shape check at all.** A repository method's scoping is
enforced above the statement and this checker cannot see which clause denies it,
so `call` is outside both operation sets. A service declaring everything as `call`
is unproved. Left open, with the one-enum fix and its cost written into D42.

**Not done: the reference's pgTAP proposal** — one `.sql` file per RLS'd table,
identical for all six languages, `cafaye/tests/_helpers.sql` with
`authenticate_as` / `authenticate_as_service_role` / `clear_authentication` /
`freeze_time`, impersonation via `set local role` + `set local
request.jwt.claim.sub`. It is the right destination and it is **the successor's
first line**, as the packet says. Three reasons it did not fit the hour: it
migrates six languages; `core` has no Postgres and `harness/` may not open a
connection; and kit's template already carries the equivalents
(`pg_temp.cafaye_as`, `pg_temp.cafaye_observed`) with all three shapes proved on a
live cluster every run, so a second copy in core would be the four-way drift
`harness/` exists to end.

**No mechanism was changed**, so a copy embedded in a service — identity embeds
one, `migrations/00017` refreshed a function in it today — **picks up nothing new
and needs no action.** If a future packet changes `protect_table`, the copy
question becomes live again.

**`docs/tenancy.md` §"what this will not do for you" was not restructured**, and
the three shapes are not yet in `examples/invalid/` as schema-constraining
examples — because they are not schema-constraining, which is the honest reason
rather than an omission.

## 6. Decisions I did not take

`operation: call` (§5) is recorded as an open question in **D42**, with the
alternatives, my recommendation — fold it into the pgTAP migration rather than
give it its own packet — and the cost of flipping. Nothing else in this packet
was a genuine design question: the two findings are the two that could have been
doc-only and the house rule forbids doc-only.

## 7. Commands, and their results

```sh
bin/prime                                      # 254/254, red proof green
bash harness/tests/tenancy_self_test.sh        # 39 breakages red, 0 skipped
cd ../identity && python3 ../wt-m39-…/harness/tenancy_check.py .
                                                # 0 failures, 1 warning
```