"""LOOM pipeline orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os
import shutil
import subprocess
import sys
import tempfile
from typing import Dict, List, Optional, Sequence

from .config import ALL_LAYOUTS, DEFAULT_AGGREGATE_BY, DEFAULT_ILP_SOLVER
from .gtfs_transform import preprocess_gtfs


class PipelineError(RuntimeError):
    """Raised when a LOOM pipeline stage fails."""

    def __init__(self, stage_number: int, stage_name: str, command: List[str], stderr: str, debug_dir: Path):
        self.stage_number = stage_number
        self.stage_name = stage_name
        self.command = command
        self.stderr = stderr
        self.debug_dir = debug_dir
        super().__init__(self._format())

    def _format(self) -> str:
        command = " ".join(self.command)
        output = self.stderr.strip() or "<no stderr>"
        return (
            f"LOOM pipeline failed during stage {self.stage_number}: {self.stage_name}\n\n"
            f"Command:\n  {command}\n\nLOOM output:\n{output}\n\n"
            f"Intermediate files preserved at:\n  {self.debug_dir}"
        )


@dataclass(frozen=True)
class Stage:
    name: str
    executable: str
    args: tuple[str, ...]
    output_name: str
    description: str

    def command(self, executable_path: str) -> List[str]:
        return [executable_path, *self.args]


@dataclass(frozen=True)
class PipelineOptions:
    gtfs_path: Path
    output_path: Path
    mode: str
    layout: str
    labels: bool
    save_intermediates: bool
    work_dir: Optional[Path]
    verbose: bool
    ilp_solver: str = DEFAULT_ILP_SOLVER
    aggregate_by: str = DEFAULT_AGGREGATE_BY
    routes: Optional[List[str]] = None


def find_executable(name: str) -> str:
    candidate = shutil.which(name)
    if candidate:
        return candidate
    repo_build = Path(__file__).resolve().parents[2] / "build" / name
    if repo_build.exists() and os.access(repo_build, os.X_OK):
        return str(repo_build)
    raise FileNotFoundError(
        f"Required LOOM executable not found: {name}\n"
        "Build LOOM first and ensure its build directory is on PATH."
    )


def resolve_layouts(layout: str) -> tuple[str, ...]:
    return ALL_LAYOUTS if layout == "all" else (layout,)


def find_required_executables(
    layouts: Sequence[str] = (),
    include_gtfs2graph: bool = False,
    include_render: bool = False,
) -> Dict[str, str]:
    required: set[str] = set()
    if include_gtfs2graph:
        required.add("gtfs2graph")
    if include_render:
        required.update({"topo", "loom", "transitmap"})
        if any(l in ("octilinear", "orthoradial") for l in layouts):
            required.add("octi")
    return {name: find_executable(name) for name in sorted(required)}


def _total_stage_count(layouts: Sequence[str], include_gtfs2graph: bool = True) -> int:
    total = (1 if include_gtfs2graph else 0) + 2  # gtfs2graph (optional), topo, loom
    for layout in layouts:
        total += 2 if layout in ("octilinear", "orthoradial") else 1
    return total


def _ensure_nonempty(path: Path, stage: Stage, stage_number: int, cmd: List[str], stderr: str, debug_dir: Path) -> None:
    if not path.exists() or path.stat().st_size == 0:
        raise PipelineError(stage_number, stage.name, cmd, stderr or f"Expected non-empty output file was not created: {path}", debug_dir)


def _run_stage(stage: Stage, stage_number: int, total: int, executable: str, input_path: Optional[Path], output_path: Path, debug_dir: Path, verbose: bool) -> None:
    cmd = stage.command(executable)
    print(f"[{stage_number}/{total}] {stage.description}...", flush=True)
    if verbose:
        print(f"  Command: {' '.join(cmd)}", file=sys.stderr)
        print(f"  Output:  {output_path}", file=sys.stderr)
    stdin = None
    try:
        if input_path is not None:
            stdin = input_path.open("rb")
        with output_path.open("wb") as stdout:
            result = subprocess.run(cmd, stdin=stdin, stdout=stdout, stderr=subprocess.PIPE, text=False, shell=False)
    finally:
        if stdin is not None:
            stdin.close()
    stderr = result.stderr.decode("utf-8", errors="replace") if result.stderr else ""
    if result.returncode != 0:
        raise PipelineError(stage_number, stage.name, cmd, stderr, debug_dir)
    _ensure_nonempty(output_path, stage, stage_number, cmd, stderr, debug_dir)


def _looks_like_svg(path: Path) -> bool:
    try:
        with path.open("rb") as handle:
            head = handle.read(4096).lower()
    except OSError:
        return False
    return b"<svg" in head


def _prepare_work_dir(work_dir: Optional[Path], save_intermediates: bool) -> tuple[Path, bool]:
    if save_intermediates:
        resolved = work_dir or Path.cwd() / "loom-debug"
        resolved.mkdir(parents=True, exist_ok=True)
        return resolved, False
    if work_dir:
        work_dir.mkdir(parents=True, exist_ok=True)
    resolved = Path(tempfile.mkdtemp(prefix="loom-map-", dir=str(work_dir) if work_dir else None))
    return resolved, True


def _atomic_write(src: Path, dest: Path) -> None:
    dest_parent = dest.parent if dest.parent != Path("") else Path(".")
    dest_parent.mkdir(parents=True, exist_ok=True)
    if dest_parent.exists() and not os.access(dest_parent, os.W_OK):
        raise PermissionError(f"Output directory is not writable: {dest_parent}")
    tmp_out = dest_parent / f".{dest.name}.tmp"
    shutil.copyfile(src, tmp_out)
    os.replace(tmp_out, dest)


def layout_output_path(base_output: Path, layout: str, multi: bool) -> Path:
    if not multi:
        return base_output
    return base_output.with_name(f"{base_output.stem}-{layout}{base_output.suffix or '.svg'}")


def run_graph_only(
    gtfs_path: Path,
    output_path: Path,
    mode: str,
    aggregate_by: str = DEFAULT_AGGREGATE_BY,
    routes: Optional[List[str]] = None,
    verbose: bool = False,
) -> Path:
    """Run GTFS preprocessing + gtfs2graph, writing the GeoJSON graph to output_path."""
    executables = find_required_executables(include_gtfs2graph=True)
    work_dir, cleanup = _prepare_work_dir(None, save_intermediates=False)
    try:
        preprocessed = preprocess_gtfs(gtfs_path, work_dir, aggregate_by, routes)
        stage = Stage(
            "GTFS graph extraction", "gtfs2graph", ("-m", mode, str(preprocessed)),
            "01-gtfs-graph.geojson", "Extracting GTFS line graph",
        )
        out = work_dir / stage.output_name
        _run_stage(stage, 1, 1, executables["gtfs2graph"], None, out, work_dir, verbose)
        _atomic_write(out, output_path)
        return output_path
    finally:
        if cleanup:
            shutil.rmtree(work_dir, ignore_errors=True)


def run_render_only(
    graph_path: Path,
    output_path: Path,
    layout: str,
    labels: bool = False,
    ilp_solver: str = DEFAULT_ILP_SOLVER,
    verbose: bool = False,
    save_intermediates: bool = False,
    work_dir: Optional[Path] = None,
    _start_stage_number: int = 0,
    _total_override: Optional[int] = None,
) -> List[Path]:
    """Run topo -> loom -> [octi] -> transitmap starting from an existing GeoJSON graph.

    When layout == "all", shares the topo/loom output across all three
    layouts and only re-runs the cheap final stage(s) per layout.

    `_start_stage_number`/`_total_override` let `run_pipeline` continue the
    same [n/total] progress counter across the gtfs2graph stage it already ran;
    standalone callers (the `render` subcommand) can ignore them.
    """
    layouts = resolve_layouts(layout)
    executables = find_required_executables(layouts, include_render=True)
    resolved_work_dir, cleanup = _prepare_work_dir(work_dir, save_intermediates)
    total = _total_override if _total_override is not None else _total_stage_count(layouts, include_gtfs2graph=False)
    stage_number = _start_stage_number
    try:
        topo_stage = Stage("topology resolution", "topo", tuple(), "02-topology.geojson", "Resolving topology")
        stage_number += 1
        topo_out = resolved_work_dir / topo_stage.output_name
        _run_stage(topo_stage, stage_number, total, executables["topo"], graph_path, topo_out, resolved_work_dir, verbose)

        loom_stage = Stage("line ordering", "loom", tuple(), "03-line-ordering.geojson", "Optimising line ordering")
        stage_number += 1
        loom_out = resolved_work_dir / loom_stage.output_name
        _run_stage(loom_stage, stage_number, total, executables["loom"], topo_out, loom_out, resolved_work_dir, verbose)

        multi = len(layouts) > 1
        written: List[Path] = []
        for this_layout in layouts:
            suffix = f"-{this_layout}" if multi else ""
            stages: List[Stage] = []
            if this_layout == "octilinear":
                stages.append(Stage("octilinear layout", "octi", ("--ilp-solver", ilp_solver), f"04-schematic{suffix}.geojson", "Creating octilinear layout"))
            elif this_layout == "orthoradial":
                stages.append(Stage("orthoradial layout", "octi", ("-b", "orthoradial", "--ilp-solver", ilp_solver), f"04-schematic{suffix}.geojson", "Creating orthoradial layout"))
            render_args = ["--render-engine", "svg"]
            if labels:
                render_args.append("--labels")
            stages.append(Stage("SVG rendering", "transitmap", tuple(render_args), f"05-map{suffix}.svg", "Rendering SVG"))

            previous = loom_out
            for stage in stages:
                stage_number += 1
                out = resolved_work_dir / stage.output_name
                _run_stage(stage, stage_number, total, executables[stage.executable], previous, out, resolved_work_dir, verbose)
                previous = out

            if not _looks_like_svg(previous):
                raise PipelineError(stage_number, "SVG rendering", [executables["transitmap"]], "Final output does not appear to contain SVG content.", resolved_work_dir)

            dest = layout_output_path(output_path, this_layout, multi)
            _atomic_write(previous, dest)
            written.append(dest)

        return written
    except Exception:
        if not save_intermediates:
            print(f"Intermediate files preserved at: {resolved_work_dir}", file=sys.stderr)
            cleanup = False
        raise
    finally:
        if cleanup:
            shutil.rmtree(resolved_work_dir, ignore_errors=True)


def run_pipeline(options: PipelineOptions) -> List[Path]:
    """Run the full GTFS -> SVG pipeline. Returns the list of SVG paths written."""
    layouts = resolve_layouts(options.layout)
    executables = find_required_executables(layouts, include_gtfs2graph=True, include_render=True)
    work_dir, cleanup = _prepare_work_dir(options.work_dir, options.save_intermediates)

    print("LOOM Map Generator\n")
    print(f"Input:   {options.gtfs_path}")
    print(f"Mode:    {options.mode}")
    print(f"Layout:  {options.layout}")
    print(f"Labels:  {'yes' if options.labels else 'no'}")
    print(f"Output:  {options.output_path}\n")

    try:
        preprocessed = preprocess_gtfs(options.gtfs_path, work_dir, options.aggregate_by, options.routes)
        total = _total_stage_count(layouts, include_gtfs2graph=True)
        graph_stage = Stage(
            "GTFS graph extraction", "gtfs2graph", ("-m", options.mode, str(preprocessed)),
            "01-gtfs-graph.geojson", "Extracting GTFS line graph",
        )
        graph_out = work_dir / graph_stage.output_name
        _run_stage(graph_stage, 1, total, executables["gtfs2graph"], None, graph_out, work_dir, options.verbose)

        written = run_render_only(
            graph_out,
            options.output_path,
            options.layout,
            labels=options.labels,
            ilp_solver=options.ilp_solver,
            verbose=options.verbose,
            save_intermediates=True,  # reuse this work_dir; we manage cleanup ourselves below
            work_dir=work_dir,
            _start_stage_number=1,
            _total_override=total,
        )
        for path in written:
            print(f"\nDone: {path}")
        return written
    except Exception:
        if not options.save_intermediates:
            print(f"Intermediate files preserved at: {work_dir}", file=sys.stderr)
            cleanup = False
        raise
    finally:
        if cleanup:
            shutil.rmtree(work_dir, ignore_errors=True)
