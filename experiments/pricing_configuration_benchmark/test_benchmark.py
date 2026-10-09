"""Regression checks for the restored benchmark using small real MOSEK solves."""

import contextlib
from datetime import datetime, timedelta
import io
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import benchmark_pricing_configuration as benchmark
from crew_pairing.duties import Duty
from crew_pairing.flights_graph import Airport, Flight
from crew_pairing.pairings import build_pairing_from_path, pairing_signature


class BenchmarkTests(unittest.TestCase):
    def setUp(self):
        base, away = Airport("AAA", 1), Airport("BBB", 0)
        self.duties = []
        for day, label in enumerate(("A", "B", "C"), start=15):
            start = datetime(2000, 1, day, 9)
            flights = (
                Flight(label + "_out", base, away, start, start + timedelta(hours=1)),
                Flight(label + "_back", away, base, start + timedelta(hours=2),
                       start + timedelta(hours=3)),
            )
            self.duties.append(Duty(label, flights, timedelta(hours=3),
                                    timedelta(hours=2), timedelta(hours=1)))
        self.flights = {f.flight_id: f for d in self.duties for f in d.flights}
        a, b, c = self.duties
        self.graph = {a: [b, c], b: [c], c: []}
        self.config = benchmark.PricingConfig("small", 20, 500, 100, 2, 500)

    def run_config(self, columns, signatures, master, **kwargs):
        rows = []
        with contextlib.redirect_stdout(io.StringIO()):
            result = benchmark.run_one_configuration(
                self.config, columns, signatures, master, self.flights,
                self.graph, rows, **kwargs,
            )
        return result, rows

    def test_pricing_reaches_binary_feasibility_and_preserves_shared_inputs(self):
        a = self.duties[0]
        columns = {"P1": build_pairing_from_path("P1", [a])}
        signatures = {pairing_signature([a])}
        master = benchmark.solve_master_lp(columns, self.flights)
        first, rows = self.run_config(columns, signatures, master, max_iterations=10)
        second, repeated = self.run_config(columns, signatures, master, max_iterations=10)
        self.assertTrue(first.reached_zero_artificials)
        self.assertTrue(first.final_ilp_succeeded)
        self.assertGreater(first.total_columns_added, 0)
        self.assertIsNone(first.final_ilp_error)
        self.assertEqual(list(columns), ["P1"])
        self.assertEqual(signatures, {pairing_signature([a])})
        self.assertEqual(first.final_columns, second.final_columns)
        self.assertAlmostEqual(first.final_ilp_cost, second.final_ilp_cost)
        self.assertEqual([r["new_columns"] for r in rows],
                         [r["new_columns"] for r in repeated])

    def test_fractionally_feasible_triangle_records_integer_infeasibility(self):
        a, b, c = self.duties
        paths = ([a, b], [a, c], [b, c])
        columns = {f"P{i}": build_pairing_from_path(f"P{i}", path)
                   for i, path in enumerate(paths, start=1)}
        signatures = {pairing_signature(path) for path in paths}
        master = benchmark.solve_master_lp(columns, self.flights)
        result, rows = self.run_config(columns, signatures, master)
        self.assertTrue(result.reached_zero_artificials)
        self.assertTrue(result.final_ilp_attempted)
        self.assertFalse(result.final_ilp_succeeded)
        self.assertEqual(result.final_ilp_error,
                         "Generated column pool is integer-infeasible")
        self.assertIsNone(result.final_ilp_cost)
        self.assertEqual(rows, [])

    def test_skip_final_ilp_does_not_call_binary_solver(self):
        columns = {f"P{i}": build_pairing_from_path(f"P{i}", [d])
                   for i, d in enumerate(self.duties, start=1)}
        signatures = {pairing_signature([d]) for d in self.duties}
        master = benchmark.solve_master_lp(columns, self.flights)
        with patch.object(benchmark, "solve_ilp") as solve:
            result, rows = self.run_config(columns, signatures, master, run_final_ilp=False)
        solve.assert_not_called()
        self.assertTrue(result.reached_zero_artificials)
        self.assertFalse(result.final_ilp_attempted)
        self.assertEqual(rows, [])

    def test_empty_pricing_retries_without_claiming_feasibility(self):
        a = self.duties[0]
        columns = {"P1": build_pairing_from_path("P1", [a])}
        signatures = {pairing_signature([a])}
        master = benchmark.solve_master_lp(columns, self.flights)
        # The missing flights have no duties in this restricted search graph.
        with patch.object(self, "graph", {a: []}), patch.object(
            benchmark, "generate_pricing_pairings", wraps=benchmark.generate_pricing_pairings
        ) as pricing:
            result, rows = self.run_config(columns, signatures, master)
        self.assertEqual(pricing.call_count, benchmark.MAX_EMPTY_PRICING_ATTEMPTS)
        self.assertFalse(result.reached_zero_artificials)
        self.assertFalse(result.final_ilp_attempted)
        self.assertEqual(result.final_artificials, 4)
        self.assertEqual(result.total_columns_added, 0)
        self.assertEqual(rows, [])


if __name__ == "__main__":
    unittest.main()
