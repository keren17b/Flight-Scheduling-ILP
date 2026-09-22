"""Tests for the restricted master LP used in column generation."""

from __future__ import annotations

from datetime import datetime, timedelta
import unittest

from duties import Duty
from flights_graph import Airport, Flight
from master_lp import ARTIFICIAL_COST, solve_master_lp
from pairings import Pairing


SOLVER_TOLERANCE = 1e-5


class MasterLpTests(unittest.TestCase):
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

    def test_covering_pairings_zero_artificials(self) -> None:
        first = self._flight("F1")
        second = self._flight("F2")
        pairings = {
            "P1": self._pairing("P1", (first,)),
            "P2": self._pairing("P2", (second,)),
        }
        flights = {"F1": first, "F2": second}

        result = solve_master_lp(
            pairings,
            flights,
            cost_function=self._costs({"P1": 5.0, "P2": 7.0}),
        )

        self.assertAlmostEqual(result.pairing_values["P1"], 1.0, delta=SOLVER_TOLERANCE)
        self.assertAlmostEqual(result.pairing_values["P2"], 1.0, delta=SOLVER_TOLERANCE)
        self.assertAlmostEqual(result.artificial_values["F1"], 0.0, delta=SOLVER_TOLERANCE)
        self.assertAlmostEqual(result.artificial_values["F2"], 0.0, delta=SOLVER_TOLERANCE)
        self.assertAlmostEqual(result.objective, 12.0, delta=SOLVER_TOLERANCE)
        self.assertEqual(set(result.duals), {"F1", "F2"})

    def test_uncovered_required_flight_uses_artificial(self) -> None:
        first = self._flight("F1")
        second = self._flight("F2")
        pairings = {"P1": self._pairing("P1", (first,))}
        flights = {"F1": first, "F2": second}

        result = solve_master_lp(
            pairings,
            flights,
            cost_function=self._costs({"P1": 5.0}),
        )

        self.assertAlmostEqual(result.pairing_values["P1"], 1.0, delta=SOLVER_TOLERANCE)
        self.assertAlmostEqual(result.artificial_values["F1"], 0.0, delta=SOLVER_TOLERANCE)
        self.assertAlmostEqual(result.artificial_values["F2"], 1.0, delta=SOLVER_TOLERANCE)
        self.assertAlmostEqual(
            result.objective,
            5.0 + ARTIFICIAL_COST,
            delta=SOLVER_TOLERANCE,
        )

    def test_padding_flight_has_no_artificial(self) -> None:
        required = self._flight("F1")
        padding = self._flight("F2", padding=True)
        pairings = {"P1": self._pairing("P1", (required,))}
        flights = {"F1": required, "F2": padding}

        result = solve_master_lp(
            pairings,
            flights,
            cost_function=self._costs({"P1": 5.0}),
        )

        self.assertIn("F1", result.artificial_values)
        self.assertNotIn("F2", result.artificial_values)
        self.assertEqual(set(result.duals), {"F1", "F2"})
        self.assertAlmostEqual(result.artificial_values["F1"], 0.0, delta=SOLVER_TOLERANCE)
        self.assertAlmostEqual(result.pairing_values["P1"], 1.0, delta=SOLVER_TOLERANCE)
        self.assertAlmostEqual(result.objective, 5.0, delta=SOLVER_TOLERANCE)

    def test_fractional_cover_when_pairings_overlap(self) -> None:
        first = self._flight("F1")
        second = self._flight("F2")
        third = self._flight("F3")
        pairings = {
            "P1": self._pairing("P1", (first, second)),
            "P2": self._pairing("P2", (second, third)),
            "P3": self._pairing("P3", (first, third)),
        }
        flights = {"F1": first, "F2": second, "F3": third}
        costs = {"P1": 10.0, "P2": 10.0, "P3": 10.0}

        result = solve_master_lp(
            pairings,
            flights,
            cost_function=self._costs(costs),
        )

        self.assertAlmostEqual(result.pairing_values["P1"], 0.5, delta=SOLVER_TOLERANCE)
        self.assertAlmostEqual(result.pairing_values["P2"], 0.5, delta=SOLVER_TOLERANCE)
        self.assertAlmostEqual(result.pairing_values["P3"], 0.5, delta=SOLVER_TOLERANCE)
        self.assertAlmostEqual(result.artificial_values["F1"], 0.0, delta=SOLVER_TOLERANCE)
        self.assertAlmostEqual(result.artificial_values["F2"], 0.0, delta=SOLVER_TOLERANCE)
        self.assertAlmostEqual(result.artificial_values["F3"], 0.0, delta=SOLVER_TOLERANCE)
        self.assertAlmostEqual(result.objective, 15.0, delta=SOLVER_TOLERANCE)

    def test_cheaper_covering_pairing_is_preferred(self) -> None:
        first = self._flight("F1")
        second = self._flight("F2")
        pairings = {
            "P_cheap": self._pairing("P_cheap", (first, second)),
            "P_expensive": self._pairing("P_expensive", (first, second)),
        }
        flights = {"F1": first, "F2": second}

        result = solve_master_lp(
            pairings,
            flights,
            cost_function=self._costs({"P_cheap": 3.0, "P_expensive": 9.0}),
        )

        self.assertAlmostEqual(
            result.pairing_values["P_cheap"],
            1.0,
            delta=SOLVER_TOLERANCE,
        )
        self.assertAlmostEqual(
            result.pairing_values["P_expensive"],
            0.0,
            delta=SOLVER_TOLERANCE,
        )
        self.assertAlmostEqual(result.objective, 3.0, delta=SOLVER_TOLERANCE)


if __name__ == "__main__":
    unittest.main()
