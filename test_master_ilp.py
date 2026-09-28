"""Tests for the final binary ILP on generated pairing columns."""

from __future__ import annotations

from datetime import datetime, timedelta
import unittest

from duties import Duty
from flights_graph import Airport, Flight
from master_ilp import solve_ilp
from pairings import Pairing


SOLVER_TOLERANCE = 1e-5


class MasterIlpTests(unittest.TestCase):
    def setUp(self) -> None:
        self.base = Airport("BASE", 1)
        self.outstation = Airport("OUTSTATION", 0)
        self.required_departure = datetime(2026, 9, 1, 8)
        self.padding_departure = datetime(2000, 1, 8, 8)

    def _flight(self, flight_id: str, padding: bool = False) -> Flight:
        departure = self.padding_departure if padding else self.required_departure
        return Flight(
            flight_id,
            self.base,
            self.outstation,
            departure,
            departure + timedelta(hours=1),
        )

    def _pairing(self, pairing_id: str, flights: tuple[Flight, ...]) -> Pairing:
        duty_time = timedelta(hours=len(flights))
        duty = Duty(
            duty_id=f"D-{pairing_id}",
            flights=flights,
            flight_time=duty_time,
            sitting_time=timedelta(0),
            total_time=duty_time,
        )
        return Pairing(
            pairing_id=pairing_id,
            duties=(duty,),
            total_time=duty_time,
            flight_time=duty_time,
            sitting_time=timedelta(0),
            rest=timedelta(0),
        )

    def _costs(self, costs_by_id: dict[str, float]):
        return lambda pairing: costs_by_id[pairing.pairing_id]

    def test_covering_pairings_are_selected(self) -> None:
        first = self._flight("F1")
        second = self._flight("F2")
        pairings = {
            "P1": self._pairing("P1", (first,)),
            "P2": self._pairing("P2", (second,)),
        }
        flights = {"F1": first, "F2": second}

        solution, total_cost = solve_ilp(
            pairings,
            flights,
            cost_function=self._costs({"P1": 5.0, "P2": 7.0}),
        )

        self.assertAlmostEqual(solution["P1"], 1.0, delta=SOLVER_TOLERANCE)
        self.assertAlmostEqual(solution["P2"], 1.0, delta=SOLVER_TOLERANCE)
        self.assertAlmostEqual(total_cost, 12.0, delta=SOLVER_TOLERANCE)

    def test_cheaper_covering_pairing_is_preferred(self) -> None:
        first = self._flight("F1")
        second = self._flight("F2")
        pairings = {
            "P_cheap": self._pairing("P_cheap", (first, second)),
            "P_expensive": self._pairing("P_expensive", (first, second)),
        }
        flights = {"F1": first, "F2": second}

        solution, total_cost = solve_ilp(
            pairings,
            flights,
            cost_function=self._costs({"P_cheap": 3.0, "P_expensive": 9.0}),
        )

        self.assertAlmostEqual(solution["P_cheap"], 1.0, delta=SOLVER_TOLERANCE)
        self.assertAlmostEqual(solution["P_expensive"], 0.0, delta=SOLVER_TOLERANCE)
        self.assertAlmostEqual(total_cost, 3.0, delta=SOLVER_TOLERANCE)

    def test_padding_flight_need_not_be_covered(self) -> None:
        required = self._flight("F1")
        padding = self._flight("F2", padding=True)
        pairings = {"P1": self._pairing("P1", (required,))}
        flights = {"F1": required, "F2": padding}

        solution, total_cost = solve_ilp(
            pairings,
            flights,
            cost_function=self._costs({"P1": 5.0}),
        )

        self.assertAlmostEqual(solution["P1"], 1.0, delta=SOLVER_TOLERANCE)
        self.assertAlmostEqual(total_cost, 5.0, delta=SOLVER_TOLERANCE)

    def test_integer_cover_when_pairings_overlap(self) -> None:
        first = self._flight("F1")
        second = self._flight("F2")
        third = self._flight("F3")
        pairings = {
            "P1": self._pairing("P1", (first, second)),
            "P2": self._pairing("P2", (third,)),
            "P3": self._pairing("P3", (first, third)),
        }
        flights = {"F1": first, "F2": second, "F3": third}

        solution, total_cost = solve_ilp(
            pairings,
            flights,
            cost_function=self._costs({"P1": 10.0, "P2": 4.0, "P3": 10.0}),
        )

        self.assertAlmostEqual(solution["P1"], 1.0, delta=SOLVER_TOLERANCE)
        self.assertAlmostEqual(solution["P2"], 1.0, delta=SOLVER_TOLERANCE)
        self.assertAlmostEqual(solution["P3"], 0.0, delta=SOLVER_TOLERANCE)
        self.assertAlmostEqual(total_cost, 14.0, delta=SOLVER_TOLERANCE)


if __name__ == "__main__":
    unittest.main()
