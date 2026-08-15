"""Generate feasible crew pairings from a duty connection graph."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

from duties import Duty
from duty_graph import DutyGraph
from flights_graph import Airport


# Pairing-level limits. Rest between duties is included in MAX_PAIRING_TIME.
MAX_PAIRING_TIME = timedelta(days=5)
MAX_DUTIES_PER_PAIRING = 5


@dataclass(frozen=True)
class Pairing:
    """A feasible ordered sequence of duties and its derived metadata."""

    pairing_id: str
    duties: Tuple[Duty, ...]
    total_time: timedelta
    cost: Optional[float] = None

    def __post_init__(self) -> None:
        if not self.duties:
            raise ValueError("a pairing must contain at least one duty")

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


def calculate_pairing_cost(duties: Tuple[Duty, ...]) -> Optional[float]:
    """Return the pairing cost once the project's cost model is defined."""
    # TODO: Add the pairing cost calculation here.
    return None


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
            pairing_duties = tuple(path)
            pairings[pairing_id] = Pairing(
                pairing_id=pairing_id,
                duties=pairing_duties,
                total_time=total_time,
                # Future pairing cost calculation is performed here.
                cost=calculate_pairing_cost(pairing_duties),
            )

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
