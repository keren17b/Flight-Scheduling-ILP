"""Check exact per-flight pairing reachability without pricing or optimization.

For each base and exact duty count, retain the latest possible prefix start
and earliest possible suffix finish. Those labels dominate other paths for
the elapsed-time limit. Joining labels at a duty identifies every duty that
can belong to a legal closed pairing, without enumerating all pairings.

This is a necessary feasibility check, not a simultaneous exact-cover solve.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import date, datetime, timedelta
import heapq
import json
import os
from pathlib import Path
import sys
from time import monotonic

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("ILP_PROGRESS", "0")

from crew_pairing import config
from crew_pairing.duties import generate_duties
from crew_pairing.flights_graph import load_flight_network


UNREACHABLE = -1
EPOCH = datetime(2000, 1, 1)


def week_intervals(week):
    """Required week and three departure-date padding days on each side."""
    start = date(2000, 1, 1) + timedelta(days=7 * (week - 1))
    end = start + timedelta(days=6)
    return (start, end), (
        (start - timedelta(days=3), start - timedelta(days=1)),
        (end + timedelta(days=1), end + timedelta(days=3)),
    )


def is_required_for_week(flight, week):
    start, end = week_intervals(week)[0]
    return start <= flight.departure_datetime.date() <= end


def closed_pairing_duties(duties, max_duties, max_pairing_time, min_rest, max_rest):
    """Return exact membership mask and one witness path per marked duty.

    Connections are chronological, so joining a prefix and suffix cannot
    repeat a duty or flight. For each fixed base/count/duty, a later prefix
    start and an earlier suffix end can only improve elapsed-time legality.
    Sliding-window heaps implement airport/rest connections without building
    the quadratic duty graph. No Top-K or search budget is applied.
    """
    count = len(duties)
    starts = np.array([int((d.start_time - EPOCH).total_seconds()) for d in duties])
    ends = np.array([int((d.end_time - EPOCH).total_seconds()) for d in duties])
    starts_at, ends_at = defaultdict(list), defaultdict(list)
    for index, duty in enumerate(duties):
        starts_at[duty.start_airport.port_name].append(index)
        ends_at[duty.end_airport.port_name].append(index)
    for indices in starts_at.values():
        indices.sort(key=lambda i: (starts[i], i))
    for indices in ends_at.values():
        indices.sort(key=lambda i: (ends[i], i))
    bases = sorted({d.start_airport.port_name for d in duties if d.start_airport.is_crew_base})
    max_span = int(max_pairing_time.total_seconds())
    rest_low, rest_high = int(min_rest.total_seconds()), int(max_rest.total_seconds())
    covered = np.zeros(count, dtype=bool)
    witnesses = {}

    def extend(previous, forward):
        result = np.full(count, UNREACHABLE, dtype=np.int64)
        parents = np.full(count, UNREACHABLE, dtype=np.int32)
        queries = starts_at if forward else ends_at
        candidates = ends_at if forward else starts_at
        query_times = starts if forward else ends
        candidate_times = ends if forward else starts
        for airport, query_indices in queries.items():
            candidate_indices = candidates.get(airport, ())
            position, heap = 0, []
            for index in query_indices:
                when = int(query_times[index])
                low = when - rest_high if forward else when + rest_low
                high = when - rest_low if forward else when + rest_high
                while position < len(candidate_indices):
                    candidate = candidate_indices[position]
                    candidate_time = int(candidate_times[candidate])
                    if candidate_time > high:
                        break
                    value = int(previous[candidate])
                    if value != UNREACHABLE:
                        heapq.heappush(heap, (-value if forward else value, candidate, candidate_time))
                    position += 1
                while heap and heap[0][2] < low:
                    heapq.heappop(heap)
                if heap:
                    score, parent, _ = heap[0]
                    value = -score if forward else score
                    span = int(ends[index]) - value if forward else value - int(starts[index])
                    if span <= max_span:
                        result[index], parents[index] = value, parent
        return result, parents

    for base in bases:
        forward = [np.full(count, UNREACHABLE, dtype=np.int64)]
        backward = [np.full(count, UNREACHABLE, dtype=np.int64)]
        predecessors = [None]
        successors = [None]
        first = np.full(count, UNREACHABLE, dtype=np.int64)
        last = np.full(count, UNREACHABLE, dtype=np.int64)
        for index, duty in enumerate(duties):
            if ends[index] - starts[index] <= max_span:
                if duty.start_airport.port_name == base:
                    first[index] = starts[index]
                if duty.end_airport.port_name == base:
                    last[index] = ends[index]
        forward.append(first)
        backward.append(last)
        predecessors.append(np.full(count, UNREACHABLE, dtype=np.int32))
        successors.append(np.full(count, UNREACHABLE, dtype=np.int32))
        for depth in range(2, max_duties + 1):
            labels, parents = extend(forward[-1], True)
            forward.append(labels)
            predecessors.append(parents)
            labels, parents = extend(backward[-1], False)
            backward.append(labels)
            successors.append(parents)
        for prefix in range(1, max_duties + 1):
            for suffix in range(1, max_duties - prefix + 2):
                feasible = (
                    (forward[prefix] != UNREACHABLE)
                    & (backward[suffix] != UNREACHABLE)
                    & (backward[suffix] - forward[prefix] <= max_span)
                )
                for index in np.flatnonzero(feasible & ~covered):
                    current = int(index)
                    before = [current]
                    for depth in range(prefix, 1, -1):
                        current = int(predecessors[depth][current])
                        before.append(current)
                    before.reverse()
                    current = int(index)
                    after = []
                    for depth in range(suffix, 1, -1):
                        current = int(successors[depth][current])
                        after.append(current)
                    witnesses[int(index)] = before + after
                covered |= feasible
    return covered, witnesses


def validate_witness(path):
    """Independently check each returned witness against production rules."""
    assert path and len(path) <= config.MAX_DUTIES_PER_PAIRING
    assert path[0].start_airport.is_crew_base
    assert path[-1].end_airport.port_name == path[0].start_airport.port_name
    assert path[-1].end_time - path[0].start_time <= config.MAX_PAIRING_TIME
    flights = [f for duty in path for f in duty.flights]
    assert len({f.flight_id for f in flights}) == len(flights)
    for duty in path:
        assert len(duty.flights) <= config.MAX_FLIGHTS_PER_DUTY
        assert duty.total_time <= config.MAX_ELAPSED_DUTY_TIME
        assert duty.flight_time <= config.MAX_ACTUAL_FLIGHT_TIME
        for first, second in zip(duty.flights, duty.flights[1:]):
            assert first.destination.port_name == second.origin.port_name
            assert config.DEFAULT_MIN_CONNECTION <= second.departure_datetime - first.arrival_datetime <= config.DEFAULT_MAX_CONNECTION
    for first, second in zip(path, path[1:]):
        assert first.end_airport.port_name == second.start_airport.port_name
        assert config.MIN_REST_BETWEEN_DUTIES <= second.start_time - first.end_time <= config.MAX_LAYOVER_BETWEEN_DUTIES


def analyze_instance(number, week=3):
    tick = monotonic()
    flights_path = ROOT / f"data/generated/instance{number}_week_{week}_with_start_end_padding.csv"
    bases_path = ROOT / f"data/inputs/instance{number}_listOfBases.csv"
    _, flights, graph = load_flight_network(flights_path, bases_path)
    _, padding = week_intervals(week)
    assert all(padding[0][0] <= f.departure_datetime.date() <= padding[1][1] for f in flights.values())
    duties = list(generate_duties(graph).values())
    print(f"instance{number} week{week}: {len(flights)} flights, {len(duties)} duties; checking closed paths", flush=True)
    mask, witnesses = closed_pairing_duties(
        duties, config.MAX_DUTIES_PER_PAIRING, config.MAX_PAIRING_TIME,
        config.MIN_REST_BETWEEN_DUTIES, config.MAX_LAYOVER_BETWEEN_DUTIES,
    )
    covered_flights = {f.flight_id for index in np.flatnonzero(mask) for f in duties[index].flights}
    required = {fid: f for fid, f in flights.items() if is_required_for_week(f, week)}
    uncovered = [f for fid, f in required.items() if fid not in covered_flights]
    # Preserve and independently validate one closed-pairing witness for every
    # coverable required flight, not merely a label claiming reachability.
    flight_witnesses = {}
    for index, indices in witnesses.items():
        target_ids = [f.flight_id for f in duties[index].flights if f.flight_id in required and f.flight_id not in flight_witnesses]
        if target_ids:
            path = [duties[i] for i in indices]
            validate_witness(path)
            record = [[f.flight_id for f in duty.flights] for duty in path]
            for fid in target_ids:
                assert any(fid in day for day in record)
                flight_witnesses[fid] = record
    assert set(flight_witnesses) == set(required) & covered_flights
    result = {
        "instance": number,
        "source_instance": 5 if number == 3 else number,
        "week": week,
        "flights_file": str(flights_path.relative_to(ROOT)),
        "bases_file": str(bases_path.relative_to(ROOT)),
        "flights": len(flights),
        "required_flights": len(required),
        "duties": len(duties),
        "required_flights_with_legal_pairing": len(flight_witnesses),
        "uncoverable_required_count": len(uncovered),
        "status": "proven_infeasible" if uncovered else "passes_individual_coverage_check",
        "uncoverable_required_flights": [
            {"flight_id": f.flight_id, "origin": f.origin.port_name,
             "destination": f.destination.port_name,
             "departure": f.departure_datetime.isoformat(sep=" ", timespec="minutes"),
             "arrival": f.arrival_datetime.isoformat(sep=" ", timespec="minutes")}
            for f in uncovered
        ],
        "legal_pairing_witnesses_by_required_flight": flight_witnesses,
        "seconds": round(monotonic() - tick, 3),
    }
    print(f"instance{number} week{week}: {result['status']}; {len(uncovered)} uncoverable required flights; {result['seconds']}s", flush=True)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--instances", nargs="+", type=int, choices=range(1, 4), default=list(range(1, 4)))
    parser.add_argument("--week", type=int, choices=(2, 3), default=3)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.output is None:
        name = "instance_coverage.json" if args.week == 3 else f"instance_coverage_week{args.week}.json"
        args.output = ROOT / "diagnostics" / name
    missing = [number for number in args.instances if not (ROOT / f"data/generated/instance{number}_week_{args.week}_with_start_end_padding.csv").exists()]
    if missing:
        parser.error(f"Week {args.week} input files are missing for instances {missing}; select prepared instances with --instances.")
    required, padding = week_intervals(args.week)
    payload = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "week": args.week,
        "required_departure_interval": [day.isoformat() for day in required],
        "method": "Exact legal closed-pairing membership per required flight; no LP, ILP, or pricing.",
        "limitation": "Individual coverage does not prove simultaneous exactly-once coverage.",
        "limits": {
            "min_connection_minutes": config.DEFAULT_MIN_CONNECTION.total_seconds() / 60,
            "max_connection_hours": config.DEFAULT_MAX_CONNECTION.total_seconds() / 3600,
            "max_duty_hours": config.MAX_ELAPSED_DUTY_TIME.total_seconds() / 3600,
            "max_flight_hours_per_duty": config.MAX_ACTUAL_FLIGHT_TIME.total_seconds() / 3600,
            "max_flights_per_duty": config.MAX_FLIGHTS_PER_DUTY,
            "min_rest_hours": config.MIN_REST_BETWEEN_DUTIES.total_seconds() / 3600,
            "max_rest_hours": config.MAX_LAYOVER_BETWEEN_DUTIES.total_seconds() / 3600,
            "max_pairing_days": config.MAX_PAIRING_TIME.total_seconds() / 86400,
            "max_duties_per_pairing": config.MAX_DUTIES_PER_PAIRING,
            "padding_intervals": [[start.isoformat(), end.isoformat()] for start, end in padding],
        },
        "instances": [],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    for number in args.instances:
        payload["instances"].append(analyze_instance(number, args.week))
        args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"Saved {args.output}")


if __name__ == "__main__":
    main()
