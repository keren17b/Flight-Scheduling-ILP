"""Temporary run progress messages. Set ILP_PROGRESS=0 to silence them."""

import os
from time import monotonic


_START = monotonic()
_ENABLED = os.environ.get("ILP_PROGRESS", "1").lower() not in {"0", "false", "no"}


def progress(message: str) -> None:
    """Print a recognizable, immediately visible progress message."""
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
