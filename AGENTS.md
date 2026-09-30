# AGENTS.md — working in `cafaye/core`

Read this before changing anything here. `core` is the substrate every other
cafaye service compiles against, so a careless edit is a fleet-wide break.

## The one rule

**A rule that is not in `schemas/` is not a cafaye rule.**

Every convention is a JSON Schema constraint plus a test plus a doc paragraph.
If you find yourself writing a convention into a README and calling it done, it
is not done — it is documentation of a wish. The test is the enforcement.

## Order of work: tests first

Per PLAN.md §3. Concretely, in this repository:

1. Add or change the test in `tests/test_specs.py`.
2. Run `bin/prime` and **show it failing**. A test that has never failed has
   never been proven to test anything.
3. Make it green by changing the schema, an example, or a doc — not by
   loosening the assertion.
4. If the failure is the wrong failure, the test is wrong. Fix the test first.

Loosening an assertion, adding a skip, or bumping a retry to get to green is
how a spec silently stops being enforced. There are no sleeps in this suite
because there is nothing to wait for.

## Editing a schema

- Draft 2020-12. `$schema`, `$id`, `title` and `description` on every file.
- **Always** meta-validate before claiming done — `test_schemas_declare_draft_2020_12`
  calls `check_schema`, so a malformed schema fails loudly.
- Keep `additionalProperties: false` at every level. It is the reason an
  undeclared key is an error instead of a silent no-op.
- Do not duplicate a pattern between the two schemas. `eventType` and
  `serviceName` exist in both; `test_envelope_type_and_source_patterns_match_the_manifest`
  asserts the copies are byte-identical. Change one, change both.
- Every new constraint needs, in the same commit: a positive example under
  `examples/valid/`, a negative case under `examples/invalid/` if it is
  constraining, a row in `examples/invalid/README.md`, and a test.

## Editing docs

- A doc and its schema are the same contract written twice. When they disagree,
  the test fails — that is the point. Fix the wrong one; do not relax the test.
- The event catalog in `docs/event-naming.md` is checked against the schema
  pattern. Adding an event means a catalog row **and** a publisher entry in
  `exposes.events`, in the same commit.
- Every event type is `<service>.<entity>.<action>` — three segments, always
  prefixed, no exceptions. The pattern is duplicated byte-identically in
  `schemas/event-envelope.schema.json` and `schemas/cafaye.manifest.schema.json`
  and a test asserts the copies match, so change one, change both.
- `data` is **not** opaque any more: per-event payload schemas live in core at
  `schemas/events/<service>/<entity>/<action>.schema.json`, with a valid and a
  negative example each. Adding one means the schema, both examples, a row in
  the payload table in `docs/event-naming.md`, and a test.
- `docs/openapi-conventions.md` is capped at roughly two pages. It is a
  checklist, not a handbook. If it grows, something belongs in a service's own
  repo.
- `docs/observability.md` states a **contract**, not a collector. The seven
  schemas under `schemas/telemetry/` say what may go in a span, a metric and a
  log record, and what `*_OTEL_ENDPOINT` means when it is set and when it is
  not. Do **not** add the OpenTelemetry Collector, the LGTM stack, an exporter,
  or a per-language SDK to this repository — that is `kit` and the services, and
  an exporter here is core becoming a runtime, which is the one thing this
  repository is not. The same rule as the outbox: core owns the contract, each
  service ships its own implementation in its own language.
- The **span-name pattern** is duplicated byte-identically in
  `span-naming.schema.json` and `traces.schema.json` on purpose, so a service
  can load either file alone. Change one, change both;
  `test_the_span_name_pattern_is_shared_with_the_traces_schema` says so.
- A **telemetry rule** is a schema plus a test plus a doc paragraph, exactly
  like any other. An attribute that is not on a signal's allowlist is not
  emitted; adding one is a spec change with an example, a README row and a test
  in the same commit.
- Prefer writing the recommendation down over asking. A reversible default with
  a stated trade-off beats a stalled packet.

## Open decisions

Specs are manager-owned: **you draft, the manager decides.**

- Never silently resolve a genuine design question.
- Never resolve it in a way that is hard to reverse either. When you draft a
  default, leave the cheapest possible path to the alternative — the pattern
  you chose, the one line that changes it.
- Mark it `> DECISION NEEDED (Dn):` in the affected doc: what the choice is,
  the alternatives, your recommendation, and the cost of flipping.
- Number sequentially per repository and reference decisions by number
  (`see D3`). One number per decision, ever — a reused number is a broken
  cross-reference, and a reference to a number that does not exist is worse
  than no reference at all.
- Report the open list in your worker report. Undecided and unreported is the
  only real failure.

## Git

- Primary branch is `master` everywhere (PLAN.md §1).
- Work on `worker/<packet-id>`. **Never push. Never create a remote.** The
  manager merges to `master` after reading the diff and running the suite.
- Remotes for anything cafaye owns are SSH (`git@github.com:cafaye/…`), never
  HTTPS — and the manifest schema rejects an HTTPS remote, so a bad habit
  fails the suite.

## Repo hygiene

- No runtime libraries, no services, no dependencies beyond `tests/requirements.txt`.
  `core` is schemas + docs + validators. If a change needs a runtime, it belongs
  in `caf`, not here.
- `docs/event-outbox.md` states a convention, not a library. Do not add a shared
  outbox implementation, migration or package to this repository — each service
  implements it in its own language, and core owns the contract only.
- Do not touch anything outside this worktree.
- Bound long or networked commands with `timeout N`.
