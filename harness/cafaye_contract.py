#!/usr/bin/env python3
"""The cafaye contract-test harness.

PLAN.md §4 Phase 0 named a contract-test harness among core v0's deliverables.
Three of the other four shipped; this is the fifth, and until now every service
that wanted one wrote its own — muse's pinned-SHA byte comparison, darkroom's
copy of core's schema, courier's document-against-router test, pantry's drift
test. Four mechanisms, no shared harness, which is the platform's headline
artifact declining to be the thing every service builds on.

    harness/bin/cafaye-contract --core ../core .

answers, offline, with nothing installed: does this repository's declared
contract surface agree with core's contracts?

WHY IT IS A SINGLE PYTHON FILE WITH NO DEPENDENCIES
---------------------------------------------------
The fleet is six languages and a service's CI runner is the environment that
matters. A Python *package* would need a venv in a Go repository; a compiled
binary would make core a release repository with per-platform artifacts, which
is the one thing it is not. A single file that imports only the standard library
runs on every runner core and every service already builds on, and it reads
`--core <dir>` — so a service's CI is three lines and no language binding.

That has one real cost, and this file is where it lives: **core's schemas are
JSON Schema, and the standard library has no JSON Schema.** So this file
contains an evaluator for the keywords core's schemas actually use, and
`tests/test_specs.py` proves it is the same answer `jsonschema` gives, over
every example in `examples/`, in both directions and by violated keyword. Read
that test before trusting the evaluator. Two consequences are deliberate:

  - `IMPLEMENTED_KEYWORDS` is exactly the keyword inventory of `schemas/`, and a
    core test fails if the two drift. A keyword this file does not implement is
    a rule the harness does not enforce, and an unenforced rule looks exactly
    like an upheld one.
  - `CHECKED_FORMATS` includes `uri`, which `jsonschema` does **not** check
    without `rfc3987-validator` installed — so on a `format: uri` failure these
    two disagree, and the harness is the stricter one. That is stated in
    docs/contract-harness.md and is decision D22.

THE SAME IS TRUE OF THE YAML READER
-----------------------------------
`cafaye.yml` and every service's OpenAPI document are YAML, PyYAML is not in the
standard library, and adding a dependency is a decision this repository has not
made. So `read_yaml` reads a **declared subset** (`YAML_REFUSALS` is everything
it refuses) and refuses everything else with a file and a line. It never guesses:
a multi-line plain scalar is legal YAML, and folding it one way means validating
a document nobody wrote. A core test proves the reader agrees with PyYAML on
every YAML document core owns.

WHAT IT DOES NOT DO
-------------------
It does not validate live responses against the event payload schemas, and it
does not resolve a `core:` constraint. Both are owed; see
docs/contract-harness.md, which is the document that says so out loud.

EXIT CODES
----------
    0   the service conforms
    1   it does not — every broken rule is on stdout, one per line
    2   the run could not happen: core was not found, the service has no
        manifest, or a file is outside the YAML subset

2 is not a soft 1. A check that could not run, exiting 0, is the defect that has
bitten this fleet four times — guard's live-Redis tier, muse's `MUSE_CORE_SCHEMAS`
tier, identity's `TEST_DATABASE_URL` tier, darkroom's `--ignored` tests — and a
contract check that cannot find the contract is worse than no contract check,
because it converts an unknown into a green badge.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# The minimum interpreter. `from __future__ import annotations` buys the
# `X | None` spelling in annotations; everything else here is 3.8-era.
MINIMUM_PYTHON = (3, 9)

#: Every JSON Schema keyword this evaluator implements, and therefore the exact
#: inventory core's schemas are allowed to use. `$defs` counts because the
#: pointer resolver reads it; `$ref` is resolved, not "followed lazily".
#:
#: The list is asserted equal to the keyword inventory of `schemas/` in both
#: directions by `test_the_harness_implements_every_keyword_core_schemas_use`.
#: A keyword nobody implements is an unenforced rule; a keyword nobody uses is a
#: rule with no test, and both are what a conformance tool cannot afford.
IMPLEMENTED_KEYWORDS = frozenset(
    {
        "$defs",
        "$ref",
        "additionalProperties",
        "allOf",
        "anyOf",
        "const",
        "enum",
        "format",
        "if",
        "items",
        "maxItems",
        "maxLength",
        "maxProperties",
        "maximum",
        "minItems",
        "minLength",
        "minProperties",
        "minimum",
        "not",
        "oneOf",
        "pattern",
        "prefixItems",
        "properties",
        "required",
        "then",
        "type",
        "uniqueItems",
    }
)

#: The `format` values this harness decides. Mirrors `jsonschema`'s own checkers
#: for the four it implements (see its `_format.py`: `email` is "@" in the
#: string, `uuid` is a parseable UUID with dashes in the right places, `date` is
#: `^\d{4}-\d{2}-\d{2}$` and a real calendar date, `date-time` is RFC 3339), and
#: adds `uri`, which `jsonschema` only checks when `rfc3987-validator` is
#: installed. `test_the_harness_checks_the_format_vocabulary_core_uses` fails if
#: a schema names a format outside this set.
CHECKED_FORMATS = frozenset({"date", "date-time", "email", "uri", "uuid"})

#: Every rule id this harness can report. The equality with the ids in
#: `harness/rules.json` is asserted by core's suite; a rule the harness reaches
#: and the inventory does not describe is a rule nobody was told about.
RULE_IDS = (
    "core.absent",
    "core.digest-mismatch",
    "core.not-a-checkout",
    "event.own-prefix",
    "event.no-self-consume",
    "event.payload-schema-missing",
    "event.unknown-consumed",
    "event.unknown-published",
    "manifest.api-file-missing",
    "manifest.schema",
    "openapi.document-is-31",
    "openapi.has-paths",
    "openapi.info-version",
    "openapi.one-version-prefix",
    "openapi.paths-are-versioned",
    "service.manifest-absent",
    "yaml.unsupported",
)

#: The refusal messages, kept in one place because they are a contract too: a
#: service's CI log has to be able to grep for the reason it did not run.
REFUSALS = {
    "core.absent": (
        "no cafaye/core checkout found; pass --core PATH, or set CAFAYE_CORE. "
        "core is offline by contract — the harness never fetches a schema, because a "
        "contract check that needs the network is one nobody runs on an air-gapped runner."
    ),
    "core.not-a-checkout": (
        "that directory is not a cafaye/core checkout: no "
        "schemas/cafaye.manifest.schema.json. A directory that exists is not proof."
    ),
    "service.manifest-absent": (
        "no cafaye.yml at the service root. An empty report's OK is indistinguishable "
        "from the OK of a repository nobody looked at."
    ),
    "yaml.unsupported": (
        "outside the YAML subset this harness reads. The subset is YAML_SUBSET below "
        "and everything refused is YAML_REFUSALS; the harness refuses rather than "
        "guessing, because guessing means validating a document nobody wrote."
    ),
}

#: The YAML constructs `read_yaml` refuses, each with the reason it is refused.
#: This is the honest edge of the reader and it is a contract: adding an entry
#: means the harness now reads a construct it did not, and every consumer needs
#: to know that.
#:
#: Not on this list, because the eleven real service repositories use them and a
#: reader that refuses them is a demonstration rather than a harness: block
#: scalars (`|`, `>` and their chomping and indentation indicators), plain scalars
#: continued across lines, flow collections of scalars including across lines, and
#: the `---` document-start marker. Every one of them was added *after* being
#: pointed at the fleet and watching eight of eleven refuse.
YAML_REFUSALS = {
    "&anchor": "anchors are not read",
    "*alias": "aliases are not read",
    "!tag": "tags are not read",
    "%YAML": "directives are not read",
    "<<": "merge keys are not read",
    "[{": (
        "flow collections of scalars, including across lines — a nested flow "
        "collection, a trailing comma, and a `[` closed with `}` are not read"
    ),
    "tab": "a tab cannot be used for indentation",
    "duplicate key": "a key that appears twice is refused rather than resolved",
    "second document": "a multi-document file is not merged",
}

#: The subset, in one sentence, for the document.
YAML_SUBSET = (
    "block mappings, block sequences, block scalars (| and >, with chomping and "
    "indentation indicators), plain scalars continued across lines, quoted scalars, "
    "flow collections of scalars including across lines, the empty collections [] and "
    "{}, the literals null/true/false, integers, a leading --- document marker, and "
    "comments on their own line or after a value."
)

EXIT_CONFORMS = 0
EXIT_VIOLATIONS = 1
EXIT_REFUSED = 2

#: core's marker for a manifest. Its absence is what makes a directory a core
#: checkout rather than a directory that happens to contain a `schemas/`.
MANIFEST_SCHEMA_RELATIVE = Path("schemas") / "cafaye.manifest.schema.json"
EVENT_CATALOG_RELATIVE = Path("docs") / "event-naming.md"
CATALOG_HEADING = "## Catalog"

SEMVER_VERSION = re.compile(r"^\d+\.\d+\.\d+$")
VERSION_PREFIX = re.compile(r"^/v(\d+)(/|$)")
PATH_PARAM = re.compile(r"\{[^{}]+\}")

# Mirrors jsonschema's `_RE_DATE`, and the same day/month range check
# `rfc3339_validator` does with `calendar.monthrange`.
DATE_SHAPE = re.compile(r"^\d{4}-\d{2}-\d{2}$", re.ASCII)

# YAML 1.2 core floats. `1.2.3` does not match — two dots — which is what keeps a
# core semver constraint a string. An exponent is deliberately not part of it:
# PyYAML resolves `1e3` to a string, so matching one here would be a divergence
# in the other direction. muse's OpenAPI `example:` writes `temperature: 0.2`,
# which is a float and has to read as one.
YAML_FLOAT = re.compile(r"^[-+]?(?:[0-9]+\.[0-9]*|\.[0-9]+)$", re.ASCII)

# RFC 3339, section 5.6, as `rfc3339_validator` spells it — the same library
# `tests/requirements.txt` pins, mirrored because this file may not import it.
# `jsonschema` upper-cases before validating, so a lowercase `t`/`z` is accepted
# here too; matching that is the point.
RFC3339 = re.compile(
    r"""
    ^
    (\d{4})
    -
    (0[1-9]|1[0-2])
    -
    (\d{2})
    [Tt]
    (?:[01]\d|2[0123])
    :
    (?:[0-5]\d)
    :
    (?:[0-5]\d)
    (?:\.\d+)?
    (?:
      [Zz]
      | [+-](?:[01]\d|2[0123]):[0-5]\d
    )
    $
    """,
    re.VERBOSE | re.ASCII,
)

# RFC 3986 URI, reduced to what `rfc3987.parse(rule="URI")` decides for the
# values core's schemas carry: an absolute URI with a scheme, and no whitespace
# or control characters anywhere in it. Deliberately conservative: the harness
# must never reject a value `jsonschema` accepts, because core's own suite is the
# reference and a disagreement here is a false accusation.
URI_SHAPE = re.compile(r"^[A-Za-z][A-Za-z0-9+.\-]*:[^\s\x00-\x20\x7f]*$", re.ASCII)

_DAYS_IN_MONTH = (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)


# --------------------------------------------------------------------------
# results
# --------------------------------------------------------------------------


class Refusal(Exception):
    """The run could not happen.

    Carries a rule id from `RULE_IDS`, so a refusal is as greppable as a
    violation and neither of them is ever exit 0. The *location* is a separate
    field rather than part of the message, because the finding that wraps it
    already prints the path and a refusal that names its file twice reads like
    two failures.
    """

    def __init__(self, rule: str, path: str = "", detail: str = "") -> None:
        self.rule = rule
        self.path = path
        self.detail = detail
        message = REFUSALS.get(rule, rule)
        if detail:
            message = f"{message} ({detail})"
        super().__init__(message)


@dataclass(frozen=True)
class Violation:
    """One schema violation, flattened for a readable assertion.

    The three fields mirror `tests/test_specs.py`'s `Failure`, which is
    deliberate: the harness and the suite are comparing the same thing about the
    same schemas, and the equivalence test reads better when both sides are the
    same shape.
    """

    keyword: str
    path: str
    message: str

    def __str__(self) -> str:
        where = self.path or "<root>"
        return f"{where}: {self.message} [{self.keyword}]"


@dataclass(frozen=True)
class Finding:
    """One broken rule, as a service's CI sees it."""

    rule: str
    path: str
    message: str

    def __str__(self) -> str:
        where = self.path or "<root>"
        return f"FAIL {self.rule} {where}: {self.message}"


@dataclass
class Result:
    """Everything one run produced. `exit_code` is the only thing to branch on.

    `refused` is what separates "the service does not conform" from "the run did
    not happen", and the two are different exit codes. Collapsing them is how a
    check that could not find the contract ends up reporting success: both cases
    produce a non-empty `findings`, so a caller branching on "did I get any
    output" cannot tell them apart, and a caller branching on the exit code
    reads 2 as 1 and files it as a contract bug rather than as a missing
    checkout.
    """

    service_root: Path
    core_root: Path | None
    digest: str | None
    findings: tuple[Finding, ...] = ()
    stopped_after_schema: bool = False
    core_commit: str | None = None
    refused: bool = False

    @property
    def exit_code(self) -> int:
        if self.refused:
            return EXIT_REFUSED
        if self.findings:
            return EXIT_VIOLATIONS
        return EXIT_CONFORMS

    @property
    def rules(self) -> tuple[str, ...]:
        return tuple(finding.rule for finding in self.findings)


# --------------------------------------------------------------------------
# the JSON Schema evaluator
# --------------------------------------------------------------------------
#
# Draft 2020-12, for the keywords in `IMPLEMENTED_KEYWORDS` and no others. The
# semantics that are easy to get wrong, and what the right answer is:
#
#   * `$ref` does not replace the schema. In 2020-12 a `$ref`'s siblings apply
#     alongside whatever the pointer resolves to, so both are evaluated.
#   * `if` never reports. It is a condition; only `then` produces violations, and
#     only when the condition held. A schema that used `if` as a validator would
#     report failures of its own precondition as failures of the document.
#   * `allOf` reports its subschemas' own keywords, not `allOf`; `oneOf` and
#     `anyOf` report themselves, because "matched two of two" has no better name.
#   * `true` and `false` are not integers and are not numbers. Every library
#     agrees and it is still worth writing down.
#   * `pattern` is an unanchored ECMA-262 regular expression, so `re.search` is
#     right and `re.match` would reject a document `jsonschema` accepts.


def _type_matches(value: Any, name: str) -> bool:
    if name == "object":
        return isinstance(value, dict)
    if name == "array":
        return isinstance(value, list)
    if name == "string":
        return isinstance(value, str)
    if name == "boolean":
        return isinstance(value, bool)
    if name == "null":
        return value is None
    if name == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if name == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    # An unknown type name matches nothing, which is what draft 2020-12 says.
    return False


def _json_type_name(value: Any) -> str:
    """The JSON type name, for a message. `bool` before `int`, deliberately."""
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return "null"


def _resolve_pointer(root: Any, pointer: str) -> Any:
    """A local JSON Pointer, `#` and `#/…` only.

    Non-local references are refused rather than skipped. Every `$ref` in core's
    schemas is local — `test_the_harness_evaluator_agrees_with_jsonschema_on_every_example`
    would not notice a `$ref` it silently ignored — so an external one means a
    schema that wants to be fetched, and the harness is offline by contract.
    """
    if pointer in ("", "#"):
        return root
    if not pointer.startswith("#/"):
        raise Refusal("core.not-a-checkout", pointer, "only local $ref pointers are resolvable")
    node = root
    for raw in pointer[2:].split("/"):
        token = raw.replace("~1", "/").replace("~0", "~")
        if isinstance(node, list):
            node = node[int(token)]
        elif isinstance(node, dict):
            node = node[token]
        else:
            raise Refusal("core.not-a-checkout", pointer, f"{token} is not in the schema")
    return node


def _format_ok(value: Any, name: str) -> bool:
    if name not in CHECKED_FORMATS:
        return True
    if not isinstance(value, str):
        return True
    if name == "email":
        return "@" in value
    if name == "uuid":
        return _is_uuid(value)
    if name == "date":
        return _is_date(value)
    if name == "date-time":
        return _is_rfc3339(value)
    return bool(URI_SHAPE.match(value))


def _is_uuid(value: str) -> bool:
    """`uuid.UUID(value)` plus dashes in the canonical places.

    The dash check is the part `jsonschema` adds: the parser alone accepts the
    32-hex and the braced forms, and core's envelope is a wire format with one
    spelling.
    """
    stripped = value.strip()
    candidate = stripped
    if candidate.startswith("{") and candidate.endswith("}"):
        candidate = candidate[1:-1]
    if candidate.startswith("urn:uuid:"):
        candidate = candidate[9:]
    body = candidate.replace("-", "")
    if len(body) != 32 or any(character not in "0123456789abcdefABCDEF" for character in body):
        return False
    if candidate == body:
        return False
    return all(stripped[position] == "-" for position in (8, 13, 18, 23))


def _is_date(value: str) -> bool:
    if not DATE_SHAPE.match(value):
        return False
    year, month, day = (int(part) for part in value.split("-"))
    if not 1 <= month <= 12:
        return False
    limit = _DAYS_IN_MONTH[month - 1]
    if month == 2 and (year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)):
        limit = 29
    return 1 <= day <= limit


def _is_rfc3339(value: str) -> bool:
    match = RFC3339.match(value.upper())
    if match is None:
        return False
    year, month, day = (int(part) for part in match.groups())
    if year == 0:
        return False
    return 1 <= day <= _DAYS_IN_MONTH[month - 1] + (
        1 if month == 2 and year % 4 == 0 and (year % 100 != 0 or year % 400 == 0) else 0
    )


def _equal(left: Any, right: Any) -> bool:
    """JSON equality, with `true` and `1` kept apart.

    `1 == True` in Python and `1` is not `true` in JSON, so a `const: true`
    would accept `1` under a naive comparison — which is a real accept-bug, not
    a theoretical one.
    """
    if isinstance(left, bool) != isinstance(right, bool):
        return False
    if isinstance(left, dict) and isinstance(right, dict):
        return left.keys() == right.keys() and all(_equal(left[k], right[k]) for k in left)
    if isinstance(left, list) and isinstance(right, list):
        return len(left) == len(right) and all(_equal(a, b) for a, b in zip(left, right))
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return left == right
    return type(left) is type(right) and left == right


def _hashable(value: Any) -> str:
    """A canonical JSON rendering, for `uniqueItems`.

    `json.dumps` with sorted keys and no spaces, so `[1, 2]` and `[2, 1]` differ
    and `{"a": 1, "b": 2}` matches a reordering of itself — the two cases a
    `set` gets wrong.
    """
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def evaluate(instance: Any, schema: Any, root: Any = None, path: str = "") -> list[Violation]:
    """Every way `instance` fails `schema`, as a flat list.

    `root` is the document the schema came from, which is what makes `$ref` and
    `$defs` resolvable; it defaults to `schema` so a caller validating against a
    self-contained document need not pass it.
    """
    if root is None:
        root = schema
    if schema is True or schema == {}:
        return []
    if schema is False:
        return [Violation(keyword="false", path=path, message="no value is allowed here")]
    if not isinstance(schema, dict):
        raise Refusal("core.not-a-checkout", path, f"a schema must be an object, got {type(schema)}")

    found: list[Violation] = []

    if "$ref" in schema:
        target = _resolve_pointer(root, schema["$ref"])
        found.extend(evaluate(instance, target, root, path))

    where = "the value" if not path else path

    names = _as_names(schema.get("type"))
    # A `type` array is a union: the value passes if it matches **any** member.
    # Reporting a violation per non-matching member turns a union of seven into
    # six failures for a document that is perfectly valid, and a rule that fires
    # on valid input is a rule nobody trusts.
    if names and not any(_type_matches(instance, name) for name in names):
        found.append(Violation(
            keyword="type", path=path,
            message=f"{where} is {_json_type_name(instance)}, not any of {names}",
        ))

    if "const" in schema and not _equal(instance, schema["const"]):
        found.append(Violation(
            keyword="const", path=path,
            message=f"{where} must be {schema['const']!r}, not {instance!r}",
        ))

    if "enum" in schema and not any(_equal(instance, option) for option in schema["enum"]):
        found.append(Violation(
            keyword="enum", path=path,
            message=f"{where} must be one of {schema['enum']!r}, not {instance!r}",
        ))

    if isinstance(instance, str):
        found.extend(_string_violations(instance, schema, path, where))
    if isinstance(instance, (int, float)) and not isinstance(instance, bool):
        if "minimum" in schema and instance < schema["minimum"]:
            found.append(Violation(
                keyword="minimum", path=path,
                message=f"{where} is {instance}, below the minimum {schema['minimum']}",
            ))
        if "maximum" in schema and instance > schema["maximum"]:
            found.append(Violation(
                keyword="maximum", path=path,
                message=f"{where} is {instance}, above the maximum {schema['maximum']}",
            ))
    if isinstance(instance, list):
        found.extend(_array_violations(instance, schema, root, path, where))
    if isinstance(instance, dict):
        found.extend(_object_violations(instance, schema, root, path, where))

    for keyword in ("allOf", "anyOf", "oneOf"):
        if keyword not in schema:
            continue
        found.extend(_combinator_violations(keyword, instance, schema[keyword], root, path, where))

    if "not" in schema and not evaluate(instance, schema["not"], root, path):
        found.append(Violation(
            keyword="not", path=path,
            message=f"{where} matches a shape core forbids here",
        ))

    # `if` is a condition, not a validator: its own failures are never reported,
    # and `then` runs only when it held. `else` is not implemented because no
    # schema in core uses it, and an implemented-but-unused keyword is a rule
    # with no test.
    if "if" in schema and not evaluate(instance, schema["if"], root, path):
        if "then" in schema:
            found.extend(evaluate(instance, schema["then"], root, path))

    return found


def _as_names(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    return [name for name in value if isinstance(name, str)]


def _string_violations(instance: str, schema: dict, path: str, where: str) -> list[Violation]:
    found = []
    if "minLength" in schema and len(instance) < schema["minLength"]:
        found.append(Violation(
            keyword="minLength", path=path,
            message=f"{where} is {len(instance)} characters, minimum {schema['minLength']}",
        ))
    if "maxLength" in schema and len(instance) > schema["maxLength"]:
        found.append(Violation(
            keyword="maxLength", path=path,
            message=f"{where} is {len(instance)} characters, maximum {schema['maxLength']}",
        ))
    if "pattern" in schema and not _pattern_search(schema["pattern"], instance):
        found.append(Violation(
            keyword="pattern", path=path,
            message=f"{where} does not match {schema['pattern']}",
        ))
    if "format" in schema and not _format_ok(instance, schema["format"]):
        found.append(Violation(
            keyword="format", path=path,
            message=f"{where} is not a valid {schema['format']}: {instance!r}",
        ))
    return found


def _pattern_search(pattern: str, value: str) -> bool:
    r"""ECMA-262 regular expressions, which are not Python's.

    One difference matters for core's schemas, and it would make the harness
    *stricter* than the reference — a false accusation, which is worse than a
    miss here. A digit class in ECMA-262 is ASCII-only while Python's is
    Unicode, so `"١٢٣"` would satisfy a pattern Python matches and a schema
    that means three ASCII digits does not. The pattern is therefore compiled
    with the ASCII flag, which is what `jsonschema` and `rfc3339_validator` both
    do.
    """
    try:
        return re.search(pattern, value, re.ASCII) is not None
    except re.error as error:
        raise Refusal("core.not-a-checkout", pattern, f"not a usable regular expression: {error}")


def _array_violations(instance: list, schema: dict, root: Any, path: str, where: str) -> list[Violation]:
    found = []
    if "minItems" in schema and len(instance) < schema["minItems"]:
        found.append(Violation(
            keyword="minItems", path=path,
            message=f"{where} has {len(instance)} items, minimum {schema['minItems']}",
        ))
    if "maxItems" in schema and len(instance) > schema["maxItems"]:
        found.append(Violation(
            keyword="maxItems", path=path,
            message=f"{where} has {len(instance)} items, maximum {schema['maxItems']}",
        ))
    if schema.get("uniqueItems") and len(instance) != len({_hashable(item) for item in instance}):
        found.append(Violation(
            keyword="uniqueItems", path=path,
            message=f"{where} repeats a value and the schema says each is unique",
        ))
    positional = schema.get("prefixItems") or []
    for index, subschema in enumerate(positional):
        if index < len(instance):
            found.extend(evaluate(instance[index], subschema, root, _join(path, index)))
    if "items" in schema:
        for index in range(len(positional), len(instance)):
            found.extend(evaluate(instance[index], schema["items"], root, _join(path, index)))
    return found


def _object_violations(
    instance: dict, schema: dict, root: Any, path: str, where: str
) -> list[Violation]:
    found = []
    for name in schema.get("required", []):
        if name not in instance:
            found.append(Violation(
                keyword="required", path=path,
                message=f"{where} is missing the required {name!r}",
            ))
    if "minProperties" in schema and len(instance) < schema["minProperties"]:
        found.append(Violation(
            keyword="minProperties", path=path,
            message=f"{where} has {len(instance)} keys, minimum {schema['minProperties']}",
        ))
    if "maxProperties" in schema and len(instance) > schema["maxProperties"]:
        found.append(Violation(
            keyword="maxProperties", path=path,
            message=f"{where} has {len(instance)} keys, maximum {schema['maxProperties']}",
        ))

    properties = schema.get("properties") or {}
    extra = schema.get("additionalProperties", True)
    for name, value in instance.items():
        child = _join(path, name)
        if name in properties:
            found.extend(evaluate(value, properties[name], root, child))
        elif extra is False:
            # The path is the object, not the key: this is the error that says
            # "core does not know this field", and it is about the object.
            found.append(Violation(
                keyword="additionalProperties", path=path,
                message=f"{where} declares {name!r}, which core's schema does not have",
            ))
        elif extra is not True:
            found.extend(evaluate(value, extra, root, child))
    return found


def _combinator_violations(
    keyword: str, instance: Any, subschemas: list, root: Any, path: str, where: str
) -> list[Violation]:
    if keyword == "allOf":
        found = []
        for subschema in subschemas:
            found.extend(evaluate(instance, subschema, root, path))
        return found
    matched = sum(1 for subschema in subschemas if not evaluate(instance, subschema, root, path))
    if keyword == "anyOf" and matched == 0:
        return [Violation(
            keyword="anyOf", path=path,
            message=f"{where} matches none of the {len(subschemas)} shapes core allows here",
        )]
    if keyword == "oneOf" and matched != 1:
        return [Violation(
            keyword="oneOf", path=path,
            message=(
                f"{where} matches {matched} of the {len(subschemas)} shapes core allows here, "
                "and oneOf means exactly one"
            ),
        )]
    return []


def _join(path: str, part: Any) -> str:
    return f"{path}/{part}" if path else str(part)


# --------------------------------------------------------------------------
# the YAML reader
# --------------------------------------------------------------------------
#
# A declared subset, and the honest edge of it is `YAML_REFUSALS` above: every
# construct this will not read, with the reason. The reader exists because the
# standard library has no YAML and adding a dependency is a decision this
# repository has not made — so it reads what `cafaye.yml` and an OpenAPI
# document actually contain, and refuses the rest.
#
# WHAT THE SUBSET IS, and how it was chosen
# ----------------------------------------
# Not by taste. The first version of this reader refused block scalars, flow
# collections and continued plain scalars, and then it was pointed at the eleven
# real service repositories in the cafaye workspace: **eight of eleven
# refused** — six on a `description:` field in their OpenAPI document, two on a
# leading `---`, and the rest on `tags: [users]`. A harness that cannot read the
# documents it exists to check is a demonstration, so all of it is in, and the
# subset is now the one the fleet writes rather than the one that was convenient
# to parse. What the fleet writes is the whole justification: every construct
# below is here because a real `cafaye.yml` or a real `openapi/*.yaml` in the
# workspace uses it, and nothing is here because it was easy.
#
# WHY `raw` IS KEPT
# -----------------
# A block scalar's body is content, not structure: a `#` in it is a hash, a blank
# line in it is a newline, and a `key: value` line in it is a sentence. The first
# version stripped comments and blank lines once, up front, and could not have
# read a block scalar correctly even if it had tried — the information is gone by
# the time the parser sees the line. So every line keeps its original text and
# the structural parsers skip blanks explicitly. That is the whole difference
# between the two designs, and it is why `_Line` carries four fields rather than
# three.
#
# WHAT IS STILL REFUSED
# ---------------------
# Anchors, aliases, tags, merge keys, non-empty flow collections, multi-line
# plain scalars, tab indentation, and duplicate keys. None of them appears in
# the eleven real service repositories. The first version *accepted* the first
# three by accident — a refusal loop compared a value starting `&` against the
# key `"&anchor"` and matched nothing — and
# `test_the_harness_yaml_reader_refuses_only_what_it_declares` probes for exactly
# those three, which is the only reason it was caught.


class _Line:
    """One physical line, parsed lazily into the two views a reader needs.

    `text` and `indent` are the *structural* view: comments removed, surrounding
    whitespace gone. `raw` is the line as written, and is the only thing a block
    scalar body may be read from.
    """

    __slots__ = ("number", "raw", "text", "indent", "blank")

    def __init__(self, number: int, raw: str) -> None:
        self.number = number
        self.raw = raw.rstrip("\n").rstrip("\r")
        stripped = _strip_comment(self.raw)
        self.blank = not stripped.strip()
        self.text = stripped.strip()
        self.indent = len(stripped) - len(stripped.lstrip(" "))


def read_yaml(text: str, path: Path) -> Any:
    """Read the declared subset, or refuse with a file and a line."""
    lines = _all_lines(text, path)
    index = _skip_blank(lines, 0)
    if index >= len(lines):
        return None
    if lines[index].text in ("---", "..."):
        # A document-start marker is not a construct anybody writes by accident;
        # two of the eleven real manifests open with one. A *second* `---` is a
        # multi-document file, which this reader does not merge, and refusing is
        # the only honest answer.
        index = _skip_blank(lines, index + 1)
        if index >= len(lines):
            return None
        if lines[index].text == "---":
            raise Refusal(
                "yaml.unsupported", f"{path}:{lines[index].number}",
                "a second document in one file; this reader reads the first and does not merge",
            )
    value, index = _parse_block(lines, index, lines[index].indent, path)
    index = _skip_blank(lines, index)
    if index < len(lines) and lines[index].text not in ("...",):
        orphan = lines[index]
        continuation = _plain_key_end(orphan.text) is None and not orphan.text.startswith("- ")
        reason = (
            "this continues the value on the line above it; a multi-line plain scalar folds "
            "to a single line and this harness does not fold anything"
            if continuation
            else "this line is not part of the block above it"
        )
        raise Refusal("yaml.unsupported", f"{path}:{orphan.number}", reason)
    return value


def _all_lines(text: str, path: Path) -> list[_Line]:
    lines: list[_Line] = []
    for number, raw in enumerate(text.splitlines(), start=1):
        leading = raw[: len(raw) - len(raw.lstrip())]
        if "\t" in leading:
            raise Refusal(
                "yaml.unsupported", f"{path}:{number}", "a tab cannot be used for indentation"
            )
        lines.append(_Line(number, raw))
    return lines


def _skip_blank(lines: list[_Line], index: int) -> int:
    while index < len(lines) and lines[index].blank:
        index += 1
    return index


def _strip_comment(line: str) -> str:
    """Drop a comment, respecting quotes so a `#` inside a quoted scalar survives.

    Only ever applied to the structural view. A `#` inside a block scalar is
    content and never reaches here, because a block body is read from `raw`.
    """
    quote = ""
    for index, character in enumerate(line):
        if quote:
            if character == quote:
                quote = ""
            continue
        if character in "\"'":
            quote = character
            continue
        if character == "#" and (index == 0 or line[index - 1] in " \t"):
            return line[:index]
    return line


def _parse_block(lines: list[_Line], index: int, indent: int, path: Path) -> tuple[Any, int]:
    index = _skip_blank(lines, index)
    if index >= len(lines):
        return None, index
    if lines[index].text == "-" or lines[index].text.startswith("- "):
        return _parse_sequence(lines, index, indent, path)
    return _parse_mapping(lines, index, indent, path)


def _parse_mapping(lines: list[_Line], index: int, indent: int, path: Path) -> tuple[dict, int]:
    mapping: dict[str, Any] = {}
    while True:
        index = _skip_blank(lines, index)
        if index >= len(lines) or lines[index].indent != indent:
            return mapping, index
        line = lines[index]
        if line.text == "-" or line.text.startswith("- "):
            return mapping, index
        key, rest = _split_key(line, path)
        if key == "<<":
            raise Refusal("yaml.unsupported", f"{path}:{line.number}", YAML_REFUSALS["<<"])
        if key in mapping:
            raise Refusal(
                "yaml.unsupported", f"{path}:{line.number}",
                f"{key!r} appears twice; the harness refuses rather than pick one",
            )
        index += 1
        if rest == "":
            after = _skip_blank(lines, index)
            if after < len(lines) and lines[after].indent > indent:
                if lines[after].text[:1] in ("[", "{"):
                    # `required:` with the flow sequence on the next line. Two of
                    # the six real OpenAPI documents in the fleet write it this
                    # way, and it is the same value as the one-line form.
                    mapping[key], index = _parse_value(
                        lines[after].text, lines[after], lines, after + 1, indent, path
                    )
                else:
                    # A nested block, or nothing — which is what YAML says for
                    # `consumes:` with no list.
                    mapping[key], index = _parse_block(lines, after, lines[after].indent, path)
            else:
                mapping[key] = None
        else:
            mapping[key], index = _parse_value(rest, line, lines, index, indent, path)


def _parse_sequence(lines: list[_Line], index: int, indent: int, path: Path) -> tuple[list, int]:
    items: list[Any] = []
    while True:
        index = _skip_blank(lines, index)
        if index >= len(lines) or lines[index].indent != indent:
            return items, index
        line = lines[index]
        if not (line.text == "-" or line.text.startswith("- ")):
            return items, index
        body = line.text[1:].strip()
        index += 1
        if body == "":
            after = _skip_blank(lines, index)
            if after < len(lines) and lines[after].indent > indent:
                value, index = _parse_block(lines, after, lines[after].indent, path)
            else:
                value = None
            items.append(value)
            continue
        # `- key: value` opens a mapping whose first key sits on the dash line.
        # The dash is two characters of indentation, so the mapping's own indent
        # is derived from the file rather than assumed to be two — the same
        # discipline courier's `OpenAPIPaths` uses, for the same reason.
        if _looks_like_key(body, path, line):
            item_indent = indent + (len(line.text) - len(body))
            # Padded, not bare: `_Line` derives its indent from the raw text, and
            # passing the stripped body produced a line at column 0 that the
            # mapping parser rejected as a dedent — so every `- name: x` in the
            # fleet read as `{}` and the harness reported two real manifests as
            # missing a required field.
            synthetic = [_Line(line.number, " " * item_indent + body)]
            while index < len(lines) and (lines[index].blank or lines[index].indent >= item_indent):
                synthetic.append(lines[index])
                index += 1
            value, _ = _parse_mapping(synthetic, 0, item_indent, path)
            items.append(value)
        else:
            items.append(_parse_value(body, line, lines, index, indent, path)[0])
    return items, index


def _split_key(line: _Line, path: Path) -> tuple[str, str]:
    """The key, and whatever is on the line after the `:` (possibly nothing).

    Returns the value *unparsed*: it may be a block-scalar header, which only
    `_parse_value` knows how to consume, so splitting it here and deciding later
    is the only order that works.
    """
    text = line.text
    if text[0] in "\"'":
        quote = text[0]
        offset = 1
        while offset < len(text) and text[offset] != quote:
            offset += 2 if text[offset] == "\\" else 1
        if offset >= len(text):
            raise Refusal("yaml.unsupported", f"{path}:{line.number}", "an unterminated quoted key")
        key = _unquote(text[: offset + 1])
        rest = text[offset + 1 :]
        if not rest.startswith(":"):
            raise Refusal("yaml.unsupported", f"{path}:{line.number}", "expected `:` after the key")
        return key, rest[1:].strip()
    marker = _plain_key_end(text)
    if marker is None:
        raise Refusal(
            "yaml.unsupported", f"{path}:{line.number}",
            f"{text!r} is not `key: value`, and a bare scalar is not read",
        )
    return text[:marker].strip(), text[marker + 1 :].strip()


def _plain_key_end(text: str) -> int | None:
    """The index of the `:` that ends a plain key, or None.

    A `:` inside a plain scalar does not end a key, and `url:
    git@github.com:cafaye/x.git` is the case that proves it: the second colon is
    not followed by a space, so it is part of the value.
    """
    for index, character in enumerate(text):
        if character != ":":
            continue
        if index + 1 == len(text):
            return index
        if text[index + 1] in " \t":
            return index
    return None


def _looks_like_key(body: str, path: Path, line: _Line) -> bool:
    try:
        _split_key(_Line(line.number, body), path)
    except Refusal:
        return False
    return True


def _parse_value(
    text: str, line: _Line, lines: list[_Line], index: int, indent: int, path: Path
) -> tuple[Any, int]:
    """The value on a `key:` line, and the index the node ended at.

    Both are returned because a block scalar's value is a string, so it cannot
    also say "and here is where the node ended" — and a side channel for that
    would be a worse answer than a tuple.
    """
    value = text.strip()
    if not value:
        return None, index
    # An anchor, alias or tag is a whole node property, so it precedes the value
    # rather than being one. Checked one indicator at a time — a loop over
    # YAML_REFUSALS looked tidier and matched nothing, because the keys are
    # `&anchor` and the values start with `&`.
    if value[0] == "&":
        raise Refusal("yaml.unsupported", f"{path}:{line.number}", YAML_REFUSALS["&anchor"])
    if value[0] == "*":
        raise Refusal("yaml.unsupported", f"{path}:{line.number}", YAML_REFUSALS["*alias"])
    if value[0] == "!":
        raise Refusal("yaml.unsupported", f"{path}:{line.number}", YAML_REFUSALS["!tag"])
    if value[0] == "%":
        raise Refusal("yaml.unsupported", f"{path}:{line.number}", YAML_REFUSALS["%YAML"])
    if value[0] in "|>":
        return _read_block_scalar(value, line, lines, index, indent, path)
    if value[0] in "[{":
        value, index = _read_flow_span(value, lines, index, indent, path)
        return _parse_scalar(value, line, path), index
    if value[0] in "\"'":
        return _parse_scalar(value, line, path), index
    # A plain scalar continued onto the following lines. Legal YAML, folded like
    # a `>` block, and one of the six real OpenAPI documents in the fleet writes
    # a `description:` this way — so refusing it meant refusing the fleet, which
    # is the same trade this reader already made for block scalars.
    #
    # The test for "is this a continuation" is structural: a deeper line that is
    # neither `key: value` nor a `- ` item continues the scalar, and anything
    # else ends it. A deeper line that *is* a key after a plain scalar is illegal
    # YAML, and is refused rather than resolved.
    parts, index = _read_plain_continuation(value, line, lines, index, indent, path)
    return _parse_scalar(_fold_parts(parts), line, path), index


def _read_plain_continuation(
    value: str, line: _Line, lines: list[_Line], index: int, indent: int, path: Path
) -> tuple[list[tuple[str, int]], int]:
    """The pieces of a continued plain scalar, as `(text, blank_lines_before)`.

    Note what is *not* here: a more-indented case. YAML folds a continued plain
    scalar to a space no matter how far the continuation is indented — checked
    against PyYAML, which returns `"two lines"` for `d: two` continued by two,
    four and six spaces alike — so the earlier version's indentation test was
    inventing a distinction the specification does not make. A block scalar has
    that rule; a plain scalar does not, and `_fold` is where the difference
    lives.
    """
    parts: list[tuple[str, int]] = [(value, 0)]
    blanks = 0
    while index < len(lines):
        candidate = lines[index]
        if candidate.blank:
            blanks += 1
            index += 1
            continue
        if candidate.indent <= indent:
            break
        if candidate.text == "-" or candidate.text.startswith("- "):
            break
        if _looks_like_key(candidate.text, path, candidate):
            raise Refusal(
                "yaml.unsupported", f"{path}:{candidate.number}",
                f"{candidate.text!r} follows the scalar on the line above it; a plain scalar "
                "cannot be continued into a mapping",
            )
        parts.append((candidate.text, blanks))
        blanks = 0
        index += 1
    # Trailing blank lines belong to whatever follows, not to this scalar, and
    # the structural parsers skip blanks themselves — so they are not returned.
    return parts, index


def _fold_parts(parts: list[tuple[str, int]]) -> str:
    """Fold a continued plain scalar: a break is a space, a blank line a newline.

    Two rules, and the third one people expect — a more-indented line keeping
    its break — belongs to a *folded block scalar* and not to this.
    """
    folded = parts[0][0]
    for text, blanks in parts[1:]:
        folded += "\n" * blanks if blanks else " "
        folded += text
    return folded


def _read_flow_span(
    value: str, lines: list[_Line], index: int, indent: int, path: Path
) -> tuple[str, int]:
    """Join a flow collection that continues onto the following lines.

    `required:` followed by an indented `[a, b,` and then `c, d]` is legal YAML
    and billing's OpenAPI document writes it that way with fourteen fields across
    two lines. Joining `text` — the comment-stripped view — is right here, because
    inside a flow collection a `#` is still a comment.
    """
    buffer = [value]
    while not _flow_complete("".join(buffer)):
        if index >= len(lines):
            last = lines[index - 1].number if index else 0
            raise Refusal(
                "yaml.unsupported", f"{path}:{last}",
                "the flow collection opened here never closes",
            )
        candidate = lines[index]
        index += 1
        if candidate.blank:
            continue
        if candidate.indent <= indent:
            raise Refusal(
                "yaml.unsupported", f"{path}:{candidate.number}",
                "the flow collection opened above it never closes",
            )
        buffer.append(" " + candidate.text)
    return "".join(buffer), index


def _flow_complete(text: str) -> bool:
    """Whether every bracket opened in a flow collection has been closed."""
    depth = 0
    quote = ""
    for character in text:
        if quote:
            if character == quote:
                quote = ""
            continue
        if character in "\"'":
            quote = character
        elif character in "[{":
            depth += 1
        elif character in "]}":
            depth -= 1
    return depth == 0 and not quote


def _parse_scalar(text: str, line: _Line, path: Path) -> Any:
    value = text.strip()
    if value[0] in "[{":
        return _parse_flow(value, line, path)
    return _scalar_value(value, line, path)


def _scalar_value(value: str, line: _Line, path: Path) -> Any:
    """One plain or quoted scalar, with YAML 1.2's core resolution.

    `true`/`false`/`null`/`~` become the three literals, a run of digits becomes
    an int, and everything else stays a string. That last one is what keeps
    `core: ^0.2.0` and `version: 1.26` strings rather than mangling them, and
    floats are deliberately absent: no schema core publishes declares a numeric
    field, and a reader that tried to decide whether `1.2.3` was a float would
    be guessing.
    """
    if value[:1] in "\"'":
        return _unquote(value)
    if value in ("null", "~"):
        return None
    if value == "true":
        return True
    if value == "false":
        return False
    if value.lstrip("-").isdigit():
        return int(value)
    if YAML_FLOAT.fullmatch(value):
        return float(value)
    return value


def _parse_flow(value: str, line: _Line, path: Path) -> Any:
    """A flow collection: `[a, b]`, `[]`, `{a: b}`, `{}`.

    **Flow collections whose members are scalars, and nothing else.** Every one
    of the six real OpenAPI documents in the fleet uses `tags: [users]`,
    `required: [data, page]`, `{ $ref: '#/components/...' }` and
    `{ status: ok }`, so a reader that refused them refused every document it
    exists to check. Beyond that the subset stops: a nested flow collection, a
    flow collection spanning lines, and a trailing comma are all refused by
    name, because each is a construct where a partial implementation reads
    something and then reports it as what the file says.
    """
    if value == "[]":
        return []
    if value == "{}":
        return {}
    if not value.endswith(("]", "}")):
        raise Refusal(
            "yaml.unsupported", f"{path}:{line.number}",
            "a flow collection that does not close is not read",
        )
    opening, closing = value[0], value[-1]
    if (opening, closing) not in (("[", "]"), ("{", "}")):
        raise Refusal(
            "yaml.unsupported", f"{path}:{line.number}",
            f"{value!r} opens with {opening!r} and closes with {closing!r}; this reader does "
            "not repair a typo",
        )
    body = value[1:-1].strip()
    entries = _split_flow_items(body, line, path) if body else []
    if opening == "[":
        return [_flow_member(entry, line, path) for entry in entries]
    return _flow_mapping(entries, line, path)


def _flow_mapping(entries: list[str], line: _Line, path: Path) -> dict:
    mapping: dict[str, Any] = {}
    for entry in entries:
        key, separator, rest = entry.partition(":")
        if not separator:
            raise Refusal(
                "yaml.unsupported", f"{path}:{line.number}",
                f"{entry!r} in a flow mapping has no `:`; a flow mapping is not a sequence",
            )
        name = key.strip()
        if name[:1] in "\"'":
            name = _unquote(name)
        if name in mapping:
            raise Refusal(
                "yaml.unsupported", f"{path}:{line.number}",
                f"{name!r} appears twice in one flow mapping; the harness refuses rather "
                "than pick one",
            )
        mapping[name] = _flow_member(rest, line, path)
    return mapping


def _flow_member(entry: str, line: _Line, path: Path) -> Any:
    entry = entry.strip()
    if not entry:
        raise Refusal(
            "yaml.unsupported", f"{path}:{line.number}",
            "a trailing comma in a flow collection is not read",
        )
    if entry[0] in "[{" or entry[-1] in "]}":
        raise Refusal(
            "yaml.unsupported", f"{path}:{line.number}",
            f"{entry!r} nests one flow collection inside another, which is not read",
        )
    return _scalar_value(entry, line, path)


def _split_flow_items(body: str, line: _Line, path: Path) -> list[str]:
    """Split on the commas that are not inside a quoted scalar.

    `[a, "b, c"]` is two items, not three, and splitting naively would read the
    document as three — the same class of error as folding a multi-line plain
    scalar wrongly, and just as quiet. A flow *mapping* needs its colons left
    alone too, which is why this splits on `,` and the caller partitions on the
    first `:`.
    """
    items: list[str] = []
    current: list[str] = []
    quote = ""
    for character in body:
        if quote:
            current.append(character)
            if character == quote:
                quote = ""
            continue
        if character in "\"'":
            quote = character
            current.append(character)
            continue
        if character == ",":
            items.append("".join(current))
            current = []
            continue
        current.append(character)
    if quote:
        raise Refusal(
            "yaml.unsupported", f"{path}:{line.number}", "an unterminated quoted scalar"
        )
    items.append("".join(current))
    return items


def _unquote(text: str) -> str:
    quote = text[0]
    body = text[1:-1] if len(text) > 1 and text[-1] == quote else text[1:]
    if quote == "'":
        return body.replace("''", "'")
    try:
        return json.loads(f'"{body}"')
    except ValueError:
        return body


# `key: |` and `key: >` — literal and folded. The header grammar is small and
# complete for what YAML defines: a style, an optional explicit indentation
# indicator, and a chomping indicator in either order.
BLOCK_HEADER = re.compile(r"^([|>])(?:([+-])|([1-9]))?(?:([1-9])?([+-])?)?$")


def _read_block_scalar(
    header: str, line: _Line, lines: list[_Line], index: int, indent: int, path: Path
) -> tuple[str, int]:
    match = BLOCK_HEADER.match(header)
    if match is None:
        raise Refusal(
            "yaml.unsupported", f"{path}:{line.number}",
            f"{header!r} is not a block scalar header; this reader reads `|`, `>` and their "
            "chomping and indentation indicators",
        )
    style, chomp_before, indicator_a, indicator_b, chomp_after = match.groups()
    # The indicators are characters; the three behaviours are names. The first
    # version compared the character against "strip", so `|-` clipped and `>-`
    # gained a trailing newline it should not have had.
    chomp = {"-": "strip", "+": "keep"}.get(chomp_before or chomp_after or "", "clip")
    indicator = indicator_a or indicator_b

    body: list[str] = []
    block_indent = indent + int(indicator) if indicator else None
    while index < len(lines):
        raw = lines[index].raw
        if not raw.strip():
            body.append("")
            index += 1
            continue
        column = len(raw) - len(raw.lstrip(" "))
        if column <= indent:
            break
        if block_indent is None:
            block_indent = column
        if column < block_indent:
            break
        body.append(raw[block_indent:].rstrip())
        index += 1

    # Blank lines at the end of a block belong to the *next* construct unless the
    # chomping indicator says otherwise, so they are counted rather than kept.
    trailing = 0
    while body and body[-1] == "":
        body.pop()
        trailing += 1
    if block_indent is None:
        # A header with no body at all: `key: |` on its own.
        return "", index

    value = "\n".join(body) if style == "|" else _fold(body)
    if chomp == "strip":
        return value, index
    if chomp == "keep":
        return value + "\n" * (trailing + 1), index
    return value + "\n", index


def _fold(body: list[str]) -> str:
    """YAML's folding, derived from PyYAML rather than from memory.

    A *more indented* line — one with leading spaces left after the block's own
    indentation is removed — keeps the break on **either** side of it; every
    other break folds to a space, except that each blank line contributes a
    newline of its own. The first version of this function tracked whether the
    *previous* line was more indented, which is wrong in both directions, and
    the second tracked only the *next* one, which is wrong for the same reason.

    Every row below was measured against PyYAML, because the difference between
    two of these cases is a single character in a `description:` and a reader
    that is almost right is worse than one that refuses:

        a, b                 -> "a b"        neither side indented
        a, "  b"             -> "a\n  b"     the next side indented
        "  a", "  b"         -> "a b"        both at the block indent, so neither
        a, "  b", c          -> "a\n  b c"   the indented line keeps *both* breaks
        a, "", "  b"         -> "a\n\n  b"   a blank line adds a newline of its own
        a, "", b             -> "a\nb"       a blank line replaces the space
    """
    parts: list[str] = []
    previous_more = False
    blanks = 0
    for entry in body:
        if entry == "":
            blanks += 1
            continue
        more = entry[:1] in (" ", "\t")
        if parts:
            parts.append("\n" * blanks)
            if more or previous_more:
                parts.append("\n")
            elif blanks == 0:
                parts.append(" ")
        parts.append(entry)
        previous_more = more
        blanks = 0
    return "".join(parts)


# --------------------------------------------------------------------------
# core: resolution, provenance, the event catalog
# --------------------------------------------------------------------------


def resolve_core(explicit: Path | None = None, *, env: dict | None = None) -> Path:
    """The core checkout to read, or a `Refusal`.

    Resolution order, and the reason it is a list rather than one answer: an
    explicit flag is a person, an environment variable is a CI step that read a
    repository variable, and walking up is a developer with a sibling checkout.
    The last is deliberately not the default — muse's `MUSE_CORE_SCHEMAS` tier
    and pantry's `PANTRY_CAFAYE_ROOT` are both "a directory that happened to be
    next to me", and both are the reason a fleet ended up with four ways to find
    core. A harness that guesses its contract is a harness whose answer depends
    on the directory it was run from.
    """
    settings = os.environ if env is None else env
    candidates = []
    if explicit is not None:
        candidates.append(Path(explicit))
    elif settings.get("CAFAYE_CORE"):
        candidates.append(Path(settings["CAFAYE_CORE"]))
    for candidate in candidates:
        if not candidate.is_dir():
            raise Refusal(
                "core.not-a-checkout", str(candidate),
                "the path given is not a directory",
            )
        if not (candidate / MANIFEST_SCHEMA_RELATIVE).is_file():
            raise Refusal("core.not-a-checkout", str(candidate))
        return candidate.resolve()
    raise Refusal("core.absent", "searched: --core, $CAFAYE_CORE")


def is_core_checkout(root: Path) -> bool:
    return (root / MANIFEST_SCHEMA_RELATIVE).is_file()


def contract_digest(root: Path) -> str:
    """A sha256 over everything under `schemas/`, path-sorted.

    **This is the pin.** Not a git ref: a ref names a commit in a repository the
    harness cannot see, and the harness is offline by contract. A digest names
    the bytes, and the bytes are the thing a service is actually compiling
    against.

    Three properties, and all three matter:
      * the same core ref gives the same digest in a worktree and in a runner, so
        a laptop and CI are the same harness rather than two that happen to look
        alike;
      * a one-byte edit to one schema changes it, so `--expect-digest` catches
        the smallest possible drift — the kind a re-vendor fan-out produces;
      * it covers all of `schemas/`, not the two files a service happens to
        vendor, so a service cannot be pinned against a partial copy.

    What it does not do is notice a *dirty* tree that has not been committed.
    A developer with an edited schema and a clean HEAD gets a different digest
    from CI, and that is the truth rather than a bug: their tree really is
    different.
    """
    digest = hashlib.sha256()
    directory = root / "schemas"
    if not directory.is_dir():
        return ""
    for path in sorted(p for p in directory.rglob("*") if p.is_file()):
        digest.update(path.relative_to(directory).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


def core_commit(root: Path) -> str | None:
    """The commit a core checkout is at, read from `.git`, or None.

    Reported, never checked. A git ref is a *name* the harness cannot verify
    offline, and pinning on a name is what made four repositories answer
    "where is core" four ways. The digest is the pin; this is provenance for a
    human reading a CI log.
    """
    head = root / ".git"
    try:
        if head.is_file():
            for line in head.read_text(encoding="utf-8").splitlines():
                if line.startswith("gitdir:"):
                    head = Path(line.split(":", 1)[1].strip())
                    if not head.is_absolute():
                        head = (root / head).resolve()
                    break
        reference = (head / "HEAD").read_text(encoding="utf-8").strip()
        if not reference.startswith("ref:"):
            return reference or None
        target = head / reference.split(":", 1)[1].strip()
        return target.read_text(encoding="utf-8").strip() if target.is_file() else None
    except OSError:
        return None


def event_catalog(core: Path) -> set[str]:
    """Every event type the catalog declares, read from `docs/event-naming.md`.

    Read from the doc, not from a data file, because the doc is the spec and
    there is no machine-readable catalog: `docs/manifest-conventions.md` rule 6
    ("every consumed type exists in the core catalog") is a rule *about* that
    document. A harness that shipped its own copy of the list would be a second
    catalog, and the drift between the two would be invisible — which is
    decision D22's neighbour and is listed as owed in docs/contract-harness.md.
    """
    text = (core / EVENT_CATALOG_RELATIVE).read_text(encoding="utf-8")
    start = text.find(CATALOG_HEADING)
    if start == -1:
        raise Refusal("core.not-a-checkout", str(EVENT_CATALOG_RELATIVE), "no catalog section")
    catalog = text[start:]
    end = catalog.find("\n## ", 1)
    if end != -1:
        catalog = catalog[:end]
    return set(re.findall(r"^\|\s*`([a-z][a-z0-9_.-]+)`\s*\|", catalog, flags=re.MULTILINE))


# --------------------------------------------------------------------------
# the rules
# --------------------------------------------------------------------------


def check_manifest_schema(manifest: Any, core: Path, service: Path) -> tuple[list[Finding], bool]:
    """`manifest.schema` — the manifest against `schemas/cafaye.manifest.schema.json`.

    The second element of the return says whether the schema held, and it is
    what `run` uses to decide whether the cross-field rules are worth running at
    all. A document whose fields are the wrong type is a document whose
    cross-field comparisons would be comparing nothing, and a finding computed
    from it is a finding about a document nobody wrote. `caf`'s linter makes the
    same call, for the same reason.
    """
    schema = _load_schema(core / MANIFEST_SCHEMA_RELATIVE)
    violations = evaluate(manifest, schema)
    if not violations:
        return [], True
    return [
        Finding("manifest.schema", f"cafaye.yml: {v.path or '<root>'}", v.message)
        for v in violations
    ], False


def check_own_prefix(manifest: dict) -> list[Finding]:
    """`event.own-prefix` — a published type starts with the publisher's name.

    `docs/manifest-conventions.md`, rule 1. Not a schema rule because JSON
    Schema cannot compare two properties of the same instance, and not in
    `schemas/` for the same reason: this function is where the rule is.
    """
    name = manifest.get("name")
    if not isinstance(name, str):
        return []
    return [
        Finding(
            "event.own-prefix", f"cafaye.yml: exposes/events[{index}]",
            f"{event_type!r} must start with this service's own name ({name}.…) — every "
            "event type is <service>.<entity>.<action>",
        )
        for index, event_type in enumerate(_exposes_events(manifest))
        if event_type.split(".")[0] != name
    ]


def check_no_self_consume(manifest: dict) -> list[Finding]:
    """`event.no-self-consume` — a service never consumes its own events.

    Not a schema rule: a set intersection across two arrays, which no JSON
    Schema keyword expresses. In the harness's source, and in
    `docs/manifest-conventions.md` rule 2, which is the document that says so.
    """
    published = set(_exposes_events(manifest))
    consumed = manifest.get("consumes") or []
    if not isinstance(consumed, list):
        return []
    return [
        Finding(
            "event.no-self-consume", f"cafaye.yml: consumes[{index}]",
            f"{event_type!r} is published by this service and must not be in consumes; react "
            "in-process instead of paying for a bus",
        )
        for index, event_type in enumerate(consumed)
        if event_type in published
    ]


def check_unknown_consumed(manifest: dict, catalog: set[str]) -> list[Finding]:
    """`event.unknown-consumed` — every consumed type exists in the catalog.

    `docs/manifest-conventions.md`, rule 6. A subscription to a type nobody
    publishes is a typo that otherwise ships silently and fails at run time, on
    someone else's deploy.
    """
    consumed = manifest.get("consumes") or []
    if not isinstance(consumed, list):
        return []
    return [
        Finding(
            "event.unknown-consumed", f"cafaye.yml: consumes[{index}]",
            f"{event_type!r} is consumed here and no publisher in core's catalog declares it",
        )
        for index, event_type in enumerate(consumed)
        if event_type not in catalog
    ]


def check_unknown_published(manifest: dict, catalog: set[str]) -> list[Finding]:
    """`event.unknown-published` — every published type exists in the catalog.

    The other half of the same fact, and it is a separate rule because it fails
    differently: a published type nothing else has heard of is a service
    announcing an event no subscriber is waiting for, which is a design bug
    rather than a typo, and it is invisible until someone generates a client.
    """
    return [
        Finding(
            "event.unknown-published", f"cafaye.yml: exposes/events[{index}]",
            f"{event_type!r} is published here and core's catalog does not list it, so no "
            "consumer is known to be waiting for it",
        )
        for index, event_type in enumerate(_exposes_events(manifest))
        if event_type not in catalog
    ]


def check_payload_schema(manifest: dict, core: Path) -> list[Finding]:
    """`event.payload-schema-missing` — a published type has a payload schema.

    `schemas/events/<service>/<entity>/<action>.schema.json` is where the `data`
    of a type is described, and a type with no schema is a type whose payload is
    whatever the publisher felt like that week. Existence is the whole check
    here; validating a payload is a live-response test and is not built — see
    docs/contract-harness.md.
    """
    return [
        Finding(
            "event.payload-schema-missing", f"cafaye.yml: exposes/events[{index}]",
            f"{event_type!r} is published with no payload schema at "
            f"schemas/events/{event_type.replace('.', '/')}.schema.json",
        )
        for index, event_type in enumerate(_exposes_events(manifest))
        if not (core / "schemas" / "events" / (event_type.replace(".", "/") + ".schema.json")).is_file()
    ]


def check_api_file_exists(manifest: dict, service: Path) -> list[Finding]:
    """`manifest.api-file-missing` — `exposes.api` resolves inside the repository.

    The schema pins the *shape* of the path and cannot check that the file is
    there, so this is a rule in the harness. It is the rule a path error breaks:
    `caf dev`, every SDK generator and this harness itself all resolve the same
    string.
    """
    reference = (manifest.get("exposes") or {}).get("api")
    if not isinstance(reference, str) or not reference:
        return []
    if (service / reference).is_file():
        return []
    return [
        Finding(
            "manifest.api-file-missing", f"cafaye.yml: exposes/api",
            f"{reference!r} does not exist in this repository; exposes.api is resolved by "
            "`caf dev`, by the SDK generators and by this harness",
        )
    ]


def check_document_is_31(document: dict, where: str) -> list[Finding]:
    """`openapi.document-is-31` — the document declares OpenAPI 3.1.

    `docs/openapi-conventions.md`, "Versioning" and the endpoint checklist. 3.1
    is what makes `null` a type rather than a keyword that changes meaning, and a
    3.0 document cannot express half of what core's payload schemas say.
    """
    declared = document.get("openapi")
    if isinstance(declared, str) and declared.startswith("3.1"):
        return []
    return [
        Finding(
            "openapi.document-is-31", where,
            f"the document declares openapi: {declared!r}; core requires 3.1",
        )
    ]


def check_info_version(document: dict, where: str) -> list[Finding]:
    """`openapi.info-version` — `info.version` is present and `X.Y.Z`.

    `docs/openapi-conventions.md`, "Versioning". It is the only signal a consumer
    has for telling "nothing moved" from "the whole document was regenerated",
    and core's sync rule — a breaking change bumps the prefix *and* the document
    version in the same commit — is stated entirely in terms of it.

    Both numbers are required and they mean different things, so the presence
    check and the parseability check are one rule: a version nobody can parse
    attributes a deprecation to nothing.
    """
    info = document.get("info")
    version = info.get("version") if isinstance(info, dict) else None
    if isinstance(version, str) and SEMVER_VERSION.match(version):
        return []
    return [
        Finding(
            "openapi.info-version", f"{where}: info/version",
            f"info.version is {version!r}; core requires MAJOR.MINOR.PATCH, and the two "
            "version numbers (the /vN prefix and this one) move together",
        )
    ]


def check_has_paths(document: dict, where: str) -> list[Finding]:
    """`openapi.has-paths` — the document declares at least one path.

    **Two empty sets agree.** A reader that finds no paths and returns an empty
    collection lets a service delete its entire HTTP contract and see a green
    build, because "no path violates the `/v1` rule" and "there is no path" are
    the same sentence. courier's `OpenAPIPaths` refuses rather than under-reads
    for exactly this; this is that rule, in the harness.
    """
    paths = document.get("paths")
    if isinstance(paths, dict) and paths:
        return []
    return [
        Finding(
            "openapi.has-paths", f"{where}: paths",
            f"paths is {paths!r}; a document that declares no operation is not a contract, and "
            "an empty set agrees with an empty set",
        )
    ]


def check_paths_are_versioned(document: dict, where: str) -> list[Finding]:
    """`openapi.paths-are-versioned` — every path sits under a `/vN` prefix.

    `docs/openapi-conventions.md`, "Versioning". The prefix is the only version
    that can ever be frozen, because a published endpoint cannot change shape.
    """
    return [
        Finding(
            "openapi.paths-are-versioned", f"{where}: paths -> {path}",
            f"{path!r} is not under a /vN prefix; core versions the path, never the body",
        )
        for path in _paths(document)
        if not VERSION_PREFIX.match(path)
    ]


def check_one_version_prefix(document: dict, where: str) -> list[Finding]:
    """`openapi.one-version-prefix` — one `/vN` per document.

    `docs/openapi-conventions.md`, "Versioning": a breaking change means a new
    prefix *alongside* the old one, and `/v1` is never mutated in place. A
    document carrying two prefixes is a breaking change that landed without one,
    and it is the shape a doc-vs-router drift test cannot see — a route count
    comparison would not notice a rename either.
    """
    prefixes = {
        match.group(1)
        for path in _paths(document)
        if (match := VERSION_PREFIX.match(path))
    }
    if len(prefixes) <= 1:
        return []
    return [
        Finding(
            "openapi.one-version-prefix", f"{where}: paths",
            f"the document carries prefixes v{sorted(prefixes)}; one document describes one "
            "contract version, and a second prefix is a breaking change that must be a "
            "decision rather than an accident",
        )
    ]


# --------------------------------------------------------------------------
# running
# --------------------------------------------------------------------------


def _load_schema(path: Path) -> dict:
    try:
        with path.open(encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError) as error:
        raise Refusal("core.not-a-checkout", str(path), str(error))


def _exposes_events(manifest: dict) -> list[str]:
    events = (manifest.get("exposes") or {}).get("events")
    if not isinstance(events, list):
        return []
    return [event for event in events if isinstance(event, str)]


def _paths(document: dict) -> list[str]:
    paths = document.get("paths")
    if not isinstance(paths, dict):
        return []
    return [path for path in paths if isinstance(path, str)]


def run(
    service_root: Path,
    core_root: Path | None = None,
    expect_digest: str | None = None,
    env: dict | None = None,
) -> Result:
    """Check one service against core's contracts. Never raises `Refusal`.

    A `Refusal` becomes a `Result` whose exit code is 2, because a caller that
    has to catch an exception to learn the run did not happen is a caller that
    will eventually not catch it.
    """
    service = Path(service_root)
    core = Path(core_root) if core_root is not None else None
    digest = None
    try:
        if core is None:
            core = resolve_core(env=env)
        if not is_core_checkout(core):
            raise Refusal("core.not-a-checkout", str(core))
        digest = contract_digest(core)
        if expect_digest and digest != expect_digest:
            return Result(
                service_root=service,
                core_root=core,
                digest=digest,
                findings=(Finding(
                    "core.digest-mismatch", "schemas/",
                    f"core's contract surface digests {digest} and the pin is {expect_digest}. "
                    "Either core moved or the pin did; both are a deliberate one-line change, "
                    "and neither is something to discover in a service's build.",
                ),),
                core_commit=core_commit(core),
            )
        return _check_service(service, core, digest)
    except Refusal as refusal:
        # The digest survives a later refusal: core *was* found and read, and a
        # log that says "no core read" next to a manifest it did read is a log
        # that sends a person to the wrong file.
        return Result(
            service_root=service,
            core_root=core,
            digest=digest,
            findings=(Finding(refusal.rule, refusal.path, str(refusal)),),
            refused=True,
        )


def _check_service(service: Path, core: Path, digest: str) -> Result:
    manifest_path = service / "cafaye.yml"
    if not manifest_path.is_file():
        raise Refusal("service.manifest-absent", str(manifest_path))
    manifest = read_yaml(manifest_path.read_text(encoding="utf-8"), manifest_path)
    if not isinstance(manifest, dict):
        raise Refusal(
            "yaml.unsupported", str(manifest_path),
            "a manifest must be a mapping at the top level",
        )

    result = Result(service_root=service, core_root=core, digest=digest, core_commit=core_commit(core))
    schema_findings, schema_held = check_manifest_schema(manifest, core, service)
    if not schema_held:
        return Result(
            service_root=service,
            core_root=core,
            digest=digest,
            findings=tuple(schema_findings),
            stopped_after_schema=True,
            core_commit=result.core_commit,
        )

    catalog = event_catalog(core)
    findings: list[Finding] = []
    findings.extend(check_own_prefix(manifest))
    findings.extend(check_no_self_consume(manifest))
    findings.extend(check_unknown_consumed(manifest, catalog))
    findings.extend(check_unknown_published(manifest, catalog))
    findings.extend(check_payload_schema(manifest, core))
    findings.extend(check_api_file_exists(manifest, service))
    findings.extend(_check_openapi(manifest, service))
    result.findings = tuple(findings)
    return result


def _check_openapi(manifest: dict, service: Path) -> list[Finding]:
    reference = (manifest.get("exposes") or {}).get("api")
    if not isinstance(reference, str) or not reference:
        return []
    path = service / reference
    if not path.is_file():
        return []  # already reported, by manifest.api-file-missing
    where = reference
    document = read_yaml(path.read_text(encoding="utf-8"), path)
    if not isinstance(document, dict):
        raise Refusal("yaml.unsupported", str(path), "an OpenAPI document must be a mapping")
    findings = []
    findings.extend(check_document_is_31(document, where))
    findings.extend(check_info_version(document, where))
    findings.extend(check_has_paths(document, where))
    findings.extend(check_paths_are_versioned(document, where))
    findings.extend(check_one_version_prefix(document, where))
    return findings


# --------------------------------------------------------------------------
# the command
# --------------------------------------------------------------------------


def render(result: Result) -> str:
    """The whole report, as one string. Deterministic: no colour, no width."""
    lines = []
    for finding in result.findings:
        lines.append(f"FAIL {finding.rule} {finding.path}: {finding.message}")
    if result.findings:
        rules = sorted({finding.rule for finding in result.findings})
        lines.append("")
        lines.append(
            f"{'REFUSED' if result.refused else f'{len(result.findings)} violation(s)'}"
            f" against core {result.core_root} "
            f"({result.digest[:12] if result.digest else 'no core read'}): " + ", ".join(rules)
        )
        return "\n".join(lines)
    lines.append(
        f"OK {result.service_root} conforms to core "
        f"{result.core_root} ({result.digest[:12] if result.digest else 'no digest'}"
        + (f", {result.core_commit[:12]}" if result.core_commit else "")
        + ")"
    )
    if result.stopped_after_schema:
        lines.append("note: the manifest failed the schema, so the cross-field rules did not run")
    return "\n".join(lines)


def rule_inventory_path() -> Path:
    return Path(__file__).resolve().parent / "rules.json"


def load_rule_inventory() -> dict:
    path = rule_inventory_path()
    try:
        with path.open(encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError) as error:
        raise Refusal("core.not-a-checkout", str(path), f"the rule inventory is unreadable: {error}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="cafaye-contract",
        description=(
            "Check a service's declared contract surface against core's contracts. "
            "Offline: core is read from a checkout, never fetched."
        ),
    )
    parser.add_argument("service", nargs="?", default=".", help="the service repository root (default: .)")
    parser.add_argument("--core", help="a cafaye/core checkout (default: $CAFAYE_CORE)")
    parser.add_argument(
        "--expect-digest",
        help="fail unless core's schemas/ digests to this sha256 — the pin, in one argument",
    )
    parser.add_argument("--json", action="store_true", help="machine-readable findings on stdout")
    parser.add_argument(
        "--list-rules", action="store_true", help="print the rule inventory and exit"
    )
    arguments = parser.parse_args(argv)

    if sys.version_info < MINIMUM_PYTHON:
        print(
            f"cafaye-contract needs python >= "
            f"{MINIMUM_PYTHON[0]}.{MINIMUM_PYTHON[1]}; this is {sys.version.split()[0]}",
            file=sys.stderr,
        )
        return EXIT_REFUSED

    if arguments.list_rules:
        try:
            inventory = load_rule_inventory()
        except Refusal as refusal:
            print(f"FAIL {refusal}", file=sys.stderr)
            return EXIT_REFUSED
        print(json.dumps(inventory, indent=2, sort_keys=False))
        return EXIT_CONFORMS

    result = run(
        service_root=Path(arguments.service),
        core_root=Path(arguments.core) if arguments.core else None,
        expect_digest=arguments.expect_digest,
    )
    if arguments.json:
        print(json.dumps({
            "service": str(result.service_root),
            "core": str(result.core_root),
            "coreCommit": result.core_commit,
            "digest": result.digest,
            "stoppedAfterSchema": result.stopped_after_schema,
            "exitCode": result.exit_code,
            "findings": [
                {"rule": f.rule, "path": f.path, "message": f.message} for f in result.findings
            ],
        }, indent=2, sort_keys=False))
        return result.exit_code
    print(render(result))
    return result.exit_code


if __name__ == "__main__":
    sys.exit(main())
