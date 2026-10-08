"""Measure reference schedules and test compatible (not identified) rule sets.

Run from the repository root with python -m tests.diagnostics.infer_reference_limits.
No production data or settings are modified. Duty boundaries are reconstructed
using the project's maximum same-duty connection of eight hours.
"""

from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
import re

from crew_pairing.flights_graph import load_flights


ROOT = Path(__file__).resolve().parents[2]
REPORT = ROOT / "reports/flight_diagnosis/original_solution"


def minutes(delta):
    return delta.total_seconds() / 60


def duration(value):
    value = int(value)
    return f"{value // 60}h{value % 60:02d}"


def main():
    _, flights = load_flights(
        ROOT / "data/inputs/all_days.csv", ROOT / "data/inputs/listOfBases.csv"
    )
    pairings, duties, rests, connections = [], [], [], []
    for line in (REPORT / "initialSolution.in").read_text().splitlines():
        match = re.fullmatch(r"Pairing (\d+) : Base (\w+) : (.*);", line)
        if not match:
            continue
        tokens = [token.strip() for token in match[3].split(",")]
        legs = [flights[token.removeprefix("TDH_")] for token in tokens]
        gaps = [minutes(b.departure_datetime - a.arrival_datetime) for a, b in zip(legs, legs[1:])]
        cuts = [0] + [i for i, gap in enumerate(gaps, 1) if gap > 480] + [len(legs)]
        record = {
            "id": int(match[1]), "base": match[2], "tokens": tokens,
            "start": str(legs[0].departure_datetime), "end": str(legs[-1].arrival_datetime),
            "elapsed_minutes": minutes(legs[-1].arrival_datetime - legs[0].departure_datetime),
            "calendar_dates_touched": (legs[-1].arrival_datetime.date() - legs[0].departure_datetime.date()).days + 1,
            "duty_count": len(cuts) - 1,
            "closed_at_assigned_base": legs[0].origin.port_name == match[2] == legs[-1].destination.port_name,
            "airport_continuity": all(a.destination == b.origin for a, b in zip(legs, legs[1:])),
            "rest_minutes": [gap for gap in gaps if gap > 480],
            "connection_minutes": [gap for gap in gaps if gap <= 480],
            "duties": [],
        }
        rests.extend(record["rest_minutes"])
        connections.extend(record["connection_minutes"])
        for a, b in zip(cuts, cuts[1:]):
            duty_legs, duty_tokens = legs[a:b], tokens[a:b]
            duty = {
                "pairing": record["id"], "tokens": duty_tokens,
                "start": str(duty_legs[0].departure_datetime), "end": str(duty_legs[-1].arrival_datetime),
                "elapsed_minutes": minutes(duty_legs[-1].arrival_datetime - duty_legs[0].departure_datetime),
                "operating_minutes": sum(minutes(f.arrival_datetime - f.departure_datetime) for f, t in zip(duty_legs, duty_tokens) if not t.startswith("TDH_")),
                "all_travel_minutes": sum(minutes(f.arrival_datetime - f.departure_datetime) for f in duty_legs),
                "leg_count": len(duty_legs),
                "operating_leg_count": sum(not t.startswith("TDH_") for t in duty_tokens),
            }
            duties.append(duty)
            record["duties"].append(duty)
        pairings.append(record)

    defaults = {
        "min_connection": 30, "max_connection": 480,
        "max_duty_elapsed": 720, "max_operating_flight": 480,
        "max_legs": 5, "min_rest": 540, "max_rest": 2880,
        "max_pairing_elapsed": 5760, "max_duties": 4,
        "count_deadhead_as_operating": False,
    }

    def validate(**overrides):
        rules = defaults | overrides
        failures = []
        for p in pairings:
            reasons = []
            if not p["closed_at_assigned_base"] or not p["airport_continuity"]:
                reasons.append("airport/base")
            if p["elapsed_minutes"] > rules["max_pairing_elapsed"]:
                reasons.append("pairing elapsed")
            if p["duty_count"] > rules["max_duties"]:
                reasons.append("duty count")
            if any(not rules["min_rest"] <= r <= rules["max_rest"] for r in p["rest_minutes"]):
                reasons.append("rest")
            if any(not rules["min_connection"] <= c <= rules["max_connection"] for c in p["connection_minutes"]):
                reasons.append("connection")
            for d in p["duties"]:
                if d["elapsed_minutes"] > rules["max_duty_elapsed"]:
                    reasons.append("duty elapsed")
                flying_key = "all_travel_minutes" if rules["count_deadhead_as_operating"] else "operating_minutes"
                if d[flying_key] > rules["max_operating_flight"]:
                    reasons.append("operating flight time")
                if d["leg_count"] > rules["max_legs"]:
                    reasons.append("leg count")
            if reasons:
                failures.append({"pairing": p["id"], "reasons": sorted(set(reasons))})
        return {"rules_minutes": rules, "passed": len(pairings) - len(failures), "failed": len(failures), "failures": failures}

    scenarios = {
        "compatible_candidate": validate(),
        "rest_9h02": validate(min_rest=542),
        "rest_9h59": validate(min_rest=599),
        "rest_10h": validate(min_rest=600),
        "count_deadheads_against_8h_flying": validate(count_deadhead_as_operating=True),
        "pairing_3_days": validate(max_pairing_elapsed=4320),
        "pairing_5_days_5_duties": validate(max_pairing_elapsed=7200, max_duties=5),
        "max_3_duties": validate(max_duties=3),
    }
    summary = {
        "pairings": len(pairings), "reconstructed_duties": len(duties),
        "min_rest_minutes": min(rests), "max_rest_minutes": max(rests),
        "min_connection_minutes": min(connections), "max_connection_minutes": max(connections),
        "max_duty_elapsed": max(duties, key=lambda d: d["elapsed_minutes"]),
        "max_operating_flight": max(duties, key=lambda d: d["operating_minutes"]),
        "max_all_travel": max(duties, key=lambda d: d["all_travel_minutes"]),
        "max_legs_per_duty": max(d["leg_count"] for d in duties),
        "max_pairing_elapsed": max(pairings, key=lambda p: p["elapsed_minutes"]),
        "max_duties_per_pairing": max(p["duty_count"] for p in pairings),
        "max_calendar_dates_touched": max(p["calendar_dates_touched"] for p in pairings),
        "duty_count_distribution": dict(Counter(p["duty_count"] for p in pairings)),
    }
    output = {
        "method": "Split consecutive legs at gaps >8h; keep all travel in elapsed duty time; distinguish operating block time from TDH passenger time.",
        "limitations": [
            "Duty boundaries are inferred, not encoded in the reference file.",
            "Passing a rule set proves compatibility, not the original solver's configured limits.",
            "Times exclude unspecified briefing/debriefing, transfers, and sleep requirements.",
            "Many larger upper limits or smaller lower limits also fit this same solution.",
        ],
        "summary": summary, "scenarios": scenarios, "pairings": pairings,
    }
    (REPORT / "inferred_limits.json").write_text(json.dumps(output, indent=2) + "\n")
    print(json.dumps({
        "observed": {
            "duty_elapsed": duration(summary["max_duty_elapsed"]["elapsed_minutes"]),
            "operating_flight": duration(summary["max_operating_flight"]["operating_minutes"]),
            "all_travel": duration(summary["max_all_travel"]["all_travel_minutes"]),
            "pairing_elapsed": duration(summary["max_pairing_elapsed"]["elapsed_minutes"]),
            "min_rest": duration(min(rests)), "max_rest": duration(max(rests)),
            "min_connection": duration(min(connections)), "max_connection": duration(max(connections)),
            "max_duties": summary["max_duties_per_pairing"],
            "max_dates_touched": summary["max_calendar_dates_touched"],
            "duty_count_distribution": summary["duty_count_distribution"],
        },
        "scenarios": {name: {k: v[k] for k in ("passed", "failed")} for name, v in scenarios.items()},
    }, indent=2))


if __name__ == "__main__":
    main()
