"""Audit the configured initial pool without running pricing or the final ILP.

Run with: python -m tests.diagnostics.initial_pool_report
Writes a JSON summary and per-flight CSV under reports/initial_pool/.
Requires the same MOSEK environment/license as the production master LP.
"""

from __future__ import annotations

from collections import Counter, defaultdict
import csv
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import sys
from time import perf_counter

from column_generation.config import (
    ARTIFICIAL_TOLERANCE, FLIGHTS_FILE_PATH, HUBS_FILE_PATH,
    MAX_INITIAL_DFS_STATES, MAX_INITIAL_DFS_STATES_PER_START,
    MAX_INITIAL_PAIRINGS, MAX_INITIAL_PAIRINGS_PER_START, MIN_INITIAL_COVERAGE,
)
from column_generation.initial_pool import generate_initial_pairings
from column_generation.master_lp import solve_master_lp
from crew_pairing.config import MAX_DUTIES_PER_PAIRING, MAX_PAIRING_TIME
from crew_pairing.duties import generate_duties
from crew_pairing.duty_graph import build_duty_graph, can_connect_duties
from crew_pairing.flights_graph import load_flight_network
from crew_pairing.padding_flights import is_padding_flight
from crew_pairing.pairings import pairing_signature
from run_progress import progress


def legal_coverage(graph, flights):
    """Exact union of flights on legal closed paths, without enumerating paths.

    For each starting duty, base and deadline are fixed. The suffix depends
    only on current duty and depth. Chronological edges prevent repeats.
    Bitmasks retain all flights on any suffix that returns to the start base.
    """
    bits = {flight_id: 1 << index for index, flight_id in enumerate(flights)}
    duty_bits = {
        duty: sum(bits[f.flight_id] for f in duty.flights) for duty in graph
    }
    assert all(
        nxt.start_time > duty.end_time
        for duty, neighbors in graph.items() for nxt in neighbors
    )
    covered = 0
    for start in graph:
        if not start.start_airport.is_crew_base:
            continue
        if not 0 <= (start.end_time - start.start_time).total_seconds() <= MAX_PAIRING_TIME.total_seconds():
            continue
        base = start.start_airport.port_name
        deadline = start.start_time + MAX_PAIRING_TIME

        @lru_cache(None)
        def suffix(duty, depth):
            result = duty_bits[duty] if duty.end_airport.port_name == base else 0
            if depth < MAX_DUTIES_PER_PAIRING:
                for nxt in graph.get(duty, ()):
                    if nxt.end_time <= deadline:
                        following = suffix(nxt, depth + 1)
                        if following:
                            result |= duty_bits[duty] | following
            return result

        covered |= suffix(start, 1)
        suffix.cache_clear()
    return {flight_id for flight_id, bit in bits.items() if covered & bit}


def audit_pool(graph, flights, **options):
    stats = Counter()
    generator_code = generate_initial_pairings.__code__

    def profile(frame, event, arg):
        if event != "return":
            return
        if frame.f_code is generator_code:
            stats["dfs_states"] = frame.f_locals["global_states"]
        elif frame.f_code.co_name == "dfs" and frame.f_code.co_filename == generator_code.co_filename:
            local = frame.f_locals
            if len(local["path"]) == 1:
                stats["starts_searched"] += 1
                if local["local_states"][0] >= options.get("max_dfs_states_per_start", MAX_INITIAL_DFS_STATES_PER_START):
                    stats["starts_at_state_limit"] += 1
                if local["local_saved"][0] >= options.get("max_pairings_per_start", MAX_INITIAL_PAIRINGS_PER_START):
                    stats["starts_at_pairing_limit"] += 1

    started = perf_counter()
    previous = sys.getprofile()
    sys.setprofile(profile)
    try:
        pairings, coverage, signatures = generate_initial_pairings(graph, flights, **options)
    finally:
        sys.setprofile(previous)
    elapsed = perf_counter() - started
    actual = Counter()
    invalid = []
    all_covered = set()
    for pairing in pairings.values():
        ids = [f.flight_id for d in pairing.duties for f in d.flights]
        all_covered.update(ids)
        actual.update(flight_id for flight_id in ids if flight_id in coverage)
        if (
            len(ids) != len(set(ids))
            or not pairing.start_airport.is_crew_base
            or pairing.start_airport != pairing.end_airport
            or len(pairing.duties) > MAX_DUTIES_PER_PAIRING
            or pairing.end_time - pairing.start_time > MAX_PAIRING_TIME
            or any(not can_connect_duties(a, b) for a, b in zip(pairing.duties, pairing.duties[1:]))
        ):
            invalid.append(pairing.pairing_id)
    assert all(actual[f] == count for f, count in coverage.items())
    assert len(signatures) == len(pairings)
    assert not invalid, invalid
    ordered = [pairing_signature(p.duties) for p in pairings.values()]
    histogram = Counter(coverage.values())
    summary = {
        "options": options, "pairings": len(pairings),
        "required_covered": sum(count > 0 for count in coverage.values()),
        "required_uncovered": sum(count == 0 for count in coverage.values()),
        "required_at_target": sum(count >= MIN_INITIAL_COVERAGE for count in coverage.values()),
        "coverage_histogram": dict(sorted(histogram.items())),
        "padding_covered": sum(is_padding_flight(flights[f]) for f in all_covered),
        "ordered_signature_sha256": hashlib.sha256(json.dumps(ordered).encode()).hexdigest(),
        "invalid_pairings": invalid, "search": dict(stats),
        "search_seconds_with_profiling": elapsed,
    }
    return pairings, coverage, summary


def lp_summary(pairings, flights):
    result = solve_master_lp(pairings, flights)
    active = {f: v for f, v in result.artificial_values.items() if v > ARTIFICIAL_TOLERANCE}
    summary = {
        "artificial_variables_created": len(result.artificial_values),
        "positive_artificials": len(active),
        "full_artificials": sum(v >= 1 - ARTIFICIAL_TOLERANCE for v in active.values()),
        "fractional_artificials": sum(v < 1 - ARTIFICIAL_TOLERANCE for v in active.values()),
        "artificial_sum": sum(result.artificial_values.values()),
        "real_coverage_equivalent": len(result.artificial_values) - sum(result.artificial_values.values()),
        "objective": result.objective,
    }
    return result, summary


def main():
    output = Path(__file__).resolve().parents[2] / "reports" / "initial_pool"
    output.mkdir(parents=True, exist_ok=True)
    progress("Audit: loading production inputs and generating duties")
    airports, flights, flight_graph = load_flight_network(FLIGHTS_FILE_PATH, HUBS_FILE_PATH)
    duties = generate_duties(flight_graph)
    progress(f"Audit: building graph for {len(duties):,} duties")
    graph = build_duty_graph(duties.values())
    report = {
        "flights_file": str(FLIGHTS_FILE_PATH),
        "flights_file_sha256": hashlib.sha256(FLIGHTS_FILE_PATH.read_bytes()).hexdigest(),
        "total_flights": len(flights),
        "required_flights": sum(not is_padding_flight(f) for f in flights.values()),
        "padding_flights": sum(is_padding_flight(f) for f in flights.values()),
        "duties": len(duties), "duty_edges": sum(map(len, graph.values())),
        "defaults": {"min_coverage": MIN_INITIAL_COVERAGE, "max_pairings": MAX_INITIAL_PAIRINGS,
                     "max_dfs_states": MAX_INITIAL_DFS_STATES,
                     "states_per_start": MAX_INITIAL_DFS_STATES_PER_START,
                     "pairings_per_start": MAX_INITIAL_PAIRINGS_PER_START},
        "scenarios": {},
    }
    pairings, coverage, baseline = audit_pool(graph, flights)
    master, baseline["lp"] = lp_summary(pairings, flights)
    report["scenarios"]["baseline"] = baseline
    print("BASELINE", json.dumps(baseline), flush=True)
    repeats = [audit_pool(graph, flights)[2] for _ in range(2)]
    report["repeat_hashes"] = [baseline["ordered_signature_sha256"]] + [r["ordered_signature_sha256"] for r in repeats]
    report["identical_on_three_runs"] = len(set(report["repeat_hashes"])) == 1
    progress("Audit: checking exact legal coverage independently of initial search budgets")
    coverable = legal_coverage(graph, flights)
    report["legally_coverable_required"] = sum(f in coverable for f in coverage)
    report["legally_uncoverable_required"] = [f for f in coverage if f not in coverable]
    per_day = defaultdict(lambda: Counter())
    rows = []
    for f in flights.values():
        required = not is_padding_flight(f)
        count = coverage.get(f.flight_id, sum(f in d.flights for p in pairings.values() for d in p.duties))
        if required:
            day = per_day[str(f.departure_datetime.date())]
            day["required"] += 1
            day["covered"] += count > 0
            day["uncovered"] += count == 0
            day["positive_artificials"] += master.artificial_values[f.flight_id] > ARTIFICIAL_TOLERANCE
        rows.append({"flight_id": f.flight_id, "origin": f.origin.port_name,
                     "destination": f.destination.port_name, "departure": f.departure_datetime.isoformat(),
                     "required": required, "initial_pairing_count": count,
                     "legally_coverable": f.flight_id in coverable,
                     "initial_lp_artificial": master.artificial_values.get(f.flight_id, "")})
    report["baseline_by_day"] = {day: dict(counts) for day, counts in sorted(per_day.items())}
    with (output / "flights.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    scenarios = [
        ("states_1000", graph, {"max_dfs_states_per_start": 1000}),
        ("states_5000", graph, {"max_dfs_states_per_start": 5000}),
        ("reversed_order", {d: list(reversed(neighbors)) for d, neighbors in reversed(list(graph.items()))}, {}),
    ]
    for name, scenario_graph, options in scenarios:
        progress(f"Audit: scenario {name}")
        pool, counts, summary = audit_pool(scenario_graph, flights, **options)
        _, summary["lp"] = lp_summary(pool, flights)
        report["scenarios"][name] = summary
        print(name.upper(), json.dumps(summary), flush=True)
    (output / "summary.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("REPORT", str(output), flush=True)
    print("LEGAL COVERAGE", report["legally_coverable_required"], "UNREACHABLE", report["legally_uncoverable_required"], flush=True)
    print("BY DAY", json.dumps(report["baseline_by_day"]), flush=True)


if __name__ == "__main__":
    main()
