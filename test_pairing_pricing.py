"""Tests for the pricing DFS."""

from __future__ import annotations

from datetime import datetime, timedelta
import unittest

from duties import Duty
from flights_graph import Airport, Flight
from pairing_pricing import generate_pricing_pairings


class PairingPricingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.base = Airport("BASE", 1)
        self.outstation = Airport("OUTSTATION", 0)
        self.departure = datetime(2026, 9, 1, 8)

    def _flight(self, flight_id: str, origin: Airport, destination: Airport) -> Flight:
        return Flight(
            flight_id,
            origin,
            destination,
            self.departure,
            self.departure + timedelta(hours=1),
        )

    def _closed_duty(self, duty_id: str, flight: Flight) -> Duty:
        return Duty(
            duty_id=duty_id,
            flights=(flight,),
            flight_time=timedelta(hours=1),
            sitting_time=timedelta(0),
            total_time=timedelta(hours=1),
        )

    def test_keeps_only_negative_reduced_cost(self) -> None:
        improving_flight = self._flight("F1", self.base, self.base)
        rejected_flight = self._flight("F2", self.base, self.base)
        improving = self._closed_duty("D1", improving_flight)
        rejected = self._closed_duty("D2", rejected_flight)
        graph = {improving: [], rejected: []}

        pairings, _existing_pairing_signature = generate_pricing_pairings(
            graph,
            {"F1": 5.0, "F2": 0.0},
            set(),
            cost_function=lambda pairing: 1.0,
        )

        self.assertEqual(list(pairings), ["P1"])
        self.assertEqual(pairings["P1"].duties, (improving,))

    def test_stops_at_max_pairings(self) -> None:
        duties = []
        duals = {}
        for index in range(3):
            flight = self._flight(f"F{index}", self.base, self.base)
            duties.append(self._closed_duty(f"D{index}", flight))
            duals[flight.flight_id] = 10.0
        graph = {duty: [] for duty in duties}

        pairings, _existing_pairing_signature = generate_pricing_pairings(
            graph,
            duals,
            set(),
            max_pairings=2,
            cost_function=lambda pairing: 1.0,
        )

        self.assertEqual(len(pairings), 2)
        self.assertEqual(
            [pairing.duties[0].duty_id for pairing in pairings.values()],
            ["D0", "D1"],
        )

    def test_requires_return_to_same_base(self) -> None:
        flight = self._flight("F1", self.base, self.outstation)
        duty = self._closed_duty("D1", flight)

        pairings, _existing_pairing_signature = generate_pricing_pairings(
            {duty: []},
            {"F1": 100.0},
            set(),
            cost_function=lambda pairing: 1.0,
        )

        self.assertEqual(pairings, {})

    def test_reduced_cost_uses_pairing_cost(self) -> None:
        first = Duty(
            duty_id="D1",
            flights=(self._flight("F1", self.base, self.outstation),),
            flight_time=timedelta(hours=1),
            sitting_time=timedelta(hours=1),
            total_time=timedelta(hours=2),
        )
        second_start = first.end_time + timedelta(hours=12)
        second = Duty(
            duty_id="D2",
            flights=(
                Flight(
                    "F2",
                    self.outstation,
                    self.base,
                    second_start,
                    second_start + timedelta(hours=1),
                ),
            ),
            flight_time=timedelta(hours=1),
            sitting_time=timedelta(0),
            total_time=timedelta(hours=1),
        )
        graph = {first: [second], second: []}

        improving, _existing_pairing_signature = generate_pricing_pairings(
            graph, {"F1": 10.0, "F2": 10.0}, set()
        )
        rejected, _existing_pairing_signature = generate_pricing_pairings(
            graph, {"F1": 1.0, "F2": 1.0}, set()
        )

        self.assertEqual(
            [duty.duty_id for duty in next(iter(improving.values())).duties],
            ["D1", "D2"],
        )
        self.assertEqual(rejected, {})

    def test_skips_pairings_already_in_existing_ids(self) -> None:
        first = self._closed_duty("D1", self._flight("F1", self.base, self.base))
        second = self._closed_duty("D2", self._flight("F2", self.base, self.base))
        graph = {first: [], second: []}
        duals = {"F1": 5.0, "F2": 5.0}
        existing_pairing_signature = {("D1",)}

        pairings, _existing_pairing_signature = generate_pricing_pairings(
            graph,
            duals,
            cost_function=lambda pairing: 1.0,
            existing_pairing_signature=existing_pairing_signature,
        )

        self.assertEqual(list(pairings), ["P1"])
        self.assertEqual(pairings["P1"].duties, (second,))
        self.assertEqual(existing_pairing_signature, {("D1",), ("D2",)})


if __name__ == "__main__":
    unittest.main()
