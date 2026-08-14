"""Duty connection graph built from generated duties."""

from __future__ import annotations

from datetime import timedelta
from typing import Dict, Iterable, List, Mapping

from duties import Duty


# Legality / safety: minimum rest required between consecutive duties.
MIN_REST_BETWEEN_DUTIES = timedelta(hours=12)

# Modeling / pruning: maximum layover allowed when linking two duties.
MAX_LAYOVER_BETWEEN_DUTIES = timedelta(hours=48)

DutyGraph = Dict[Duty, List[Duty]]


def can_connect_duties(
    first: Duty,
    second: Duty,
    min_rest: timedelta = MIN_REST_BETWEEN_DUTIES,
    max_layover: timedelta = MAX_LAYOVER_BETWEEN_DUTIES,
) -> bool:
    """
    Return True if second can follow first as a valid duty connection.

    Requires:
    - second starts at the airport where first ended
    - second starts after first ends
    - layover time is within [min_rest, max_layover]
    """
    if first.end_airport.port_name != second.start_airport.port_name:
        return False
    if second.start_time <= first.end_time:
        return False

    layover_time = second.start_time - first.end_time
    return min_rest <= layover_time <= max_layover


def build_duty_graph(
    duties: Iterable[Duty],
    min_rest: timedelta = MIN_REST_BETWEEN_DUTIES,
    max_layover: timedelta = MAX_LAYOVER_BETWEEN_DUTIES,
) -> DutyGraph:
    """
    Build an adjacency list where each node is a Duty.

    Edge D1 -> D2 exists only when end/start airports match and the
    layover time is within [min_rest, max_layover].
    """

    duty_list = list(duties)

    graph: DutyGraph = {duty: [] for duty in duty_list}

    for first in duty_list:
        for second in duty_list:
            if first is second:
                continue
            if can_connect_duties(first, second, min_rest, max_layover):
                graph[first].append(second)

    return graph
