# REPORT — core-numeric-enum-53-01

**A 53-bit integer behind an `enum` gets a warning, not a refusal.**

Branch `worker/core-numeric-enum-53-01`. Four commits. `bin/prime` green,
**272/272**.

Everything below was printed. Where a number appears, it is a number this
session's runs produced; where a table is a measurement, it says how it was
measured. There is one place (§6) where I name a gap I chose not to close, and
one place (§7) where I name work I chose not to build.

---

## 1. The gap, confirmed rather than assumed

`numeric.float64-unsafe` decided itself from two things: `maximum`, and a
field NAME in `IDENTITY_NAME_TOKENS`. `walk()` files a node that is both
`type: integer` and an `enum` in **two** lists — it goes into `positions`
because `"integer" in kinds`, and into `enums` because the members are all
ints — and it carries neither the members nor the name into the position. So the
position branch saw `maximum: None` and a name that is not an identity token,
and the enum branch only ever produced `numeric.enum`.

Measured on the **unedited** tree at `cdfa528~1`, one property per document,
through `python3 harness/numeric_check.py`:

| the document said | the checker said | exit |
| --- | --- | --- |
| `"shard_id": {"type": "integer", "enum": [0, 1, 9007199254740993]}` | `numeric.enum` **warning** | **0** |
| `"shard_id": {"type": "integer", "enum": [-9007199254740993, 0]}` | `numeric.enum` **warning** | **0** |
| `"shard_id": {"enum": [0, 9007199254740993]}` (no `type` at all) | `numeric.enum` **warning** | **0** |

`9007199254740993` is `2**53 + 1`. `JSON.stringify` in TypeScript rounds it, so
every `Number()` round trip through a generated client returns `9007199254740992`.
The only finding on the node was about **evolution** — "adding one is NOT a
compatible change" — and said nothing about the value being unrepresentable
today.

### The packet asked me to measure point 3 rather than assume it

> Measure whether `float64_unsafe` as written would catch
> `enum: [-9007199254740993, 0]`, because I believe it would not.

**It would not**, and the reason is structural rather than a subtle sign bug:
the rule reads `maximum`, which is **one number**, and an enum is a **set**.
There is no comparison to get wrong — there is no comparison at all. That is
why the fix is a magnitude predicate over the members rather than a change of
operator on an existing one (§3, decision 3).

---

## 2. The four red/green cases, measured

Nine documents, one property each, through
`python3 harness/numeric_check.py <dir>` on the merged tree. The
`notEnforced` ledger prints on every run and is elided below; nothing else is.

### 2.1 `enum: [0, 1, 9007199254740993]` → **red**, exit **1**

```
numeric.float64-unsafe   failure  DIR/openapi.json
    #.properties.shard_id
      enumerates 9007199254740993, which a binary64 cannot hold exactly — it
      parses back as 9007199254740992. A value at or past 9007199254740993 is
      exact in Go, Python and Ruby and is already wrong in TypeScript, by one.
      It must be a string.
numeric.enum             warning  DIR/openapi.json
    #.properties.shard_id
      is a numeric enum [0, 1, 9007199254740993]. Codegen closes it into a
      union in every language at once, so adding a value is a breaking change
      in six of them — the reference calls numeric enums out for exactly this,
      and adding one is NOT a compatible change.

numeric_check — 1 failure(s), 1 warning(s), over 1 numeric position(s) in 1 document(s).
exit=1
```

Both findings, on one node, at the severities each is owed.

### 2.2 `enum: [0, 1, 9007199254740992]` — exactly `2**53` → **not red**, exit **0**

```
numeric.enum             warning  DIR/openapi.json
    #.properties.shard_id
      is a numeric enum [0, 1, 9007199254740992]. Codegen closes it into a
      union in every language at once, so adding a value is a breaking change
      in six of them — the reference calls numeric enums out for exactly this,
      and adding one is NOT a compatible change.

numeric_check — 0 failure(s), 1 warning(s), over 1 numeric position(s) in 1 document(s).
exit=0
```

`numeric.float64-unsafe` is **absent**. The enum is still seen — `numeric.enum`
is printed and the exit code is 0 — so "not red for this rule" did not become
"not looked at". `2**53` is the last integer a binary64 holds exactly:
`JSON.stringify(2**53)` returns `"9007199254740992"` and `JSON.parse` of that
returns `2**53`. An off-by-one here would refuse a document that is correct, and
it would be invisible until a real client silently rounded.

### 2.3 `enum: [-9007199254740993, 0]` → **red**, exit **1**

```
numeric.float64-unsafe   failure  DIR/openapi.json
    #.properties.shard_id
      enumerates -9007199254740993, which a binary64 cannot hold exactly — it
      parses back as -9007199254740992. A value at or past 9007199254740993 is
      exact in Go, Python and Ruby and is already wrong in TypeScript, by one.
      It must be a string.
numeric.enum             warning  DIR/openapi.json
    #.properties.shard_id
      is a numeric enum [-9007199254740993, 0]. Codegen closes it into a
      union in every language at once, so adding a value is a breaking change
      in six of them — the reference calls numeric enums out for exactly this,
      and adding one is NOT a compatible change.

numeric_check — 1 failure(s), 1 warning(s), over 1 numeric position(s) in 1 document(s).
exit=1
```

The magnitude test, with the sign preserved in the message so the reader can
find the member. Its mirror, `enum: [-9007199254740992, 0]`, is **green, exit
0**, `numeric.enum` only — so a branch written as `value > LIMIT` fails §2.3,
and one written as `abs(value) >= LIMIT` fails §2.3 **and** the mirror.

### 2.4 A string enum, an enum of floats, an enum with one non-integer member → **unchanged**

| document | findings | exit |
| --- | --- | --- |
| `{"type": "string", "enum": ["0", "9007199254740993"]}` | **none** | 0 |
| `{"type": "number", "enum": [1.5, 2.5]}` | `numeric.float` warning | 0 |
| `{"type": "integer", "enum": [1, "two"]}` | **none** | 0 |

The `all(_is_int(v) for v in values)` guard in `walk()` is what keeps these out
of `enums` at all, and it was **not** widened. The float enum is the proof that
"unchanged" means unchanged: it still says `numeric.float`, which is what it
said before this packet, and it is still exit 0.

### 2.5 Two cases the packet did not ask for

**An enum with no declared `type`** — `{"enum": [0, 9007199254740993]}` — is
**red, exit 1**, and the run's own summary line reads:

```
numeric_check — 1 failure(s), 1 warning(s), over 0 numeric position(s) in 1 document(s).
```

**Zero numeric positions.** That is the measurement behind the design decision
in §3: `walk()` only files a node in `positions` when its `types` include
`integer` or `number`, so this node is in `enums` and not in `positions`, and no
widening of a position-shaped rule could ever have seen it.

**A node with both a crossing maximum and a crossing enum**:

```
numeric.float64-unsafe   failure  DIR/openapi.json
    #.properties.shard_id
      declares maximum 9223372036854775807, at or past the float64 exact range
      9007199254740992. A value at or past 9007199254740993 is exact in Go,
      Python and Ruby and is already wrong in TypeScript, by one. It must be a
      string.
numeric.enum             warning  DIR/openapi.json
    #.properties.shard_id
      is a numeric enum [200, 9007199254740993]. …

numeric_check — 1 failure(s), 1 warning(s), over 1 numeric position(s) in 1 document(s).
exit=1
```

**One** `numeric.float64-unsafe`, and it is the maximum's message.

---

## 3. The three decisions, and why

Full argument in [DECISIONS.md D44](DECISIONS.md#d44-is-an-enum-member-past-the-float64-exact-range-a-failure-or-a-warning).
The short versions:

### 1. Severity: FAILURE, sharing `numeric.float64-unsafe`'s id

An enum is a **stronger** statement than a maximum, not a weaker one. A maximum
*bounds a range*: it says how big the value may get, and a writer that stays
inside it produces nothing a reader cannot hold — the hazard is real but
prospective. An enum *enumerates the complete set of legal values*, so a member
past the limit is not a possibility the contract tolerates; it is a value the
contract **requires**, and every one of those values is a value a JavaScript
client silently rounds. The distinction this checker draws everywhere is *can
this value cross the wire wrong*, and this one can.

It shares the id rather than becoming a fifth rule so that one grep still finds
every value that crosses the wire wrong, whatever shape declared it.
`numeric.enum` stays a WARNING and stays a **separate** finding: the two are
about different things — a value wrong today versus what adding a value costs
later — so one node carries both. That is asserted in two places
(`expect_red_with_warning` in the red proof, and the suite's
`test_an_integer_enum_carrying_a_53_bit_value_…`).

**Measured, the new trigger fires on nothing that exists.** Per service spec,
on the sibling checkouts, through this checker:

| spec | exit | `numeric.float64-unsafe` | of which from an enum |
| --- | --- | --- | --- |
| `billing/openapi/v1.yaml` | 1 | 1 | **0** |
| `courier/openapi.yaml` | 0 | 0 | **0** |
| `darkroom/openapi/v1.yaml` | 1 | 1 | **0** |
| `identity/openapi/v1.yaml` | 1 | 3 | **0** |
| `muse/openapi/v1.yaml` | 1 | 1 | **0** |
| `pantry/openapi/v1.yaml` | 0 | 0 | **0** |
| `core`'s own `schemas/` | 0 | 0 | **0** |

Six fleet findings — the same six D43 recorded in June — all six from branches
that already existed, and **zero** from the new one. Core's own surface is
unchanged: `0 failure(s), 4 warning(s), over 31 numeric position(s)`. A
failure-severity rule that fires on zero of what exists can be a failure; one
that fires on everything is switched off within a release and leaves the fleet
with no check at all.

### 2. Do not double-report: the **maximum** reports and the **enum** yields

`check()` walks `positions` first and remembers each `(source, path)` it
reported; the enum loop skips one already in that set. Same rule, same
`reported` set, and the same reason as `harness/reserved_check.py`'s
`_cross_service_pairs`: a finding printed twice reads as two problems where
there is one.

The **maximum** wins because it is the branch that already existed.
Suppressing it is the edit that can lose a finding nobody re-reads; suppressing
a **new second copy** of an id that was already there cannot. It is also the
cheaper direction to test: the "suppress a new copy" path has nothing left to
get wrong, while "suppress the old one" would need the position loop to learn
about enums it does not carry.

Asserted three ways: `expect_red_once` (the count is `grep -c`, not a
substring — a message that merely *mentioned* both would satisfy a substring
check while still printing twice), the needle `declares maximum`, and the
suite's `len(numeric_findings(...)) == 1`.

### 3. Where the check lives, and magnitude

**In `check()`, not in `float64_unsafe()`.** Measured reason, in §2.5: an
untyped enum is in `enums` and not in `positions`, so a position-shaped rule
could never reach it however wide it grew. `check()` is where the two lists meet.

**Magnitude, not sign.** `abs(value) > FLOAT64_EXACT_LIMIT`, in a named
function `_unrepresentable()`. Named rather than inlined because the whole
argument is that a **set has no sign**, and a signed comparison answers "is the
largest member too big" — which is a question about a `maximum`.

### The boundary differs from the maximum branch by exactly one value, on purpose

`float64_unsafe()` fires at `maximum >= FLOAT64_EXACT_LIMIT`. The enum branch
fires at `abs(value) > FLOAT64_EXACT_LIMIT`. That is a real asymmetry and I am
not going to paper over it:

- `2**53 = 9007199254740992` **is** exactly representable. `JSON.stringify` of
  it returns `"9007199254740992"`; `JSON.parse` of that returns `2**53`.
- An enum member is a **value**. If every member is exact, no reader can ever be
  handed one it cannot hold, and there is nothing left to refuse.
- A `maximum` is a **range bound**, so the checker treats its endpoint landing
  on the last exact integer as worth a look: a document that declares
  `maximum: 9007199254740992` is declaring that values this big are legal, and
  the next edit is `+ 1`. That branch is one value conservative. It is also the
  published rule, `docs/numeric-conventions.md` states it, and case (1) of the
  red proof pins it.

Making both `>` would be *more* consistent and would refuse fewer correct
documents. I did not do it because it is a change to a published rule with an
existing red proof behind it, which is a different packet's claim. Making both
`>=` would refuse a correct document, which §2.2 shows is exactly the off-by-one
the packet warned about. The asymmetry is mitigated in three places instead: it
is stated in `docs/numeric-conventions.md`, in `enum_float64_unsafe()`'s
docstring, and in D44 — and cases (11) and (13) are **greens sitting exactly on
the boundary from both directions**, so a future edit to either operator goes
red.

---

## 4. The red proof, and the mutation that removes only the new branch

`harness/tests/numeric_self_test.sh` cases **(10)–(18)**, hanging off a header
entry that says the enum is a third way in rather than a fourth rule. On the
merged tree:

```
numeric_self_test — counts, reported separately so a green cannot hide one:
  breakages that went RED and named their finding : 10
  warning cases that stayed GREEN                 : 3
  green cases, each of which named what it cannot check : 6
  not-enforced cases that stayed GREEN and in the ledger : 2
  controls (a conforming surface, unbroken)        : 1
  SKIPPED                                           : 0
exit=0
```

Ten breakages, where the unedited script had `grep -c "^expect_red '"` = **4**
(there is a fifth `expect_red` in the file's own header comment, which is not a
case). Every mutation in the group is **confined
to the `enum` and the `type`**: no `maximum` is added anywhere except in (15),
which is about the count, and no identity-shaped name is involved at all. That
confinement is what makes the group a proof about the enum path rather than a
sixth spelling of (1)–(5).

### The mutation

Copying `harness/` aside and deleting the enum block from `check()` — leaving
`float64_unsafe()`, the maximum branch and `numeric.enum` untouched — then
`ast.parse`-ing the result so a syntax error could not pass for a mutant:

| case | on the mutant |
| --- | --- |
| the control | **PASS** — green and warning-free |
| (1), (2), (3), (4), (5) | **PASS** — all five existing breakages |
| green case 1, warning cases 1 and 2 | **PASS** |
| **(10)** member one past the limit | **FAIL** — expected exit 1, got 0 |
| the node is both a failure and a warning (case 10's `expect_red_with_warning`) | **FAIL** — expected exit 1, got 0 |
| **(12)** large NEGATIVE member | **FAIL** — expected exit 1, got 0 |
| **(14)** enum with NO declared type | **FAIL** — expected exit 1, got 0 |
| (11), (13) the boundary greens | PASS |
| (15) both maximum and enum, and its `expect_red_with_warning` | PASS |
| warning 3, green cases 4 and 5, both not-enforced, unreadable | PASS |

`numeric_self_test` exit **1** on the mutant; `6 breakages` counted against
`10` on the merged tree.

**Case (15) still passing is the honest half of that table.** It exercises the
maximum branch, which the mutant kept, so it cannot detect this removal. Four
cases detect it, and all four have an enum as their only trigger — which is the
opposite of the mistake the packet named. A mutation that reds the *existing*
`numeric.float64-unsafe` cases would have proved nothing here, and (15) is the
proof that I checked.

**My first mutant proved nothing, and I am recording that rather than only the
fixed one.** Replacing the block with `if False:` and leaving the body as a
comment is an `IndentationError`, and that run went red on **every** case
including the control and including (1)–(5), which have nothing to do with
enums. That is a red about my mutation. It is the same failure mode as a test
that goes red because the JSON is malformed, and it is why the mutant is
re-made, re-parsed and re-measured.

### Two faults injected into the suite, to show the new assertions bite

| fault injection | result |
| --- | --- |
| the negative-member mutation replaced by a copy of the positive one | `269/272 passed`, `test_the_numeric_red_proof_and_its_header_name_the_same_rules_in_both_directions` **FAIL** |
| one case's expected id typo'd to `numeric.float64-unsaf` | `269/272 passed`, the same test **FAIL** |

The second is why the bidirectional check exists. The pre-existing
`test_every_numeric_finding_is_proved_able_to_go_red_and_CI_runs_the_proof`
looks only for ids the checker **emits** being present in the script; it cannot
see an id **in the script** that the checker cannot emit, which is a case red
for the wrong rule and green for the right one, forever.

---

## 5. The floor

`core/gate.yml`'s `minimum` was **270**. The suite printed, with the ratchet
itself red:

```
271/272 passed
```

**270 → 272.** The number in the denominator is the count; it was not computed
by adding. The two tests added are the enum predicate asserted in both
directions, and the header-against-cases check in both directions.

### The header check, both directions

`test_the_numeric_red_proof_and_its_header_name_the_same_rules_in_both_directions`
asserts three things:

1. the header's rule list **equals** `FINDING_IDS | NOT_ENFORCED` — a rule the
   header never mentions is one whose severity a reader cannot predict, and a
   header entry nothing proves is a promise nobody keeps;
2. every id named by an `expect_*` **call** is an id the checker can emit;
3. every id in the inventory is named by a **call**.

The ids are harvested from the calls, not from the file, because a rule named
only in a comment satisfies a substring search and proves nothing — which is
exactly what a comment is. The enum branch is the case most exposed to this: it
added **no finding id**, so no inventory moved and nothing else would have
noticed a header entry with no case beside it.

### Two helpers the new cases needed, and could not be faked with

- `expect_red_once` — asserts the **count** of a finding id on one node, via
  `grep -c`, because a message that merely mentioned both a maximum and an enum
  would satisfy a substring check while still printing twice.
- `expect_red_with_warning` — asserts a run is red **and** a second finding is
  printed. `expect_warn` requires exit 0, which a node that is also a failure
  never has; `expect_red` does not look for a second finding at all. So
  "one node, two true statements" was unreachable until this helper existed,
  which is precisely how a packet adds a finding to an existing node and
  silently suppresses the first.

### One defect in the red proof's own machinery, found by writing case (12)

`edit` claimed in its own comment that it "FAILS LOUDLY" on an unmatched
anchor. It did not. The script runs under `set -uo pipefail` **without** `-e`,
so `edit` on a line of its own reported nothing when the fixture had moved past
it — and case (15) anchored on a mutation the *previous* case had written
rather than on the control's own text. The only reason it went red was that the
case after it could see a green. `edit` is now a wrapper that turns its
primitive's exit status into a failure, which matters most for the **green**
cases: an `expect_green` whose mutation silently did nothing passes for the
wrong reason, and "the boundary is quiet" is exactly the kind of claim that has
to be earned.

The same class of defect, one function over: `grep -q "$needle"` reads a needle
that **starts with a dash** as a list of options, so `grep -q
"-9007199254740993"` cannot match a message that says exactly that. Case (12)'s
needle is a negative member. The checker said `-9007199254740993` and the helper
reported that it had never said it — a false accusation about a checker that
was right. Every needle now reaches grep as `grep -q -e "$needle"`.

---

## 6. A gap I measured, named, and deliberately did not close

**`{"type": "integer", "maximum": -9007199254740993}` is silent today**, and was
silent before this packet. Measured on the unedited tree: no findings, exit 0.
`float64_unsafe()`'s comparison is `maximum >= FLOAT64_EXACT_LIMIT`, which is
signed, so a negative maximum past the exact range never reaches it.

I could have closed it with one edit — `abs(maximum) >= FLOAT64_EXACT_LIMIT` —
and I did not, for a reason worth writing down rather than discovering later:
that expression is `maximum >= FLOAT64_EXACT_LIMIT` **union** `maximum <=
-FLOAT64_EXACT_LIMIT`. So it closes the hole and opens a worse one: it fires on
`maximum: -9007199254740992`, which is exactly representable and which the enum
branch correctly stays silent on. It would trade a **documented** asymmetry for
an **undocumented** one, in a packet whose entire subject is an undocumented
asymmetry in the other direction.

Two further reasons, both smaller: it is a second trigger on a failure-severity
rule in a packet about the first, and a rule that fires on everything gets
switched off. The fix is one operator and it needs its own red proof; the honest
place for it is a packet that also decides whether the `maximum` branch should
become `>` and match the enum branch exactly — which is the change this packet
declined to make for the same underlying reason.

Recorded in D44 as alternative 5 and here. **Not built.**

---

## 7. Out of scope, written up rather than built

**`manifest.schema.json` should not be changed by this packet, and the larger
claim is worth stating.** A schema constraint could forbid 53-bit enum members
outright — `"not": {"enum": [...]}`-style, or a `maximum`-free assertion the
schema engine can decide. That is a *different and larger* claim than the one
this packet makes, for four reasons:

1. **It changes a published schema under the fleet's adopters**, and a schema
   change is a contract change; a checker change is not. Every other packet in
   this repository that changed `schemas/` says so in `CHANGELOG.md` under
   *breaking*, and D43 already carries one such change as the **manager's**
   call rather than a numeric checker's.
2. **It would make the value unpublishable rather than refused at review.** The
   two rules have different failure modes: a checker finding can be declined
   with a reason and a patch; a schema refusal is a hard error with no
   exception path, which D41 argues about at length for the tenancy checker.
3. **A JSON Schema cannot express the boundary the way the checker means it.**
   The checker's rule is about a *language* — that `JSON.stringify` rounds — and
   2^53 is a fact about TypeScript, not about a document. Putting the number in
   a schema turns a language fact into a format fact, which is precisely what
   D43's alternative 4 rejected.
4. **It would be a second statement of one constraint**, and this repository's
   rule is that duplication is a **test** — a test that would have to assert
   the schema's number and the checker's constant agree, forever, in both
   directions, for a number that already has one home.

**Recommendation: keep the boundary in the checker, and let a service's own
generated client be what proves its reader.** If a schema-level constraint is
wanted, it is worth a packet of its own whose first act is to measure what it
would do to the fleet's existing manifests — the same first act every packet in
this repository has taken.

---

## 8. The commits

| commit | what |
| --- | --- |
| `d9f2973` | the tests, the red-proof recipes, the `edit` fix, the fixture, the floor. Red: `271/272`. |
| `cdfa528` | `enum_float64_unsafe()`, the `check()` loop, `grep -e`, `--explain`, `--survey`. Green: `272/272`. |
| `f427cfb` | `docs/numeric-conventions.md`, D44, `CHANGELOG.md`. Green: `272/272`. |
| this one | this report. |

### Every assertion in this packet, and what it is

| claim | where |
| --- | --- |
| the predicate, in both directions, through the real CLI | `test_an_integer_enum_carrying_a_53_bit_value_is_a_failure_and_the_boundary_is_exact` |
| the red proof's header against its cases, both directions | `test_the_numeric_red_proof_and_its_header_name_the_same_rules_in_both_directions` |
| the enum branch under `-I -S`, named by the **member** not the id | `test_bin_prime_checks_the_numeric_surface_and_the_check_needs_nothing_core_does_not_ship` |
| one finding per node, on the shell side | `expect_red_once`, case (15) |
| both findings on one node, on the shell side | `expect_red_with_warning`, on cases (10) and (15) |
| the enum cases are confined to the enum | cases (10)–(18), each mutation asserted by text |
| a green whose mutation did not apply is not a green | `edit` |
| a needle that begins with a dash is a pattern, not options | `grep -q -e` |

### What is NOT proved, and I am not claiming it

- **No line of any of the six languages is read.** `harness/` reads documents and
  decides from static facts; a service's own typed client is what proves that a
  Go `int64` became a TypeScript `number`.
- **The checker is not run against the fleet's own manifests** — it runs against
  their OpenAPI specs, which is what it is pointed at. Seven specs read, none
  from a running service.
- **`max()` and `minimum` are still not handled for a range that is unbounded
  below.** A field with `maximum: 100` and no `minimum` can still carry
  `-10**30`, and nothing here sees it. That is the same shape as §6 and is
  named there rather than fixed here.
- **No finding id was added**, so `FINDING_IDS` still has three entries and no
  mirrored inventory needed editing — the new branch reuses `numeric.float64-unsafe`.
  That is also why §5's header check had to be written: a branch that adds no id
  moves no inventory, so nothing else in the repository would have noticed a
  header entry with no case beside it.