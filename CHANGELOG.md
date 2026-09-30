# Changelog

All notable changes to the cafaye **spec** are recorded here. This repository
is schemas, docs and validators, so "notable" means *a rule changed or a
document was clarified* — not a release of code. Bump guidance lives in
[README.md](README.md#spec-versioning).

Consumers pin a spec range in their manifest (`core: ^0.1.0`), so the
**breaking** section below is the one that matters when a service CI fails to
resolve.

## [Unreleased]

Open decisions for the manager are the `DECISION NEEDED` callouts in `docs/`.
Nothing in this section is decided until the manager says so.

## [0.1.0] — 2026-09-30

First cut of the cafaye contract substrate. Everything below is a new rule, so
nothing here can break an existing service; a service pinned to `^0.1.0` may
move to any `0.1.x` without review.

### Added

- **`schemas/cafaye.manifest.schema.json`** — draft 2020-12 schema for
  `cafaye.yml`: `name` (cafaye namespace rules), `language` enum, the `core`
  spec constraint, `exposes` (OpenAPI path + published event types),
  `consumes`, `dependencies`, `repository` (SSH remotes, `master` default
  branch), and `owner`. Closed with `additionalProperties: false` at every
  level.
- **`schemas/event-envelope.schema.json`** — the envelope every event travels
  in: `id` (UUID), `type` (`<entity>.<action>` or
  `<service>.<entity>.<action>`), `source` (the publishing service), `subject`,
  `time` (RFC3339), opaque `data`, and `specversion`. CloudEvents 1.0 attribute
  names; `specversion` pins the dialect.
- **`docs/event-naming.md`** — the event grammar, the action vocabulary, the
  delivery guarantees, and the initial catalog for **identity** (12 events),
  **billing** (10) and **courier** (5).
- **`docs/openapi-conventions.md`** — the `application/problem+json` error
  envelope, cursor pagination, `/v1` versioning, the `Idempotency-Key` rule,
  JWT auth via identity with a JWKS URL, and the deprecation policy.
- **`docs/manifest-conventions.md`** — manifest shape, namespace rules, the
  core semver mini-grammar, and the five cross-field rules JSON Schema cannot
  express.
- **`examples/`** — four valid manifests (Go API, Ruby API, event-publishing
  worker, worker-only), a valid envelope, and one invalid document per schema
  with the expected failure documented field by field in
  [`examples/invalid/README.md`](examples/invalid/README.md).- **`tests/`** — the contract suite: every valid example validates, every
  invalid example is rejected for its documented reasons, and the docs are
  checked against the schemas. `bin/prime` runs it; `tests/setup.sh` builds the
  venv. The catalog and the example manifests are asserted to agree in both
  directions, so an event cannot be published without being documented or
  documented without being published.
- **`cafaye.yml`** — core's own manifest, `language: spec`, validated against
  core's own schema on every test run.
- **`README.md`**, **`AGENTS.md`**, **`mise.toml`**, **`.gitignore`**.

### Open decisions

Numbered as in the docs. Each is drafted with a default so nothing is blocked;
the manager confirms or flips.

| # | Question | Drafted default |
| --- | --- | --- |
| D1 | two- or three-segment event types | both accepted; service prefix required only for generic entities |
| D2 | is `subject` required? | required, with `platform` as the no-single-entity escape hatch |
| D3 | where does a per-event `data` payload schema live? | none in v0 — the publisher owns it; recommends a future `contracts/` repo |
| D4 | `/v1` path prefix vs. document version | both required, with the sync footgun noted |
| D5 | cafaye's semver mini-grammar vs. full npm semver | keep the mini-grammar, resolve it in `caf contract` |

### Known gaps

- The reserved service-name list (`cafaye`, `caf`, `kit`, `core`, `docs`,
  `pantry`) is a review rule, not a schema constraint — core's own manifest is
  `name: core`, so encoding the list would make core fail its own schema.
- No per-event `data` payload schemas, by design pending D3. Contract tests
  validate the envelope; payload tests are the publisher's.
- No OpenAPI document is shipped. `core` supplies the conventions a service's
  own `openapi/openapi.yaml` must agree with, not the documents themselves.

[Unreleased]: https://cafaye.com/changelog/core
[0.1.0]: https://cafaye.com/changelog/core/v0.1.0
