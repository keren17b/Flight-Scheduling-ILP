"""Generate feasible crew duties from a flight connection graph."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Tuple

from graph import (
    DEFAULT_MAX_CONNECTION,
    DEFAULT_MIN_CONNECTION,
    Airport,
    Flight,
    FlightGraph,
    load_flight_network,
)


# Duty-level limits. These are separate from the connection-time limits in graph.py.
MAX_DUTY_TIME = timedelta(hours=8)
MAX_FLIGHTS_PER_DUTY = 5


@dataclass(frozen=True)
class Duty:
    """A feasible ordered sequence of flights and its derived metadata."""

    duty_id: str
    flights: Tuple[Flight, ...]
    total_time: timedelta
    sitting_time: timedelta

    def __post_init__(self) -> None:
        if not self.flights:
            raise ValueError("a duty must contain at least one flight")

    @property
    def start_airport(self) -> Airport:
        return self.flights[0].origin

    @property
    def end_airport(self) -> Airport:
        return self.flights[-1].destination

    @property
    def start_time(self) -> datetime:
        return self.flights[0].departure_datetime

    @property
    def end_time(self) -> datetime:
        return self.flights[-1].arrival_datetime


def generate_duties(
    graph: FlightGraph,
    max_duty_time: timedelta = MAX_DUTY_TIME,
    max_flights: int = MAX_FLIGHTS_PER_DUTY,
) -> Dict[str, Duty]:
    """
    Generate all feasible duties with depth-first search.

    DFS starts once from every flight in the graph. Every non-empty legal prefix
    reached during the traversal is saved immediately as a separate Duty. Total
    time is measured from the first departure until the last arrival, including
    connection time between flights. Sitting time is the sum of those waits.
    """
    if max_duty_time <= timedelta(0):
        raise ValueError("max_duty_time must be positive")
    if max_flights < 1:
        raise ValueError("max_flights must be at least 1")

    duties: Dict[str, Duty] = {}

    def dfs(
        current_flight: Flight,
        path: List[Flight],
        total_time: timedelta,
        sitting_time: timedelta,
    ) -> None:
        duty_id = f"D{len(duties) + 1}"
        duties[duty_id] = Duty(
            duty_id=duty_id,
            flights=tuple(path),
            total_time=total_time,
            sitting_time=sitting_time,
        )

        if len(path) >= max_flights:
            return

        for next_flight in graph.get(current_flight, []):
            # The graph is chronological, so cycles should not occur. This
            # guard also keeps DFS safe if a graph is constructed manually.
            if next_flight in path:
                continue

            connection_time = (
                next_flight.departure_datetime - current_flight.arrival_datetime
            )
            next_flight_time = (
                next_flight.arrival_datetime - next_flight.departure_datetime
            )
            next_total_time = total_time + connection_time + next_flight_time
            next_sitting_time = sitting_time + connection_time

            if next_total_time > max_duty_time:
                continue

            path.append(next_flight)
            dfs(next_flight, path, next_total_time, next_sitting_time)
            path.pop()

    for first_flight in graph:
        first_flight_time = (
            first_flight.arrival_datetime - first_flight.departure_datetime
        )
        if timedelta(0) <= first_flight_time <= max_duty_time:
            dfs(first_flight, [first_flight], first_flight_time, timedelta(0))

    return duties

