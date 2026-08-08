"""Temporary runner for load_flight_network."""

from graph import load_flight_network

FLIGHTS_FILE_PATH = r"c:\Users\97254\OneDrive - Tel Hai College - Students\שולחן העבודה\מדמח\פרויקט גמר\data sets\GERAD\instance1\day_1.csv"
HUBS_FILE_PATH = r"c:\Users\97254\OneDrive - Tel Hai College - Students\שולחן העבודה\מדמח\פרויקט גמר\data sets\GERAD\instance1\listOfBases.csv"


def main() -> None:
    airports, flights, graph = load_flight_network(FLIGHTS_FILE_PATH, HUBS_FILE_PATH)

    print("=== Airports ===")
    for port_name, airport in airports.items():
        print(f"{port_name}: is_crew_base={airport.is_crew_base}")

    print("\n=== Flights ===")
    for flight_id, flight in flights.items():
        print(
            f"{flight_id}: {flight.origin.port_name} -> {flight.destination.port_name} "
            f"({flight.departure_datetime} - {flight.arrival_datetime})"
        )

    print("\n=== Graph (flight connections) ===")
    for flight, successors in graph.items():
        successor_ids = [s.flight_id for s in successors]
        print(f"{flight.flight_id} -> {successor_ids}")


if __name__ == "__main__":
    main()
