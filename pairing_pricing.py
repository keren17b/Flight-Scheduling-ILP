"""Pricing DFS: legal pairings with negative reduced cost."""

from __future__ import annotations

from datetime import timedelta
from typing import Dict, List

from duties import Duty
from duty_graph import DutyGraph
from pairing_cost import PairingCostFunction, current_pairing_cost
from pairings import (
    MAX_DUTIES_PER_PAIRING,
    MAX_PAIRING_TIME,
    Pairing,
    build_pairing_from_path,
)


MAX_PRICING_PAIRINGS = 50


def _reduced_cost(
    pairing: Pairing,
    duals: Dict[str, float],
    cost_function: PairingCostFunction,
) -> float:
    dual_sum = 0.0
    for duty in pairing.duties:
        for flight in duty.flights:
            dual_sum += duals[flight.flight_id]
    return cost_function(pairing) - dual_sum


def generate_pricing_pairings(
    graph: DutyGraph,
    duals: Dict[str, float],
    max_pairing_time: timedelta = MAX_PAIRING_TIME,
    max_duties: int = MAX_DUTIES_PER_PAIRING,
    max_pairings: int = MAX_PRICING_PAIRINGS,
    cost_function: PairingCostFunction = current_pairing_cost,
) -> Dict[str, Pairing]:
    """
    Search the duty graph for pairings with negative reduced cost.

    Legality matches generate_initial_pairings. A closed pairing is kept
    only when cost(p) - sum(dual[f] for f in p) is negative. Search stops
    after max_pairings improving pairings.
    """
    pairings: Dict[str, Pairing] = {}

    def dfs(current_duty: Duty, path: List[Duty]) -> None:
        if len(pairings) >= max_pairings:
            return

        returned_to_base = (
            current_duty.end_airport.is_crew_base
            and current_duty.end_airport.port_name
            == path[0].start_airport.port_name
        )

        if returned_to_base:
            pairing_id = f"P{len(pairings) + 1}"
            pairing = build_pairing_from_path(pairing_id, path)
            if _reduced_cost(pairing, duals, cost_function) < 0:
                pairings[pairing_id] = pairing

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

            if len(pairings) >= max_pairings:
                return

    for first_duty in graph:
        if len(pairings) >= max_pairings:
            break

        if not first_duty.start_airport.is_crew_base:
            continue

        first_duty_time = first_duty.end_time - first_duty.start_time
        if timedelta(0) <= first_duty_time <= max_pairing_time:
            dfs(first_duty, [first_duty])

    return pairings
