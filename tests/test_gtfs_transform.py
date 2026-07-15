import csv
import io
import sys
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "wrapper"))

from loom_map.gtfs_transform import (  # noqa: E402
    GTFSTransformError,
    aggregate_route_map,
    filter_route_ids,
    preprocess_gtfs,
)

ROUTES = [
    {"route_id": "R1", "route_short_name": "T1", "route_long_name": "Pattern A"},
    {"route_id": "R2", "route_short_name": "T1", "route_long_name": "Pattern B"},
    {"route_id": "R3", "route_short_name": "T2", "route_long_name": "Other Rail"},
]


def test_filter_route_ids_matches_short_name():
    kept = filter_route_ids(ROUTES, ["T2"])
    assert kept == {"R3"}


def test_filter_route_ids_matches_multiple():
    kept = filter_route_ids(ROUTES, ["T1", "T2"])
    assert kept == {"R1", "R2", "R3"}


def test_filter_route_ids_ignores_blank_entries():
    kept = filter_route_ids(ROUTES, ["T2", "", "  "])
    assert kept == {"R3"}


def test_filter_route_ids_raises_for_unknown_route():
    with pytest.raises(GTFSTransformError, match="T9"):
        filter_route_ids(ROUTES, ["T9"])


def test_aggregate_route_map_groups_by_short_name():
    mapping = aggregate_route_map(ROUTES)
    assert mapping["R1"] == mapping["R2"] == "R1"
    assert mapping["R3"] == "R3"


def test_aggregate_route_map_leaves_unnamed_routes_unaggregated():
    routes = ROUTES + [
        {"route_id": "R4", "route_short_name": "", "route_long_name": "No short name A"},
        {"route_id": "R5", "route_short_name": "", "route_long_name": "No short name B"},
    ]
    mapping = aggregate_route_map(routes)
    assert mapping["R4"] == "R4"
    assert mapping["R5"] == "R5"


def _write_gtfs_zip(path: Path, files: dict) -> Path:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return path


def _dup_route_gtfs_files() -> dict:
    return {
        "agency.txt": "agency_id,agency_name,agency_url,agency_timezone\nA,Tiny Transit,https://example.com,Etc/UTC\n",
        "stops.txt": "stop_id,stop_name,stop_lat,stop_lon\nS1,Alpha,47.0000,7.0000\nS2,Beta,47.0100,7.0100\nS3,Gamma,47.0200,7.0200\n",
        "routes.txt": (
            "route_id,agency_id,route_short_name,route_long_name,route_type,route_color\n"
            "R1,A,T1,Pattern A,2,3366cc\n"
            "R2,A,T1,Pattern B,2,3366cc\n"
            "R3,A,T2,Other Rail,2,cc3366\n"
        ),
        "trips.txt": (
            "route_id,service_id,trip_id,trip_headsign\n"
            "R1,WK,T1,Gamma\n"
            "R2,WK,T2,Alpha\n"
            "R3,WK,T3,Beta\n"
        ),
        "stop_times.txt": (
            "trip_id,arrival_time,departure_time,stop_id,stop_sequence\n"
            "T1,08:00:00,08:00:00,S1,1\nT1,08:05:00,08:05:00,S2,2\nT1,08:10:00,08:10:00,S3,3\n"
            "T2,09:00:00,09:00:00,S3,1\nT2,09:05:00,09:05:00,S2,2\nT2,09:10:00,09:10:00,S1,3\n"
            "T3,10:00:00,10:00:00,S1,1\nT3,10:05:00,10:05:00,S3,2\n"
        ),
        "calendar.txt": (
            "service_id,monday,tuesday,wednesday,thursday,friday,saturday,sunday,start_date,end_date\n"
            "WK,1,1,1,1,1,1,1,20260101,20261231\n"
        ),
    }


def _read_csv(archive: zipfile.ZipFile, name: str) -> list:
    with archive.open(name) as fh:
        text = io.TextIOWrapper(fh, encoding="utf-8-sig", newline="")
        return list(csv.DictReader(text))


def test_preprocess_gtfs_noop_by_default(tmp_path):
    gtfs = _write_gtfs_zip(tmp_path / "in.zip", _dup_route_gtfs_files())
    result = preprocess_gtfs(gtfs, tmp_path / "work", aggregate_by="route_id", routes=None)
    assert result == gtfs


def test_preprocess_gtfs_filters_routes_trips_and_stop_times(tmp_path):
    gtfs = _write_gtfs_zip(tmp_path / "in.zip", _dup_route_gtfs_files())
    result = preprocess_gtfs(gtfs, tmp_path / "work", aggregate_by="route_id", routes=["T2"])
    assert result != gtfs
    with zipfile.ZipFile(result) as archive:
        routes = _read_csv(archive, "routes.txt")
        trips = _read_csv(archive, "trips.txt")
        stop_times = _read_csv(archive, "stop_times.txt")
        assert {r["route_id"] for r in routes} == {"R3"}
        assert {t["trip_id"] for t in trips} == {"T3"}
        assert {s["trip_id"] for s in stop_times} == {"T3"}
        # untouched files pass through unchanged
        agency = _read_csv(archive, "agency.txt")
        assert agency[0]["agency_id"] == "A"


def test_preprocess_gtfs_aggregates_by_short_name(tmp_path):
    gtfs = _write_gtfs_zip(tmp_path / "in.zip", _dup_route_gtfs_files())
    result = preprocess_gtfs(gtfs, tmp_path / "work", aggregate_by="route_short_name", routes=None)
    with zipfile.ZipFile(result) as archive:
        routes = _read_csv(archive, "routes.txt")
        trips = _read_csv(archive, "trips.txt")
        assert {r["route_id"] for r in routes} == {"R1", "R3"}
        trip_route_ids = {t["trip_id"]: t["route_id"] for t in trips}
        assert trip_route_ids["T1"] == "R1"
        assert trip_route_ids["T2"] == "R1"  # was R2, remapped onto the canonical R1
        assert trip_route_ids["T3"] == "R3"


def test_preprocess_gtfs_filter_then_aggregate(tmp_path):
    gtfs = _write_gtfs_zip(tmp_path / "in.zip", _dup_route_gtfs_files())
    result = preprocess_gtfs(gtfs, tmp_path / "work", aggregate_by="route_short_name", routes=["T1"])
    with zipfile.ZipFile(result) as archive:
        routes = _read_csv(archive, "routes.txt")
        trips = _read_csv(archive, "trips.txt")
        assert {r["route_id"] for r in routes} == {"R1"}
        assert {t["route_id"] for t in trips} == {"R1"}
        assert {t["trip_id"] for t in trips} == {"T1", "T2"}
