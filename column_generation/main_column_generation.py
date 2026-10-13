"""Run CG and the final ILP on graphs prepared by the root entry point."""

import random

from crew_pairing.duty_graph import DutyGraph
from crew_pairing.flights_graph import Flight
from crew_pairing.solution_validator import validate_solution

from column_generation.column_generation import run_column_generation
from column_generation.config import (
    ARTIFICIAL_TOLERANCE,
    PRICING_RANDOM_SEED,
)
from column_generation.master_ilp import solve_ilp
from column_generation.run_summary import (
    IntegerSolutionSummary,
    RunSummary,
    measure_runtime,
)
from column_generation.solution_export import (
    selected_pairings_payload,
    selected_pairings,
)
from run_progress import progress, stage


def main(
    duty_graph: DutyGraph | None = None,
    flights: dict[str, Flight] | None = None,
    *,
    seed: int | None = PRICING_RANDOM_SEED,
    summary: RunSummary | None = None,
    rng: random.Random | None = None,
) -> RunSummary | None:
    """Optimize prepared inputs, or forward the legacy no-argument entry point."""
    if duty_graph is None and flights is None and summary is None and rng is None:
        from main import main as run_project
        return run_project(seed=seed)
    if duty_graph is None or flights is None or summary is None:
        raise ValueError("Prepared duty_graph, flights and run summary must be supplied together")
    pairings, master_result = run_column_generation(
        duty_graph,
        flights,
        summary=summary,
        seed=seed,
        rng=rng,
    )

    leftover_artificials = [
        flight_id
        for flight_id, value in master_result.artificial_values.items()
        if value > ARTIFICIAL_TOLERANCE
    ]
    if leftover_artificials:
        summary.outcome = "lp_artificials_remaining"
        summary.outcome_detail = "Required flights still use artificial coverage in the restricted LP; this does not establish infeasibility of the full problem."
        summary.ilp.skip_reason = "lp_artificials_remaining"
        print(
            "Warning: restricted master LP still uses artificials for "
            f"{len(leftover_artificials)} required flights."
        )
        for flight_id in leftover_artificials:
            print(
                f"  {flight_id}: "
                f"artificial={master_result.artificial_values[flight_id]:.6f}, "
                f"dual={master_result.duals[flight_id]:.6f}"
            )
        return summary

    print(f"Generated columns: {len(pairings)}")
    print(f"Restricted master LP objective: {master_result.objective}")

    stage("final ILP")
    progress(f"Starting final ILP with {len(pairings):,} pairings")
    summary.ilp.attempted = True
    summary.ilp.skip_reason = None
    with measure_runtime(summary, "final_ilp"):
        ilp_result = solve_ilp(pairings, flights, summary=summary)
    if ilp_result is None:
        summary.outcome = "generated_pool_integer_infeasible"
        summary.outcome_detail = "No binary feasible solution exists within the generated pairing pool; this does not establish infeasibility of the full problem."
        return summary
    solution, total_cost = ilp_result
    progress("Final ILP finished")
    chosen = selected_pairings(pairings, solution)
    validation = validate_solution(chosen, flights, total_cost)
    summary.ilp.validation = validation
    print(f"Solution validation: {'VALID' if validation.is_valid else 'INVALID'}")
    if not validation.is_valid:
        for error in validation.errors:
            print(f"  {error}")
        summary.integer_solution = None
        summary.outcome = "solution_validation_failed"
        summary.outcome_detail = "Selected integer solution failed independent validation; see ilp.validation.errors."
        return summary
    summary.integer_solution = IntegerSolutionSummary(total_cost, len(chosen))
    # Reuse the existing pairing serializer inside the single run result.
    payload = selected_pairings_payload(chosen, total_cost=total_cost)
    summary.integer_solution.generated_at = payload["generated_at"]
    summary.integer_solution.pairings = payload["pairings"]
    summary.outcome = "integer_solution_found"
    summary.outcome_detail = "Feasible integer solution found within the generated pairing pool."
    print(f"Solution list dimensions: {len(solution)}")
    print(f"Total cost: {total_cost}")
    print(f"Selected pairings: {len(chosen)}")
    return summary


if __name__ == "__main__":
    main()
