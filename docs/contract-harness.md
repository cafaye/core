# The contract-test harness

`harness/` is how a service checks itself against core's contracts using
something core ships, rather than writing that check itself. It is the fifth of
core v0's five Phase 0 deliverables (PLAN.md §4) and the only one that did not
exist until now — which is why muse, darkroom, courier and pantry each wrote
their own version, differently.

```
harness/bin/cafaye-contract      what a service's CI calls
harness/cafaye_contract.py       the harness. One file, standard library only
harness/rules.json               the rule inventory, and where each rule lives
harness/tests/self_test.sh       twenty breakages, twenty reds
harness/tests/fixtures/          a conforming service, and five that are not
```

## Running it

```
harness/bin/cafaye-contract --core ../core .
harness/bin/cafaye-contract --core ../core --expect-digest <sha256> .
harness/bin/cafaye-contract --list-rules
```

Offline, always. The harness never fetches a schema, resolves a `$ref` over the
network, or reads an environment variable other than `CAFAYE_CORE` — a contract
check that needs the network is one nobody runs on an air-gapped runner, and one
that reads a variable is two harnesses.

| Exit | Meaning |
| --- | --- |
| `0` | the service conforms |
| `1` | it does not; every broken rule is one `FAIL <rule-id> <path>:` line |
| `2` | **the run could not happen** — no core, no manifest, or YAML outside the declared subset |

`2` is not a soft `1`, and a reader is meant to notice the difference. A run that
could not happen and a run that found nothing to complain about both produce
output; treating them as the same thing is how a check that could not find the
contract ends up reporting success. Four repositories in this fleet have shipped
that defect: guard's live-Redis tier, muse's `MUSE_CORE_SCHEMAS` tier, identity's
`TEST_DATABASE_URL` tier, and darkroom's `--ignored` tests. **A contract check
that cannot find the contract is worse than no contract check, because it
converts an unknown into a green badge.**

`test_the_harness_fails_loudly_when_core_is_absent` and
`test_the_harness_fails_loudly_when_a_service_manifest_is_absent` are the two
assertions that keep `2` honest, and self-test breakages 15–18 and 20 are the
same five rules proved able to go red.

## Where it lives, and why it is in core

Inside core, not its own repository. Three reasons, in order of weight:

1. **It reads core's schemas.** A harness in its own repository would have to
   vendor them, which is the exact drift this packet exists to end — four
   vendored copies today, one per service, at four different SHAs. The harness
   is the thing that makes vendoring unnecessary, so it cannot be the fifth
   vendored copy.
2. **It is the executable form of a rule that already lives in `schemas/`.** It
   adds no new contract; it decides the existing one, and it is checked by the
   same suite that checks the schemas.
3. **core already contains executable code.** `bin/prime`, `tests/test_specs.py`,
   `tests/setup.sh` and `tests/validate.sh` are all programs. The line
   AGENTS.md draws is not *no code* — it is **no runtime**: no service, no
   framework, no library, no dependency. The harness starts nothing, listens on
   nothing, ships no packages, and imports only the standard library, which is a
   stricter reading of the rule than `tests/requirements.txt` is.

The alternative that loses is a compiled binary released from its own
repository: that makes core a release-engineering project with per-platform
artifacts and a version to keep in step with the spec, which is what
`refs/goreleaser` is on the reference shelf for and not what this is.

## Pinning

**The pin is a sha256 over everything under core's `schemas/`, path-sorted. The
same argument works on a laptop and in CI because there is only one argument.**

Not a git ref, and the reason is the fleet's own history. A ref names a commit
in a repository the harness is not allowed to fetch; `muse` pins `CORE_REF` in
CI and compares bytes, `pantry` reads `PANTRY_CAFAYE_ROOT`, `darkroom` uses "the
checked-out cafaye/core schema", and `courier` reads its router. Four ways to
answer "where is core", one of which is a `git` object and three of which are
directories. A digest names **bytes**, and bytes are the thing a service is
actually compiling against.

```console
$ harness/bin/cafaye-contract --core ../core --list-rules >/dev/null
$ python3 -c "import sys; sys.path.insert(0,'../core/harness'); \
    import cafaye_contract, pathlib; print(cafaye_contract.contract_digest(pathlib.Path('../core')))"
aaf8216e42b8…
```

What the digest gives, and what it does not:

- the same core commit digests identically in a worktree and in a runner, so a
  developer's local run and CI's step are the same check, with the same code and
  the same rules;
- one byte in one schema changes it — the smallest possible drift, and the one a
  re-vendor fan-out produces;
- it covers **all** of `schemas/`, not the two files a service happens to vendor,
  so a service cannot be pinned against a partial copy;
- it does **not** notice a dirty tree that has not been committed. A developer
  with an edited schema gets a different digest from CI, and that is the truth
  rather than a bug — their tree really is different. The git commit is
  *reported* in every run, never checked, because a name the harness cannot
  verify offline is not a pin.

`--expect-digest` is the opt-in that turns "different" into a red build, and it
is a **violation** (exit 1) rather than a refusal (exit 2): core was found and
read in full, it is simply not the core that was pinned. Refusing here would say
"I could not check", and a service owner would spend an afternoon on a checkout
problem they do not have.

## What it validates, and what it deliberately does not

PLAN.md §3 asks for two different things by the same name, and conflating them
is how a service ends up believing it has a check it does not have.

**Built: a service's *declared* contracts.** Its `cafaye.yml` against core's
manifest schema, the manifest's cross-field rules, its event types against
core's catalog, and its OpenAPI document against core's conventions. All of it
is decidable from files, offline, in any language.

**Not built, and still owed: a *live response* against the event envelope and the
per-type payload schema.** That is PLAN.md §3's "each service's CI validates
responses against the spec" — the richer reading of "contract test", and arguably
the more valuable one. It needs a running service, and core ships no runtime;
`darkroom`'s `tests/contract.rs` already says so in a comment, naming
`caf contract test` as the thing that was supposed to do it. A service can
already validate a payload by hand against
`schemas/events/<service>/<entity>/<action>.schema.json`; what is missing is
something that does it for every published type, in CI, without the service
writing the loop. **Until that lands, a reader of this document should assume the
harness does not look at a single byte of live traffic.**

Also not built, and named so it is not mistaken for an oversight:

- **The `core:` constraint is not resolved.** It needs a machine-readable core
  spec version on both sides of the comparison, and core publishes none — the
  version is in this file's CHANGELOG in prose. `caf` already implements the
  resolver in Go (`internal/contract/version.go`); what is missing is core
  publishing the version to resolve *against*. [D24](https://github.com/cafaye/core/blob/master/DECISIONS.md)
  says which half to build first, and why a new file under `schemas/` should wait
  until the re-vendor fan-out has an owner.
- **The document is not compared to the service's router.** That half needs the
  service's language: courier reads `Router.__routes__/0` in ExUnit, muse
  compares against a live FastAPI app, and a language-neutral harness cannot
  read either. courier's test stays. The *readable* half — the reserved error
  codes, the pagination envelope, `Idempotency-Key` on retryable `POST`s — is
  decidable from a document alone and is still owed.
- **The YAML reader reads a subset, and refuses the rest.** See below.

## Where each rule actually lives

This is core's own question turned on core's own tool, so the answer is
field-by-field rather than a summary. The honest answer is **"some in
`schemas/`, some in `docs/` and therefore in the harness's source, and some
about the filesystem"**, and
[`harness/rules.json`](../harness/rules.json) is where that stops being a
summary: every rule declares an `enforcedBy` with a kind, and
`test_the_rule_inventory_says_where_every_rule_lives` checks that a `schema`
claim names a real file under `schemas/`, that a `doc` claim names a real
heading in a real document, and that a `harness` claim names a function that
exists.

| Rule | What it decides | Where it lives |
| --- | --- | --- |
| `manifest.schema` | the manifest satisfies the manifest schema | `schemas/cafaye.manifest.schema.json` |
| `event.own-prefix` | a published type starts with the publisher's own name | `docs/manifest-conventions.md`, "Rules the schema cannot state" — **in the harness** |
| `event.no-self-consume` | a service never consumes its own events | same — **in the harness** |
| `event.unknown-consumed` | every consumed type is in core's catalog | same — **in the harness** |
| `event.unknown-published` | every published type is in core's catalog | same — **in the harness** |
| `event.payload-schema-missing` | every published type has a payload schema | `docs/event-naming.md` — **in the harness** |
| `manifest.api-file-missing` | `exposes.api` resolves inside the repository | **in the harness**; a fact about a filesystem, not a document |
| `openapi.document-is-31` | the document declares 3.1 | `docs/openapi-conventions.md` — **in the harness** |
| `openapi.info-version` | `info.version` is `MAJOR.MINOR.PATCH` | same — **in the harness** |
| `openapi.has-paths` | the document declares at least one path | same — **in the harness** |
| `openapi.paths-are-versioned` | every path is under a `/vN` prefix | same — **in the harness** |
| `openapi.one-version-prefix` | one `/vN` per document | same — **in the harness** |
| `core.digest-mismatch` | core's `schemas/` digests to the pin | **in the harness** |
| `core.not-a-checkout` | the directory named is a core checkout | **in the harness** |
| `core.absent` | the run says where it looked, and never skips | **in the harness** |
| `service.manifest-absent` | the service root carries a `cafaye.yml` | **in the harness** |
| `yaml.unsupported` | a construct outside the declared subset is refused | **in the harness** |

One rule out of seventeen is enforced by a JSON Schema. The other sixteen are
in code, and **that is not a finding about the harness — it is the finding**:
`docs/openapi-conventions.md` says in its own words that "until a future
`caf contract lint` lands the rule is review-enforced, like every other
convention here", and sixteen of the rules a service is asked to live by have
never been mechanically checkable at all. The harness does not make them
schemas. It makes them *executable, named, tested and inventoried*, which is the
step before a schema and the step that a manager can now decide on —
[D23](https://github.com/cafaye/core/blob/master/DECISIONS.md) is that decision,
and it is open because the list of sixteen did not exist a week ago.

`event.unknown-published` is not in
[`docs/manifest-conventions.md`](manifest-conventions.md) today; it is the other
half of rule 6 and this document and the inventory are its home until a manager
moves it. See [D22](https://github.com/cafaye/core/blob/master/DECISIONS.md).

Two structural notes a reader will otherwise have to discover:

- **`event.payload-schema-missing` cannot fire on its own.** Every catalogued
  type has a payload schema, so a published type without one is necessarily not
  in the catalog, and `event.unknown-published` fires alongside it. The two rules
  are coupled, self-test breakage 8 asserts both, and the coupling is recorded
  in the inventory.
- **The manifest schema is a gate, and the cross-field rules only run past it.**
  A document whose fields are the wrong type is a document whose cross-field
  comparisons would be comparing nothing. `caf`'s linter makes the same call, and
  the harness prints that it stopped rather than letting a quiet half-run read as
  a pass.

## The two hand-written pieces, and the receipts for them

The standard library has no JSON Schema and no YAML. Both are in this repository
rather than in a dependency, and both are receipts rather than claims.

**The evaluator.** 27 keywords, exactly the inventory of `schemas/`.
`test_the_harness_evaluator_agrees_with_jsonschema_on_every_example` compares
violated keywords with `jsonschema` over every example in `examples/`, in both
directions, and
`test_the_harness_implements_every_keyword_core_schemas_use` holds the keyword
list equal in both directions — a keyword nothing implements is an unenforced
rule, and a keyword nothing uses is a rule with no test. The equivalence test
found a real bug within the hour: a `type` array is a union, and the first
version reported a violation per non-matching member, so the envelope's `data` —
declared as any of seven types, correctly holding an object — produced six
failures. **Read that test before trusting the evaluator.**

One deliberate divergence: `CHECKED_FORMATS` includes `uri`, which `jsonschema`
does not check without `rfc3987-validator` installed. So on a `format: uri`
failure the two disagree and the harness is the stricter one. That is a gap in
core's own suite, the harness made it visible, and it is
[D22](https://github.com/cafaye/core/blob/master/DECISIONS.md) —
`tests/requirements.txt` already carries the same note about `date-time`.

**The YAML reader.** It reads block mappings, block sequences, plain and quoted
scalars, the empty flow collections `[]` and `{}`, the literals
`null`/`true`/`false`, integers, and comments on their own line or after a value.
Everything else is refused with a file and a line. The refusals are
`YAML_REFUSALS` in the source, and
`test_the_harness_yaml_reader_refuses_only_what_it_declares` asserts the list
*and* that the reader actually refuses each one.

It refuses rather than guesses because a guess means validating a document
nobody wrote: a multi-line plain scalar is legal YAML, PyYAML folds it to one
line, and a reader that folded it differently would report a schema error
against a value it invented. The most common refusal by far is that one, and the
message says what to do instead.

Two of core's own YAML files are outside the subset — `fleet.yml` folds a
description with `>-`, and `examples/invalid/fleet.invalid.yml` uses a non-empty
flow collection — and neither is a document the harness reads.
`test_the_harness_yaml_reader_refuses_a_named_list_of_core_documents` names both
so the limit is a written fact rather than a surprise the first service hits.
`test_the_harness_yaml_reader_agrees_with_pyyaml_on_every_manifest` is the
receipt: every manifest-shaped document core owns goes through PyYAML and through
the reader, and the values must be identical.

## Proving the harness can fail

```
bash harness/tests/self_test.sh
```

Twenty deliberate breakages, twenty reds, and a control on the unbroken tree
first — without it the breakages prove nothing. Every breakage names the rule id
it expects, because "the harness went red" is a weak claim when seventeen checks
can make it red: a breakage caught by the wrong check still reads as a pass, and
the check it was written for can be dead code forever.

All seventeen rules have at least one breakage. The mutations are chosen the way
kit chose its own: not a typo a reviewer would see, but the mistake that looks
like diligence — an HTTPS remote, a core constraint with no patch component, a
second `/vN` prefix added beside the first, a one-byte change to a schema
against a pinned digest. The first version of the second-prefix breakage
*renamed* a path instead of adding one and the harness stayed green, correctly,
because a rename leaves one prefix behind; that is courier's route-count lesson
arriving three repositories later.

CI runs it. `bin/prime` runs the suite, which includes the harness's own tests
but not this script — the same split kit makes, because a self-test that ran
inside every gate invocation would be a second gate that can disagree with the
first. The `gate` job in [`.github/workflows/ci.yml`](../.github/workflows/ci.yml)
has a step for it, and a comment claiming CI runs something is not CI running
it (PLAN.md §1).

## Adopting it

This packet deliberately migrates **no** service. One packet, one repository: a
harness adopted by four services at once is four workers in four languages
discovering four things nobody anticipated, and the manager would not be able to
tell which of them found a bug in the harness.

For a service that wants it, the whole thing is a CI step and a checkout:

```yaml
- uses: actions/checkout@v7          # cafaye/core at the ref you pinned
  with: { repository: cafaye/core, ref: <your pinned sha> }
- uses: actions/checkout@v7          # your service
- run: core/harness/bin/cafaye-contract --core core --expect-digest "$DIGEST" .
```

Add `--expect-digest` on the first run: run once without it, read the digest
off the `OK` line, and pin that. Until you do, the digest is still printed on
every run and the pin is still one argument away.
