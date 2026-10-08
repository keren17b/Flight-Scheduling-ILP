# Original instance1 solution audit

The original `initialSolution.in` is directly related to the flight data in this project. It covers `LEG_02_27` in Pairing 95, using `LEG_02_25` to reach AIR12 first and a 9h59 arrival-to-departure gap. The current 10-hour minimum rest rejects that connection.

No flight times, dataset files, or production rules were changed during this audit.

## Sources and coverage

The supplied temporary extraction path was unavailable as an ordinary directory. The audit read `instance1.zip` inside the workspace copy of `data/source/G1422-DataSets.zip`. The source files copied into this report directory retain their original contents.

- All 1,013 source flight records match the project's `all_days.csv`, including identifiers, airports, and timestamps.
- `initialSolution.in` contains 172 pairings, with all 1,013 flights operated exactly once.
- It also contains 40 deadhead occurrences involving 38 distinct flights. Deadheading means transporting a crew member as a passenger to reposition them.
- Every referenced flight exists. All consecutive legs have matching arrival/departure airports and nonnegative time gaps.
- `solution_0` contains 33 employee schedules and identifies the crew assigned to the relevant pairings.

The README, page 11, describes `initialSolution.in` as an initial solution of the pairing problem and `solution_0` as detailed crew schedules from a previous scheduling solution. These are reference solution files; this audit did not rerun their original solver or establish their optimality.

## How the disputed flights were covered

| Reference pairing | Employee in solution_0 | Relevant operating flights | Gap at AIR12 |
| --- | --- | --- | --- |
| 8 | EMP030 | `01_30 → 01_28` | Jan 1, 15:46 → 17:00: **1h14** |
| 95 | EMP026 | `02_25 → 02_27`, followed by six more flights | Jan 2, 03:46 → 13:45: **9h59** |

Thus, the reference solution uses two separate outbound flights: `01_30` supplies the crew for `01_28`; `02_25` supplies the crew for `02_27`. Neither of these two connections is marked as deadhead.

Pairing 95 appears at line 191 of `initialSolution.in`:

```text
LEG_02_25 → LEG_02_27 → LEG_02_21 → LEG_02_4 → LEG_02_5
           → LEG_03_7 → LEG_03_6 → LEG_03_8
```

One valid split under the current other duty limits, if the minimum rest were 9h59, is:

| Duty | Flights | Start | End | Arrival-to-departure gap before next duty |
| --- | --- | --- | --- | --- |
| 1 | `02_25` | Jan 2 01:04 | Jan 2 03:46 | **9h59** |
| 2 | `02_27, 02_21, 02_4, 02_5` | Jan 2 13:45 | Jan 3 00:22 | **11h58** |
| 3 | `03_7, 03_6, 03_8` | Jan 3 12:20 | Jan 3 20:23 | — |

The source does not explicitly encode duty boundaries; this table reconstructs a feasible split using the project's other duty limits. The first two legs cannot belong to one duty under those limits: their gap exceeds the 8-hour connection maximum and their combined elapsed span is 15h30, exceeding the 12-hour duty maximum. Therefore the 9h59 gap is a decisive failure under the project's 10-hour minimum rest.

In `solution_0`, EMP026's same sequence begins `PAL_LEG_02_25 → LEG_02_27`. The original generator code treats `PAL_` as a preferred airleg marker. It does not mean passenger/deadhead. The deadhead marker is `TDH_`.

## Broader differences from the current rules

All 13 AIR12 connections with a 9h59 gap identified in the flight-data scan occur in the original pairings. The source solution also contains other gaps below 10 hours:

| Gap | Occurrences |
| --- | ---: |
| 9h01 | 3 |
| 9h05 | 1 |
| 9h18 | 11 |
| 9h30 | 1 |
| 9h40 | 2 |
| 9h48 | 1 |
| 9h59 | 13 |
| **Total** | **32** |

These are consecutive-leg gaps longer than the project's 8-hour same-duty connection limit but shorter than its 10-hour minimum rest. Under the current model they require rest breaks and fail the rest test. They are not explicit duty-boundary records in the source.

For example, Pairing 6 uses `LEG_29_27 → LEG_29_14` at AIR3: arrival Jan 29 02:59, departure 12:00, a **9h01** gap. The same pattern occurs on Jan 30 and Jan 31. Consequently, changing only the 9h59 gaps by one minute would not make the entire original monthly solution compatible with the current model.

The original solution's deadhead support is another difference: the project's current pairing model does not represent a separate passenger traversal. Deadhead handling matters for reproducing the complete reference solution, although it is not how Pairing 95 covers `02_27`.

## What is known and what remains unknown

The reference solution covers `02_27` using a connection that the current model rejects. The source data itself has the same timestamps as this project. That explains how the reference covers both `01_28` and `02_27` without competing for the single `01_30` operating leg.

The README defines duties, rest layovers, and deadheads, but does not state a numerical minimum-rest rule. This archive provides data and constraint generators, rather than the solver that produced the reference pairings. The shortest observed long gap is consistent with a 9-hour minimum, but it does not prove that was the original rule; other duty or location-specific rules could have been used.

Arrival-to-departure time also does not establish available sleeping time: these files do not specify hotel transfers, briefing/debriefing offsets, or an eight-hour sleep guarantee. The report does not infer those guarantees from the reference schedule.

Before treating the one-minute gaps as data errors, decide whether the objective is to reproduce the reference assumptions or solve the instance with a mandatory 10-hour rest. For the latter, retain that rule and use explicitly justified schedule changes or model supported repositioning options; the reference solution cannot be accepted unchanged.

Detailed records are in `audit.json` and `short_gaps.csv`. The duty compatibility counts in the JSON count all timed travel as flight time and are diagnostic checks of this project's limits, not validation of the original solver's unknown deadhead rules.
