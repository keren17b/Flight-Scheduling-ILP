# Limits compatible with the original reference solution

All 172 original pairings can be reconstructed into 378 duties using the candidate limits below. This establishes compatibility with those limits; the source documentation does not identify the original solver's configured limits.

No production data or settings were changed. The diagnostic is reproducible with `python -m tests.diagnostics.infer_reference_limits` from the repository root. Detailed schedules and scenario results are in `inferred_limits.json`.

## Observed values and inference

| Quantity | Observed reference value | Interpretation |
| --- | --- | --- |
| Longest elapsed duty | **11h55** | A **12-hour** maximum fits and is a plausible round-number limit. |
| Most operating block time in one duty | **7h57** | An **8-hour** operating flight-time maximum fits and is plausible. |
| Shortest gap between reconstructed duties | **9h01** | A **9-hour** minimum rest fits. A uniform 10-hour rule rejects the reference under this reconstruction. |
| Most flight legs in a duty, including deadheads | **5** | A five-leg maximum fits; a larger maximum would also fit. |
| Longest complete pairing | **81h26** | A cap of **96 hours** fits, as does **120 hours**. The exact original cap cannot be identified. |
| Most duties in a pairing | **4** | Four duties suffice. A five-duty cap is also compatible and cannot be ruled out. |
| Most calendar dates touched by a pairing | **5** | Calendar-date counting is different from elapsed duration; some pairings touch five dates while lasting less than 96 hours. |
| Shortest/longest within-duty gap | **40 minutes / 5h40** | The project's 30-minute to 8-hour connection range fits but its endpoints are not established by this solution. |
| Longest gap between reconstructed duties | **25h02** | The project's 48-hour maximum layover fits; a 48-hour original limit is not established. |

The duty reconstruction splits consecutive legs at gaps exceeding eight hours, as required by the project's current maximum same-duty connection. The resulting within-duty gaps top out at 5h40; the resulting between-duty gaps start at 9h01. That separation makes this reconstruction consistent with a nine-hour rest threshold.

The longest duty occurs, for example, in Pairing 12:

```text
LEG_03_22 → LEG_03_14 → LEG_04_35
Jan 3 14:00 → Jan 4 01:55 = 11h55 elapsed
```

The largest operating flight-time sum is in Pairing 122:

```text
LEG_13_24 → LEG_13_29 → LEG_13_0
7h57 operating block time; 10h36 elapsed duty time
```

The longest pairing is Pairing 172: 81h26 elapsed across four reconstructed duties. Pairing duration includes the intervening rest gaps.

## A fully compatible candidate rule set

- Same-duty connection: 30 minutes to eight hours.
- Elapsed duty: at most 12 hours, measured from first departure to last arrival and including passenger travel.
- Operating flight time per duty: at most eight hours, excluding `TDH_` passenger block time.
- Legs per duty: at most five, including passenger legs.
- Gap between duties: at least nine hours and at most 48 hours.
- Pairing elapsed duration: at most 96 hours.
- Duties per pairing: at most four.
- Start and end at the pairing's assigned base; preserve airport continuity throughout.

All 172 pairings pass every check in this candidate set. Replacing only the final two caps with 120 hours and five duties also passes every pairing.

## Sensitivity checks

All scenarios below retain the candidate rules except the named change.

| Change | Pairings that pass | Pairings that fail |
| --- | ---: | ---: |
| Candidate limits above | 172 | 0 |
| Minimum rest 9h02 | 169 | 3 |
| Minimum rest 9h59 | 153 | 19 |
| Minimum rest 10h | 140 | 32 |
| Count passenger block time against eight-hour operating cap | 160 | 12 |
| Maximum pairing duration 72 hours | 152 | 20 |
| Maximum three duties per pairing | 145 | 27 |
| Maximum pairing duration 120 hours and five duties | 172 | 0 |

Passenger time must remain in elapsed duty time in the compatible candidate; it is excluded only from the operating block-time sum. One reconstructed duty in Pairing 116 contains 9h09 of total airborne travel, but only 3h54 of operating flying. This explains why treating every `TDH_` leg as an operating flight causes an eight-hour-cap failure. It does not prove the original solver used exactly this accounting; a larger cap on all travel time could also fit.

## Limits of this inference

The original file records flight sequences without explicit duty separators or numerical legality parameters. These are candidate rules consistent with the reference, rather than recovered original settings. Observed maxima only bound how small an upper limit can be; observed minima only bound how large a lower limit can be for these sequences under the reconstruction. Larger upper limits and smaller lower limits may produce exactly the same solution.

The inferred 12-hour elapsed-duty measurement excludes briefing/debriefing before and after the flight sequence, because their timestamps are absent. The README mentions briefing/debriefing in credited-hour calculations; it does not supply actual report/release times or a maximum duty rule. Therefore a 12-hour flight-sequence span cannot be equated automatically to a 12-hour total work shift.

Likewise, the nine-hour arrival-to-departure gap does not establish available sleep time. Transfer, report, and release times would be needed to evaluate a sleep requirement.
