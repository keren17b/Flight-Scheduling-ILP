"""Generate feasible crew pairings from a duty connection graph."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, Iterable, List, Tuple

from duties import Duty
from duty_graph import DutyGraph
from flights_graph import Airport


# Pairing-level limits. Rest between duties is included in MAX_PAIRING_TIME.
MAX_PAIRING_TIME = timedelta(days=5)
MAX_DUTIES_PER_PAIRING = 5
MAX_INITIAL_PAIRINGS = 5000
MIN_INITIAL_COVERAGE = 1


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


def generate_pairings(
    graph: DutyGraph,
    max_pairing_time: timedelta = MAX_PAIRING_TIME,
    max_duties: int = MAX_DUTIES_PER_PAIRING,
) -> Dict[str, Pairing]:
    """
    Generate all feasible pairings with depth-first search.

    DFS starts only from duties that depart from a crew base. A path is saved
    whenever it reaches a crew base, and DFS then continues so both a shorter
    pairing ending at an intermediate hub and a longer pairing can be kept.
    Total time is measured from the first duty's departure until the last
    duty's arrival, so it includes all rest between duties.

    A pairing is closed: it is saved only when it returns to the same crew
    base from which it departed.
    """
    if max_pairing_time <= timedelta(0):
        raise ValueError("max_pairing_time must be positive")
    if max_duties < 1:
        raise ValueError("max_duties must be at least 1")

    pairings: Dict[str, Pairing] = {}

    def dfs(current_duty: Duty, path: List[Duty]) -> None:
        total_time = current_duty.end_time - path[0].start_time

        if (
            current_duty.end_airport.is_crew_base
            and current_duty.end_airport.port_name
            == path[0].start_airport.port_name
        ):
            pairing_id = f"P{len(pairings) + 1}"
            pairings[pairing_id] = build_pairing_from_path(pairing_id, path)

        if len(path) >= max_duties:
            return

        for next_duty in graph.get(current_duty, []):
            # Duty graphs are chronological, but keep DFS safe for manually
            # constructed graphs as well.
            if next_duty in path:
                continue

            next_total_time = next_duty.end_time - path[0].start_time
            if next_total_time > max_pairing_time:
                continue

            path.append(next_duty)
            dfs(next_duty, path)
            path.pop()

    for first_duty in graph:
        if not first_duty.start_airport.is_crew_base:
            continue

        first_duty_time = first_duty.end_time - first_duty.start_time
        if timedelta(0) <= first_duty_time <= max_pairing_time:
            dfs(first_duty, [first_duty])

    return pairings


def generate_initial_pairings(
    graph: DutyGraph,
    all_flight_ids: Iterable[str],
    max_pairing_time: timedelta = MAX_PAIRING_TIME,
    max_duties: int = MAX_DUTIES_PER_PAIRING,
    min_cover_per_flight: int = MIN_INITIAL_COVERAGE,
    max_pairings: int = MAX_INITIAL_PAIRINGS,
) -> Tuple[Dict[str, Pairing], Dict[str, int]]:
    """
    Generate a small initial pairing pool with a limited DFS.

    Pairings are kept only when they cover a flight that still needs
    initial coverage. Search stops when every tracked flight reaches
    min_cover_per_flight, when max_pairings is reached, or when DFS
    has no remaining legal branches.
    """
    if max_pairing_time <= timedelta(0):
        raise ValueError("max_pairing_time must be positive")
    if max_duties < 1:
        raise ValueError("max_duties must be at least 1")
    if min_cover_per_flight < 1:
        raise ValueError("min_cover_per_flight must be at least 1")
    if max_pairings < 1:
        raise ValueError("max_pairings must be at least 1")

    pairings: Dict[str, Pairing] = {}
    coverage_count = {flight_id: 0 for flight_id in all_flight_ids}

    def pairing_flight_ids(path: List[Duty]) -> set[str]:
        covered = set()
        for duty in path:
            for flight in duty.flights:
                covered.add(flight.flight_id)
        return covered

    def enough_coverage() -> bool:
        return all(
            count >= min_cover_per_flight
            for count in coverage_count.values()
        )

    def dfs(current_duty: Duty, path: List[Duty]) -> None:
        if len(pairings) >= max_pairings:
            return

        if enough_coverage():
            return

        returned_to_base = (
            current_duty.end_airport.is_crew_base
            and current_duty.end_airport.port_name
            == path[0].start_airport.port_name
        )

        if returned_to_base:
            covered = pairing_flight_ids(path)
            useful = any(
                coverage_count[flight_id] < min_cover_per_flight
                for flight_id in covered
                if flight_id in coverage_count
            )

            if useful:
                pairing_id = f"P{len(pairings) + 1}"
                pairings[pairing_id] = build_pairing_from_path(pairing_id, path)
                for flight_id in covered:
                    if flight_id in coverage_count:
                        coverage_count[flight_id] += 1

        if len(path) >= max_duties:
            return

        for next_duty in graph.get(current_duty, []):
            if next_duty in path:
                continue

            total_time = next_duty.end_time - path[0].start_time
            if total_time > max_pairing_time:
                continue

            path.append(next_duty)
            dfs(next_duty, path)
            path.pop()

            if enough_coverage():
                return

            if len(pairings) >= max_pairings:
                return

    for first_duty in graph:
        if enough_coverage():
            break

        if len(pairings) >= max_pairings:
            break

        if not first_duty.start_airport.is_crew_base:
            continue

        first_duty_time = first_duty.end_time - first_duty.start_time
        if timedelta(0) <= first_duty_time <= max_pairing_time:
            dfs(first_duty, [first_duty])

    return pairings, coverage_count
