"""Test a January day's pattern as December 31 optional start padding.

This is an in-memory calendar-shift experiment, not real December data. The
exact path checks diagnose the original two-flight AIR12 conflict; they do not
solve the full weekly or monthly set-partitioning problem.
"""

import argparse
from dataclasses import replace
from datetime import date, timedelta
import hashlib
import json
from pathlib import Path

from crew_pairing.config import MIN_REST_BETWEEN_DUTIES
from crew_pairing.duties import generate_duties
from crew_pairing.duty_graph import build_duty_graph
from crew_pairing.flights_graph import build_flight_graph, load_flights
from tests.diagnostics.diagnose_flight import describe_path, exact_target_search


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-day", type=int, choices=range(1, 32), default=31)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    month_path = root / "data/inputs/all_days.csv"
    week_path = root / "data/generated/week_1_with_padding.csv"
    hubs = root / "data/inputs/listOfBases.csv"
    hashes = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in (month_path, week_path)}
    _, month = load_flights(month_path, hubs)
    _, week = load_flights(week_path, hubs)
    source_date = date(2000, 1, args.source_day)
    destination_date = date(1999, 12, 31)
    shift = destination_date - source_date
    source = [f for f in month.values() if f.departure_datetime.date() == source_date]
    padding = {
        "HYP_PRE_" + f.flight_id: replace(
            f, flight_id="HYP_PRE_" + f.flight_id,
            departure_datetime=f.departure_datetime + shift,
            arrival_datetime=f.arrival_datetime + shift,
        ) for f in source
    }
    flights = week | padding
    duties = generate_duties(build_flight_graph(flights.values()))
    report = {
        "experiment": f"January {args.source_day} records shifted to hypothetical December 31 start padding",
        "source_date": str(source_date), "destination_date": str(destination_date),
        "actual_december_31_records": sum(f.departure_datetime.date() == date(1999, 12, 31) for f in month.values()),
        "source_month_flight_count": len(month),
        "source_day_flight_count": len(source),
        "source_day_air12_flights": [f.flight_id for f in source if "AIR12" in (f.origin.port_name, f.destination.port_name)],
        "current_rest_minutes": MIN_REST_BETWEEN_DUTIES.total_seconds() / 60,
        "active_week_plus_end_padding_count": len(week),
        "combined_count": len(flights), "duties": len(duties),
        "production_input_hashes": hashes, "scenarios": {},
        "padding_records": [{"id": f.flight_id, "origin": f.origin.port_name, "destination": f.destination.port_name, "departure": str(f.departure_datetime), "arrival": str(f.arrival_datetime)} for f in padding.values()],
        "limitations": [
            "The supplied full-month data has no actual December 31 schedule.",
            "The shifted January pattern is hypothetical and does not establish the previous day's actual flights.",
            "These exact searches test path feasibility, not optimization of all required flights.",
            "Production padding classification is unchanged; a real integration would need to mark pre-period flights optional.",
        ],
    }
    for name, rest in [("original_10h", timedelta(hours=10)), ("current", MIN_REST_BETWEEN_DUTIES)]:
        graph = build_duty_graph(duties.values(), min_rest=rest)
        cases = {}
        for label, required, forbidden in [
            ("target_without_01_30", ("LEG_02_27",), ("LEG_01_30",)),
            ("competitor_without_01_30", ("LEG_01_28",), ("LEG_01_30",)),
            ("both_returns_in_one_pairing", ("LEG_01_28", "LEG_02_27"), ()),
        ]:
            exact, path = exact_target_search(graph, flights, required, forbidden)
            cases[label] = {**exact, "witness": describe_path(path, min_rest=rest)}
            print(name, label, "paths", exact["closed_pairing_count"], flush=True)
        competitor = cases["competitor_without_01_30"]["witness"]
        if competitor:
            used_ids = competitor["flight_ids"]
            exact, path = exact_target_search(graph, flights, ("LEG_02_27",), used_ids)
            target = describe_path(path, min_rest=rest)
            if target:
                assert not set(used_ids).intersection(target["flight_ids"])
            cases["disjoint_target_after_covering_competitor"] = {**exact, "witness": target}
            print(name, "disjoint two-pairing cover", bool(target), flush=True)
        report["scenarios"][name] = {"min_rest_minutes": rest.total_seconds() / 60, "cases": cases}
    if args.source_day == 31:
        assert all(case["closed_pairing_count"] == 0 for case in report["scenarios"]["original_10h"]["cases"].values())
    report["input_files_unchanged"] = all(hashlib.sha256(Path(p).read_bytes()).hexdigest() == h for p, h in hashes.items())
    assert report["input_files_unchanged"]
    output = root / "reports/flight_diagnosis/start_padding"
    if args.source_day != 31:
        output = output / f"jan{args.source_day}_as_dec31"
    output.mkdir(parents=True, exist_ok=True)
    (output / "audit.json").write_text(json.dumps(report, indent=2) + "\n")
    print("REPORT", output / "audit.json", flush=True)


if __name__ == "__main__":
    main()
