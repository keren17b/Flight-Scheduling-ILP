"""Compare label reachability with exhaustive paths on small graphs."""

from datetime import datetime, timedelta
import random
import unittest

from diagnostics.diagnose_instance_coverage import closed_pairing_duties, is_required_for_week
from crew_pairing.duties import Duty
from crew_pairing.flights_graph import Airport, Flight


START = datetime(2000, 1, 15)
A, B, X = Airport("A", 1), Airport("B", 1), Airport("X", 0)


def duty(index, origin, destination, start_hours, end_hours):
    start, end = START + timedelta(hours=start_hours), START + timedelta(hours=end_hours)
    flight = Flight(f"F{index}", origin, destination, start, end)
    return Duty(f"D{index}", (flight,), end - start, end - start, timedelta())


def enumerate_membership(duties, limit, span, min_rest, max_rest):
    covered = set()

    def visit(path):
        first, last = duties[path[0]], duties[path[-1]]
        if last.end_airport.port_name == first.start_airport.port_name:
            covered.update(path)
        if len(path) == limit:
            return
        for index, candidate in enumerate(duties):
            rest = candidate.start_time - last.end_time
            if (
                last.end_airport.port_name == candidate.start_airport.port_name
                and min_rest <= rest <= max_rest
                and candidate.end_time - first.start_time <= span
            ):
                visit(path + [index])

    for index, first in enumerate(duties):
        if first.start_airport.is_crew_base and first.total_time <= span:
            visit([index])
    return covered


class CoverageTests(unittest.TestCase):
    def test_week2_classification_is_independent_of_active_week3_config(self):
        for day in range(5, 18):
            flight = Flight(str(day), A, X, datetime(2000, 1, day, 8), datetime(2000, 1, day, 9))
            self.assertEqual(is_required_for_week(flight, 2), 8 <= day <= 14)
            self.assertEqual(is_required_for_week(flight, 3), 15 <= day <= 21)

    def compare(self, duties, limit=5, span=timedelta(days=5)):
        low, high = timedelta(hours=10), timedelta(hours=48)
        mask, witnesses = closed_pairing_duties(duties, limit, span, low, high)
        expected = enumerate_membership(duties, limit, span, low, high)
        self.assertEqual({i for i, value in enumerate(mask) if value}, expected)
        self.assertEqual(set(witnesses), expected)
        for index, path in witnesses.items():
            self.assertIn(index, path)
            self.assertLessEqual(len(path), limit)
            self.assertTrue(duties[path[0]].start_airport.is_crew_base)
            self.assertEqual(duties[path[0]].start_airport, duties[path[-1]].end_airport)
            self.assertLessEqual(duties[path[-1]].end_time - duties[path[0]].start_time, span)
            for first, second in zip(path, path[1:]):
                self.assertEqual(duties[first].end_airport, duties[second].start_airport)
                self.assertTrue(low <= duties[second].start_time - duties[first].end_time <= high)
        return expected

    def test_rest_and_elapsed_boundaries(self):
        first = duty(0, A, X, 0, 1)
        self.assertEqual(self.compare([first, duty(1, X, A, 11 - 1 / 60, 12)]), set())
        self.assertEqual(self.compare([first, duty(1, X, A, 11, 12)], span=timedelta(hours=12)), {0, 1})
        self.assertEqual(self.compare([first, duty(1, X, A, 11, 12 + 1 / 60)], span=timedelta(hours=12)), set())
        self.assertEqual(self.compare([first, duty(1, X, A, 49, 50)]), {0, 1})
        self.assertEqual(self.compare([first, duty(1, X, A, 49 + 1 / 60, 50)]), set())

    def test_base_and_duty_count(self):
        self.assertEqual(self.compare([duty(0, A, X, 0, 1), duty(1, X, B, 11, 12)]), set())
        path = [duty(0, A, X, 0, 1), duty(1, X, A, 11, 12)]
        self.assertEqual(self.compare(path, limit=1), set())
        self.assertEqual(self.compare(path, limit=2), {0, 1})

    def test_random_graphs_match_exhaustive_paths(self):
        for seed in range(80):
            rng = random.Random(seed)
            duties = []
            for index in range(18):
                start = rng.randrange(0, 144)
                duties.append(duty(index, rng.choice([A, B, X]), rng.choice([A, B, X]), start, start + rng.randrange(1, 5)))
            with self.subTest(seed=seed):
                self.compare(duties, limit=rng.randrange(1, 6), span=timedelta(hours=rng.randrange(12, 121)))


if __name__ == "__main__":
    unittest.main()
