"""Temporary runner for flight-network loading, duty generation, and duty graph."""

from duties import generate_duties
from duty_graph import build_duty_graph
from graph import load_flight_network


FLIGHTS_FILE_PATH = "day_1.csv"
HUBS_FILE_PATH = "listOfBases.csv"


def main() -> None:
    _, _, graph = load_flight_network(FLIGHTS_FILE_PATH, HUBS_FILE_PATH)
    duties = generate_duties(graph)
    duty_graph = build_duty_graph(duties.values())

    print(f"Generated {len(duties)} duties:\n")
    for duty_id, duty in duties.items():
        flight_ids = " -> ".join(flight.flight_id for flight in duty.flights)
        print(
            f"{duty_id}: {flight_ids} | "
            f"{duty.start_airport.port_name} -> {duty.end_airport.port_name} | "
            f"{duty.start_time} - {duty.end_time} | "
            f"total time: {duty.total_time}"
        )

    edge_count = sum(len(neighbors) for neighbors in duty_graph.values())
    print(f"\nDuty graph: {len(duty_graph)} nodes, {edge_count} edges")


if __name__ == "__main__":
    main()
