#!/usr/bin/env python3
"""tenancy_check — is a service's account-isolation declaration still true?

    tenancy-check .                       # static: the declaration against the tree
    tenancy-check --json .                # the same findings, as JSON
    tenancy-check --explain               # every finding this checker can report

WHAT THIS IS

The platform is sold as self-hostable multi-tenant code. The defect that ends
that product is one customer reading another's data, and measured across the
fleet that defect is invisible from the outside:

    cross-tenant NEGATIVE tests — ones asserting account A is refused account B
    identity 7    courier 19
    billing 0   cafaye-rb 0   cafaye-ts 0   guard 0
    darkroom 0  pantry 0     muse 0        cafaye-py 0

Two services prove isolation. Eight do not, and six of those scope by account
in production code. `darkroom` is the clean case: `assets` and `asset_variants`
carry `account_id uuid not null`, every query reads `where id = $1 and
account_id = $2`, and **zero** tests assert any of it. A refactor that drops
one `and account_id = $2` gives a customer another customer's files and the
whole suite stays green.

SO THE BOUNDARY IS DECLARED, IN `tenancy.yml`, AGAINST THIS SCHEMA

...and declared rather than inferred because inference is what just failed.
Counting account-scoped routes by pattern gives a different answer per
framework:

    guard       route_defs=96     (TypeScript decorators)
    muse        route_defs=76
    cafaye-ts   route_defs=51
    darkroom    route_defs=0      (axum — a different syntax entirely)
    billing     route_defs=0      (Rails — a different syntax entirely)

A grep reporting "darkroom has no routes" when darkroom has account-scoped
queries against customer assets is **worse than no grep**, because it reads
like an answer. So this checker does not count routes. It reads the service's
own enumeration, checks that enumeration against the tree, and says out loud
what it could not classify.

CROSS-TENANT ACCESS IS ANSWERED AS NONEXISTENCE

The assertions the two proving services write are about **absence**, not
refusal:

    assert WebhookEndpoints.get(endpoint.id, @other_account_id) == nil
    assert WebhookEndpoints.list(@other_account_id) == []

A `403` tells an attacker the id exists; a `nil`/`[]`/`NotFound` tells them
nothing. So `schemas/tenant-isolation.schema.json` makes `negative.asserts` a
`const: absent`, and `tenancy.denial-refuses` is a FAILURE — if your contract
permits "forbidden" for another account's resource, it has reintroduced an
enumeration oracle, and a test must be able to catch that. See D33.

WHAT IS PROVED, AND WHAT IS NOT

Four things, and the fourth is the one this packet exists for:

  * every declared entry point names a file that EXISTS and a line that is
    really there — a declaration pointing at nothing is worse than none;
  * the enforcement line still carries the tenancy key, so dropping the
    predicate is a red rather than a refactor;
  * the declared enumeration is CLOSED in both directions, against the SQL the
    scanner can read: a site it finds that nobody declared, and a declaration
    whose site it can no longer find;
  * each entry point's negative assertion is in the service's tests, on the
    line the declaration names, and asserts absence.

And one thing it deliberately does not do: **claim completeness for a language
it cannot read.** `tenancy.enumeration-partial` is a WARNING that names every
declared entry point the scanner could not classify and every account-scope
site it saw and could not attribute, and it says the declaration is not proven
closed. A warning never moves the exit code, so a Go service's CI stays green —
and the report cannot be read as "no routes found".

EXIT CODES

    0   no finding at severity `fail`. Warnings may still be printed.
    1   at least one `fail`.
    2   the check could not happen. Never 0, and never 1: a run that could not
        find the declaration has not checked the boundary, and converting an
        unknown into a green badge is the defect core exists to prevent.

PYTHON 3.9, AND WHY THIS FILE IS NOT 3.11

`harness/gate_check.py` needs 3.11 because it reads `mise.toml` and `tomllib`
is stdlib from 3.11. This one reads no TOML and runs no process, so it runs on
the same floor as `harness/cafaye_contract.py`. That is not a detail: a
contract check that needs an interpreter some service's CI does not have is a
contract check that runs nowhere.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

try:
    from cafaye_contract import Refusal, read_yaml
except ModuleNotFoundError as _missing:  # pragma: no cover
    raise SystemExit(
        f"tenancy_check: cannot import cafaye_contract from {Path(__file__).resolve().parent}: "
        f"{_missing}. tenancy_check travels with the harness; a copy of one without the "
        "other would mean a second YAML dialect, which is the drift core exists to prevent."
    )

EXIT_OK = 0
EXIT_FAIL = 1
EXIT_COULD_NOT_RUN = 2

#: The declaration file. One per repository, at its root. Named for the same
#: reason `gate.yml` is: a boundary that is discovered by guessing its
#: filename is not a declaration.
DECLARATION = Path("tenancy.yml")

#: The schema the declaration is written against. This file is stdlib-only, so
#: it re-implements the handful of constraints that decide whether a
#: declaration is well-formed — core's own idiom for a document and its schema
#: being the same contract written twice.
TENANCY_SCHEMA_RELATIVE = Path("schemas") / "tenant-isolation.schema.json"

#: The floor. See the module docstring: this checker reads no TOML and runs no
#: process, so it does not inherit `gate_check`'s 3.11.
MINIMUM_PYTHON = (3, 9)

#: The modules this file may import beyond the contract harness's own list.
#: Everything here is stdlib and nothing else; there is no `tomllib`, no
#: `shlex` and no `tempfile`, which is the mechanical form of the version floor.
EXTRA_STDLIB: frozenset[str] = frozenset()

NAME_PATTERN = re.compile(r"^[a-z][a-z0-9-]*$")
ID_PATTERN = re.compile(r"^[a-z][a-z0-9-]*$")
SUBJECT_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")
IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
EXPECT_PATTERN = re.compile(r"^(?:[A-Za-z_][A-Za-z0-9_.]*|\[\])$")
PATH_PATTERN = re.compile(r"^[A-Za-z0-9._-]+/[A-Za-z0-9._/-]+$")
SCOPE_PATH_PATTERN = re.compile(r"^[A-Za-z0-9._-]+(/[A-Za-z0-9._-]+)*$")

#: The findings this checker can report, and nothing else. Mirrored in
#: `harness/tenancy_findings.json` and asserted equal in both directions by
#: core's suite, for the reason `harness/rules.json` and
#: `harness/gate_findings.json` are both asserted: a finding nobody was told
#: about is a finding that will be wrong the first time somebody needs it.
FINDINGS: dict[str, tuple[str, str, str]] = {
    "tenancy.declaration-missing": (
        "fail",
        "the service declares no account boundary, so its boundary can only be discovered by reading every query by hand.",
        "write tenancy.yml; schemas/tenant-isolation.schema.json is the format and docs/tenancy.md is the worked example",
    ),
    "tenancy.declaration-unreadable": (
        "fail",
        "the declaration is not a YAML document core's reader accepts.",
        "run: python3 harness/bin/tenancy-check <repo> --explain, and read the file and line it names",
    ),
    "tenancy.schema": (
        "fail",
        "the declaration does not satisfy schemas/tenant-isolation.schema.json.",
        "run: python3 harness/bin/tenancy-check <repo> --explain, for the constraint and the path",
    ),
    "tenancy.location-missing": (
        "fail",
        "a declaration names a file that is not in this repository, so the boundary it claims to enforce is nowhere.",
        "point enforced.file and negative.file at files that exist, or restore the files it names",
    ),
    "tenancy.line-missing": (
        "fail",
        "a declaration names a line past the end of the file.",
        "point enforced.line and negative.line at lines that exist; a line number nobody checked is the false green written down",
    ),
    "tenancy.scope-lost": (
        "fail",
        "the entry point is still account-scoped, but not on the line the declaration names.",
        "move the declaration to the line that carries the tenancy key, or put the key back where the declaration says it is",
    ),
    "tenancy.bind-missing": (
        "fail",
        "the mechanism is bind-parameter and the parameter that carries the account is not on the declared line.",
        "pass the account where the declaration says it is passed, or change the mechanism to the one actually enforced",
    ),
    "tenancy.entry-absent": (
        "fail",
        "an entry point is declared and the scanner can no longer find it: either the scoping was dropped or the code is gone.",
        "put the tenancy key back in the statement, or delete the entry point from the declaration",
    ),
    "tenancy.undeclared-entry": (
        "fail",
        "the scanner found account-scoped access nobody declared, so the enumeration is a summary rather than a contract.",
        "add the entry point to tenancy.yml with its mechanism, its line and its negative assertion",
    ),
    "tenancy.enumeration-empty": (
        "fail",
        "the service says it scopes by account and declares no way it does.",
        "declare the entry points, or set accountScoped: false if the service genuinely holds no customer data",
    ),
    "tenancy.honest-zero": (
        "fail",
        "the service declares no account scoping and has account-scoped code, so its honest zero is not honest.",
        "declare the entry points it has, with the negative assertions it needs; an omission is not a zero",
    ),
    "tenancy.denial-missing": (
        "fail",
        "the negative assertion for an entry point is not on the line the declaration names, so nothing asserts that account A is refused account B.",
        "write the assertion — absent, not refused — and point negative.line at the line that carries it",
    ),
    "tenancy.denial-refuses": (
        "fail",
        "the declaration answers cross-tenant access with a refusal, which is an enumeration oracle: a 403 tells an attacker the id exists.",
        "assert absence instead (nil, [], NotFound) and say so in negative.expects; see D33",
    ),
    "tenancy.enumeration-partial": (
        "warn",
        "this checker cannot classify every account-scoped site, so this declaration is NOT proven closed and this machine cannot settle it.",
        "read the named files by hand and confirm each one is declared; the checker's scanner reads SQL and account-key predicates only",
    ),
    "tenancy.scan-narrowed": (
        "warn",
        "a source path the declaration names is not in this repository, so the scan read less than was declared.",
        "point scope.sources at paths that exist, or add the one that is missing",
    ),
    "tenancy.scope-key-unused": (
        "warn",
        "no account-scoped statement this scanner can read carries the declared tenancy key, so it found nothing to close the enumeration against.",
        "check scope.key against the column or parameter this service really scopes by; a key nothing matches is either spelled differently or lives in a language this scanner cannot classify",
    ),
}

SEVERITIES = ("ok", "warn", "fail")

#: Every key a tenancy declaration may carry. Mirrors the root `properties` of
#: `schemas/tenant-isolation.schema.json`, so a field added to the schema and
#: never taught to this file is a red rather than a silent acceptance.
TOP_LEVEL_KEYS = frozenset({"version", "service", "accountScoped", "scope", "entryPoints"})
REQUIRED_TOP_LEVEL_KEYS = ("version", "service", "accountScoped", "scope", "entryPoints")

OPERATIONS = ("select", "update", "delete", "call")
MECHANISMS = ("query-filter", "bind-parameter", "repository-method", "middleware")

#: The operations the scanner can find in SQL. `call` is not among them by
#: construction — a repository method is a `select` as far as the boundary is
#: concerned and something else as far as a text scanner is concerned — and the
#: schema says so in the same words.
SCANNER_OPERATIONS = frozenset({"select", "update", "delete"})

#: The three spellings of a tenancy key this checker will look for on a declared
#: enforcement line. The fleet has three vocabularies already (D7) and a
#: checker that guessed which one a service uses would be guessing at the
#: boundary rather than at the data. The bare key first, because `account_id`
#: is what four of the services write and the camel spelling is the fallback.
KEY_SPELLINGS = ("{key}", "{key}_", "{key}Id")

#: How far above a tenancy-key line the scanner looks for the operation keyword
#: that names the statement. A SQL statement is routinely wrapped across lines,
#: and attributing the key to the nearest preceding `select`/`update`/`delete`
#: is a bounded rule rather than a guess. Beyond the window the site is
#: reported as a candidate the scanner could not attribute — never guessed at,
#: which is what `tenancy.enumeration-partial` is for.
ATTRIBUTION_WINDOW = 4

#: Directory names never walked. A checker that reads a dependency tree is a
#: checker whose answer depends on whether `node_modules` is installed, and
#: core's rule is that a check which could not run is not a pass.
SKIPPED_DIRECTORIES = frozenset({
    ".git", ".venv", "node_modules", "vendor", "target", "deps", "_build",
    "dist", "build", ".next", ".tox", ".mypy_cache", ".pytest_cache", "coverage",
})

#: File suffixes read by the scanner. Everything else in a declared source is
#: walked past and reported only if it carries a tenancy key, which is how a
#: Go or Elixir service gets `tenancy.enumeration-partial` instead of a
#: confident zero.
TEXT_SUFFIXES = frozenset({".sql", ".go", ".ex", ".exs", ".rb", ".py", ".ts", ".tsx",
                            ".rs", ".java", ".kt", ".php", ".cs", ".swift", ".js", ".mjs"})

_SQL_COMMENT = re.compile(r"--[^\n]*")

#: Line comments, per file type. Only used to decide whether a line *carries*
#: the tenancy key, so a comment that talks about `account_id` is not an
#: account-scoped statement. Stripping them for that purpose and nothing else is
#: deliberate: a `#` inside a string literal would hide a real site, which is why
#: the fixture's comments are written to avoid the token rather than relying on
#: this being cleverer than it is.
_HASH_COMMENT = re.compile(r"#.*$")
_SLASH_COMMENT = re.compile(r"//.*$")

#: A line that DEFINES the shape rather than reaching a row. `create table
#: assets ( … account_id uuid not null … )` names the tenancy key on the line
#: that declares the column, and skipping to the closing paren is what keeps a
#: schema from being reported as an enumeration of itself.
_DDL = re.compile(
    r"\b(create\s+table|alter\s+table|create\s+(unique\s+)?index|create\s+view)\b", re.IGNORECASE
)

#: An insert is not an entry point, and the schema says why in the same words:
#: it creates a row in the account the caller is already acting as, so it cannot
#: read or write another account's row. `Assets.insert(id: …, account_id: …)`
#: in a test factory is the same statement, and it is the most common line in
#: this fleet that carries the key.
_INSERT = re.compile(r"\binsert\b", re.IGNORECASE)

_SQL_KEYWORDS = {
    "select": r"select\s+.*?\s+from\s+([A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)?)",
    "update": r"update\s+([A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)?)\s+set\b",
    "delete": r"delete\s+from\s+([A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)?)",
}


# --------------------------------------------------------------------------
# the format, re-implemented from schemas/tenant-isolation.schema.json
# --------------------------------------------------------------------------


def validate(declaration: Any) -> list[str]:
    """The well-formedness half, without `jsonschema`.

    Every message names the path and the constraint, because the point of this
    half is to tell a reader what to change. It mirrors the schema file for
    the same reason `gate_check.validate` does: a service's CI must be able to
    run this checker with nothing installed.
    """
    problems: list[str] = []

    def complain(path: str, constraint: str) -> None:
        problems.append(f"{path or '<root>'}: {constraint}")

    if not isinstance(declaration, dict):
        return ["<root>: type object"]

    for key in sorted(declaration):
        if key not in TOP_LEVEL_KEYS:
            complain("", f"additionalProperties: {key!r} is not a key of a tenancy declaration")
    for key in REQUIRED_TOP_LEVEL_KEYS:
        if key not in declaration:
            complain(key, "required")
    if declaration.get("version") != 1:
        complain("version", "const 1")
    service = declaration.get("service")
    if not isinstance(service, str) or not NAME_PATTERN.fullmatch(service) or len(service) > 40:
        complain("service", "pattern ^[a-z][a-z0-9-]*$, maxLength 40")
    account_scoped = declaration.get("accountScoped")
    if not isinstance(account_scoped, bool):
        complain("accountScoped", "type boolean")
    if "scope" in declaration:
        problems.extend(_validate_scope(declaration["scope"]))
    if "entryPoints" in declaration:
        problems.extend(_validate_entry_points(declaration["entryPoints"], account_scoped))
    return problems


def _validate_scope(scope: Any) -> list[str]:
    problems: list[str] = []
    if not isinstance(scope, dict):
        return ["scope: type object"]
    allowed = {"key", "sources"}
    for key in sorted(scope):
        if key not in allowed:
            problems.append(f"scope: additionalProperties {key!r}")
    for key in ("key", "sources"):
        if key not in scope:
            problems.append(f"scope/{key}: required")
    name = scope.get("key")
    if name is not None and (
        not isinstance(name, str)
        or not 3 <= len(name) <= 64
        or not IDENTIFIER_PATTERN.fullmatch(name)
    ):
        problems.append("scope/key: minLength 3, maxLength 64, pattern ^[A-Za-z_][A-Za-z0-9_]*$")
    sources = scope.get("sources")
    if sources is None:
        return problems
    if not isinstance(sources, list):
        problems.append("scope/sources: type array")
        return problems
    if not 1 <= len(sources) <= 32:
        problems.append("scope/sources: minItems 1, maxItems 32")
    if len(set(map(str, sources))) != len(sources):
        problems.append("scope/sources: uniqueItems — the same path twice is one path")
    for index, item in enumerate(sources):
        where = f"scope/sources/{index}"
        if not isinstance(item, str):
            problems.append(f"{where}: type string")
            continue
        if not 1 <= len(item) <= 200:
            problems.append(f"{where}: minLength 1, maxLength 200")
        elif not SCOPE_PATH_PATTERN.fullmatch(item):
            problems.append(f"{where}: pattern a repository-relative path")
        elif ".." in item.split("/"):
            problems.append(f"{where}: not — a path may not leave the repository")
    return problems


def _validate_entry_points(entry_points: Any, account_scoped: Any) -> list[str]:
    problems: list[str] = []
    if not isinstance(entry_points, list):
        return ["entryPoints: type array"]
    if len(entry_points) > 512:
        problems.append("entryPoints: maxItems 512")
    if account_scoped is False and entry_points:
        problems.append(
            "entryPoints: maxItems 0 — the declaration says the service has no "
            f"account scoping and names {len(entry_points)} entry point(s)"
        )
    if account_scoped is True and not entry_points:
        problems.append(
            "entryPoints: minItems 1 — the declaration says the service scopes by "
            "account and names no way it does"
        )
    identifiers: set[str] = set()
    for index, item in enumerate(entry_points):
        where = f"entryPoints/{index}"
        if not isinstance(item, dict):
            problems.append(f"{where}: type object")
            continue
        for key in sorted(item):
            if key not in {"id", "operation", "subject", "enforced", "negative"}:
                problems.append(f"{where}: additionalProperties {key!r}")
        for key in ("id", "operation", "subject", "enforced", "negative"):
            if key not in item:
                problems.append(f"{where}/{key}: required")
        identifier = item.get("id")
        if identifier is not None:
            if not isinstance(identifier, str) or not ID_PATTERN.fullmatch(identifier) \
                    or len(identifier) > 60:
                problems.append(f"{where}/id: pattern ^[a-z][a-z0-9-]*$, maxLength 60")
            elif identifier in identifiers:
                problems.append(f"{where}/id: unique — {identifier!r} appears twice")
            else:
                identifiers.add(identifier)
        operation = item.get("operation")
        if operation is not None and operation not in OPERATIONS:
            problems.append(f"{where}/operation: enum {list(OPERATIONS)}")
        subject = item.get("subject")
        if subject is not None and (
            not isinstance(subject, str)
            or not SUBJECT_PATTERN.fullmatch(subject)
            or not 2 <= len(subject) <= 80
        ):
            problems.append(f"{where}/subject: pattern ^[a-z][a-z0-9_]*$, maxLength 80")
        if "enforced" in item:
            problems.extend(_validate_enforced(item["enforced"], f"{where}/enforced"))
        if "negative" in item:
            problems.extend(_validate_negative(item["negative"], f"{where}/negative"))
    return problems


def _validate_enforced(enforced: Any, where: str) -> list[str]:
    problems: list[str] = []
    if not isinstance(enforced, dict):
        return [f"{where}: type object"]
    allowed = {"mechanism", "binds", "file", "line"}
    for key in sorted(enforced):
        if key not in allowed:
            problems.append(f"{where}: additionalProperties {key!r}")
    for key in ("mechanism", "file", "line"):
        if key not in enforced:
            problems.append(f"{where}/{key}: required")
    mechanism = enforced.get("mechanism")
    if mechanism is not None and mechanism not in MECHANISMS:
        problems.append(f"{where}/mechanism: enum {list(MECHANISMS)}")
    binds = enforced.get("binds")
    if binds is not None and (
        not isinstance(binds, str) or not 2 <= len(binds) <= 60
        or not IDENTIFIER_PATTERN.fullmatch(binds)
    ):
        problems.append(f"{where}/binds: pattern ^[A-Za-z_][A-Za-z0-9_]*$, maxLength 60")
    # The conditional, both arms. A bind-parameter with no parameter named is a
    # query scoped on paper; a parameter on any other mechanism is a field
    # nothing reads, which is how an exception gets in.
    if mechanism == "bind-parameter" and binds is None:
        problems.append(f"{where}/binds: required when mechanism is bind-parameter")
    if mechanism is not None and mechanism != "bind-parameter" and binds is not None:
        problems.append(
            f"{where}: not — binds belongs to bind-parameter, not to {mechanism}"
        )
    problems.extend(_validate_file_and_line(enforced, where))
    return problems


def _validate_negative(negative: Any, where: str) -> list[str]:
    problems: list[str] = []
    if not isinstance(negative, dict):
        return [f"{where}: type object"]
    allowed = {"asserts", "expects", "file", "line"}
    for key in sorted(negative):
        if key not in allowed:
            problems.append(f"{where}: additionalProperties {key!r}")
    for key in ("asserts", "expects", "file", "line"):
        if key not in negative:
            problems.append(f"{where}/{key}: required")
    asserts = negative.get("asserts")
    if asserts is not None and asserts != "absent":
        problems.append(
            f"{where}/asserts: const absent — {asserts!r} tells an attacker the id exists"
        )
    expects = negative.get("expects")
    if expects is not None and (
        not isinstance(expects, str) or not 2 <= len(expects) <= 40
        or not EXPECT_PATTERN.fullmatch(expects)
    ):
        problems.append(
            f"{where}/expects: pattern an identifier or the two characters [], maxLength 40"
        )
    problems.extend(_validate_file_and_line(negative, where))
    return problems


def _validate_file_and_line(block: Any, where: str) -> list[str]:
    problems: list[str] = []
    path = block.get("file")
    if path is not None:
        if not isinstance(path, str) or not 3 <= len(path) <= 200 or not PATH_PATTERN.fullmatch(path):
            problems.append(f"{where}/file: pattern a repository-relative path with a directory in it")
        elif ".." in path.split("/"):
            problems.append(f"{where}/file: not — a path may not leave the repository")
    line = block.get("line")
    if line is not None and (
        not isinstance(line, int) or isinstance(line, bool) or not 1 <= line <= 1_000_000
    ):
        problems.append(f"{where}/line: minimum 1, maximum 1000000")
    return problems


# --------------------------------------------------------------------------
# the shape, and the finding it produces
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Finding:
    """One check's answer, in the shape gate_check uses and `caf` will read.

    `remediate` is not decoration: MD13's most transferable finding about
    yamine was that every check message carries the exact remediation, because a
    check that says only "not ok" makes the reader go and look.
    """

    id: str
    severity: str
    message: str
    remediate: str

    def render(self) -> str:
        return f"{self.severity.upper()} {self.id}: {self.message}\n    fix: {self.remediate}"


@dataclass
class Report:
    """Everything one run produced. `exit_code` is the only thing to branch on."""

    repo: Path
    findings: list[Finding]
    could_not_run: str | None = None

    def of(self, severity: str) -> list[Finding]:
        return [finding for finding in self.findings if finding.severity == severity]

    @property
    def exit_code(self) -> int:
        if self.could_not_run is not None:
            return EXIT_COULD_NOT_RUN
        if self.of("fail"):
            return EXIT_FAIL
        return EXIT_OK

    def render(self) -> str:
        lines = [finding.render() for finding in self.findings]
        lines.append("")
        if self.could_not_run is not None:
            lines.append(f"COULD NOT RUN {self.repo}: {self.could_not_run}")
            return "\n".join(lines)
        failed = len(self.of("fail"))
        warned = len(self.of("warn"))
        verdict = "FAIL" if failed else "OK"
        # Warnings counted separately, every time. A report that says "0
        # findings" when two of them were warnings is a report that lies.
        lines.append(
            f"{verdict} {self.repo}: {failed} failure(s), {warned} warning(s) — "
            + (
                "warnings do not move the exit code"
                if warned
                else "no warnings, so nothing was left unproven silently"
            )
        )
        return "\n".join(lines)


def finding(identifier: str, message: str) -> Finding:
    """Build a finding from the inventory, so an unknown id cannot be invented."""
    try:
        severity, _claim, remediate = FINDINGS[identifier]
    except KeyError:  # pragma: no cover - a test asserts the inventory is complete
        raise SystemExit(
            f"tenancy_check: {identifier} is not in FINDINGS. A finding the inventory "
            "does not describe is a finding nobody was told about."
        )
    return Finding(id=identifier, severity=severity, message=message, remediate=remediate)


# --------------------------------------------------------------------------
# reading the declaration, and the source it names
# --------------------------------------------------------------------------


def declaration_path(repo: Path) -> Path:
    return repo / DECLARATION


def read_declaration(repo: Path) -> tuple[Any, Finding | None]:
    path = declaration_path(repo)
    if not path.is_file():
        return None, finding("tenancy.declaration-missing", f"{DECLARATION} is not in {repo}")
    try:
        return read_yaml(path.read_text(encoding="utf-8"), path), None
    except Refusal as refusal:
        return None, finding(
            "tenancy.declaration-unreadable",
            f"{DECLARATION} could not be read: {refusal.detail} (at {refusal.path})",
        )
    except OSError as error:
        return None, finding("tenancy.declaration-unreadable", f"{DECLARATION} is unreadable: {error}")


def source_lines(path: Path) -> list[str]:
    """A file's lines, or an empty list if it cannot be read.

    A file that cannot be decoded as UTF-8 is not an error: it is a binary, and
    a binary in a declared source is something the checker walks past rather
    than a run that fails.
    """
    try:
        return path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []


def declared_files(repo: Path, sources: Any) -> tuple[list[Path], list[str]]:
    """The files in the declared sources, and the ones that are not there."""
    files: list[Path] = []
    missing: list[str] = []
    for item in sources or []:
        if not isinstance(item, str):
            continue
        root = repo / item
        if root.is_file():
            files.append(root)
        elif root.is_dir():
            for found in sorted(root.rglob("*")):
                if not found.is_file():
                    continue
                if SKIPPED_DIRECTORIES & set(found.relative_to(root).parts):
                    continue
                files.append(found)
        else:
            missing.append(item)
    return files, missing


# --------------------------------------------------------------------------
# the scanner — SQL, and nothing it cannot see
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Site:
    """One account-scoped statement the scanner recognised.

    `file`, `operation` and `subject` are the identity closure is checked on,
    and the line is deliberately NOT part of it: a refactor that moves a query
    down three lines must not turn ten declarations red, while a refactor that
    drops `and account_id = $2` must turn one red.
    """

    file: str
    line: int
    operation: str
    subject: str

    def key(self) -> tuple[str, str, str]:
        return (self.file, self.operation, self.subject)


def key_spelling(key: str) -> tuple[str, ...]:
    """The fleet spellings of a tenancy key, anchored at a word boundary.

    The boundary is what makes `account_id` not match inside `sub_account_id`. It
    is also why a declaration saying `expects: unchanged` cannot be satisfied by
    a line containing `assert_unchanged`: a token search with no boundary lets a
    declaration be met by a substring of a different identifier, which is the
    same false green as a proof pattern that matches a colour escape.
    """
    return tuple(
        re.compile(rf"(?<![A-Za-z0-9_]){spelling}(?![A-Za-z0-9_])")
        for spelling in (item.format(key=key) for item in KEY_SPELLINGS)
    )


def carries_key(line: str, matchers: tuple[re.Pattern[str], ...]) -> bool:
    return any(matcher.search(line) for matcher in matchers)


def sql_operation(line: str) -> tuple[str, str] | None:
    """`(operation, subject)` for a SQL statement opening on this line, or None.

    `select * from assets` and `delete from assets` name their table directly;
    a `select a.id from assets a where …` names it after the alias and is
    attributed to the nearest table this line or the ones above it names, which
    is the bounded rule `ATTRIBUTION_WINDOW` describes. A line that names two
    different tables is a join, and a join's boundary is the one this checker
    cannot see — so it is reported as unclassified rather than attributed to
    whichever table happened to be written first.
    """
    stripped = _SQL_COMMENT.sub("", line).strip()
    if not stripped:
        return None
    tables: list[str] = []
    for operation, pattern in _SQL_KEYWORDS.items():
        for match in re.finditer(pattern, stripped, re.IGNORECASE):
            tables.append(match.group(1).split(".")[-1].lower())
    if not tables:
        return None
    distinct = set(tables)
    if len(distinct) != 1:
        return None
    subject = tables[0]
    for operation in ("select", "update", "delete"):
        if re.search(_SQL_KEYWORDS[operation], stripped, re.IGNORECASE):
            return operation, subject
    return None


def strip_comment(line: str, suffix: str) -> str:
    """`line` without its comment, for deciding whether it CARRIES the key.

    Never used to decide whether a statement is scoped — only whether the key is
    mentioned at all — which is why the imprecision of "a `#` anywhere ends the
    line" is acceptable here and would not be one line up.
    """
    if suffix == ".sql":
        return _SQL_COMMENT.sub("", line)
    if suffix in {".rb", ".py", ".ex", ".exs", ".php"}:
        return _HASH_COMMENT.sub("", line)
    if suffix in {".go", ".ts", ".tsx", ".rs", ".java", ".kt", ".cs", ".js", ".mjs"}:
        return _SLASH_COMMENT.sub("", line)
    return line


def scan_file(repo: Path, path: Path, matchers: tuple[re.Pattern[str], ...]) -> tuple[
    list[Site], list[tuple[str, str]]
]:
    """Every account-scoped statement in one file, and what could not be attributed.

    The second list is the honest residue: a line carrying the tenancy key that
    this checker could not tie to a statement inside `ATTRIBUTION_WINDOW`. It is
    reported by name in `tenancy.enumeration-partial` and never silently
    counted as covered — the "darkroom has no routes" defect in its smallest
    form is a site this list would have hidden.
    """
    relative = path.relative_to(repo).as_posix()
    lines = source_lines(path)
    sites: list[Site] = []
    unattributed: list[tuple[str, str]] = []
    ddl_depth = 0
    for index, raw in enumerate(lines):
        line = index + 1
        if ddl_depth > 0:
            ddl_depth += raw.count("(") - raw.count(")")
            continue
        if _DDL.search(raw):
            ddl_depth = max(raw.count("(") - raw.count(")"), 0)
            continue
        stripped = strip_comment(raw, path.suffix)
        if not carries_key(stripped, matchers) or _INSERT.search(stripped):
            continue
        if path.suffix not in TEXT_SUFFIXES:
            unattributed.append((f"{relative}:{line}", "a file type this checker does not read"))
            continue
        resolved = sql_operation(stripped)
        if resolved is None:
            # The key is not on the statement's own line. Look above, within the
            # window, for the statement it belongs to.
            for back in range(1, ATTRIBUTION_WINDOW + 1):
                above = index - back
                if above < 0:
                    break
                resolved = sql_operation(strip_comment(lines[above], path.suffix))
                if resolved is not None:
                    break
        if resolved is None:
            unattributed.append((
                f"{relative}:{line}",
                f"no statement within {ATTRIBUTION_WINDOW} lines",
            ))
            continue
        operation, subject = resolved
        sites.append(Site(file=relative, line=line, operation=operation, subject=subject))
    return sites, unattributed


# --------------------------------------------------------------------------
# the checks
# --------------------------------------------------------------------------


def check_locations(repo: Path, entry_points: list) -> list[Finding]:
    """Every named file exists and every named line is really there.

    A declaration that points at nothing is worse than no declaration, because
    it reads as a boundary somebody looked at. This is the cheapest check in
    the file and the one that most often fails the day a service renames a
    directory.
    """
    found: list[Finding] = []
    for index, item in enumerate(entry_points):
        if not isinstance(item, dict):
            continue
        label = _label(item, index)
        for block_name in ("enforced", "negative"):
            block = item.get(block_name)
            if not isinstance(block, dict):
                continue
            relative = block.get("file")
            line = block.get("line")
            if not isinstance(relative, str) or not isinstance(line, int) or isinstance(line, bool):
                continue
            target = repo / relative
            if not target.is_file():
                found.append(finding(
                    "tenancy.location-missing",
                    f"{label}.{block_name}.file names {relative!r}, which is not a file in "
                    f"this repository",
                ))
                continue
            total = len(source_lines(target))
            if line < 1 or line > total:
                found.append(finding(
                    "tenancy.line-missing",
                    f"{label}.{block_name}.line is {line} and {relative} has {total} line(s)",
                ))
    return found


def check_enforcement(repo: Path, entry_points: list, matchers: tuple[re.Pattern[str], ...]) -> list[Finding]:
    """The declared line still carries the tenancy key, or the bind it names.

    One fact per mechanism, which is why they are ordered rather than stacked. A
    `bind-parameter` entry point's line carries the key *through* the bind — the
    account is what is being passed — so the bind token is the whole check, and
    reporting `tenancy.scope-lost` as well would say the same thing twice. The
    other three mechanisms are enforced by a predicate on the line, and the key
    is the whole check.
    """
    found: list[Finding] = []
    for index, item in enumerate(entry_points):
        if not isinstance(item, dict):
            continue
        label = _label(item, index)
        enforced = item.get("enforced")
        if not isinstance(enforced, dict):
            continue
        relative = enforced.get("file")
        line = enforced.get("line")
        mechanism = enforced.get("mechanism")
        if not isinstance(relative, str) or not isinstance(line, int) or isinstance(line, bool):
            continue
        target = repo / relative
        if not target.is_file():
            continue  # check_locations already reported it, with the same line
        lines = source_lines(target)
        if not 1 <= line <= len(lines):
            continue
        text = strip_comment(lines[line - 1], target.suffix)
        if mechanism == "bind-parameter":
            binds = enforced.get("binds")
            if isinstance(binds, str) and not re.search(
                rf"(?<![A-Za-z0-9_]){re.escape(binds)}(?![A-Za-z0-9_])", text
            ):
                found.append(finding(
                    "tenancy.bind-missing",
                    f"{label} declares mechanism bind-parameter with binds={binds!r} at "
                    f"{relative}:{line}, and that line does not pass it — {text.strip()!r}. A query "
                    "that still says `account_id = $2` while nothing passes $2 is scoped on paper "
                    "and unscoped in fact, which is the defect a predicate check cannot see",
                ))
            continue
        if not carries_key(text, matchers):
            found.append(finding(
                "tenancy.scope-lost",
                f"{label} declares {mechanism} at {relative}:{line} and that line does not carry "
                f"the tenancy key — {text.strip()!r}. Either the scoping moved to another line or "
                "it was dropped, and the two want different fixes",
            ))
    return found


def check_closure(repo: Path, entry_points: list, sites: list[Site],
                  unclassified: list[tuple[str, str]]) -> list[Finding]:
    """The enumeration is closed in BOTH directions — where it can be.

    A site the scanner found that nobody declared means the declaration is a
    summary. A declaration whose site the scanner can no longer find means the
    scoping was dropped, or the code was deleted, and both are the same event
    from the boundary's point of view. Either direction alone is a summary.

    A declared entry point the scanner cannot classify is NOT counted as either
    direction. It goes into `tenancy.enumeration-partial` with its name, which
    is the difference between "this service has no account scoping" and "this
    checker cannot read this service" — the difference between an answer and a
    shrug that reads like one.
    """
    found: list[Finding] = []
    scannable: list[tuple[str, tuple[str, str, str]]] = []
    for index, item in enumerate(entry_points):
        if not isinstance(item, dict):
            continue
        enforced = item.get("enforced")
        if not isinstance(enforced, dict):
            continue
        relative = enforced.get("file")
        operation = item.get("operation")
        subject = item.get("subject")
        if not all(isinstance(value, str) for value in (relative, operation, subject)):
            continue
        if operation not in SCANNER_OPERATIONS:
            unclassified.append((
                _label(item, index),
                f"{relative}:{enforced.get('line')} (operation {operation} is not a statement "
                "this checker's scanner reads)",
            ))
            continue
        if not _is_scannable(repo / relative, enforced.get("line"), operation):
            unclassified.append((
                _label(item, index),
                f"{relative}:{enforced.get('line')} (the scanner could not read this line as "
                f"a {operation})",
            ))
            continue
        scannable.append((_label(item, index), (relative, operation, subject)))

    declared = {key: label for label, key in scannable}
    found_keys = {site.key() for site in sites}
    for key, label in sorted(declared.items()):
        if key not in found_keys:
            found.append(finding(
                "tenancy.entry-absent",
                f"{label} declares {key[1]} on {key[2]} at {key[0]}: the tenancy key is no "
                "longer in that statement. The scoping was dropped or the code is gone, and "
                "both leave the boundary where it was",
            ))
    declared_keys = set(declared)
    for site in sorted(sites, key=lambda item: item.key()):
        if site.key() not in declared_keys:
            found.append(finding(
                "tenancy.undeclared-entry",
                f"{site.operation} on {site.subject} at {site.file}:{site.line} carries the "
                "tenancy key and nobody declared it",
            ))
    if unclassified:
        named = "; ".join(f"{label} at {where}" for label, where in sorted(unclassified))
        found.append(finding(
            "tenancy.enumeration-partial",
            f"this checker reads SQL statements and account-key predicates, and it could not "
            f"classify {len(unclassified)} account-scoped site(s): {named}. This declaration is "
            "NOT proven closed, and this is a warning rather than a failure because no language "
            "agnostic text scanner can settle it — read the named files and confirm each one is "
            "declared",
        ))
    return found


def _is_scannable(target: Path, line: Any, operation: str) -> bool:
    """Can the scanner read this exact line as this operation, right now?

    Asked about the DECLARED line, not about the file: the identity of an entry
    point is its subject and what it does, so a declaration is closure-checked
    when the scanner can still find that subject doing that thing anywhere in
    the declared sources — which is what makes a dropped predicate
    (`tenancy.entry-absent`) a different event from a moved one
    (`tenancy.scope-lost`).
    """
    if not isinstance(line, int) or isinstance(line, bool) or not target.is_file():
        return False
    lines = source_lines(target)
    if not 1 <= line <= len(lines):
        return False
    resolved = sql_operation(lines[line - 1])
    if resolved is not None:
        return resolved[0] == operation
    for back in range(1, ATTRIBUTION_WINDOW + 1):
        above = line - 1 - back
        if above < 0:
            return False
        resolved = sql_operation(lines[above])
        if resolved is not None:
            return resolved[0] == operation
    return False


def check_denials(repo: Path, entry_points: list) -> list[Finding]:
    """The negative assertion is in the tests, on the line, and asserts absence.

    Two directions, both red. Leave the assertion alone and weaken it in the
    test and the declared spelling of 'nothing' is no longer there
    (`tenancy.denial-missing`). Weaken it in the declaration too and the schema
    refuses a refusal outright (`tenancy.denial-refuses`), because a `403` is an
    enumeration oracle and the contract's answer is nonexistence (D33).
    """
    found: list[Finding] = []
    for index, item in enumerate(entry_points):
        if not isinstance(item, dict):
            continue
        label = _label(item, index)
        negative = item.get("negative")
        if not isinstance(negative, dict):
            continue
        if negative.get("asserts") != "absent":
            found.append(finding(
                "tenancy.denial-refuses",
                f"{label} answers another account's resource with "
                f"{negative.get('asserts')!r} rather than nonexistence. A refusal confirms the "
                "id exists, which is an enumeration oracle; assert nil, [] or NotFound instead",
            ))
            continue
        relative = negative.get("file")
        line = negative.get("line")
        expects = negative.get("expects")
        if not all(isinstance(value, str) for value in (relative, expects)) \
                or not isinstance(line, int) or isinstance(line, bool):
            continue
        target = repo / relative
        if not target.is_file():
            continue  # check_locations already reported it
        lines = source_lines(target)
        if not 1 <= line <= len(lines):
            continue  # likewise
        if not re.search(rf"(?<![A-Za-z0-9_]){re.escape(expects)}(?![A-Za-z0-9_])",
                         strip_comment(lines[line - 1], target.suffix)):
            found.append(finding(
                "tenancy.denial-missing",
                f"{label} declares its negative assertion at {relative}:{line} with "
                f"expects={expects!r}, and that line does not carry it — "
                f"{lines[line - 1].strip()!r}. Nothing in the service's tests asserts that "
                "account A is refused account B",
            ))
    return found


def check_honest_zero(repo: Path, account_scoped: Any, sites: list[Site], entry_points: list,
                      unclassified: list[tuple[str, str]]) -> list[Finding]:
    """`accountScoped: false` is a claim, and it is checked.

    Both halves. A service saying `true` with an empty list is the same omission
    wearing a declaration. And a service saying `false` has to have no
    account-scoped code AT ALL — including code the scanner could not classify,
    which is the half that matters: "the declared tenancy key appears in the
    declared sources" needs no parser, so the honest zero is checkable even for a
    language this checker cannot read. A service that legitimately holds no
    customer data — `kit` and `caf` are the fleet's two — says so here and is
    believed only while it stays true.
    """
    found: list[Finding] = []
    evidence = len(sites) + len(unclassified)
    if account_scoped is False:
        if evidence:
            where = ""
            if sites:
                where = f", starting at {sites[0].file}:{sites[0].line}"
            elif unclassified:
                where = f" ({len(unclassified)} of them at {unclassified[0][0]})"
            found.append(finding(
                "tenancy.honest-zero",
                f"the service declares no account scoping and the scan found {evidence} "
                f"place(s) carrying its tenancy key in the sources it declared{where}. An "
                "omission is not a zero, and a key that appears in the source is a key this "
                "service is scoping by — whether or not this checker could classify the "
                "statement it appears in",
            ))
    elif account_scoped is True and not entry_points:
        found.append(finding(
            "tenancy.enumeration-empty",
            "the service says it scopes by account and declares no entry point that does it",
        ))
    return found


def check_scan(repo: Path, scope: Any, sites: list[Site], missing: list[str]) -> list[Finding]:
    """Two warnings about the scan itself, because a scan that reads less than
    it was told to read must not read as a clean answer."""
    found: list[Finding] = []
    if missing:
        found.append(finding(
            "tenancy.scan-narrowed",
            f"scope.sources names {missing} which is not in this repository, so the scan "
            f"covered less than the declaration asked it to",
        ))
    if isinstance(scope, dict):
        key = scope.get("key")
        if isinstance(key, str) and not sites:
            found.append(finding(
                "tenancy.scope-key-unused",
                f"no account-scoped statement this scanner can read carries {key!r}. That is not "
                "proof the service has no scoping — it is usually a key spelled differently from "
                "the column it is really scoping by, and on a service written in a language this "
                "scanner cannot classify it is what an honest 'I cannot see this' looks like",
            ))
    return found


def _label(item: dict, index: int) -> str:
    identifier = item.get("id")
    return identifier if isinstance(identifier, str) and identifier else f"entryPoints[{index}]"


# --------------------------------------------------------------------------
# the run
# --------------------------------------------------------------------------


def check(repo: Path) -> Report:
    """Check one service's tenancy declaration against that service."""
    repo = repo.resolve()
    if not repo.is_dir():
        return Report(repo=repo, findings=[], could_not_run=f"{repo} is not a directory")
    if sys.version_info < MINIMUM_PYTHON:  # pragma: no cover
        return Report(
            repo=repo, findings=[],
            could_not_run=(
                f"tenancy_check needs python {MINIMUM_PYTHON[0]}.{MINIMUM_PYTHON[1]} or newer. "
                "This is exit 2 and never 0: a check that could not run has not checked "
                "anything."
            ),
        )

    declaration, problem = read_declaration(repo)
    if problem is not None:
        return Report(repo=repo, findings=[problem])
    if not isinstance(declaration, dict):
        return Report(repo=repo, findings=[finding("tenancy.schema", f"{DECLARATION} is not a mapping")])

    # NOTE, and it is a deliberate departure from gate_check: gate_check returns
    # as soon as the schema fails. This file does not, because the two
    # diagnoses it can add on top of a malformed declaration are the ones a
    # reader most needs. `negative.asserts: refused` is both a schema violation
    # and an enumeration oracle, and a reader who is told only "your file is
    # invalid" goes looking for a typo.
    problems = validate(declaration)
    found: list[Finding] = []
    if problems:
        found.append(finding(
            "tenancy.schema",
            f"{DECLARATION} does not satisfy schemas/tenant-isolation.schema.json: "
            + "; ".join(problems[:6])
            + (f" (and {len(problems) - 6} more)" if len(problems) > 6 else ""),
        ))

    scope = declaration.get("scope") if isinstance(declaration.get("scope"), dict) else {}
    entry_points = declaration.get("entryPoints")
    if not isinstance(entry_points, list):
        entry_points = []

    files, missing = declared_files(repo, scope.get("sources"))
    matchers = key_spelling(scope.get("key")) if isinstance(scope.get("key"), str) else ()
    sites: list[Site] = []
    unclassified: list[tuple[str, str]] = []
    for path in files:
        found_sites, unattributed = scan_file(repo, path, matchers)
        sites.extend(found_sites)
        unclassified.extend(unattributed)

    found += check_locations(repo, entry_points)
    found += check_enforcement(repo, entry_points, matchers)
    found += check_closure(repo, entry_points, sites, unclassified)
    found += check_denials(repo, entry_points)
    found += check_honest_zero(repo, declaration.get("accountScoped"), sites, entry_points, unclassified)
    found += check_scan(repo, scope, sites, missing)
    return Report(repo=repo, findings=found)


def to_json(report: Report) -> str:
    return json.dumps(
        {
            "repo": str(report.repo),
            "exitCode": report.exit_code,
            "couldNotRun": report.could_not_run,
            "counts": {severity: len(report.of(severity)) for severity in SEVERITIES},
            "findings": [
                {
                    "id": item.id,
                    "severity": item.severity,
                    "message": item.message,
                    "remediate": item.remediate,
                }
                for item in report.findings
            ],
        },
        indent=2,
        sort_keys=True,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="tenancy-check",
        description="Check a service's tenant-isolation declaration against that service.",
    )
    parser.add_argument("repo", nargs="?", default=".", help="the repository to check (default: .)")
    parser.add_argument("--json", action="store_true", help="emit the findings as JSON")
    parser.add_argument(
        "--explain",
        action="store_true",
        help="list every finding this checker can report, and what each one means",
    )
    arguments = parser.parse_args(argv)

    if arguments.explain:
        for identifier in sorted(FINDINGS):
            severity, claim, remediate = FINDINGS[identifier]
            print(f"{identifier}  [{severity}]\n  {claim}\n  fix: {remediate}")
        return EXIT_OK

    report = check(Path(arguments.repo))
    print(to_json(report) if arguments.json else report.render())
    return report.exit_code


if __name__ == "__main__":
    sys.exit(main())
