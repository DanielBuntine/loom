"""Lightweight GTFS ZIP validation."""

from __future__ import annotations

from pathlib import Path
import zipfile

from .config import REQUIRED_GTFS_FILES


class GTFSValidationError(ValueError):
    """Raised when an input file is not a usable GTFS ZIP."""


def _normalise_zip_name(name: str) -> str:
    return name.replace("\\", "/").strip("/")


def validate_gtfs_zip(path: Path) -> None:
    """Validate that *path* exists, is a readable ZIP, and has core GTFS files."""
    if not path.exists():
        raise GTFSValidationError(f"Input file does not exist: {path}")
    if not path.is_file():
        raise GTFSValidationError(f"Input path is not a file: {path}")

    try:
        with zipfile.ZipFile(path) as archive:
            bad_member = archive.testzip()
            if bad_member is not None:
                raise GTFSValidationError(
                    "Input does not appear to be a valid GTFS ZIP:\n"
                    f"corrupt ZIP member: {bad_member}"
                )
            names = {_normalise_zip_name(info.filename) for info in archive.infolist() if not info.is_dir()}
    except zipfile.BadZipFile as exc:
        raise GTFSValidationError(
            "Input does not appear to be a valid GTFS ZIP:\nnot a readable ZIP archive"
        ) from exc
    except OSError as exc:
        raise GTFSValidationError(f"Could not read input ZIP: {exc}") from exc

    basenames = {Path(name).name for name in names}
    missing = [required for required in REQUIRED_GTFS_FILES if required not in basenames]
    if missing:
        details = "\n".join(f"missing {name}" for name in missing)
        raise GTFSValidationError(f"Input does not appear to be a valid GTFS ZIP:\n{details}")
