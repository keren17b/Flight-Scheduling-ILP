"""Pre-solver full-month coverage report using production legality functions.

The only non-default value is a ten-hour minimum rest passed to the production
duty-graph builder.  Pairing paths are counted exactly with dynamic programming
before deciding whether it is safe to materialize every Pairing object.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import timedelta
from functools import lru_cache
from time import perf_counter

from tests.diagnostics.diagnose_pairing_coverage import coverable_duties
from crew_pairing.data_paths import INPUT_DIR
from crew_pairing.duties import generate_duties
from crew_pairing.duty_graph import build_duty_graph
from crew_pairing.flights_graph import load_flight_network
from crew_pairing.pairings import MAX_DUTIES_PER_PAIRING, MAX_PAIRING_TIME


FLIGHTS_FILE = INPUT_DIR / "all_days.csv"
BASES_FILE = INPUT_DIR / "listOfBases.csv"
MIN_REST = timedelta(hours=10)


def exact_pairing_count(graph):
    """Count exactly the same closed paths saved by generate_pairings()."""
    total = 0
    by_base = defaultdict(int)

    for start in graph:
        if not start.start_airport.is_crew_base:
            continue

        original_base = start.start_airport.port_name

        @lru_cache(maxsize=None)
        def count_from(current, depth):
            count = int(
                current.end_airport.is_crew_base
                and current.end_airport.port_name == original_base
            )
            if depth >= MAX_DUTIES_PER_PAIRING:
                return count

            for next_duty in graph[current]:
                if next_duty.end_time - start.start_time > MAX_PAIRING_TIME:
                    continue
                count += count_from(next_duty, depth + 1)
            return count

        start_count = count_from(start, 1)
        total += start_count
        by_base[original_base] += start_count

    return total, dict(sorted(by_base.items()))


def main() -> None:
    started = perf_counter()
    _, flights, flight_graph = load_flight_network(FLIGHTS_FILE, BASES_FILE)
    after_flights = perf_counter()
    duties = generate_duties(flight_graph)
    after_duties = perf_counter()
    duty_graph = build_duty_graph(duties.values(), min_rest=MIN_REST)
    after_duty_graph = perf_counter()

    pairing_count, pairings_by_base = exact_pairing_count(duty_graph)
    after_count = perf_counter()
    useful_duties = coverable_duties(
        duty_graph, MAX_PAIRING_TIME, MAX_DUTIES_PER_PAIRING
    )
    covered = {
        flight.flight_id
        for duty in useful_duties
        for flight in duty.flights
    }
    uncovered = sorted(set(flights) - covered)
    after_coverage = perf_counter()

    print(f"flights={len(flights)}")
    print(f"flight_edges={sum(len(values) for values in flight_graph.values())}")
    print(f"duties={len(duties)}")
    print(f"duty_edges={sum(len(values) for values in duty_graph.values())}")
    print(f"pairings_exact={pairing_count}")
    print(f"pairings_by_base={pairings_by_base}")
    print(f"covered={len(covered)}")
    print(f"uncovered={len(uncovered)}")
    print(f"uncovered_ids={uncovered}")
    print(
        "seconds="
        f"load:{after_flights - started:.3f},"
        f"duties:{after_duties - after_flights:.3f},"
        f"duty_graph:{after_duty_graph - after_duties:.3f},"
        f"pairing_count:{after_count - after_duty_graph:.3f},"
        f"coverage:{after_coverage - after_count:.3f},"
        f"total:{after_coverage - started:.3f}"
    )


if __name__ == "__main__":
    main()
