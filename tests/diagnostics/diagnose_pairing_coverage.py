"""Diagnostic runner for flights that appear in no legal closed pairing.

This file deliberately does not call the ILP solver.  A zero column in the
pairing/flight matrix is already enough to make the set-partitioning model
infeasible, so the diagnostic works one stage earlier.  It follows the same
duty and pairing constraints as the production pipeline, but collapses paths
that reach the same duty at the same depth.  That makes full-horizon coverage
analysis possible without storing every generated pairing.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from dataclasses import dataclass
from datetime import timedelta
from typing import Dict, Iterable, Set, Tuple

from crew_pairing.duties import Duty, generate_duties
from crew_pairing.data_paths import INPUT_DIR
from crew_pairing.duty_graph import DutyGraph, build_duty_graph
from crew_pairing.flights_graph import Flight, load_flight_network


@dataclass(frozen=True)
class Limits:
    min_connection_hours: float = 0.5
    max_connection_hours: float = 8.0
    max_duty_hours: float = 8.0
    min_rest_hours: float = 12.0
    max_layover_hours: float = 48.0
    max_pairing_days: float = 5.0
    max_duties: int = 5


def hours(value: float) -> timedelta:
    return timedelta(hours=value)


def coverable_duties(
    graph: DutyGraph,
    max_pairing_time: timedelta,
    max_duties: int,
) -> Set[Duty]:
    """Return duties lying on at least one legal, closed pairing path.

    The production DFS distinguishes every complete path.  For coverage, paths
    reaching the same (depth, duty) state are equivalent: future legality only
    depends on the first duty, current duty, depth, and original base.  Parent
    sets retain all prefixes, allowing an exact backwards mark from every
    closed state.
    """

    covered: Set[Duty] = set()

    for start in graph:
        if not start.start_airport.is_crew_base:
            continue

        states: Set[Tuple[int, Duty]] = {(1, start)}
        parents: Dict[Tuple[int, Duty], Set[Tuple[int, Duty]]] = defaultdict(set)
        closed: Set[Tuple[int, Duty]] = set()

        for depth in range(1, max_duties + 1):
            current_layer = [state for state in states if state[0] == depth]
            for state in current_layer:
                _, duty = state
                if (
                    duty.end_airport.is_crew_base
                    and duty.end_airport.port_name == start.start_airport.port_name
                ):
                    closed.add(state)

                if depth == max_duties:
                    continue

                for next_duty in graph.get(duty, []):
                    if next_duty.end_time - start.start_time > max_pairing_time:
                        continue
                    next_state = (depth + 1, next_duty)
                    states.add(next_state)
                    parents[next_state].add(state)

        stack = list(closed)
        useful_states = set(closed)
        while stack:
            state = stack.pop()
            covered.add(state[1])
            for parent in parents.get(state, ()):
                if parent not in useful_states:
                    useful_states.add(parent)
                    stack.append(parent)

    return covered


def nearest_gaps(flight: Flight, flights: Iterable[Flight]) -> tuple[str, str]:
    predecessors = [
        flight.departure_datetime - other.arrival_datetime
        for other in flights
        if other.destination.port_name == flight.origin.port_name
        and other.arrival_datetime < flight.departure_datetime
    ]
    successors = [
        other.departure_datetime - flight.arrival_datetime
        for other in flights
        if other.origin.port_name == flight.destination.port_name
        and other.departure_datetime > flight.arrival_datetime
    ]

    def describe(gaps: list[timedelta]) -> str:
        if not gaps:
            return "none"
        gap = min(gaps)
        return f"{gap.total_seconds() / 3600:.2f}h"

    return describe(predecessors), describe(successors)


def analyze(csv_path: str, limits: Limits, print_uncovered: bool = True):
    _, flights, flight_graph = load_flight_network(
        csv_path,
        INPUT_DIR / "listOfBases.csv",
        min_connection=hours(limits.min_connection_hours),
        max_connection=hours(limits.max_connection_hours),
    )
    duties = generate_duties(
        flight_graph,
        max_duty_time=hours(limits.max_duty_hours),
    )
    duty_graph = build_duty_graph(
        duties.values(),
        min_rest=hours(limits.min_rest_hours),
        max_layover=hours(limits.max_layover_hours),
    )
    useful_duties = coverable_duties(
        duty_graph,
        timedelta(days=limits.max_pairing_days),
        limits.max_duties,
    )
    covered_ids = {
        flight.flight_id
        for duty in useful_duties
        for flight in duty.flights
    }
    uncovered = [flight for flight_id, flight in flights.items() if flight_id not in covered_ids]

    print(
        f"{csv_path}: flights={len(flights)}, flight_edges="
        f"{sum(len(v) for v in flight_graph.values())}, duties={len(duties)}, "
        f"duty_edges={sum(len(v) for v in duty_graph.values())}, "
        f"covered={len(covered_ids)}, uncovered={len(uncovered)}"
    )

    if print_uncovered:
        all_flights = list(flights.values())
        for flight in uncovered:
            incoming = sum(flight in neighbors for neighbors in flight_graph.values())
            outgoing = len(flight_graph[flight])
            predecessor_gap, successor_gap = nearest_gaps(flight, all_flights)
            print(
                f"  {flight.flight_id}: {flight.origin.port_name}->"
                f"{flight.destination.port_name}, "
                f"{flight.departure_datetime:%Y-%m-%d %H:%M}-"
                f"{flight.arrival_datetime:%H:%M}, "
                f"base_flags={flight.origin.is_crew_base}/"
                f"{flight.destination.is_crew_base}, "
                f"legal_same_duty_edges={incoming}/{outgoing}, "
                f"nearest_any_airport_gaps={predecessor_gap}/{successor_gap}"
            )

    return flights, covered_ids, uncovered


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("csv_path", nargs="?", default=INPUT_DIR / "week_1.csv")
    parser.add_argument("--min-connection", type=float, default=0.5)
    parser.add_argument("--max-connection", type=float, default=8.0)
    parser.add_argument("--max-duty", type=float, default=8.0)
    parser.add_argument("--min-rest", type=float, default=12.0)
    parser.add_argument("--max-layover", type=float, default=48.0)
    parser.add_argument("--max-pairing-days", type=float, default=5.0)
    parser.add_argument("--max-duties", type=int, default=5)
    args = parser.parse_args()

    analyze(
        args.csv_path,
        Limits(
            min_connection_hours=args.min_connection,
            max_connection_hours=args.max_connection,
            max_duty_hours=args.max_duty,
            min_rest_hours=args.min_rest,
            max_layover_hours=args.max_layover,
            max_pairing_days=args.max_pairing_days,
            max_duties=args.max_duties,
        ),
    )


if __name__ == "__main__":
    main()
