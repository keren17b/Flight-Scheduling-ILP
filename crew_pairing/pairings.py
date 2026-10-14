"""Pairing model and helpers shared by initial-pool generation and pricing."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import List, Tuple

from crew_pairing.duties import Duty
from crew_pairing.flights_graph import Airport


@dataclass(frozen=True)
class Pairing:
    """A feasible ordered sequence of duties and its derived metadata."""

    pairing_id: str
    duties: Tuple[Duty, ...]
    total_time: timedelta
    flight_time: timedelta
    sitting_time: timedelta
    rest: timedelta

    def __post_init__(self) -> None:
        if not self.duties:
            raise ValueError("a pairing must contain at least one duty")
        if self.flight_time < timedelta(0):
            raise ValueError("flight_time cannot be negative")
        if self.sitting_time < timedelta(0):
            raise ValueError("sitting_time cannot be negative")
        if self.rest < timedelta(0):
            raise ValueError("rest cannot be negative")
        if self.total_time != self.flight_time + self.sitting_time + self.rest:
            raise ValueError(
                "total_time must equal flight_time plus sitting_time plus rest"
            )

    @property
    def start_airport(self) -> Airport:
        return self.duties[0].start_airport
    #that must be the same - no?
    @property
    def end_airport(self) -> Airport:
        return self.duties[-1].end_airport

    @property
    def start_time(self) -> datetime:
        return self.duties[0].start_time

    @property
    def end_time(self) -> datetime:
        return self.duties[-1].end_time


def calculate_pairing_rest(duties: Tuple[Duty, ...]) -> timedelta:
    """Return the total layover time between consecutive duties."""
    rest = timedelta(0)
    for previous_duty, next_duty in zip(duties, duties[1:]):
        rest += next_duty.start_time - previous_duty.end_time
    return rest


def calculate_pairing_flight_time(duties: Tuple[Duty, ...]) -> timedelta:
    """Return the total time spent on flights across all duties."""
    return sum((duty.flight_time for duty in duties), timedelta(0))


def calculate_pairing_sitting_time(duties: Tuple[Duty, ...]) -> timedelta:
    """Return the total connection time inside all duties."""
    return sum((duty.sitting_time for duty in duties), timedelta(0))


def pairing_signature(duties: Tuple[Duty, ...] | List[Duty]) -> Tuple[str, ...]:
    return tuple(duty.duty_id for duty in duties)


def build_pairing_from_path(pairing_id: str, path: List[Duty]) -> Pairing:
    pairing_duties = tuple(path)
    flight_time = calculate_pairing_flight_time(pairing_duties)
    sitting_time = calculate_pairing_sitting_time(pairing_duties)
    rest = calculate_pairing_rest(pairing_duties)
    return Pairing(
        pairing_id=pairing_id,
        duties=pairing_duties,
        total_time=flight_time + sitting_time + rest,
        flight_time=flight_time,
        sitting_time=sitting_time,
        rest=rest,
    )
