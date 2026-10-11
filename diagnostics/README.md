# Instance feasibility diagnosis

The retained week 3 results were checked October 11, 2026, with January 12-24
inputs, January 15-21 required flights, and production legality limits. No LP,
ILP, or column-generation run was performed.

There are now three local instances. Local instance 3 is the original archive's
instance 5. The extracted original instances 3 and 4, their week 2 variants,
and their infeasibility reports were deleted. The saved report retains only the
three remaining datasets and records their original archive instance numbers.

| Instance | Required flights | In a legal closed pairing | Diagnosis |
| --- | --- | --- | --- |
| 1 | 227 | 227 | Confirmed feasible from an independently validated existing result |
| 2 | 351 | 351 | Passes individual coverage; simultaneous exact coverage not established |
| 3 (original archive instance 5) | 1,309 | 1,309 | Passes individual coverage; simultaneous exact coverage not established |

## How the coverage check works

[diagnose_instance_coverage.py](diagnose_instance_coverage.py) builds the flight
graph and generates all duties using the production code. For each base and
exact duty count, it retains the latest possible start of a prefix ending at
a duty and the earliest possible finish of a suffix starting at that duty.
Joining the prefix and suffix tests whether a legal closed pairing contains
the duty within the five-day and five-duty limits.

The airport/rest connections are evaluated with sliding-window heaps rather
than constructing the quadratic duty graph. The method uses no Top-K cutoff,
random search, pricing budget, or optimization model. Later prefix starts and
earlier suffix finishes dominate other paths for the elapsed-time limit;
chronological connections prevent repeated flights when paths are joined.

The report includes a legal pairing witness for every coverable required flight.
Witnesses were independently checked for base closure, airport continuity,
flight uniqueness, connection/rest intervals, duty limits, and pairing limits.
[test_instance_coverage.py](test_instance_coverage.py) compares the method with
exhaustive enumeration on 80 small random graphs and explicit rest, elapsed-time,
base, and duty-count boundary cases.

Individual witnesses can overlap, so they do not themselves form an exact-cover
solution. This is why local instances 2 and 3 are not labeled proven feasible.

## Existing instance 1 solution

The existing `results/selected_pairings.json`, timestamped
`2026-10-11 14:06:59`, contains 66 pairings with reported cost 915.55. A separate
read-only check matched every exported flight ID, airport, and timestamp against
instance 1, reconstructed its duties, and checked all pairing legality rules.
All 227 required flights occur exactly once and padding flights occur at most
once. This is a feasibility certificate, without a claim of global optimality.
The result file will change on the next successful production run.

## Run the diagnostic again

From the repository root:

```powershell
python -B diagnostics/diagnose_instance_coverage.py
```

For selected instances:

```powershell
python -B diagnostics/diagnose_instance_coverage.py --instances 2 3
```

The output is [instance_coverage.json](instance_coverage.json). Use `--output`
to save a separate report. Rerunning regenerates the individual-coverage report;
the existing-result certificate above was an additional check of the saved
October 11 report. Only week 3 files are currently retained; `--week 2` requires
preparing new inputs first.

Run the small validation cases with:

```powershell
python -B -m unittest diagnostics.test_instance_coverage -v
```
