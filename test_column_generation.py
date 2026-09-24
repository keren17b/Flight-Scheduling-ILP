"""Tests for the shared pairing-signature set in column generation."""

from __future__ import annotations

from datetime import datetime, timedelta
import unittest

from duties import Duty
from flights_graph import Airport, Flight
from column_generation import run_column_generation
from pairing_pricing import pairing_signature


class ColumnGenerationTests(unittest.TestCase):
    def test_shared_set_starts_from_initial_pairings_and_grows(self) -> None:
        base = Airport("BASE", 1)
        departure = datetime(2026, 9, 1, 8)
        duties = []
        flights = {}
        for index in range(2):
            flight = Flight(
                f"F{index}",
                base,
                base,
                departure,
                departure + timedelta(hours=1),
            )
            flights[flight.flight_id] = flight
            duties.append(
                Duty(
                    duty_id=f"D{index}",
                    flights=(flight,),
                    flight_time=timedelta(hours=1),
                    sitting_time=timedelta(0),
                    total_time=timedelta(hours=1),
                )
            )
        graph = {duty: [] for duty in duties}

        columns, existing_pairing_signature, _master = run_column_generation(
            graph,
            flights,
            cost_function=lambda pairing: 1.0,
            max_initial_pairings=1,
        )

        self.assertEqual(
            existing_pairing_signature,
            {pairing_signature(pairing.duties) for pairing in columns.values()},
        )
        self.assertEqual(existing_pairing_signature, {("D0",), ("D1",)})
        self.assertEqual(len(columns), 2)


if __name__ == "__main__":
    unittest.main()
