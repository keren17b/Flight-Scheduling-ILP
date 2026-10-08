# December 31 start-padding assessment

The full-month CSV contains 1,013 flights departing January 1–31, 2000. It contains no actual December 31 flight records. January 31 has 25 flights, none arriving at or departing from AIR12.

## Experiment

All 25 January 31 flights were copied in memory and shifted back 31 days to serve as hypothetical December 31 start-padding candidates. Both departure and arrival timestamps were shifted, preserving overnight flights. No CSV, production setting, or padding classification was changed.

The experiment combined these candidates with the current active week and January 8–10 end padding: 367 flights and 2,367 generated duties. Exact closed-pairing searches used the production duty limits and pairing limits, without pricing state or column limits. The start-padding candidates were permitted in paths; no requirement to cover them was imposed in these feasibility searches.

## Original 10-hour-rest scenario

| Exact search with all hypothetical start-padding flights available | Result |
| --- | --- |
| Cover `02_27` without using `01_30` | Zero legal closed pairings |
| Cover `01_28` without using `01_30` | Zero legal closed pairings |
| Cover both `01_28` and `02_27` within one pairing | Zero legal closed pairings |

Therefore the original conflict remains: each return requires `01_30`, they cannot be combined in a single pairing, and the operating flight `01_30` cannot be covered twice. Adding this shifted January 31 pattern cannot cover both returns under the current operating-only model with a ten-hour rest rule, regardless of column-generation iteration count.

The earlier hypothetical example assumed a December 31 flight into AIR12. The actual January 31 pattern does not contain that flight. This does not establish what the airline really operated on December 31; that schedule is absent from the supplied data.

## Current configuration

At the time of this experiment, the production minimum rest was 9h58. Under that setting, the exact search found a valid pairing without `01_30`:

```text
02_25: BASE2 → AIR12, Jan 2 01:04–03:46
9h59 between duties
02_27: AIR12 → BASE2, Jan 2 13:45–16:34
```

This path uses no start-padding flight. Together with the previously validated `01_30 → 01_28` pairing, it resolves this particular two-return conflict. These checks do not claim that the full weekly or monthly optimization has been rerun or solved.

## Conclusion

Copying January 31 to December 31 does not solve the original ten-hour AIR12 rest bottleneck. Real previous-day flights might provide alternatives if they include suitable arrivals and satisfy the remaining rules, but the supplied dataset cannot establish that schedule. With the current 9h58 rest setting, the target already has a valid path without start padding.

Both input CSV hashes were checked before and after the experiment and remain unchanged. Detailed counts and witnesses are in `audit.json`. Reproduce the check from the repository root with `python -m tests.diagnostics.diagnose_start_padding`.
