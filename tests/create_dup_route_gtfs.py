#!/usr/bin/env python3
"""Create a tiny GTFS fixture with two route_ids sharing one route_short_name.

Used to exercise --aggregate-by route_short_name and --routes end to end:
R1 and R2 both carry the public route number "T1" (as separate GTFS
route_id patterns, the way Translink-style feeds do); R3 is a distinct
route "T2".
"""
from __future__ import annotations

from pathlib import Path
import zipfile

FILES = {
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


def main() -> int:
    out = Path(__file__).with_name("dup-route-gtfs.zip")
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in FILES.items():
            archive.writestr(name, content)
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
