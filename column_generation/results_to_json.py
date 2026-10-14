"""Summarize optimization runs and export selected pairings as JSON."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
from contextlib import contextmanager
from datetime import datetime, timedelta
import json
from pathlib import Path
from time import perf_counter
from typing import Dict, Iterator, Mapping
from uuid import uuid4

from column_generation.config import SELECTION_THRESHOLD
from crew_pairing.duties import Duty
from crew_pairing.flights_graph import DATETIME_FORMAT, Flight
from crew_pairing.pairing_cost import PairingCostFunction, current_pairing_cost
from crew_pairing.pairings import Pairing
from crew_pairing.solution_validator import ValidationResult


RUN_DATETIME_FORMAT = "%d/%m/%y %H:%M"


def run_timestamp() -> str:
    """Return local run date and time, without seconds or a timezone suffix."""
    return datetime.now().strftime(RUN_DATETIME_FORMAT)


@dataclass
class CgSummary:
    completed_iterations: int = 0
    pairing_pool_size: int | None = None
    termination_reason: str | None = None


@dataclass
class LpSummary:
    problem_status: str | None = None
    solution_status: str | None = None
    dual_solution_status: str | None = None
    objective_value: float | None = None
    artificials_above_tolerance: int | None = None


@dataclass
class IlpSummary:
    attempted: bool = False
    skip_reason: str | None = "run_did_not_reach_final_ilp"
    problem_status: str | None = None
    solution_status: str | None = None
    validation: ValidationResult | None = None


@dataclass
class IntegerSolutionSummary:
    cost: float
    selected_pairing_count: int
    generated_at: str | None = None
    pairings: list[dict] | None = None


@dataclass
class RunSummary:
    schema_version: int = 4
    run_id: str = field(default_factory=lambda: uuid4().hex)
    started_at: str = field(default_factory=run_timestamp)
    random_seed: int | None = None
    batch_run_index: int | None = None
    runtime_seconds: dict[str, float | None] = field(
        default_factory=lambda: {
            "total": None,
            "build_graphs": None,
            "initial_pool": None,
            "column_generation": None,
            "final_ilp": None,
        }
    )
    column_generation: CgSummary = field(default_factory=CgSummary)
    lp: LpSummary = field(default_factory=LpSummary)
    ilp: IlpSummary = field(default_factory=IlpSummary)
    integer_solution: IntegerSolutionSummary | None = None
    outcome: str = "execution_error"
    outcome_detail: str | None = None
    error: dict[str, str] | None = None


@dataclass
class BatchSummary:
    schema_version: int = 3
    batch_id: str = field(default_factory=lambda: uuid4().hex)
    started_at: str = field(default_factory=run_timestamp)
    finished_at: str | None = None
    random_seed: int | None = None
    seed_strategy: str = "shared_stream"
    requested_runs: int = 5
    completed_runs: int = 0
    runtime_seconds: dict[str, float | None] = field(
        default_factory=lambda: {"total": None, "build_graphs": None}
    )
    runs: list[dict] = field(default_factory=list)
    best_run_id: str | None = None
    best_cost: float | None = None
    best_solution_path: str | None = None
    outcome: str = "no_integer_solution_found"
    error: dict[str, str] | None = None


def compact_run_record(summary: RunSummary) -> dict:
    """Copy run metadata and solution metrics without copying pairing records."""
    record = asdict(replace(summary, integer_solution=None))
    solution = summary.integer_solution
    if solution is not None:
        record["integer_solution"] = {
            "cost": solution.cost,
            "selected_pairing_count": solution.selected_pairing_count,
            "generated_at": solution.generated_at,
        }
    return record


@contextmanager
def measure_runtime(summary: RunSummary | None, phase: str) -> Iterator[None]:
    """Record one phase's elapsed seconds, including an interrupted phase."""
    if summary is None:
        yield
        return
    started = perf_counter()
    try:
        yield
    finally:
        summary.runtime_seconds[phase] = perf_counter() - started


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


def selected_pairings_payload(
    pairings: Mapping[str, Pairing],
    total_cost: float | None = None,
    cost_function: PairingCostFunction = current_pairing_cost,
) -> dict:
    """Build the existing export payload for standalone or combined results."""
    ordered = sorted(
        pairings.values(),
        key=lambda pairing: (pairing.start_time, pairing.pairing_id),
    )
    return {
        "generated_at": run_timestamp(),
        "total_cost": total_cost,
        "selected_count": len(ordered),
        "pairings": [
            _pairing_record(pairing, cost_function(pairing)) for pairing in ordered
        ],
    }


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


def save_selected_pairings(
    pairings: Mapping[str, Pairing],
    output_path: str | Path,
    total_cost: float | None = None,
    cost_function: PairingCostFunction = current_pairing_cost,
) -> Path:
    """Write chosen pairings, with nested duties and flights, as JSON."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    payload = selected_pairings_payload(pairings, total_cost, cost_function)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def save_run_result(summary: RunSummary, directory: str | Path) -> Path:
    """Create a new JSON file, refusing to overwrite an existing run."""
    return _save_json(asdict(summary), Path(directory) / f"run_{summary.run_id}.json")


def save_best_run(summary: RunSummary, directory: str | Path, batch_id: str) -> Path:
    """Save the batch's winning run in the existing full result format."""
    return _save_json(asdict(summary), Path(directory) / f"best_{batch_id}.json")


def save_run_comparison(summary: BatchSummary, directory: str | Path) -> Path:
    return _save_json(asdict(summary), Path(directory) / f"comparison_{summary.batch_id}.json")


def _save_json(payload: dict, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        json.dump(payload, stream, indent=2, allow_nan=False)
        stream.write("\n")
    return path
