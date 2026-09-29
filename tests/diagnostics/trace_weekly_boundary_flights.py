"""Trace the six week-one flights uncovered with ten-hour minimum rest."""

from __future__ import annotations

from datetime import timedelta
from functools import lru_cache

from crew_pairing.duties import Duty, generate_duties
from crew_pairing.data_paths import INPUT_DIR
from crew_pairing.duty_graph import build_duty_graph
from crew_pairing.flights_graph import Flight, load_flight_network
from crew_pairing.pairings import MAX_DUTIES_PER_PAIRING, MAX_PAIRING_TIME


TARGET_IDS = (
    "LEG_07_5",
    "LEG_07_9",
    "LEG_07_14",
    "LEG_07_17",
    "LEG_07_23",
    "LEG_07_33",
)
MIN_REST = timedelta(hours=10)


def fmt(value: timedelta) -> str:
    minutes = int(value.total_seconds() // 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h{minutes:02d}m"


def sequence(duty: Duty) -> str:
    return " -> ".join(flight.flight_id for flight in duty.flights)


def find_closed_pairing(graph, candidate_starts: list[Duty]):
    for start in candidate_starts:
        original_base = start.start_airport.port_name

        @lru_cache(maxsize=None)
        def suffix(current: Duty, depth: int):
            if (
                current.end_airport.is_crew_base
                and current.end_airport.port_name == original_base
            ):
                return (current,)
            if depth >= MAX_DUTIES_PER_PAIRING:
                return None
            for next_duty in graph[current]:
                if next_duty.end_time - start.start_time > MAX_PAIRING_TIME:
                    continue
                result = suffix(next_duty, depth + 1)
                if result is not None:
                    return (current,) + result
            return None

        result = suffix(start, 1)
        if result is not None:
            return result
    return None


def build(csv_path: str):
    _, flights, flight_graph = load_flight_network(csv_path, INPUT_DIR / "listOfBases.csv")
    duties = generate_duties(flight_graph)
    duty_graph = build_duty_graph(duties.values(), min_rest=MIN_REST)
    return flights, duties, duty_graph


def main() -> None:
    week_flights, week_duties, week_graph = build(INPUT_DIR / "week_1.csv")
    full_flights, full_duties, full_graph = build(INPUT_DIR / "all_days.csv")

    week_latest_departure = max(
        flight.departure_datetime for flight in week_flights.values()
    )
    print(f"week latest departure: {week_latest_departure}")

    for target_id in TARGET_IDS:
        week_target = week_flights[target_id]
        full_target = full_flights[target_id]
        week_target_duties = [
            duty for duty in week_duties.values() if week_target in duty.flights
        ]
        full_target_duties = [
            duty for duty in full_duties.values() if full_target in duty.flights
        ]
        week_outgoing = sum(len(week_graph[duty]) for duty in week_target_duties)

        missing_future_departures = sorted(
            (
                flight
                for flight_id, flight in full_flights.items()
                if flight_id not in week_flights
                and flight.origin.port_name == full_target.destination.port_name
                and flight.departure_datetime > full_target.arrival_datetime
                and flight.departure_datetime - full_target.arrival_datetime
                <= timedelta(hours=48)
            ),
            key=lambda flight: flight.departure_datetime,
        )

        candidate_starts = sorted(
            (
                duty
                for duty in full_target_duties
                if duty.start_airport.is_crew_base
            ),
            key=lambda duty: (len(duty.flights), duty.start_time),
        )
        witness = find_closed_pairing(full_graph, candidate_starts)

        print("\n" + "=" * 90)
        print(
            f"{target_id}: {week_target.origin.port_name}->"
            f"{week_target.destination.port_name}, "
            f"{week_target.departure_datetime}..{week_target.arrival_datetime}"
        )
        print(
            f"week duties containing target={len(week_target_duties)}, "
            f"base-starting={sum(d.start_airport.is_crew_base for d in week_target_duties)}, "
            f"outgoing duty edges={week_outgoing}"
        )
        if missing_future_departures:
            first = missing_future_departures[0]
            print(
                f"first post-week departure at {full_target.destination.port_name}: "
                f"{first.flight_id} at {first.departure_datetime}, "
                f"gap after target={fmt(first.departure_datetime - full_target.arrival_datetime)}"
            )
        else:
            print("no post-week departure within 48 hours")

        if witness is None:
            print("no full-month closed-pairing witness")
            continue
        print(
            f"full-month witness: base={witness[0].start_airport.port_name}, "
            f"duties={len(witness)}, duration="
            f"{fmt(witness[-1].end_time - witness[0].start_time)}"
        )
        for index, duty in enumerate(witness):
            if index:
                rest = duty.start_time - witness[index - 1].end_time
                print(f"  rest={fmt(rest)}")
            print(
                f"  {duty.duty_id} [{sequence(duty)}] "
                f"{duty.start_airport.port_name}->{duty.end_airport.port_name} "
                f"{duty.start_time}..{duty.end_time}"
            )


if __name__ == "__main__":
    main()
