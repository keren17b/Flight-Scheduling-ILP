"""Generate feasible crew duties from a flight connection graph."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import List

from graph import (
    DEFAULT_MAX_CONNECTION,
    DEFAULT_MIN_CONNECTION,
    Flight,
    FlightGraph,
    load_flight_network,
)


# Duty-level limits. These are separate from the connection-time limits in graph.py.
MAX_DUTY_TIME = timedelta(hours=12)
MAX_FLIGHTS_PER_DUTY = 5


@dataclass(frozen=True)
class Duty:
    """A feasible ordered sequence of flights and its total elapsed time."""

    flights: tuple[Flight, ...]
    total_time: timedelta


def generate_duties(
    graph: FlightGraph,
    max_duty_time: timedelta = MAX_DUTY_TIME,
    max_flights: int = MAX_FLIGHTS_PER_DUTY,
) -> List[Duty]:
    """
    Generate all feasible duties with depth-first search.

    A duty starts with a flight departing from a crew base. Every non-empty
    prefix reached by DFS is a candidate duty. Its total time is measured from
    the first flight's departure until the last flight's arrival, including
    connection time between flights.
    """
    if max_duty_time <= timedelta(0):
        raise ValueError("max_duty_time must be positive")
    if max_flights < 1:
        raise ValueError("max_flights must be at least 1")

    duties: List[Duty] = []

    def dfs(
        current_flight: Flight,
        path: List[Flight],
        total_time: timedelta,
    ) -> None:
        duties.append(Duty(flights=tuple(path), total_time=total_time))

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

            if next_total_time > max_duty_time:
                continue

            path.append(next_flight)
            dfs(next_flight, path, next_total_time)
            path.pop()

    for first_flight in graph:
        if first_flight.origin.is_crew_base != 1:
            continue

        first_flight_time = (
            first_flight.arrival_datetime - first_flight.departure_datetime
        )
        if timedelta(0) <= first_flight_time <= max_duty_time:
            dfs(first_flight, [first_flight], first_flight_time)

    return duties


def load_duties(
    flights_csv_path: str | Path,
    hubs_csv_path: str | Path,
    max_duty_time: timedelta = MAX_DUTY_TIME,
    max_flights: int = MAX_FLIGHTS_PER_DUTY,
    min_connection: timedelta = DEFAULT_MIN_CONNECTION,
    max_connection: timedelta = DEFAULT_MAX_CONNECTION,
) -> List[Duty]:
    """Load the flight network from CSV files and generate its duties."""
    _, _, graph = load_flight_network(
        flights_csv_path,
        hubs_csv_path,
        min_connection=min_connection,
        max_connection=max_connection,
    )
    return generate_duties(
        graph,
        max_duty_time=max_duty_time,
        max_flights=max_flights,
    )
