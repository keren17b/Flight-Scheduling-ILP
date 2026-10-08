"""Final binary ILP on the pairing columns produced by column generation."""

from __future__ import annotations

from typing import Dict, Tuple

from mosek.fusion import Model, Domain, Expr, ObjectiveSense, ProblemStatus, SolutionStatus, AccSolutionStatus

from crew_pairing.flights_graph import Flight
from column_generation.config import SELECTION_THRESHOLD
from column_generation.master_lp import _coverage_index
from crew_pairing.padding_flights import PADDING_TAG, flight_constraint_tags
from crew_pairing.pairing_cost import PairingCostFunction, current_pairing_cost
from crew_pairing.pairings import Pairing
from run_progress import progress


def solve_ilp(
    pairings: Dict[str, Pairing],
    flights: Dict[str, Flight],
    cost_function: PairingCostFunction = current_pairing_cost,
) -> Tuple[Dict[str, float], float] | None:
    """
    Select a minimum-cost set of pairings with binary variables.

    Required flights are covered exactly once. Padding flights are covered
    at most once. Coverage is built from flight IDs inside each pairing;
    the dense pairing-flight matrix is not built.
    Return None if the currently generated pairing pool is integer-infeasible.
    """
    flight_ids = list(flights.keys())
    progress(f"Building final ILP coverage for {len(pairings):,} pairings and {len(flights):,} flights")
    flight_tags = flight_constraint_tags(flights)
    pairing_ids, costs, covering = _coverage_index(
        pairings,
        flight_ids,
        cost_function,
    )

    with Model("master_ilp") as M:
        x = M.variable("x", len(pairing_ids), Domain.binary())

        M.objective(
            "minimize_cost",
            ObjectiveSense.Minimize,
            Expr.dot(costs, x),
        )

        for flight_id, tag in zip(flight_ids, flight_tags):
            covering_indices = covering[flight_id]
            if covering_indices:
                coverage = Expr.sum(x.pick(covering_indices))
            else:
                coverage = Expr.constTerm(0.0)

            if tag == PADDING_TAG:
                M.constraint(
                    f"flight_{flight_id}_{PADDING_TAG}",
                    coverage,
                    Domain.lessThan(1.0),
                )
            else:
                M.constraint(
                    f"flight_{flight_id}_covered_once",
                    coverage,
                    Domain.equalsTo(1.0),
                )

        progress("MOSEK: solving final ILP")
        M.solve()
        progress("MOSEK: final ILP solve finished")
        problem_status = M.getProblemStatus()
        solution_status = M.getPrimalSolutionStatus()
        if problem_status == ProblemStatus.PrimalInfeasible:
            print(
                "No binary feasible solution exists within the currently "
                "generated pairing pool."
            )
            return None
        if solution_status not in (SolutionStatus.Optimal, SolutionStatus.Feasible):
            raise RuntimeError(f"No valid ILP solution: {solution_status}")

        M.acceptedSolutionStatus(AccSolutionStatus.Feasible)

        solution_level = x.level()

        total_cost = 0.0
        solution: Dict[str, float] = {}
        for index, pairing_id in enumerate(pairing_ids):
            value = float(solution_level[index])
            solution[pairing_id] = value
            if value > SELECTION_THRESHOLD:
                total_cost += costs[index]

        return solution, total_cost
