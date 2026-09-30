# Manifest conventions

`cafaye.yml` is the one file every cafaye repository carries. Its schema is
[`schemas/cafaye.manifest.schema.json`](../schemas/cafaye.manifest.schema.json);
this document explains the parts a schema cannot.

## Shape

```yaml
name: billing                      # required — the cafaye namespace name
description: …                     # one sentence, shown by `caf new` and pantry
language: ruby                     # required — go|ruby|elixir|python|typescript|rust|spec
core: ^0.1.0                       # required — the core spec range this service compiles against

exposes:                           # omit entirely for libraries and spec-only repos
  api: openapi/openapi.yaml        # repo-relative path to an OpenAPI 3.1 document
  events: [subscription.started]   # event types this service publishes

consumes: [user.created]           # event types this service subscribes to
dependencies:                      # other cafaye services, not packages
  - name: identity
    version: ^0.1.0
    required: true                 # false = soft dependency, runs degraded without it

repository:
  url: git@github.com:cafaye/billing.git   # SSH only (PLAN.md §1)
  defaultBranch: master
  visibility: public

owner:
  team: billing
  contact: billing@cafaye.com
```

## Namespace rules

A service `name` is lowercase kebab-case (`^[a-z][a-z0-9]*(-[a-z0-9]+)*$`, 2–40
characters). It is simultaneously the repository name, the Go module path
segment, the event envelope `source`, and the guard routing prefix. Changing one
means changing all of them, which is why the rules are this strict.

Reserved, never usable as a service name: `cafaye`, `caf`, `kit`, `core`,
`docs`, `pantry`.

The schema does **not** enforce the reserved list. `core` is the single
legitimate exception — this repository's own `cafaye.yml` is `name: core` — so
encoding the list as a `not`/`enum` in the schema would make core's manifest
fail the schema core publishes. Until core v1, the list is a review rule, and
`tests/test_specs.py` is the place to add it if the manager wants it
mechanically enforced.

## Semver constraints

The constraint grammar is deliberately tiny:

| Form | Meaning |
| --- | --- |
| `^1.2.3` | `>=1.2.3 <2.0.0` — the default. |
| `~1.2.3` | `>=1.2.3 <1.3.0` — pin the minor. |
| `>=1.2.3` | open-ended floor. |
| `1.2.3` | exactly. |

> DECISION NEEDED (D5): cafaye's own mini-grammar versus a full npm-style
> semver (ranges, `||`, `x`-ranges, hyphen ranges). Mini-grammar is one regex
> and one resolver; full semver costs a dependency and a footgun (`>=1.0.0` on a
> 0.x service is meaningless — `^0.1.0` is `>=0.1.0 <0.2.0`). Recommendation:
> keep the mini-grammar, and make `caf contract` resolve it. Manager decides.

## Rules the schema cannot state

JSON Schema cannot compare two properties of the same instance, so these live in
`tests/test_specs.py` and in review:

1. **A published long-form event type starts with the publisher's own name.**
   `identity.api_key.created` is legal in `identity`; it is a bug anywhere else.
2. **A service never consumes its own events.** If it needs to react to its own
   output, it should call itself in-process instead of paying for a bus.
3. **Any service that serves or receives traffic declares `exposes`.** A
   repository with no `exposes` is a library or a spec repo. `caf dev` and
   `pantry` read this to decide what to run and what to route.
4. **`dependencies` are services, not packages.** A Ruby gem or an npm module
   belongs in the language's own lockfile, not here.
5. **`owner.team` is accountable, not an author.** Renaming a team is a
   changelog-worthy governance event.

## Adding a field

A new top-level key is a **minor** bump of core and requires, in the same
commit: the schema, an example under `examples/valid/`, at least one
`examples/invalid/` case if it is constraining, and a test. Making an optional
field required, tightening a pattern, or adding an enum value that invalidates
an existing manifest is a **major** bump. `core` is pre-1.0, so `0.x` majors are
allowed; state the intent in the PR.

## Why a manifest at all

`caf init`, `caf new`, `caf dev`, `caf gen` (SDKs), `pantry` (registry) and
`guard` (routing) all need the same six facts about a service. Six tools
answering six questions by reading six bespoke config files is how cross-repo
drift starts. One file, one schema, one validator.
