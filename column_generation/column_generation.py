"""Column generation loop. Owns the shared set of pairing signatures."""

from __future__ import annotations

from typing import Dict, Set, Tuple

from column_generation.config import MAX_INITIAL_PAIRINGS, MAX_ITERATIONS
from column_generation.initial_pool import generate_initial_pairings
from crew_pairing.duty_graph import DutyGraph
from crew_pairing.flights_graph import Flight
from column_generation.master_lp import MasterLpResult, solve_master_lp
from crew_pairing.pairing_cost import PairingCostFunction, current_pairing_cost
from column_generation.pairing_pricing import generate_pricing_pairings
from crew_pairing.pairings import Pairing


def run_column_generation(
    graph: DutyGraph,
    flights: Dict[str, Flight],
    cost_function: PairingCostFunction = current_pairing_cost,
    max_initial_pairings: int = MAX_INITIAL_PAIRINGS,
    max_iterations: int = MAX_ITERATIONS,
) -> Tuple[Dict[str, Pairing], Set[Tuple[str, ...]], MasterLpResult]:
    """
    Build columns from an initial pool, then price and add new pairings.

    existing_pairing_signature is created once from the initial pairings and passed
    into every pricing call. Pricing adds each new signature to that same set.
    """
    columns, _coverage_count, existing_pairing_signature = generate_initial_pairings(
        graph,
        flights.keys(),
        max_pairings=max_initial_pairings,
    )

    master_result = solve_master_lp(columns, flights, cost_function)
    for _iteration in range(max_iterations):
        new_pairings, existing_pairing_signature = generate_pricing_pairings(
            graph,
            master_result.duals,
            existing_pairing_signature,
            cost_function=cost_function,
        )
        if not new_pairings:
            return columns, existing_pairing_signature, master_result

        for pairing in new_pairings.values():
            columns[f"P{len(columns) + 1}"] = pairing

        master_result = solve_master_lp(columns, flights, cost_function)

    return columns, existing_pairing_signature, master_result
