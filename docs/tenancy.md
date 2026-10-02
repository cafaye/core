# docs/tenancy.md — how a cafaye service declares its account boundary

The format is `tenancy.yml` at the service's repository root, written against
[`schemas/tenant-isolation.schema.json`](../schemas/tenant-isolation.schema.json),
checked by [`harness/tenancy_check.py`](../harness/tenancy_check.py), and proved
able to fail by [`harness/tests/tenancy_self_test.sh`](../harness/tests/tenancy_self_test.sh).
This document is the reasoning, including the things it will not do for you.

A declaration has **two** halves and they are separate claims about separate
things. `entryPoints` says where the service's **code** draws the boundary and
which test proves it. `rls` says what **Postgres** does — and the rule that
block exists for is one Postgres does not document where anybody looks for it and
**no lint in the world checks**: a table's owner bypasses row-level security
unless the table is set `FORCE ROW LEVEL SECURITY`, and a service owns the tables
it created. Start at [The three-way denial shape](#the-three-way-denial-shape)
for the test side and [What the database does about it](#what-the-database-does-about-it--rls)
for the FORCE bit.

## Why this file exists

The platform is sold as self-hostable multi-tenant code. The defect that ends
that product is one customer reading another's data, and nothing in the fleet
made it visible:

```
cross-tenant NEGATIVE tests — ones asserting account A is refused account B
  identity 7    courier 19
  billing 0   cafaye-rb 0   cafaye-ts 0   guard 0
  darkroom 0  pantry 0     muse 0        cafaye-py 0
```

Two services prove isolation. Eight do not, and six of those scope by account
in production code.

**The implementations are largely correct.** `darkroom` is the clean example:
`assets` and `asset_variants` carry `account_id uuid not null`, there is a
`unique (account_id, checksum)`, and every query constrains on it —

```sql
where id = $1 and account_id = $2
update assets where id = $1 and account_id = $2 and status = 'pending'
delete from assets where id = $1 and account_id = $2
```

— with **zero** tests asserting any of it. A refactor that drops one
`and account_id = $2` gives a customer another customer's files and the whole
suite stays green. Correct by construction, unprotected by test.

## Why not a grep, or a rule, or an inference

The part that matters more than the missing tests is that **nobody can ask the
question mechanically**. Counting account-scoped routes by pattern gives a
different answer per framework:

```
  guard       route_defs=96     (TypeScript decorators)
  muse        route_defs=76
  cafaye-ts   route_defs=51
  darkroom    route_defs=0      (axum — a different syntax entirely)
  billing     route_defs=0      (Rails — a different syntax entirely)
```

A grep that reports "darkroom has no routes" when darkroom has account-scoped
queries against customer assets is **worse than no grep**, because it reads
like an answer. Someone runs it, believes it, and stops looking.

So the fix is not "grep harder". It is the same move that made
[the gate](gate.md) work: `core` publishes a format, `kit` distributes it, and
services adopt one shape. Cross-tenant access is **declared, never inferred**
(**D33**).

There is also a rule-shaped version of the question that does not work, and
worth naming so nobody writes it later: "every query touching a
`tenant`-prefixed table must have a `tenant_id` predicate". It cannot see the
join that drops the scope, the repository method three layers down, the CTE that
loses it between two `select`s, or the middleware that resolves the account in
the first place — and a rule that is right about 90% of the sites reads as a
boundary that is enforced.

## What already worked, and what this copies

Two services already write the right test, and this format is their shape:

- `courier/test/courier/webhook_endpoints_test.exs` and
  `courier/test/courier/workers/dispatch_webhooks_worker_test.exs`
- `identity/internal/apikeys/service_test.go` (`TestRevokeCannotCrossTenants`)
- `identity/internal/httpapi/admin_integration_test.go`
  (`TestAnAdminCannotReadAnotherAccountsTrail`)
- `identity/internal/httpapi/oidc_test.go` (the `otherAccount` fixture)

What they share, and what the format preserves:

1. **A second account fixture** — `f.otherAccount(t)`, `@other_account_id`,
   `f.elsewhere`.
2. **A negative assertion per entry point** — and the assertions are about
   **absence, not refusal**:

```elixir
assert WebhookEndpoints.get(endpoint.id, @other_account_id) == nil
assert WebhookEndpoints.list(@other_account_id) == []
assert WebhookEndpoints.enabled(@other_account_id) == []
```

That second half is the load-bearing decision and it is **D33**: cross-tenant
access must be *indistinguishable from nonexistence*. A `403` tells an attacker
the id exists; a `nil`/`[]`/`NotFound` tells them nothing. If your contract
permits a service to answer "forbidden" for another account's resource, it has
reintroduced an enumeration oracle, and a test must be able to catch that —
which is why `negative.asserts` is a `const: absent` rather than an enum with a
discouraged second value.

## The three-way denial shape

**The question is not "does an unauthenticated request fail".** That question is
satisfied by a table with no policy at all, by a table with no predicate at all,
and by a service whose database is switched off — and all three of those are the
**bug**, not the fix. A service that answers "nothing" to everybody passes that
test perfectly and forever, and so does a service that answers "everything" to
everybody if its table has no policy and no `FORCE` bit.

So the boundary has to answer three questions, and `negative.cases` is exactly
three entries, one per question:

| `id` | who is acting | what must come back |
| --- | --- | --- |
| `no-identity` | nothing at all — no session, no credential | **zero rows** |
| `other-account` | a **valid** credential belonging to a *different* account | **zero rows** |
| `own-account` | this account's own valid credential | **its own rows** |

**`other-account` is the arm with all the information in it**, and it is the one
a naive suite leaves out. `no-identity` is nearly free: refusing an
unauthenticated request is what an absent predicate or an absent policy does by
accident. `other-account` is the only arm that requires the credential to be
*real* and the scope to be *checked*.

**`own-account` is the control, and `cases` is `minItems: 3`/`maxItems: 3`
because of it.** Without the third arm the first two are satisfied by a service
that returns nothing to anybody — a broken service. So `own-account` is
`const: present`, and `negative.cases[].expects` on that arm is **a column or
field the assertion reads off the row that came back** (`checksum`, `status`,
`object_key`), not merely "the call did not raise". `lives_ok` passes when the
write matched zero rows, which is exactly the failure the third arm exists to
catch. And it is refused to be an absent spelling: pointing the arm at a line
that asserts `nil` is `tenancy.positive-control-refused`, a **FAILURE**, because
it is a declaration that says "this account sees its own rows" about a test that
says the opposite.

### Match the assertion to how the request is denied

The three arms are not three of the same assertion. Postgres denies a row two
different ways and they want different assertions, and getting this wrong is how
a policy that admits every tenant gets a green test:

| Denied by | Postgres | Assert with |
| --- | --- | --- |
| a missing grant | raises `42501` | an exception assertion (`throws_ok`, `assert_raises`) |
| a `with check` violation | raises `42501` | an exception assertion |
| a `using` clause filtering the row out | **raises nothing, matches zero rows** | an empty-result assertion (`is_empty`, `assert … .empty?`) |

So `rls.policies[].clause` records which mechanism each policy uses, and the
schema **derives it from `command`** rather than letting a service choose:
`for select` and `for delete` are denied by `USING`; `for insert` is denied by
`with check`; `update` and `all` may carry either. Asserting an exception on a
read that a `using` clause filtered out is asserting a *privilege* failure — and
if the table has no policy at all, that is exactly the error you get, so the test
passes for the wrong reason.

And **a denied write is never proved by the write alone.** Pair every denied
write with a read proving the target row is intact, scoped to that row: a suite
that asserts on everything a role can see breaks the moment the table holds more
than one customer's data. `negative.cases[].expects` for a write is therefore
the assertion's own name — `rows_affected_zero`, `assert_unchanged` — rather
than an empty result, which would be a lie about a row that exists.

## What the database does about it — `rls`

`tenancy.yml` has a second half, and it is required. `accountScoped` says what
the service's code does; `rls` says what **Postgres** does, and the two claims
are independent: every line of the `rls` block could be deleted and the
`entryPoints` predicates would still hold.

```yaml
rls:
  databaseEnforced: true          # false + tables: [] is the honest "the DB does nothing"
  identity: app.current_account()  # the stable, zero-argument call every policy reads
  sources:
    - migrations                   # a SEPARATE list from scope.sources — see below
  tables:
    - table: assets
      forced: true                 # const. this is the load-bearing field in the file.
      policies:
        - name: assets_select_own
          command: select
          clause: using
          roles: [tenant_app]      # `public` is refused
          constrained:
            file: migrations/0002_rls.sql
            line: 67
```

**`forced` is a `const: true`, and it is the single highest-value thing in this
document.** Postgres does not apply row-level security to a table's **OWNER**
unless the table is set `FORCE ROW LEVEL SECURITY`. A service creates its tables
in its own schema and therefore **owns them**. So a migration that writes

```sql
create policy assets_select_own on assets for select to tenant_app using (…);
alter table assets enable row level security;
-- and stops
```

has shipped a policy that is **never evaluated by the role that matters**. Every
query still succeeds. Every policy still exists in `pg_catalog`. Nothing raises,
because a policy that is never evaluated is not a policy that fails — and the
runtime role reads every row in the table.

Two things make this the rule to have. **Postgres documents it in the CREATE
TABLE reference and not in the row-level-security guide**, and **no lint checks
it**: Supabase's database advisor — the reference for this whole problem —
collects `relforcerowsecurity` for its dashboard's table list and never judges
it (measured: `packages/pg-meta/src/sql/studio/advisor/lints.ts`, which holds
twenty-eight lints and none of them is this one). Cafaye uses `FORCE` zero times
today across nine account-scoped services, which is why this is free to prevent
rather than expensive to retrofit.

`force` is a **separate `reloptions` bit** from `enable` and neither implies the
other, which is why the schema constrains one thing and the checker checks the
other: the schema cannot see the migrations, and the checker cannot see the
schema. `tenancy.rls-owner-bypass` is where they meet, and
`harness/tests/tenancy_self_test.sh` proves it by deleting the one `force` line
from the fixture and asserting that finding appears **about that table and
nothing else**.

### Why `rls.sources` is a second list

`scope.sources` is where the account-scoped **statements** are; `rls.sources` is
where the **DDL** is. In a Go service those are `internal/` and `migrations/`,
and one list naming both is a list that ends up naming the whole repository —
which is the dependency-tree answer `harness/tenancy_findings.json`'s
`notEnforced` entry names as this checker's sharpest limit. Two lists, each
naming exactly what its own check reads, and one `tenancy.scan-narrowed`
warning for "a declared path is not there".

### `databaseEnforced: false` is a claim, not a gap

Six of this fleet's account-scoped services scope every statement in their
repository and enable row-level security on nothing. That is a legitimate design
— `darkroom`'s is the clean example — and
[`examples/valid/tenancy.rls-declared-none.yml`](../examples/valid/tenancy.rls-declared-none.yml)
is what saying so looks like.

It cannot simply be **left out**, for the same reason `accountScoped` cannot: an
omitted block and a block saying `false` are the same file to a reader who has
not been told which one they are looking at. And it is not inert — a policy, a
`force` bit or an `enable` line anywhere in `rls.sources` is
`tenancy.rls-undeclared`, a **FAILURE**. So `false` is a claim, the claim is
checked, and the day somebody writes the first migration they have to say so.

`identity` must be a **zero-argument call**. That is not tidiness: the rule below
is about the call being hoisted out of the row loop, and a call with arguments
cannot be hoisted. `current_setting('app.account_id')` is deliberately not
declarable here — it is the shape this field exists to steer away from, and
[**D41**](DECISIONS.md#d41-how-is-the-force-rule-declared-and-what-may-a-warning-mean-in-the-tenancy-checker)
records that as the first thing to revisit.

### The per-row rule: `(select …)`, not the bare call

Write the identity wrapped:

```sql
-- RIGHT. One evaluation per statement; the planner treats it as an InitPlan.
using (account_id = (select app.current_account()));

-- WRONG. Re-evaluated for every row the statement touches.
using (account_id = app.current_account());
```

**The reason, and why it is a failure.** Supabase's note on this lint is "this
produces suboptimal query performance at scale", which is true and is not the
reason core made it a **failure** rather than a warning. The reason is what a
warning means *in this checker*: the three warnings `tenancy_check.py` already
had all say *this machine cannot answer that question*, and a warning that does
not move the exit code exists because failing on it would get the checker
disabled. That argument does not transfer to a fact that is fully decidable from
the migration text. A severity nobody chose is not a severity, so the finding is
`tenancy.rls-per-row` and it is a failure.

The wrapped form is also what makes the plan reusable: Postgres evaluates the
`stable` function once and the planner can cache the result, so the policy's
predicate stops being a per-row call into `current_setting`. And it composes with
the `identity` requirement — a zero-argument call can be hoisted, a call with
arguments cannot, which is why the declaration's pattern ends in `()`.

## The ledger — Supabase's twenty-eight lints, and this one

Supabase's [database advisor][advisor] is the reference for this problem and is
worth reading rather than reinventing: **twenty-eight** lints, of which
**thirteen** are `SECURITY` and several of those are exactly the shapes a
database-per-service fleet gets wrong. The brief that asked for this said thirty;
**measured, it is twenty-eight** — the advisor is one SQL string and `lints.ts`
holds exactly that many `'…' as name,` blocks. The number is recorded here rather
than repeated because a number in a document goes stale and the fix is to
re-measure, which is the lesson PLAN.md §4b draws about counts.

`test_the_row_level_security_rules_are_adopted_and_the_exclusions_are_written_down`
reads the table below and fails if a lint is missing from it, if a row names no
cafaye finding, or if a row says `left out` with no reason. **A rule that was
looked at and left out on purpose is a decision; the same rule left out silently
is the thing this whole document exists to stop.**

<!-- rls-ledger:begin -->

| Supabase lint | Level | Verdict | cafaye finding | Why |
| --- | --- | --- | --- | --- |
| `policy_exists_rls_disabled` | ERROR | adopted | `tenancy.rls-not-enabled` | Policies with RLS never enabled: the policies are never evaluated and nothing raises. Adopted whole — the fact is the same in a service's own migration. |
| `rls_enabled_no_policy` | INFO | adapted | `tenancy.rls-policy-absent` | Supabase rates this INFO because a deny-all table is fail-closed and harmless. In cafaye it is folded into *closure*: a declared table with no policy in the DDL is `rls-policy-absent`, and a policy in the DDL that the declaration does not name is `rls-undeclared`. The severity comes from closure rather than from a judgement about deny-all. |
| `rls_policy_always_true` | WARN | adapted | `tenancy.rls-permissive` | Adopted with **one deliberate change**: Supabase excludes `USING (true)` on a SELECT because deliberate public read is a real thing on their platform. Cafaye has no public read tier — every table in `rls.tables` is account-scoped by construction — so the exclusion does not carry over. This is the one place a severity goes **up**, and it is recorded here rather than buried. |
| `auth_rls_initplan` | WARN | adapted | `tenancy.rls-per-row` | Their `auth.uid()` becomes our declared `identity`, and their `WARN`/`PERFORMANCE` becomes a FAILURE: see *The per-row rule* above for why a warning in this checker means "this machine cannot answer" and this one can. |
| `function_search_path_mutable` | WARN | adapted | `tenancy.rls-definer-search-path` | Adopted whole and raised from WARN. In cafaye the runtime role can create objects in its own schema, so an unpinned `search_path` on a `security definer` function is a tenant-crossing primitive rather than a hardening nit. |
| `security_definer_view` | ERROR | adapted | `tenancy.rls-view-invoker` | Their question is "can `anon` reach this view", which is a **privilege** question about `has_table_privilege` and this checker has no database. Ours is "does the reader's policy run", which is a fact about the DDL: a view without `security_invoker` is security definer by default on every PostgreSQL version. |
| `foreign_table_in_api` | WARN | adapted | `tenancy.rls-unprotectable` | Their WARN is about PostgREST reachability. Ours is the underlying fact, which is stronger and needs no API: a foreign table has no policies to enforce, so a policy on one is a comment. |
| `materialized_view_in_api` | WARN | adapted | `tenancy.rls-unprotectable` | The same finding and the same reason: a materialized view cannot carry row-level security at all, and a snapshot of every tenant's rows is not a boundary. Merged with the foreign-table rule because it is one fact about Postgres. |
| `multiple_permissive_policies` | WARN | left out | — | A **performance** lint: several permissive policies for one (role, command) each run. The security consequence — that permissive policies are OR-ed, so an undeclared one can widen a declared one — is real, and it is already covered: an undeclared policy on a declared table is `tenancy.rls-undeclared`. Counting policies would be a fact this checker can determine and is not a defect, and core's finding vocabulary is for defects. |
| `rls_references_user_metadata` | ERROR | left out | — | Specific to Supabase's `auth.users.user_metadata`, which cafaye has no equivalent of: identity is cafaye's own service and the account arrives as a verified JWT claim. The *shape* of the defect — a policy whose identity input the caller can change — is not checkable from a migration, because whether `app.current_account()` is set from a verified claim or from a header is a fact about a service's middleware and not about its DDL. |
| `anon_security_definer_function_executable` | WARN | left out | — | Asks whether the `anon` role can `EXECUTE` a function. cafaye has no `anon`; the runtime role is named per service, and a `security definer` function the runtime role can call is not itself the defect. What closes the hole — the `search_path` pin — is `tenancy.rls-definer-search-path`. |
| `authenticated_security_definer_function_executable` | WARN | left out | — | The same rule against the other role. Same reasoning, and the second copy of it would double the findings without adding a fact. |
| `auth_users_exposed` | ERROR | left out | — | Entirely about views over Supabase's `auth.users` reaching PostgREST. There is no `auth.users` here and no PostgREST; identity's tables are reached by its own API, not by a generic data plane. |
| `rls_disabled_in_public` | ERROR | left out | — | The predicate is "a role the API can reach has RLS disabled", which is `has_table_privilege` against a schema list this checker does not have. Its *intent* — a table carrying the tenancy key and no RLS — is what `tenancy.rls-undeclared` names in the direction cafaye can close, which is the one where a service claims a boundary it did not declare. |
| `fkey_to_auth_unique` | ERROR | left out | — | Foreign keys into Supabase's `auth` schema. Cafaye's identity-side tables are reached by id across services rather than by a cross-database foreign key, so the shape has no instance here. |
| `sensitive_columns_exposed` | ERROR | left out | — | A column-name denylist (`password`, `api_key`, …) combined with "the table is API-exposed". Both halves are wrong for cafaye: the exposure question needs `has_table_privilege`, and core has no column denylist anywhere — `docs/observability.md`'s vocabulary is a closed **allow**list for exactly this reason, and a denylist of secret-ish words catches nothing that a well-named column is not already safe from. |
| `insecure_queue_exposed_in_api` | ERROR | left out | — | `pgmq` queue tables in the `pgmq` schema. cafaye uses no Postgres queue extension; the outbox convention is a plain table drained by the service's own code (`docs/event-outbox.md`). |
| `unindexed_foreign_keys` | INFO | left out | — | Performance, not boundary. It belongs with the query-path lints kit already ships, not with a check whose reason for existing is one customer reading another's data. |
| `no_primary_key` | INFO | left out | — | Performance. The same answer. |
| `unused_index` | INFO | left out | — | Performance, and the one lint here whose answer legitimately requires running the database's statistics rather than reading a migration. |
| `duplicate_index` | WARN | left out | — | Performance. The same answer. |
| `extension_in_public` | WARN | left out | — | A schema-hygiene rule about where extensions install. Nothing to do with an account boundary. |
| `extension_versions_outdated` | WARN | left out | — | A supply-chain check against `pg_available_extensions`, which needs a database connection and says nothing about tenancy. |
| `unsupported_reg_types` | WARN | left out | — | An upgrade-tooling rule about `reg*` column types blocking `pg_upgrade`. Nothing to do with an account boundary. |
| `table_bloat` | INFO | left out | — | Maintenance. Needs `pg_stats`, needs a database, and says nothing about tenancy. |
| `public_bucket_allows_listing` | WARN | left out | — | Supabase Storage buckets. darkroom's objects are in S3/R2 behind presigned URLs, and there is no bucket with a `SELECT` policy on it. |
| `pg_graphql_anon_table_exposed` | WARN | left out | — | Requires the `pg_graphql` extension, which cafaye does not use and should not. |
| `pg_graphql_authenticated_table_exposed` | WARN | left out | — | The second copy of the same rule against the other role. Same answer, and the reason is the extension rather than the role. |

<!-- rls-ledger:end -->

**And the one with no Supabase ancestor at all**, which is why it has no row in
the table above: **`tenancy.rls-owner-bypass`**. It is the FORCE rule, there is
no lint behind it anywhere, and "adopted from Supabase" would be claiming a
credit that does not exist. It is the reason this half of the format is here.

[advisor]: https://supabase.com/docs/guides/database/database-linter## The format

```yaml
version: 1
service: darkroom

# Required, and a boolean. "I have no boundary" is a claim, and a format that
# cannot express it forces every service to either invent one or omit itself.
accountScoped: true

scope:
  key: account_id        # the tenancy key THIS service scopes by
  sources:               # exactly what the checker may read
    - migrations
    - src

rls:
  databaseEnforced: false   # true when Postgres holds the boundary; see `rls` above
  sources:                  # the DDL, which is NOT the same tree as scope.sources
    - migrations
  tables: []                # empty exactly when databaseEnforced is false

entryPoints:
  - id: asset-fetch
    operation: select        # select | update | delete | call
    subject: assets
    enforced:
      mechanism: query-filter # query-filter | bind-parameter | repository-method | middleware
      file: migrations/0001_assets.sql
      line: 22
    negative:
      asserts: absent        # const. the only legal value at this level.
      cases:                 # EXACTLY three — see the three-way section above
        - id: no-identity    # nothing is acting            -> zero rows
          asserts: absent
          expects: nil       # this language's spelling of nothing
          file: tests/tenancy_test.rb
          line: 39
        - id: other-account  # a VALID credential, other one -> zero rows
          asserts: absent
          expects: nil
          file: tests/tenancy_test.rb
          line: 44
        - id: own-account    # this account's own credential -> ITS ROWS
          asserts: present   # const. the third arm is a control, not a denial
          expects: checksum  # a column read off the row that came back
          file: tests/tenancy_test.rb
          line: 49
```

Three things per entry point, and all three are required:

- **where the scoping happens** — `mechanism` from a closed vocabulary, plus the
  file and the line. `mechanism: bind-parameter` additionally names the
  parameter, because a query that still says `account_id = $2` while nothing
  passes `$2` any more is scoped on paper and unscoped in fact.
- **the three denial cases**, each on the line it names, and the third of them
  asserting that the account's own rows come back.
- **an id**, because a finding, a test and a human all need to name the same
  thing.

### Why the line is a line

`enforced.line` is **exact**, and the drift it causes is the intended trade. A
refactor that moves a query three lines down is `tenancy.scope-lost` until the
declaration moves with it, and the message says which of two things happened:
the scoping moved, or the scoping was dropped. Those want different fixes and a
checker that cannot tell them apart reports the second as a pass.

**Closure does not use the line.** An entry point's identity is its file, its
operation and its subject, so:

- a query that moves → the declaration's line is stale (`scope-lost`) and the
  entry point still exists;
- a query that loses its predicate → the site disappears and `entry-absent`
  fires, which is the red that matters;
- adding a new scoped query → `undeclared-entry`, which is the other red.

That split is what keeps a refactor from opening ten failures while still
catching the one that ends a customer's data.

### Why `insert` is not an operation

An insert creates a row in the account the caller is already acting as. It
cannot read or write another account's row, so it is not a place a cross-tenant
leak can happen — and including it would mean a legal declaration whose
`enforced.line` does not carry the tenancy key, because the account is in the
column list rather than in a predicate. An exception inside the contract is how
the next exception gets added.

### Why `call` closes nothing

`operation: call` is for a repository method, a worker or a route whose scoping
is enforced above the statement. Closure cannot be checked against it: the same
line is a `select` to a human deciding where a leak can happen and something
else entirely to a text scanner. Guessing between those is the failure this
whole format exists to stop, so `call` closes nothing and the checker says so —
`tenancy.enumeration-partial` names every `call` it could not classify.

## What the checker reports

`tenancy-check <repo>`, twenty-eight findings in
[`harness/tenancy_findings.json`](../harness/tenancy_findings.json), each with
the exact command that fixes it. Exit codes are the three the gate checker uses:
`0` clean, `1` at least one failure, `2` the check could not happen — and `2` is
never collapsed into `0`, because a check that could not find the declaration
has not checked the boundary.

**Twenty-four failures**, in three groups. The three that say the declaration
describes nothing that is there:

| id | what it means |
| --- | --- |
| `tenancy.declaration-missing` | there is no `tenancy.yml` |
| `tenancy.declaration-unreadable` | it is not a YAML document core's reader accepts |
| `tenancy.schema` | it does not satisfy the schema |

And the eleven that say the declaration no longer matches the code — which is
the whole contract:

| id | what it means |
| --- | --- |
| `tenancy.location-missing` | a declaration names a file this service does not have |
| `tenancy.line-missing` | a declaration names a line past the end of the file |
| `tenancy.scope-lost` | the entry point is still scoped, but not on the line it names |
| `tenancy.bind-missing` | the mechanism is `bind-parameter` and the parameter is not on the line |
| `tenancy.entry-absent` | declared, and the scanner can no longer find it — the scoping was dropped |
| `tenancy.undeclared-entry` | the scanner found account-scoped access nobody declared |
| `tenancy.denial-missing` | a denial arm is not on the line the declaration names, and the message says WHICH ARM |
| `tenancy.denial-refuses` | the declaration answers cross-tenant access with a refusal |
| `tenancy.positive-control-refused` | the third arm is answered with this language's spelling of nothing, so a service returning nothing to everybody passes all three |
| `tenancy.honest-zero` | the service declares no scoping and has account-scoped code |
| `tenancy.enumeration-empty` | the service says it scopes by account and declares no way it does |

And the ten that say what the **database** does does not match the declaration.
This group is new, it is the whole of the second half, and
`tenancy.rls-owner-bypass` is the one it exists for:

| id | what it means |
| --- | --- |
| `tenancy.rls-owner-bypass` | **the table is not set `FORCE ROW LEVEL SECURITY`, so its OWNER — the role this service connects as — reads every row in it** |
| `tenancy.rls-not-enabled` | policies exist and RLS is not enabled, so none of them is ever evaluated |
| `tenancy.rls-policy-absent` | the declaration names a policy the migrations do not create |
| `tenancy.rls-undeclared` | row-level-security DDL exists for a table (or a policy) the declaration does not cover — the half-adopted boundary |
| `tenancy.rls-permissive` | a clause is always true, or a policy names no role and therefore applies to `PUBLIC` |
| `tenancy.rls-per-row` | the identity is called bare instead of as `(select …)`, so it runs once per row |
| `tenancy.rls-role-bypass` | a policy applies to a role carrying `BYPASSRLS` or `SUPERUSER` |
| `tenancy.rls-unprotectable` | a policy is on a foreign table or a materialized view, neither of which row-level security can constrain |
| `tenancy.rls-definer-search-path` | a `SECURITY DEFINER` function does not pin its `search_path` |
| `tenancy.rls-view-invoker` | a view over an account-scoped table is not `security_invoker`, so the reader's policies never run |

**Four warnings**, and none of them moves the exit code. All of them are the same
claim — *this machine cannot answer that question*:

| id | what it means |
| --- | --- |
| `tenancy.enumeration-partial` | the scanner could not classify every site; the enumeration is **not** proven closed |
| `tenancy.scan-narrowed` | a declared source path is not there, so the scan read less than declared |
| `tenancy.scope-key-unused` | no statement the scanner can read carries the declared key |
| `tenancy.rls-unreadable` | row-level-security DDL was found in a file this checker cannot parse — a Rails migration is a `.rb` file, a Python migration is a `.py` file, and both are **named** rather than passed over |

A warning is a claim about the machine, it is printed and counted separately, and
it leaves the verdict alone. Failing on those is how a checker gets disabled,
which would leave the fleet with **no** boundary check instead of an incomplete
one; ignoring them silently is how a report becomes a lie — and this checker's
entire reason for existing is a grep that reported "darkroom has no routes".

### What the scanner reads, and what it says it cannot

The scanner reads **SQL statements** whose line carries the tenancy key, or a
line within `ATTRIBUTION_WINDOW` (four) above one. It skips `create table`
blocks — which name the column rather than reach a row — and `insert`, for the
reason above. The key itself is **declared by the service**, never guessed: the
fleet already has three vocabularies for it (**D7**), and a checker that picked
one would be guessing at the boundary rather than at the data.

Everything else is reported by name and not counted as covered. Measured over the
thirteen repositories in this fleet with the scanner pointed at each whole tree:

| | services | of which the scanner can classify |
| --- | --- | --- |
| SQL-heavy (identity, darkroom) | 2 | 21 and 10 classifiable sites |
| language-neutral or framework-scoped (courier, billing, cafaye-py, muse, guard, cafaye-ts, cafaye-rb, parlor) | 8 | 10–124 account-key lines, **0** classifiable |

The second row is the whole point of `enumeration-partial`. Those eight services
get a warning naming every file and line the scanner saw and could not attribute,
an exit code of `0`, and **never** a line reading "no account-scoped entry
points found".

## What this does not prove

The eight entries in `harness/tenancy_findings.json`'s `notEnforced` list are
the honest inventory, and the two worth stating here are these.

There are two, and they are the ones a service author will hit.

**A negative assertion is READ, not run.** `tenancy.denial-missing` proves the
assertion is *written* — a second account fixture, an absent-shaped result, at a
line a reader can open. Running darkroom's suite needs its container and its
Postgres; running courier's needs a mix database. A checker that started
containers to see whether an isolation test passed would be red on a laptop and
green on CI depending on what happened to be running, which is the defect
`gate.requirement-unproven` already exists to name. Running the test is the
gate's job, in the service. This is a real gap and it is the same one MD12
names: a test that is written and never run reads exactly like a test that
passes. **The database half adds to it rather than fixing it:** a `.sql`
migration is read as text, so `tenancy.rls-owner-bypass` proves the migration
says `force`, not that the deployed database has the bit. The two are kept in
step by running the migrations, which is the same obligation.

**`enforced.line` is the only place the scoping happens.** The checker reads one
line and asks whether it carries the key. A statement that scopes in a CTE, a
subquery, a view, or a repository method three layers down is scoped, and this
checker can be pointed at the wrong one line of it — which is why `call` exists,
and why a service with two enforcement points declares two entry points.

The other six — completeness for a language the scanner cannot read, the
database half's three (`.sql` only, `SECURITY DEFINER` bodies, and a table with
no account column), and the line's exactness — are in the JSON with their
reasoning.

## Adopting it in a service

1. Write `tenancy.yml` at the root. Start from
   [`examples/valid/tenancy.account-scoped.yml`](../examples/valid/tenancy.account-scoped.yml)
   — or the honest zero in
   [`examples/valid/tenancy.honest-zero.yml`](../examples/valid/tenancy.honest-zero.yml)
   if the service holds no customer rows. Do not skip step 2.
2. **Write the negative assertions first**, then point `negative.cases[]` at
   them. Two account fixtures and **three** assertions per entry point: two that
   assert absence and one that asserts the account's own row comes back. The
   third is the one with the information in it. This is the deliverable;
   `enforced` is the claim.
3. **Then the `rls` block**, and it is a question rather than a chore: does the
   database hold this boundary or does the repository? `false` with an empty
   `tables` is a legitimate answer and the honest one for most services today —
   write it down. `true` means writing `alter table … enable row level security`
   **and `force row level security`** for every table you list, plus an
   `identity` function and a policy per command, and it is worth doing: the
   FORCE bit is the one rule in this whole document that nothing anywhere checks.
   See [`examples/valid/tenancy.rls-enforced.yml`](../examples/valid/tenancy.rls-enforced.yml).
4. `tenancy-check .` and fix what it names. A Go or Elixir service will get
   warnings; that is the expected verdict, not a failure to fix.
5. Add it to the gate once it is green. Until then it is a second thing to
   remember, which is how it will be forgotten.

## The red proof

[`harness/tests/tenancy_self_test.sh`](../harness/tests/tenancy_self_test.sh)
takes one conforming fixture, copies it, and breaks exactly one thing in each
copy: a missing `WHERE` on a read, a missing bind parameter, an unscoped list,
an unscoped update, an unscoped delete, an IDOR on fetch-by-id, a negative
assertion weakened from *absent* to *forbidden*, a file that is not there, a
line past the end of the file, a refusal in the declaration, an undeclared
query, and a service whose honest zero is not honest. Each asserts the checker
goes red **and names the finding and the entry point** — "something went red" is
not the claim, "this check is still the one that catches this defect" is, and
the two decay differently.

Four more break the declaration rather than the code, and they cover the four
findings that fire *before* a boundary is even declared — which is where the
fleet starts, since every repository in it produces
`tenancy.declaration-missing` today. A `tenancy.yml` that is not there, one the
reader cannot parse, a service that claims to scope by account and names no way
it does, and a declaration carrying a key the format does not declare.

**Eleven more break the database half**, and they are the ten
`tenancy.rls-*` failures plus the positive control. Two of them are worth
naming because they are the packet in miniature:

- **breakage 17 deletes one line** — `alter table assets force row level
  security;` — and asserts that `tenancy.rls-owner-bypass` fires **about that
  table and about nothing else**. `force` is a separate `reloptions` bit from
  `enable`, so removing it cannot disturb the line beside it, which is what lets
  one finding be proved by one deletion rather than by a diff that moved two
  things;
- **breakage 7b points the third arm at a line asserting `nil`** and asserts
  `tenancy.positive-control-refused`. The other two arms are untouched and still
  green: the defect is one nobody notices, because every case a suite usually
  writes still passes.

The rest are the nine neighbours: policies that are never evaluated, a declared
policy the migrations do not create, DDL for a table nobody declared, `using
(true)`, the bare identity call, a policy applied to a `BYPASSRLS` role, a
policy on a foreign table, an unpinned `search_path` on a `SECURITY DEFINER`
function, and a view that reads as its owner.

**Every one of the twenty-four failure-severity findings has a breakage naming
it**, and `test_every_tenancy_finding_is_proved_able_to_go_red` in
[`tests/test_specs.py`](../tests/test_specs.py) is what keeps that true: a
finding added without a breakage is red rather than shipped untested. That
assertion is the reason the four above exist — they were the four that did not,
and every repository in the fleet was about to hit them. The same eleven RLS
breakages are ALSO driven in-process by
`test_every_behavioural_check_the_checker_has_is_proved_load_bearing`, which is
the only one of the three proofs `bin/prime` runs; a rule proved only in CI is a
rule a developer running the gate locally has learned nothing about.

Four cases assert a **warning stays green**: the unreadable-language service, a
declared source path that is not there, a key nothing matches, and row-level
security written in a language this checker cannot parse. All four exit `0`. Two
green cases assert the report *names what it cannot see*, because a checker that
printed nothing at all about a service it cannot read would pass those too.

The control runs first and is asserted **warning-free**, not merely green: that
is what proves the scanner classifies everything the fixture contains, so the
warning cases are warnings about a fixture's shape rather than artefacts of an
over-eager scanner.

One detail in the script is worth naming because it is the bug this packet is
about, in miniature. Each breakage is applied by a textual `edit` that **fails
loudly when its anchor is missing, and equally when its anchor is ambiguous** —
when the file contains that text more than once. It did not used to, and the
first run of the stricter version caught a breakage that had been editing a
`#` comment instead of the line beneath it: green, reporting a check it had
never exercised. That is the same failure as a grep reporting "darkroom has no
routes", and the guard against it is a tool that says *I could not tell which
one you meant* rather than picking the first.

**It caught four more the day the database half landed**, and that is the
argument for it in one sentence: a policy's clause text
(`account_id = (select app.current_account())`) appears five times in the RLS
fixture, and a declaration's `expects: checksum` appears on three of its seven
entry points. Every RLS anchor therefore spans the `for … to …` line above the
clause, or the `create policy … on <table>` line above that, and the same anchors
are used in `tests/test_specs.py` so the two proofs cannot drift. A breakage that
had quietly edited the wrong policy would have reported a pass for a check it had
not exercised — the exact defect this script exists to prevent, discovered by the
guard rather than by a reviewer reading carefully.

It is deliberately not inside `bin/prime`. A self-test in every gate invocation
is a second gate that can disagree with the first, which is why core's CI runs it
as a step of its own.

## Open questions, left open deliberately

- **Should closure cover non-SQL languages?** It should, and it will need a
  parser per language rather than a pattern, which is `caf`'s job rather than
  core's. Until then the honest answer is the warning.
- **Should a `call` entry point's closure be checked by name?** A service could
  declare its repository method names and have the scanner check that each name
  appears in the sources. That is a real improvement and it is not this
  packet's, because it starts to be inference.
- **Does `expects` belong in the declaration at all?** It is a token the
  checker looks for, which makes the assertion present. A stronger version would
  assert the *shape* of the absence rather than a substring of it, and that
  needs to run the language's test.
- **Should `identity` admit `current_setting('app.account_id')`?** The `()`
  requirement exists so a policy's identity call can be hoisted out of the row
  loop, and it rules out an idiom several services will reach for. It is the
  first thing to revisit and it is named in
  [**D41**](DECISIONS.md#d41-how-is-the-force-rule-declared-and-what-may-a-warning-mean-in-the-tenancy-checker).

None of the four is urgent enough to hold the format up, and all four are
cheaper to answer once a service has adopted it and can say which one bites.
