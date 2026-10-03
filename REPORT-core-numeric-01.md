# REPORT — core-numeric-01

**Packet:** core-numeric-01 · **Repo:** `cafaye/core` · **Branch:**
`worker/core-numeric-01` · **Base:** `d49e14c` · **Five commits**, worktree
green at **259/259**, `bin/prime` exits 0.

Read this first if you have not seen the packet. It has three halves: **the
measurement**, which came before any rule and is the packet's first deliverable;
**the check**, with one failure-severity rule and two warnings and one rule
deliberately not enforced; and **the adopter run**, which found six real defects
in the fleet's own OpenAPI documents.

---

## 1. Why this packet exists, in one sentence

cafaye has one contract and six languages reading it, and **JSON.stringify in
TypeScript rounds every number through an IEEE-754 binary64**. A Go service that
writes `9007199254740993` produces a document TypeScript cannot represent —
Python's `int` and Ruby's `Integer` are fine — so nothing fails, nothing logs,
and the value is wrong. That is precisely what a contract layer exists to
prevent, and nothing in core's checker prevented it.

## 2. THE MEASUREMENT — before any rule existed

Produced by `harness/bin/numeric-check --survey`, which is a tool rather than a
claim. The seven service specs are measured from the fleet checkout beside this
worktree, by static reads only.

| | core's `schemas/` | the 7 service OpenAPI specs |
| --- | --- | --- |
| numeric positions | **31** | **66** |
| numeric enums | **2** | **1** |

Core's 31 positions, bucketed:

| bucket | count | what it means |
| --- | --- | --- |
| bounded below the float64 range | 9 | has a `maximum` under 2^53 — safe by declaration |
| unbounded, bounded in practice | 19 | no `maximum`, but a count or an amount that cannot reach 9×10^15 |
| `RULE numeric.float` | 2 | `slo.objective`, `slo-windows.factor` — both ratios |
| union permitting number | 1 | `event-envelope`'s opaque `data`, which merely *permits* number |

**The number that decided every severity in this packet: `numeric.float64-unsafe`
fires on ZERO of core's 31 positions.** No field declares a maximum at or past
9007199254740992, and no unbounded integer carries an identity name.

So the honest answer to the brief's question — "if the answer is *zero
violations*, that is a finding worth stating plainly" — is: **core's own contract
surface is clean, and the rule is therefore cheap.** One rule can be a *failure*
because it costs nothing to keep, and a rule that fires on every existing field
is a rule that is disabled within one release, which leaves the fleet with NO
check rather than an incomplete one. That argument is
[`REPORT-core-negative-01.md`](REPORT-core-negative-01.md) §5's, reached
deliberately and not by accident.

## 3. The check, and the three decisions in it

`harness/numeric_check.py`, wrapped by `harness/bin/numeric-check`, run by
`bin/prime` against `schemas/` on every invocation. Exit `0` conforms, `1`
failures, `2` the check could not happen.

| rule | severity | core | fleet | why |
| --- | --- | --- | --- | --- |
| `numeric.float64-unsafe` | **FAILURE** | 0 | **6** | fires on 6 of 97, and 4 are `created`/`byte_size`/`iat`/`exp` |
| `numeric.float` | WARNING | 2 | 0 | both are ratios — a ratio that cannot be a whole number is not a rounding bug |
| `numeric.enum` | WARNING | 2 | 1 | real cost, but failing a gate over a status code is how a gate is switched off |
| `numeric.unsigned` | **NOT ENFORCED** | 45 | — | see below |

**The rule has two triggers, and the distinction is the rule.** A *declared
maximum at or past 2^53* is a bug today, because the document already says the
value gets that big. *No maximum at all on a field whose name says it carries an
identity* is a bug because unbounded is only alarming where the ceiling is
reachable — a token count cannot plausibly reach 9×10^15, an `int64` `byte_size`
can, because the only thing bounding it is whatever the writer felt like putting
there.

**`numeric.unsigned` is not enforced, for two reasons and the second is the one
that decides it.** It would fire on 45 of 97 numeric positions, every one a count,
an amount in minor units or a status code — the fleet's own vocabulary. And it is
*structurally invisible in any document*: there is no unsigned integer type in
JSON at all, Go has no unsigned JSON, TypeScript has no unsigned number, and
Python's `bool` **is** an `int`. It is enforceable only in a service's own types.
The name is in the `notEnforced` ledger with the count, and the ledger prints on
**every run** — a surface this checker declined to rule on says so, or the silence
is indistinguishable from an unexamined surface.

**The two float fields, which the brief asked to be thought about rather than
pattern-matched.** `slo.objective` and `slo-windows.factor` are ratios, so the
reference's "cannot be reliably round-tripped" does apply but does not make them a
bug. `docs/numeric-conventions.md` states the convention: **a scaled integer**
(`objective_milli: {type: integer, minimum: 1, maximum: 1000}`). Sloth's
`prometheus/v1` block needs a fraction, so the *declaration* keeps one; what must
be an integer is anything a client reads and re-emits. **That rewrite is owed and
not done** — it changes two published schemas under the fleet's adopters, and
that is the manager's call. See [D43](DECISIONS.md#d43-is-a-value-that-one-language-cannot-represent-a-finding-and-where-do-the-numeric-vocabularies-live).

## 4. WHERE THE VOCABULARIES LIVE, and the test that keeps them from drifting

**A JSON Schema cannot ask whether a line of TypeScript holds an `int`.** It can
say `type: integer` and `maximum:`; it cannot ask whether a Go `uint64` survived a
JSON round trip, whether an enum is one a client may add to, or what a field
*name* means. So all four vocabularies live in the checker — the same reason
`harness/tenancy_check.py` keeps `RAISING_TOKENS` / `LIVENESS_TOKENS` /
`ABSENCE_TOKENS` there rather than in `tenant-isolation.schema.json`.

**The cost of that is duplication, and core's rule makes duplication a test.** Two
tests carry it:

- `test_the_float64_limit_is_stated_once_in_the_checker_and_agrees_with_the_doc` —
  2^53 is **one constant**; the first unrepresentable value is *derived* as `+1`
  rather than typed; no third literal is hardcoded anywhere in the module; and the
  integer appears in the checker, in `--explain`, and in the doc.
- `test_the_numeric_identity_names_are_declared_once_and_the_ledger_says_why` —
  `IDENTITY_NAME_TOKENS` is non-empty, duplicate-free, and every token appears in
  the doc, **because a service author must be able to predict what will be refused
  before writing the field**, not after.

## 5. THE ADOPTER RUN — six real defects, found by reading the fleet

`harness/` may not take a dependency or open a connection, so this decides from
static facts only. Run against the seven service OpenAPI specs in the fleet
checkout beside this worktree:

```
$ numeric-check --survey ../{billing,courier,darkroom,guard,identity,muse,pantry}/openapi/v1.yaml
$ numeric-check ../…  →  EXIT 1
```

**6 findings, all `numeric.float64-unsafe`, all unbounded integers on
identity-named fields:**

| service | field | what it is |
| --- | --- | --- |
| billing | `StripeEvent.created` | a Unix timestamp, unbounded |
| darkroom | `AssetVariant.byte_size` | an `int64` file size, unbounded |
| identity | `IntrospectionResponse.iat` | a JWT `iat` claim, unbounded |
| identity | `IntrospectionResponse.exp` | a JWT `exp` claim, unbounded |
| identity | `IntrospectionResponse.last_used_at` | unbounded |
| muse | `RouteResponse.created` | a Unix timestamp, unbounded |

Plus one warning: `guard`'s `Problem.status` is a **9-value numeric enum**
`[400, 401, 403, 409, 413, 422, 423, 429, 503]` — the reference's case exactly,
because adding a value breaks six closed unions at once.

**identity is the only service in the fleet with a `tenancy.yml`**, and it is
also the only one with three. That is not a coincidence to act on today, and this
packet does not act on it: **no mechanism changed**, so every adopter picks up
nothing new and needs no action. But a service's CI should now be able to run
`harness/bin/numeric-check openapi/v1.yaml` and get this answer, and 6 of 7
services would go red — which is the correct answer and a change to their
contracts, not to this checker.

## 6. Red proofs — every one run, every one named

`harness/tests/numeric_self_test.sh`, nine cases, all run:

| | cases | detail |
| --- | --- | --- |
| control | 1 | the conforming fixture, green **and warning-free**, first |
| breakages RED | 4 | declared maximum **at** 2^53; **one past** it; unbounded `byte_size`; unbounded `expires_at` |
| warnings GREEN | 2 | `numeric.float`, `numeric.enum` — named, exit code unmoved |
| green cases | 2 | the boundary **from the other side** (2^53 − 1); a malformed document reported as unread |
| not-enforced | 2 | `numeric.unsigned` stayed green **and** is in the ledger — against the fixture and against core's own 31 |

Every breakage names the finding **and the field**, so a red on `byte_size` cannot
read as a pass for `expires_at`. The green from the other side is load-bearing:
a rule that fired on any large maximum would fail it, and a rule that refused
every bounded integer would fail the control.

**`bin/prime`'s own red proof still passes** — 18 breakages, exit 0 — so no rule
added here has made a legal declaration illegal. `bin/prime` runs the *check* (a
fact about this tree, needed now) and CI runs the *red proof* as a step of its
own (assertions about the checker against copies of a twenty-line fixture), which
is the asymmetry `bin/prime`'s own header already argues and which
`docs/gate.md` says not to "fix".

**Three defects were found by RUNNING, not reading**, and all three are worth
naming because each is a shape other checks in this repo share:

1. `numeric_check.py` imported **PyYAML**. `harness/` may not take a dependency, and
   `test_the_harness_imports_nothing_outside_the_standard_library` — which walks
   every module that travels — was **RED on the commit that added the file**. The
   fix is core's own reader, `cafaye_contract.read_yaml`, so there is one YAML
   dialect in one directory rather than two.
2. `local name=$1 dst=$WORK/$name` expands `$name` **before** the first assignment
   takes effect under `set -u`. Every case in the red proof failed on a path that
   did not exist, which would have been a self-test reporting real failures about
   nothing.
3. The checker printed its `notEnforced` ledger **only under `--explain`**, so a
   surface the rule was deliberately silent about looked exactly like a surface
   nobody had examined — which is the defect the ledger exists to prevent.

## 7. What I did NOT check, and why

- **No line of any of the six languages.** The checker reads documents. That a Go
  `int64` became a TypeScript `number` is proved by that language's own typed
  client and tests. What this proves is narrower and is the point: that the
  *contract* did not invite it.
- **Nothing live.** No Postgres, no service, no OpenAPI served over HTTP — a
  checkout's `openapi/v1.yaml` is what a service commits, so that is what was read.
- **The two SLO float fields are NOT rewritten**, and no schema changed in this
  packet. Deliberate: it changes two published schemas under the fleet's adopters.
  See D43 and the handoff.
- **`IDENTITY_NAME_TOKENS` is English.** It matches a field *name*, and 4 of the 6
  adopter findings were caught by it while 2 (`created`) were caught by a token
  that happens to match this fleet's spelling. A service that calls the same field
  `size_bytes` or `expires` gets no warning. That is a real gap, it is the same
  gap `REPORT-core-negative-01.md` §5 recorded for the tenancy vocabulary, and it
  is better admitted here than papered over: **the rule catches a fleet whose
  vocabulary it knows.**
- **`numeric.unsigned` stays unenforced**, so nothing in this repository stops a
  service declaring `type: integer, minimum: 0` where it meant `uint64`. It is
  first in the ledger with its measured count.
- **`schemas/` only, in the gate.** `bin/prime` checks core's own contract; a
  service's OpenAPI is checked by that service's CI, because core cannot reach a
  sibling checkout on a clean runner.
- **The service findings are not filed as tickets.** §5 is the evidence; whether
  a service's OpenAPI change is that service's packet is not this packet's call.

## 8. Decisions I did not take

- **Whether the 6 adopter findings become fleet work.** Recommended: yes, one
  line per service (a string, or a `maximum` under 2^53), and it is a change to
  their contracts.
- **Whether `slo.objective` becomes `objective_milli`.** Left open above.
- **Whether `numeric.float` is promoted to a failure.** One constant either way;
  promoting it means the SLO rewrite lands in the same commit or not at all.
- **Whether `probes.statusCode` stops being a numeric enum.** Two positions, both
  warnings, no adopter breakage; not worth a published-schema change on its own.