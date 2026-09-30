# REPORT — core-17: make `core:` mean something

**Branch:** `worker/core-17-pinversion` · **Not pushed. I created no tag.**
(A tag `v0.2.0` appeared mid-session, created by the repository owner at 22:42
naming `c63af27` — see §1. I did not create it, have not touched it, and my
commit is untagged.)

**Result:** `bin/prime` 176/176 · `self_test.sh` 28 breakages red · 
`core_version_test.sh` 21 passed / 0 failed / **0 skipped**, 4 breakages red ·
`gate_self_test.sh` 25 breakages red, 0 skipped.

---

## 1. Re-verification: most of the brief reproduced, two claims did not

The brief said *"re-verify all of this yourself before building on it. If it
does not reproduce, that is the finding."* Four of six reproduced exactly. Two
did not, and both mattered, so they are first.

### Did NOT reproduce: `identity` does not publish `account.created`

> *brief: "identity publishes `account.created`, the two-segment form 0.2.0
> explicitly forbids, under a `^0.1.0` declaration, and nothing reports it."*

**There is no two-segment event anywhere in the fleet.** `identity` publishes
`identity.account.created` — three segments, correct — at
`identity/internal/outbox/tenancy.go:46`. The bare string `account.created`
appears only in a *comment* at `identity/cafaye.yml:120` and in a docstring.

So the severity is **lower than the brief stated**: the drift is a
mis-declaration of `^0.1.0`, not a published contract violation. No service is
shipping an event type the schema forbids. The defect is real and the fix is
identical, but "identity publishes a forbidden event" is not a sentence I am
going to hand the manager. `identity`'s published set is
`identity.user.created`, `identity.oidc_client.created`,
`identity.oidc_client.revoked`, `identity.mfa.enabled`, `identity.mfa.disabled`,
`identity.api_key.created`, `identity.api_key.revoked` — all well-formed.

#### …and there is a worse, real defect in the same place

Having established the two-segment claim was false, I checked the whole
direction the brief was pointing at, and found something that *is* true:

```
published in Go (internal/, 12 types)   vs   declared in cafaye.yml (7 types)
```

**Five events `identity` publishes are not in its own manifest:**

| Event | In `exposes.events`? | Row in core's catalog? | Payload schema in core? |
| --- | --- | --- | --- |
| `identity.account.created` | no | yes | **no** |
| `identity.member.invited` | no | yes | **no** |
| `identity.member.removed` | no | yes | **no** |
| `identity.member.role_changed` | no | yes | **no** |
| `identity.member.accepted` | no | **no** | **no** |

Core ships exactly **one** payload schema for identity —
`schemas/events/identity/user/created.schema.json` — for twelve published types.
And `identity.member.accepted` appears in **none** of the three places: not in
the manifest, not in the catalog, not as a payload schema.

So the true defect in this area is not a malformed event type. It is that
**`exposes.events` is not a complete declaration of what a service publishes**,
which is the same class of problem core-17 exists to fix — a contract that does
not say what it means — one layer over. No core rule catches it, because every
rule reads the *manifest* and none of them reads a service's source. Fixing it
means a new rule and a new decision about reading another language's code, and
it is **not this packet's work**. Flagging it, not doing it.

### Did NOT reproduce: a tag now exists, and its release note repeats the false claim

At the start of this session `git tag -l` in `cafaye/core` was empty, as the
brief measured. It now contains one:

```
v0.2.0  ->  c63af27   tagged 2026-09-30 22:42:45 by Kaka Ruto
```

**I did not create it.** I ran no `git tag` command, and the tagger is the
repository owner; the timestamp is after my branch was cut. It names `c63af27`,
which is `master`'s tip and my branch's starting commit — so it is a correct
0.2.0 release of the pre-core-17 tree. **I have not touched it and will not.**
My commit is *not* tagged, and `VERSION` reads `0.2.0` to match it.

Flagging one thing about it, because it is published and it is wrong. The tag
message says:

> *"identity still publishes the two-segment `account.created`"*

That is the brief's claim, and it is false — see above. A service owner reading
that release note will go looking for a two-segment event that does not exist,
and will not find the five undeclared events that *do*. **The tag message
should be amended or followed.** That is the owner's call and not mine; I am
reporting it because I am the one who measured it.

It also cites `DEBT.md` D22, which carries the same claim in the same
"Measured, 2026-09-30" block. Same correction applies.

### Did NOT reproduce: the CI ref census

> *brief: "Of five CI workflows checking out `cafaye/core`, three use `ref:
> ${{ env.CORE_REF }}` and two use `ref: master`."*

Measured, across every `*/.github/workflows/*.yml`:

| Service | Mechanism | Ref |
| --- | --- | --- |
| `billing` | checkout | `ref: master` |
| `muse` | checkout | `ref: ${{ env.CORE_REF }}` — a pinned **sha** |
| `docs` | checkout | `ref: ${{ env.CORE_REF }}` where `CORE_REF: 'master'` |
| `guard` | **raw URL, not a checkout** | `raw.githubusercontent.com/cafaye/core/master/<schema>` |
| `pantry` | **vendir** | `vendir.lock.yml`, `ref: master` + recorded sha |

**Four workflows reference `cafaye/core`, three of them checkouts**; of those
three it is one `master` / two `CORE_REF`, not three / two. And `guard` is the
interesting one the brief missed: it is not a checkout at all, it fetches a
single schema over HTTPS, which is why it has no tree to point `--core` at and
why it is the most expensive service to migrate.

**This changes the finding for the better.** The brief implied `identity`,
`courier` and `guard` were being handed `master` content. In fact **only
`billing` pins `master` — and `billing` declares `^0.2.0`, so it is
consistent.** The three services that declare `^0.1.0` are `identity`,
`courier` and `guard`, and **none of them has a workflow that checks out core
at all.** Their gates read a core checkout from somewhere else (a sibling
worktree, a vendored copy, a local path). So the mis-declaration is not being
*masked* by a loose ref; it is simply unexamined, which is the same defect one
layer further out and a worse one — there is no ref to tighten.

### DID reproduce, exactly

- `git -C core tag | wc -l` → **0**. Core publishes no tags.
- `core:` declarations: **`^0.1.0` in `identity`, `courier`, `guard`**;
  `^0.2.0` in the other nine that declare one; **`parlor` declares none**.
- `harness/cafaye_contract.py` stated in its own docstring that it *"does not
  resolve a `core:` constraint"*, and `RULE_IDS` held only `core.absent`,
  `core.not-a-checkout` and `core.digest-mismatch` — presence, not version.
- The version existed only as a `## [0.2.0]` heading in `CHANGELOG.md`.
- The counts `MUSE_CORE_SCHEMAS (10)` / `PANTRY_CAFAYE_ROOT (6)` did **not**
  reproduce either (see §5), but the *shape* — bespoke env vars plus vendir
  plus three ref strategies — is exactly right.

---

## 2. What was built

### A machine-readable version — `VERSION` (new, one line: `0.2.0`)

Deliberately **not** a schema and **not** a tag, and both rejections are
argued in `docs/core-version.md`:

- **Not a tag.** The harness is offline by contract. A tag names a commit in a
  repository it cannot see; a `core:` constraint resolves against bytes. This
  is the same reason `contract_digest` is a sha256 and not a commit id.
- **Not a new file under `schemas/`.** `contract_digest` hashes everything under
  `schemas/`, so a version file there would change the pin six services have
  already recorded — forcing a fleet-wide re-pin for a docs-only release. A
  version is the *name* of a set of contract bytes, not a contract byte.

It is asserted to hold **exactly one non-blank line**, to be **in the
resolver's grammar**, and to **equal the newest released `## [x.y.z]` heading
in `CHANGELOG.md`** (`## [Unreleased]` skipped — it is a section, not a
version, and counting it would make the test red on every worker branch).

### A resolver — `harness/core_version.py` (new)

A transliteration of `caf/internal/contract/version.go`, **not a second
dialect**. That was the single most important constraint in the brief and it
is honoured structurally: the Python module has no grammar of its own, and
`core_version_test.sh` pins all fourteen rows where the two could drift —
`^0.1.0` → `[0.1.0, 0.2.0)`, `^0.0.3` pinning the patch, `~` pinning the minor,
`10.0.0` newer than `9.0.0`, leading zeros refused.

**Deliberately stricter than the manifest schema.** `semverRange` uses
`[0-9]+`, so `core: ^0.01.0` is a *schema-valid* manifest with an unresolvable
constraint. The schema must accept what people write; a resolver must not be
lied to. That gap is breakage 2.

### Three rules, wired into the existing idiom

`core.constraint-unmet` (exit 1) · `core.constraint-unresolvable` (exit 1) ·
`core.version-absent` (**exit 2**). The 1-vs-2 split is the design: a service
whose `core:` disagrees is **wrong** (fix the manifest); a core publishing no
version means the check **could not happen** (fix the checkout). Reporting the
second as the first would send an owner to a manifest that was not the problem —
the same defect shape as the four skipped test tiers core already documents.

**No `core:` at all is deliberately *not* a rule here.** `core` is in `required`
in the manifest schema, so absence is `manifest.schema`'s finding; a second rule
would be two rules that could disagree. `check()` is total anyway — handed a
non-string it reports unresolvable rather than raising, so a future loosening of
the schema degrades to a finding, not a crash. `parlor` is the live case and is
already `manifest.schema`'s to report.

### A red proof that cannot rot — `harness/tests/core_version_test.sh` (new)

Every breakage in `self_test.sh` is chosen to be *permanently* broken. This
packet's central assertion is not: **`^0.1.0` stops being a violation the
moment core publishes 0.3.0.** A fixture pinned to it goes quietly green and
nobody re-reads it. So the script **derives** the conflicting constraint from
the version core actually publishes — a caret one minor *ahead*, which no
version of core can satisfy — and proves the red there. It is rot-proof with
no maintenance. That is also why it is a separate file rather than a section of
`self_test.sh`: mixing them would give one file two owners.

**21 passed, 0 failed, 0 skipped, 4 breakages proved red.** No skips exist and
none were added; the script prints the skip count and fails the run if it is
ever non-zero, because a skip is the defect this packet was sent to fix.

### A documented single way to fetch core — `docs/core-version.md` (new)

Declares the mechanism (one tag → one directory, `.cafaye/core`, `--core`
always explicit), tables the five services and four ref strategies with the
**measured** cost of each, and orders the migration cheapest-first. **No service
repository was edited.** Adoption is per-service follow-up.

---

## 3. It fires on the real fleet

Read-only, against the live checkouts:

```
identity  → FAIL core.constraint-unmet   declares ^0.1.0, core publishes 0.2.0
courier   → FAIL core.constraint-unmet   declares ^0.1.0, core publishes 0.2.0
guard     → FAIL core.constraint-unmet   declares ^0.1.0, core publishes 0.2.0
billing   → (silent — declares ^0.2.0)
caf / pantry / muse → (silent — declare ^0.2.0)
```

Exactly the three the brief predicted, and silent on the four that declare
`^0.2.0`. **This will make three services' gates red on adoption.** That is the
rule working, not a regression — but it is a sequencing decision, not mine, and
it is the first thing in §6.

---

## 4. Files touched — and the collision, stated plainly

**New (no collision with any other worker):**

| File | What |
| --- | --- |
| `VERSION` | the published version, one line |
| `harness/core_version.py` | the resolver — the brief's "new module for version resolution" |
| `harness/tests/core_version_test.sh` | the rot-proof red proof (not `gate_self_test.sh`) |
| `harness/tests/fixtures/nonconforming-core-version/` | the fixture, `^0.1.0`, copied from the fleet |
| `docs/core-version.md` | version contract, grammar, rules, fetch mechanism, migration |
| `REPORT-core-17.md` | this file |

**Edited — three shared files, minimal and each one forced:**

1. **`harness/cafaye_contract.py`** (core-16's, as warned). **Four edits, all
   in or adjacent to the rule table**: the sibling `import` shim (mirroring
   `gate_check.py`'s existing precedent), 3 ids in `RULE_IDS`, 1 entry in
   `REFUSALS`, and 1 `findings.extend` in `_check_service`. Plus one
   `check_core_version` adapter and the module docstring, which said "does not
   resolve a `core:` constraint" and no longer may. **Merge guidance for the
   manager: `RULE_IDS`, `REFUSALS` and the `findings.extend` block are the three
   conflict points. `check_core_version` and the import shim are new
   identifiers and should apply cleanly.**

2. **`tests/test_specs.py`** (core-14's). **One line plus three tests.** The one
   line is `siblings = {"core_version"}` in the stdlib AST walk — structurally
   unavoidable (a second module in `harness/` cannot be imported without it, and
   `gate_check.py` already carries the identical exemption for the same reason).
   The three tests are described below; none weakens anything.

3. **`gate.yml`** — the `minimum:` ratchet, **173 → 176**. Raised because three
   tests were added, which is what the ratchet is *for*. **Not lowered. Not
   touched otherwise.** This is core-14's territory by adjacency (`bin/prime`
   runs the gate) and is the single most likely conflict point in this packet.

Also edited: `harness/rules.json` (+3 entries), `docs/contract-harness.md`
(+3 table rows, count 25→28, and the "not built" section rewritten),
`harness/tests/self_test.sh` (**one line** — its synthetic core now copies
`VERSION`), `README.md` (one docs row).

### The three new tests in `test_specs.py`, and why each was unavoidable

- **`test_the_published_version_is_one_line_and_agrees_with_the_changelog`** —
  I wrote "it agrees with `CHANGELOG.md`" in the doc, so it had to be enforced
  or the doc would be a wish. **Proven able to fail:** bumping `VERSION` to
  `0.2.1`, appending a line, and writing `0.02.0` each go red with the right
  message; control green.
- **`test_the_harness_siblings_are_the_ones_that_travel`** — I widened an
  allowlist, so something had to make it unable to rot. Asserts the exemptions
  are exactly the sibling modules the harness imports, both directions.
  **Proven able to fail:** adding a module and importing it undeclared goes red
  on this *and* on the stdlib proof. (My first mutation — appending a comment —
  correctly did not fail it; the mutation was wrong, not the test.)
- **`test_the_contract_harness_refuses_to_run_without_its_resolver`** — because a
  harness that quietly checks *less* when a file is missing would be green
  everywhere and checking nothing, which is the worst version of this feature.

**The stdlib proof was verified not to have been neutered:** injecting
`import jsonschema` into the harness still fails it with
`imports ['jsonschema']`.

### One existing test legitimately had to change

`test_the_harness_digest_is_the_pin_and_it_notices_a_changed_schema` builds a
synthetic core from `schemas/` + `docs/` and asserts it is otherwise a pass. It
went red — **because the new refusal correctly rejected a core with no
`VERSION`.** The test now copies `VERSION` too, with a comment saying why: a
copy of core's contract surface is no longer a copy without it. **This was a
real bug in the test, caught by the new rule, and it is the best evidence the
rule works.** `self_test.sh`'s synthetic core got the same one-line fix — without
it, breakage 14 would have gone red via `core.version-absent` instead of
`core.digest-mismatch`, and a breakage caught by the wrong rule is exactly what
`expect_red` exists to reject.

---

## 5. The counts in the brief, measured

| Brief said | Measured | Note |
| --- | --- | --- |
| `MUSE_CORE_SCHEMAS` — 10 uses | **8 non-doc files** in `muse` | `gate.yml`, `pyproject.toml`, 2 `src/` modules, 4 test files |
| `PANTRY_CAFAYE_ROOT` — 6 uses | **7 non-doc files** in `pantry` | `bin/prime`, `registry/index.yml`, 5 test files |
| `vendir` — 2 | **2** ✓ | `pantry/`, `kit/core/release/release.yml` |
| 5 workflows / 3 `CORE_REF` / 2 `master` | **4 / 2 / 1** + guard's raw fetch | §1 |
| `identity` publishes `account.created` | **it does not** | §1 |
| 0 tags | **0** ✓ | |
| `^0.1.0` × 3, `parlor` none | **✓ exactly** | |

The env-var numbers are larger than the brief's because the brief counted
*mentions* and I counted the **migration surface** — which is the number that
decides whether this is a one-line change. It is not. Every one of those files
is a place a reader has to learn a second way to find core.

---

## 6. For the manager, in priority order

1. **Sequencing — this makes three services red.** `identity`, `courier` and
   `guard` will fail `core.constraint-unmet` the moment they adopt a core
   checkout. Each needs one line: `^0.1.0` → `^0.2.0`. **They need it anyway** —
   they are already compiling against 0.2.0 content, so the declaration is a
   lie today and the fix is a truth, not a concession. Which of: land core
   first and let three services go red, or land the three one-liners first? I
   would land the one-liners first; there is no reason to make three gates red
   for a fact that was already true.
2. **Merge order, by conflict risk:** `gate.yml` (the `minimum:` ratchet) and
   the three edit sites in `harness/cafaye_contract.py` are the two points where
   core-14 and core-16 will collide with me. Everything else is new files.
3. **Tagging is not mine, and a tag has since appeared.** `v0.2.0` was created
   by the repository owner at 22:42, naming `c63af27` — `master`'s tip, and
   this branch's base. **I did not create it and have not touched it**; my
   commit is untagged and `VERSION` reads `0.2.0` to agree with it. Two things
   for you: the tag's release note repeats the false `account.created` claim
   (§1), and it cites `DEBT.md` D22 which carries the same claim. `VERSION`
   being `0.2.0` means `docs/core-version.md`'s fetch mechanism is now
   *runnable* — the `ref: v0.2.0` in that document resolves for the first time.
4. **`parlor`** declares no `core:` and is a `v0-draft` shape throughout. It is
   already `manifest.schema`'s finding, and reconciling it to the real schema is
   its own packet. Nothing here blocks or enables it.

## 7. Decisions I made, with the cost of flipping each

The brief says never ask, make the call, write down the reasoning. Core's
`AGENTS.md` says specs are manager-owned and a genuine question must not be
silently resolved — and `test_no_open_decision_callouts_remain_in_the_docs`
forbids a `DECISION NEEDED` marker from surviving. So each is **decided,
argued, and priced** in `docs/core-version.md`, which satisfies both. None
blocks a merge; each is cheap to override:

- **`contract_digest` does not cover `VERSION`.** *Flip:* one line plus a
  fleet-wide `--expect-digest` re-pin. Default chosen because a docs-only
  release must not force six services to re-pin.
- **`>=` against a pre-1.0 core stays permitted**, as prose rather than rule.
  `docs/manifest-conventions.md` calls it "a lie" while its own grammar accepts
  it. The resolver matches `caf` rather than inventing a third opinion.
  *Flip:* tighten `semverRange` (a published-schema break) or change `caf` first.
- **A tag is the unit; a recorded commit sha is the accepted interim; a branch
  never is.** Stated so the mechanism is ready the moment a tag exists, without
  pretending one does. *Flip:* nothing in the resolver changes.

**Nothing was weakened.** No severity lowered, no assertion loosened, no skip
added, no sleep, no retry raised, no token or key logged. The one allowlist I
widened (`siblings`) is proven above to still fail on a real outside import.

## 8. Two limits worth stating

- **The rules read the checkout they are given.** They cannot detect that CI
  fetched the wrong core and then passed `--core` a directory that agrees with
  it. That half is a **convention with a document, not yet a rule** — a rule for
  it would have to read a service's workflow, which is a different repository
  with a different lifetime. Said so in `docs/contract-harness.md` rather than
  left to be discovered.
- **The fetch mechanism is review-enforced**, for the same reason, and
  `harness/rules.json` is not where a wish goes.
