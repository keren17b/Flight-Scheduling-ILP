"""Identify padding flights that the ILP does not have to cover."""

from __future__ import annotations

from datetime import date
from typing import Dict, List

from flights_graph import Flight


PADDING_TAG = "padding"
REQUIRED_TAG = "required"

PADDING_START_DATE = date(2000, 1, 8)
PADDING_END_DATE = date(2000, 1, 10)


def is_padding_flight(flight: Flight) -> bool:
    departure_date = flight.departure_datetime.date()
    return PADDING_START_DATE <= departure_date <= PADDING_END_DATE


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
