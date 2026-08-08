"""Flight connection graph built from scheduling CSV files."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Optional


DEFAULT_MIN_CONNECTION = timedelta(minutes=30)
DEFAULT_MAX_CONNECTION = timedelta(hours=8)

FLIGHT_ID_FIELD = "leg_nb"
ORIGIN_FIELD = "airport_dep"
DEPARTURE_DATE_FIELD = "date_dep"
DEPARTURE_TIME_FIELD = "hour_dep"
DESTINATION_FIELD = "airport_arr"
ARRIVAL_DATE_FIELD = "date_arr"
ARRIVAL_TIME_FIELD = "hour_arr"

AIRPORT_CODE_FIELD = "airport"
AIRPORT_STATUS_FIELD = "status"

DATETIME_FORMAT = "%Y-%m-%d %H:%M"


@dataclass(frozen=True)
class Airport:
    port_name: str
    is_crew_base: int  # 1 = hub / crew base, 0 = not


@dataclass(frozen=True)
class Flight:
    flight_id: str
    origin: Airport
    destination: Airport
    departure_datetime: datetime
    arrival_datetime: datetime


FlightGraph = Dict[Flight, List[Flight]]


def _normalize_header(name: str) -> str:
    return name.lstrip("#").strip().lower()


def _clean_row(row: Mapping[str, str]) -> Dict[str, str]:
    return {_normalize_header(key): value.strip() for key, value in row.items() if key is not None}


def _parse_datetime(date_str: str, time_str: str) -> datetime:
    return datetime.strptime(f"{date_str} {time_str}", DATETIME_FORMAT)


def _get_or_create_airport(
    airports: Dict[str, Airport],
    port_name: str,
    hub_status: Mapping[str, int],
) -> Airport:
    if port_name not in airports:
        airports[port_name] = Airport(
            port_name=port_name,
            is_crew_base=hub_status.get(port_name, 0),
        )
    return airports[port_name]


def load_hub_status(bases_csv_path: str | Path) -> Dict[str, int]:
    """Load airport -> hub status (1 or 0) from a listOfBases-style CSV."""
    hub_status: Dict[str, int] = {}

    with open(bases_csv_path, newline="", encoding="utf-8") as csv_file:
        reader = csv.DictReader(csv_file, skipinitialspace=True)
        for raw_row in reader:
            row = _clean_row(raw_row)
            port_name = row[AIRPORT_CODE_FIELD]
            hub_status[port_name] = int(row[AIRPORT_STATUS_FIELD])

    return hub_status


def load_flights(
    flights_csv_path: str | Path,
    hubs_csv_path: str | Path,
) -> tuple[Dict[str, Airport], Dict[str, Flight]]:
    """
    Load flights and airports from CSV files.

    Returns:
        airports: unique airports keyed by port_name
        flights: flights keyed by flight_id
    """
    hub_status = load_hub_status(hubs_csv_path)
    airports: Dict[str, Airport] = {
        port_name: Airport(port_name=port_name, is_crew_base=status)
        for port_name, status in hub_status.items()
    }
    flights: Dict[str, Flight] = {}

    with open(flights_csv_path, newline="", encoding="utf-8") as csv_file:
        reader = csv.DictReader(csv_file, skipinitialspace=True)
        for raw_row in reader:
            row = _clean_row(raw_row)

            flight_id = row[FLIGHT_ID_FIELD]
            origin = _get_or_create_airport(airports, row[ORIGIN_FIELD], hub_status)
            destination = _get_or_create_airport(airports, row[DESTINATION_FIELD], hub_status)
            departure_datetime = _parse_datetime(
                row[DEPARTURE_DATE_FIELD],
                row[DEPARTURE_TIME_FIELD],
            )
            arrival_datetime = _parse_datetime(
                row[ARRIVAL_DATE_FIELD],
                row[ARRIVAL_TIME_FIELD],
            )

            flights[flight_id] = Flight(
                flight_id=flight_id,
                origin=origin,
                destination=destination,
                departure_datetime=departure_datetime,
                arrival_datetime=arrival_datetime,
            )

    return airports, flights


def can_connect(
    first: Flight,
    second: Flight,
    min_connection: timedelta = DEFAULT_MIN_CONNECTION,
    max_connection: timedelta = DEFAULT_MAX_CONNECTION,
) -> bool:
    """Return True if second can follow first as a valid connection."""
    if first.destination.port_name != second.origin.port_name:
        return False
    if second.departure_datetime <= first.arrival_datetime:
        return False

    connection_time = second.departure_datetime - first.arrival_datetime
    return min_connection <= connection_time <= max_connection


def build_flight_graph(
    flights: Iterable[Flight],
    min_connection: timedelta = DEFAULT_MIN_CONNECTION,
    max_connection: timedelta = DEFAULT_MAX_CONNECTION,
) -> FlightGraph:
    """
    Build an adjacency list where each node is a Flight.

    Edge F1 -> F2 exists only when destination/origin match and the
    connection time is within [min_connection, max_connection].
    """
    flight_list = list(flights)
    graph: FlightGraph = {flight: [] for flight in flight_list}

    for first in flight_list:
        for second in flight_list:
            if first is second:
                continue
            if can_connect(first, second, min_connection, max_connection):
                graph[first].append(second)

    return graph


def load_flight_network(
    flights_csv_path: str | Path,
    hubs_csv_path: str | Path,
    min_connection: timedelta = DEFAULT_MIN_CONNECTION,
    max_connection: timedelta = DEFAULT_MAX_CONNECTION,
) -> tuple[Dict[str, Airport], Dict[str, Flight], FlightGraph]:
    """
    Load CSV inputs and build the flight connection graph.

    Returns:
        airports, flights, adjacency_list
    """
    airports, flights = load_flights(flights_csv_path, hubs_csv_path)
    graph = build_flight_graph(
        flights.values(),
        min_connection=min_connection,
        max_connection=max_connection,
    )
    return airports, flights, graph
