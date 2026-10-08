"""Column generation loop. Owns the shared set of pairing signatures."""

from __future__ import annotations

import random
from dataclasses import replace
from typing import Dict, Tuple

from column_generation.config import (
    ARTIFICIAL_TOLERANCE,
    MAX_EMPTY_PRICING_ATTEMPTS,
    MAX_INITIAL_PAIRINGS,
    MAX_ITERATIONS,
    PRICING_RANDOM_SEED,
)
from column_generation.initial_pool import generate_initial_pairings
from column_generation.master_lp import MasterLpResult, solve_master_lp
from column_generation.pairing_pricing import generate_pricing_pairings

from crew_pairing.duty_graph import DutyGraph
from crew_pairing.flights_graph import Flight
from crew_pairing.pairing_cost import (
    PairingCostFunction,
    current_pairing_cost,
)
from crew_pairing.pairings import Pairing

from run_progress import progress


def run_column_generation(
    graph: DutyGraph,
    flights: Dict[str, Flight],
    cost_function: PairingCostFunction = current_pairing_cost,
    max_initial_pairings: int = MAX_INITIAL_PAIRINGS,
    max_iterations: int = MAX_ITERATIONS,
) -> Tuple[Dict[str, Pairing], MasterLpResult]:
    # Reuse one random sequence throughout this column-generation run.
    rng = random.Random(PRICING_RANDOM_SEED)

    # ---------------------------------------------------------
    # 1. Generate initial pairing pool
    # ---------------------------------------------------------
    progress(
        f"Searching initial pairings "
        f"(limit {max_initial_pairings:,})"
    )

    columns, existing_pairing_signature = (
        generate_initial_pairings(
            graph,
            flights,
            max_pairings=max_initial_pairings,
        )
    )

    progress(
        f"Initial pool ready: {len(columns):,} pairings; "
        "solving first master LP"
    )

    # ---------------------------------------------------------
    # 2. Solve first restricted master LP
    # ---------------------------------------------------------
    master_result = solve_master_lp(
        columns,
        flights,
        cost_function,
    )

    progress(
        f"First master LP solved: "
        f"objective {master_result.objective:,.2f}"
    )

    # ---------------------------------------------------------
    # 3. Column generation iterations
    # ---------------------------------------------------------
    for iteration in range(1, max_iterations + 1):
        progress(
            f"Iteration {iteration}/{max_iterations}: "
            f"pricing {len(columns):,} existing columns"
        )

        # Check whether artificial variables still remain.
        remaining_artificials = [
            flight_id
            for flight_id, value
            in master_result.artificial_values.items()
            if value > ARTIFICIAL_TOLERANCE
        ]

        # If artificials remain, allow several randomized
        # pricing attempts before giving up.
        # If no artificials remain, one empty pricing attempt
        # is enough to stop.
        max_pricing_attempts = (
            MAX_EMPTY_PRICING_ATTEMPTS
            if remaining_artificials
            else 1
        )

        new_pairings = {}

        # -----------------------------------------------------
        # Pricing retries
        # -----------------------------------------------------
        for attempt in range(1, max_pricing_attempts + 1):
            progress(
                f"Iteration {iteration}: "
                f"pricing attempt "
                f"{attempt}/{max_pricing_attempts}"
            )

            new_pairings = generate_pricing_pairings(
                graph,
                master_result.duals,
                existing_pairing_signature,
                rng=rng,
                cost_function=cost_function,
            )

            # Pricing succeeded.
            if new_pairings:
                break

            progress(
                f"Iteration {iteration}: "
                f"pricing attempt "
                f"{attempt}/{max_pricing_attempts} "
                "found no new pairings"
            )

        # -----------------------------------------------------
        # No pricing attempt found a new column
        # -----------------------------------------------------
        if not new_pairings:
            if remaining_artificials:
                progress(
                    f"Iteration {iteration}: "
                    f"no improving pairings after "
                    f"{max_pricing_attempts} randomized attempts; "
                    f"{len(remaining_artificials)} "
                    "artificial variables still remain"
                )
            else:
                progress(
                    f"Iteration {iteration}: "
                    "no improving pairings and "
                    "no artificial variables remain"
                )

            return columns, master_result

        # -----------------------------------------------------
        # 4. Add new columns
        # -----------------------------------------------------
        progress(
            f"Iteration {iteration}: "
            f"found {len(new_pairings):,} new pairings"
        )

        for pairing in new_pairings.values():
            pairing_id = f"P{len(columns) + 1}"
            columns[pairing_id] = replace(pairing, pairing_id=pairing_id)

        # -----------------------------------------------------
        # 5. Re-solve restricted master LP
        # -----------------------------------------------------
        progress(
            f"Iteration {iteration}: "
            f"solving master LP with "
            f"{len(columns):,} columns"
        )

        master_result = solve_master_lp(
            columns,
            flights,
            cost_function,
        )

        progress(
            f"Iteration {iteration}: "
            f"master LP objective "
            f"{master_result.objective:,.2f}"
        )

    # ---------------------------------------------------------
    # Maximum number of CG iterations reached
    # ---------------------------------------------------------
    progress(
        f"Reached column generation iteration limit "
        f"({max_iterations})"
    )

    return columns, master_result
