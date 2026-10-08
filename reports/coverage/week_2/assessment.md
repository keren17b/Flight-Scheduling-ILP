# Required-flight coverage diagnosis

The active January 5-16 dataset has 243 required flights (January 8-14).
With the current 10-hour minimum rest, the MOSEK master LP leaves
`LEG_14_26` fully uncovered by real pairings (artificial variable = 1).
All other required-flight constraints have zero artificial coverage.
This is an LP result, not a final integer schedule.

## Flight conflict on January 14, 2000

| Flight | Route | Departure | Arrival |
| --- | --- | --- | --- |
| LEG_14_26 | BASE2 to AIR12 | 01:04 | 03:46 |
| LEG_14_28 | AIR12 to BASE2 | 13:45 | 16:34 |
| LEG_14_31 | BASE2 to AIR12 | 12:59 | 15:46 |
| LEG_14_29 | AIR12 to BASE2 | 17:00 | 19:52 |

`LEG_14_26` cannot connect to `LEG_14_28`: the gap is 9h59,
which exceeds the 8h maximum connection within one duty and falls one minute
below the 10h minimum rest between duties.
Its only possible return in a closed pairing is `LEG_14_29`.
`LEG_14_31` also requires `LEG_14_29` in every closed pairing.
The two outbounds cannot share one pairing because their flights cannot
form one duty and the early flight's first possible successor is after the
later outbound has departed. Covering them in separate pairings would use
`LEG_14_29` twice, which the model forbids.

Therefore at least one of these two required outbound flights must remain
uncovered in any LP or ILP solution under the current constraints.
The observed LP attains that lower bound with a deficit of exactly one,
currently assigned to `LEG_14_26`. A different solution could assign it to
`LEG_14_31` instead. This is a structural conflict, not a missing pairing
caused by search budgets or an incorrect base list.

## Why padding does not resolve it

There are no departures from AIR12 on January 15 or 16. Earlier padding
cannot provide a return after these January 14 outbound flights.
The exact coverage audit found a legal pairing for each required flight
individually, and the initial pool contained all 243 required flights.
Individual coverability does not guarantee simultaneous coverage.

## Verified local alternative

With a hypothetical minimum rest of 9h59, two disjoint legal pairings exist:
`LEG_14_26 -> LEG_14_28` and `LEG_14_31 -> LEG_14_29`.
This resolves the local conflict. It does not by itself establish feasibility
of a complete integer schedule. Production settings and flight times were
not changed.

## Verification scope

The exact audit used the production flight, duty, and duty-connection rules
and found 60,833,749 legal closed pairing paths.
The graph proof checked all 18 duties containing `LEG_14_26` and all 9 duties
containing `LEG_14_31`: avoiding `LEG_14_29` leaves every relevant duty at
AIR12 without any successor that avoids that return.
The production initial pool contained 1,529 pairings.
MOSEK completed 57 production pricing iterations and 58 master solves,
ending with 19,513 columns and artificial sum 1.
Further pricing and redundant exact-path counting were stopped after the
conflict and matching deficit were proven. The final ILP was not run.

Evidence: `audit.json`, `master_history.json`, `conflict_proof.json`,
`rest_gap.json`, and `solution.json` in this directory.
