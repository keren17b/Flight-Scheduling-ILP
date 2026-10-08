# Audit of recurring 9h59m rest gaps

All flight input files were scanned without modifying their contents. An exact 599-minute gap was counted only when the arriving and departing flights meet at the same airport.

Every match is the same BASE2 -> AIR12 -> BASE2 rotation: outbound 01:04-03:46, return 13:45-16:34. The full-month source has 13 matches, all January 2-14. Week one has 6 required matches (January 2-7); the active padded week has 9 (January 2-10). Day one has none. Flight suffixes vary, so matching by route, times, and date is more reliable than matching a numeric suffix.

Proposed direction: advance the arriving outbound flight by one minute, changing BOTH departure and arrival from 01:04-03:46 to 01:03-03:45. Keep the return at 13:45-16:34. Flight duration remains 2h42m and the gap becomes exactly 10 hours. Advancing the return departure instead would shorten the rest to 9h58m.

| Date (2000) | Outbound to advance one minute | Return left unchanged |
|---|---|---|
| 2000-01-02 | LEG_02_25 | LEG_02_27 |
| 2000-01-03 | LEG_03_25 | LEG_03_27 |
| 2000-01-04 | LEG_04_25 | LEG_04_27 |
| 2000-01-05 | LEG_05_22 | LEG_05_24 |
| 2000-01-06 | LEG_06_22 | LEG_06_24 |
| 2000-01-07 | LEG_07_25 | LEG_07_27 |
| 2000-01-08 | LEG_08_25 | LEG_08_27 |
| 2000-01-09 | LEG_09_25 | LEG_09_27 |
| 2000-01-10 | LEG_10_25 | LEG_10_27 |
| 2000-01-11 | LEG_11_25 | LEG_11_27 |
| 2000-01-12 | LEG_12_22 | LEG_12_24 |
| 2000-01-13 | LEG_13_22 | LEG_13_24 |
| 2000-01-14 | LEG_14_26 | LEG_14_28 |

The changes were simulated in memory only. Across the required week, padded week, and full-month source, the simulation removed zero existing flight connections, zero legal duties, and zero legal duty-rest connections. No candidate first departure had a same-base arrival exactly five days later that could cross the pairing-duration boundary when shifted earlier.

The previously generated 72-pairing binary week solution was rebuilt with the nine hypothetical earlier outbounds in the active padded week. Every duty and connection was checked against the original rules. It still covers all 234 required flights exactly once, padding flights at most once, and its minimum rest is now exactly 600 minutes. This is validation of an existing complete solution; the optimizer was not rerun. Full-month schedule feasibility was not solved in this audit.

All four source-file SHA-256 hashes were verified unchanged after the audit. The machine-readable audit is in audit.json; proposed_changes.csv lists the proposal separately for each dataset, so repeated physical flights appear once per dataset containing them.
