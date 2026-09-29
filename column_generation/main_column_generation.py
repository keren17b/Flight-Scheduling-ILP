"""Temporary runner for the column-generation pairing path."""

from column_generation.column_generation import run_column_generation
from crew_pairing.duties import generate_duties
from crew_pairing.duty_graph import build_duty_graph
from crew_pairing.flights_graph import load_flight_network
from crew_pairing.data_paths import GENERATED_DIR, INPUT_DIR
from column_generation.master_ilp import solve_ilp


FLIGHTS_FILE_PATH = GENERATED_DIR / "week_1_with_padding.csv"
HUBS_FILE_PATH = INPUT_DIR / "listOfBases.csv"
SELECTION_THRESHOLD = 0.5
ARTIFICIAL_TOLERANCE = 1e-6


def main() -> None:
    airports, flights, graph = load_flight_network(FLIGHTS_FILE_PATH, HUBS_FILE_PATH)
    duties = generate_duties(graph)
    duty_graph = build_duty_graph(duties.values())
    pairings, _existing_signatures, master_result = run_column_generation(
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

    print(f"Generated columns: {len(pairings)}")
    print(f"Restricted master LP objective: {master_result.objective}")

    solution, total_cost = solve_ilp(pairings, flights)
    selected_count = sum(
        1 for value in solution.values() if value > SELECTION_THRESHOLD
    )
    print(f"Solution list dimensions: {len(solution)}")
    print(f"Total cost: {total_cost}")
    print(f"Selected pairings: {selected_count}")


if __name__ == "__main__":
    main()
