# Crew-Pairing UI

The local Streamlit UI runs the shared optimization pipeline and displays the
best validated solution as an interactive pairing timeline. See the
[project README](../README.md) for installation, inputs, legality rules,
command-line usage, and the optimization model.

## Launch

From the repository root (`Flight-Scheduling-ILP`), in your Python environment
(Python 3.12 is the verified version):

```bash
python -m pip install -r UI/requirements.txt
python -m streamlit run UI/app.py
```

The UI requirements include the solver dependencies. Open the local URL printed
by Streamlit, normally `http://localhost:8501`. A valid MOSEK license is required
to run optimization.

## Run and Inspect a Solution

1. Choose **Initial seed** and **Number of runs** (defaults: 42 and 1).
2. Click **Run optimization**. The UI clears the previous result, disables the
   controls, and shows the current stage and elapsed time while the batch runs.
3. Review the best result's total sitting + rest hours and selected pairing count.
4. Use **Base** to filter by departure base, and click a duty bar to select its pairing.
5. Expand a duty in **Pairing details** to see its chronological flight records.
6. Use **Download solution JSON** to download the complete saved result.

The timeline sorts pairings by start time and provides one row per pairing in
a vertically scrolling panel with a fixed time axis. Blue bars represent duties,
muted tan bars represent rest intervals, and an amber outline highlights the
selected pairing. The full solution period includes selected padding flights.
Details appear beside the chart on desktop and below it on narrow screens.

Base filtering preserves the selected pairing; a note appears if it is outside
the filter. Filtering, selection, duty expansion, and downloads reuse the saved
result without calling the solver again. Downloads include all selected pairings
and run metadata, regardless of the current filter.

If no attempt produces an accepted integer solution, the UI shows that outcome
without a timeline or download. It does not restore an older batch's result.

## Inputs, Seeds, and Output

The UI reads the dataset, bases, legality limits, and padding dates from
`crew_pairing/config.py`, and the search budgets from `column_generation/config.py`.
Only the initial seed and run count are editable in the UI.

The shared `main.run_batch` builds graphs once, runs each attempt, and selects
the lowest-cost validated integer solution, keeping the first result in a tie.
The UI and CLI use one random generator initialized once with the chosen seed.
Its state advances across all attempts; it is not reset between attempts.
With the same seed, run count, inputs, and settings, both modes use the same
random search sequence. Different attempts can still return the same solution.

Both modes save `best_<batch_id>.json` when a validated solution is accepted and
`comparison_<batch_id>.json` for the batch under `results/runs/`. The best result
contains nested pairings, duties, and flights. The comparison records each
attempt's outcome, validation report, seed, timings, and available solver statuses. The UI downloads
the exact saved best-result bytes.

## Preview a Saved Result

Choose an existing best-result JSON printed by a completed batch:

```bash
python -m streamlit run UI/app.py -- --result results/runs/best_<batch_id>.json
```

Replace `best_<batch_id>.json` with an actual saved filename. Previewing requires
no solve or MOSEK license and is labeled as a saved-result preview. A standalone
pairing export is also accepted; a batch comparison is not a solution preview.
Result files are ignored by Git, so a fresh clone has no saved result to preview.

## Solution Validation

Every UI-started attempt that produces an ILP solution uses the same independent
validator as the CLI. It checks selected flight coverage, configured scheduling
legality, and recalculated cost before accepting a solution for Best Run.

Validation keeps the existing UI fields and layout. `Solution validation: VALID`
or `Solution validation: INVALID` and any diagnostics print in the terminal.
The comparison JSON retains every attempt's `ilp.validation` report, including
failed validation. Invalid attempts cannot become the displayed Best Run.
If no attempt is accepted, the UI shows its existing
`No run produced a feasible integer solution.` warning.

The saved best-result JSON and its download include the validation report.
Previewing an existing JSON displays stored records without rerunning validation.

## Limits and Restarting

This is a local, single-user demonstration. Results survive Streamlit interaction
reruns within the same session. A browser reload, new session, or server restart
discards session state; saved JSON remains on disk. The background worker is not
a durable job queue and has no cancellation control. Separate browser sessions
can start separate batches. Timestamp labels retain the input dataset's time basis.

Stop Streamlit with **Ctrl+C** and relaunch after editing Python modules or
configuration. Stopping the server interrupts an active optimization.
The bounded heuristic search and final ILP over generated columns do not
establish global optimality over all feasible pairings.
