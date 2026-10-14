"""Validate selected pairings against input flights without using a solver."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, replace
from datetime import timedelta
from math import fsum, isclose, isfinite
from typing import Mapping

from crew_pairing.config import (
    DEFAULT_MAX_CONNECTION,
    DEFAULT_MIN_CONNECTION,
    MAX_ACTUAL_FLIGHT_TIME,
    MAX_DUTIES_PER_PAIRING,
    MAX_ELAPSED_DUTY_TIME,
    MAX_FLIGHTS_PER_DUTY,
    MAX_LAYOVER_BETWEEN_DUTIES,
    MAX_PAIRING_TIME,
    MIN_REST_BETWEEN_DUTIES,
)
from crew_pairing.duties import Duty
from crew_pairing.flights_graph import Flight
from crew_pairing.padding_flights import is_padding_flight
from crew_pairing.pairing_cost import PairingCostFunction, current_pairing_cost
from crew_pairing.pairings import Pairing, build_pairing_from_path


@dataclass
class ValidationResult:
    is_valid: bool
    errors: list[str]


def validate_solution(
    selected_pairings: Mapping[str, Pairing],
    flights: Mapping[str, Flight],
    total_cost: float,
    cost_function: PairingCostFunction = current_pairing_cost,
) -> ValidationResult:
    """Collect coverage, legality and objective errors for selected columns only.

    Checks performed:
        Flight coverage and input consistency:
            - Every required flight is covered exactly once.
            - Every padding flight is covered at most once, using the existing
              departure-date classification in is_padding_flight().
            - No flight ID repeats within a pairing, including across duties,
              or is covered by multiple selected pairings.
            - Every referenced flight ID exists in the original input, and its
              Flight object has the same data as the original Flight.

        Pairing legality:
            - Each pairing contains at least one duty, starts at a Crew Base,
              and ends at that same airport.
            - Duty count does not exceed MAX_DUTIES_PER_PAIRING.
            - Elapsed time from the first departure to the last arrival,
              including rest, does not exceed MAX_PAIRING_TIME.

        Duty legality:
            - Each duty contains at least one flight, and each flight arrives
              strictly after its departure.
            - Consecutive flights connect at the same airport, and the next
              departure is strictly after the previous arrival.
            - Connection time is within the inclusive limits
              DEFAULT_MIN_CONNECTION and DEFAULT_MAX_CONNECTION.
            - Elapsed duty time does not exceed MAX_ELAPSED_DUTY_TIME.
            - Summed flight durations do not exceed MAX_ACTUAL_FLIGHT_TIME.
            - Flight count does not exceed MAX_FLIGHTS_PER_DUTY.

        Connections between duties:
            - Consecutive duties connect at the same airport.
            - Time from the previous duty's last arrival to the next duty's
              first departure is at least MIN_REST_BETWEEN_DUTIES and at most
              MAX_LAYOVER_BETWEEN_DUTIES.

        Total cost:
            - Rebuild duty and pairing durations from original flight data and
              recalculate each selected pairing's cost with cost_function.
            - Reconstructed metadata must satisfy the existing Duty and Pairing
              dataclass invariants, and calculated costs must be finite.
            - The reported ILP objective must be finite and, when every pairing
              cost can be reconstructed, match the recalculated total within
              the floating-point tolerance below.

    Flight IDs are resolved against the original input, and all times used for
    legality and cost are recomputed. Temporary copies preserve input objects
    and IDs while giving the cost function independently derived metadata.
    The objective comparison allows 1e-6 absolute and 1e-9 relative error.
    No optimization is run. All detectable errors are collected in the returned
    ValidationResult; is_valid is True only when the error list is empty.
    """
    errors: list[str] = []
    coverage: dict[str, list[str]] = defaultdict(list)
    costs: list[float] = []
    cost_complete = True

    for pairing_id, pairing in selected_pairings.items():
        context = f"Pairing {pairing_id}"
        if not pairing.duties:
            errors.append(f"{context}: contains no duties.")
            cost_complete = False
            continue
        if len(pairing.duties) > MAX_DUTIES_PER_PAIRING:
            errors.append(
                f"{context}: duty count {len(pairing.duties)} exceeds "
                f"MAX_DUTIES_PER_PAIRING ({MAX_DUTIES_PER_PAIRING})."
            )

        seen: set[str] = set()
        resolved_duties: list[list[Flight | None]] = []
        rebuilt_duties: list[Duty] = []
        pairing_cost_complete = True
        for duty in pairing.duties:
            duty_context = f"{context}, Duty {duty.duty_id}"
            resolved: list[Flight | None] = []
            resolved_duties.append(resolved)
            if not duty.flights:
                errors.append(f"{duty_context}: contains no flights.")
            if len(duty.flights) > MAX_FLIGHTS_PER_DUTY:
                errors.append(
                    f"{duty_context}: flight count {len(duty.flights)} exceeds "
                    f"MAX_FLIGHTS_PER_DUTY ({MAX_FLIGHTS_PER_DUTY})."
                )

            for reference in duty.flights:
                flight_id = reference.flight_id
                coverage[flight_id].append(pairing_id)
                if flight_id in seen:
                    errors.append(f"{duty_context}: Flight {flight_id} appears more than once within the pairing.")
                seen.add(flight_id)
                flight = flights.get(flight_id)
                resolved.append(flight)
                if flight is None:
                    errors.append(f"{duty_context}: unknown Flight {flight_id}.")
                elif reference != flight:
                    errors.append(
                        f"{duty_context}: Flight {flight_id} differs from the original input data."
                    )
                if flight is not None and flight.arrival_datetime <= flight.departure_datetime:
                    errors.append(
                        f"{duty_context}: Flight {flight_id} is not chronological "
                        "(arrival must follow departure)."
                    )

            for first, second in zip(resolved, resolved[1:]):
                if first is None or second is None:
                    continue
                connection_context = f"{duty_context}, Flights {first.flight_id} -> {second.flight_id}"
                if first.destination.port_name != second.origin.port_name:
                    errors.append(f"{connection_context}: airports do not connect.")
                connection = second.departure_datetime - first.arrival_datetime
                if second.departure_datetime <= first.arrival_datetime:
                    errors.append(f"{connection_context}: flights are not chronological.")
                if not DEFAULT_MIN_CONNECTION <= connection <= DEFAULT_MAX_CONNECTION:
                    errors.append(
                        f"{connection_context}: connection time {connection} is outside "
                        f"[{DEFAULT_MIN_CONNECTION}, {DEFAULT_MAX_CONNECTION}]."
                    )

            if not resolved:
                pairing_cost_complete = False
                continue
            original_flights = tuple(flight for flight in resolved if flight is not None)
            elapsed = None
            if resolved[0] is not None and resolved[-1] is not None:
                elapsed = resolved[-1].arrival_datetime - resolved[0].departure_datetime
                if elapsed > MAX_ELAPSED_DUTY_TIME:
                    errors.append(
                        f"{duty_context}: elapsed time {elapsed} exceeds "
                        f"MAX_ELAPSED_DUTY_TIME ({MAX_ELAPSED_DUTY_TIME}); "
                        f"Flights {resolved[0].flight_id} -> {resolved[-1].flight_id}."
                    )
            flight_time = sum(
                (flight.arrival_datetime - flight.departure_datetime for flight in original_flights),
                timedelta(0),
            )
            if flight_time > MAX_ACTUAL_FLIGHT_TIME:
                errors.append(
                    f"{duty_context}: flight time {flight_time} exceeds "
                    f"MAX_ACTUAL_FLIGHT_TIME ({MAX_ACTUAL_FLIGHT_TIME}); "
                    f"Flights {[f.flight_id for f in original_flights]}."
                )
            if any(flight is None for flight in resolved):
                pairing_cost_complete = False
                continue
            try:
                rebuilt_duties.append(replace(
                    duty, flights=original_flights, total_time=elapsed,
                    flight_time=flight_time, sitting_time=elapsed - flight_time,
                ))
            except ValueError as error:
                errors.append(f"{duty_context}: cannot reconstruct cost metadata: {error}.")
                pairing_cost_complete = False

        first = resolved_duties[0][0] if resolved_duties[0] else None
        last = resolved_duties[-1][-1] if resolved_duties[-1] else None
        if first is not None:
            if first.origin.is_crew_base != 1:
                errors.append(
                    f"{context}: Flight {first.flight_id} starts at "
                    f"{first.origin.port_name}, which is not a Crew Base."
                )
            if last is not None:
                if last.destination.port_name != first.origin.port_name:
                    errors.append(
                        f"{context}: Flight {last.flight_id} ends at {last.destination.port_name}, "
                        f"not starting Crew Base {first.origin.port_name} (Flight {first.flight_id})."
                    )
                elapsed = last.arrival_datetime - first.departure_datetime
                if elapsed > MAX_PAIRING_TIME:
                    errors.append(
                        f"{context}: elapsed time {elapsed} exceeds MAX_PAIRING_TIME "
                        f"({MAX_PAIRING_TIME}); Flights {first.flight_id} -> {last.flight_id}."
                    )

        for previous, following in zip(resolved_duties, resolved_duties[1:]):
            first = previous[-1] if previous else None
            second = following[0] if following else None
            if first is None or second is None:
                continue
            connection_context = (
                f"{context}, duty boundary Flights {first.flight_id} -> {second.flight_id}"
            )
            if first.destination.port_name != second.origin.port_name:
                errors.append(f"{connection_context}: airports do not connect.")
            rest = second.departure_datetime - first.arrival_datetime
            if rest < MIN_REST_BETWEEN_DUTIES:
                errors.append(
                    f"{connection_context}: rest {rest} is below "
                    f"MIN_REST_BETWEEN_DUTIES ({MIN_REST_BETWEEN_DUTIES})."
                )
            if rest > MAX_LAYOVER_BETWEEN_DUTIES:
                errors.append(
                    f"{connection_context}: layover {rest} exceeds "
                    f"MAX_LAYOVER_BETWEEN_DUTIES ({MAX_LAYOVER_BETWEEN_DUTIES})."
                )

        if pairing_cost_complete:
            try:
                rebuilt = build_pairing_from_path(pairing.pairing_id, rebuilt_duties)
                cost = float(cost_function(rebuilt))
                if not isfinite(cost):
                    raise ValueError(f"non-finite cost {cost}")
                costs.append(cost)
            except (ValueError, ArithmeticError) as error:
                errors.append(f"{context}: cannot recalculate cost: {error}.")
                pairing_cost_complete = False
        cost_complete = cost_complete and pairing_cost_complete

    for flight_id, flight in flights.items():
        occurrences = coverage.get(flight_id, [])
        if is_padding_flight(flight):
            if len(occurrences) > 1:
                errors.append(
                    f"Padding Flight {flight_id}: covered {len(occurrences)} times, "
                    f"must be at most once; Pairings {occurrences}."
                )
        elif len(occurrences) != 1:
            errors.append(
                f"Required Flight {flight_id}: covered {len(occurrences)} times, "
                f"must be exactly once; Pairings {occurrences}."
            )
    for flight_id, occurrences in coverage.items():
        owners = list(dict.fromkeys(occurrences))
        if len(owners) > 1:
            errors.append(f"Flight {flight_id}: covered by multiple selected Pairings {owners}.")

    if not isfinite(total_cost):
        errors.append(f"Reported ILP objective is not finite: {total_cost}.")
    elif cost_complete:
        calculated = fsum(costs)
        if not isclose(calculated, total_cost, rel_tol=1e-9, abs_tol=1e-6):
            errors.append(
                f"Total cost mismatch: recalculated {calculated}, "
                f"reported ILP objective {total_cost}; Pairings {list(selected_pairings)}."
            )

    return ValidationResult(is_valid=not errors, errors=errors)
