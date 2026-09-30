# core-18 — `compose.postgres-pin`, and the ceiling is nine of eleven

**Packet:** core-18-pgpin · **Branch:** `worker/core-18-pgpin` · **Not pushed.**
**Suite:** 212/212 passed under both entry points (`bin/prime` and
`bin/prime --pytest`), floor raised 196 → 212. **Harness self-test:** 41
breakages red naming their rule, 4 warning cases green, 4 controls green.
**Gate checker red proof:** 18 red, 7 warning, 0 skipped. **`--prove`:**
0 failures, 1 warning.

---

## The finding that changed the packet

The brief said the fleet was uniform, and DEBT.md D24 records it as uniform, and
instructed me to make the rule a hard failure **because** the ceiling was zero.
I measured it before writing the rule. **It is not uniform, and the ceiling is
two, not zero.**

| Repository | Declaration | Reference | |
| --- | --- | --- | --- |
| billing | `docker-compose.yml`, `ci.yml` `services:` | `postgres:17-alpine` | ✅ |
| courier | `docker-compose.yml`, `ci.yml` `services:` | `postgres:17-alpine` | ✅ |
| darkroom | `docker-compose.yml`, `ci.yml` `services:` | `postgres:17-alpine` | ✅ |
| muse | `docker-compose.yml` | `postgres:17-alpine` | ✅ |
| identity | `docker-compose.yml` | `postgres:17-alpine` | ✅ |
| identity | `ci.yml` `services:` | **`postgres:17.11-alpine`** | ❌ |
| parlor | `e2e/docker-compose.yml` | `postgres:17-alpine` | ✅ |
| kit | `templates/compose/docker-compose.yml` | **`postgres:${KIT_POSTGRES_TAG:-16.6-alpine}`** | ❌ |

**Nine of eleven.** Both failures are real, and neither is a typo:

- **identity drifts inside one repository.** Its compose floats at `17-alpine`
  and its CI pins `17.11-alpine`, and its own CI comment says so in four lines —
  "docker-compose.yml still floats at `17-alpine`, so the dev stack and CI can
  drift onto different minors". A developer and a runner are on different
  database builds **today**. The fix is a decision with a cost: move CI to
  `17-alpine`, or pin compose to `17.11-alpine`. Not core's call.
- **kit's template defaults to 16.6.** A developer running `bin/dev` gets
  postgres 16.6 unless they set `KIT_POSTGRES_TAG`. The rule reads the
  `${VAR:-default}` default, because the default is what a developer with nothing
  configured gets — which is why that form is resolved rather than skipped.

**I did not soften the rule.** A severity chosen to make today's tree green is a
warning wearing a rule's clothes. Nothing adopts the harness yet (it deliberately
migrates no service), so **no build turns red today**; these two are what a
service finds on adoption. That is the desired shape for a rule that lands after
adoption — but the honest sentence is "nine of eleven", not "the fleet is
uniform", and
`test_the_scan_reads_the_real_fleet_and_its_result_is_recorded_here` holds the
measurement so the two go red together when a repository is fixed.

## What a service that legitimately needs another major does

It writes **`postgres-pin-exceptions.yaml`** at its root. Declared, never
inferred:

```yaml
exceptions:
  - file: docker-compose.yml
    image: postgres:16-alpine
    reason: >
      One legacy reporting replica, retired with the 2026-Q4 data-store
      migration. It is the only database container here.
    owner: platform
    until: "2026-12-31"
```

Matching is on the **exact path and exact reference** — no wildcard, because a
blanket exemption is the thing a rule exists to prevent. Five properties, all
findings:

1. A missing `reason`, `owner` or `until`.
2. An exception for the tag core **already declares** — grants nothing today and
   hides the next change to `POSTGRES_TAG` behind a line that looks reviewed.
3. An `image` this rule does not decide (`redis:…`).
4. A `file` that is not a path.
5. **An entry failing any of the above does not GRANT** — reported *and* inert.
   A suppression nobody can review must not suppress, so the pin it was written
   for stays red and the finding names the missing field. Reporting an entry and
   honouring it at once is the one outcome a declaration mechanism must never
   produce.

`until` is required and **never compared to a date.** A rule whose answer depends
on the day it runs is not a rule; the harness never resolves a `$ref` over the
network for the same reason. A horizon is a promise to a reader.

## What the rule reads, and what it deliberately does not

**Executable declarations only**: an `image:` key in a compose file or a
workflow's `services:`, and a `docker run` line in a shell script.

**Prose is excluded, and it is the largest exclusion.** A `grep -r 'postgres:'`
over the fleet's own history finds `postgres:17` in six CHANGELOGs and
`postgres:18-alpine` in muse's — every one of them correct about when it was
written. A rule that read history would turn six changelogs red for being
accurate, and the fix a service owner reaches for is deleting the record. Same
reasoning as `OFFSET_PARAMETER_NAMES` being a named list, not a pattern.

**A DSN is not an image reference, and that is a credential-safety property.**
`postgres://user:pass@host/db` appears across this fleet and carries a password.
A scanner reading `postgres:` as a floating reference would print a **credential
into a build log** as the evidence for a finding. The tag pattern cannot begin
with `/`, so it cannot match, and
`test_a_dsn_is_not_a_postgres_image_reference` runs the reader over core's own
self-test scripts — which really do contain
`postgres://gate:should-never-be-printed@localhost:5432/gate`.

**Four shapes the rule refuses to compare**, each a finding: a digest with no
tag, a variable with no default, no tag at all, and `latest`. `postgres:17` gets
its own sentence — the major is right, the minor floats.

## Three defects I introduced and found by running it

Recorded because the rule is new code and each was a **false green**, which is the
failure this repository exists to prevent.

1. **The scan bound was silent.** The walk stopped *descending* at the depth
   bound, so a compose file three levels down was never *found* — the truncation
   warning could not fire, and a bound that could hide a pin was invisible. Found
   by moving a fixture's compose file down a directory and asking why the run was
   still green. **The walk is now unbounded and the *reading* is bounded**, which
   is the only shape in which the limit can be named. `compose.pin-scan-truncated`
   exists for it.
2. **A declared exception matched nothing.** It compared against the on-disk path
   while entries spell `docker-compose.yml`. A suppression nobody can see is not
   suppressing anything, and the pin stays red with no way to tell why. The
   *conforming exception fixture* found this — a green state a rule with a broken
   exception path could not produce, which is why that fixture is a control.
3. **`postgres:17-alpine@sha256:…` was silently skipped.** Legal docker syntax,
   and the first version returned `None` — a silent pass reported as a decision. It
   now keeps the tag, so a digest with the declared tag passes and one without it
   is reported against the tag.

Also found: the script scanner stopped at `--rm` — an option, not the end of
them — and would have found **zero** pins in a file that declares one. It no longer
tries to parse options: `parse_image_reference` is anchored, so `VAR=postgres:16`
and `postgres://…` are not image references and every word after the verb can be
examined. A narrower rule that reads nothing is worse than no rule, because it
reports that it checked.

## Two decisions I did not make alone

- **`POSTGRES_TAG` is a root file, not a `schemas/` file.** Putting it under
  `schemas/` would have been more in the spirit of "a rule not in `schemas/` is
  not a cafaye rule" — and it would have **changed `contract_digest`**, turning
  every pinned service red for a file none consumes. `VERSION` set the precedent;
  the cost is that `POSTGRES_TAG` is covered by a test and not by
  `--expect-digest`, stated in the doc rather than glossed. **Manager's call if
  the digest argument is wrong** — it is a one-file move.
- **core has no compose file**, so "core's own compose as the first conforming
  example" is delivered as `examples/valid/`-adjacent fixtures rather than a
  compose file core does not need. Inventing a database core does not run to
  demonstrate a rule about databases would be a worse example than a fixture.

## A CI step that was failing on every run

Not mine, found by reading the step I had to edit.
`.github/workflows/ci.yml`'s "the self-test said what it did" step greps the
log for `all N breakages went red`; the footer has **always** printed
`PASS: self_test — N breakages went red naming their rule`. So `claimed` was
empty, `[ -z "$claimed" ]` was true on **every** run, and the step **exited 1** —
blaming a self-test that had just succeeded. The self-test's own count was
correct throughout.

Fixed, and pinned by
`test_the_ci_self_test_step_reads_the_phrase_the_footer_prints`, which reads the
step's own `run:` block **with shell comments stripped** — writing down what was
wrong put the broken phrase into the step's comments, and a check a comment can
satisfy is not a check (kit's rule, hit twice in one packet).

The same step required **exactly one** control (`-ne 1`) and this packet adds two.
It now requires ≥1 **and** asserts the first control precedes the first breakage.
Order is the property it was for: a control that runs after a breakage has not
controlled it. A check that hard-codes a count fails on every addition, and the
2am fix is to delete the assertion.

## Measured, not guessed

| Claim | Measured how |
| --- | --- |
| 9 of 11 fleet declarations conform | `postgres_references()` over the workspace; asserted in `test_specs.py` |
| The harness reads every fleet compose file and workflow | 19 files, 19 read, 0 refused |
| `*.sh` alone would read zero of the fleet's real scripts | `bin/prime` et al. have no extension; `bin/` is now scanned |
| Every image reference is at an `image:` key | 16 `image:` keys walked across 8 repositories |
| The pin rule can be neutered without `bin/prime` noticing | **rule body mutated (every reference matches) → 208/212.** Restored |
| Removing the call site | **→ 205/212.** Restored |

## Files

**New:** `POSTGRES_TAG`, `docs/postgres-pin.md`, five fixtures
(`conforming-postgres`, `conforming-postgres-exception`,
`nonconforming-postgres-divergent`, `-undeclared`, `-exception`).
**Changed:** `harness/cafaye_contract.py` (+1016: the rule, the reader, the
exception mechanism, `POSTGRES_TAG` reader), `harness/rules.json` (36 → **38**
rules, 3 → **4** warnings, 3 new `notEnforced`), `harness/tests/self_test.sh`
(breakages 41–44, warning 45, two new controls), `tests/test_specs.py` (+843,
section 8), `gate.yml` (floor 196 → **212**), `docs/contract-harness.md` (rule
table, counts, two new sections), `CHANGELOG.md`, `.github/workflows/ci.yml`.

## Owed, and not mine

- **identity and kit are red on adoption** (§ above). Both need their own packet;
  I did not edit a service repository.
- **Digest coverage.** `POSTGRES_TAG` is not in `contract_digest` (§ above).
- **Open decisions: none introduced.** The exception mechanism is decided, the
  digest trade is recorded and reversible.