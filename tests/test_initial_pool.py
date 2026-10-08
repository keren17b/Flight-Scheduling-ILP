"""Tests for the bounded initial pairing pool."""

from __future__ import annotations

from datetime import datetime, timedelta
import unittest

from column_generation.initial_pool import generate_initial_pairings
from crew_pairing.duties import Duty
from crew_pairing.flights_graph import Airport, Flight


class InitialPoolTests(unittest.TestCase):
    def setUp(self) -> None:
        self.base = Airport("BASE", 1)
        self.required_departure = datetime(2000, 1, 15, 8)
        self.padding_departure = datetime(2000, 1, 12, 8)

    def _flight(
        self,
        flight_id: str,
        *,
        padding: bool = False,
        hour: int = 8,
    ) -> Flight:
        departure = (
            self.padding_departure.replace(hour=hour)
            if padding
            else self.required_departure.replace(hour=hour)
        )
        return Flight(
            flight_id,
            self.base,
            self.base,
            departure,
            departure + timedelta(hours=1),
        )

    def _duty(self, duty_id: str, flight: Flight) -> Duty:
        return Duty(
            duty_id=duty_id,
            flights=(flight,),
            flight_time=timedelta(hours=1),
            sitting_time=timedelta(0),
            total_time=timedelta(hours=1),
        )

    def test_padding_flights_do_not_count_toward_coverage(self) -> None:
        required = self._flight("F_REQUIRED")
        padding = self._flight("F_PADDING", padding=True)
        required_duty = self._duty("D_REQUIRED", required)
        padding_duty = self._duty("D_PADDING", padding)
        graph = {required_duty: [], padding_duty: []}
        flights = {required.flight_id: required, padding.flight_id: padding}

        pairings, coverage_count, signatures = generate_initial_pairings(graph, flights)

        self.assertIn("F_REQUIRED", coverage_count)
        self.assertNotIn("F_PADDING", coverage_count)
        self.assertGreaterEqual(coverage_count["F_REQUIRED"], 1)
        self.assertIn(("D_REQUIRED",), signatures)
        self.assertTrue(pairings)

    def test_saves_up_to_three_pairings_per_required_flight(self) -> None:
        flight = self._flight("F1")
        duties = [self._duty(f"D{index}", flight) for index in range(5)]
        graph = {duty: [] for duty in duties}
        flights = {flight.flight_id: flight}

        pairings, coverage_count, signatures = generate_initial_pairings(
            graph,
            flights,
            min_cover_per_flight=3,
        )

        self.assertEqual(coverage_count["F1"], 3)
        self.assertEqual(len(pairings), 3)
        self.assertEqual(len(signatures), 3)

    def test_per_start_pairing_limit_is_independent(self) -> None:
        flights = {}
        duties = []
        for index in range(3):
            flight = self._flight(f"F{index}", hour=8 + index)
            flights[flight.flight_id] = flight
            duties.append(self._duty(f"D{index}", flight))
        graph = {duty: [] for duty in duties}

        pairings, coverage_count, _signatures = generate_initial_pairings(
            graph,
            flights,
            min_cover_per_flight=3,
            max_pairings=100,
            max_pairings_per_start=1,
            max_dfs_states_per_start=200,
        )

        self.assertEqual(len(pairings), 3)
        self.assertEqual(coverage_count["F0"], 1)
        self.assertEqual(coverage_count["F1"], 1)
        self.assertEqual(coverage_count["F2"], 1)

    def test_does_not_fail_when_required_flights_remain_uncovered(self) -> None:
        covered = self._flight("F_COVERED")
        uncovered = self._flight("F_UNCOVERED", hour=12)
        covered_duty = self._duty("D_COVERED", covered)
        graph = {covered_duty: []}
        flights = {
            covered.flight_id: covered,
            uncovered.flight_id: uncovered,
        }

        pairings, coverage_count, _signatures = generate_initial_pairings(
            graph,
            flights,
            min_cover_per_flight=3,
        )

        self.assertEqual(len(pairings), 1)
        self.assertEqual(coverage_count["F_COVERED"], 1)
        self.assertEqual(coverage_count["F_UNCOVERED"], 0)
