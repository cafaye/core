# cafaye/core

The substrate every cafaye service compiles against: the service manifest
format, the event envelope, and the HTTP contract conventions. Schemas, docs
and validators — nothing else. There is no runtime here, on purpose; a
service's runtime is that service's problem.

```
schemas/   the machine-readable contract (JSON Schema, draft 2020-12)
  events/  one payload schema per event type, at schemas/events/<type>.schema.json
  telemetry/ the observability spec: span naming, the per-signal attribute
           allowlists, the redaction boundary, the *_OTEL_ENDPOINT contract
docs/      the human contract: the same rules, with the reasoning
examples/  one valid and one invalid document per schema
tests/     the executable statement of every rule above
harness/   the contract-test harness: how a service checks itself against all
           of the above without writing the check
cafaye.yml core's own manifest, validated against core's own schema
fleet.yml  what the real service repositories publish, read at a named commit
```

## What core is for

`caf init`, `caf new`, `caf dev`, `caf gen` (SDKs), `pantry` (registry),
`guard` (routing) and every service's contract tests all need the same handful
of facts about a service: what it is called, which language it is written in,
which spec version it was written against, what contracts it exposes and
consumes, and who owns it. Six tools answering six questions by reading six
bespoke config files is how cross-repo drift starts. One file, one schema, one
validator.

**A rule that is not in `schemas/` is not a cafaye rule.** If a convention is
real, it is a JSON Schema constraint with a test, and a document explaining why.
A convention that lives only in a README is a convention nobody enforces.

## The schemas

| File | Describes | Enforced by |
| --- | --- | --- |
| [`schemas/cafaye.manifest.schema.json`](schemas/cafaye.manifest.schema.json) | `cafaye.yml`, the per-service manifest | `test_every_example_manifest_is_covered_by_the_manifest_schema` + the cross-field rules below |
| [`schemas/event-envelope.schema.json`](schemas/event-envelope.schema.json) | the envelope every event travels in | `test_valid_event_envelope_example_validates` |
| `schemas/events/<service>/<entity>/<action>.schema.json` | the `data` payload of one event type | `test_payload_schema_examples_validate` + `test_valid_envelope_data_validates_against_its_payload_schema` |
| [`schemas/telemetry/span-naming.schema.json`](schemas/telemetry/span-naming.schema.json) | one span-name scheme, low-cardinality by construction | `test_span_names_are_low_cardinality_by_construction` + the invalid example |
| [`schemas/telemetry/{traces,metrics,logs}.schema.json`](schemas/telemetry/traces.schema.json) | the per-signal attribute allowlists, and the prohibition on unbounded identifiers as a measurement attribute | `test_every_signal_declares_an_allowlist` + `test_prohibited_identifiers_are_not_measurement_attributes` |
| [`schemas/telemetry/redaction.schema.json`](schemas/telemetry/redaction.schema.json) | the redaction boundary, and where it is enforced | `test_the_redaction_boundary_is_a_schema` + `test_the_redaction_policy_never_allowlists_a_content_attribute` |
| [`schemas/telemetry/otel-endpoint.schema.json`](schemas/telemetry/otel-endpoint.schema.json) | the `*_OTEL_ENDPOINT` contract and its no-op path | `test_unsetting_the_endpoint_declares_a_free_no_op` + the invalid example |
| [`schemas/telemetry/probes.schema.json`](schemas/telemetry/probes.schema.json) | `healthz` unconditional, `readyz` really checking | `test_a_readyz_that_checks_nothing_is_rejected` |
| [`schemas/fleet.schema.json`](schemas/fleet.schema.json) | [`fleet.yml`](fleet.yml) — what each service repository actually publishes, read at a named commit | `test_fleet_declaration_matches_its_schema` + the fleet section of `tests/test_specs.py` |

All are draft 2020-12, meta-validated by `check_schema` on every test run, and
all close themselves with `additionalProperties: false`. A key core does not
know about cannot be validated, so a producer cannot quietly invent one.

Some rules compare two properties of the same document, which JSON Schema
cannot express. Those live in `tests/test_specs.py` and in
[`docs/manifest-conventions.md`](docs/manifest-conventions.md) — for example, a
published event type must be prefixed with the publisher's own service name, a
service never consumes its own events, and every consumed type must exist in
the core catalog.

## Docs

| Document | Covers |
| --- | --- |
| [`docs/manifest-conventions.md`](docs/manifest-conventions.md) | manifest shape, namespace rules, semver constraints, the rules the schema cannot state |
| [`docs/event-naming.md`](docs/event-naming.md) | event grammar, action vocabulary, payload schemas, delivery guarantees, and the catalog of every event that exists |
| [`docs/event-outbox.md`](docs/event-outbox.md) | the transactional outbox: the table, the publisher loop, at-least-once, retention |
| [`docs/observability.md`](docs/observability.md) | span naming, the per-signal attribute allowlists, the prohibition on unbounded metric dimensions, the redaction boundary, the `*_OTEL_ENDPOINT` contract and its no-op path, and `healthz` vs `readyz` |
| [`docs/openapi-conventions.md`](docs/openapi-conventions.md) | error envelope, pagination, versioning, idempotency, auth, deprecation |
| [`docs/contract-harness.md`](docs/contract-harness.md) | the contract-test harness: what it checks, how it pins core, where each rule lives, and what it does not check |
| [`examples/invalid/README.md`](examples/invalid/README.md) | the expected failure of every negative example, field by field |
| [`DECISIONS.md`](DECISIONS.md) | every open question about the spec, numbered, with its recommendation |

`docs/event-outbox.md` is a convention, not a package. Every service implements
it in its own language against its own database; core states the table and the
loop and deliberately ships no shared code.

`docs/observability.md` is a contract, not a collector. The seven schemas under
`schemas/telemetry/` say what may go in a span, a metric and a log record, and
what the `*_OTEL_ENDPOINT` variable means when it is set and when it is not.
**The OpenTelemetry Collector, the LGTM stack and the per-language SDK setup are
deliberately not here** — that is `kit` and the services, and core shipping an
exporter would be core becoming a runtime, which is the one thing this
repository is not.

## The contract-test harness

PLAN.md §4 Phase 0 named five deliverables for `core` v0. Four shipped. The
fifth — a **contract-test harness** — did not, and four services each wrote their
own instead: `muse` pins a core SHA in CI and compares bytes, `darkroom` tests
against its own vendored copy, `courier` holds its document to the router,
`pantry` has a byte-equality drift test. Four mechanisms, no shared harness.

```
harness/bin/cafaye-contract --core ../core .
harness/bin/cafaye-contract --core ../core --expect-digest <sha256> .
```

A service's CI, in three lines. Offline — core is read from a checkout, never
fetched. Standard library only, so a Go repository needs no Python package to run
it. It exits `0` for conforms, `1` for does-not-conform, and **`2` for "the run
could not happen"**, because a check that cannot find the contract and reports
success is worse than no check: it converts an unknown into a green badge.

It validates a service's *declared* contracts — its manifest against core's
schema, the cross-field rules JSON Schema cannot state, its event types against
core's catalog, and its OpenAPI document against core's conventions. It does
**not** validate live responses against the event payload schemas, and
[`docs/contract-harness.md`](docs/contract-harness.md) says so in its own words
rather than leaving a reader to assume otherwise.

Seventeen rules, and the honest answer to "where does each one live" is that
**one is a JSON Schema and sixteen are in the harness's source** — because
[`docs/openapi-conventions.md`](docs/openapi-conventions.md) says itself that
those rules are review-enforced "until a future `caf contract lint` lands".
[`harness/rules.json`](harness/rules.json) is where that stops being a summary:
every rule declares whether it is enforced by a schema, by a document, or by a
named function, and core's suite checks that each claim is true. Moving a rule
into a schema is a one-line inventory change, and the question is
[D23](DECISIONS.md#d23-do-the-openapi-and-cross-field-rules-become-a-schema).

The pin is a **sha256 over core's `schemas/`**, not a git ref: a ref names a
commit in a repository the harness is not allowed to fetch, and a digest names
bytes, which is what a service compiles against. It is printed on every run and
`--expect-digest` turns it into a red build. The same argument works on a laptop
and in CI because there is only one argument.

`bash harness/tests/self_test.sh` breaks the harness twenty ways and asserts
twenty reds, naming the rule each breakage must be caught by. CI runs it — a
comment claiming CI runs something is not CI running it.

## Spec versioning

`core` is pre-1.0 and versioned as a spec, not as a library — services
constrain it in their manifest (`core: ^0.2.0`) and CI pins it to a release
inside that range.

| Change | Bump |
| --- | --- |
| New event, new example, more documentation, a looser rule | **patch** |
| New manifest field, new optional `data` field, a new action in the vocabulary | **minor** |
| Tightening a pattern, making an optional field required, an enum value that invalidates an existing manifest, a removed event type, a changed envelope attribute | **major** (`0.x` majors are allowed while pre-1.0 — state the intent in the PR) |

`0.x` majors are legal but must be deliberate: a service pinned to `^0.1.0`
should never be broken by a `0.2.0` landing. A breaking change to a `0.1.x`
patch is a bug. The last major bump was v0.2.0, which changed the event type
format; the migration is in
[CHANGELOG.md](CHANGELOG.md#breaking).

## Governance — worker drafts, the manager decides

Specs are **manager-owned**. A worker never decides what the contract is.

1. A packet briefs a spec change.
2. The worker drafts it: schema, examples, docs, and tests written **first** and
   shown failing. Where a genuine choice exists, the worker picks a defensible
   default, implements it end to end, and marks the choice with a
   `> DECISION NEEDED (Dn):` callout in the doc it affects — stating the
   alternatives, the recommendation, and how expensive it is to flip.
3. The manager reads the diff, runs the suite, and either decides or sends it
   back. Open decisions are numbered `D1`, `D2`, … and referenced by number. A
   decision is folded into the spec as if it had always been the rule — no
   callout survives the merge, and `test_no_open_decision_callouts_remain_in_the_docs`
   fails the build if one does.
4. The manager merges to `master`. Workers commit to their own branch and never
   push.

Drafting a default rather than blocking on a question is deliberate: a worker
that stops to ask has stalled the phase, and a reversible default with a written
trade-off is cheaper than a stalled week. Nothing is merged undecided.

## Running the tests

```
bin/prime              # setup if needed, then the full suite
bin/prime --pytest     # the same suite through pytest
```

`bin/prime` creates `tests/.venv` on first run via `tests/setup.sh` and
validates every example: valid examples must validate, invalid ones must be
rejected for the exact reasons
[`examples/invalid/README.md`](examples/invalid/README.md) lists. There is
nothing to run and nothing to deploy — if this suite is green, core agrees with
itself.

Python is pinned in `mise.toml`; `mise run test` and `mise run setup` are thin
wrappers over the same two commands.

The suite is **118 tests**, all of which run on every invocation, in about a
second, with no database, no network and no fixtures outside the tree — the only
network access is `tests/setup.sh` installing four packages from PyPI on first
run. Nothing in `tests/test_specs.py` reads an environment variable and nothing
in it skips. So a green result means 118 rules held.

**There is no second tier and no environment gate** — and there is now something
that looks like one, so the distinction is worth being exact about.
`harness/tests/self_test.sh` is a *documented command* that CI also runs; it is
not a tier of this suite, it is not gated on an environment variable, and it does
not run inside `bin/prime`. It is a conformance tool proving it can fail, in the
same shape kit's `tests/self_test.sh` is, and it is invoked because a self-test
nobody runs is a claim rather than a proof. Anything that ever *does* need a
second tier has to arrive with the environment that forces it, not with a default
that leaves it dormant.

`tests/validate.sh` exists for one reason and one reason only: kit's reusable
workflow runs that exact path, and fails a build that asks for a gate and does
not ship one. It is `exec bin/prime "$@"` and nothing else. **Use `bin/prime`** —
`validate.sh` is the filename kit's contract looks for, not a second way in.

## CI

```
.github/workflows/ci.yml   calls kit's reusable workflow; owns the rest
```

Two jobs, and the job names are the claims they make:

| Job | Claim |
| --- | --- |
| `kit` | kit's workflow resolves from core, and the gate bootstraps from nothing on a clean runner |
| `gate` | the gate: `bin/prime` on the pinned interpreter, `bin/prime --pytest`, the drift guards, and the harness's own self-test |

**A red build in `core` is not "core is broken" — it is "a rule the fleet
depends on no longer holds".** core publishes no service and no API, but six
repositories' contract tests consume these schemas and vendor them, so a red
here is a spec regression until proven otherwise. Escalate it as one; do not
file it as a docs nit, and do not fix it by loosening a test.

The pin is read from `mise.toml` at run time and asserted against the
interpreter that arrives, rather than written into the workflow as a second
literal. That is not fussiness: `python-version-file: mise.toml` reads as if it
should work and **silently installs nothing**, because the action reads
`project.requires-python` or `tool.poetry.dependencies.python` and mise's
`[tools]` is neither.

Two things about this arrangement are open rather than settled, and both are in
[DECISIONS.md](DECISIONS.md) with their alternatives argued:
[**D20**](DECISIONS.md) is that kit's `none` job installs no interpreter, so the
`kit` job above runs the suite on the runner's own Python and only `gate` is
pinned; [**D21**](DECISIONS.md) is that a breaking schema change still has no
re-vendor fan-out, because core is the tree six services vendor and nothing
currently tells a service owner one is owed.

The self-test step is the one that reads its own log rather than only producing
it: it compares the number of breakages the script's footer *claims* went red
against the number of assertions actually logged, and requires the control to
have run exactly once. That check was proved able to fail — against a log with
three assertions removed, a log with no footer, and a log with the control
removed — because a guard that cannot find its target is not a guard, and a
footer nobody checks is the same claim core-06 got wrong about `uses:`.

## Status

`core` v0.3, unreleased. The five decisions carried in v0.1 are decided and
folded into `docs/`, and a doc that grows a `DECISION NEEDED` callout fails the
suite — the open questions live in
[DECISIONS.md](DECISIONS.md), numbered, and each one cites the files it affects.
Nine are open as of this release: **D13** (where the redaction boundary is
enforced), **D14** (`error.type` granularity), **D15** (the span-name form),
**D16** and **D17** (the endpoint variable, and a divergence between core,
PLAN.md §7b and muse), **D18**/**D19** (which classes are in the `error.type`
vocabulary, and whether the OTel `_OTHER` fallback belongs in a snake_case one),
and **D20**/**D21** (the unpinned interpreter in kit's `none` job, and the
missing re-vendor fan-out). Three more arrived with the harness: **D22** (core's
own suite does not assert `format: uri`, because no installed checker
implements it), **D23** (whether the sixteen rules the harness keeps in code
become a JSON Schema), and **D24** (the event catalog and the spec version are
documents rather than data, which is why the harness parses a markdown table and
cannot resolve a `core:` constraint). See
[CHANGELOG.md](CHANGELOG.md#unreleased) for what changed and
[CHANGELOG.md](CHANGELOG.md#020--2026-09-30) for what v0.2 broke.
