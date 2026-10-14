"""Compare pricing budgets using the current production pricing function.

Restored from commit a564e63 and adapted to the current solver API. Build the
initial columns and first master LP once; each configuration gets its own copies
and a continuously reused RNG seeded identically. Stop at zero LP artificials,
then optionally check final binary feasibility. This benchmark measures time to
feasibility, rather than the production loop's subsequent objective improvement.

Run from any directory:
    python <repo>/experiments/pricing_configuration_benchmark/benchmark_pricing_configuration.py

New CSVs go into a fresh runs/ subfolder. The adjacent historical CSVs are kept
as records of the original implementation and dataset.
"""

from __future__ import annotations

import argparse
import csv
import random
import sys
import time
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
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

# Support direct script execution from any working directory.
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from column_generation.config import (
    ARTIFICIAL_TOLERANCE,
    MAX_EMPTY_PRICING_ATTEMPTS,
    MAX_PRICING_DFS_STATES,
    PRICING_RANDOM_SEED,
    SELECTION_THRESHOLD,
    MAX_INITIAL_PAIRINGS,
)
from column_generation.initial_pool import generate_initial_pairings
from column_generation.master_ilp import solve_ilp
from column_generation.master_lp import MasterLpResult, solve_master_lp
from crew_pairing.config import FLIGHTS_FILE_PATH, HUBS_FILE_PATH
from crew_pairing.duties import generate_duties
from crew_pairing.duty_graph import DutyGraph, build_duty_graph
from crew_pairing.flights_graph import Flight, load_flight_network
from crew_pairing.pairing_cost import current_pairing_cost
from crew_pairing.pairings import Pairing
from crew_pairing.padding_flights import is_padding_flight
from column_generation.pairing_pricing import generate_pricing_pairings
from run_progress import progress


# ---------------------------------------------------------------------------
# Benchmark controls
# ---------------------------------------------------------------------------

BASE_RANDOM_SEED = PRICING_RANDOM_SEED
BENCHMARK_MAX_ITERATIONS = 10
RUN_FINAL_ILP = True

RESULTS_NAME = "pricing_configuration_benchmark_results.csv"
ITERATIONS_NAME = "pricing_configuration_benchmark_iterations.csv"


@dataclass(frozen=True)
class PricingConfig:
    name: str
    top_k_successors: int
    max_states_per_start: int
    max_negative_pairings_per_start: int
    max_new_pairings_per_iteration: int
    max_dfs_states: int = MAX_PRICING_DFS_STATES


# Preserve the historical comparison grid, changing one budget at a time
# around Top-K=20. These are experiment settings, not solver recommendations.
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
class ConfigResult:
    name: str
    top_k: int
    states_per_start: int
    neg_per_start_cap: int
    max_new_per_iteration: int
    max_dfs_states: int
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
    final_ilp_error: Optional[str]


def _count_artificials(master_result: MasterLpResult) -> int:
    return sum(
        1
        for value in master_result.artificial_values.values()
        if value > ARTIFICIAL_TOLERANCE
    )


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
    max_iterations: int = BENCHMARK_MAX_ITERATIONS,
    run_final_ilp: bool = RUN_FINAL_ILP,
) -> ConfigResult:
    columns = dict(initial_columns)
    signatures = set(initial_signatures)
    master_result = initial_master
    rng = random.Random(BASE_RANDOM_SEED)

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
        f"new/iteration cap={config.max_new_pairings_per_iteration:,}, "
        f"global states/call={config.max_dfs_states:,}"
    )
    print(f"Initial columns: {len(columns):,}; initial artificials: {initial_artificials}")
    print("=" * 92)

    for iteration in range(1, max_iterations + 1):
        artificials_before = _count_artificials(master_result)
        if artificials_before == 0:
            break

        pricing_start = time.perf_counter()
        new_pairings = {}
        for attempt in range(1, MAX_EMPTY_PRICING_ATTEMPTS + 1):
            new_pairings = generate_pricing_pairings(
                graph,
                master_result.duals,
                signatures,
                rng=rng,
                max_pairings=config.max_new_pairings_per_iteration,
                max_dfs_states_per_start=config.max_states_per_start,
                max_negative_pairings_per_start=config.max_negative_pairings_per_start,
                top_k_successors=config.top_k_successors,
                max_dfs_states=config.max_dfs_states,
                cost_function=current_pairing_cost,
            )
            if new_pairings:
                break
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
                "pricing_attempts": attempt,
                "max_dfs_states": config.max_dfs_states,
                "master_objective": master_result.objective,
            }
        )

        print(
            f"Iteration {iteration:2d}: "
            f"artificials {artificials_before:3d} -> {artificials_after:3d} | "
            f"new columns {len(new_pairings):5,d} | "
            f"columns total {len(columns):6,d} | "
            f"pricing {pricing_sec:6.2f}s | master {master_sec:6.2f}s | "
            f"attempts {attempt}"
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
    ilp_error: Optional[str] = None

    if run_final_ilp and reached_zero:
        ilp_attempted = True
        ilp_start = time.perf_counter()
        try:
            ilp_result = solve_ilp(columns, flights, current_pairing_cost)
            if ilp_result is None:
                ilp_error = "Generated column pool is integer-infeasible"
            else:
                solution, total_cost = ilp_result
                ilp_succeeded = True
                ilp_selected = sum(
                    1 for value in solution.values() if value > SELECTION_THRESHOLD
                )
                ilp_cost = total_cost
        except Exception as exc:  # Benchmark should continue to the next config.
            ilp_error = f"{type(exc).__name__}: {exc}"
        finally:
            ilp_time = time.perf_counter() - ilp_start
        if ilp_error:
            print(f"Final ILP failed for {config.name}: {ilp_error}")

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
        max_dfs_states=config.max_dfs_states,
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
        final_ilp_error=ilp_error,
    )


def _write_csv(path: Path, rows: List[dict]) -> None:
    if not rows:
        return
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def _print_summary(results: List[ConfigResult], run_final_ilp: bool) -> None:
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
        ilp_status = str(r.final_ilp_succeeded) if r.final_ilp_attempted else "-"
        print(
            f"{r.name:<29} "
            f"{str(r.reached_zero_artificials):>8} "
            f"{r.iterations:5d} "
            f"{r.total_columns_added:8,d} "
            f"{r.pricing_time_sec:10.2f} "
            f"{r.master_time_sec:9.2f} "
            f"{r.final_ilp_time_sec:8.2f} "
            f"{r.total_time_sec:9.2f} "
            f"{ilp_status:>7} "
            f"{selected:>8}"
        )

    feasible = [
        r for r in results
        if r.reached_zero_artificials
        and (not run_final_ilp or r.final_ilp_succeeded)
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


def _positive_int(value: str) -> int:
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return number


def main(argv: Optional[List[str]] = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config", action="append", choices=[c.name for c in BENCHMARK_CONFIGS],
        help="Run only this configuration; repeat to select several (default: all).",
    )
    parser.add_argument("--iterations", type=_positive_int, default=BENCHMARK_MAX_ITERATIONS)
    parser.add_argument("--skip-final-ilp", action="store_true", help="Check LP feasibility only.")
    parser.add_argument(
        "--output-dir", type=Path,
        default=SCRIPT_DIR / "runs" / datetime.now().strftime("%Y%m%d_%H%M%S_%f"),
        help="Destination for new CSVs (default: a fresh folder under runs/).",
    )
    args = parser.parse_args(argv)
    configs = [c for c in BENCHMARK_CONFIGS if not args.config or c.name in args.config]
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    results_csv = output_dir / RESULTS_NAME
    iterations_csv = output_dir / ITERATIONS_NAME
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
    initial_columns, initial_signatures = generate_initial_pairings(
        duty_graph,
        flights,
        max_pairings=MAX_INITIAL_PAIRINGS,
    )
    covered_ids = {
        flight.flight_id
        for pairing in initial_columns.values()
        for duty in pairing.duties
        for flight in duty.flights
    }
    uncovered = sum(
        1 for flight_id, flight in flights.items()
        if not is_padding_flight(flight) and flight_id not in covered_ids
    )
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

    for index, config in enumerate(configs, start=1):
        print(f"\nRunning benchmark {index}/{len(configs)}...")
        result = run_one_configuration(
            config,
            initial_columns,
            initial_signatures,
            initial_master,
            flights,
            duty_graph,
            iteration_rows,
            max_iterations=args.iterations,
            run_final_ilp=RUN_FINAL_ILP and not args.skip_final_ilp,
        )
        results.append(result)

        # Persist partial results after each config, so a long run still leaves data.
        summary_rows = [r.__dict__.copy() for r in results]
        for row in summary_rows:
            for key, value in list(row.items()):
                if isinstance(value, float):
                    row[key] = round(value, 6)
        _write_csv(results_csv, summary_rows)
        _write_csv(iterations_csv, iteration_rows)

    _print_summary(results, run_final_ilp=RUN_FINAL_ILP and not args.skip_final_ilp)

    print(f"\nProject root detected: {PROJECT_ROOT}")
    print(f"Benchmark folder: {SCRIPT_DIR}")
    print("\nFiles written:")
    print(f"  {results_csv}")
    if iteration_rows:
        print(f"  {iterations_csv}")
    print(f"Total benchmark wall time: {time.perf_counter() - overall_start:.2f}s")


if __name__ == "__main__":
    main()
