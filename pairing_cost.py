"""Replaceable cost functions for generated crew pairings."""

from __future__ import annotations

from typing import Callable

from pairings import Pairing


SECONDS_PER_HOUR = 3600
PairingCostFunction = Callable[[Pairing], float]


def current_pairing_cost(pairing: Pairing) -> float:
    """Return the existing cost model: rest plus sitting time, in hours."""
    non_flight_time = pairing.rest + pairing.sitting_time
    return non_flight_time.total_seconds() / SECONDS_PER_HOUR
