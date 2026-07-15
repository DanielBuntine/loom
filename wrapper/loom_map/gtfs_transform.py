"""GTFS preprocessing: route filtering and route_short_name aggregation.

gtfs2graph groups trips into a "line" by GTFS route_id identity (see
src/gtfs2graph/graph/EdgeTripGeom.cpp), not by route_short_name. Some feeds
(e.g. Translink's) issue a fresh route_id per shape/pattern/timetable variant
under one public route number, which can turn a handful of real routes into
hundreds of distinct lines for the downstream line-ordering optimizer. These
functions rewrite a GTFS feed's routes.txt/trips.txt/stop_times.txt ahead of
gtfs2graph so callers can opt into merging by route_short_name and/or
restrict the feed to a specific set of routes before the expensive stages run.
"""

from __future__ import annotations

import csv
import io
import zipfile
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set, Tuple

AGGREGATE_BY_CHOICES = ("route_id", "route_short_name")


class GTFSTransformError(ValueError):
    """Raised when GTFS route filtering or aggregation cannot proceed."""


def filter_route_ids(routes: List[dict], wanted: Iterable[str]) -> Set[str]:
    """Return the route_id values whose route_short_name is in `wanted`."""
    wanted_set = {w.strip() for w in wanted if w.strip()}
    available = {r.get("route_short_name", "").strip() for r in routes}
    missing = wanted_set - available
    if missing:
        raise GTFSTransformError(
            "No route with route_short_name matching: " + ", ".join(sorted(missing))
        )
    return {r["route_id"] for r in routes if r.get("route_short_name", "").strip() in wanted_set}


def aggregate_route_map(routes: List[dict]) -> Dict[str, str]:
    """Map every route_id to a canonical route_id, grouped by
    (route_short_name, route_type, agency_id).

    route_type and agency_id are part of the key, not just route_short_name,
    because gtfs2graph filters trips by the *rewritten* route's route_type
    (via -m/--mots). Merging e.g. bus route "1" and rail route "1" onto one
    canonical route_id would make gtfs2graph classify every merged trip as
    whichever mode the canonical route happens to be, silently dropping or
    misclassifying trips under --mode. Routes with no route_short_name are
    left unaggregated. The canonical route_id within a group is its
    lexicographically smallest route_id, kept deterministic across runs
    rather than picking e.g. the busiest variant.
    """
    groups: Dict[str, List[str]] = {}
    for r in routes:
        name = r.get("route_short_name", "").strip()
        if not name:
            key = f"id:{r['route_id']}"
        else:
            route_type = r.get("route_type", "").strip()
            agency = r.get("agency_id", "").strip()
            key = f"name:{name}|type:{route_type}|agency:{agency}"
        groups.setdefault(key, []).append(r["route_id"])

    mapping: Dict[str, str] = {}
    for route_ids in groups.values():
        canonical = min(route_ids)
        for route_id in route_ids:
            mapping[route_id] = canonical
    return mapping


def _read_csv_rows(archive: zipfile.ZipFile, member: str) -> Tuple[List[str], List[dict]]:
    with archive.open(member) as fh:
        text = io.TextIOWrapper(fh, encoding="utf-8-sig", newline="")
        reader = csv.DictReader(text)
        return list(reader.fieldnames or []), list(reader)


def _write_csv(fieldnames: List[str], rows: List[dict]) -> bytes:
    buf = io.StringIO(newline="")
    writer = csv.DictWriter(buf, fieldnames=fieldnames, extrasaction="ignore", lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue().encode("utf-8")


def preprocess_gtfs(
    input_zip: Path,
    work_dir: Path,
    aggregate_by: str = "route_id",
    routes: Optional[List[str]] = None,
) -> Path:
    """Return a GTFS zip with route filtering/aggregation applied.

    Returns `input_zip` unchanged when neither a route filter nor
    route_short_name aggregation was requested.
    """
    if aggregate_by not in AGGREGATE_BY_CHOICES:
        raise GTFSTransformError(f"Unknown aggregate_by: {aggregate_by}")
    if aggregate_by == "route_id" and not routes:
        return input_zip

    with zipfile.ZipFile(input_zip) as archive:
        member_by_name = {Path(n).name: n for n in archive.namelist()}
        for required in ("routes.txt", "trips.txt"):
            if required not in member_by_name:
                raise GTFSTransformError(f"GTFS feed is missing {required}")

        route_fields, routes_rows = _read_csv_rows(archive, member_by_name["routes.txt"])
        trip_fields, trips_rows = _read_csv_rows(archive, member_by_name["trips.txt"])
        stop_times_member = member_by_name.get("stop_times.txt")
        stop_time_fields: List[str] = []
        stop_times_rows: Optional[List[dict]] = None
        # Only route filtering touches stop_times; aggregation only rewrites
        # routes.txt/trips.txt, so skip parsing this (often huge) file when
        # there's nothing to filter and just pass it through unchanged below.
        if routes and stop_times_member:
            stop_time_fields, stop_times_rows = _read_csv_rows(archive, stop_times_member)

        if routes:
            kept_route_ids = filter_route_ids(routes_rows, routes)
            routes_rows = [r for r in routes_rows if r["route_id"] in kept_route_ids]
            trips_rows = [t for t in trips_rows if t["route_id"] in kept_route_ids]
            if stop_times_rows is not None:
                kept_trip_ids = {t["trip_id"] for t in trips_rows}
                stop_times_rows = [s for s in stop_times_rows if s["trip_id"] in kept_trip_ids]

        if aggregate_by == "route_short_name":
            mapping = aggregate_route_map(routes_rows)
            canonical_ids = set(mapping.values())
            routes_rows = [r for r in routes_rows if r["route_id"] in canonical_ids]
            for t in trips_rows:
                t["route_id"] = mapping.get(t["route_id"], t["route_id"])

        work_dir.mkdir(parents=True, exist_ok=True)
        output_zip = work_dir / "00-preprocessed.gtfs.zip"
        with zipfile.ZipFile(output_zip, "w", compression=zipfile.ZIP_DEFLATED) as out:
            for info in archive.infolist():
                base = Path(info.filename).name
                if base == "routes.txt":
                    out.writestr(info.filename, _write_csv(route_fields, routes_rows))
                elif base == "trips.txt":
                    out.writestr(info.filename, _write_csv(trip_fields, trips_rows))
                elif base == "stop_times.txt" and stop_times_rows is not None:
                    out.writestr(info.filename, _write_csv(stop_time_fields, stop_times_rows))
                else:
                    out.writestr(info, archive.read(info.filename))

    return output_zip
