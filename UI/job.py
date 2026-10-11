"""Background adapter to the shared run manager. No Streamlit calls here."""

from dataclasses import dataclass
from pathlib import Path
from threading import Lock, Thread
from time import monotonic


@dataclass(frozen=True)
class CompletedResult:
    data: bytes | None
    filename: str | None
    outcome: str
    error: str | None = None


class OptimizationJob:
    def __init__(self, initial_seed: int, run_count: int):
        self.initial_seed = initial_seed
        self.run_count = run_count
        self._lock = Lock()
        self._started = False
        self._started_at = None
        self._finished_at = None
        self._run = 1
        self._stage = "loading data"
        self._result = None

    def start(self):
        with self._lock:
            if self._started:
                return False
            self._started = True
            self._started_at = monotonic()
        Thread(target=self._execute, daemon=True, name="crew-pairing-run").start()
        return True

    def _progress(self, stage, run_index):
        with self._lock:
            self._stage = stage
            if run_index is not None:
                self._run = run_index

    def _execute(self):
        try:
            # Import lazily: viewing saved JSON does not load MOSEK or graphs.
            from main import run_batch
            batch = run_batch(
                self.initial_seed, self.run_count, consecutive_seeds=True,
                on_progress=self._progress,
            )
            path = batch.summary.best_solution_path
            result = CompletedResult(
                Path(path).read_bytes() if path else None,
                Path(path).name if path else None,
                batch.summary.outcome,
            )
        except Exception as error:
            result = CompletedResult(None, None, "execution_error", str(error))
        with self._lock:
            self._result = result
            self._finished_at = monotonic()

    def snapshot(self):
        with self._lock:
            elapsed = 0 if self._started_at is None else (
                (self._finished_at or monotonic()) - self._started_at
            )
            return self._run, self._stage, elapsed, self._result
