#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export PYTHONPATH="$ROOT/wrapper"
export PATH="$ROOT/scripts:$ROOT/build:$PATH"
python3 "$ROOT/tests/create_tiny_gtfs.py" >/dev/null
rm -f "$ROOT/tests/tiny-gtfs.svg"
loom-map "$ROOT/tests/tiny-gtfs.zip" --layout geographic --output "$ROOT/tests/tiny-gtfs.svg" --verbose
[ -s "$ROOT/tests/tiny-gtfs.svg" ]
python3 - <<'PY'
from pathlib import Path
p = Path('tests/tiny-gtfs.svg')
assert b'<svg' in p.read_bytes()[:4096].lower()
PY
