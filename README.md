# cafaye/core

The substrate every cafaye service compiles against: the service manifest
format, the event envelope, and the HTTP contract conventions. Schemas, docs
and validators — nothing else. There is no runtime here, on purpose; a
service's runtime is that service's problem.

```
schemas/   the machine-readable contract (JSON Schema, draft 2020-12)
  events/  one payload schema per event type, at schemas/events/<type>.schema.json
docs/      the human contract: the same rules, with the reasoning
examples/  one valid and one invalid document per schema
tests/     the executable statement of every rule above
cafaye.yml core's own manifest, validated against core's own schema
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
| [`docs/openapi-conventions.md`](docs/openapi-conventions.md) | error envelope, pagination, versioning, idempotency, auth, deprecation |
| [`examples/invalid/README.md`](examples/invalid/README.md) | the expected failure of every negative example, field by field |

`docs/event-outbox.md` is a convention, not a package. Every service implements
it in its own language against its own database; core states the table and the
loop and deliberately ships no shared code.

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

## Status

`core` v0.2. No open decisions: the five carried in v0.1 are decided and folded
into `docs/`, and a doc that grows a new `DECISION NEEDED` callout fails the
suite until the manager rules on it. See
[CHANGELOG.md](CHANGELOG.md#020--2026-09-30) for what v0.2 broke and what a
downstream service has to do about it.
