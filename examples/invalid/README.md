# Invalid examples — expected failures

One negative example per schema. Both are **supposed to fail** validation: the
errors below are the contract, not accidents. If one of these files starts
validating, either a schema got looser or an example stopped being a real
mistake — both are review events.

`tests/test_specs.py` asserts the exact `(keyword, path)` pairs listed here, so
the tables cannot drift from the schemas silently.

Reproduce with:

```
bin/prime                                  # both must be reported as rejected
```

or, to see the raw validator output:

```
tests/.venv/bin/python - <<'PY'
import sys; sys.path.insert(0, "tests")
import test_specs as t
for schema, doc in ((t.MANIFEST_SCHEMA_PATH, t.INVALID_MANIFEST),
                    (t.ENVELOPE_SCHEMA_PATH, t.INVALID_ENVELOPE)):
    print(doc.name)
    for f in t.failures_for(t.load_document(doc), t.load_schema(schema)):
        print("   ", f)
PY
```

## `manifest.cafaye.invalid.yml`

Rejected by [`schemas/cafaye.manifest.schema.json`](../../schemas/cafaye.manifest.schema.json).
It is a realistic bad manifest — the mistakes a service actually ships with,
all at once — not a single deliberate typo.

| # | Field | Keyword | Why it is rejected |
| --- | --- | --- | --- |
| 1 | `name: Billing_Service` | `pattern` | Names are lowercase kebab-case. The `name` is also the repo name, the event `source` and the routing prefix, so it cannot carry case or underscores. |
| 2 | `language: python3` | `enum` | Not a cafaye language. The enum is `go`, `ruby`, `elixir`, `python`, `typescript`, `rust`, `spec`. |
| 3 | `core: ^0.1` | `pattern` | A core constraint must be a full `MAJOR.MINOR.PATCH`. A missing patch version silently widens the range. |
| 4 | `exposes.api: ./openapi.yaml` | `pattern` | Must be a repository-relative path with no `./` prefix, no absolute path and no URL — the path is resolved inside the repo by `caf` and by contract tests. |
| 5 | `exposes.events[0]: user.Created` | `pattern` | Event type segments are lowercase snake_case. `Created` would fork the topic away from every existing `user.created` subscription. |
| 6 | `repository.url: https://github.com/…` | `pattern` | SSH remotes only, for anything cafaye or anywaye owns (PLAN.md §1). |
| 7 | `repository.defaultBranch: main` | `const` | The cafaye primary branch is `master` everywhere. |
| 8 | `ports:` | `additionalProperties` | Undeclared top-level key. Manifests are closed on purpose: a key core does not know about cannot be validated, and cannot be enforced. Ports are deployment configuration, not contract surface. |

## `event-envelope.invalid.json`

Rejected by [`schemas/event-envelope.schema.json`](../../schemas/event-envelope.schema.json).
JSON has no comment syntax, so this table is the expected-failure note for
this file.

| # | Field | Keyword | Why it is rejected |
| --- | --- | --- | --- |
| 1 | *(absent)* `specversion` | `required` | The envelope dialect is not optional. A consumer that cannot tell which envelope it is reading cannot decode the rest. |
| 2 | `id: "usr-01J9Z8QK5M4N7P2R3T6V8W9X0A"` | `format` | `id` is a UUID, not a business id. Consumers dedupe on `id`, and business ids are reused across entities — they belong in `subject`/`data`. |
| 3 | `type: "identity.user.account.created"` | `pattern` | Four segments. The grammar is `<entity>.<action>` or `<service>.<entity>.<action>`; there is no room for a container level. |
| 4 | `subject: "user usr_01J9Z8QK5M4N7P2R3T6V8W9X0A"` | `pattern` | `subject` is a bare identifier, never prose. A space also breaks per-entity ordering guarantees, which correlate on this value. |
| 5 | `time: "2026-13-45T99:99:00Z"` | `format` | Not a valid RFC3339 timestamp (month 13, hour 99). |
| 6 | `trace_id: "0af7651916cd43dd8448eb211c80319c"` | `additionalProperties` | Undeclared envelope attribute. The envelope is closed: transport metadata travels in transport headers, so a producer that needs it added must go through a spec change, not a private field. |

Note on the `format` assertions: `jsonschema` silently skips `format` checks
unless a format implementation is installed. `tests/requirements.txt` pins
`rfc3339-validator` precisely so the RFC3339 assertion above cannot pass
vacuously — without it, row 5 would report no violation and this example would
look valid.

## Adding a negative case

A new `examples/invalid/` file needs, in the same commit: the file itself, its
row in the table above, and an `assert_keywords` entry in
`tests/test_specs.py`. A negative example that no test asserts is a comment.
