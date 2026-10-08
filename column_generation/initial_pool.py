"""Build the initial pairing pool for column generation."""

from __future__ import annotations

from datetime import timedelta
from typing import Dict, List, Set, Tuple

from column_generation.config import (
    MAX_INITIAL_DFS_STATES,
    MAX_INITIAL_DFS_STATES_PER_START,
    MAX_INITIAL_PAIRINGS,
    MAX_INITIAL_PAIRINGS_PER_START,
    MIN_INITIAL_COVERAGE,
)
from crew_pairing.config import MAX_DUTIES_PER_PAIRING, MAX_PAIRING_TIME
from crew_pairing.duties import Duty
from crew_pairing.duty_graph import DutyGraph
from crew_pairing.flights_graph import Flight
from crew_pairing.padding_flights import is_padding_flight
from crew_pairing.pairings import Pairing, build_pairing_from_path, pairing_signature
from run_progress import ProgressTicker


def generate_initial_pairings(
    graph: DutyGraph,
    flights: Dict[str, Flight],
    max_pairing_time: timedelta = MAX_PAIRING_TIME,
    max_duties: int = MAX_DUTIES_PER_PAIRING,
    min_cover_per_flight: int = MIN_INITIAL_COVERAGE,
    max_pairings: int = MAX_INITIAL_PAIRINGS,
    max_dfs_states: int = MAX_INITIAL_DFS_STATES,
    max_dfs_states_per_start: int = MAX_INITIAL_DFS_STATES_PER_START,
    max_pairings_per_start: int = MAX_INITIAL_PAIRINGS_PER_START,
) -> Tuple[Dict[str, Pairing], Dict[str, int], Set[Tuple[str, ...]]]:
    """
    Generate a small, diverse initial pairing pool with bounded DFS.

    Only required (non-padding) flights count toward coverage.
    min_cover_per_flight is a coverage target, not a strict upper bound. A
    pairing may improve one flight's coverage while including other flights
    that have already exceeded their targets.

    Search walks starting duties one at a time so a single branch cannot consume
    the whole budget. Incomplete required-flight coverage is not a failure:
    pricing can add missing columns later.
    """
    if max_pairing_time <= timedelta(0):
        raise ValueError("max_pairing_time must be positive")
    if max_duties < 1:
        raise ValueError("max_duties must be at least 1")
    if min_cover_per_flight < 1:
        raise ValueError("min_cover_per_flight must be at least 1")
    if max_pairings < 1:
        raise ValueError("max_pairings must be at least 1")
    if max_dfs_states < 1:
        raise ValueError("max_dfs_states must be at least 1")
    if max_dfs_states_per_start < 1:
        raise ValueError("max_dfs_states_per_start must be at least 1")
    if max_pairings_per_start < 1:
        raise ValueError("max_pairings_per_start must be at least 1")

    pairings: Dict[str, Pairing] = {}
    existing_pairing_signature: Set[Tuple[str, ...]] = set()
    coverage_count = {
        flight_id: 0
        for flight_id, flight in flights.items()
        if not is_padding_flight(flight)
    }
    ticker = ProgressTicker("Initial pairing search")
    global_states = 0

    def pairing_flight_ids(path: List[Duty]) -> List[str]:
        return [
            flight.flight_id
            for duty in path
            for flight in duty.flights
        ]

    def enough_required_coverage() -> bool:
        return all(
            count >= min_cover_per_flight
            for count in coverage_count.values()
        )

    def pool_or_global_budget_exhausted() -> bool:
        return (
            len(pairings) >= max_pairings
            or global_states >= max_dfs_states
            or enough_required_coverage()
        )

    def dfs(
        current_duty: Duty,
        path: List[Duty],
        local_states: List[int],
        local_saved: List[int],
    ) -> None:
        nonlocal global_states

        if local_states[0] >= max_dfs_states_per_start:
            return
        if local_saved[0] >= max_pairings_per_start:
            return
        if pool_or_global_budget_exhausted():
            return

        local_states[0] += 1
        global_states += 1
        if global_states % 10_000 == 0:
            ticker.update(global_states, f"{len(pairings):,} pairings found")

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
            signature = pairing_signature(path)

            if useful and signature not in existing_pairing_signature:
                pairing_id = f"P{len(pairings) + 1}"
                pairings[pairing_id] = build_pairing_from_path(pairing_id, path)
                existing_pairing_signature.add(signature)
                local_saved[0] += 1
                for flight_id in covered:
                    if flight_id in coverage_count:
                        coverage_count[flight_id] += 1

        if len(path) >= max_duties:
            return
        if local_saved[0] >= max_pairings_per_start:
            return
        if pool_or_global_budget_exhausted():
            return

        for next_duty in graph.get(current_duty, []):
            if next_duty in path:
                continue

            total_time = next_duty.end_time - path[0].start_time
            if total_time > max_pairing_time:
                continue

            path.append(next_duty)
            dfs(next_duty, path, local_states, local_saved)
            path.pop()

            if local_states[0] >= max_dfs_states_per_start:
                return
            if local_saved[0] >= max_pairings_per_start:
                return
            if pool_or_global_budget_exhausted():
                return

    for first_duty in graph:
        if pool_or_global_budget_exhausted():
            break

        if not first_duty.start_airport.is_crew_base:
            continue

        first_duty_time = first_duty.end_time - first_duty.start_time
        if timedelta(0) <= first_duty_time <= max_pairing_time:
            dfs(first_duty, [first_duty], [0], [0])

    return pairings, coverage_count, existing_pairing_signature
