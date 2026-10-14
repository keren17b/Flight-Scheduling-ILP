"""Temporary run progress messages. Set ILP_PROGRESS=0 to silence them."""

import os
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from time import monotonic


_START = monotonic()
_ENABLED = os.environ.get("ILP_PROGRESS", "1").lower() not in {"0", "false", "no"}
_STAGE_OBSERVER = ContextVar("stage_observer", default=None)
_MESSAGE_OBSERVER = ContextVar("message_observer", default=None)


@dataclass(frozen=True)
class ProgressMessage:
    text: str
    iteration: int | None = None
    new_pairings: int | None = None
    lp_objective: float | None = None


@contextmanager
def observe_messages(callback):
    """Receive raw messages and optional CG metadata for this execution only."""
    token = _MESSAGE_OBSERVER.set(callback)
    try:
        yield
    finally:
        _MESSAGE_OBSERVER.reset(token)


@contextmanager
def observe_stages(callback):
    """Observe this execution's stages without redirecting global stdout."""
    token = _STAGE_OBSERVER.set(callback)
    try:
        yield
    finally:
        _STAGE_OBSERVER.reset(token)


def stage(name: str, run_index: int | None = None) -> None:
    """Report a phase boundary independently of verbose console progress."""
    callback = _STAGE_OBSERVER.get()
    if callback is not None:
        callback(name, run_index)


def progress(message: str, *, iteration: int | None = None,
             new_pairings: int | None = None, lp_objective: float | None = None) -> None:
    """Print a recognizable, immediately visible progress message."""
    callback = _MESSAGE_OBSERVER.get()
    if callback is not None:
        callback(ProgressMessage(message, iteration, new_pairings, lp_objective))
    if _ENABLED:
        print(f"[ILP PROGRESS +{monotonic() - _START:.1f}s] {message}", flush=True)


class ProgressTicker:
    """Report a busy loop at most once every five seconds."""

    def __init__(self, stage: str, interval_seconds: float = 5.0) -> None:
        self.stage = stage
        self.interval_seconds = interval_seconds
        self.last_report = monotonic()

    def update(self, completed: int, detail: str = "") -> None:
        if not _ENABLED:
            return
        now = monotonic()
        if now - self.last_report >= self.interval_seconds:
            progress(f"{self.stage}: {completed:,} processed{'; ' + detail if detail else ''}")
            self.last_report = now
