#!/usr/bin/env bash
# tests/validate.sh — the name kit's reusable workflow looks for.
#
# kit's `language: none` job runs exactly this path, and fails the build if it is
# absent: a caller who asks for the configuration gate and ships no gate has asked
# for a green checkmark on nothing, which is the same defect as a coverage
# threshold left at 0.
#
# It contains no logic. `bin/prime` is the gate — it is what AGENTS.md, README.md
# and `mise run test` all name, and it is what CI's `gate` job runs. This file is
# the same command under the filename kit's contract requires, so that adopting
# kit does not require inventing a second entry point or, worse, a second gate
# that can disagree with the first.
#
# If you are here trying to add a check: add it to `tests/test_specs.py` and run
# `bin/prime`. This file should never need to change again.
#
# Arguments are forwarded, so `bash tests/validate.sh --pytest` is
# `bin/prime --pytest` and CI can reach both entry points through one name.
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "$here/../bin/prime" "$@"