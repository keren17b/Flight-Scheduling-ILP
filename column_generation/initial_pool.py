"""Build the initial pairing pool for column generation."""

from __future__ import annotations

from datetime import timedelta
from typing import Dict, Iterable, List, Set, Tuple

from column_generation.config import MAX_INITIAL_PAIRINGS, MIN_INITIAL_COVERAGE
from crew_pairing.config import MAX_DUTIES_PER_PAIRING, MAX_PAIRING_TIME
from crew_pairing.duties import Duty
from crew_pairing.duty_graph import DutyGraph
from crew_pairing.pairings import Pairing, build_pairing_from_path, pairing_signature


def generate_initial_pairings(
    graph: DutyGraph,
    all_flight_ids: Iterable[str],
    max_pairing_time: timedelta = MAX_PAIRING_TIME,
    max_duties: int = MAX_DUTIES_PER_PAIRING,
    min_cover_per_flight: int = MIN_INITIAL_COVERAGE,
    max_pairings: int = MAX_INITIAL_PAIRINGS,
) -> Tuple[Dict[str, Pairing], Dict[str, int], Set[Tuple[str, ...]]]:
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
    existing_pairing_signature: Set[Tuple[str, ...]] = set()
    coverage_count = {flight_id: 0 for flight_id in all_flight_ids}

    def pairing_flight_ids(path: List[Duty]) -> List[str]:
        return [
            flight.flight_id
            for duty in path
            for flight in duty.flights
        ]

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
                existing_pairing_signature.add(pairing_signature(path))
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

    return pairings, coverage_count, existing_pairing_signature
