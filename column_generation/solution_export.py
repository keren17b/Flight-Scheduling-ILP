"""Select ILP-chosen pairings and write them to a result file."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Mapping

from column_generation.config import SELECTION_THRESHOLD
from crew_pairing.duties import Duty
from crew_pairing.flights_graph import DATETIME_FORMAT, Flight
from crew_pairing.pairing_cost import PairingCostFunction, current_pairing_cost
from crew_pairing.pairings import Pairing


def selected_pairings(
    pairings: Mapping[str, Pairing],
    solution: Mapping[str, float],
    selection_threshold: float = SELECTION_THRESHOLD,
) -> Dict[str, Pairing]:
    """Return the pairing objects whose ILP value is above the selection cutoff."""
    chosen: Dict[str, Pairing] = {}
    for pairing_id, pairing in pairings.items():
        if solution.get(pairing_id, 0.0) > selection_threshold:
            chosen[pairing_id] = pairing
    return chosen


def save_selected_pairings(
    pairings: Mapping[str, Pairing],
    output_path: str | Path,
    total_cost: float | None = None,
    cost_function: PairingCostFunction = current_pairing_cost,
) -> Path:
    """Write chosen pairings, with nested duties and flights, as JSON."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    ordered = sorted(
        pairings.values(),
        key=lambda pairing: (pairing.start_time, pairing.pairing_id),
    )
    payload = {
        "total_cost": total_cost,
        "selected_count": len(ordered),
        "pairings": [
            _pairing_record(pairing, cost_function(pairing)) for pairing in ordered
        ],
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def _pairing_record(pairing: Pairing, cost: float) -> dict:
    return {
        "pairing_id": pairing.pairing_id,
        "cost": cost,
        "start_airport": pairing.start_airport.port_name,
        "end_airport": pairing.end_airport.port_name,
        "start_time": _format_datetime(pairing.start_time),
        "end_time": _format_datetime(pairing.end_time),
        "total_time": _format_timedelta(pairing.total_time),
        "flight_time": _format_timedelta(pairing.flight_time),
        "sitting_time": _format_timedelta(pairing.sitting_time),
        "rest": _format_timedelta(pairing.rest),
        "duties": [_duty_record(duty) for duty in pairing.duties],
    }


def _duty_record(duty: Duty) -> dict:
    return {
        "duty_id": duty.duty_id,
        "start_airport": duty.start_airport.port_name,
        "end_airport": duty.end_airport.port_name,
        "start_time": _format_datetime(duty.start_time),
        "end_time": _format_datetime(duty.end_time),
        "total_time": _format_timedelta(duty.total_time),
        "flight_time": _format_timedelta(duty.flight_time),
        "sitting_time": _format_timedelta(duty.sitting_time),
        "flights": [_flight_record(flight) for flight in duty.flights],
    }


def _flight_record(flight: Flight) -> dict:
    return {
        "flight_id": flight.flight_id,
        "origin": flight.origin.port_name,
        "destination": flight.destination.port_name,
        "departure": _format_datetime(flight.departure_datetime),
        "arrival": _format_datetime(flight.arrival_datetime),
    }


def _format_datetime(value: datetime) -> str:
    return value.strftime(DATETIME_FORMAT)


def _format_timedelta(value: timedelta) -> str:
    return str(value)
