[![2015 Stuttgart light rail network maps generated from GTFS data, with optimal line orderings, geographically correct (left), octilinear (middle), and orthoradial (right).](examples/render/stuttgart-example-small.png?raw=true)](examples/render/stuttgart-example.png?raw=true)
*2015 Stuttgart light rail network maps generated from GTFS data, with optimal line orderings, geographically correct (left), octilinear (middle), and orthoradial (right).*

[![Build](https://github.com/ad-freiburg/loom/actions/workflows/build.yml/badge.svg)](https://github.com/ad-freiburg/loom/actions/workflows/build.yml)

LOOM Map Wrapper
================

This fork adds `loom-map`, a small Python 3 convenience wrapper around the existing LOOM command-line tools. It lets a user turn a GTFS ZIP feed into an SVG transit diagram with one command:

```sh
loom-map network.zip
```

By default this creates:

```text
network.svg
```

`loom-map` is an orchestration and usability layer. It does **not** replace or rewrite LOOM's graph extraction, topology, line-ordering, schematic layout, or rendering algorithms.

Quick start
-----------

Build LOOM and put both the wrapper script and LOOM binaries on `PATH`:

```sh
git submodule update --init --recursive
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build --parallel
export PYTHONPATH="$PWD/wrapper"
export PATH="$PWD/scripts:$PWD/build:$PATH"
loom-map network.zip
```

Use explicit options:

```sh
loom-map network.zip \
  --mode rail \
  --layout octilinear \
  --labels \
  --output network.svg
```

Save debuggable intermediate files:

```sh
loom-map network.zip \
  --save-intermediates \
  --work-dir ./loom-debug
```

The preserved stage outputs are named clearly, for example `01-gtfs-graph.geojson`, `02-topology.geojson`, `03-line-ordering.geojson`, `04-schematic.geojson`, and `05-map.svg`. The schematic stage is only present for schematic layouts. When `--layout all` is used, stages 4 and 5 are suffixed per layout (`04-schematic-octilinear.geojson`, `05-map-octilinear.svg`, and so on).

Generate all three layouts at once:

```sh
loom-map network.zip --layout all --output network.svg
```

This runs the shared, expensive stages (`gtfs2graph`, `topo`, `loom`) once and only re-runs the cheap final stage(s) per layout, writing `network-geographic.svg`, `network-octilinear.svg`, and `network-orthoradial.svg`.

`graph` and `render` subcommands
---------------------------------

The full pipeline can be split into two independently useful pieces:

```sh
# GTFS -> GeoJSON line graph only (the gtfs2graph stage)
loom-map graph network.zip -o network-graph.json --mode rail

# GeoJSON line graph -> SVG map only (topo -> loom -> [octi] -> transitmap)
loom-map render network-graph.json -o network.svg --layout octilinear --labels
```

`loom-map network.zip` is equivalent to running `graph` followed by `render`.
Splitting them lets you cache or inspect the graph extraction step separately
from rendering, or render several layouts from one extracted graph without
re-parsing the GTFS feed. `render` also accepts `--layout all`.

Route aggregation and filtering
--------------------------------

`gtfs2graph` groups trips into a "line" by GTFS `route_id` identity, not by
`route_short_name`. Most feeds mint one `route_id` per public route, but some
(Translink among them) mint a fresh `route_id` per shape, pattern, or
timetable variant under the same public route number — which can turn a
handful of real routes into hundreds of apparent "lines", both misleading a
reader and blowing up the line-ordering optimizer's runtime (its complexity
scales with how many distinct lines converge at a station).

`loom-map` and `loom-map graph` can rewrite the GTFS feed before extraction:

```sh
# Merge route_id variants that share a public route number
loom-map network.zip --aggregate-by route_short_name

# Restrict the feed to specific public route numbers
loom-map network.zip --routes 66,130,P1

# Both together
loom-map network.zip --aggregate-by route_short_name --routes 66,130,P1
```

`--aggregate-by` defaults to `route_id` (today's behavior, unchanged) and
accepts `route_short_name` to merge `route_id`s sharing a short name onto one
canonical `route_id` before extraction. `--routes` takes a comma-separated
list matched against `route_short_name` and drops every other route (and its
trips and stop times) before extraction. Both apply only to the `graph`
stage; `render` operates on an already-extracted graph.

Docker
------

Build the checked-out source tree:

```sh
docker build -t loom-map .
```

Generate an SVG on the host:

```sh
docker run --rm \
  -v "$PWD:/data" \
  loom-map \
  /data/network.zip \
  --output /data/network.svg
```

The container entrypoint is `loom-map`. The original low-level LOOM tools remain available by naming one as the first argument, and so are the `graph`/`render` subcommands:

```sh
docker run --rm loom-map loom --help
docker run --rm -i loom-map octi < examples/stuttgart.json > stuttgart-octi.json
docker run --rm -v "$PWD:/data" loom-map graph /data/network.zip -o /data/network-graph.json
```

The default Docker build uses open-source solvers (`coinor-cbc` and GLPK packages) and does not require Gurobi.

A prebuilt image is published to GHCR on every push to `main` (see below), so
you don't need to build locally unless you've changed the source:

```sh
docker pull ghcr.io/<owner>/loom-map:latest
```

GitHub Actions
---------------

Two workflows cover building and using the Docker image:

**`.github/workflows/build-image.yml`** builds and publishes the image to
`ghcr.io/<owner>/loom-map` (tagged `latest` and `sha-<commit>`) on every push
to `main`, or on demand via `workflow_dispatch`. The image is built once here,
not on every diagram generation run.

**`.github/workflows/generate-map.yml`** (manual, "Generate Transit Diagram")
turns a GTFS feed into one or more SVGs. It pulls the published image instead
of rebuilding (falling back to a one-off local build+push if no published
image exists yet, e.g. on a fork before its first `build-image.yml` run), and
runs the pipeline as a chain of separate jobs — `prepare` -> `graph` ->
`topology` -> `line-ordering` -> `render` (matrix, one leg per layout) ->
`summary` — instead of one long `docker run`. Each stage gets its own log,
duration, and timeout in the Actions UI (`line-ordering`, the optimizer stage,
is capped at 90 minutes so a runaway feed fails loudly with its intermediate
artifact preserved, instead of hanging silently for hours), and intermediate
GeoJSON is passed between jobs as artifacts so a `--layout all` run only pays
for graph extraction and line ordering once.

To run it:

1. Open the repository's **Actions** tab.
2. Select **Generate Transit Diagram**.
3. Click **Run workflow**.
4. Paste a public `http://` or `https://` GTFS ZIP URL.
5. Choose the mode, layout (including `all`), labels, aggregation field,
   an optional route filter, and whether to upload intermediates.
6. Run the workflow.
7. Download the generated SVG artifact(s), named `loom-map-svg-<layout>`.

If a stage fails, its job uploads a `loom-map-diagnostics-<stage>` artifact
with the input it was given, so you can reproduce the failure locally with
the same LOOM tool.

Wrapper CLI
-----------

```text
Usage: loom-map INPUT [options]

Generate a geographic or schematic transit diagram from a GTFS feed.

Arguments:
  INPUT                   Path to a GTFS ZIP file

Options:
  -o, --output PATH       Output SVG path (base name when --layout all)
  --mode MODE             Transit mode
  --layout LAYOUT         geographic, octilinear, orthoradial, or all
  --aggregate-by FIELD    route_id (default) or route_short_name
  --routes ROUTES         Comma-separated route_short_names to keep
  --labels                Render stop/station labels
  --no-labels             Do not render stop/station labels
  --save-intermediates    Preserve GeoJSON output from each pipeline stage
  --work-dir PATH         Working directory for intermediate files
  --verbose               Show detailed pipeline information
  -h, --help              Show help
  --version               Show wrapper and source version

Subcommands:
  loom-map graph INPUT.zip -o graph.json      GTFS -> GeoJSON graph only
  loom-map render graph.json -o network.svg   GeoJSON graph -> SVG only
```

Supported modes
---------------

The checked-in `gtfs2graph` source documents `-m/--mots` as accepting comma-separated mode names or GTFS mode codes. `loom-map` exposes friendly names and aliases, then passes the corresponding value to `gtfs2graph -m`.

Canonical wrapper modes:

- `all`
- `tram`
- `subway`
- `rail`
- `bus`
- `ferry`
- `cablecar`
- `gondola`
- `funicular`
- `coach`
- `monorail`
- `trolley`

Useful aliases include:

- `streetcar` and `light-rail` -> `tram`
- `metro` -> `subway`
- `train`, `heavy-rail`, `commuter-rail`, and `suburban-rail` -> `rail`
- `boat` and `ship` -> `ferry`
- `mono-rail` -> `monorail`
- `trolleybus` and `trolley-bus` -> `trolley`

LOOM does not separately distinguish heavy rail, commuter rail, and suburban rail in this wrapper; all map to the `rail` mode that `gtfs2graph` supports.

Supported layouts
-----------------

- `geographic`: `gtfs2graph -> topo -> loom -> transitmap`
- `octilinear`: `gtfs2graph -> topo -> loom -> octi -> transitmap`
- `orthoradial`: `gtfs2graph -> topo -> loom -> octi -b orthoradial -> transitmap`
- `all`: generates all three above, writing `<output>-geographic.svg`, `<output>-octilinear.svg`, and `<output>-orthoradial.svg`. The shared `gtfs2graph -> topo -> loom` stages run once; only the cheap final stage(s) are repeated per layout.

The underlying `octi` tool supports additional base graphs, but the wrapper intentionally exposes only these three user-facing layouts (plus `all`) for the first MVP.

Labels
------

Labels are disabled by default to match the existing simple LOOM examples. Use `--labels` to pass `--labels` to `transitmap`; use `--no-labels` to be explicit.

Validation and error handling
-----------------------------

Before running LOOM, `loom-map` checks that the input exists, is a readable ZIP file, and contains the core GTFS files required for this pipeline: `agency.txt`, `stops.txt`, `routes.txt`, `trips.txt`, and `stop_times.txt`. It does not attempt full semantic GTFS validation.

Each LOOM stage is run separately with safe argument arrays, not by concatenating shell commands. If a stage fails, the wrapper reports the failed stage, the command, and LOOM stderr. Final SVG writes are atomic so a failed run does not leave a misleading final output file.

Troubleshooting
---------------

- `Required LOOM executable not found`: build LOOM and ensure `build/` is on `PATH`.
- `missing stops.txt` or similar: the input ZIP does not contain the required core GTFS files.
- Schematic layout fails in `octi`: try `--layout geographic` to confirm extraction/topology/rendering first, then rerun with `--save-intermediates --work-dir ./loom-debug`.
- Some GTFS feeds contain many routes. Start with a specific `--mode` such as `rail`, `subway`, or `tram` before trying `all`.
- Line ordering (stage 3, `loom`) hanging or taking a very long time on a feed that shouldn't be that complex: this is usually a route-explosion problem, not a scale problem. If the agency mints a fresh `route_id` per shape/pattern/timetable variant under one public route number, `loom` sees far more "distinct lines" converging at busy stations than actually exist. Try `--aggregate-by route_short_name` first; narrowing with `--routes` also helps while iterating.

Solver choice
-------------

LOOM's ILP-capable tools support `glpk`, `cbc`, and `gurobi` where available. The upstream help text defaults to Gurobi and falls back if unavailable. This wrapper and Docker image prefer `cbc` for schematic layout because it is open-source, requires no licence, and is generally a practical MILP default. Gurobi remains usable outside the wrapper by invoking LOOM tools directly if you build LOOM with Gurobi support and provide a licence.

Original LOOM tools
===================

Software suite for the automated generation of geographically correct or schematic transit maps.

Based on the work in the following papers:
[Bast H., Brosi P., Storandt S., Efficient Generation of Geographically Accurate Transit Maps, SIGSPATIAL 2018](http://ad-publications.informatik.uni-freiburg.de/SIGSPATIAL_transitmaps_2018.pdf)
[Bast H., Brosi P., Storandt S., Efficient Generation of Geographically Accurate Transit Maps (extended version), ACM TSAS, Vol. 5, No. 4, Article 25, 2019](http://ad-publications.informatik.uni-freiburg.de/ACM_efficient%20Generation%20of%20%20Geographically%20Accurate%20Transit%20Maps_extended%20version.pdf)
[Bast H., Brosi P., Storandt S., Metro Maps on Octilinear Grid Graphs, EuroVis 2020](http://ad-publications.informatik.uni-freiburg.de/EuroVis%20octi-maps.pdf)
[Bast H., Brosi P., Storandt S., Metro Maps on Flexible Base Grids, SSTD 2021](http://ad-publications.informatik.uni-freiburg.de/SSTD_Metro%20Maps%20on%20Flexible%20Base%20Grids.pdf).
A pipeline for generating geographically accurate transit maps which appears to be similar was described by Anton Dubrau in a [blog post](https://blog.transitapp.com/how-we-built-the-worlds-prettiest-auto-generated-transit-maps-12d0c6fa502f).

Also see the web demos [here](https://loom.cs.uni-freiburg.de/), [here](https://loom.cs.uni-freiburg.de/global), and [here](https://octi.cs.uni-freiburg.de).

[Transport for Cairo](https://transportforcairo.com) has created a cross-platform [QGIS plugin](https://github.com/transportforcairo/loom_qgis) for LOOM.

Requirements
------------

Build-time requirements:

- `cmake`
- `gcc >= 5.1` or `clang >= 3.9`
- `make`
- submodules: `src/util` and `src/cppgtfs`
- `libprotobuf-dev` and `protobuf-compiler`
- optional solver development packages: `coinor-libcbc-dev`, `libglpk-dev`, or Gurobi
- optional `libzip-dev` for ZIP GTFS input support

Runtime requirements for the wrapper and default Docker image:

- Python 3 standard library
- LOOM executables: `gtfs2graph`, `topo`, `loom`, `octi`, `transitmap`
- runtime libraries for the selected LOOM build, including solver and ZIP libraries when linked

Building and Installation
-------------------------

Fetch this repository and init submodules:

```sh
git clone --recurse-submodules https://github.com/ad-freiburg/loom.git
```

Build:

```sh
cd loom
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build --parallel
```

Optionally install the C++ tools:

```sh
cmake --install build
```

You can also use the binaries in `./build` directly.

Low-level usage
===============

This suite consists of several tools:

- `gtfs2graph`, create a GeoJSON line graph from GTFS data
- `topo`, create an overlapping-free line graph from an arbitrary line graph
- `loom`, find optimal line orderings on a line graph
- `octi`, create a schematic version of a line graph
- `transitmap`, render a line graph into an SVG map (`--render-engine=svg`) or into vector tiles (`--render-engine=mvt`)

All tools output a graph, in the GeoJSON format, to `stdout`, and expect a GeoJSON graph at `stdin`. Exceptions are `gtfs2graph`, where the input is a GTFS feed, and `transitmap`, which writes SVG to `stdout` or MVT vector tiles to a specified folder. Running a tool with `-h` shows a help message with allowed options.

To render the geographically correct Stuttgart map from above:

```sh
cat examples/stuttgart.json | loom | transitmap > stuttgart.svg
```

To also render labels:

```sh
cat examples/stuttgart.json | loom | transitmap -l > stuttgart-label.svg
```

To render an octilinear map:

```sh
cat examples/stuttgart.json | loom | octi | transitmap -l > stuttgart-octilin.svg
```

To render an orthoradial map:

```sh
cat examples/stuttgart.json | loom | octi -b orthoradial | transitmap -l > stuttgart-orthorad.svg
```

Line graph extraction from GTFS:

```sh
gtfs2graph -m tram freiburg.zip | topo | loom | octi | transitmap > freiburg-tram.svg
```

License and attribution
=======================

LOOM is GPL-3.0 licensed. This wrapper is a convenience addition around LOOM and does not imply official University of Freiburg endorsement. Preserve the academic attribution above when reusing or redistributing this software.
