# Changelog

All notable changes to the cafaye **spec** are recorded here. This repository
is schemas, docs and validators, so "notable" means *a rule changed or a
document was clarified* — not a release of code. Bump guidance lives in
[README.md](README.md#spec-versioning).

Consumers pin a spec range in their manifest (`core: ^0.2.0`), so the
**breaking** section below is the one that matters when a service CI fails to
resolve.

## [Unreleased]

The payload reconciliation, the observability spec, the contract-test
harness, the SLO and error-budget specification, and the gate declaration.

### Fixed — the gate self-test reported "no python found" on machines that had one

**No schema changed, no declaration changed, and no consumer is affected.** The
candidate list, the order, the version floor and the `CAFAYE_GATE_PYTHON`
override are all exactly as they were. What changed is one condition inside the
loop, and three cases that prove it. This **fixes a false negative** — it can
only turn a previous `exit 1` into a run, never the reverse.

- **`harness/tests/gate_self_test.sh` walks the whole candidate list and stops at
  the first interpreter that PASSES the version check**, rather than at the first
  one that merely *resolves*. The loop used to `break` out of
  `python3 python3.13 python3.12 python3.11 python` as soon as `command -v`
  succeeded and check the version afterwards, so a candidate that RESOLVES was
  mistaken for a candidate that QUALIFIES.
- **What that cost, on a real machine rather than a thought experiment.** Where
  `python3` is 3.9.6 the search took it, stopped, and printed
  `gate_self_test: no python >= 3.11 found; set CAFAYE_GATE_PYTHON` while 3.13
  and 3.14 sat unused on the same PATH. A **false negative in the project's own
  proof-of-failure** — the one script whose job is to prove the gate checker can
  go red, reporting that it could not run at all — and indistinguishable from a
  machine that genuinely has nothing. That indistinguishability is why it
  survived: the only way to see it is to be the developer whose `python3` is
  3.9.6, while `bin/prime` exports `CAFAYE_GATE_PYTHON` and CI runs on
  `setup-python`, so the machine that could show it was the one machine nobody
  ran it on.
- **`CAFAYE_GATE_PYTHON` is honoured exactly as before**, including the half that
  is easy to break while fixing the other: an override that is **too old is still
  an error**, not a reason to go looking for a second interpreter. Quietly
  substituting a different program would make every `PASS` line below a claim
  about an interpreter nobody chose. Both halves are asserted, and the override
  case was proved load-bearing by breaking only the refusal: it then reports
  `exited 0` and answers with the host's own 3.14.
- **`resolve_interpreter` is the only place this decision is made**, and
  `--which-python` runs that decision and nothing else, so the cases drive the
  real search rather than a copy of it. One line, deliberately: asking the winner
  for its version too would probe it twice and put a second copy of its name in
  the trace the cases assert exactly.
- **`harness/tests/fixtures/interpreter-path/`** — two PATHs, no repository and no
  declaration in either, so nothing here is checked by `gate_check.py`. `stale-first`
  is a too-old `python3` followed by a qualifying `python3.13`; `stale-only` has
  all five names and every one too old. **The new-enough stub delegates to a real
  interpreter** (`sys.executable` of the one already running the script) rather
  than answering the version probe with a hardcoded `exit 0`: the bug is *when the
  loop stops*, not *what it decides about the interpreter it stopped at*, so only
  a real `sys.version_info` tells a fixed search from a broken one. For the same
  reason **no path to any interpreter is committed** — a red proof that passes on
  the machine that wrote it is not a red proof.
- **Three cases, all driving the real search through `--which-python`,** and the
  reason they all use that flag is a measurement rather than a preference. The
  `stale-first` case must end up on the *fixture's* `python3.13` and not merely on
  some new-enough interpreter — asserted on the whole path, because a bare
  `python3.13` would match the host's too. The `stale-only` case asserts exit 1,
  the **exact** refusal line, and **empty stdout** — empty because the exit has to
  come from the precondition rather than from some case failing forty lines in.
  The third pins a `CAFAYE_GATE_PYTHON` that resolves and is too old, which stays
  an error rather than becoming a reason to go looking: that half is the easy one
  to lose while fixing the other, and a search that quietly answers with something
  else makes every `PASS` line in the script a claim about an interpreter nobody
  chose. It is a guard rather than a red proof — it stays green with the loop
  condition reverted, which is what a guard is for.
- **Every case asserts the trace — the ordered list of candidates actually
  consulted.** That is what separates *"tried the stale `python3`, rejected it,
  went on"* from *"happened to skip it"*, and on `stale-only` it is what proves
  the loop did not give up early. **An empty trace is the signature of this
  defect**: the probe is what makes a stub record itself, so a loop that stopped
  at the first name that *resolved* probes nothing at all. The failure message
  therefore says `<none — nothing was probed at all>` and carries the child's
  exit code and chosen path, because "consulted nothing" is otherwise
  indistinguishable from a broken fixture — the one diagnosis that would send
  someone to fix the wrong file.
- **All proved red before proved green, and the red is fast.** With the original
  condition restored: `stale-first` reports the 3.9.6 stub as the chosen
  interpreter at exit 0, `stale-only` reports the same stub at exit 0 instead of
  refusing, both with nothing probed. Nineteen seconds, ordinary non-zero exit,
  no leftover processes. `bin/prime` is green at `196/196 passed` both with
  `CAFAYE_GATE_PYTHON` pinned and with it **unset**, and the self-test is also
  green run directly on a PATH whose `python3` answers `Python 3.9.6` with 3.13
  and 3.14 behind it — the run that used to print "no python found".
- **The `timeout` case no longer shells out to a bare `python3`,** which is a
  second-order fix this packet forced into the open. Its fixture gate used
  `python3` for a three-second CPU-bound wait, so on the developer whose
  `python3` is 3.9.6 the gate failed instantly and the case reported
  `gate.nonzero` where it meant to report `gate.timeout`. The search fix is what
  made that machine run the script at all, and the case then went red for a
  reason unrelated to the thing it tests. It is a pure-bash `SECONDS` wait now,
  because a case about the checker enforcing a budget has no business caring
  which python the gate happens to use. Still proved load-bearing: with the
  budget raised the case reports `expected exit 1, got 0`.
- **The obvious "stronger" test was a trap, and this is the sentence to keep.**
  The `stale-only` case was first written to run the **whole script** and assert
  its exit code, on the reasoning that with no qualifying interpreter the script
  exits at the precondition and there is nothing to recurse into. That reasoning
  is false the moment the search is broken — which is the only time the case
  matters. The child resolves the stub, the precondition lets it through, and the
  child runs every case down to that one and spawns another child. Measured:
  eighteen seconds in, `97132 -> 97666 -> 97667 -> 98130`, each link a
  `gate_self_test.sh` whose parent is the last, still growing, killed by hand. So
  it passed on green code and **exhausted a machine on broken code** — inside
  `bin/prime`, where the declaration allows 900 seconds, it would have spent
  those and reported a timeout that names nothing. Every case here drives
  `--which-python`, which runs the same search and the same refusal and stops
  before the first case; the flag's branch sits *after* the precondition, so on a
  PATH where the search finds nothing the two runs are the same execution up to
  and including the exit.
- **`gate.yml`'s floor is unchanged at `minimum: 196`, and that is measured.**
  These are cases in a shell script, not tests in `tests/test_specs.py`, and
  `test_the_gate_floor_is_not_below_the_suite_core_claims_to_have` counts
  `test_*` functions there. `bin/prime` prints `196/196 passed` on this tree.

### Added — the tenant-isolation declaration

**No schema a service consumes changed**, and no manifest, envelope, payload,
SLO or gate declaration is constrained by any of this. A service that vendors
`schemas/` picks up one new file it does not use and is unaffected. There is no
**contract change** and nothing to re-vendor; the cost of adopting this is
opt-in and is a file a service writes about itself.

- **`schemas/tenant-isolation.schema.json`** — one file per service at its root,
  `tenancy.yml`, declaring the account-scoped entry points, the **file and line**
  where each is scoped, the mechanism (`query-filter`, `bind-parameter`,
  `repository-method`, `middleware`), and the negative assertion each one
  requires — `negative.asserts` is a `const: absent`, because cross-tenant access
  is answered as **nonexistence**, never as a refusal. `accountScoped` is a
  required boolean so a service with no boundary says so with an explicit,
  checkable zero rather than by omission.
- **`harness/tenancy_check.py`** and `harness/bin/tenancy-check` — a checker of
  declarations, standard library only, reporting `{ok, warn, fail}` with
  **`warn` never moving the exit code**. It proves the declared files and lines
  exist, that each declared line still carries the tenancy key (or the bind it
  names), that the enumeration is **closed in both directions** against the SQL
  it can read, and that every negative assertion is in the service's tests and
  asserts absence. It runs on Python 3.9: no TOML, no subprocess, unlike
  `gate-check`'s 3.11 floor.
- **`harness/tenancy_findings.json`** — the sixteen findings, each with the claim
  it makes and the exact command that fixes it, plus five `notEnforced` entries
  saying what the checker does **not** prove — including that it reads the
  negative assertion rather than running it.
- **`harness/tests/tenancy_self_test.sh`** — the red proof: one conforming
  fixture and three more (an honest zero, and a language the scanner cannot
  read), sixteen deliberate breakages each asserting the checker goes red **and
  names the finding and the entry point**, three warning cases asserting a
  warning stays green, and two green cases asserting the report names what the
  checker cannot see. The control is asserted **warning-free**, not merely green.
- **Six worked examples** — `examples/valid/tenancy.account-scoped.yml`,
  `examples/valid/tenancy.honest-zero.yml`, and four negative cases with their
  tables in `examples/invalid/README.md`.
- **`docs/tenancy.md`** — why the enumeration is declared rather than inferred
  (counting account-scoped routes by pattern gives 96 for guard and **0** for
  darkroom, and a grep reporting "no routes" about a service with account-scoped
  queries is worse than no grep), why the line is exact, why `insert` is not an
  operation, and what the checker cannot prove.
- **core's CI runs the tenancy self-test as a step of its own**, beside the gate
  checker's and the harness's. A self-test nobody invokes is not a test.
- **Fourteen tests in `tests/test_specs.py`**, and the `gate.yml` floor raised to
  187 with them. They are not only inventory and documentation checks: the
  fourteenth drives **every failure-severity finding through `check()` in the
  suite itself**, one case per finding, because the self-test is a CI step and
  not part of `bin/prime`. Measured before that test existed, deleting
  `check_denials` from the checker left `bin/prime` reporting 186/186 passed —
  a green gate over a checker that no longer checked. Deleting any of the six
  check functions now turns the gate red.

Measured against the fleet, every repository fails with
`tenancy.declaration-missing`: none of the thirteen publishes a boundary. See
[`REPORT-core-15.md`](REPORT-core-15.md) for the table, including which of the
three zeros are real zeros. **No adopter was fixed in this packet** — a contract
with no failing adopter is a contract nobody has tested against reality.

### Added — the gate declaration

**No schema a service consumes changed.** `schemas/gate.schema.json` is new and
nothing in it constrains a manifest, an envelope, a payload or an SLO, so a
service that vendors `schemas/` picks up a file it does not use and is
unaffected. The one **contract change** is core's own: `mise run test` is now an
alias for `mise run prime`, so the fleet's spelling of "run the gate" is right
here too, and `mise run test` keeps working.

- **`schemas/gate.schema.json`** — one file per repository at its root, `gate.yml`,
  declaring the gate command as an **argv** (never a shell string), whether the
  gate is self-contained or what it needs from the machine and the command that
  satisfies each thing, the CI workflow that must agree, and `gate.proof` — the
  patterns the gate's own output must contain, with an optional `minimum` floor.
- **`harness/gate_check.py`** and `harness/bin/gate-check` — a checker of
  declarations, standard library only, reporting `{ok, warn, fail}` with
  **`warn` never moving the exit code**. Two phases: the static one compares the
  declaration to the tree, and `--prove` also **runs** the gate and requires
  every declared proof to appear. A run that exits 0 having run nothing is
  `gate.proof-missing`, and it is a failure.
- **`harness/gate_findings.json`** — the twenty-two findings, each with the claim
  it makes and the exact command that fixes it, plus three `notEnforced` entries
  saying what the checker does **not** prove.
- **`harness/tests/gate_self_test.sh`** — the red proof: one conforming fixture
  copied twenty-three times, one breakage each, every red asserting the exit
  code is 1 **and** naming the finding it expects; five warning cases asserting
  the exit code is still **0**; and a case proving the checker's report does not
  carry a value out of the gate's environment.
- **`gate.yml`** and **`docs/gate.md`** — core's own declaration, and the
  document that measures the two alternatives it is not: mise tasks alone, which
  can be run but not checked, and a CI-only declaration, which cannot be run
  locally and has no second copy to drift against.
- **Two examples and four negative cases**, each with a row in
  [`examples/invalid/README.md`](examples/invalid/README.md).
- **A CI step for the proving phase and one for the red proof.** `bin/prime` runs
  the static half only, because the proving half runs `bin/prime`; a gate that
  verifies itself by running itself proves nothing and terminates.

**D30** (a proof, or a description), **D31** (3.11 for the gate checker, 3.9 for
the contract harness) and **D32** (no CI is a warning) are open.

### Fixed — a proof is matched against bytes that still carry terminal colour

**No schema changed.** `schemas/gate.schema.json` is untouched, so this is a
checker behaviour change and a documentation change. It **fixes a false red and a
false green**, and it can turn a previously-green declaration red — see below.

**Ruled as MD17** (manager-owned, in the workspace `DECISIONS.md`, not one of
core's `D` numbers): the checker strips ANSI from the gate's captured output
before applying any `proof[].match`. The direction is not re-opened here; the
implementation notes are in `harness/gate_check.py` and the format rules are in
[`docs/gate.md`](docs/gate.md#the-output-is-matched-colour-free).

- **`harness/gate_check.py` strips ANSI from the gate's captured output before
  applying any `proof[].match`.** One `strip_ansi` function, one call site, in
  `prove()` where the output is read; stripping inside each of the four checks
  that apply a pattern is four call sites that will drift. The gate's **log keeps
  the raw bytes** — stripping applies to matching only, because the log is the
  operator's evidence.
- **Why it was a defect in the checker and not in a declaration.** A person writes
  a proof pattern by reading their terminal, and a terminal does not show them the
  bytes. `^[ ]*Tests[ ]+([0-9]+) passed` is correct for the line a human sees and
  cannot match `\x1b[2m      Tests …`. That produced `gate.proof-missing` on a gate
  that had just proved, in the same log, that it ran 377 tests. Not vitest-specific:
  `cargo test`, `pytest`, `go test` under a TTY and colour-enabled `mix test` are
  the same shape.
- **The quieter false green this also removes.** `\x1b[38;5;208m` is a 256-colour
  **index**, so a gate that ran 3 tests and printed `\x1b[38;5;208m3 passed` matched
  `^.*?([0-9]+).* passed$` with group(1) equal to `38` — `minimum: 38` was green
  over a suite of three.
- **Sequences handled:** CSI (`ESC [ … final`, and 8-bit `0x9b`), OSC (`ESC ] …
  BEL`/`ST`, and 8-bit `0x9d`), DCS, and the two-character escapes. **An
  unterminated sequence is deliberately left in place** rather than consumed to
  end-of-input, which would delete every following line — the proof included — and
  manufacture a green.
- **What stripping does to a pattern, stated in
  [`docs/gate.md`](docs/gate.md#the-output-is-matched-colour-free) rather than left
  for an adopter to discover.** It can **broaden** an anchored pattern to a line it
  could not reach, and since `minimum` reads the **last match**, that can change
  the number the ratchet sees; and `.` counts escape bytes before and visible bytes
  after. What is unconditional is that stripping only ever **deletes**, so it
  cannot fabricate a match.
- **Three green cases and two colour reds** in
  `harness/tests/gate_self_test.sh` — a colourising gate that really ran, a proof
  behind an OSC hyperlink, a proof below an unterminated OSC, and two that must
  still go red (an absent proof, and a suite below its floor) so the stripper
  cannot swallow evidence.

**Adopters: re-read your `proof[].match` patterns.** They are now applied to
colour-free text. A pattern written to match escape-bearing bytes stops matching;
one that relied on `^` being blocked by an escape may now match more lines. Both
are documented above and in `docs/gate.md`.

### Fixed — the local gate was weaker than CI, and nothing said so

**No schema changed. No declaration format changed. Nothing an adopting
repository has to do.** `harness/gate_check.py` is untouched, `gate.yml` is
untouched apart from its proof floor, and a service's `gate.yml` means exactly
what it meant. What changed is **core's own `bin/prime`**, and one number in it.

- **`bin/prime` now runs `harness/tests/gate_self_test.sh`, the gate checker's own
  red proof, and its failure fails `bin/prime`.** It used to be a CI step only.
  So a developer on a clean checkout ran the one command core's own
  documentation and every adopting repository's `mise.toml` name, saw
  `179/179 passed`, exited 0 — and had learned **nothing** about whether
  `harness/gate_check.py` could detect anything. Replace the checker with a
  function that returns 0 and `bin/prime` stayed green while CI went red, which
  is the definition of a local gate that does not gate.
- **It is not the recursion the static half avoids.** `--prove` runs the declared
  gate, and core's declared gate is `bin/prime`, so `bin/prime` must never call
  it — that reasoning stands and is unchanged. The red proof is different in kind:
  it runs assertions about the checker in throwaway copies of
  `harness/tests/fixtures/gates/conforming`, a repository whose declared gate is
  three lines long and is not `bin/prime`. Nothing in it reads core, runs
  `bin/prime`, or knows this repository exists, so there is no cycle. They also
  answer different questions: `--prove` asks whether *this* gate ran, and a
  checker that could only say *yes* would look exactly like a passing gate to it.
- **It cannot skip, and its report is read.** A missing script, no `bash`, or an
  interpreter older than 3.11 is a non-zero exit naming the precondition — never
  the word "skipped". A red proof that exits 0 having printed **no counts** is
  refused, because an exit code is not a report. The counts block is parsed: every
  category must be present and non-empty, the control must have printed its own
  `PASS` line, the skip count must be zero, and the logged case lines must cover
  the counts. Pass and skip counts are printed **separately**, because a single
  number where there are two is how a skip hides inside a pass.
- **It runs on the pinned interpreter.** `bin/prime` exports
  `CAFAYE_GATE_PYTHON` as the venv interpreter — the same one the suite runs on —
  instead of letting the script scan `PATH`. Without that, a local gate would
  depend on the machine: a laptop whose system Python is 3.9 fails a checkout CI
  is green on, and one on 3.13 proves something CI did not.
- **The red proof's own counts were wrong, and were fixed.** Its footer printed
  `breakages that went RED: 25`. **Eighteen** cases went red. The 25 was a
  hand-incremented *case label* — incremented before warnings too, so that
  printed lines can be referred to by the same number the comments use — printed
  as if it were a tally, and it counted seven warning cases that stayed green. Each
  category is now counted inside the function that runs it, every category has a
  row (three had none: the colour cases and the leak case), and the footer prints
  variables rather than literals. Measured now: **18 red, 7 warning-green, 3
  colour-green, 2 colour-red, 12 spellings accepted, 4 extractor assertions, 1
  leak case, 1 control, 0 skipped.**
- **Cost, stated because a cost nobody mentions is a cost somebody rediscovers:**
  `bin/prime` goes from about 20 seconds to about 58, warm. The red proof runs
  **last**, after the suite, so a red suite still costs 20 seconds and not 58. The
  proof floor in `gate.yml` is 900 seconds, so CI has room. Six tests were added
  to `tests/test_specs.py`, so the floor moved 173 → **179** in the same commit.
- **One sharp edge this introduces is closed.** `gate.proof` is matched against
  everything `bin/prime` prints with the floor reading the **last** match, and a
  second program now prints into that output — so a proof-shaped line from the red
  proof could satisfy the gate's proof or be read as the floor's number. Every
  literal `printf`/`echo` in the red proof is checked against every pattern
  `gate.yml` declares, with conversion specs filled in as digits.
- **Asymmetry, deliberate.** `harness/tests/self_test.sh` — the **contract**
  harness's red proof — is still CI-only. The gate checker's red proof runs
  locally because it guards the checker `bin/prime` ran on the line above.
  Reasoning in [`docs/gate.md`](docs/gate.md#the-third-thing-binprime-runs-and-why-it-is-not-the-recursion).

### Added — the SLO and error-budget spec

**No event, envelope or manifest changed; every existing schema is untouched.**
Three new files under `schemas/telemetry/`, so a service that vendors
`schemas/` picks them up when it re-vendors, and nothing in a conforming
service's world moved. What *is* a contract change is the thing this packet
specifies for the first time: what an SLO is.

- **Three schemas and one document.**
  [`slo.schema.json`](schemas/telemetry/slo.schema.json) is one service's
  declaration — a Sloth `prometheus/v1` file, which is the artifact R1 settles on
  because `sloth validate -i slos/` is a single static binary that walks a
  directory with no cluster and no Docker daemon, because it *generates* the
  recording rules and the burn-rate alerts, and because its SLI is two PromQL
  strings: **the one representation all six languages can be checked against
  without a Go or Rust parser.**
  [`slo-windows.schema.json`](schemas/telemetry/slo-windows.schema.json) is the
  burn-rate catalog, pinned once for the fleet.
  [`slo-metrics.schema.json`](schemas/telemetry/slo-metrics.schema.json) is the
  SLI catalogue and label allowlist — **the mechanical check that replaces a
  shared client library**, which is what six languages would otherwise each grow
  a copy of. [`docs/slo.md`](docs/slo.md) is all three written as prose.

- **The tier alone decides whether a page is generated** (R4), and the schema
  derives both alert switches from it. `critical` and `high` page and ticket,
  `low` tickets, `none` publishes nothing. Required, with no default. A page per
  SLO across seven services is textbook alert fatigue, and the cost is not the
  page: the self-hoster who mutes one at 3am about a twenty-user deployment has
  also muted the `critical` SLO, and the instrument is gone in one gesture.
  `page_alert.disable: false` on a `low` SLO does not validate, and the negative
  example is that document with nothing else changed.

- **The burn-rate windows are 14.4/6/3/1 at 5m+1h, 30m+6h, 2h+1d, 6h+3d**, pinned
  byte-wise by `prefixItems` — *order included*, because the generator consumes
  them in short/long pairs and a reordered catalog still validates as a set while
  producing four alerts with the wrong pairing. Per-service windows are refused:
  Sloth takes `--slo-period-windows-path` for exactly that, which is why the
  declaration is closed.

- **The arithmetic is published because the number will be questioned**, and
  **it does not agree with the period.** R2's `14.4 = 0.02 x 720h` is a *thirty*-day
  budget; R3's period is twenty-eight days, where 2% is 13.44. Both are
  implemented as ruled, so the fleet's fast-burn alerts fire about **7% early** —
  the safe direction — and
  `test_the_window_catalog_is_the_workbooks_numbers` asserts the workbook's
  arithmetic, the 28-day arithmetic *and the direction of the gap*, so the
  inconsistency cannot harden into a number nobody recomputed. **D27**.

- **An SLO is scoped to a named user-visible operation, not to a service.**
  `authentication_succeeds` therefore *requires* `http_route`: an SLO whose total
  is every request identity ever served can be green while nobody can log in.
  The four candidates are already written out — authentication, an event
  accepted into an outbox, an email dispatched, an invoice computed — each named
  after the **operation**, never after a service, and each with the Postgres-
  normalized metric names it needs. **No service declares one yet**: an SLO
  written before the metric exists is a commitment nobody can keep, so which tier
  each service gets is **D29** and the packet stops here.

- **An objective is never 100%**, as `exclusiveMaximum: 100` rather than a
  comment. An objective of 100% has an error budget of zero, so no burn rate is
  worth interrupting anyone for and the alert can only be *reacted to*. That
  needed two keywords the harness did not implement, so the evaluator grew
  `exclusiveMinimum`/`exclusiveMaximum` and
  `test_the_harness_evaluator_agrees_with_jsonschema_on_every_example` now covers
  all three SLO schemas — which is where `if`/`then` inside `prefixItems`,
  `const` beside a `$ref`, and `not` on a string get their receipts too. The
  keyword inventory asked for them by name before the harness had them:
  *core's schemas use ['exclusiveMaximum', 'exclusiveMinimum'] and
  harness/cafaye_contract.py does not implement them.*

- **Two denylists, because there are two reasons.** Unbounded dimensions
  (`tenant`, `user_id`, `account_id`, `request_id`) are barred on the
  2000-combination-cap grounds `metrics.schema.json` already established;
  infrastructure signals (`cpu`, `memory`, `pod`, `restart`) are barred because
  an SLO on them is not an SLO on behaviour. One merged list would keep the
  enforcement and lose the second reason, which is what a reader has at the
  moment they are about to add one. The schema's `not` is asserted to be exactly
  the union of the two lists, so neither can describe something the schema does
  not enforce.

- **The multi-tenancy question is answered here rather than deferred.** The
  metric is aggregate; per-tenant views are **recording rules and logs and
  traces** over the `resourceAttributes`, because the measurement attributes that
  count toward the cap are exactly where `tenant_id` is bargained out and the
  resource attributes are where it is exempt. `docs/slo.md` says so in one
  paragraph with the reason, because the next reader will ask and "the metric
  schema already prohibits it" is the answer.

- **The spanmetrics migration is specified, and the collector is what moves.** A
  service derives its HTTP SLI from **native** OpenTelemetry instrumentation, never
  from a `spanmetrics`-derived metric: the connector's unit default is migrating
  from `ms` to `s`, which renames
  `traces_span_metrics_duration_milliseconds_bucket` to `…_seconds_bucket` and
  breaks every latency query in every service at once — between the service and
  Prometheus, where no service-level test can see it. The collector version is
  pinned in the kit templates and **a bump is a breaking change**.
  `http.server.request.duration` is Stable with recommended bucket boundaries,
  and `http.route` is low-cardinality by construction, which is what
  `metrics.schema.json` already encodes.

- **No SLA, and it is a test.** The acronym appears in no `const`, `enum` or
  `default` under `schemas/` and in no example, and a `not` refuses it in any SLO
  prose. What a self-hoster gets instead is stated in the shape of an honest
  statement: **No SLA commitment.** Intended behaviour on adequate hardware,
  measured by the operator, with the exclusions published — which is the part
  that makes it honest, and which includes 4xx never counting as a failure and
  `email_dispatched` measuring *dispatched* rather than delivered.

- **Eight harness rules, twenty-eight breakages, and two the self-test caught
  in my own code.** `slo.schema`, `slo.window-token`, `slo.unknown-metric`,
  `slo.no-unbounded-dimension`, `slo.no-infrastructure-slo`,
  `slo.sli-canonical`, `slo.window-override` and `slo.duplicate-name`, each
  declared in `harness/rules.json` with where it lives and each proved able to go
  red by a breakage that **names the rule it expects**. The catalogue is read out
  of `schemas/` rather than copied into the harness, so `--expect-digest` covers
  it. Breakages 23 and 24 found that `_denylisted` scanned the queries and not the
  declaration's `labels` — where the mistake arrives first — so a `tenant_id` came
  back as `slo.sli-canonical`: a true statement about a consequence, reported in
  place of the mistake. It now scans three places.

- **`sloth validate` is not run by core's gate**, which is a decision and not an
  omission (**D28**). Taking the dependency would mean core's gate reaching the
  network for a Go binary on a runner that may be air-gapped, against a
  repository whose whole dependency story is one venv and four PyPI packages. The
  harness implements the checks that matter in the standard library, and
  `slo.sli-canonical` compares each query against the canonical composition *as a
  string* — stricter about the shape than Sloth is, blinder about the grammar.
  PromQL parsing is named in `harness/rules.json`'s `notEnforced`, and
  `docs/slo.md` gives the pinned command for a service that has network.

- **Twenty-one new tests, and the counts. Suite: 119 → 140.** Every schema has a
  valid document and a named invalid document per constraint; every harness rule
  has a breakage; `test_every_rule_the_harness_can_emit_is_proved_able_to_go_red`
  is new and asserts the self-test breaks *every* rule rather than a number of
  them. CI's two-entry-point guard reads the count out of both runs, so it moves
  in one place.

- **Four new open decisions: D26, D27, D28, D29.** **D26** — do the cafaye
  fields (`tier`, `period`, `labels`, `catalogEntry`) live inside the Sloth
  document or in a cafaye document kit converts? Sloth's tolerance of unknown
  keys could not be checked offline, so the answer is the one that leaves a
  four-line fallback. **D27** — the factors come from a 30-day budget and the
  period is 28. **D28** — may the gate take the `sloth` dependency? **D29** —
  which tier each of the seven services gets.
### Added — the contract-test harness

**No schema changed. No consumer has to re-vendor.** Nothing under `schemas/`
was touched, so there is nothing here that should make a service's vendored copy
stale. PLAN.md §4 Phase 0 named a contract-test harness among core v0's five
deliverables; three had shipped, the harness had not, and four services each
wrote their own version of it instead — muse's pinned-SHA byte comparison,
darkroom's vendored copy, courier's document-against-router test, pantry's drift
test.

- **`harness/`** — `bin/cafaye-contract`, `cafaye_contract.py`, `rules.json`,
  `tests/self_test.sh` and six fixtures. A service's CI is three lines:

  ```
  harness/bin/cafaye-contract --core ../core --expect-digest <sha256> .
  ```

  **Standard library only, no dependencies, offline.** A Python *package* would
  need a venv in a Go repository; a compiled binary would make core a release
  repository with per-platform artifacts, which is the one thing AGENTS.md rules
  out twice. A single file that imports nothing outside the standard library runs
  on every runner core and every service already builds on.

- **Exit `2` is a refusal, and it is not a soft `1`.** `0` conforms, `1` does
  not, `2` the run could not happen — no core, no manifest, or YAML outside the
  declared subset. A contract check that cannot find the contract and reports
  success is worse than no contract check, because it converts an unknown into a
  green badge. That is the defect behind guard's live-Redis tier, muse's
  `MUSE_CORE_SCHEMAS` tier, identity's `TEST_DATABASE_URL` tier and darkroom's
  `--ignored` tests, and
  `test_the_harness_fails_loudly_when_core_is_absent` is the assertion.

- **The pin is a sha256 over `schemas/`, not a git ref.** A ref names a commit in
  a repository the harness is not allowed to fetch; a digest names bytes, which
  is what a service compiles against. It covers all of `schemas/` rather than the
  two files a service happens to vendor, it is printed on every run, and
  `--expect-digest` turns "different" into a red build. muse's `CORE_REF` is the
  fleet's existing precedent and it is a *ref*; the digest is the same answer on
  a laptop and in CI, which a checkout step and a working directory are not.

- **Where each rule lives, field by field.** `harness/rules.json` gives every
  rule an `enforcedBy` — a schema file, a document and a heading, or a named
  function — and `test_the_rule_inventory_says_where_every_rule_lives` checks each
  claim is true. The honest answer is **one rule in `schemas/` and sixteen in the
  harness's own source**, and that is the finding rather than a failure of it:
  `docs/openapi-conventions.md` says in its own words that those rules are
  review-enforced "until a future `caf contract lint` lands". See **D23**.

- **The evaluator and the YAML reader are receipts, not claims.** The standard
  library has no JSON Schema and no YAML, so core has a hand-written evaluator
  for the 27 keywords its schemas use and a reader for a declared subset of YAML.
  `test_the_harness_evaluator_agrees_with_jsonschema_on_every_example` compares
  violated keywords with `jsonschema` over every example in `examples/`, in both
  directions, and
  `test_the_harness_implements_every_keyword_core_schemas_use` holds the keyword
  list equal in both directions. It caught a real bug within the hour: a `type`
  array is a union, and the first version reported a violation per non-matching
  member, so the envelope's `data` — declared as any of seven types, correctly
  holding an object — produced six failures.

- **Twenty breakages, twenty reds, and a control first.**
  `harness/tests/self_test.sh` is kit's shape: every breakage names the rule id
  it expects, because "the harness went red" is a weak claim when seventeen
  checks can make it red. All seventeen rules have at least one. Writing it found
  that `event.payload-schema-missing` is structurally coupled to
  `event.unknown-published` — every catalogued type has a payload schema, so a
  published type without one is necessarily not catalogued — which is recorded in
  the inventory rather than papered over with a contrived fixture.

- **The self-test is a documented command CI also runs.** Not part of `bin/prime`:
  a self-test inside every gate invocation would be a second gate that can
  disagree with the first, which is what `tests/validate.sh` was written not to
  create. The CI step reads its own log and compares the breakages the footer
  claims against the assertions logged, and that guard was proved able to fail
  against three doctored logs.

- **Twenty-seven tests, and the counts. Suite: 92 → 119.** They are in a new
  section 7 of `tests/test_specs.py`, and the twenty-three that could be written
  before the harness existed were shown failing first, and the four added afterwards were shown
  failing against the reader they constrain — a named missing file each
  time, not a collection error. CI's two-entry-point guard reads the count out of
  both runs, so it moves in one place.

- **Four new open decisions.** **D22** (core's own suite does not assert
  `format: uri`, because `jsonschema` registers no checker for it without
  `rfc3987-validator` — the same gap `tests/requirements.txt` already documents
  for `date-time`, and the harness made it visible by checking it), **D23** (do
  the sixteen rules the harness keeps in code become a JSON Schema), **D24** (the
  event catalog and the spec version are markdown and prose, not data — so the
  harness parses a table and cannot resolve a `core:` constraint at all), and
  **D25** (may a service document `/healthz` and `/readyz`? three do, one
  deliberately does not with a paragraph explaining why, and
  `docs/openapi-conventions.md` does not say which is right — found by running
  the harness at the fleet, not by building it).

- **The YAML subset was reversed by the fleet, and that is the whole story of
  this packet.** The reader shipped reading a small subset and refusing
  everything else, on the reasoning that a guess means validating a document
  nobody wrote. Then it was pointed at the eleven real service repositories and
  **eight of eleven refused**: six on a `description:`, two on a leading `---`,
  the rest on `tags: [users]`.

  Guessing wrongly means a *schema* error printed against a value the harness
  invented, which sends a person to the wrong field. Refusing a document the
  whole fleet writes means the harness checks nothing at all. So the subset is
  now the one the fleet writes — block scalars with chomping and indentation
  indicators, plain scalars continued across lines, flow collections including
  across lines, floats, a leading `---` — and what is left is what no real
  document needed. Over the thirty-three real `cafaye.yml` and `openapi/*.yaml`
  files in the workspace: **thirty-three byte-identical to PyYAML, zero
  mismatched, zero refused.**

  The fold was the risky part and it was wrong twice: the first version tracked
  whether the *previous* line was more indented, the second whether the *next*
  one was, and billing's `change_plan` description is the document that showed
  both were wrong. YAML keeps the break on **both** sides of a more-indented
  line. `test_the_harness_yaml_reader_agrees_with_pyyaml_on_every_fold` is the
  receipt, and it is a separate test because a fold can be almost right.

- **What the harness found in the fleet on its first run.** Eight of eleven
  conform. `identity` publishes two OIDC client event types that core's catalog
  does not list and has no payload schema for, and `mfa.enabled`/`.disabled` have
  no payload schema either; `darkroom` publishes three event types with neither;
  and `identity`, `darkroom` and `pantry` all document `/healthz` and `/readyz`,
  which `courier` deliberately does not. Every one of those is checkable by hand
  today and none of it is checked by anything — which is the gap, in the only
  terms that matter. The probe finding is a spec gap rather than a service bug
  and it is **D25**.

- **What it does not do, in its own document.**
  [`docs/contract-harness.md`](docs/contract-harness.md) says so in the first
  third rather than at the end: it validates a service's *declared* contracts and
  never looks at a byte of live traffic, so PLAN.md §3's "each service's CI
  validates responses against the spec" — the richer reading of "contract test" —
  is **still owed**. `harness/rules.json`'s `notEnforced` block names four things
  it does not check and why.

- **This packet migrates no service.** One packet, one repository: a harness
  adopted by four services at once is four workers in four languages discovering
  four things nobody anticipated, and the manager would not be able to tell which
  of them found a bug in the harness.

### Added — CI, on kit's reusable workflow

**No schema changed. No consumer has to re-vendor.** This is build
configuration: nothing under `schemas/` was touched, so there is nothing here
that should make a service's vendored copy stale.

- **`.github/workflows/ci.yml`** calls
  `cafaye/kit/.github/workflows/ci.reusable.yml@master` with
  `language: 'none'`, plus a companion `gate` job that runs `bin/prime` on the
  interpreter `mise.toml` pins, `bin/prime --pytest`, and the drift guards.

  `none` rather than `python` because kit's `none` is documented for "a
  repository with **no service manifest at all**", which is what core is; the
  seven language jobs are not inapplicable here, they are red on arrival
  (`uv sync --frozen` exits 2 with "No pyproject.toml found" in a repository
  that has never had one and should not). `tests/validate.sh` is the three lines
  kit's contract looks for — an `exec bin/prime "$@"`, no logic — so there is
  still one gate and one suite.

- **Two tests, and the counts.** `test_the_ci_workflow_calls_kit_at_the_path_kit_documents`
  exact-matches the cross-repository `uses:` line, because a substring search is
  what let kit-02's unresolvable path through:
  `cafaye/kit/workflows/ci.reusable.yml@master` contains every interesting
  token and is the string that does not work.
  `test_core_declares_no_service_manifest` keeps `none` honest. Both were shown
  failing before the workflow existed, and the second was run against a scratch
  `pyproject.toml` to prove it can go red. Suite: **90 → 92**.

- **`git diff --exit-code` over the whole tracked tree**, which is kit's
  lockfile rule generalised. core has no lockfile, and the tree is what six
  services vendor: a gate that could rewrite a schema would put un-reviewed
  bytes into every one of them.

- **Both entry points must report the same number of tests.** Two entry points
  to one suite, and the cheap assertion is not "it exits 0" — it is that both
  collect 92. A renamed test or a module only the script runner imports is
  invisible in either log alone.

  Two bugs in that guard were found by running the step locally against real and
  doctored logs, not by reading it: `cut -d/ -f2` on `92/92 passed` yields `92
  passed`, and under `set -e` a `grep` matching nothing killed the step before
  its own emptiness check could explain itself.

**A red build here is not "core is broken"** — it is "a rule the fleet depends
on no longer holds", and the workflow says so at the top of the file, because six
repositories consume these schemas and a docs nit is the wrong escalation.

The pin is read from `mise.toml` and asserted against the interpreter that
arrives rather than written into the workflow twice. `python-version-file:
mise.toml` reads as if it should work and **silently installs nothing**: the
action looks for `project.requires-python` or `tool.poetry.dependencies.python`,
and mise's `[tools]` is neither.

There is **no environment-gated tier** in this repository, and none is
implied: 92 tests, no `os.environ` read anywhere in `tests/test_specs.py`, no
skip, no database, no network beyond `tests/setup.sh`'s four PyPI packages.

### Changed — `error.type` is a closed vocabulary, and the status error obliges it

**BREAKING for a service that emits a class, and for kit-03, which is reading
these schemas in parallel.** muse is the only service that emits one today and it
is **not** migrated here — see "not migrated" below.

- **`error.type` is an `enum`, not a `pattern`, on all three signals.** The
  twelve classes plus `_OTHER`, byte-identical in
  [`traces`](schemas/telemetry/traces.schema.json),
  [`metrics`](schemas/telemetry/metrics.schema.json) and
  [`logs`](schemas/telemetry/logs.schema.json).

  **Why.** The previous constraint was a `pattern` and a 64-character cap, which
  bound the **shape** of the value and not the **vocabulary** — so
  `error.type = "user_42_email_invalid"` validated cleanly on every signal.
  Snake_case, twenty-two characters, a series per value. On metrics that is
  `tenant_id` on a measurement under a name that sounds like a classification:
  the same 2000-combination cap, the same silent undercount, the same dashboard
  that renders and is wrong. The description promised a bounded vocabulary and
  the schema did not have one, and a rule the schema does not enforce is not a
  cafaye rule (**D14**, ratified, now implemented). The `pattern` and the cap
  stay alongside the `enum` as the second line — they cannot reject a value the
  `enum` accepts — and a test asserts all three copies are byte-identical.

  One `enum` on all three signals is not tidiness. It is what makes the semconv
  rule that `error.type` is **identical** on a span and on its metric for the
  same operation enforceable at all: no JSON Schema can compare two documents, so
  the coupling has to be structural.

- **Four semconv rules encoded rather than described.** core-04 stated these and
  enforced none of them; with `error.type` deleted from `span.muse.json` the file
  still validated. They are constraints now, with negative examples.

  - **Span status `error` obliges `error.type`, and `error.type` obliges a failed
    status.** The biconditional is the point: the class is present exactly when
    the span failed, so its **absence is the load-bearing not-an-error marker**
    rather than an omission. On a duration histogram the samples carrying the
    class are the errors; a success that carries one moves the numerator and
    makes the error rate a number nobody can trust.
  - **`otel.status_code` may not contradict `status.code`.** Not a fifth rule —
    without it the first one is about a span with two statuses, which has no
    status to be obliged.
  - **Handled and retried errors are not recorded at all.** `SHOULD NOT` has no
    schema keyword, so it is encoded as **unrepresentable**: no signal allowlists
    an attribute a service could use to say "this attempt failed and I
    recovered", and no class in the vocabulary names one. The realistic
    violation is a well-meaning `error.handled: true` added in six months, and it
    now fails the suite.
  - **`error.type` is required on the operation duration histogram and absent on
    success** — the doc states it and the first rule above encodes the
    success half of it.

- **`error.message` stays absent, and its reasoning is kept in full.** It is
  `NOT RECOMMENDED` for metrics and spans: unbounded cardinality, and it
  duplicates span status. More concretely it is the one attribute already on a
  natural allowlist — every tracing SDK adds it by default — and the one that
  could carry a prompt, because a provider's content-policy rejection quotes the
  offending content back. That refusal is now recorded as `provider_rejected`,
  which says what happened with no content in it.

- **Two structural claims that were described everywhere and asserted nowhere,
  now asserted.** Found by mutation against core-04: deleting
  `additionalProperties` from the traces allowlist left the suite **green**, and
  adding `critical` to the span-status enum left it **green**. The status enum is
  the fleet-wide error predicate, so a fourth value invented by one service is a
  dashboard that silently misses it — which is exactly what the schema's own
  description promised could not happen.

- **Two more decisions**, both four paragraphs and both raised by core-06 rather
  than by the observability work: **D20** (kit's `language: none` job installs no
  interpreter, so the `kit` job runs the suite on the runner's own Python and
  only `gate` is pinned) and **D21** (a breaking schema change still has no
  re-vendor fan-out, even though six services vendor these schemas). D21 changes
  nothing in this release: **nothing under `schemas/` was touched**, so no
  consumer needs to re-vendor, and the gap is recorded rather than closed.

- **Two new decisions**, both four paragraphs: **D18** (which twelve classes, and
  the test — is this class's rate worth an alert on its own? — rather than the
  list) and **D19** (whether semconv's `_OTHER` belongs in a snake_case
  vocabulary; it is the one documented exception, because a closed enum with no
  escape hatch gets widened under pressure and an alert on `_OTHER` is an alert
  that this service has not classified its own errors).

- **Stability marked honestly.** `error.type` and the trace status rules are
  **Stable**; the cross-signal coupling document, `recording-errors.md`, is
  **Development**. Where core encodes that coupling, each schema says so rather
  than implying the whole model has frozen.

- **The fleet-wide predicate is span status `Error`, not `error.type`** — stated
  plainly in [`docs/observability.md`](docs/observability.md#errortype) rather
  than left to be implied by the schema's shape. Partition by `service.name`,
  filter on status `error`, use `error.type` as a drill-down **inside** a
  service, and **never as a global grouping key**.

- **Not migrated, deliberately: muse.** It emits `error.type =
  "ProviderAuthError"` and `"CircuitOpen"`, and
  `tests/test_trace_propagation.py` asserts both. That is D14's stated cost of
  flipping and it is a separate packet; this one changes the contract. The
  file-by-file mapping a cold author needs is a table in
  [`docs/observability.md`](docs/observability.md#what-is-not-migrated-yet).

- **Sixteen new tests, and fifteen more examples** — one valid span per class,
  so `ls examples/valid/telemetry/error-type.*` is the whole vocabulary, plus
  five negative examples including the one that matters most: a well-shaped,
  snake_case, under-64-characters value that is not in the vocabulary, on traces
  and on metrics. The test asserts that value produces **exactly one** violation
  and that it is the `enum`, so it cannot pass because the pattern caught it —
  only the vocabulary can. The doc's class table is asserted against the schema
  too, so the two halves of the contract cannot drift apart quietly.

  Mutation-proved thirteen ways, all red. The one that caught a test of mine:
  deleting the `otel.status_code` mirror rule left its test green, because the
  document it built also tripped the rule above it — a test passing on someone
  else's constraint.

### Added — the observability spec

- **[`schemas/telemetry/`](schemas/telemetry/) and
  [`docs/observability.md`](docs/observability.md)** — the observability spec
  (PLAN.md §7b), as seven schemas and 33 tests. Core owns the event envelope the
  same way, so this is a contract and not a README paragraph: a rule that is not
  in `schemas/` is not a cafaye rule, and six services in six languages would each
  otherwise invent their own span names and their own idea of which attributes
  are safe.

  - **`span-naming.schema.json`** — one scheme, all six languages:
    `<service>.<operation>[.<target>]`, the same *shape* as the event grammar's
    `<service>.<entity>.<action>` and for the same reason. Low-cardinality **by
    construction**: a segment is at most fifteen characters, which is what
    refuses `muse.user.usr_01J9Z8QK5M4N7P2R3T6V8W9X0A` without core growing a
    cafaye-id pattern to recognise one. `GET /users/:id`, `get_user` and
    `users.GET` are all rejected, and `get_user` and `users.GET` are what a
    fleet ships when nobody has said. **D15** records the alternatives, including
    the OTel HTTP convention (`{method} {route}`), which is rejected for putting
    the route in the name.

  - **`metrics.schema.json`** — the part with teeth, and the reason this packet
    exists. OpenTelemetry caps a metric stream at **2000 distinct attribute
    combinations**; on overflow the SDK folds everything into a single
    `otel.metric.overflow=true` point and drops every measurement attribute.
    Totals stay correct, per-dimension breakdowns silently undercount, and
    nothing anywhere reports an error. So `tenant_id`, `user_id`, `account_id`,
    `request_id`, `trace_id` and eight more are **prohibited** as measurement
    attributes and **required** on `resourceAttributes` instead, which are
    attached once per process, exempt from the cap, and survive on the overflow
    point — so a per-tenant total stays answerable when the measurement has
    folded. The prohibition is enforced twice (absent from the allowlist *and*
    named in a `not`, so adding it to the allowlist later does not quietly
    succeed), the two lists are disjoint by construction, and a test asserts that
    a resource name is *rejected* when submitted as a measurement attribute.
    That last one is the mechanism: moving identity onto the measurement to get
    a per-tenant breakdown is what produces a dashboard that looks right and is
    wrong.

  - **`redaction.schema.json`** — prompt and completion content must never appear
    in a telemetry span, encoded as an **allowlist, default-deny**, because
    "don't log prompts" in prose has been tried across this fleet and does not
    hold. The realistic leak is not an attacker; it is a well-meaning
    `muse.prompt` added in six months by someone debugging a routing decision, in
    a service whose prompts are other customers' data. No allowlisted name on
    any of the three signals contains a word that names content — muse's canary
    at `muse/tests/test_trace_propagation.py`, promoted to a spec assertion.
    `error.message` is prohibited *by name* because a tracing SDK adds it by
    default and a content-policy rejection quotes the offending content back, so
    it is a prompt by another route. The may-record side is in the schema too
    (token counts, model id, latency, status, finish reason), because a policy
    that only says what may **not** be recorded is not implementable.
    `enforcedAt` is an enum with `collector` as the only value a cafaye policy may
    carry, so kit's collector config and a service's SDK setup are both checked
    against one file. **D13** argues the enforcement point with evidence.

  - **`otel-endpoint.schema.json`** — `*_OTEL_ENDPOINT` is the contract, the
    shipped collector is only its **default value**, and `required` is a
    `const: false`, which is the field that separates on-by-default from
    mandatory. The no-op path is four negative properties — **no buffering, no
    retry, no warning spam, no dial at boot** — each pinned to `none`, so a
    declaration that admits any of them does not validate. It is implemented by
    the OTel spec's own `OTEL_SDK_DISABLED`, not a cafaye invention, because
    re-implementing "disabled" in six languages is how six services acquire six
    definitions of it. `disabledBy` is keyed by signal and requires all four, so
    a declaration cannot document a no-op that covers only traces — a service
    still phoning home for metrics is discovered by a customer's invoice.

  - **`probes.schema.json`** — `healthz` gets `maxItems: 0` and `readyz` gets
    `minItems: 1`, so **a `readyz` that checks nothing fails the schema** and a
    `healthz` that starts consulting the database cannot validate. The second is
    the restart loop: a liveness probe that fails on a dependency restarts a
    process that is fine, turning a database outage into a fleet-wide crash loop
    and destroying the evidence needed to diagnose it. darkroom is the pattern
    (`/healthz` never touches a dependency, `/readyz` really runs `select 1`),
    and both probes are `auth: exempt` by explicit path allow-list, because a
    probe behind the auth middleware returns 401, every instance is marked
    unhealthy, and the rollback says nothing about authentication.

  - **`traces.schema.json` / `logs.schema.json`** — the other two per-signal
    allowlists, with the same rules applied. Logs are the smallest by design
    (`maxProperties: 12`, well under OTel's default 128): every log attribute is
    a candidate for a Loki label, every label is a stream, and streams are what a
    log store runs out of.

- **`error.type` as the fleet's error grouping key.** The user asked whether
  there is one place to see all errors for the whole system; this is the part of
  the spec that makes the answer yes rather than a wall of ungrouped text. It is
  a low-cardinality class — snake_case, ≤ 64 characters, the same shape on every
  signal — and never a message, a stack trace, or a per-service exception class
  name, because `ProviderAuthError` (Python), `ErrProviderAuth` (Go) and
  `ProviderAuthError` (Elixir) are one failure in three taxonomies, and three
  taxonomies means six places rather than one. **D14** has the alternatives and
  the cost, including the fact that flipping it touches a muse test.

- **`fleet.yml` gains a required `telemetry` block per service** — which
  signals it exports today, which `*_OTEL_ENDPOINT` variable points at it, and
  whether it serves HTTP. Required, so "what is instrumented across the fleet"
  has one answer rather than six, and so a service dropped from the declaration
  is a service nobody checks. Every service currently declares `signals: []`
  except muse, which is the honest record rather than claiming instrumentation
  that is not there.

- **Five new numbered decisions**, all with the four paragraphs AGENTS.md asks
  for: **D13** the redaction enforcement point, **D14** `error.type` granularity,
  **D15** the span-name form, **D16** the endpoint variable name, and **D17** a
  divergence this packet found rather than fixed.

### Fixed

- **A cross-repo drift the observability spec made visible.** `muse` reads
  `MUSE_OTEL_EXPORTER_OTLP_ENDPOINT` — the OpenTelemetry standard spelling,
  which is what `muse/tests/test_resilience_config.py` asserts — while
  `muse/tests/test_telemetry.py` and PLAN.md §7b both call it
  `MUSE_OTEL_ENDPOINT`. Three places, three spellings, and the code agrees with
  neither document. Core specifies `<SERVICE>_OTEL_ENDPOINT` (**D16**), `fleet.yml`
  records the divergence, and **D17** carries it as an open decision with the
  alternative (adopt the OTel standard names, in which case muse is already
  conforming and the divergence disappears) rather than leaving it only in a
  commit message. No service was modified: muse is a read-only reference here.

### Added — the payload reconciliation

- **[`fleet.yml`](fleet.yml) and
  [`schemas/fleet.schema.json`](schemas/fleet.schema.json)** — a machine-readable
  record, per service repository, of what that service's own `cafaye.yml`
  declares on `master`, with the full 40-character commit each one was read at
  and the day it was read. Per service, three lists: `events` (published today,
  in the conforming three-segment form), `cataloguedOnly` (a catalog row nobody
  publishes yet — a promise, not a claim), and `manifestViolations` (types a
  manifest spells in a way that breaks the grammar, transcribed verbatim).

  **Why.** The catalog was asserted only against core's own
  `examples/valid/*.cafaye.yml`, which core also writes, so the assertion could
  only ever catch core disagreeing with itself. A service could advertise
  anything. courier did: five types in the two-segment form v0.2 froze away
  reached master and are still there. `fleet.yml` is the missing other side of
  that comparison, and it gives `caf contract lint` one file to consume instead
  of a re-derivation of the catalog that can disagree with this one.

  It is a record of other repositories, so it is versioned as one: `sourceCommit`
  and `readOn` are required, and `manifestViolations` entries are deleted when
  the publisher corrects its manifest.

- **Thirteen new per-event payload schemas**, plus one rewritten, for events the
  fleet already publishes but core had never described. See the payload table in
  [docs/event-naming.md](docs/event-naming.md#payload-schemas): courier's five,
  `muse.tokens.consumed`, and billing's seven more. Fifteen of the catalog's
  thirty rows now have a schema; the other fifteen belong to types no service
  publishes yet. The root cause of the gap was the same as the root cause of
  courier's violation — nothing compared a real service's manifest against core's
  catalog — so the schemas and the check land together.

  **courier's five**, `courier.email.queued`, `.delivered`, `.bounced`,
  `.complained` and `courier.notification.suppressed`. Four carry the four fields
  `Courier.Deliver` builds, which is `message_id`, `user_id`, `notification_type`
  and `email` — and nothing from the caller's payload, because the envelope goes
  to every subscriber on the bus and a verification token in there is a credential
  leak into a fan-out. `courier.notification.suppressed` has **no** `message_id`,
  because nothing was rendered, addressed or sent: the entity is the recipient,
  so the payload is `user_id`, `notification_type`, `email` and a `reason`. No
  provider diagnostic appears in the bounced or complained payloads, because
  courier has no webhook receiver yet and a field no publisher emits is a contract
  that lies.

  Two fields are deliberately absent across all five, each recorded in
  [DECISIONS.md](DECISIONS.md): a provider message id (real — courier's own test
  fixture carries `provider_id`, its `Deliver` module does not), and a recipient
  key the fleet can join on (**D7** — courier uses a bare uuid, identity
  publishes `usr_…`, and no schema can reconcile that).

  **`muse.tokens.consumed`**, exactly the five fields `muse/metering.py` builds:
  `model`, `provider`, `tokens_in`, `tokens_out`, `cost_micros`. No account, no
  request id, no price — a payload schema is closed, and a field added now is one
  a future schema carries forever. The negative example is the price table: the
  per-1k rates really are in the publisher's `Price` object and really do move,
  so an event carrying them would say the cost and the price were true at the same
  instant. `muse` gets a catalog section and
  `examples/valid/muse.cafaye.yml` to go with it.

  **`consumed` joins the action vocabulary.** muse has published this type since
  it existed and `consumed` was not on the list, which the vocabulary itself
  says is a manager decision (**D9**). `muse.usage.recorded` was the alternative
  and is rejected in D9: it already means a different fact on a different subject.
  The call is reversible in one word plus a deprecation cycle, and it is recorded
  rather than made quietly.

  **billing's seven more** — `billing.customer.created`, `billing.plan.created`,
  `billing.plan.updated`, `billing.subscription.updated`,
  `billing.subscription.canceled`, `billing.payment.succeeded`,
  `billing.payment.failed` — plus the rewrite above. Two of them earned their keep
  on their own.

  `billing.payment.succeeded` **has two shapes**: billing emits it from an
  invoice (`invoice_id`, `subscription_id`, `attempt_count`,
  `next_payment_attempt`) *and* from a one-time Checkout session
  (`checkout_session_id`, `client_reference_id`). Rather than flatten them into
  an optional-everything schema, the schema declares a `oneOf` — exactly one
  shape, never both, never neither — and both are covered by a valid example,
  checked by a new `test_payload_schema_variant_examples_validate` so neither is
  assumed (**D11**). The negative example claims to be both at once, which is the
  mistake `oneOf` exists to make impossible.

  `billing.payment.failed`'s `amount` is **what could not be collected** — the
  amount due, never the amount paid. Its negative example carries a second
  `amount_paid: 0` field, because on a failed charge that zero is truthy and
  reads as "nothing was collected" to a consumer that wants the charge size.
  billing's own source comment names this exact bug.

  `billing.customer.created`'s `metadata` is **the one deliberately open object in
  the repository** (**D12**): it is a free-form `jsonb` bag, and closing it would
  make the field permanently `{}`. Every other object in every schema here is
  closed, and that field's own description says it is the exception.

- **Every published event type now has a catalog row and a payload schema, checked
  against the services' real manifests.** `fleet.yml` is the input;
  `test_every_published_fleet_event_has_a_catalog_row_and_a_payload_schema` is
  the assertion, and it is the check courier's five types would have failed the
  day they were declared — the one with no equivalent anywhere else. Proven by
  hiding courier's payload schemas and watching it fail with all five named.

### Breaking

- **`billing.subscription.started`'s payload schema was rewritten.** The v0.2
  version required `subscription_id`, `plan_id` and `account_id` as
  `sub_…`/`pln_…`/`acc_…` — a world in which billing holds cafaye-prefixed ids.
  billing has no subscriptions table and cannot invent ids it does not have; its
  webhooks carry the processor's `sub_…`, `cus_…` and `price_…` and its primary
  keys are bare uuids. The schema now describes what billing emits, with
  `processor` and `processor_event_id` on every payload so a consumer can tell a
  fact billing knows from a fact billing was told. **D10**, with the alternatives
  and the cost of reversing it.

  The alternative was to keep the text and write a valid example full of ids
  billing never sends — which validates, passes the suite, and fails on every
  real event. That is the outcome the rewrite exists to prevent.

### Fixed

- **`billing.plan.updated` had no catalog row.** billing has published it from
  its own manifest since it existed, and core's suite could not see it for the
  reason above. Row added; `billing.plan.created` and `billing.customer.created`
  had rows and no payload schemas, which is the same gap one layer down.

- **`muse` had no catalog section at all.** The service publishes a type and core
  had never heard of it, for the same reason. Section added, and an example
  manifest so the bidirectional assertion covers the new publisher rather than
  skipping it.

- **The `eventType` and `serviceName` patterns now have a third copy to keep in
  step** (`schemas/fleet.schema.json`), and the parity test covers all three. A
  pattern that appears once is a rule; a pattern that appears three times with
  two assertions is still one rule, but the assertions have to name all three.

### Changed

- **Open decisions are tracked in [DECISIONS.md](DECISIONS.md), not as callouts
  in `docs/`.** `docs/` stays free of undecided callouts because
  `test_no_open_decision_callouts_remain_in_the_docs` is a merge gate: a spec on
  `master` must read as decided. A worker branch that opens a real question
  would trip it, and the tempting fix — weakening or skipping that test — is how
  a spec silently stops being enforced. So open questions are numbered in one
  file at the repository root, linked from the doc that raises them, and
  asserted well-formed by `test_open_decisions_are_numbered_and_complete`.

### Known gaps

- Fifteen payload schemas still absent, for catalogued types no service publishes
  yet: identity's other eleven, `billing.subscription.past_due`,
  `billing.payment.refunded`, `billing.invoice.created`,
  `billing.usage.recorded`. `fleet.yml` marks each as `cataloguedOnly` so the
  difference between a promise and a fact is mechanical rather than a judgement.

## [0.2.0] — 2026-09-30

The event grammar, the payload-schema home, and the OpenAPI versioning rule are
all decided. One of them breaks an existing manifest, so this is a spec major.

### Breaking

- **Event types are `<service>.<entity>.<action>`. Three segments, always
  prefixed, no exceptions.** v0.1 accepted a two-segment `user.created` and only
  required the prefix for generic entities (`identity.api_key.created`); that
  exception is gone.

  | v0.1 | v0.2 |
  | --- | --- |
  | `user.created` | `identity.user.created` |
  | `subscription.started` | `billing.subscription.started` |
  | `identity.api_key.created` | unchanged — it was already the canonical form |

  The service segment is a service name, so it is kebab-case and may contain a
  dash (`email-sender.email.queued`); an underscore in the first segment is now a
  schema violation. The entity and action segments stay lowercase snake_case.

  **Downstream action.** Every published and consumed event type in every
  `cafaye.yml` must be renamed to its three-segment form, and every
  subscription, route, SDK constant and dashboard filter keyed on a two-segment
  type must follow it. This is a follow-up packet per service: core's own
  examples are updated here, the service repositories are not. Bump `core` to
  `^0.2.0` in the same commit as the rename — a service pinned to `^0.1.0`
  cannot resolve this release and will fail CI rather than silently accept the
  old format.
- **`subject` is required on the envelope.** It was already documented as
  required and was in fact optional in the schema. Entity-less events use the
  literal `platform`; there is no absent-`subject` case any more.

### Added

- **`schemas/events/<service>/<entity>/<action>.schema.json`** — per-event
  `data` payload schemas, in core. Two ship as the pattern:
  [`identity/user/created`](schemas/events/identity/user/created.schema.json)
  and
  [`billing/subscription/started`](schemas/events/billing/subscription/started.schema.json).
  A payload schema is a promise to other services, so it has one home with one
  release cadence rather than a copy in each publisher's repository. Core churns
  on every payload change; that is the cost, paid in review instead of in a
  consumer breaking on a Tuesday.
- **`docs/event-outbox.md`** — the transactional outbox convention: the
  `outbox_events` table, the insert in the same transaction as the domain write,
  the publisher loop (`for update skip locked`, ack before `published_at`,
  `attempts` with exponential backoff), at-least-once and therefore mandatory
  consumer idempotency, retention, and a sequence diagram. A convention only:
  each service implements it in its own language, and there is deliberately no
  shared outbox library.
- **`billing.plan.created`** to the billing catalog (11 events, up from 10).
- **Negative examples** for the tightened grammar (`event-envelope.untagged.invalid.json`),
  for the now-required `subject` (`event-envelope.subjectless.invalid.json`), and
  for both payload schemas. A negative example now needs a row in
  `examples/invalid/README.md` keyed by repo-relative path, and the suite fails on
  any negative file that is not documented.

### Changed

- **`docs/openapi-conventions.md`** — `/v1` path prefix **and** `info.version` are
  both required, with the sync rule (breaking change bumps both together, a
  non-breaking change bumps only `info.version`) and a note that a future
  `caf contract lint` will enforce it.
- **`docs/manifest-conventions.md`** — the semver mini-grammar stays. Full npm
  semver is out of scope: resolution belongs to a future `caf contract`, and
  `>=1.0.0` against a `0.x` service is a range that lies. Added a sixth
  cross-field rule: a consumed event type must exist in the core catalog.
- **`docs/event-naming.md`** — the grammar section, the catalog and the envelope
  table are rewritten around the three-segment rule, with the reasoning for
  making `subject` required. The new [Payload schemas](docs/event-naming.md#payload-schemas)
  section states the path convention and lists every payload schema in core.
- **`examples/valid/event-envelope.json`** — `data.user_id` was a 27-character id
  and did not match `subject`; the account id in the same payload was also 27
  characters. Both are 26-character ULIDs now, and the payload example is the one
  `schemas/events/identity/user/created.schema.json` validates.

### Open decisions

None. D1–D5 are decided:

| # | Decision |
| --- | --- |
| D1 | One canonical form: `<service>.<entity>.<action>`, always prefixed. |
| D2 | `subject` stays required; `platform` is the escape hatch for entity-less events. |
| D3 | Payload schemas live in core, one per event type, at a path derived from the type. |
| D4 | Both `/v1` and `info.version` are required, with the sync rule documented. |
| D5 | The semver mini-grammar is kept; `caf contract` resolves it. |

### Known gaps

- The reserved service-name list (`cafaye`, `caf`, `kit`, `core`, `docs`,
  `pantry`) is a review rule, not a schema constraint — core's own manifest is
  `name: core`, so encoding the list would make core fail its own schema.
- Only 2 of the 28 catalogued events have a payload schema. Each lands with the
  packet that first needs one; the suite fails on a payload schema that is not
  listed, or a listed path that does not exist.
- No OpenAPI document is shipped. `core` supplies the conventions a service's
  own `openapi/openapi.yaml` must agree with, not the documents themselves, and
  `caf contract lint` does not exist yet.
- The outbox convention is a document, not a schema: the column list is asserted
  out of the SQL block in `docs/event-outbox.md`, and nothing here checks a
  service's actual migration.

## [0.1.0] — 2026-09-30

> Superseded by [0.2.0](#020--2026-09-30), which changed the event type format.
> This section is the record of what 0.1.0 said, including the decisions that
> were still open when it shipped; all five were decided in 0.2.0.

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
  [`examples/invalid/README.md`](examples/invalid/README.md).
- **`tests/`** — the contract suite: every valid example validates, every
  invalid example is rejected for its documented reasons, and the docs are
  checked against the schemas. `bin/prime` runs it; `tests/setup.sh` builds the
  venv. The catalog and the example manifests are asserted to agree in both
  directions, so an event cannot be published without being documented or
  documented without being published.
- **`cafaye.yml`** — core's own manifest, `language: spec`, validated against
  core's own schema on every test run.
- **`README.md`**, **`AGENTS.md`**, **`mise.toml`**, **`.gitignore`**.

### Open decisions

Numbered as in the docs. Each was drafted with a default so nothing was blocked.
**All five were decided in [0.2.0](#020--2026-09-30)**; the outcomes are in that
release's "Open decisions" table, and the drafted defaults below are the record
of what shipped in 0.1.0, not a statement of the spec today.

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
[0.2.0]: https://cafaye.com/changelog/core/v0.2.0
[0.1.0]: https://cafaye.com/changelog/core/v0.1.0
