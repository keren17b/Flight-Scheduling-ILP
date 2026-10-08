"""Regression tests for padding on both sides of the required week."""

from datetime import datetime, timedelta
import random
import unittest

from column_generation.config import FLIGHTS_FILE_PATH, HUBS_FILE_PATH
from column_generation.initial_pool import generate_initial_pairings
from column_generation.pairing_pricing import generate_pricing_pairings
from crew_pairing.duties import generate_duties
from crew_pairing.duty_graph import build_duty_graph
from crew_pairing.flights_graph import Airport, Flight, build_flight_graph, load_flights
from crew_pairing.padding_flights import (
    PADDING_TAG, REQUIRED_TAG, flight_constraint_tags, is_padding_flight,
)
from crew_pairing.pairings import generate_pairings


class PaddingFlightTests(unittest.TestCase):
    def _flight(self, flight_id, day, origin, destination):
        departure = datetime(2000, 1, day, 8)
        return Flight(flight_id, origin, destination, departure,
                      departure + timedelta(hours=1))

    def test_inclusive_boundaries_and_required_gap(self):
        base = Airport("BASE", 1)
        for day in range(11, 26):
            with self.subTest(day=day):
                flight = self._flight(str(day), day, base, base)
                self.assertEqual(is_padding_flight(flight), day in (12, 13, 14, 22, 23, 24))

    def test_active_dataset_tags_preserve_flight_order(self):
        _, flights = load_flights(FLIGHTS_FILE_PATH, HUBS_FILE_PATH)
        self.assertEqual(FLIGHTS_FILE_PATH.name, "week_3_with_start_end_padding.csv")
        self.assertEqual(len(flights), 428)
        tags = flight_constraint_tags(flights)
        self.assertEqual(tags.count(REQUIRED_TAG), 227)
        self.assertEqual(tags.count(PADDING_TAG), 201)
        for flight, tag in zip(flights.values(), tags):
            required = 15 <= flight.departure_datetime.day <= 21
            self.assertEqual(tag, REQUIRED_TAG if required else PADDING_TAG)

    def test_pairing_searches_can_use_start_and_end_padding(self):
        base, away = Airport("BASE", 1), Airport("AWAY", 0)
        for first_day, second_day, required_id in ((14, 15, "RETURN"), (21, 22, "OUT")):
            with self.subTest(days=(first_day, second_day)):
                outbound = self._flight("OUT", first_day, base, away)
                inbound = self._flight("RETURN", second_day, away, base)
                flights = {"OUT": outbound, "RETURN": inbound}
                duties = generate_duties(build_flight_graph(flights.values()))
                graph = build_duty_graph(duties.values())
                initial, coverage, _ = generate_initial_pairings(graph, flights)
                self.assertEqual(coverage, {required_id: 1})
                exhaustive = generate_pairings(graph)
                priced, _ = generate_pricing_pairings(
                    graph,
                    {key: 100.0 if key == required_id else 0.0 for key in flights},
                    set(), rng=random.Random(42),
                )
                for pool in (initial, exhaustive, priced):
                    self.assertEqual(len(pool), 1)
                    pairing = next(iter(pool.values()))
                    self.assertEqual(
                        [flight.flight_id for duty in pairing.duties for flight in duty.flights],
                        ["OUT", "RETURN"],
                    )


if __name__ == "__main__":
    unittest.main()
