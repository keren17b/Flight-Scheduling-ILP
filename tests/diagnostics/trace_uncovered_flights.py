"""Exhaustive trace for the three flights uncovered with ten-hour rest.

This is a read-only diagnostic.  It imports the production graph/duty logic,
uses the existing production limits, and changes only the minimum duty-to-duty
rest passed to ``build_duty_graph`` from its code default of 12 hours to the
requested 10 hours.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import timedelta
from typing import Iterable

from crew_pairing.data_paths import INPUT_DIR
from crew_pairing.duties import MAX_ELAPSED_DUTY_TIME as MAX_DUTY_TIME, Duty, generate_duties
from crew_pairing.duty_graph import MAX_LAYOVER_BETWEEN_DUTIES, build_duty_graph
from crew_pairing.flights_graph import (
    DEFAULT_MAX_CONNECTION,
    DEFAULT_MIN_CONNECTION,
    Flight,
    can_connect,
    load_flight_network,
)
from crew_pairing.pairings import MAX_DUTIES_PER_PAIRING, MAX_PAIRING_TIME


TARGET_IDS = ("LEG_27_0", "LEG_27_12", "LEG_30_1")
TEN_HOURS = timedelta(hours=10)


def duration(value: timedelta) -> str:
    total_minutes = int(value.total_seconds() // 60)
    sign = "-" if total_minutes < 0 else ""
    total_minutes = abs(total_minutes)
    hours, minutes = divmod(total_minutes, 60)
    return f"{sign}{hours}h{minutes:02d}m"


def flight_sequence(duty: Duty) -> str:
    return " -> ".join(flight.flight_id for flight in duty.flights)


def direct_candidate_reason(first: Flight, second: Flight) -> str:
    if first.destination.port_name != second.origin.port_name:
        return "wrong airport"
    if second.departure_datetime <= first.arrival_datetime:
        return "not chronological"

    wait = second.departure_datetime - first.arrival_datetime
    if wait < DEFAULT_MIN_CONNECTION:
        return (
            f"REJECT connection wait {duration(wait)} < minimum "
            f"{duration(DEFAULT_MIN_CONNECTION)}"
        )
    if wait > DEFAULT_MAX_CONNECTION:
        return (
            f"REJECT connection wait {duration(wait)} > maximum "
            f"{duration(DEFAULT_MAX_CONNECTION)}"
        )

    two_flight_span = second.arrival_datetime - first.departure_datetime
    if two_flight_span > MAX_DUTY_TIME:
        return (
            f"flight edge exists, but REJECT two-flight duty length "
            f"{duration(two_flight_span)} > {duration(MAX_DUTY_TIME)}"
        )
    return (
        f"ACCEPT wait={duration(wait)}, two-flight duty="
        f"{duration(two_flight_span)}"
    )


def print_direct_candidates(target: Flight, flights: Iterable[Flight]) -> None:
    flights = list(flights)
    predecessors = sorted(
        (
            flight
            for flight in flights
            if flight.flight_id != target.flight_id
            and flight.destination.port_name == target.origin.port_name
            and flight.arrival_datetime < target.departure_datetime
        ),
        key=lambda flight: flight.arrival_datetime,
        reverse=True,
    )
    successors = sorted(
        (
            flight
            for flight in flights
            if flight.flight_id != target.flight_id
            and flight.origin.port_name == target.destination.port_name
            and flight.departure_datetime > target.arrival_datetime
        ),
        key=lambda flight: flight.departure_datetime,
    )

    print("  Same-duty predecessor candidates at", target.origin.port_name)
    relevant_predecessors = [
        flight
        for flight in predecessors
        if target.departure_datetime - flight.arrival_datetime
        <= MAX_LAYOVER_BETWEEN_DUTIES
    ]
    if not relevant_predecessors:
        print("    none in the preceding 48-hour window")
    for flight in relevant_predecessors:
        print(
            f"    {flight.flight_id} {flight.origin.port_name}->"
            f"{flight.destination.port_name}, arrives "
            f"{flight.arrival_datetime:%Y-%m-%d %H:%M}: "
            f"{direct_candidate_reason(flight, target)}"
        )

    print("  Same-duty successor candidates at", target.destination.port_name)
    relevant_successors = [
        flight
        for flight in successors
        if flight.departure_datetime - target.arrival_datetime
        <= MAX_LAYOVER_BETWEEN_DUTIES
    ]
    if not relevant_successors:
        print("    none in the following 48-hour window")
    for flight in relevant_successors:
        print(
            f"    {flight.flight_id} {flight.origin.port_name}->"
            f"{flight.destination.port_name}, departs "
            f"{flight.departure_datetime:%Y-%m-%d %H:%M}: "
            f"{direct_candidate_reason(target, flight)}"
        )

    if successors:
        first = successors[0]
        print(
            f"  First in-dataset future departure from destination: "
            f"{first.flight_id} at {first.departure_datetime:%Y-%m-%d %H:%M}"
        )
    else:
        print("  No future departure from destination exists in the dataset")


def reachable_target_duties(graph, target_duties: set[Duty]):
    """Return target duties reachable by a legal pairing prefix."""
    reached = defaultdict(list)
    for start in graph:
        if not start.start_airport.is_crew_base:
            continue
        stack = [(start, (start,))]
        seen = set()
        while stack:
            current, path = stack.pop()
            state = (current, len(path))
            if state in seen:
                continue
            seen.add(state)
            if current in target_duties:
                reached[current].append(path)
            if len(path) >= MAX_DUTIES_PER_PAIRING:
                continue
            for next_duty in graph[current]:
                if next_duty.end_time - start.start_time > MAX_PAIRING_TIME:
                    continue
                stack.append((next_duty, path + (next_duty,)))
    return reached


def pairing_suffix_closures(graph, prefix: tuple[Duty, ...]):
    """Find closed suffixes after a prefix, preserving pairing limits."""
    start = prefix[0]
    results = []
    stack = [prefix]
    while stack:
        path = stack.pop()
        current = path[-1]
        if (
            current.end_airport.is_crew_base
            and current.end_airport.port_name == start.start_airport.port_name
        ):
            results.append(path)
        if len(path) >= MAX_DUTIES_PER_PAIRING:
            continue
        for next_duty in graph[current]:
            if next_duty.end_time - start.start_time > MAX_PAIRING_TIME:
                continue
            stack.append(path + (next_duty,))
    return results


def main() -> None:
    _, flights, flight_graph = load_flight_network(
        INPUT_DIR / "all_days.csv", INPUT_DIR / "listOfBases.csv"
    )
    duties = generate_duties(flight_graph)
    duty_graph = build_duty_graph(duties.values(), min_rest=TEN_HOURS)
    reverse_duty_graph = defaultdict(list)
    for previous, next_duties in duty_graph.items():
        for next_duty in next_duties:
            reverse_duty_graph[next_duty].append(previous)

    print(
        f"Limits: connection={duration(DEFAULT_MIN_CONNECTION)}.."
        f"{duration(DEFAULT_MAX_CONNECTION)}, duty<="
        f"{duration(MAX_DUTY_TIME)}, rest={duration(TEN_HOURS)}.."
        f"{duration(MAX_LAYOVER_BETWEEN_DUTIES)}, pairing<="
        f"{MAX_PAIRING_TIME.days}d/{MAX_DUTIES_PER_PAIRING} duties"
    )
    print(
        f"Dataset: {min(f.departure_datetime for f in flights.values())} .. "
        f"{max(f.arrival_datetime for f in flights.values())}"
    )

    for target_id in TARGET_IDS:
        target = flights[target_id]
        print("\n" + "=" * 100)
        print(
            f"{target.flight_id}: {target.origin.port_name}->"
            f"{target.destination.port_name}, "
            f"{target.departure_datetime:%Y-%m-%d %H:%M} .. "
            f"{target.arrival_datetime:%Y-%m-%d %H:%M}"
        )
        print_direct_candidates(target, flights.values())

        target_duties = {
            duty for duty in duties.values() if target in duty.flights
        }
        reached = reachable_target_duties(duty_graph, target_duties)
        print(f"  Generated duties containing flight: {len(target_duties)}")
        for duty in sorted(target_duties, key=lambda item: item.duty_id):
            incoming = reverse_duty_graph[duty]
            outgoing = duty_graph[duty]
            start_allowed = bool(duty.start_airport.is_crew_base)
            prefixes = reached.get(duty, [])
            closures = []
            for prefix in prefixes:
                closures.extend(pairing_suffix_closures(duty_graph, prefix))
            print(
                f"    {duty.duty_id} [{flight_sequence(duty)}] "
                f"{duty.start_airport.port_name}->"
                f"{duty.end_airport.port_name}, "
                f"{duty.start_time:%Y-%m-%d %H:%M}.."
                f"{duty.end_time:%Y-%m-%d %H:%M}, "
                f"length={duration(duty.total_time)}"
            )
            print(
                f"      can_start_pairing={start_allowed}; "
                f"previous_duties={len(incoming)}; "
                f"next_duties={len(outgoing)}; "
                f"reachable_prefixes={len(prefixes)}; "
                f"same-base_closures={len(closures)}"
            )
            if incoming:
                rests = [duty.start_time - previous.end_time for previous in incoming]
                print(
                    f"      accepted previous-duty rest range: "
                    f"{duration(min(rests))}..{duration(max(rests))}"
                )
            if outgoing:
                rests = [following.start_time - duty.end_time for following in outgoing]
                print(
                    f"      accepted next-duty rest range: "
                    f"{duration(min(rests))}..{duration(max(rests))}"
                )
                for following in outgoing:
                    print(
                        f"        -> {following.duty_id} "
                        f"[{flight_sequence(following)}], rest="
                        f"{duration(following.start_time - duty.end_time)}"
                    )

        print(
            f"  Result: reachable target duties={sum(bool(reached.get(d)) for d in target_duties)}, "
            f"closed pairings containing target=0"
        )


if __name__ == "__main__":
    main()
