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

The preserved stage outputs are named clearly, for example `01-gtfs-graph.geojson`, `02-topology.geojson`, `03-line-ordering.geojson`, `04-schematic.geojson`, and `05-map.svg`. The schematic stage is only present for schematic layouts.

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

The container entrypoint is `loom-map`. The original low-level LOOM tools remain available by naming one as the first argument:

```sh
docker run --rm loom-map loom --help
docker run --rm -i loom-map octi < examples/stuttgart.json > stuttgart-octi.json
```

The default Docker build uses open-source solvers (`coinor-cbc` and GLPK packages) and does not require Gurobi.

GitHub Actions: Generate Transit Diagram
----------------------------------------

A manual workflow is provided at `.github/workflows/generate-map.yml`.

1. Open the repository's **Actions** tab.
2. Select **Generate Transit Diagram**.
3. Click **Run workflow**.
4. Paste a public `http://` or `https://` GTFS ZIP URL.
5. Choose the mode, layout, labels, and whether to upload intermediates.
6. Run the workflow.
7. Download the generated SVG artifact named `loom-map-svg`.

The workflow downloads the feed with `curl --fail --location`, builds the Docker image from this repository, runs `loom-map`, uploads the SVG, optionally uploads intermediates, and uploads diagnostics if generation fails.

Wrapper CLI
-----------

```text
Usage: loom-map INPUT [options]

Generate a geographic or schematic transit diagram from a GTFS feed.

Arguments:
  INPUT                 Path to a GTFS ZIP file

Options:
  -o, --output PATH     Output SVG path
  --mode MODE           Transit mode
  --layout LAYOUT       geographic, octilinear, or orthoradial
  --labels              Render stop/station labels
  --no-labels           Do not render stop/station labels
  --save-intermediates  Preserve GeoJSON output from each pipeline stage
  --work-dir PATH       Working directory for intermediate files
  --verbose             Show detailed pipeline information
  -h, --help            Show help
  --version             Show wrapper and source version
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

The underlying `octi` tool supports additional base graphs, but the wrapper intentionally exposes only these three user-facing layouts for the first MVP.

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
