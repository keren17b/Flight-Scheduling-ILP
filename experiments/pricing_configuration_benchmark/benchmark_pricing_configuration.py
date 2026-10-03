"""
Benchmark pricing configurations for the column-generation branch.

Purpose
-------
Choose practical values for:
    - TOP_K_SUCCESSORS
    - MAX_STATES_PER_START
    - MAX_NEGATIVE_PAIRINGS_PER_START
    - MAX_NEW_PAIRINGS_PER_ITERATION

The benchmark is intentionally aligned with the project goal: obtain a feasible
solution, not prove LP optimality.  It therefore measures how quickly each
configuration removes artificial variables from the restricted master, and
(optionally) whether the resulting columns admit a feasible final binary ILP.

Recommended location inside the repository:
    experiments/pricing_configuration_benchmark/benchmark_pricing_configuration.py

Run it from that folder:
    python benchmark_pricing_configuration.py

The script automatically locates the repository root, temporarily uses it as
the working directory so the project's existing relative paths keep working,
and writes benchmark CSV output next to this script.

The script does NOT modify the project files.  It builds the initial pool once,
then starts every tested configuration from the exact same initial columns and
first master-LP solution.
"""

from __future__ import annotations

import csv
import os
import random
import sys
import time
from dataclasses import dataclass, replace
from datetime import timedelta
from pathlib import Path
from statistics import mean, median
from typing import Dict, List, Optional, Set, Tuple


def _find_project_root(script_dir: Path) -> Path:
    """Find the repository root from the benchmark script location.

    We look for the directories imported by this project instead of assuming a
    fixed number of parent directories.  This keeps the benchmark usable even
    if the experiments folder is moved one level up/down later.
    """
    candidates = (script_dir, *script_dir.parents)
    for candidate in candidates:
        if (candidate / "column_generation").is_dir() and (candidate / "crew_pairing").is_dir():
            return candidate
    raise RuntimeError(
        "Could not locate the project root. Expected to find both "
        "'column_generation' and 'crew_pairing' directories above this script."
    )


SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = _find_project_root(SCRIPT_DIR)

# Existing project configuration uses repository-relative paths.  Running from
# the benchmark subfolder should therefore behave exactly like running the main
# project from the repository root.
os.chdir(PROJECT_ROOT)
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from column_generation.config import (
    ARTIFICIAL_TOLERANCE,
    FLIGHTS_FILE_PATH,
    HUBS_FILE_PATH,
    MAX_INITIAL_PAIRINGS,
)
from column_generation.initial_pool import generate_initial_pairings
from column_generation.master_ilp import solve_ilp
from column_generation.master_lp import MasterLpResult, solve_master_lp
from crew_pairing.config import MAX_DUTIES_PER_PAIRING, MAX_PAIRING_TIME
from crew_pairing.duties import Duty, generate_duties
from crew_pairing.duty_graph import DutyGraph, build_duty_graph
from crew_pairing.flights_graph import Flight, load_flight_network
from crew_pairing.pairing_cost import current_pairing_cost
from crew_pairing.pairings import Pairing, build_pairing_from_path, pairing_signature
from run_progress import progress


# ---------------------------------------------------------------------------
# Benchmark controls
# ---------------------------------------------------------------------------

BASE_RANDOM_SEED = 42
REDUCED_COST_EPS = 1e-9
BENCHMARK_MAX_ITERATIONS = 10
RUN_FINAL_ILP = True

RESULTS_CSV = SCRIPT_DIR / "pricing_configuration_benchmark_results.csv"
ITERATIONS_CSV = SCRIPT_DIR / "pricing_configuration_benchmark_iterations.csv"


@dataclass(frozen=True)
class PricingConfig:
    name: str
    top_k_successors: int
    max_states_per_start: int
    max_negative_pairings_per_start: int
    max_new_pairings_per_iteration: int


# The list is deliberately small enough to run in one session, while changing
# one important knob at a time around the current best candidate K=20.
BENCHMARK_CONFIGS: Tuple[PricingConfig, ...] = (
    # State-budget comparison, fixed K / per-start cap / global batch size.
    PricingConfig("K20_S500_P500_G2000", 20, 500, 500, 2_000),
    PricingConfig("K20_S1000_P500_G2000", 20, 1_000, 500, 2_000),
    PricingConfig("K20_S2000_P500_G2000", 20, 2_000, 500, 2_000),
    PricingConfig("K20_S3000_P500_G2000", 20, 3_000, 500, 2_000),

    # K comparison at the same state budget and batch size.
    PricingConfig("K10_S2000_P500_G2000", 10, 2_000, 500, 2_000),
    PricingConfig("K30_S2000_P500_G2000", 30, 2_000, 500, 2_000),

    # Per-start cap comparison: does forcing more diversity help feasibility?
    PricingConfig("K20_S2000_P100_G2000", 20, 2_000, 100, 2_000),

    # Global number of columns added per CG iteration.
    PricingConfig("K20_S2000_P500_G500", 20, 2_000, 500, 500),
    PricingConfig("K20_S2000_P500_G5000", 20, 2_000, 500, 5_000),
)


@dataclass
class PricingStats:
    states_visited: int = 0
    starts_visited: int = 0
    starts_with_negative: int = 0
    closed_pairings_checked: int = 0
    negative_pairings_found: int = 0
    negative_per_start: Optional[List[int]] = None

    def __post_init__(self) -> None:
        if self.negative_per_start is None:
            self.negative_per_start = []


@dataclass
class ConfigResult:
    name: str
    top_k: int
    states_per_start: int
    neg_per_start_cap: int
    max_new_per_iteration: int
    reached_zero_artificials: bool
    iterations: int
    initial_artificials: int
    final_artificials: int
    initial_columns: int
    final_columns: int
    total_columns_added: int
    total_time_sec: float
    pricing_time_sec: float
    master_time_sec: float
    final_ilp_attempted: bool
    final_ilp_succeeded: bool
    final_ilp_time_sec: float
    final_ilp_selected_pairings: Optional[int]
    final_ilp_cost: Optional[float]


def _count_artificials(master_result: MasterLpResult) -> int:
    return sum(
        1
        for value in master_result.artificial_values.values()
        if value > ARTIFICIAL_TOLERANCE
    )


def _pairing_reduced_cost(
    pairing: Pairing,
    duals: Dict[str, float],
) -> float:
    dual_sum = sum(
        duals[flight.flight_id]
        for duty in pairing.duties
        for flight in duty.flights
    )
    return current_pairing_cost(pairing) - dual_sum


def _successor_score(
    current_duty: Duty,
    next_duty: Duty,
    duals: Dict[str, float],
) -> float:
    """Incremental reduced-cost contribution of extending to next_duty.

    Pairing cost is rest + sitting time.  Extending a path contributes the rest
    from current_duty to next_duty plus next_duty's sitting time, while the
    flights in next_duty contribute their dual values.

    Lower score is more promising.
    """
    rest_hours = (
        next_duty.start_time - current_duty.end_time
    ).total_seconds() / 3600.0
    sitting_hours = next_duty.sitting_time.total_seconds() / 3600.0
    dual_value = sum(duals[flight.flight_id] for flight in next_duty.flights)
    return rest_hours + sitting_hours - dual_value


def _legal_starting_duties(
    graph: DutyGraph,
    max_pairing_time: timedelta = MAX_PAIRING_TIME,
) -> List[Duty]:
    starts: List[Duty] = []
    for duty in graph:
        if not duty.start_airport.is_crew_base:
            continue
        duty_time = duty.end_time - duty.start_time
        if timedelta(0) <= duty_time <= max_pairing_time:
            starts.append(duty)
    return starts


def generate_benchmark_pricing_pairings(
    graph: DutyGraph,
    duals: Dict[str, float],
    existing_signatures: Set[Tuple[str, ...]],
    config: PricingConfig,
    iteration: int,
    max_pairing_time: timedelta = MAX_PAIRING_TIME,
    max_duties: int = MAX_DUTIES_PER_PAIRING,
) -> Tuple[Dict[str, Pairing], Set[Tuple[str, ...]], PricingStats]:
    """Guided randomized DFS used only by this benchmark.

    Design:
      * all legal starting duties are eligible;
      * start order is shuffled reproducibly per iteration;
      * at each node, successors are ranked by incremental reduced-cost score;
      * only Top-K successors are kept, then their order is shuffled;
      * budgets are local per starting duty;
      * only new, unique, negative-reduced-cost pairings count toward caps.
    """
    rng = random.Random(BASE_RANDOM_SEED + iteration)
    starts = _legal_starting_duties(graph, max_pairing_time)
    rng.shuffle(starts)

    # Cache deterministic rankings for the current dual vector.  The Top-K list
    # itself is copied and shuffled at each visit so DFS order can vary.
    ranked_successors: Dict[Duty, List[Duty]] = {}

    def get_ranked_successors(current: Duty) -> List[Duty]:
        cached = ranked_successors.get(current)
        if cached is not None:
            return cached
        ranked = sorted(
            graph.get(current, []),
            key=lambda nxt: _successor_score(current, nxt, duals),
        )
        ranked_successors[current] = ranked
        return ranked

    pairings: Dict[str, Pairing] = {}
    stats = PricingStats()

    for start in starts:
        if len(pairings) >= config.max_new_pairings_per_iteration:
            break

        stats.starts_visited += 1
        local_states = 0
        local_negative = 0

        def dfs(current_duty: Duty, path: List[Duty]) -> None:
            nonlocal local_states, local_negative

            if local_states >= config.max_states_per_start:
                return
            if local_negative >= config.max_negative_pairings_per_start:
                return
            if len(pairings) >= config.max_new_pairings_per_iteration:
                return

            local_states += 1
            stats.states_visited += 1

            returned_to_base = (
                current_duty.end_airport.is_crew_base
                and current_duty.end_airport.port_name
                == path[0].start_airport.port_name
            )

            if returned_to_base:
                stats.closed_pairings_checked += 1
                signature = pairing_signature(path)
                if signature not in existing_signatures:
                    temp_id = f"TMP{len(pairings) + 1}"
                    pairing = build_pairing_from_path(temp_id, path)
                    rc = _pairing_reduced_cost(pairing, duals)
                    if rc < -REDUCED_COST_EPS:
                        pairings[temp_id] = pairing
                        existing_signatures.add(signature)
                        local_negative += 1
                        stats.negative_pairings_found += 1

                        if local_negative >= config.max_negative_pairings_per_start:
                            return
                        if len(pairings) >= config.max_new_pairings_per_iteration:
                            return

            if len(path) >= max_duties:
                return

            ranked = get_ranked_successors(current_duty)
            top = list(ranked[: config.top_k_successors])
            rng.shuffle(top)

            for next_duty in top:
                if next_duty in path:
                    continue
                total_time = next_duty.end_time - path[0].start_time
                if total_time > max_pairing_time:
                    continue

                path.append(next_duty)
                dfs(next_duty, path)
                path.pop()

                if local_states >= config.max_states_per_start:
                    return
                if local_negative >= config.max_negative_pairings_per_start:
                    return
                if len(pairings) >= config.max_new_pairings_per_iteration:
                    return

        dfs(start, [start])
        stats.negative_per_start.append(local_negative)
        if local_negative > 0:
            stats.starts_with_negative += 1

    return pairings, existing_signatures, stats


def _add_columns(
    columns: Dict[str, Pairing],
    new_pairings: Dict[str, Pairing],
) -> None:
    for pairing in new_pairings.values():
        column_id = f"P{len(columns) + 1}"
        columns[column_id] = replace(pairing, pairing_id=column_id)


def run_one_configuration(
    config: PricingConfig,
    initial_columns: Dict[str, Pairing],
    initial_signatures: Set[Tuple[str, ...]],
    initial_master: MasterLpResult,
    flights: Dict[str, Flight],
    graph: DutyGraph,
    iteration_rows: List[dict],
) -> ConfigResult:
    columns = dict(initial_columns)
    signatures = set(initial_signatures)
    master_result = initial_master

    initial_artificials = _count_artificials(master_result)
    pricing_time = 0.0
    master_time = 0.0
    total_start = time.perf_counter()
    iterations_done = 0

    print("\n" + "=" * 92)
    print(f"CONFIG: {config.name}")
    print(
        f"K={config.top_k_successors}, "
        f"states/start={config.max_states_per_start:,}, "
        f"negative/start cap={config.max_negative_pairings_per_start:,}, "
        f"new/iteration cap={config.max_new_pairings_per_iteration:,}"
    )
    print(f"Initial columns: {len(columns):,}; initial artificials: {initial_artificials}")
    print("=" * 92)

    for iteration in range(1, BENCHMARK_MAX_ITERATIONS + 1):
        artificials_before = _count_artificials(master_result)
        if artificials_before == 0:
            break

        pricing_start = time.perf_counter()
        new_pairings, signatures, pricing_stats = generate_benchmark_pricing_pairings(
            graph,
            master_result.duals,
            signatures,
            config,
            iteration,
        )
        pricing_sec = time.perf_counter() - pricing_start
        pricing_time += pricing_sec

        if not new_pairings:
            print(
                f"Iteration {iteration}: pricing found no new negative pairings; "
                "stopping this configuration."
            )
            break

        _add_columns(columns, new_pairings)

        master_start = time.perf_counter()
        master_result = solve_master_lp(columns, flights, current_pairing_cost)
        master_sec = time.perf_counter() - master_start
        master_time += master_sec

        iterations_done = iteration
        artificials_after = _count_artificials(master_result)
        neg_counts = pricing_stats.negative_per_start or [0]

        iteration_rows.append(
            {
                "config": config.name,
                "iteration": iteration,
                "top_k": config.top_k_successors,
                "states_per_start": config.max_states_per_start,
                "neg_per_start_cap": config.max_negative_pairings_per_start,
                "new_per_iteration_cap": config.max_new_pairings_per_iteration,
                "artificials_before": artificials_before,
                "artificials_after": artificials_after,
                "new_columns": len(new_pairings),
                "total_columns": len(columns),
                "pricing_sec": round(pricing_sec, 6),
                "master_sec": round(master_sec, 6),
                "states_visited": pricing_stats.states_visited,
                "starts_visited": pricing_stats.starts_visited,
                "starts_with_negative": pricing_stats.starts_with_negative,
                "closed_pairings_checked": pricing_stats.closed_pairings_checked,
                "avg_negative_per_visited_start": round(mean(neg_counts), 3),
                "median_negative_per_visited_start": round(median(neg_counts), 3),
                "master_objective": master_result.objective,
            }
        )

        print(
            f"Iteration {iteration:2d}: "
            f"artificials {artificials_before:3d} -> {artificials_after:3d} | "
            f"new columns {len(new_pairings):5,d} | "
            f"columns total {len(columns):6,d} | "
            f"pricing {pricing_sec:6.2f}s | master {master_sec:6.2f}s | "
            f"states {pricing_stats.states_visited:8,d} | "
            f"starts {pricing_stats.starts_visited:4,d}"
        )

        if artificials_after == 0:
            break

    final_artificials = _count_artificials(master_result)
    reached_zero = final_artificials == 0

    ilp_attempted = False
    ilp_succeeded = False
    ilp_time = 0.0
    ilp_selected: Optional[int] = None
    ilp_cost: Optional[float] = None

    if RUN_FINAL_ILP and reached_zero:
        ilp_attempted = True
        ilp_start = time.perf_counter()
        try:
            solution, total_cost = solve_ilp(columns, flights, current_pairing_cost)
            ilp_time = time.perf_counter() - ilp_start
            ilp_succeeded = True
            ilp_selected = sum(1 for value in solution.values() if value > 0.5)
            ilp_cost = total_cost
        except Exception as exc:  # Benchmark should continue to the next config.
            ilp_time = time.perf_counter() - ilp_start
            print(f"Final ILP failed for {config.name}: {type(exc).__name__}: {exc}")

    total_time = time.perf_counter() - total_start

    print(
        f"RESULT {config.name}: zero_artificials={reached_zero}, "
        f"iterations={iterations_done}, columns={len(columns):,}, "
        f"CG_time={pricing_time + master_time:.2f}s, total_time={total_time:.2f}s"
    )
    if ilp_attempted:
        print(
            f"Final ILP: success={ilp_succeeded}, time={ilp_time:.2f}s, "
            f"selected={ilp_selected}, cost={ilp_cost}"
        )

    return ConfigResult(
        name=config.name,
        top_k=config.top_k_successors,
        states_per_start=config.max_states_per_start,
        neg_per_start_cap=config.max_negative_pairings_per_start,
        max_new_per_iteration=config.max_new_pairings_per_iteration,
        reached_zero_artificials=reached_zero,
        iterations=iterations_done,
        initial_artificials=initial_artificials,
        final_artificials=final_artificials,
        initial_columns=len(initial_columns),
        final_columns=len(columns),
        total_columns_added=len(columns) - len(initial_columns),
        total_time_sec=total_time,
        pricing_time_sec=pricing_time,
        master_time_sec=master_time,
        final_ilp_attempted=ilp_attempted,
        final_ilp_succeeded=ilp_succeeded,
        final_ilp_time_sec=ilp_time,
        final_ilp_selected_pairings=ilp_selected,
        final_ilp_cost=ilp_cost,
    )


def _write_csv(path: Path, rows: List[dict]) -> None:
    if not rows:
        return
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def _print_summary(results: List[ConfigResult]) -> None:
    print("\n\n" + "=" * 132)
    print("FINAL BENCHMARK SUMMARY")
    print("=" * 132)
    header = (
        f"{'config':<29} {'zero art':>8} {'iters':>5} {'added':>8} "
        f"{'pricing s':>10} {'master s':>9} {'ILP s':>8} {'total s':>9} "
        f"{'ILP ok':>7} {'selected':>8}"
    )
    print(header)
    print("-" * len(header))
    for r in results:
        selected = "-" if r.final_ilp_selected_pairings is None else str(r.final_ilp_selected_pairings)
        print(
            f"{r.name:<29} "
            f"{str(r.reached_zero_artificials):>8} "
            f"{r.iterations:5d} "
            f"{r.total_columns_added:8,d} "
            f"{r.pricing_time_sec:10.2f} "
            f"{r.master_time_sec:9.2f} "
            f"{r.final_ilp_time_sec:8.2f} "
            f"{r.total_time_sec:9.2f} "
            f"{str(r.final_ilp_succeeded):>7} "
            f"{selected:>8}"
        )

    feasible = [
        r for r in results
        if r.reached_zero_artificials
        and (not RUN_FINAL_ILP or r.final_ilp_succeeded)
    ]
    if feasible:
        fastest = min(feasible, key=lambda r: r.total_time_sec)
        fewest_columns = min(feasible, key=lambda r: r.final_columns)
        print("\nUseful comparisons (not an automatic final recommendation):")
        print(
            f"  Fastest configuration reaching the requested feasibility criterion: "
            f"{fastest.name} ({fastest.total_time_sec:.2f}s)."
        )
        print(
            f"  Smallest final column pool among feasible configurations: "
            f"{fewest_columns.name} ({fewest_columns.final_columns:,} columns)."
        )
    else:
        print("\nNo tested configuration reached the requested feasibility criterion.")


def main() -> None:
    overall_start = time.perf_counter()

    progress(f"Loading flights from {FLIGHTS_FILE_PATH} and building flight graph")
    airports, flights, flight_graph = load_flight_network(
        FLIGHTS_FILE_PATH,
        HUBS_FILE_PATH,
    )
    progress(
        f"Flight graph ready: {len(flights):,} flights, {len(airports):,} airports"
    )

    progress("Generating duties")
    duties = generate_duties(flight_graph)
    progress(f"Generated {len(duties):,} duties; building duty graph")
    duty_graph = build_duty_graph(duties.values())
    progress(f"Duty graph ready: {len(duty_graph):,} duties")

    # Build once so all configurations start from exactly the same initial pool.
    progress("Generating shared initial pairing pool")
    initial_columns, coverage_count, initial_signatures = generate_initial_pairings(
        duty_graph,
        flights,
        max_pairings=MAX_INITIAL_PAIRINGS,
    )
    uncovered = sum(1 for value in coverage_count.values() if value == 0)
    print("\n=== SHARED INITIAL POOL ===")
    print(f"Initial columns: {len(initial_columns):,}")
    print(f"Required flights with zero initial-pool coverage: {uncovered}")

    progress("Solving shared first master LP")
    initial_master = solve_master_lp(initial_columns, flights, current_pairing_cost)
    initial_artificials = _count_artificials(initial_master)
    print(f"First master objective: {initial_master.objective:,.3f}")
    print(f"Initial artificial variables > tolerance: {initial_artificials}")

    results: List[ConfigResult] = []
    iteration_rows: List[dict] = []

    for index, config in enumerate(BENCHMARK_CONFIGS, start=1):
        print(f"\nRunning benchmark {index}/{len(BENCHMARK_CONFIGS)}...")
        result = run_one_configuration(
            config,
            initial_columns,
            initial_signatures,
            initial_master,
            flights,
            duty_graph,
            iteration_rows,
        )
        results.append(result)

        # Persist partial results after each config, so a long run still leaves data.
        summary_rows = [r.__dict__.copy() for r in results]
        for row in summary_rows:
            for key, value in list(row.items()):
                if isinstance(value, float):
                    row[key] = round(value, 6)
        _write_csv(RESULTS_CSV, summary_rows)
        _write_csv(ITERATIONS_CSV, iteration_rows)

    _print_summary(results)

    print(f"\nProject root detected: {PROJECT_ROOT}")
    print(f"Benchmark folder: {SCRIPT_DIR}")
    print("\nFiles written:")
    print(f"  {RESULTS_CSV.resolve()}")
    print(f"  {ITERATIONS_CSV.resolve()}")
    print(f"Total benchmark wall time: {time.perf_counter() - overall_start:.2f}s")

    print("\nWHAT TO SEND BACK")
    print("Please send:")
    print("  1. The FINAL BENCHMARK SUMMARY printed above")
    print("  2. pricing_configuration_benchmark_results.csv")
    print("If needed, I can use the iteration CSV for a deeper comparison.")


if __name__ == "__main__":
    main()
