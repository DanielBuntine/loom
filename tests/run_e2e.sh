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

echo "--- loom-map graph / render subcommands ---"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
loom-map graph "$ROOT/tests/tiny-gtfs.zip" -o "$WORK/graph.json" --mode rail --verbose
[ -s "$WORK/graph.json" ]
loom-map render "$WORK/graph.json" -o "$WORK/rendered.svg" --layout geographic --verbose
[ -s "$WORK/rendered.svg" ]
python3 - "$WORK/rendered.svg" "$ROOT/tests/tiny-gtfs.svg" <<'PY'
import sys
from pathlib import Path
rendered, full_pipeline = (Path(p).read_bytes() for p in sys.argv[1:3])
assert b'<svg' in rendered[:4096].lower()
assert rendered == full_pipeline, "'graph' + 'render' should match the equivalent single loom-map run"
PY

echo "--- --layout all ---"
loom-map render "$WORK/graph.json" -o "$WORK/multi.svg" --layout all
python3 - "$WORK" <<'PY'
import sys
from pathlib import Path
work = Path(sys.argv[1])
svgs = {}
for layout in ("geographic", "octilinear", "orthoradial"):
    p = work / f"multi-{layout}.svg"
    assert p.stat().st_size > 0, f"missing/empty output for layout {layout}"
    svgs[layout] = p.read_bytes()
assert len(set(svgs.values())) == 3, "the three layouts should not render byte-identical output"
PY

echo "--- --aggregate-by / --routes ---"
python3 "$ROOT/tests/create_dup_route_gtfs.py" >/dev/null
loom-map graph "$ROOT/tests/dup-route-gtfs.zip" -o "$WORK/dup-default.json" --mode rail
loom-map graph "$ROOT/tests/dup-route-gtfs.zip" -o "$WORK/dup-agg.json" --mode rail --aggregate-by route_short_name
loom-map graph "$ROOT/tests/dup-route-gtfs.zip" -o "$WORK/dup-filtered.json" --mode rail --routes T2
python3 - "$WORK" <<'PY'
import json
import sys
from pathlib import Path

work = Path(sys.argv[1])


def line_ids(name):
    data = json.loads((work / name).read_text())
    ids = set()
    for feature in data["features"]:
        for line in feature.get("properties", {}).get("lines", []):
            ids.add(line["id"])
    return ids


def line_labels(name):
    data = json.loads((work / name).read_text())
    labels = set()
    for feature in data["features"]:
        for line in feature.get("properties", {}).get("lines", []):
            labels.add(line["label"])
    return labels


assert len(line_ids("dup-default.json")) == 3, "R1/R2/R3 should be distinct lines without aggregation"
assert len(line_ids("dup-agg.json")) == 2, "R1+R2 (both short name T1) should collapse under --aggregate-by route_short_name"
assert line_labels("dup-filtered.json") == {"T2"}, "--routes T2 should keep only the T2 line"
PY
