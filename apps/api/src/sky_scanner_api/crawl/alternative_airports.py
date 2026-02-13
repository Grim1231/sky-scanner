"""Alternative / nearby airport expansion for search broadening."""

from __future__ import annotations

ALTERNATIVE_AIRPORTS: dict[str, list[str]] = {
    # South Korea
    "ICN": ["GMP"],
    "GMP": ["ICN"],
    # Tokyo
    "NRT": ["HND"],
    "HND": ["NRT"],
    # London
    "LHR": ["LGW", "STN", "LTN", "LCY"],
    "LGW": ["LHR"],
    "STN": ["LHR"],
    "LTN": ["LHR"],
    "LCY": ["LHR"],
    # New York
    "JFK": ["EWR", "LGA"],
    "EWR": ["JFK", "LGA"],
    "LGA": ["JFK", "EWR"],
    # Los Angeles
    "LAX": ["BUR", "SNA", "ONT"],
    "BUR": ["LAX"],
    "SNA": ["LAX"],
    "ONT": ["LAX"],
    # Beijing
    "PEK": ["PKX"],
    "PKX": ["PEK"],
    # Paris
    "CDG": ["ORY"],
    "ORY": ["CDG"],
    # Shanghai
    "PVG": ["SHA"],
    "SHA": ["PVG"],
    # Osaka
    "KIX": ["ITM"],
    "ITM": ["KIX"],
    # San Francisco
    "SFO": ["OAK", "SJC"],
    "OAK": ["SFO"],
    "SJC": ["SFO"],
    # Chicago
    "ORD": ["MDW"],
    "MDW": ["ORD"],
    # Washington DC
    "IAD": ["DCA", "BWI"],
    "DCA": ["IAD", "BWI"],
    "BWI": ["IAD", "DCA"],
}


def expand_airports(code: str) -> list[str]:
    """Return the code plus its alternatives."""
    return [code, *ALTERNATIVE_AIRPORTS.get(code, [])]
