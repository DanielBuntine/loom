#!/usr/bin/env python3
"""Create a tiny deterministic GTFS fixture for wrapper smoke tests."""
from __future__ import annotations

from pathlib import Path
import zipfile

FILES = {
    "agency.txt": "agency_id,agency_name,agency_url,agency_timezone\nA,Tiny Transit,https://example.com,Etc/UTC\n",
    "stops.txt": "stop_id,stop_name,stop_lat,stop_lon\nS1,Alpha,47.0000,7.0000\nS2,Beta,47.0100,7.0100\nS3,Gamma,47.0200,7.0200\n",
    "routes.txt": "route_id,agency_id,route_short_name,route_long_name,route_type,route_color\nR1,A,T1,Tiny Rail,2,3366cc\n",
    "trips.txt": "route_id,service_id,trip_id,trip_headsign\nR1,WK,T1,Gamma\nR1,WK,T2,Alpha\n",
    "stop_times.txt": "trip_id,arrival_time,departure_time,stop_id,stop_sequence\nT1,08:00:00,08:00:00,S1,1\nT1,08:05:00,08:05:00,S2,2\nT1,08:10:00,08:10:00,S3,3\nT2,09:00:00,09:00:00,S3,1\nT2,09:05:00,09:05:00,S2,2\nT2,09:10:00,09:10:00,S1,3\n",
    "calendar.txt": "service_id,monday,tuesday,wednesday,thursday,friday,saturday,sunday,start_date,end_date\nWK,1,1,1,1,1,1,1,20260101,20261231\n",
}


def main() -> int:
    out = Path(__file__).with_name("tiny-gtfs.zip")
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in FILES.items():
            archive.writestr(name, content)
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
