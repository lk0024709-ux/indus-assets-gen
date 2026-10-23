#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
if ! command -v blender >/dev/null 2>&1 && [ -z "${BLENDER_BIN:-}" ]; then
  echo "Blender 4.x was not found. Install Blender and add it to PATH, or set BLENDER_BIN." >&2
  exit 1
fi
PYTHON_BIN="${PYTHON_BIN:-python3}"
"$PYTHON_BIN" -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r backend/requirements.txt
export PYTHONPATH="$PWD/backend"
exec uvicorn main:app --app-dir backend --host 0.0.0.0 --port "${PORT:-8000}"
