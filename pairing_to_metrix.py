"""Build the pairing-flight coverage matrix and pairing costs for the ILP solver."""

from __future__ import annotations

from typing import Dict, List, Tuple

import numpy as np

from flights_graph import Flight
from pairings import Pairing


def pairings_to_matrix(
    flights: Dict[str, Flight],
    pairings: Dict[str, Pairing],
) -> Tuple[np.ndarray, List[float]]:
    """
    Convert pairings and flights into the binary coverage matrix and cost list.

    Rows are pairings in dict order. Columns are flights in dict order.
    Entry (i, j) is 1 if pairing i covers flight j, otherwise 0.
    costs[i] is the cost of the pairing in row i.
    """
    flight_ids = list(flights.keys())
    flight_index = {flight_id: index for index, flight_id in enumerate(flight_ids)}

    matrix = np.zeros((len(pairings), len(flight_ids)), dtype=int)
    costs: List[float] = []

    for row, pairing in enumerate(pairings.values()):
        costs.append(pairing.cost)
        for duty in pairing.duties:
            for flight in duty.flights:
                column = flight_index[flight.flight_id]
                matrix[row, column] = 1

    return matrix, costs
