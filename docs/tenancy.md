# docs/tenancy.md — how a cafaye service declares its account boundary

The format is `tenancy.yml` at the service's repository root, written against
[`schemas/tenant-isolation.schema.json`](../schemas/tenant-isolation.schema.json),
checked by [`harness/tenancy_check.py`](../harness/tenancy_check.py), and proved
able to fail by [`harness/tests/tenancy_self_test.sh`](../harness/tests/tenancy_self_test.sh).
This document is the reasoning, including the things it will not do for you.

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

## The format

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

entryPoints:
  - id: asset-fetch
    operation: select        # select | update | delete | call
    subject: assets
    enforced:
      mechanism: query-filter # query-filter | bind-parameter | repository-method | middleware
      file: migrations/0001_assets.sql
      line: 22
    negative:
      asserts: absent        # const. the only legal value.
      expects: nil           # this language's spelling of nothing
      file: tests/tenancy_test.rs
      line: 34
```

Three things per entry point, and all three are required:

- **where the scoping happens** — `mechanism` from a closed vocabulary, plus the
  file and the line. `mechanism: bind-parameter` additionally names the
  parameter, because a query that still says `account_id = $2` while nothing
  passes `$2` any more is scoped on paper and unscoped in fact.
- **the negative assertion**, on the line it names, asserting absence.
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

`tenancy-check <repo>`, sixteen findings in
[`harness/tenancy_findings.json`](../harness/tenancy_findings.json), each with
the exact command that fixes it. Exit codes are the three the gate checker uses:
`0` clean, `1` at least one failure, `2` the check could not happen — and `2` is
never collapsed into `0`, because a check that could not find the declaration
has not checked the boundary.

**Thirteen failures**, in two groups. The three that say the declaration
describes nothing that is there:

| id | what it means |
| --- | --- |
| `tenancy.declaration-missing` | there is no `tenancy.yml` |
| `tenancy.declaration-unreadable` | it is not a YAML document core's reader accepts |
| `tenancy.schema` | it does not satisfy the schema |

And the ten that say the declaration no longer matches the code — which is the
whole contract:

| id | what it means |
| --- | --- |
| `tenancy.location-missing` | a declaration names a file this service does not have |
| `tenancy.line-missing` | a declaration names a line past the end of the file |
| `tenancy.scope-lost` | the entry point is still scoped, but not on the line it names |
| `tenancy.bind-missing` | the mechanism is `bind-parameter` and the parameter is not on the line |
| `tenancy.entry-absent` | declared, and the scanner can no longer find it — the scoping was dropped |
| `tenancy.undeclared-entry` | the scanner found account-scoped access nobody declared |
| `tenancy.denial-missing` | the negative assertion is not on the line the declaration names |
| `tenancy.denial-refuses` | the declaration answers cross-tenant access with a refusal |
| `tenancy.honest-zero` | the service declares no scoping and has account-scoped code |
| `tenancy.enumeration-empty` | the service says it scopes by account and declares no way it does |

**Three warnings, and none of them moves the exit code.** All three are the same
claim — *this machine cannot answer that question*:

| id | what it means |
| --- | --- |
| `tenancy.enumeration-partial` | the scanner could not classify every site; the enumeration is **not** proven closed |
| `tenancy.scan-narrowed` | a declared source path is not there, so the scan read less than declared |
| `tenancy.scope-key-unused` | no statement the scanner can read carries the declared key |

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

The five entries in `harness/tenancy_findings.json`'s `notEnforced` list are the
honest inventory, and the two worth stating here are these.

**The negative assertion is read, not run.** `tenancy.denial-missing` proves the
assertion is *written* — a second account fixture, an absent-shaped result, at a
line a reader can open. Running darkroom's suite needs its container and its
Postgres; running courier's needs a mix database. A checker that started
containers to see whether an isolation test passed would be red on a laptop and
green on CI depending on what happened to be running, which is the defect
`gate.requirement-unproven` already exists to name. Running the test is the
gate's job, in the service. This is a real gap and it is the same one MD12
names: a test that is written and never run reads exactly like a test that
passes.

**`enforced.line` is the only place the scoping happens.** The checker reads one
line and asks whether it carries the key. A statement that scopes in a CTE, a
subquery, a view, or a repository method three layers down is scoped, and this
checker can be pointed at the wrong one line of it — which is why `call` exists,
and why a service with two enforcement points declares two entry points.

The other three — completeness for a language the scanner cannot read, the
account-scoped code being all inside `scope.sources`, and the line's exactness —
are in the JSON with their reasoning.

## Adopting it in a service

1. Write `tenancy.yml` at the root. Start from
   [`examples/valid/tenancy.account-scoped.yml`](../examples/valid/tenancy.account-scoped.yml)
   — or the honest zero in
   [`examples/valid/tenancy.honest-zero.yml`](../examples/valid/tenancy.honest-zero.yml)
   if the service holds no customer rows. Do not skip step 2.
2. **Write the negative assertion first**, then point `negative.file` and
   `negative.line` at it. Two account fixtures and one assertion per entry
   point, asserting absence. This is the deliverable; `enforced` is the claim.
3. `tenancy-check .` and fix what it names. A Go or Elixir service will get
   warnings; that is the expected verdict, not a failure to fix.
4. Add it to the gate once it is green. Until then it is a second thing to
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

**Every one of the thirteen failure-severity findings has a breakage naming
it**, and `test_every_tenancy_finding_is_proved_able_to_go_red` in
[`tests/test_specs.py`](../tests/test_specs.py) is what keeps that true: a
finding added without a breakage is red rather than shipped untested. That
assertion is the reason the four above exist — they were the four that did not,
and every repository in the fleet was about to hit them.

Three cases assert a **warning stays green**: the unreadable-language service, a
declared source path that is not there, and a key nothing matches. All three
exit `0`. Two green cases assert the report *names what it cannot see*, because a
checker that printed nothing at all about a service it cannot read would pass
those too.

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

None of the three is urgent enough to hold the format up, and all three are
cheaper to answer once a service has adopted it and can say which one bites.
