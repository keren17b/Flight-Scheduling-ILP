"""Identify padding flights that the ILP does not have to cover."""

from __future__ import annotations

from typing import Dict, List

from crew_pairing.config import PADDING_DATE_RANGES
from crew_pairing.flights_graph import Flight


PADDING_TAG = "padding"
REQUIRED_TAG = "required"


def is_padding_flight(flight: Flight) -> bool:
    """Return whether departure falls in any configured padding interval."""
    departure_date = flight.departure_datetime.date()
    return any(start <= departure_date <= end for start, end in PADDING_DATE_RANGES)


def flight_constraint_tags(flights: Dict[str, Flight]) -> List[str]:
    """
    One tag per matrix column, in the same order as flights dict keys.

    Padding columns use PADDING_TAG (cover at most once).
    All other columns use REQUIRED_TAG (cover exactly once).
    """
    tags: List[str] = []
    for flight in flights.values():
        if is_padding_flight(flight):
            tags.append(PADDING_TAG)
        else:
            tags.append(REQUIRED_TAG)
    return tags
