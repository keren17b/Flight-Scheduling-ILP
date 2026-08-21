"""Temporary runner for flight, duty, and pairing generation."""

from itertools import islice

from duties import generate_duties
from duty_graph import build_duty_graph
from flights_graph import load_flight_network
from pairing_to_metrix import pairings_to_matrix
from pairings import generate_pairings
from solver import simple_model


FLIGHTS_FILE_PATH = "week_1.csv"
HUBS_FILE_PATH = "listOfBases.csv"
OUTPUT_PREVIEW_LIMIT = 10
SELECTION_THRESHOLD = 0.5


def main() -> None:
    airports, flights, graph = load_flight_network(FLIGHTS_FILE_PATH, HUBS_FILE_PATH)
    duties = generate_duties(graph)
    duty_graph = build_duty_graph(duties.values())
    pairings = generate_pairings(duty_graph)
    matrix, costs = pairings_to_matrix(flights, pairings)
    print(f"Matrix dimensions: {matrix.shape}")
    solution, total_cost = simple_model(matrix, costs)
    selected_count = sum(1 for value in solution if value > SELECTION_THRESHOLD)
    print(f"Solution list dimensions: {len(solution)}")
    print(f"Total cost: {total_cost}")
    print(f"Selected pairings: {selected_count}")
"""

    print(f"Generated {len(duties)} duties:\n")
    for duty_id, duty in islice(duties.items(), OUTPUT_PREVIEW_LIMIT):
        flight_ids = " -> ".join(flight.flight_id for flight in duty.flights)
        print(
            f"{duty_id}: {flight_ids} | "
            f"{duty.start_airport.port_name} -> {duty.end_airport.port_name} | "
            f"{duty.start_time} - {duty.end_time} | "
            f"total time: {duty.total_time}"
        )
    if len(duties) > OUTPUT_PREVIEW_LIMIT:
        print(f"... {len(duties) - OUTPUT_PREVIEW_LIMIT} more duties not shown")

    edge_count = sum(len(neighbors) for neighbors in duty_graph.values())
    print(f"\nDuty graph: {len(duty_graph)} nodes, {edge_count} edges")
"""
    print(f"\nGenerated {len(pairings)} pairings:\n")
    """
    for pairing_id, pairing in islice(pairings.items(), OUTPUT_PREVIEW_LIMIT):
        duty_ids = " -> ".join(duty.duty_id for duty in pairing.duties)
        flight_ids = " -> ".join(
            flight.flight_id
            for duty in pairing.duties
            for flight in duty.flights
        )
        print(
            f"{pairing_id}: duties [{duty_ids}] | flights [{flight_ids}] | "
            f"{pairing.start_airport.port_name} -> "
            f"{pairing.end_airport.port_name} | "
            f"{pairing.start_time} - {pairing.end_time} | "
            f"total time: {pairing.total_time} | cost: {pairing.cost}"
        )
    if len(pairings) > OUTPUT_PREVIEW_LIMIT:
        print(f"... {len(pairings) - OUTPUT_PREVIEW_LIMIT} more pairings not shown")
"""

if __name__ == "__main__":
    main()
