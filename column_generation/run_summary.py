"""Serializable summary and selected pairings for one run."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
from contextlib import contextmanager
from datetime import datetime
import json
from pathlib import Path
from time import perf_counter
from typing import Iterator
from uuid import uuid4


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
