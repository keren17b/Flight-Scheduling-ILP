"""Replaceable cost functions for generated crew pairings."""

from __future__ import annotations

from typing import Callable

from crew_pairing.duties import Duty
from crew_pairing.pairings import Pairing


SECONDS_PER_HOUR = 3600
PairingCostFunction = Callable[[Pairing], float]


def current_pairing_cost(pairing: Pairing) -> float:
    """Return the existing cost model: rest plus sitting time, in hours."""
    non_flight_time = pairing.rest + pairing.sitting_time
    return non_flight_time.total_seconds() / SECONDS_PER_HOUR


def duty_incremental_cost(current_duty: Duty, next_duty: Duty) -> float:
    """Return added rest and sitting hours under the current pairing cost model.

    This is a transition's contribution, not the cost of a complete pairing.
    """
    rest_hours = (
        next_duty.start_time - current_duty.end_time
    ).total_seconds() / SECONDS_PER_HOUR
    sitting_hours = next_duty.sitting_time.total_seconds() / SECONDS_PER_HOUR
    return rest_hours + sitting_hours
