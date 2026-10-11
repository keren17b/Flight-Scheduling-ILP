# Local crew-pairing demonstration

From the repository root (`Flight-Scheduling-ILP`), using Python 3.12:

```powershell
python -m pip install -r UI/requirements.txt
python -m streamlit run UI/app.py
```

Open the local URL printed by Streamlit (normally http://localhost:8501).
After updating Python modules while the server is running, stop Streamlit with
Ctrl+C and run the launch command again so cached solver modules are refreshed.
Restarting the server interrupts any active optimization.
A valid MOSEK license is required to optimize. The UI uses the existing configured
dataset, legality limits, and search budgets; only initial seed and run count are
editable. Run `i` uses `initial_seed + i`, with `i` starting at zero.

The shared `main.run_batch` prepares graphs once, runs each attempt, chooses the
lowest-cost feasible integer solution, and saves the best JSON and batch comparison
under `results/runs/`. CLI `main.main` retains its existing shared RNG behavior.
Batch comparisons now include `seed_strategy` (`consecutive` or `shared_stream`)
and schema version 3. Individual attempt records contain their actual seed.

While running, the UI shows only the current stage and elapsed time; controls
are disabled and the previous result is cleared. The worker does not call Streamlit.
Thread-local stage notifications cover loading data, building graphs, initial pool,
column generation, and final ILP. The UI does not subscribe to solver messages or
show iteration, pairing-count, or LP-objective updates. The display refreshes every
half second. Console progress output remains available when running normally.
No feasible result produces an explicit outcome without a timeline or download.

The completed result and original saved bytes stay in session state. Filtering,
chart selection, expanding duties, and downloading only change the
presentation. Downloads contain the exact saved best-result bytes, including
run metadata and nested duties/flights. The total objective is sitting + rest hours.

The timeline sorts pairings by start time, uses one 36-pixel row per pairing, and
scrolls vertically in a 620-pixel panel. The aligned time axis remains above the
scrolling rows. Blue bars are duties; thin muted tan bars are rest intervals;
amber outlines mark the selected pairing. Click a duty to select its parent using
the stable pairing ID in Plotly bar `customdata`. The base filter uses departure
base and preserves the selected pairing (a note appears if it is filtered out).
The timeline always shows the full solution period, including all selected padding flights.
Details sit beside the timeline on desktop and stack below it at widths up to 950px.

## Preview existing JSON without a solve

Explicitly choose a saved combined run result or standalone pairing export:

```powershell
python -m streamlit run UI/app.py -- --result results/runs/run_eb8a2bd94f0946f28008f2fd88486b6d.json
```

This filename is an existing local result, ignored by Git. Substitute another
saved result path when unavailable. The preview is clearly labeled; results are
never automatically recovered from earlier batches after an unsuccessful run.
The local 66-pairing solution was sufficient to check scrolling; no synthetic
or inflated optimization result is included.

## Validation

```powershell
python -m unittest UI.test_ui column_generation.test_run_summary -v
```

Verified with Streamlit 1.65.0 and Plotly 6.9.0:

- 15 focused UI/integration tests: independent consecutive seeds, shared graph
  reuse, lowest-cost/first-tie selection, failed/no-feasible outcomes, duplicate
  start rejection, byte-exact saved downloads, real 66-row trace/range checks,
  Streamlit reruns that cannot invoke the runner or graph builder, and all five
  stage notifications from a real two-flight optimization.
- The wait screen was checked to show only stage and elapsed time, including
  when an older running job still has message data. The worker subscribes only
  to stage updates; console messages remain independent of the UI.
- Regression checks cover importing the UI with an older cached progress module
  and monitoring callbacks queued after job completion or replacement. Both
  four-field and older five-field job snapshots are handled safely.
- All 41 existing run-summary tests passed, including small real MOSEK solves.
  No full dataset solver batch was launched for UI validation.
- Browser checks on the existing 66-pairing result: actual duty-bar clicks
  before and after filtering selected the correct parent ID; BASE3 reduced the
  chart to 9 rows; duty expansion exposed chronological flight records; selection and expansion survived
  these interactions; row scrolling retained readable date labels above it.
- Browser download was compared byte-for-byte with the existing JSON.
  Desktop (1440px) and narrow (700px) layouts were checked.

## Limits

This is a local, single-user demonstration. State survives Streamlit interaction
reruns, but a browser reload/new session or server restart discards session state;
a daemon worker is not a durable job queue and there is no cancellation control.
Server shutdown interrupts a running optimization. Separate browser sessions
can initiate separate batches. Timestamp labels retain the dataset's existing
time basis. The existing bounded heuristic and final generated-pool ILP do not
establish global optimality. Optimization still needs the configured inputs and
MOSEK license; saved-result previews do not.

Chart interactions use Streamlit's [Plotly selection API](https://docs.streamlit.io/develop/api-reference/charts/st.plotly_chart)
and Plotly's [horizontal bar trace event data](https://plotly.com/python/reference/bar/).
