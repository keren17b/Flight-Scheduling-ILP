# Initial-pool stopping limits and larger-budget experiment

The baseline finishes its outer loop over all 826 eligible starting duties.
It does not meet the all-flight coverage target (three flights have zero
coverage), exhaust the 500,000-state global budget (127,664 visited), or reach
the 1,000-pairing global cap (413 saved). However, 617 starts reach the local
200-state search cap and two reach the local 20-pairing cap. Remaining branches
for those starts are abandoned; restarting with unchanged settings repeats the
same traversal.

The coverage target also filters which closed paths are saved: a unique pairing
is kept only if at least one required flight in it has fewer than three saved
pairings. Once its flights reach the target, additional alternatives containing
only those flights are discarded. Three is a target, not a maximum count for
each flight. Five duties and five elapsed days are separate legality limits.

The following settings were tested through function arguments, without changing
production configuration:

```python
MIN_INITIAL_COVERAGE = 10
MAX_INITIAL_PAIRINGS = 3_000
MAX_INITIAL_DFS_STATES = 1_000_000
MAX_INITIAL_DFS_STATES_PER_START = 1_000
MAX_INITIAL_PAIRINGS_PER_START = 50
```

With 826 starting duties, at most 826,000 states are visited under the local
1,000-state cap; a one-million-state global budget therefore avoids cutting
off later starts due to state consumption by earlier starts on this dataset.
The global pairing cap and local pairing cap still apply.

| Result | Current settings | Tested larger budgets |
|---|---:|---:|
| Saved pairings | 413 | 1,298 |
| Required flights present | 231 / 234 | 232 / 234 |
| Flights with positive first-LP artificials | 160 | 111 |
| Sum of first-LP artificials | 114.7692 | 88.5 |
| Initial search time, without profiling | 3.97 s | 19.14 s |

Timings exclude loading, graph construction, and the LP solve. Both were
measured in the same run and environment; the larger configuration took about
4.8 times as long. The earlier audit's profiled timings are not comparable to
normal search performance. The user's own baseline timing may differ.

The larger configuration is a demonstrated improvement, but leaves
`LEG_02_22` and `LEG_03_22` absent and substantial artificials. It is a useful
next budget experiment, not a guarantee of complete coverage. Further work
should give uncovered flights targeted search effort and add useful alternative
pairings for flights still dependent on artificials.

Exact results and settings are recorded in `budget_comparison.json`.
