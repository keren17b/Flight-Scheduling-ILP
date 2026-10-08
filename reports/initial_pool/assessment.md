# Initial pool audit — 2026-09-30

The configured runner's initial pool was reproduced exactly: **413 real
pairings**. Three runs with identical inputs, graph order, and settings produced
identical ordered pairing signatures. There is no randomness in the search.
Reordering inputs or duty adjacency lists can change its results.

This audit stops at the **first restricted master LP**. It does not run pricing
or the final integer solver. All LP values below come from the production
`solve_master_lp` using MOSEK and the current cost function.

## Coverage and artificials

| Measure | Baseline result |
|---|---:|
| Total input flights | 342 |
| Required flights | 234 |
| Optional padding flights | 108 |
| Required flights present in at least one initial pairing | 231 (98.72%) |
| Required flights absent from the initial pool | 3 |
| Padding flights present in the initial pool | 21 |
| Required flights present in at least three initial pairings | 231 |
| Artificial variables created by the first LP | 234 |
| Artificial variables positive above 1e-6 | 160 |
| Full artificials, approximately 1 | 71 |
| Fractional positive artificials | 89 |
| Sum of artificial values | 114.769231 |
| Required flights fully covered by real columns in this LP solution | 74 |
| Real coverage, measured in flight-equivalents | 119.230769 |

An artificial is a coverage variable, not a real flight or crew pairing. Each
required flight has one such variable in the LP; padding flights have none.
For a required flight, real pairing coverage plus its artificial equals one.
Thus a fractional artificial of 0.4 means that real columns cover 0.6 of that
flight in the LP relaxation. The sum of artificials measures total missing
coverage; the count of positive artificials measures how many flights are
affected. Counts and fractions can depend on the particular optimal LP solution.

The three flights absent from the pool are `LEG_02_22`, `LEG_03_22`, and
`LEG_04_22`, each AIR6 → BASE2, departing at 14:00 on January 2, 3, and 4,
2000, respectively. All three are individually legally coverable. An exact
reachability audit found that **all 234 required flights** can individually
appear in a closed pairing under the currently implemented legality rules.
This does not prove that a simultaneous exact-cover solution exists.

## Search comparisons

All experiments keep the global 500,000-state and 1,000-pairing caps. The
reversed experiment reverses both starting-duty and successor-duty order.

| Experiment | Pairings | Required flights present | Positive artificials | Sum of artificials |
|---|---:|---:|---:|---:|
| Current defaults: 200 states per start | 413 | 231 | 160 | 114.77 |
| 1,000 states per start | 440 | 232 | 129 | 129.00 |
| 5,000 states per start | 347 | 188 | 174 | 161.33 |
| Reversed traversal, default budgets | 422 | 228 | 107 | 84.40 |

The baseline visited 127,664 states over 826 starting duties. Of these starts,
617 reached their 200-state local budget and two reached their 20-pairing local
budget. It did not reach either global cap. Higher local budgets exhausted the
global state budget after only 523 and 109 starts, respectively, reducing the
opportunity to search later starts.

`MIN_INITIAL_COVERAGE = 3` is a saving target, not a strict maximum per flight.
A pairing is saved if **any** required flight in it is below the target. Other
flights in that same pairing are incremented too. Baseline counts range from
3 to 97 for flights present in the pool, so reaching three does not mean those
flights have independent, mutually compatible alternatives. The function's
docstring describes this as an upper bound, but the implementation is a target.

## Assessment

The pool is a workable starting point for column generation with artificials,
but its near-complete flight union overstates its ability to cover flights
simultaneously. Flights share pairing columns; selecting a column to cover one
flight may conflict with exact coverage of another flight or the at-most-once
padding constraints. In the baseline LP, even 157 of the 231 flights that
appear in real pairings still have positive artificial coverage.

Increasing the number of states alone did not improve the artificial sum.
Changing order did improve it, which demonstrates substantial traversal bias.
The next improvement should target useful alternatives: prioritize uncovered
flights, favor short closed paths before long extensions, and spread effort
across starts. Evaluate changes using both required-flight presence and the
first-LP artificial sum, rather than the number of saved pairings alone.
Eliminating initial artificials is desirable, but is not a prerequisite for
starting column generation; pricing must subsequently remove them before the
final model can cover required flights with real columns.

## Verification and reproduction

- All four existing initial-pool tests and five master-LP tests passed.
- Three baseline runs had identical ordered signature hashes.
- Coverage counters were independently recomputed from saved pairing flights.
- All saved pairings in the four experiments passed checks for base closure,
  chronology/rest connections, duration/depth limits, and no repeated flights.
- The exact coverage calculation agreed with both exhaustive pairing
  enumeration and the existing reachability diagnostic on 100 small
  chronological synthetic graphs.

Run from the repository root with the project's Python/MOSEK environment:

```powershell
python -m tests.diagnostics.initial_pool_report
```

`summary.json` contains all scenario results, hashes, daily counts, and search
statistics. `flights.csv` contains a row for every input flight, its initial
pairing count, exact legal reachability, and first-LP artificial value.
The production algorithm and settings were not modified.
