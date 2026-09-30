# Core versions, and the one way to fetch them

Core is the substrate every cafaye service compiles against. A service says
which version of it it was written against:

```yaml
# cafaye.yml
core: ^0.2.0
```

Until core-17 that line was a comment with a pattern on it. Nothing resolved it,
because **there was nothing to resolve it against**: `git tag -l` in
`cafaye/core` was empty, and the version existed only as a `## [0.2.0]` heading
in `CHANGELOG.md`. The harness checked that `core` was *present*
(`core.absent`) and never compared it to anything. "One deploy, many services,
all compiling against one core" had no way to notice when core moved under a
service that had already said which core it wanted.

This document states the version contract, the grammar, the three rules that
enforce them, and the one supported way to fetch core. It is the document
`harness/rules.json` cites for `core.constraint-unmet`,
`core.constraint-unresolvable` and `core.version-absent`.

---

## What core publishes

One file, at the repository root, named `VERSION`, holding exactly one
`MAJOR.MINOR.PATCH` line and nothing else:

```
0.2.0
```

Read it with `harness/core_version.py`, or in a shell:

```sh
tr -d '[:space:]' < VERSION
```

Rules about the file, all of them enforced:

- **One line.** A `VERSION` that has been appended to is not a version, and
  reading only the first line would make it one again. `read_version` refuses
  a file with any other number of non-blank lines.
- **No prefix, no prerelease, no build metadata.** `v0.2.0` is not a version
  here. What a release is *tagged* is a separate question — see "Not done yet".
- **No leading zeros in any component.** `0.02.0` is not a version. Two
  spellings of one number are two different strings, and a range that accepts
  both is a range nobody can reason about.
- **It agrees with `CHANGELOG.md`.** The topmost released `## [x.y.z]` heading
  is the published version; `## [Unreleased]` is not a version and is skipped.

### Why a file and not a tag, and not a schema

A git tag names a commit in a repository the harness cannot see, and the
harness is offline by contract — it reads a checkout and never fetches one. A
`core:` constraint resolves against *bytes*, and the bytes are the thing a
service is compiling against. That is the same reason `contract_digest` is a
sha256 over `schemas/` and not a commit id, and the same reason the harness
cannot verify a tag even if one existed.

A new schema under `schemas/` would be the wrong shape for a different reason:
`contract_digest` hashes everything under `schemas/`, so adding a file there
changes the pin that six services have already recorded. A version is not part
of the contract bytes; it is the *name* of a set of contract bytes. Putting it
in `schemas/` would conflate the two and force a fleet-wide re-pin for a
docs-only release.

### `contract_digest` does not cover `VERSION` — and should not

**Decided: no.** A release that changes no schema bumps `VERSION` and leaves
the digest alone, so a service pinned to a digest is not forced to re-pin for a
documentation change. A version is the *name* of a set of contract bytes, and
folding it into the hash would conflate the two.

The cost of this choice: a version bump with no schema change is invisible to a
digest-pinned consumer. That is correct — it changed nothing they consume — and
it is the reason this is a decision rather than an oversight.

**To flip:** add `VERSION` to the input of `contract_digest` in
`harness/cafaye_contract.py`, and re-pin every `--expect-digest` in the fleet.
That is one line and six service pull requests, which is why the default is the
other way.

---

## The constraint grammar

Unchanged by this packet, and stated here because the rules below are decided
by it. `docs/manifest-conventions.md` owns the grammar; this section is the
part a resolver needs.

| Form | Admits | Example |
| --- | --- | --- |
| `^A.B.C` | everything that does not change the **left-most non-zero** component | `^0.1.0` → `[0.1.0, 0.2.0)` |
| `~A.B.C` | the minor is pinned | `~1.2.3` → `[1.2.3, 1.3.0)` |
| `>=A.B.C` | open-ended floor | `>=0.1.0` → `[0.1.0, ∞)` |
| `A.B.C` | exactly that version | `0.2.0` → `{0.2.0}` |

**The caret rule for a `0.x` release is the one that matters.** Before 1.0 the
*minor* is the breaking surface, so `^0.1.0` admits `[0.1.0, 0.2.0)` and
**not** `[0.1.0, 1.0.0)`. A service that declares `^0.1.0` and compiles against
0.2.0 content is compiling against something it explicitly declined.

### One resolver, not two

`caf` already resolves these strings, in Go, at
`caf/internal/contract/version.go`, and `caf contract resolve` prints the
answer. `harness/core_version.py` is a transliteration of that file rather than
a second dialect, and `harness/tests/core_version_test.sh` pins every row where
the two could drift — including `^0.0.3` pinning the patch, `~` pinning the
minor, `10.0.0` being newer than `9.0.0`, and the refusal of a leading zero.

A service must never be told it conforms by the Go tool and does not by the
Python one. If they ever disagree, that is a bug in the harness, not a choice.

The resolver is **stricter than the manifest schema**, on purpose. `semverRange`
in `schemas/cafaye.manifest.schema.json` uses `[0-9]+`, so `core: ^0.01.0` is a
schema-valid manifest with an unresolvable constraint. The schema has to accept
what people write; a resolver has to not be lied to. That gap is
`core.constraint-unresolvable`.

### `>=` against a pre-1.0 core is permitted, against this document's own argument

**Decided: permitted, as prose rather than as a rule.**
`docs/manifest-conventions.md` argues that `>=1.0.0` against a `0.x` service is
"not a range, it is a lie" — and the grammar it documents accepts exactly that
construct. The two statements contradict each other, and both are load-bearing:
the doc's argument is *why* the grammar is small.

`harness/core_version.py` therefore permits it, because that is what `caf`'s Go
resolver does and matching it is the whole point of this section. Inventing a
stricter answer in the harness would be exactly the second dialect that
`harness/core_version.py`'s own docstring says it exists to prevent. So the
prose stands as a **recommendation against `>=` pre-1.0**, and nothing enforces
it, and that is stated rather than papered over.

**To flip:** either tighten `semverRange` in
`schemas/cafaye.manifest.schema.json` to reject `>=` on a `0.x` version — a
breaking change to a published schema, needing an `examples/invalid/` case and a
major bump — or add a rule in `harness/core_version.py` that reports it, which
would diverge from `caf` and should not be done without changing `caf` first.

---

## What the harness does about it

Three rules, in `harness/rules.json`, the table in
[`docs/contract-harness.md`](contract-harness.md), and `RULE_IDS` in
`harness/cafaye_contract.py` — three statements of one list, which core's suite
asserts agree.

| Rule | Fires when | Exit |
| --- | --- | --- |
| `core.constraint-unmet` | a declared constraint does not admit the version core publishes | 1 |
| `core.constraint-unresolvable` | `core` is absent, is not a string, or is outside the grammar | 1 |
| `core.version-absent` | core publishes no readable version | **2** |

The split between 1 and 2 is the design, not an implementation detail. A service
whose `core:` disagrees with what core publishes is **wrong** — fix the
manifest. A core that publishes no version means the check **could not happen**
— fix the checkout. Reporting the second as the first would tell a service owner
to change a manifest that was not the problem, which is the same shape of defect
as the four skipped test tiers this repository already documents: muse's
`MUSE_CORE_SCHEMAS`, pantry's `PANTRY_CAFAYE_ROOT`, identity's
`TEST_DATABASE_URL` and darkroom's `--ignored`.

**No `core:` at all is deliberately not a rule here.** `core` is listed in
`required` by the manifest schema, so a manifest that validates has one, and
absence is `manifest.schema`'s finding. A second rule for the same fact would be
two rules that could disagree about the same manifest. `check()` is nonetheless
total: handed a non-string or missing field it reports
`core.constraint-unresolvable` rather than raising, so a future loosening of the
schema degrades to a clear finding instead of a crash. `parlor` is the live
case — its `cafaye.yml` is a `v0-draft` document with a different shape
throughout and no `core:` key — and it is already `manifest.schema`'s to report.

### What these rules do not do

They read the checkout they are given. They cannot detect that CI fetched the
wrong thing and then passed `--core` a directory that agrees with it. That
half is the next section, and it is a **convention with a document, not yet a
rule** — a rule for it would have to read a service's workflow, which is a
different repository and a different lifetime.

---

## The one way to fetch core

> **This section declares the mechanism. It does not migrate anything.** No
> service repository was touched by the packet that wrote this. Adoption is
> per-service follow-up, and each service is a separate pull request against a
> repository with its own owner.

A service resolves core by fetching **one tag, into one directory, named by one
convention**, and running `harness/bin/cafaye-contract --core <that directory>`.
Concretely:

```yaml
# .github/workflows/ci.yml
- uses: actions/checkout@v7
  with:
    repository: cafaye/core
    ref: v0.2.0          # the tag; never a branch
    path: .cafaye/core    # one location, every service
- name: contract
  run: python3 .cafaye/core/harness/bin/cafaye-contract --core .cafaye/core .
```

Three properties, and each one is a rule someone wrote down:

- **A tag, never a branch.** `ref: master` compiles against whatever core is
  today, which is the defect this whole packet exists to remove. A tag is a
  claim about compatibility.
- **One directory, named `.cafaye/core`.** So a service's Makefile, its CI, its
  docs and a developer's shell all read the same path, and no service invents
  its own environment variable to find it.
- **`--core` explicitly, always.** Never a bare invocation that searches. The
  harness's `core.absent` rule exists because a check that cannot find core must
  say where it looked.

### What exists today, and what each one costs

Measured across the fleet's CI and build configuration, not assumed:

| Service | Mechanism | Shape | What migrating costs |
| --- | --- | --- | --- |
| `muse` | `CORE_REF` env + checkout | `CORE_REF` is a hand-bumped commit sha | 1 workflow line; `CORE_REF` becomes `v0.2.0` |
| `docs` | `CORE_REF` env + checkout | `CORE_REF: 'master'` — **a branch, spelled as a pin** | 1 workflow line |
| `billing` | checkout | `ref: master` | 1 workflow line |
| `guard` | raw URL | `raw.githubusercontent.com/cafaye/core/master/<schema>` — **not a checkout at all** | the largest: it fetches one schema and has no tree to point `--core` at |
| `pantry` | `vendir` + `vendir.lock.yml` | vendors 2 files, records a sha, re-copies by hand | 1 workflow step; `vendir.lock.yml` becomes the record |
| `pantry`, `muse` | bespoke env vars | `PANTRY_CAFAYE_ROOT` (7 non-doc files), `MUSE_CORE_SCHEMAS` (8 non-doc files) | the real cost: each is read in source, in tests, in a gate declaration and in a build config |

That is **five services, four ref strategies, and two bespoke environment
variables** — and the two variables are the expensive half, because they are
not one line each. `MUSE_CORE_SCHEMAS` is read in `gate.yml`,
`pyproject.toml`, two modules under `src/` and four test files;
`PANTRY_CAFAYE_ROOT` in `bin/prime`, `registry/index.yml` and five test files.
Every one of those is a place a reader has to learn a second way to find core.

**The migration, in order of cost:**

1. **`docs` and `billing`** — one line each. They already check out a tree, so
   they only need `ref: master` → `ref: v0.2.0`. Do these first: they are the
   two services most obviously compiling against a moving target, and the diff
   is unreadable in the bad way.
2. **`muse`** — `CORE_REF` becomes a tag. Its sha pin is *more* precise than a
   tag and there is an argument for keeping it; the honest resolution is that a
   tag is the platform's unit and a sha is a service's private refinement, so
   `v0.2.0` in the workflow and the sha in a comment if the service needs one.
3. **`pantry`** — keep `vendir.lock.yml`; it is already the honest record of
   *which* core, and it is what `pantry::pin` reads. Point it at the tag and
   retire `PANTRY_CAFAYE_ROOT` behind it.
4. **`guard`** — the only real work, because it has no checkout to rename.
   Adopting a checkout is the fix; a raw fetch of one schema cannot be pointed
   at a tag *and* verified, and verification is the point.
5. **The environment variables last**, once the directory exists, because they
   exist only to *find* core and the directory removes the need.

### What is not done yet, and is not this packet's to do

- **Core publishes no tag.** `git tag -l` in `cafaye/core` is still empty. The
  `ref: v0.2.0` above is the mechanism, written down and ready; **it does not
  work until a tag exists.** Tagging is the platform owner's call, not a
  worker's, and the tree is left ready to tag. This is also why the two repos
  already written to fetch a tag are `kit/core/release/release.yml` (a
  candidate workflow, not yet installed) and `pantry/vendir.lock.yml`
  (`ref: master` with a sha, because the tag does not exist).
- **No service was migrated.** Not one service repository was edited. Adoption
  is per-service, and per-service owners.
- **The fetch mechanism is not yet a rule.** `harness/rules.json` says
  `harness` or `doc` for every rule, and a rule that read a service's workflow
  would be reading another repository. This document is the convention; the
  enforcement is per-service CI configuration, and the honest statement is that
  it is review-enforced until someone owns the fan-out.

### A tag is the unit; a recorded commit sha is the interim

**Decided: a tag is the unit, and a recorded commit sha is an acceptable
interim — but a branch never is.** Core has never been tagged, so the `ref:
v0.2.0` above does not work yet, and a document that only worked would be
worthless.

Two things are therefore declared, and they are not in conflict:

- The **mechanism** is a tag, and it is written down now so it is ready the
  moment a tag exists.
- The **interim**, for any service that must resolve core before then, is a
  *recorded* commit sha — `muse`'s `CORE_REF` and `pantry`'s
  `vendir.lock.yml` both already do this, and both record the sha rather than
  trusting a name.

So read `ref: v0.2.0` above as "**a tag, or a recorded sha, but never a
branch**". The defect this packet fixes is not the absence of a tag; it is
`ref: master`, which compiles against whatever core happens to be today and
cannot be reasoned about afterwards. A recorded sha has neither problem.

**To flip:** if the platform owner would rather core never carry tags, the
mechanism becomes a `vendir.lock.yml`-style recorded sha everywhere and the tag
rows above become sha rows. Nothing in `harness/core_version.py` changes — it
resolves a *version*, and the sha is only ever the way a service finds the
checkout carrying it.
