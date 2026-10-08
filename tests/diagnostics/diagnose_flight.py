"""Exact single-flight coverage diagnosis using the production legality rules.

Run from the repository root:
    python -m tests.diagnostics.diagnose_flight LEG_02_27

This diagnostic does not modify production settings or need an LP solver.
The optional --bottleneck and --competitor checks distinguish individual
coverability from compatibility with other required flights.
"""

from __future__ import annotations

import argparse
from dataclasses import replace
from datetime import timedelta
from functools import lru_cache
import hashlib
import json
import random
from pathlib import Path

from column_generation.config import ARTIFICIAL_COST, FLIGHTS_FILE_PATH, HUBS_FILE_PATH, PRICING_RANDOM_SEED
from column_generation.pairing_pricing import generate_pricing_pairings
from crew_pairing.config import MAX_DUTIES_PER_PAIRING, MAX_PAIRING_TIME, MIN_REST_BETWEEN_DUTIES
from crew_pairing.duties import generate_duties
from crew_pairing.duty_graph import build_duty_graph, can_connect_duties
from crew_pairing.flights_graph import build_flight_graph, can_connect, load_flight_network
from crew_pairing.pairing_cost import current_pairing_cost
from crew_pairing.pairings import build_pairing_from_path
from run_progress import progress


def exact_target_search(graph, flights, required_ids, forbidden_ids=(), duals=None):
    """Count every closed path containing required_ids; return its cheapest path.

    For each start, the base and deadline are fixed. Memoization merges suffixes
    only with the same current duty, depth, and required-flight mask. Time
    increases on every edge, so paths cannot repeat a flight or duty. There are
    no Top-K, state, or column budgets. Cost is the production rest+sitting model,
    optionally minus the sum of flight duals.
    """
    required_ids = tuple(required_ids)
    forbidden_ids = set(forbidden_ids)
    duals = duals or {}
    bits = {flight_id: 1 << i for i, flight_id in enumerate(required_ids)}
    full_mask = (1 << len(bits)) - 1
    duty_ids = {d: {f.flight_id for f in d.flights} for d in graph}
    masks = {d: sum(bits.get(f, 0) for f in ids) for d, ids in duty_ids.items()}
    allowed = {d: not (ids & forbidden_ids) for d, ids in duty_ids.items()}
    weights = {
        d: d.sitting_time.total_seconds() / 3600 - sum(duals.get(f, 0) for f in ids)
        for d, ids in duty_ids.items()
    }
    total_count, best_cost, best_path, total_states = 0, float("inf"), (), 0
    earliest_required = min(flights[f].departure_datetime for f in required_ids)
    for start in graph:
        if not start.start_airport.is_crew_base or not allowed[start]:
            continue
        if start.start_time > earliest_required:
            continue
        if not 0 <= (start.end_time - start.start_time).total_seconds() <= MAX_PAIRING_TIME.total_seconds():
            continue
        base = start.start_airport.port_name
        deadline = start.start_time + MAX_PAIRING_TIME

        @lru_cache(None)
        def suffix(duty, depth, mask):
            mask |= masks[duty]
            # A missing flight cannot be visited after its departure has passed.
            if any(
                not (mask & bit) and flights[f].departure_datetime < duty.end_time
                for f, bit in bits.items()
            ):
                return 0, float("inf"), ()
            closed = mask == full_mask and duty.end_airport.port_name == base
            count = int(closed)
            cost = weights[duty] if closed else float("inf")
            path = (duty,) if closed else ()
            if depth < MAX_DUTIES_PER_PAIRING:
                for nxt in graph[duty]:
                    if not allowed[nxt] or nxt.end_time > deadline:
                        continue
                    following_count, following_cost, following_path = suffix(nxt, depth + 1, mask)
                    count += following_count
                    candidate_cost = weights[duty] + (nxt.start_time - duty.end_time).total_seconds() / 3600 + following_cost
                    if candidate_cost < cost:
                        cost, path = candidate_cost, (duty,) + following_path
            return count, cost, path

        count, cost, path = suffix(start, 1, 0)
        total_count += count
        if cost < best_cost:
            best_cost, best_path = cost, path
        total_states += suffix.cache_info().currsize
        suffix.cache_clear()
    return {
        "closed_pairing_count": total_count,
        "minimum_cost": best_cost if best_path else None,
        "states": total_states,
    }, best_path


def describe_path(path, min_rest=MIN_REST_BETWEEN_DUTIES):
    if not path:
        return None
    pairing = build_pairing_from_path("DIAGNOSTIC", list(path))
    ids = [f.flight_id for d in path for f in d.flights]
    assert len(ids) == len(set(ids))
    assert pairing.start_airport.is_crew_base and pairing.start_airport == pairing.end_airport
    assert pairing.total_time <= MAX_PAIRING_TIME and len(path) <= MAX_DUTIES_PER_PAIRING
    assert all(can_connect_duties(a, b, min_rest=min_rest) for a, b in zip(path, path[1:]))
    return {
        "flight_ids": ids,
        "base": pairing.start_airport.port_name,
        "total_hours": pairing.total_time.total_seconds() / 3600,
        "cost": current_pairing_cost(pairing),
        "duties": [
            {
                "duty_id": d.duty_id,
                "flights": [f.flight_id for f in d.flights],
                "start": d.start_time.isoformat(), "end": d.end_time.isoformat(),
                "flight_hours": d.flight_time.total_seconds() / 3600,
                "elapsed_hours": d.total_time.total_seconds() / 3600,
            }
            for d in path
        ],
        "rests_minutes": [(b.start_time - a.end_time).total_seconds() / 60 for a, b in zip(path, path[1:])],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("flight_id", nargs="?", default="LEG_02_27")
    parser.add_argument("--bottleneck", default="LEG_01_30")
    parser.add_argument("--competitor", default="LEG_01_28")
    parser.add_argument("--pricing-check", action="store_true", help="Run production pricing with two diagnostic dual vectors")
    parser.add_argument("--initial-pool-check", action="store_true", help="Check target coverage in the current production initial pool")
    parser.add_argument("--output", type=Path, default=Path("reports/flight_diagnosis/LEG_02_27.json"))
    args = parser.parse_args()
    _, flights, fg = load_flight_network(FLIGHTS_FILE_PATH, HUBS_FILE_PATH)
    target = flights[args.flight_id]
    duties = generate_duties(fg)
    graph = build_duty_graph(duties.values())
    target_duties = [d for d in graph if target in d.flights]
    report = {
        "flight_id": target.flight_id,
        "route": f"{target.origin.port_name}->{target.destination.port_name}",
        "departure": target.departure_datetime.isoformat(), "arrival": target.arrival_datetime.isoformat(),
        "input": str(FLIGHTS_FILE_PATH),
        "input_sha256": hashlib.sha256(FLIGHTS_FILE_PATH.read_bytes()).hexdigest(),
        "flights": len(flights), "duties": len(graph),
        "duties_containing_target": len(target_duties),
        "same_duty_predecessors": [f.flight_id for f, neighbors in fg.items() if target in neighbors],
        "incoming_target_duty_flights": sorted({
            previous.flights[-1].flight_id
            for previous, neighbors in graph.items() for d in neighbors if d in target_duties
        }),
        "airport_predecessors": [
            {
                "flight_id": f.flight_id, "arrival": f.arrival_datetime.isoformat(),
                "gap_minutes": (target.departure_datetime - f.arrival_datetime).total_seconds() / 60,
                "same_duty_connection_allowed": can_connect(f, target),
            }
            for f in flights.values()
            if f.destination == target.origin and f.arrival_datetime < target.departure_datetime
        ],
    }
    checks = [
        ("target", (target.flight_id,), ()),
        ("target_without_bottleneck", (target.flight_id,), (args.bottleneck,)),
        ("competitor", (args.competitor,), ()),
        ("competitor_without_bottleneck", (args.competitor,), (args.bottleneck,)),
        ("target_and_competitor_same_pairing", (target.flight_id, args.competitor), ()),
    ]
    for name, required, forbidden in checks:
        progress(f"Exact diagnosis: {name}")
        result, path = exact_target_search(graph, flights, required, forbidden)
        result["witness"] = describe_path(path)
        report[name] = result
        print(name, json.dumps(result), flush=True)

    # These are separate hypothetical inputs, never production configuration edits.
    # They apply specifically to the supplied LEG_02_27 bottleneck.
    if args.flight_id == "LEG_02_27" and args.bottleneck == "LEG_01_30" and args.competitor == "LEG_01_28":
        reduced_rest = timedelta(hours=9, minutes=59)
        relaxed_graph = build_duty_graph(duties.values(), min_rest=reduced_rest)
        result, path = exact_target_search(relaxed_graph, flights, (target.flight_id,))
        result["min_rest_minutes"] = reduced_rest.total_seconds() / 60
        result["witness"] = describe_path(path, min_rest=reduced_rest)
        competitor_ids = set(report["competitor"]["witness"]["flight_ids"])
        result["disjoint_from_competitor_witness"] = not competitor_ids.intersection(result["witness"]["flight_ids"])
        report["hypothetical_9h59_rest"] = result
        print("hypothetical_9h59_rest", json.dumps(result), flush=True)

        delayed_target = replace(
            target, departure_datetime=target.departure_datetime + timedelta(minutes=1),
            arrival_datetime=target.arrival_datetime + timedelta(minutes=1),
        )
        delayed_flights = {**flights, target.flight_id: delayed_target}
        delayed_duties = generate_duties(build_flight_graph(delayed_flights.values()))
        delayed_graph = build_duty_graph(delayed_duties.values())
        result, path = exact_target_search(delayed_graph, delayed_flights, (target.flight_id,))
        result["witness"] = describe_path(path)
        result["disjoint_from_competitor_witness"] = not competitor_ids.intersection(result["witness"]["flight_ids"])
        report["hypothetical_one_minute_flight_delay"] = result
        print("hypothetical_one_minute_flight_delay", json.dumps(result), flush=True)

        # A feasible flight-dual vector that exposes the capacity bottleneck.
        # It is a certificate/example, NOT the dual vector from the user's run.
        certificate = {f: 0.0 for f in flights}
        certificate[target.flight_id] = ARTIFICIAL_COST
        certificate[args.competitor] = ARTIFICIAL_COST
        certificate[args.bottleneck] = -ARTIFICIAL_COST + report["competitor"]["minimum_cost"]
        exact_rc, _ = exact_target_search(graph, flights, (target.flight_id,), duals=certificate)
        report["illustrative_dual_certificate"] = {
            "duals": {f: certificate[f] for f in (target.flight_id, args.competitor, args.bottleneck)},
            "minimum_target_reduced_cost": exact_rc["minimum_cost"],
            "not_an_observation_of_user_run": True,
            "minimum_artificial_sum_for_target_and_competitor": 1,
        }
        if args.pricing_check:
            rng = random.Random(PRICING_RANDOM_SEED)
            pricing_results = {}
            target_only = {f: 0.0 for f in flights}
            target_only[target.flight_id] = ARTIFICIAL_COST
            for name, duals in (("target_only_large_dual", target_only), ("bottleneck_dual_certificate", certificate)):
                progress(f"Production pricing diagnostic: {name}")
                pool, _ = generate_pricing_pairings(graph, duals, set(), rng=rng)
                pricing_results[name] = {
                    "new_pairings": len(pool),
                    "containing_target": sum(target in d.flights for p in pool.values() for d in p.duties),
                    "synthetic_duals": True,
                }
                print(name, json.dumps(pricing_results[name]), flush=True)
            report["production_pricing_checks"] = pricing_results
    if args.initial_pool_check:
        from column_generation.initial_pool import generate_initial_pairings
        progress("Checking current production initial pool")
        pool, coverage, _ = generate_initial_pairings(graph, flights)
        target_pool = [p for p in pool.values() if any(target in d.flights for d in p.duties)]
        report["current_initial_pool"] = {
            "total_pairings": len(pool), "target_pairings": coverage[target.flight_id],
            "first_target_witness": describe_path(target_pool[0].duties) if target_pool else None,
        }
        print("current_initial_pool", json.dumps(report["current_initial_pool"]), flush=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("REPORT", args.output.resolve(), flush=True)


if __name__ == "__main__":
    main()
