"""Temporary runner for the column-generation pairing path."""

from crew_pairing.duties import generate_duties
from crew_pairing.duty_graph import build_duty_graph
from crew_pairing.flights_graph import load_flight_network
from crew_pairing.config import FLIGHTS_FILE_PATH, HUBS_FILE_PATH

from column_generation.column_generation import run_column_generation
from column_generation.config import (
    ARTIFICIAL_TOLERANCE,
    SELECTED_PAIRINGS_PATH,
)
from column_generation.master_ilp import solve_ilp
from column_generation.solution_export import (
    save_selected_pairings,
    selected_pairings,
)
from run_progress import progress


def main() -> None:
    progress(f"Loading flights from {FLIGHTS_FILE_PATH} and building flight graph")
    airports, flights, graph = load_flight_network(FLIGHTS_FILE_PATH, HUBS_FILE_PATH)
    progress(f"Flight graph ready: {len(flights):,} flights, {len(airports):,} airports")
    progress("Generating duties")
    duties = generate_duties(graph)
    progress(f"Generated {len(duties):,} duties; building duty graph")
    duty_graph = build_duty_graph(duties.values())
    progress(f"Duty graph ready: {len(duty_graph):,} duties")
    pairings, master_result = run_column_generation(
        duty_graph,
        flights,
    )

    leftover_artificials = [
        flight_id
        for flight_id, value in master_result.artificial_values.items()
        if value > ARTIFICIAL_TOLERANCE
    ]
    if leftover_artificials:
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
        return

    print(f"Generated columns: {len(pairings)}")
    print(f"Restricted master LP objective: {master_result.objective}")

    progress(f"Starting final ILP with {len(pairings):,} pairings")
    ilp_result = solve_ilp(pairings, flights)
    if ilp_result is None:
        return
    solution, total_cost = ilp_result
    progress("Final ILP finished")
    chosen = selected_pairings(pairings, solution)
    output_path = save_selected_pairings(
        chosen,
        SELECTED_PAIRINGS_PATH,
        total_cost=total_cost,
    )
    print(f"Solution list dimensions: {len(solution)}")
    print(f"Total cost: {total_cost}")
    print(f"Selected pairings: {len(chosen)}")
    print(f"Wrote selected pairings to {output_path}")


if __name__ == "__main__":
    main()
