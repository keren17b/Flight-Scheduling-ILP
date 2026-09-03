"""Focused regression tests for duty, pairing, and cost time calculations."""

from datetime import datetime, timedelta
import unittest

from duties import Duty, generate_duties
from flights_graph import Airport, Flight
from pairing_cost import current_pairing_cost
from pairing_to_metrix import pairings_to_matrix
from pairings import generate_pairings


class TimeAndCostTests(unittest.TestCase):
    def setUp(self) -> None:
        self.base = Airport("BASE", 1)
        self.connection = Airport("CONNECTION", 0)
        self.outstation = Airport("OUTSTATION", 0)

        self.first_flight = Flight(
            "F1",
            self.base,
            self.connection,
            datetime(2026, 9, 1, 8),
            datetime(2026, 9, 1, 10),
        )
        self.second_flight = Flight(
            "F2",
            self.connection,
            self.outstation,
            datetime(2026, 9, 1, 11),
            datetime(2026, 9, 1, 12),
        )
        self.return_flight = Flight(
            "F3",
            self.outstation,
            self.base,
            datetime(2026, 9, 2, 0),
            datetime(2026, 9, 2, 2),
        )

    def test_generated_duty_separates_flight_and_sitting_time(self) -> None:
        graph = {
            self.first_flight: [self.second_flight],
            self.second_flight: [],
        }

        duty = next(
            duty for duty in generate_duties(graph).values() if len(duty.flights) == 2
        )

        self.assertEqual(duty.flight_time, timedelta(hours=3))
        self.assertEqual(duty.sitting_time, timedelta(hours=1))
        self.assertEqual(duty.total_time, timedelta(hours=4))

    def test_pairing_components_default_cost_and_replacement_cost(self) -> None:
        outbound_duty = Duty(
            duty_id="D1",
            flights=(self.first_flight, self.second_flight),
            flight_time=timedelta(hours=3),
            sitting_time=timedelta(hours=1),
            total_time=timedelta(hours=4),
        )
        return_duty = Duty(
            duty_id="D2",
            flights=(self.return_flight,),
            flight_time=timedelta(hours=2),
            sitting_time=timedelta(0),
            total_time=timedelta(hours=2),
        )
        pairings = generate_pairings(
            {
                outbound_duty: [return_duty],
                return_duty: [],
            }
        )
        pairing = next(iter(pairings.values()))

        self.assertEqual(pairing.flight_time, timedelta(hours=5))
        self.assertEqual(pairing.sitting_time, timedelta(hours=1))
        self.assertEqual(pairing.rest, timedelta(hours=12))
        self.assertEqual(pairing.total_time, timedelta(hours=18))
        self.assertEqual(current_pairing_cost(pairing), 13.0)

        flights = {
            flight.flight_id: flight
            for flight in (
                self.first_flight,
                self.second_flight,
                self.return_flight,
            )
        }
        matrix, default_costs = pairings_to_matrix(flights, pairings)
        _, flight_time_costs = pairings_to_matrix(
            flights,
            pairings,
            cost_function=lambda selected_pairing: (
                selected_pairing.flight_time.total_seconds() / 3600
            ),
        )

        self.assertEqual(matrix.tolist(), [[1, 1, 1]])
        self.assertEqual(default_costs, [13.0])
        self.assertEqual(flight_time_costs, [5.0])


if __name__ == "__main__":
    unittest.main()
