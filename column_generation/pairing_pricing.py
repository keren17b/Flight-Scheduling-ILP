"""Pricing DFS: guided randomized search for legal pairings with negative reduced cost."""

from __future__ import annotations

import random
from datetime import timedelta
from typing import Dict, List, Set, Tuple

from crew_pairing.duties import Duty
from crew_pairing.duty_graph import DutyGraph
from crew_pairing.pairing_cost import PairingCostFunction, current_pairing_cost
from crew_pairing.pairings import (
    MAX_DUTIES_PER_PAIRING,
    MAX_PAIRING_TIME,
    Pairing,
    build_pairing_from_path,
    pairing_signature,
)
from column_generation.config import (
    MAX_NEGATIVE_PAIRINGS_PER_START,
    MAX_PRICING_DFS_STATES_PER_START,
    MAX_PRICING_PAIRINGS,
    PRICING_RANDOM_SEED,
    TOP_K_SUCCESSORS,
)
from run_progress import ProgressTicker


SECONDS_PER_HOUR = 3600.0


def _reduced_cost(
    pairing: Pairing,
    duals: Dict[str, float],
    cost_function: PairingCostFunction,
) -> float:
    dual_sum = 0.0
    for duty in pairing.duties:
        for flight in duty.flights:
            dual_sum += duals[flight.flight_id]
    return cost_function(pairing) - dual_sum


def _successor_score(
    current_duty: Duty,
    next_duty: Duty,
    duals: Dict[str, float],
) -> float:
    """
    Heuristic score used only to rank successors before DFS expansion.

    Lower is better. With the current cost model this is the incremental
    reduced-cost contribution of moving from current_duty to next_duty:
    rest between duties + sitting time inside next_duty - flight duals.

    Final acceptance of a closed pairing always uses _reduced_cost(), so the
    pricing decision remains based on the real pairing cost function.
    """
    rest_hours = (
        next_duty.start_time - current_duty.end_time
    ).total_seconds() / SECONDS_PER_HOUR
    sitting_hours = next_duty.sitting_time.total_seconds() / SECONDS_PER_HOUR
    dual_sum = sum(duals[flight.flight_id] for flight in next_duty.flights)
    return rest_hours + sitting_hours - dual_sum


def generate_pricing_pairings(
    graph: DutyGraph,
    duals: Dict[str, float],
    existing_pairing_signature: Set[Tuple[str, ...]],
    max_pairing_time: timedelta = MAX_PAIRING_TIME,
    max_duties: int = MAX_DUTIES_PER_PAIRING,
    max_pairings: int = MAX_PRICING_PAIRINGS,
    max_dfs_states_per_start: int = MAX_PRICING_DFS_STATES_PER_START,
    max_negative_pairings_per_start: int = MAX_NEGATIVE_PAIRINGS_PER_START,
    top_k_successors: int = TOP_K_SUCCESSORS,
    random_seed: int = PRICING_RANDOM_SEED,
    cost_function: PairingCostFunction = current_pairing_cost,
) -> Tuple[Dict[str, Pairing], Set[Tuple[str, ...]]]:
    """
    Search the duty graph for new pairings with negative reduced cost.

    The original DFS structure is kept, with four bounded-search additions:

    1. Every legal starting duty gets its own DFS-state budget.
    2. Every starting duty may contribute only a bounded number of new,
       unique, negative-reduced-cost pairings.
    3. At every DFS state, legal successors are ranked by a dual-guided score;
       only the best top_k_successors are explored.
    4. The selected Top-K successors and the starting duties are shuffled to
       avoid always exploring the same branch first.

    There is intentionally no post-pricing filter here. Every new, unique
    pairing with negative reduced cost is kept immediately, until the global
    max_pairings limit is reached.
    """
    if max_pairing_time <= timedelta(0):
        raise ValueError("max_pairing_time must be positive")
    if max_duties < 1:
        raise ValueError("max_duties must be at least 1")
    if max_pairings < 1:
        raise ValueError("max_pairings must be at least 1")
    if max_dfs_states_per_start < 1:
        raise ValueError("max_dfs_states_per_start must be at least 1")
    if max_negative_pairings_per_start < 1:
        raise ValueError("max_negative_pairings_per_start must be at least 1")
    if top_k_successors < 1:
        raise ValueError("top_k_successors must be at least 1")

    pairings: Dict[str, Pairing] = {}
    ticker = ProgressTicker("Pricing search")
    searched_paths = 0

    # The signature count changes between CG iterations, so this keeps the
    # search reproducible while still changing the randomized traversal order
    # from one pricing call to the next.
    rng = random.Random(random_seed + len(existing_pairing_signature))

    def global_pairing_limit_reached() -> bool:
        return len(pairings) >= max_pairings

    def dfs(
        current_duty: Duty,
        path: List[Duty],
        local_states: List[int],
        local_negative_saved: List[int],
    ) -> None:
        nonlocal searched_paths

        if local_states[0] >= max_dfs_states_per_start:
            return
        if local_negative_saved[0] >= max_negative_pairings_per_start:
            return
        if global_pairing_limit_reached():
            return

        local_states[0] += 1
        searched_paths += 1
        if searched_paths % 10_000 == 0:
            ticker.update(
                searched_paths,
                f"{len(pairings):,} new negative pairings found",
            )

        returned_to_base = (
            current_duty.end_airport.is_crew_base
            and current_duty.end_airport.port_name
            == path[0].start_airport.port_name
        )
        if returned_to_base:
            signature = pairing_signature(path)
            if signature not in existing_pairing_signature:
                pairing_id = f"P{len(pairings) + 1}"
                pairing = build_pairing_from_path(pairing_id, path)
                if _reduced_cost(pairing, duals, cost_function) < 0:
                    pairings[pairing_id] = pairing
                    existing_pairing_signature.add(signature)
                    local_negative_saved[0] += 1

        if len(path) >= max_duties:
            return
        if local_states[0] >= max_dfs_states_per_start:
            return
        if local_negative_saved[0] >= max_negative_pairings_per_start:
            return
        if global_pairing_limit_reached():
            return

        feasible_successors: List[Duty] = []
        for next_duty in graph.get(current_duty, []):
            if next_duty in path:
                continue

            total_time = next_duty.end_time - path[0].start_time
            if total_time > max_pairing_time:
                continue

            feasible_successors.append(next_duty)

        # Lower score is more promising. Rank first, keep only Top-K, then
        # shuffle that promising subset so a bounded DFS does not always enter
        # the same branch first.
        feasible_successors.sort(
            key=lambda next_duty: (
                _successor_score(current_duty, next_duty, duals),
                next_duty.duty_id,
            )
        )
        top_successors = feasible_successors[:top_k_successors]
        rng.shuffle(top_successors)

        for next_duty in top_successors:
            path.append(next_duty)
            dfs(
                next_duty,
                path,
                local_states,
                local_negative_saved,
            )
            path.pop()

            if local_states[0] >= max_dfs_states_per_start:
                return
            if local_negative_saved[0] >= max_negative_pairings_per_start:
                return
            if global_pairing_limit_reached():
                return

    starting_duties: List[Duty] = []
    for first_duty in graph:
        if not first_duty.start_airport.is_crew_base:
            continue

        first_duty_time = first_duty.end_time - first_duty.start_time
        if timedelta(0) <= first_duty_time <= max_pairing_time:
            starting_duties.append(first_duty)

    rng.shuffle(starting_duties)

    for first_duty in starting_duties:
        if global_pairing_limit_reached():
            break

        dfs(
            first_duty,
            [first_duty],
            [0],  # states visited from this starting duty
            [0],  # unique negative-RC pairings saved from this starting duty
        )

    return pairings, existing_pairing_signature
