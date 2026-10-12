# Selected dataset coverage

The retained datasets and matching `*_padding3_config.txt` snippets in
`data/generated/` cover three seven-day windows, each with three days of padding
before and after:

| Instance | Required dates (January 2000) | Required flights with legal pairing |
| --- | --- | --- |
| 1 | 14-20 | 230/230 |
| 2 | 11-17 | 353/353 |
| 2 | 6-12 | 353/353 |

[selected_weeks_coverage.json](selected_weeks_coverage.json) contains one legal
closed-pairing witness per required flight, with paths updated to the retained
CSV and bases files. The flight IDs, airport continuity, base closure, duty
limits, connection/rest intervals and pairing limits were independently checked.
The 936 witnesses can overlap; they do not establish simultaneous exactly-once
coverage. No LP, ILP, pricing or full program run was performed.

The reusable reachability and witness-validation functions are in
[diagnose_instance_coverage.py](diagnose_instance_coverage.py). Its legacy
week-number CLI expects the old week-number datasets, which are no longer
retained. The current report describes the explicitly selected date ranges.

The validation suite compares reachability with exhaustive enumeration on 80
small random graphs and checks legality boundaries:

```powershell
python -B -m unittest diagnostics.test_instance_coverage -v
```
