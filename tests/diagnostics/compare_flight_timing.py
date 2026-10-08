"""Run the production optimizer for isolated LEG_02_27 timing experiments.

python -m tests.diagnostics.compare_flight_timing rest_9h58
python -m tests.diagnostics.compare_flight_timing delay_one_minute

Only in-memory graph/input copies change. No production CSV or settings change.
Requires the same MOSEK license as the production runner. An optional --deps
directory permits a workspace-local MOSEK installation.
"""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import replace
from datetime import timedelta
import hashlib
import json
from pathlib import Path
import sys
from time import perf_counter


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("scenario", choices=("rest_9h58", "delay_one_minute"))
    parser.add_argument("--deps", type=Path)
    parser.add_argument("--max-iterations", type=int, default=100)
    args = parser.parse_args()
    if args.deps:
        sys.path.insert(0, str(args.deps.resolve()))

    import column_generation.column_generation as cg
    from column_generation.config import ARTIFICIAL_TOLERANCE, FLIGHTS_FILE_PATH, HUBS_FILE_PATH
    from column_generation.master_ilp import solve_ilp
    from crew_pairing.config import MIN_REST_BETWEEN_DUTIES
    from crew_pairing.duties import generate_duties
    from crew_pairing.duty_graph import build_duty_graph
    from crew_pairing.flights_graph import build_flight_graph, load_flight_network
    from crew_pairing.padding_flights import is_padding_flight
    from tests.diagnostics.diagnose_flight import describe_path, exact_target_search
    from run_progress import progress

    started = perf_counter()
    output = Path(__file__).resolve().parents[2] / "reports" / "flight_diagnosis" / args.scenario
    output.mkdir(parents=True, exist_ok=True)
    _, flights, flight_graph = load_flight_network(FLIGHTS_FILE_PATH, HUBS_FILE_PATH)
    target_id, competitor_id = "LEG_02_27", "LEG_01_28"
    min_rest = MIN_REST_BETWEEN_DUTIES
    if args.scenario == "rest_9h58":
        min_rest = timedelta(hours=9, minutes=58)
    else:
        target = flights[target_id]
        flights[target_id] = replace(
            target, departure_datetime=target.departure_datetime + timedelta(minutes=1),
            arrival_datetime=target.arrival_datetime + timedelta(minutes=1),
        )
        flight_graph = build_flight_graph(flights.values())
    duties = generate_duties(flight_graph)
    graph = build_duty_graph(duties.values(), min_rest=min_rest)
    report = {
        "scenario": args.scenario,
        "input": str(FLIGHTS_FILE_PATH),
        "input_sha256": hashlib.sha256(FLIGHTS_FILE_PATH.read_bytes()).hexdigest(),
        "min_rest_minutes": min_rest.total_seconds() / 60,
        "target_departure": flights[target_id].departure_datetime.isoformat(),
        "target_arrival": flights[target_id].arrival_datetime.isoformat(),
        "max_iterations": args.max_iterations,
        "flights": len(flights), "duties": len(graph),
        "duty_edges": sum(map(len, graph.values())),
        "history": [],
    }

    # Independent exact witnesses establish that both returns can be covered
    # without sharing an operating flight, before running heuristic pricing.
    witnesses = {}
    for flight_id in (target_id, competitor_id):
        exact, path = exact_target_search(graph, flights, (flight_id,))
        witnesses[flight_id] = {**exact, "witness": describe_path(path, min_rest=min_rest)}
    assert not set(witnesses[target_id]["witness"]["flight_ids"]).intersection(
        witnesses[competitor_id]["witness"]["flight_ids"]
    )
    report["exact_disjoint_witnesses"] = witnesses

    original_solve = cg.solve_master_lp

    def tracked_solve(columns, all_flights, cost_function):
        result = original_solve(columns, all_flights, cost_function)
        active = {f: a for f, a in result.artificial_values.items() if a > ARTIFICIAL_TOLERANCE}
        row = {
            "iteration": len(report["history"]), "columns": len(columns),
            "objective": result.objective,
            "artificial_count": len(active), "artificial_sum": sum(result.artificial_values.values()),
            "target_artificial": result.artificial_values[target_id],
            "competitor_artificial": result.artificial_values[competitor_id],
            "target_dual": result.duals[target_id],
            "elapsed_seconds": perf_counter() - started,
        }
        report["history"].append(row)
        (output / "summary.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        print("SCENARIO_MASTER", json.dumps(row), flush=True)
        return result

    cg.solve_master_lp = tracked_solve
    progress(f"Experiment {args.scenario}: running production column generation")
    columns, _, master = cg.run_column_generation(graph, flights, max_iterations=args.max_iterations)
    active = {f: a for f, a in master.artificial_values.items() if a > ARTIFICIAL_TOLERANCE}
    report["final_lp"] = {
        "columns": len(columns), "objective": master.objective,
        "artificial_count": len(active), "artificial_sum": sum(master.artificial_values.values()),
        "positive_artificials": active,
        "duals": master.duals,
        "target_pairings_in_pool": sum(any(f.flight_id == target_id for d in p.duties for f in d.flights) for p in columns.values()),
    }
    selected_lp = []
    coverage = Counter()
    for pairing_id, value in master.pairing_values.items():
        if value <= ARTIFICIAL_TOLERANCE:
            continue
        pairing = columns[pairing_id]
        ids = [f.flight_id for d in pairing.duties for f in d.flights]
        for flight_id in ids:
            coverage[flight_id] += value
        if target_id in ids or competitor_id in ids:
            selected_lp.append({"column_id": pairing_id, "value": value, **describe_path(pairing.duties, min_rest=min_rest)})
    for flight_id, flight in flights.items():
        if is_padding_flight(flight):
            assert coverage[flight_id] <= 1 + 1e-5
        else:
            assert abs(coverage[flight_id] + master.artificial_values[flight_id] - 1) < 1e-5
    report["final_lp"]["selected_target_or_competitor_pairings"] = selected_lp
    report["final_lp"]["target_real_coverage"] = coverage[target_id]
    report["final_lp"]["competitor_real_coverage"] = coverage[competitor_id]
    if active:
        exact, path = exact_target_search(graph, flights, (target_id,), duals=master.duals)
        report["final_lp"]["exact_minimum_target_reduced_cost"] = exact["minimum_cost"]
        report["final_lp"]["minimum_reduced_cost_target_witness"] = describe_path(path, min_rest=min_rest)
        report["final_ilp"] = {"run": False, "reason": "Production runner skips final ILP while artificials remain"}
    else:
        progress(f"Experiment {args.scenario}: running production final binary ILP")
        try:
            solution, cost = solve_ilp(columns, flights)
            selected = [columns[p] for p, value in solution.items() if value > 0.5]
            integer_coverage = Counter(f.flight_id for p in selected for d in p.duties for f in d.flights)
            for flight_id, flight in flights.items():
                assert integer_coverage[flight_id] <= 1
                if not is_padding_flight(flight):
                    assert integer_coverage[flight_id] == 1
            selected_paths = [describe_path(p.duties, min_rest=min_rest) for p in selected]
            (output / "selected_pairings.json").write_text(json.dumps(selected_paths, indent=2), encoding="utf-8")
            report["final_ilp"] = {
                "run": True, "success": True, "cost": cost, "selected_pairings": len(selected),
                "required_covered": sum(integer_coverage[f] == 1 for f in flights if not is_padding_flight(flights[f])),
                "target_coverage": integer_coverage[target_id], "competitor_coverage": integer_coverage[competitor_id],
                "target_or_competitor_pairings": [p for p in selected_paths if target_id in p["flight_ids"] or competitor_id in p["flight_ids"]],
            }
        except Exception as error:
            report["final_ilp"] = {"run": True, "success": False, "error": str(error)}
    report["elapsed_seconds"] = perf_counter() - started
    (output / "summary.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    concise = {k: v for k, v in report["final_lp"].items() if k not in ("duals", "selected_target_or_competitor_pairings", "minimum_reduced_cost_target_witness")}
    print("SCENARIO_RESULT", json.dumps({"scenario": args.scenario, "lp": concise, "ilp": report["final_ilp"], "elapsed_seconds": report["elapsed_seconds"]}), flush=True)
    print("REPORT", output / "summary.json", flush=True)


if __name__ == "__main__":
    main()
