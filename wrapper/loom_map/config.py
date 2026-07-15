"""Authoritative public wrapper configuration."""

SUPPORTED_MODES = {
    "all": "all",
    "tram": "tram",
    "streetcar": "tram",
    "light-rail": "tram",
    "subway": "subway",
    "metro": "subway",
    "rail": "rail",
    "train": "rail",
    "heavy-rail": "rail",
    "commuter-rail": "rail",
    "suburban-rail": "rail",
    "bus": "bus",
    "ferry": "ferry",
    "boat": "ferry",
    "ship": "ferry",
    "cablecar": "cablecar",
    "gondola": "gondola",
    "funicular": "funicular",
    "coach": "coach",
    "monorail": "monorail",
    "mono-rail": "monorail",
    "trolley": "trolley",
    "trolleybus": "trolley",
    "trolley-bus": "trolley",
}

CANONICAL_MODES = tuple(dict.fromkeys(SUPPORTED_MODES.values()))
SUPPORTED_LAYOUTS = ("geographic", "octilinear", "orthoradial")
ALL_LAYOUTS = ("geographic", "octilinear", "orthoradial")
LAYOUT_CHOICES = SUPPORTED_LAYOUTS + ("all",)
DEFAULT_MODE = "rail"
DEFAULT_LAYOUT = "octilinear"
DEFAULT_ILP_SOLVER = "cbc"
DEFAULT_AGGREGATE_BY = "route_id"
AGGREGATE_BY_CHOICES = ("route_id", "route_short_name")
REQUIRED_GTFS_FILES = ("agency.txt", "stops.txt", "routes.txt", "trips.txt", "stop_times.txt")
