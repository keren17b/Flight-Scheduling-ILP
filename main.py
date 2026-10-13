"""Run several heuristic attempts, saving the best solution and a comparison."""

from time import perf_counter
from dataclasses import dataclass
import random
import sys
import traceback

from column_generation import main_column_generation
from column_generation.config import RUN_RESULTS_DIR
from column_generation.run_summary import (
    BatchSummary, RunSummary, compact_run_record,
    run_timestamp, save_best_run, save_run_comparison,
)
from crew_pairing.config import FLIGHTS_FILE_PATH, HUBS_FILE_PATH
from crew_pairing.duties import generate_duties
from crew_pairing.duty_graph import DutyGraph, build_duty_graph
from crew_pairing.flights_graph import Flight, load_flight_network
from run_progress import observe_messages, observe_stages, progress, stage


def prepare_graphs() -> tuple[DutyGraph, dict[str, Flight]]:
    stage("loading data")
    progress(f"Loading flights from {FLIGHTS_FILE_PATH} and building flight graph")
    airports, flights, graph = load_flight_network(FLIGHTS_FILE_PATH, HUBS_FILE_PATH)
    stage("building graphs")
    progress(f"Flight graph ready: {len(flights):,} flights, {len(airports):,} airports")
    progress("Generating duties")
    duties = generate_duties(graph)
    progress(f"Generated {len(duties):,} duties; building duty graph")
    duty_graph = build_duty_graph(duties.values())
    progress(f"Duty graph ready: {len(duty_graph):,} duties")
    return duty_graph, flights


def run_once(
    duty_graph: DutyGraph,
    flights: dict[str, Flight],
    *,
    seed: int | None = 42,
    rng: random.Random | None = None,
    batch_run_index: int | None = None,
) -> RunSummary:
    """Return one attempt in memory, recording errors and keeping their traceback."""
    summary = RunSummary()
    summary.batch_run_index = batch_run_index
    if rng is not None:
        summary.random_seed = seed
    # Prepared graphs are shared by the batch and not rebuilt for this attempt.
    summary.runtime_seconds["build_graphs"] = 0.0
    started = perf_counter()
    try:
        return main_column_generation.main(duty_graph, flights, seed=seed, rng=rng, summary=summary)
    except Exception as error:
        if summary.outcome != "solver_no_conclusion":
            summary.outcome = "execution_error"
            summary.outcome_detail = "Execution failed; see error details."
        if not summary.ilp.attempted:
            summary.ilp.skip_reason = summary.outcome
        summary.error = _error_details(error)
        traceback.print_exc()
        return summary
    finally:
        summary.runtime_seconds["total"] = perf_counter() - started


def _error_details(error: Exception) -> dict[str, str]:
    return {
        "type": type(error).__name__,
        "message": str(error),
        "traceback": traceback.format_exc(),
    }


@dataclass
class BatchResult:
    summary: BatchSummary
    best: RunSummary | None


def main(seed: int | None = 42, num_runs: int = 5) -> RunSummary | None:
    """Preserve the CLI's advancing shared random stream and return type."""
    return run_batch(seed, num_runs).best


def run_batch(seed: int | None = 42, num_runs: int = 5, *,
              consecutive_seeds: bool = False, on_progress=None, on_message=None) -> BatchResult:
    """Shared orchestration, selection and persistence for CLI and local UI.

    The CLI and UI use one seeded random stream that advances across attempts.
    consecutive_seeds optionally starts each attempt with seed + zero-based index.
    Observers receive (stage_name, one_based_run_index_or_None).
    on_message receives raw ProgressMessage events without elapsed-time prefixes.
    """
    if not isinstance(num_runs, int) or isinstance(num_runs, bool) or num_runs < 1:
        raise ValueError("num_runs must be a positive integer")
    with observe_stages(on_progress), observe_messages(on_message):
        return _run_batch(seed, num_runs, consecutive_seeds)


def _run_batch(seed, num_runs, consecutive_seeds) -> BatchResult:
    batch = BatchSummary(requested_runs=num_runs)
    batch.seed_strategy = "consecutive" if consecutive_seeds else "shared_stream"
    best: RunSummary | None = None
    started = perf_counter()
    try:
        graph_started = perf_counter()
        try:
            duty_graph, flights = prepare_graphs()
        finally:
            batch.runtime_seconds["build_graphs"] = perf_counter() - graph_started

        if seed is None:
            seed = random.SystemRandom().getrandbits(128)
        rng = random.Random(seed)
        batch.random_seed = seed
        for index in range(num_runs):
            run_seed = seed + index if consecutive_seeds else seed
            run_rng = random.Random(run_seed) if consecutive_seeds else rng
            stage("initial pool", index + 1)
            progress(f"Run {index + 1}/{num_runs}")
            result = run_once(
                duty_graph, flights, seed=run_seed, rng=run_rng, batch_run_index=index + 1,
            )
            batch.runs.append(compact_run_record(result))
            batch.completed_runs += 1
            solution = result.integer_solution
            if (
                result.outcome == "integer_solution_found"
                and solution is not None
                and solution.pairings is not None
                and (best is None or solution.cost < best.integer_solution.cost)
            ):
                best = result

        if best is not None:
            batch.outcome = "integer_solution_found"
            batch.best_run_id = best.run_id
            batch.best_cost = best.integer_solution.cost
            path = save_best_run(best, RUN_RESULTS_DIR, batch.batch_id)
            batch.best_solution_path = str(path.resolve())
            print(f"Best run: {best.run_id} (seed {best.random_seed})")
            print(f"Best total cost (rest + sitting hours): {best.integer_solution.cost}")
            print(f"Selected pairings: {best.integer_solution.selected_pairing_count}")
            print(f"Wrote best run result to {path}")
        else:
            print("No feasible integer solution was found in this batch; see the run comparison for each outcome.")
        return BatchResult(batch, best)
    except Exception as error:
        batch.outcome = "execution_error"
        batch.error = _error_details(error)
        raise
    finally:
        batch.finished_at = run_timestamp()
        batch.runtime_seconds["total"] = perf_counter() - started
        try:
            path = save_run_comparison(batch, RUN_RESULTS_DIR)
        except Exception as error:
            if batch.error is None:
                raise
            print(f"Failed to save run comparison: {error}", file=sys.stderr)
        else:
            print(f"Wrote run comparison to {path}")


if __name__ == "__main__":
    main()
