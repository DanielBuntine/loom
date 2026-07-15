"""Command-line interface for loom-map."""

from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import sys

from . import __version__
from .config import CANONICAL_MODES, DEFAULT_LAYOUT, DEFAULT_MODE, SUPPORTED_LAYOUTS, SUPPORTED_MODES
from .gtfs import GTFSValidationError, validate_gtfs_zip
from .pipeline import PipelineError, PipelineOptions, run_pipeline


class Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        self.print_usage(sys.stderr)
        self.exit(2, f"Error: {message}\n")


def git_commit() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=Path(__file__).resolve().parents[2],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            check=True,
        )
        return result.stdout.strip() or "unknown"
    except Exception:
        return "unknown"


def build_parser() -> argparse.ArgumentParser:
    modes = ", ".join(CANONICAL_MODES)
    aliases = ", ".join(sorted(k for k in SUPPORTED_MODES if k not in CANONICAL_MODES))
    parser = Parser(
        prog="loom-map",
        description="Generate a geographic or schematic transit diagram from a GTFS feed.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            f"Supported modes: {modes}\n"
            f"Recognised aliases: {aliases}\n"
            "Layouts: geographic (no octi stage), octilinear, orthoradial\n\n"
            "Examples:\n"
            "  loom-map network.zip\n"
            "  loom-map network.zip --mode tram --layout octilinear --labels -o network.svg"
        ),
    )
    parser.add_argument("input", nargs="?", type=Path, help="Path to a GTFS ZIP file")
    parser.add_argument("-o", "--output", type=Path, help="Output SVG path")
    parser.add_argument("--mode", default=DEFAULT_MODE, help=f"Transit mode (default: {DEFAULT_MODE})")
    parser.add_argument("--layout", default=DEFAULT_LAYOUT, choices=SUPPORTED_LAYOUTS, help=f"Layout: {', '.join(SUPPORTED_LAYOUTS)} (default: {DEFAULT_LAYOUT})")
    labels = parser.add_mutually_exclusive_group()
    labels.add_argument("--labels", dest="labels", action="store_true", help="Render stop/station labels")
    labels.add_argument("--no-labels", dest="labels", action="store_false", help="Do not render stop/station labels (default)")
    parser.set_defaults(labels=False)
    parser.add_argument("--save-intermediates", action="store_true", help="Preserve GeoJSON output from each pipeline stage")
    parser.add_argument("--work-dir", type=Path, help="Working/debug directory for intermediate files")
    parser.add_argument("--verbose", action="store_true", help="Show detailed pipeline information")
    parser.add_argument("--version", action="store_true", help="Show version information and exit")
    return parser


def default_output_path(input_path: Path) -> Path:
    name = input_path.name
    if name.endswith(".gtfs.zip"):
        return input_path.with_name(name[: -len(".gtfs.zip")] + ".svg")
    if name.endswith(".zip"):
        return input_path.with_suffix(".svg")
    return input_path.with_suffix(input_path.suffix + ".svg") if input_path.suffix else input_path.with_suffix(".svg")


def normalise_mode(mode: str) -> str:
    key = mode.strip().lower()
    if key in SUPPORTED_MODES:
        return SUPPORTED_MODES[key]
    raise ValueError(f"unsupported mode '{mode}'. Supported modes: {', '.join(CANONICAL_MODES)}")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.version:
        print(f"loom-map {__version__}")
        print(f"LOOM source: {git_commit()}")
        return 0
    if args.input is None:
        parser.error("the following argument is required: INPUT")

    try:
        mode = normalise_mode(args.mode)
        gtfs = args.input.expanduser().resolve()
        validate_gtfs_zip(gtfs)
        output = args.output.expanduser() if args.output else default_output_path(args.input)
        options = PipelineOptions(
            gtfs_path=gtfs,
            output_path=output,
            mode=mode,
            layout=args.layout,
            labels=args.labels,
            save_intermediates=args.save_intermediates,
            work_dir=args.work_dir,
            verbose=args.verbose,
        )
        run_pipeline(options)
        return 0
    except (GTFSValidationError, ValueError, FileNotFoundError, PermissionError, PipelineError, OSError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
