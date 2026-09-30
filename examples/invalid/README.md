# Invalid examples — expected failures

One negative example per rule that constrains, per schema. Every file here is
**supposed to fail** validation: the errors below are the contract, not
accidents. If one of these files starts validating, either a schema got looser
or an example stopped being a real mistake — both are review events.

`tests/test_specs.py` asserts the exact `(keyword, path)` pairs listed here, so
the tables cannot drift from the schemas silently. It also walks this directory
and fails on any file whose repo-relative path is missing from this document,
which is what keeps a new negative example from landing as an unreviewed
comment.

Reproduce with:

```
bin/prime                                  # every file here must be reported as rejected
```

or, to see the raw validator output:

```
tests/.venv/bin/python - <<'PY'
import sys; sys.path.insert(0, "tests")
import test_specs as t
for schema, doc in ((t.MANIFEST_SCHEMA_PATH, t.INVALID_MANIFEST),
                    (t.ENVELOPE_SCHEMA_PATH, t.INVALID_ENVELOPE),
                    (t.ENVELOPE_SCHEMA_PATH, t.INVALID_UNTAGGED_ENVELOPE),
                    (t.ENVELOPE_SCHEMA_PATH, t.INVALID_SUBJECTLESS_ENVELOPE)):
    print(doc.name)
    for f in t.failures_for(t.load_document(doc), t.load_schema(schema)):
        print("   ", f)
PY
```

## `examples/invalid/manifest.cafaye.invalid.yml`

Rejected by [`schemas/cafaye.manifest.schema.json`](../../schemas/cafaye.manifest.schema.json).
It is a realistic bad manifest — the mistakes a service actually ships with,
all at once — not a single deliberate typo.

| # | Field | Keyword | Why it is rejected |
| --- | --- | --- | --- |
| 1 | `name: Billing_Service` | `pattern` | Names are lowercase kebab-case. The `name` is also the repo name, the event `source` and the routing prefix, so it cannot carry case or underscores. |
| 2 | `language: python3` | `enum` | Not a cafaye language. The enum is `go`, `ruby`, `elixir`, `python`, `typescript`, `rust`, `spec`. |
| 3 | `core: ^0.1` | `pattern` | A core constraint must be a full `MAJOR.MINOR.PATCH`. A missing patch version silently widens the range. |
| 4 | `exposes.api: ./openapi.yaml` | `pattern` | Must be a repository-relative path with no `./` prefix, no absolute path and no URL — the path is resolved inside the repo by `caf` and by contract tests. |
| 5 | `exposes.events[0]: user.Created` | `pattern` | Two violations in one value. The type is **two** segments, and the grammar is exactly `<service>.<entity>.<action>`; and `Created` is not lowercase snake_case, which would fork the topic away from every existing `identity.user.created` subscription. |
| 6 | `repository.url: https://github.com/…` | `pattern` | SSH remotes only, for anything cafaye or anywaye owns (PLAN.md §1). |
| 7 | `repository.defaultBranch: main` | `const` | The cafaye primary branch is `master` everywhere. |
| 8 | `ports:` | `additionalProperties` | Undeclared top-level key. Manifests are closed on purpose: a key core does not know about cannot be validated, and cannot be enforced. Ports are deployment configuration, not contract surface. |

## `examples/invalid/event-envelope.invalid.json`

Rejected by [`schemas/event-envelope.schema.json`](../../schemas/event-envelope.schema.json).
JSON has no comment syntax, so this table is the expected-failure note for
this file.

| # | Field | Keyword | Why it is rejected |
| --- | --- | --- | --- |
| 1 | *(absent)* `specversion` | `required` | The envelope dialect is not optional. A consumer that cannot tell which envelope it is reading cannot decode the rest. |
| 2 | `id: "usr-01J9Z8QK5M4N7P2R3T6V8W9X0A"` | `format` | `id` is a UUID, not a business id. Consumers dedupe on `id`, and business ids are reused across entities — they belong in `subject`/`data`. |
| 3 | `type: "identity.user.account.created"` | `pattern` | Four segments. The grammar is exactly three: there is no room for a container level. |
| 4 | `subject: "user usr_01J9Z8QK5M4N7P2R3T6V8W9X0A"` | `pattern` | `subject` is a bare identifier, never prose. A space also breaks per-entity ordering guarantees, which correlate on this value. |
| 5 | `time: "2026-13-45T99:99:00Z"` | `format` | Not a valid RFC3339 timestamp (month 13, hour 99). |
| 6 | `trace_id: "0af7651916cd43dd8448eb211c80319c"` | `additionalProperties` | Undeclared envelope attribute. The envelope is closed: transport metadata travels in transport headers, so a producer that needs it added must go through a spec change, not a private field. |

## `examples/invalid/event-envelope.untagged.invalid.json`

Rejected by [`schemas/event-envelope.schema.json`](../../schemas/event-envelope.schema.json).
Every field is legal except the `type`, which is the mistake the file exists to
pin down — the pre-v0.2 short form, still in every subscription from before the
grammar change.

| # | Field | Keyword | Why it is rejected |
| --- | --- | --- | --- |
| 1 | `type: "user.created"` | `pattern` | Two segments. There is no short form: the publisher's own name is the first segment of every event type, because an unprefixed type says what changed and not who changed it. `identity.user.created`, not `user.created`. |

## `examples/invalid/event-envelope.subjectless.invalid.json`

Rejected by [`schemas/event-envelope.schema.json`](../../schemas/event-envelope.schema.json).
A well-formed envelope that simply forgot `subject` — the failure mode of
writing the field from an optional CloudEvents mental model.

| # | Field | Keyword | Why it is rejected |
| --- | --- | --- | --- |
| 1 | *(absent)* `subject` | `required` | `subject` is required, not optional. It is the correlation key that carries per-entity ordering, and an event with no single entity uses the literal `platform` — a required field with a reserved value, never a missing one. |

## `examples/invalid/events/identity/user/created.data.json`

Rejected by [`schemas/events/identity/user/created.schema.json`](../../schemas/events/identity/user/created.schema.json).
A payload with a field the schema never declared and one it requires, missing.
This is the shape of a payload that grew in the publisher's code and never came
back to core.

| # | Field | Keyword | Why it is rejected |
| --- | --- | --- | --- |
| 1 | *(absent)* `email` | `required` | The address is not optional — a consumer that cannot send verification mail has nothing to do with this event. |
| 2 | `favourite_colour` | `additionalProperties` | Undeclared payload field. Payload schemas are closed, so an unknown field is a contract difference to resolve in core, not something a publisher adds in a hurry. |

## `examples/invalid/events/billing/subscription/started.data.json`

Rejected by [`schemas/events/billing/subscription/started.schema.json`](../../schemas/events/billing/subscription/started.schema.json).
The tenancy field is missing and a money field arrived that no schema declares.

| # | Field | Keyword | Why it is rejected |
| --- | --- | --- | --- |
| 1 | *(absent)* `account_id` | `required` | Without the account, the subscription cannot be correlated with the identity-side account, and every query downstream needs a lookup that will not exist. |
| 2 | `amount_minor` | `additionalProperties` | Undeclared money field. Amounts belong to the charge that is actually attempted, which is `billing.payment.succeeded`; a price here would be a second, competing source of truth for what a plan costs. |

Note on the `format` assertions: `jsonschema` silently skips `format` checks
unless a format implementation is installed. `tests/requirements.txt` pins
`rfc3339-validator` precisely so the RFC3339 assertion above cannot pass
vacuously — without it, row 5 would report no violation and this example would
look valid. The `date` format in the fleet case below is checked by
`jsonschema` itself, so it needs nothing extra; the same would not be true of an
RFC3339 assertion, which is why that one is pinned.

## `examples/invalid/fleet.invalid.yml`

Rejected by [`schemas/fleet.schema.json`](../../schemas/fleet.schema.json).
A fleet declaration written by a human, with the mistakes a human makes: the
namespace rule, the wrong manifest path, the wrong branch, a short sha, the
two-segment event types courier shipped, an undeclared key and a read date that
is not a date.

| # | Field | Keyword | Why it is rejected |
| --- | --- | --- | --- |
| 1 | `spec: "0.1"` | `const` | Transcribed against the wrong spec. The field exists so a reader can tell how stale the numbers are, and a wrong value answers that confidently and wrongly. |
| 2 | `readOn: "not-a-date"` | `format` | The one thing that makes `fleet.yml` checkable rather than a claim is that it says when it was true. A value that is not a date has no truth to check. |
| 3 | `name: Billing_Service` | `pattern` | Names are lowercase kebab-case. A fleet entry's name is matched against the first segment of every type the service publishes, so an underscore here silently disables that comparison instead of failing it. |
| 4 | `manifest: manifest.yml` | `const` | Every cafaye service names its manifest `cafaye.yml`. A linter resolving a service's declaration needs one pinned path, not a convention it has to know. |
| 5 | `branch: main` | `const` | The cafaye primary branch is `master` everywhere (PLAN.md §1). A declaration read from any other branch is not a declaration about the fleet. |
| 6 | `sourceCommit: "5475352"` | `pattern` | A short sha is enough to read by and not enough to re-read. The point of recording a commit is that the next reader can re-read the exact bytes the claim was made from. |
| 7 | `events[0]: billing.customer.Created` | `pattern` | `Created` is not lowercase snake_case, which forks the topic away from every existing subscription to the type. |
| 8 | `events[1]: plan.created` | `pattern` | Two segments: no service prefix. This is courier's mistake five times over, and it is the reason `fleet.yml` exists rather than a checklist — the difference between catching it here and shipping it to master. |
| 9 | `publishes:` | `additionalProperties` | Undeclared key. A fleet declaration is closed for the same reason a manifest is: a key the schema does not know about cannot be validated, and a linter that ignores it reports a clean fleet. |

## Adding a negative case

A new `examples/invalid/` file needs, in the same commit: the file itself, its
row in the table above, and an `assert_keywords` entry in
`tests/test_specs.py` — a negative example that no test asserts is a comment,
and a table row that no file backs is a rule nobody is enforcing.
