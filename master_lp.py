"""Restricted Master LP for column generation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple

from mosek.fusion import Model, Domain, Expr, ObjectiveSense

from flights_graph import Flight
from padding_flights import PADDING_TAG, REQUIRED_TAG, flight_constraint_tags
from pairing_cost import PairingCostFunction, current_pairing_cost
from pairings import Pairing


ARTIFICIAL_COST = 1_000_000.0


@dataclass(frozen=True)
class MasterLpResult:
    pairing_values: Dict[str, float]
    duals: Dict[str, float]
    objective: float
    artificial_values: Dict[str, float]


def _pairing_flight_ids(pairing: Pairing) -> List[str]:
    return [
        flight.flight_id
        for duty in pairing.duties
        for flight in duty.flights
    ]


def _coverage_index(
    pairings: Dict[str, Pairing],
    flight_ids: List[str],
    cost_function: PairingCostFunction,
) -> Tuple[List[str], List[float], Dict[str, List[int]]]:
    pairing_ids = list(pairings.keys())
    known_flights = set(flight_ids)
    covering = {flight_id: [] for flight_id in flight_ids}
    costs: List[float] = []

    for pairing_index, pairing in enumerate(pairings.values()):
        costs.append(cost_function(pairing))
        for flight_id in _pairing_flight_ids(pairing):
            if flight_id in known_flights:
                covering[flight_id].append(pairing_index)

    return pairing_ids, costs, covering


def solve_master_lp(
    pairings: Dict[str, Pairing],
    flights: Dict[str, Flight],
    cost_function: PairingCostFunction = current_pairing_cost,
) -> MasterLpResult:
    """
    Solve the restricted master as a continuous LP.

    Required flights are covered exactly once, with an artificial variable
    on each required constraint. Padding flights are covered at most once.
    """
    flight_ids = list(flights.keys())
    flight_tags = flight_constraint_tags(flights)
    pairing_ids, costs, covering = _coverage_index(
        pairings,
        flight_ids,
        cost_function,
    )

    required_ids = [
        flight_id
        for flight_id, tag in zip(flight_ids, flight_tags)
        if tag == REQUIRED_TAG
    ]
    artificial_index = {
        flight_id: index for index, flight_id in enumerate(required_ids)
    }

    with Model("restricted_master_lp") as M:
        x = M.variable("x", len(pairing_ids), Domain.inRange(0.0, 1.0))
        a = M.variable("artificial", len(required_ids), Domain.inRange(0.0, 1.0))

        M.objective(
            "minimize_cost",
            ObjectiveSense.Minimize,
            Expr.add(
                Expr.dot(costs, x),
                Expr.mul(ARTIFICIAL_COST, Expr.sum(a)),
            ),
        )

        flight_constraints = {}
        for flight_id, tag in zip(flight_ids, flight_tags):
            covering_indices = covering[flight_id]
            if covering_indices:
                coverage = Expr.sum(x.pick(covering_indices))
            else:
                coverage = Expr.constTerm(0.0)

            if tag == PADDING_TAG:
                flight_constraints[flight_id] = M.constraint(
                    f"flight_{flight_id}_{PADDING_TAG}",
                    coverage,
                    Domain.lessThan(1.0),
                )
                continue

            flight_constraints[flight_id] = M.constraint(
                f"flight_{flight_id}_covered_once",
                Expr.add(coverage, a.index(artificial_index[flight_id])),
                Domain.equalsTo(1.0),
            )

        M.solve()

        x_level = x.level()
        pairing_values = {
            pairing_id: float(x_level[index])
            for index, pairing_id in enumerate(pairing_ids)
        }

        a_level = a.level()
        artificial_values = {
            flight_id: float(a_level[index])
            for flight_id, index in artificial_index.items()
        }

        duals = {
            flight_id: float(constraint.dual()[0])
            for flight_id, constraint in flight_constraints.items()
        }

        return MasterLpResult(
            pairing_values=pairing_values,
            duals=duals,
            objective=float(M.primalObjValue()),
            artificial_values=artificial_values,
        )
