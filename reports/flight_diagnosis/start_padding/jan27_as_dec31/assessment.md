# January 27 as hypothetical December 31 start padding

**Yes: this pattern resolves the `01_28` / `02_27` coverage conflict even with a 10-hour minimum rest.** This is a local pairing-feasibility result, not a rerun of the complete weekly optimizer.

All 27 flights departing January 27 were shifted in memory to December 31, preserving arrival offsets, including overnight flights. Production CSV files, settings, and padding classification were unchanged. The source is a hypothetical prior-day pattern; the supplied data does not establish actual December 31 operations.

Unlike January 31, January 27 includes AIR12 flights:

| Source flight | Route | Shifted departure | Shifted arrival |
| --- | --- | --- | --- |
| `27_25` | BASE2 → AIR12 | Dec 31 15:34 | Dec 31 18:19 |
| `27_24` | AIR12 → BASE2 | Dec 31 19:50 | Dec 31 22:40 |

The exact search found two closed, disjoint pairings under ten-hour rest:

| Pairing | Flights | Separate-duty gap | Total pairing elapsed |
| --- | --- | --- | --- |
| A | shifted `27_25` → `01_28` | Dec 31 18:19 → Jan 1 17:00 = **22h41** | 28h18 |
| B | `01_30` → `02_27` | Jan 1 15:46 → Jan 2 13:45 = **21h59** | 27h35 |

Each leg is a separate duty. Both pairings begin and end at BASE2, satisfy the 12-hour elapsed-duty and eight-hour operating-flight caps, satisfy ten-hour minimum rest and 48-hour maximum layover, and fit within five days and five duties. Their flight identifiers do not overlap.

The shifted `27_24` return is optional; this particular witness does not use it. The shifted outbound supplies the crew for `01_28`, freeing `01_30` to supply the crew for `02_27`. No deadheading is involved.

With the current 9h58 rest setting, the search also found disjoint pairings, with `02_25 → 02_27` available as an alternative. Under ten-hour rest, searches found 12,896 closed paths for `02_27` without `01_30` and 91,018 for `01_28` without `01_30`; those counts alone are not proof of a simultaneous cover, so the explicitly disjoint witnesses above were separately validated.

Actual use in the optimizer would require unique identifiers for the copied flights and marking the December flights as optional (covered zero or one times). This diagnostic permitted them as optional path candidates but did not change the production master or run full weekly column generation/ILP. Both production input CSV hashes were verified unchanged.

Detailed results are in `audit.json`. Reproduce the check from the repository root with `python -m tests.diagnostics.diagnose_start_padding --source-day 27`.
