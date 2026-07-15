"""LOOM pipeline orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os
import shutil
import subprocess
import sys
import tempfile
from typing import List, Optional

from .config import DEFAULT_ILP_SOLVER


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
    input_path: Optional[Path] = None

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


def build_stages(options: PipelineOptions, final_temp: Path) -> List[Stage]:
    stages: List[Stage] = [
        Stage("GTFS graph extraction", "gtfs2graph", ("-m", options.mode, str(options.gtfs_path)), "01-gtfs-graph.geojson", "Extracting GTFS line graph"),
        Stage("topology resolution", "topo", tuple(), "02-topology.geojson", "Resolving topology"),
        Stage("line ordering", "loom", tuple(), "03-line-ordering.geojson", "Optimising line ordering"),
    ]
    if options.layout == "octilinear":
        stages.append(Stage("octilinear layout", "octi", ("--ilp-solver", options.ilp_solver), "04-schematic.geojson", "Creating octilinear layout"))
    elif options.layout == "orthoradial":
        stages.append(Stage("orthoradial layout", "octi", ("-b", "orthoradial", "--ilp-solver", options.ilp_solver), "04-schematic.geojson", "Creating orthoradial layout"))
    render_args = ["--render-engine", "svg"]
    if options.labels:
        render_args.append("--labels")
    stages.append(Stage("SVG rendering", "transitmap", tuple(render_args), final_temp.name, "Rendering SVG"))
    return stages


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


def run_pipeline(options: PipelineOptions) -> None:
    required = {"gtfs2graph", "topo", "loom", "transitmap"}
    if options.layout in {"octilinear", "orthoradial"}:
        required.add("octi")
    executables = {name: find_executable(name) for name in sorted(required)}

    output_parent = options.output_path.parent if options.output_path.parent != Path("") else Path(".")
    output_parent.mkdir(parents=True, exist_ok=True)
    if output_parent.exists() and not os.access(output_parent, os.W_OK):
        raise PermissionError(f"Output directory is not writable: {output_parent}")

    if options.save_intermediates:
        work_dir = options.work_dir or Path.cwd() / "loom-debug"
        work_dir.mkdir(parents=True, exist_ok=True)
        cleanup = False
    else:
        temp_parent = options.work_dir
        if temp_parent:
            temp_parent.mkdir(parents=True, exist_ok=True)
        work_dir = Path(tempfile.mkdtemp(prefix="loom-map-", dir=str(temp_parent) if temp_parent else None))
        cleanup = True

    final_temp = work_dir / "05-map.svg"
    stages = build_stages(options, final_temp)
    print("LOOM Map Generator\n")
    print(f"Input:   {options.gtfs_path}")
    print(f"Mode:    {options.mode}")
    print(f"Layout:  {options.layout}")
    print(f"Labels:  {'yes' if options.labels else 'no'}")
    print(f"Output:  {options.output_path}\n")

    try:
        previous: Optional[Path] = None
        for index, stage in enumerate(stages, start=1):
            out = work_dir / stage.output_name
            _run_stage(stage, index, len(stages), executables[stage.executable], previous, out, work_dir, options.verbose)
            previous = out
        if previous is None or not _looks_like_svg(previous):
            raise PipelineError(len(stages), "SVG rendering", [executables["transitmap"]], "Final output does not appear to contain SVG content.", work_dir)
        tmp_out = output_parent / f".{options.output_path.name}.tmp"
        shutil.copyfile(previous, tmp_out)
        os.replace(tmp_out, options.output_path)
        print(f"\nDone: {options.output_path}")
    except Exception:
        if not options.save_intermediates:
            print(f"Intermediate files preserved at: {work_dir}", file=sys.stderr)
            cleanup = False
        raise
    finally:
        if cleanup:
            shutil.rmtree(work_dir, ignore_errors=True)
