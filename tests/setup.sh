#!/usr/bin/env bash
# Creates tests/.venv and installs the validator dependencies.
# Idempotent: re-running is a no-op once the venv satisfies requirements.txt.
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
venv="$here/.venv"
python="${PYTHON:-python3}"

if [ ! -x "$venv/bin/python" ]; then
  "$python" -m venv "$venv"
fi

"$venv/bin/python" -m pip install --quiet --disable-pip-version-check --upgrade pip
"$venv/bin/python" -m pip install --quiet --disable-pip-version-check -r "$here/requirements.txt"

"$venv/bin/python" - <<'PY'
import importlib.metadata as md

for pkg in ("jsonschema", "PyYAML", "pytest"):
    print(f"{pkg}=={md.version(pkg)}")
PY
