"""Focused checks for the independent bounded-pricing module."""

from __future__ import annotations

from datetime import datetime, timedelta
import inspect
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from column_generation import pairing_pricing_bounded as bounded
from crew_pairing.duties import Duty
from crew_pairing.flights_graph import Airport, Flight
from crew_pairing.pairings import build_pairing_from_path, pairing_signature


class BoundedPricingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.base = Airport("BASE", 1)
        self.outstation = Airport("OUT", 0)
        self.departure = datetime(2026, 9, 1, 8)
        clock = patch.object(bounded, "monotonic", return_value=0.0)
        self.clock = clock.start()
        self.addCleanup(clock.stop)
        messages = patch.object(bounded, "progress")
        self.messages = messages.start()
        self.addCleanup(messages.stop)

    def _duty(self, duty_id, origin=None, destination=None, departure=None, flight_id=None):
        departure = self.departure if departure is None else departure
        flight = Flight(
            duty_id if flight_id is None else flight_id,
            self.base if origin is None else origin,
            self.base if destination is None else destination,
            departure, departure + timedelta(hours=1),
        )
        return Duty(
            duty_id, (flight,), timedelta(hours=1), timedelta(hours=1), timedelta(0)
        )

    def _branches(self, starts=1, returns=3):
        graph = {}
        duals = {}
        for index in range(starts):
            first = self._duty(f"S{index}", destination=self.outstation)
            successors = [
                self._duty(
                    f"R{index}-{child}", origin=self.outstation,
                    departure=self.departure + timedelta(hours=12),
                )
                for child in range(returns)
            ]
            graph[first] = successors
            duals[first.duty_id] = 0.0
            duals.update({duty.duty_id: 10.0 + child for child, duty in enumerate(successors)})
        return graph, duals

    def test_requested_pricing_defaults_live_in_the_new_module(self) -> None:
        signature = inspect.signature(bounded.generate_pricing_pairings)
        for name, value in (
            ("max_dfs_states", 500_000),
            ("max_dfs_states_per_start", 1_000),
            ("max_candidates_per_start", 10),
            ("max_candidates", 500),
            ("max_pairings", 50),
            ("max_seconds", 30.0),
        ):
            with self.subTest(name=name):
                self.assertEqual(signature.parameters[name].default, value)

    def test_ranks_by_real_reduced_cost_and_updates_only_selected_signatures(self) -> None:
        duties = [self._duty(f"D{i}") for i in range(3)]
        duals = {duty.duty_id: 10.0 + i for i, duty in enumerate(duties)}
        costs = {"D0": 1.0, "D1": 0.0, "D2": 2.0}
        signatures = set()
        pairings, returned, report = bounded.generate_pricing_pairings(
            {duty: [] for duty in duties}, duals, signatures, max_pairings=2,
            cost_function=lambda pairing: costs[pairing.duties[0].duty_id],
        )
        self.assertIs(returned, signatures)
        self.assertEqual([p.duties[0].duty_id for p in pairings.values()], ["D1", "D2"])
        self.assertEqual(report.selected_reduced_costs, (-11.0, -10.0))
        self.assertEqual(signatures, {("D1",), ("D2",)})
        self.assertEqual(report.candidates_collected, 3)
        self.assertEqual(report.dfs_states, 3)
        self.assertFalse(report.truncated)
        self.assertEqual(report.termination_reason, "complete exploration")
        self.assertEqual([p.pairing_id for p in pairings.values()], ["P1", "P2"])

        remaining, _, _ = bounded.generate_pricing_pairings(
            {duty: [] for duty in duties}, duals, signatures,
            cost_function=lambda pairing: 1.0,
        )
        self.assertEqual(remaining["P1"].duties, (duties[0],))

    def test_global_limits_stop_all_starts_and_local_limits_continue_other_starts(self) -> None:
        graph, duals = self._branches(starts=3)
        for limits, reason, states, candidates in (
            ({"max_dfs_states": 2}, "global DFS state limit", 2, 1),
            ({"max_candidates": 1}, "global candidate limit", 2, 1),
            ({"max_dfs_states_per_start": 1}, "per-start DFS state limit", 3, 0),
            ({"max_candidates_per_start": 1}, "per-start candidate limit", 6, 3),
        ):
            with self.subTest(reason=reason):
                pairings, _, report = bounded.generate_pricing_pairings(
                    graph, duals, set(), cost_function=lambda pairing: 1.0, **limits
                )
                self.assertEqual(report.limits_reached, (reason,))
                self.assertTrue(report.truncated)
                self.assertEqual(report.dfs_states, states)
                self.assertEqual(report.candidates_collected, candidates)
                self.assertEqual(len(pairings), candidates)
                if reason == "per-start candidate limit":
                    self.assertEqual(
                        {p.duties[0].duty_id for p in pairings.values()}, {"S0", "S1", "S2"}
                    )

    def test_clock_can_expire_before_the_first_state(self) -> None:
        graph, duals = self._branches()
        self.clock.side_effect = [0.0, 30.0]
        pairings, _, report = bounded.generate_pricing_pairings(graph, duals, set())
        self.assertEqual(pairings, {})
        self.assertEqual(report.dfs_states, 0)
        self.assertEqual(report.limits_reached, ("time limit",))

    def test_clock_expiry_keeps_collected_candidates_and_stops_other_starts(self) -> None:
        duties = [self._duty(f"D{i}") for i in range(3)]

        def cost(pairing):
            self.clock.return_value = 30.0
            return 1.0

        pairings, _, report = bounded.generate_pricing_pairings(
            {duty: [] for duty in duties}, {duty.duty_id: 10.0 for duty in duties},
            set(), cost_function=cost,
        )
        self.assertEqual(len(pairings), 1)
        self.assertEqual(report.dfs_states, 1)
        self.assertEqual(report.limits_reached, ("time limit",))

    def test_duplicate_and_existing_paths_do_not_consume_candidate_budget(self) -> None:
        graph, duals = self._branches(returns=2)
        first = next(iter(graph))
        low, high = graph[first]
        graph[first] = [low, low, high]
        for existing in (set(), {(first.duty_id, low.duty_id)}):
            with self.subTest(existing=bool(existing)):
                expected = 1 if existing else 2
                pairings, _, report = bounded.generate_pricing_pairings(
                    graph, duals, existing, max_candidates=3, max_candidates_per_start=3,
                    cost_function=lambda pairing: 1.0,
                )
                self.assertEqual(len(pairings), expected)
                self.assertEqual(report.candidates_collected, expected)
                self.assertEqual(report.dfs_states, 4)
                self.assertFalse(report.truncated)

    def test_nonnegative_prefix_is_extended_with_dual_guidance_and_exploration(self) -> None:
        first = self._duty("S0")
        departure = self.departure + timedelta(hours=12)
        direct = self._duty("DIRECT", departure=departure)
        via = Duty(
            "VIA", (
                Flight("A", self.base, self.outstation, departure, departure + timedelta(hours=1)),
                Flight("B", self.outstation, self.base,
                       departure + timedelta(hours=2), departure + timedelta(hours=3)),
            ), timedelta(hours=3), timedelta(hours=2), timedelta(hours=1),
        )
        for random_value, expected in ((0.5, via), (0.0, direct)):
            with (
                self.subTest(random_value=random_value),
                patch.object(bounded.Random, "random", return_value=random_value),
                patch.object(bounded.Random, "shuffle"),
            ):
                pairings, _, _ = bounded.generate_pricing_pairings(
                    {first: [direct, via]}, {"S0": 0.0, "DIRECT": 11.0, "A": 6.0, "B": 6.0},
                    set(), max_candidates_per_start=1, cost_function=lambda pairing: 1.0,
                )
                self.assertEqual(pairings["P1"].duties, (first, expected))

    def test_explores_successors_outside_the_old_top_twenty(self) -> None:
        graph, duals = self._branches(returns=25)
        pairings, _, report = bounded.generate_pricing_pairings(
            graph, duals, set(), max_candidates_per_start=30,
            cost_function=lambda pairing: 1.0,
        )
        self.assertEqual(len(pairings), 25)
        self.assertEqual(report.dfs_states, 26)
        self.assertFalse(report.truncated)

    def test_padding_duals_use_the_strict_negative_tolerance(self) -> None:
        duty = self._duty("PAD", departure=datetime(2000, 1, 8, 8))
        for dual, expected in ((-5.0, 0), (0.0, 0), (5e-7, 0), (1e-6, 0), (2e-6, 1)):
            with self.subTest(dual=dual):
                pairings, _, _ = bounded.generate_pricing_pairings(
                    {duty: []}, {"PAD": dual}, set(), cost_function=lambda pairing: 0.0,
                )
                self.assertEqual(len(pairings), expected)

    def test_required_and_padding_duals_both_contribute_to_reduced_cost(self) -> None:
        first = self._duty("REQ", destination=self.outstation, departure=datetime(2000, 1, 7, 18))
        second = self._duty("PAD", origin=self.outstation, departure=datetime(2000, 1, 8, 8))
        for padding_dual, expected in ((-10.0, 0), (-5.0, 1)):
            with self.subTest(padding_dual=padding_dual):
                pairings, _, _ = bounded.generate_pricing_pairings(
                    {first: [second]}, {"REQ": 10.0, "PAD": padding_dual}, set(),
                    cost_function=lambda pairing: 1.0,
                )
                self.assertEqual(len(pairings), expected)

    def test_previously_covered_flights_remain_eligible(self) -> None:
        first = self._duty("D0", flight_id="F1")
        second = self._duty("D1", flight_id="F1")
        pairings, _, _ = bounded.generate_pricing_pairings(
            {first: [], second: []}, {"F1": 5.0}, {("D0",)},
            cost_function=lambda pairing: 1.0,
        )
        self.assertEqual(pairings["P1"].duties, (second,))

    def test_existing_base_duty_count_and_elapsed_time_legality_are_preserved(self) -> None:
        graph, duals = self._branches()
        for limits in ({"max_duties": 1}, {"max_pairing_time": timedelta(hours=12)}):
            with self.subTest(limits=limits):
                pairings, _, report = bounded.generate_pricing_pairings(
                    graph, duals, set(), cost_function=lambda pairing: 1.0, **limits
                )
                self.assertEqual(pairings, {})
                self.assertFalse(report.truncated)
        other_base = Airport("OTHER", 1)
        duty = self._duty("OTHER", destination=other_base)
        pairings, _, _ = bounded.generate_pricing_pairings(
            {duty: []}, {"OTHER": 100.0}, set(), cost_function=lambda pairing: 1.0,
        )
        self.assertEqual(pairings, {})

    def test_seed_is_reproducible_and_changes_bounded_exploration(self) -> None:
        graph, duals = self._branches(starts=8)

        def selected(seed):
            pairings, _, report = bounded.generate_pricing_pairings(
                graph, duals, set(), seed=seed, max_candidates=1,
                cost_function=lambda pairing: 1.0,
            )
            return pairings["P1"].duties, report

        self.assertEqual(selected(0), selected(0))
        self.assertNotEqual(selected(0)[0], selected(1)[0])

    def test_empty_truncated_search_retries_once_and_returns_explicit_status(self) -> None:
        signatures = set()
        duals = {"F1": 5.0}
        cost = lambda pairing: 1.0
        for retry_limits in ((), ("time limit",)):
            with self.subTest(retry_limits=retry_limits), patch.object(
                bounded, "generate_pricing_pairings", side_effect=[
                    ({}, signatures, bounded.PricingSearchReport(21, 1, 0, ("per-start DFS state limit",))),
                    ({}, signatures, bounded.PricingSearchReport(22, 2, 0, retry_limits)),
                ],
            ) as search:
                result = bounded.price_with_retry(
                    {}, duals, signatures, iteration=3, seed=17, cost_function=cost,
                    max_dfs_states_per_start=1, max_candidates_per_start=5, max_candidates=20,
                )
                self.assertEqual(search.call_count, 2)
                first, retry = search.call_args_list
                self.assertEqual(first.kwargs["seed"], 21)
                self.assertEqual(retry.kwargs["seed"], 22)
                self.assertIs(retry.args[1], first.args[1])
                self.assertIs(retry.args[2], signatures)
                self.assertIs(retry.kwargs["cost_function"], cost)
                self.assertEqual(retry.kwargs["max_dfs_states"], 1_000_000)
                self.assertEqual(retry.kwargs["max_seconds"], 60.0)
                for name in ("max_dfs_states_per_start", "max_candidates_per_start", "max_candidates"):
                    self.assertEqual(first.kwargs[name], retry.kwargs[name])
                self.assertEqual(result.status, "heuristic search found no improving columns")
                self.assertEqual(len(result.searches), 2)

    def test_complete_empty_search_and_nonempty_truncated_search_do_not_retry(self) -> None:
        signatures = set()
        pairing = build_pairing_from_path("P1", [self._duty("D0")])
        for pairings, report, status in (
            ({}, bounded.PricingSearchReport(0, 1, 0), bounded.COMPLETE_SEARCH_NO_COLUMNS),
            ({"P1": pairing}, bounded.PricingSearchReport(0, 1, 1, ("global candidate limit",)),
             bounded.IMPROVING_COLUMNS_FOUND),
        ):
            with self.subTest(status=status), patch.object(
                bounded, "generate_pricing_pairings", return_value=(pairings, signatures, report),
            ) as search:
                result = bounded.price_with_retry({}, {}, signatures)
                self.assertEqual(search.call_count, 1)
                self.assertEqual(result.status, status)

    def test_larger_retry_can_find_candidates_on_the_same_duals(self) -> None:
        graph, duals = self._branches()
        with patch.object(
            bounded, "generate_pricing_pairings", wraps=bounded.generate_pricing_pairings,
        ) as search:
            result = bounded.price_with_retry(
                graph, duals, set(), max_dfs_states=1, cost_function=lambda pairing: 1.0,
            )
        self.assertEqual(len(result.pairings), 3)
        self.assertEqual([report.seed for report in result.searches], [0, 1])
        self.assertEqual(result.searches[0].dfs_states, 1)
        self.assertEqual(result.status, bounded.IMPROVING_COLUMNS_FOUND)
        self.assertIs(search.call_args_list[0].args[1], search.call_args_list[1].args[1])

    def test_alternative_cg_reuses_initial_pool_and_master_with_iteration_seeds(self) -> None:
        duties = [self._duty("D0"), self._duty("D1")]
        graph = {duty: [] for duty in duties}
        flights = {duty.duty_id: duty.flights[0] for duty in duties}
        first = SimpleNamespace(duals={"D0": 1.0, "D1": 5.0}, objective=10.0)
        final = SimpleNamespace(duals={"D0": 1.0, "D1": 1.0}, objective=2.0)
        for max_iterations, expected_status, expected_seeds in (
            (1, bounded.ITERATION_LIMIT_REACHED, [0]),
            (2, bounded.COMPLETE_SEARCH_NO_COLUMNS, [0, 2]),
        ):
            solver_module = ModuleType("column_generation.master_lp")
            solver_module.solve_master_lp = Mock(side_effect=[first, final])
            with (
                self.subTest(max_iterations=max_iterations),
                patch.dict(sys.modules, {"column_generation.master_lp": solver_module}),
                patch.object(bounded, "price_with_retry", wraps=bounded.price_with_retry) as price,
            ):
                columns, signatures, master, status = bounded.run_column_generation(
                    graph, flights, cost_function=lambda pairing: 1.0,
                    max_initial_pairings=1, max_iterations=max_iterations,
                )
                self.assertEqual(len(columns), 2)
                self.assertEqual(signatures, {pairing_signature(p.duties) for p in columns.values()})
                self.assertIs(master, final)
                self.assertEqual(status, expected_status)
                self.assertEqual(solver_module.solve_master_lp.call_count, 2)
                self.assertEqual(
                    [2 * (call.kwargs["iteration"] - 1) for call in price.call_args_list],
                    expected_seeds,
                )
                self.assertIs(price.call_args_list[0].args[1], first.duals)
                if max_iterations == 2:
                    self.assertIs(price.call_args_list[1].args[1], final.duals)

    def test_alternative_cg_stops_with_heuristic_status_after_empty_retry(self) -> None:
        graph, duals = self._branches()
        flights = {
            flight.flight_id: flight
            for first, successors in graph.items()
            for duty in [first, *successors]
            for flight in duty.flights
        }
        master = SimpleNamespace(duals=duals, objective=1.0)
        solver_module = ModuleType("column_generation.master_lp")
        solver_module.solve_master_lp = Mock(return_value=master)
        with patch.dict(sys.modules, {"column_generation.master_lp": solver_module}):
            _, _, returned_master, status = bounded.run_column_generation(
                graph, flights, max_initial_pairings=1, max_dfs_states_per_start=1,
                cost_function=lambda pairing: 1.0,
            )
        self.assertIs(returned_master, master)
        self.assertEqual(solver_module.solve_master_lp.call_count, 1)
        self.assertEqual(status, "heuristic search found no improving columns")


if __name__ == "__main__":
    unittest.main()
