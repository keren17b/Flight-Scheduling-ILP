"""Temporary runner for flight, duty, and pairing generation."""

from crew_pairing.duties import generate_duties
from crew_pairing.duty_graph import build_duty_graph
from crew_pairing.flights_graph import load_flight_network
from crew_pairing.data_paths import GENERATED_DIR, INPUT_DIR
from crew_pairing.padding_flights import flight_constraint_tags
from historical_code.pairing_to_metrix import pairings_to_matrix
from crew_pairing.pairings import generate_pairings
from historical_code.solver import simple_model


FLIGHTS_FILE_PATH = GENERATED_DIR / "week_1_with_padding.csv"
HUBS_FILE_PATH = INPUT_DIR / "listOfBases.csv"
SELECTION_THRESHOLD = 0.5


def main() -> None:
    airports, flights, graph = load_flight_network(FLIGHTS_FILE_PATH, HUBS_FILE_PATH)
    duties = generate_duties(graph)
    duty_graph = build_duty_graph(duties.values())
    pairings = generate_pairings(duty_graph)
    matrix, costs = pairings_to_matrix(flights, pairings)
    flight_tags = flight_constraint_tags(flights)
    print(f"Matrix dimensions: {matrix.shape}")
    solution, total_cost = simple_model(matrix, costs, flight_tags)
    selected_count = sum(1 for value in solution if value > SELECTION_THRESHOLD)
    print(f"Solution list dimensions: {len(solution)}")
    print(f"Total cost: {total_cost}")
    print(f"Selected pairings: {selected_count}")

if __name__ == "__main__":
    main()
