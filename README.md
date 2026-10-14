# Airline Crew Pairing Optimization

A final engineering project that uses Integer Linear Programming (ILP)
and heuristic column generation to solve the airline crew pairing problem.

Given a fixed flight schedule, the system generates feasible crew pairings
and selects a low-cost combination that covers every required flight
exactly once. The final ILP optimizes over the generated pairing pool;
the heuristic search does not guarantee global optimality over all possible pairings.

The project follows the classical set partitioning approach, with
MOSEK Fusion for Python as the optimization solver.

The same optimization pipeline is available through a command-line runner
and a local Streamlit UI with an interactive pairing timeline and JSON download.
Both save the lowest-cost validated solution and a comparison of the batch attempts.

## Key Concepts

- **Flight:** A scheduled flight between two airports.
- **Duty:** A sequence of flights performed within one work period.
- **Pairing:** A sequence of duties separated by rest periods, starting
  and ending at the same crew base.

The system selects pairings. Assignment of individual crew members to
those pairings is outside the current scope.

## Solution Pipeline

1. Load flight and crew-base data from CSV files.
2. Build a graph of feasible connections between flights.
3. Generate feasible duties using depth-first search (DFS).
4. Build a graph of feasible connections between duties.
5. Generate a bounded initial pool of feasible pairings.
6. Solve the restricted master LP and extract flight dual values.
7. Search for new pairings with negative reduced cost using a
   dual-guided, randomized DFS.
8. Add the new pairings and repeat until the search finds no new
   improving pairings or the iteration limit is reached.
9. Solve a binary ILP over the generated pairing pool.
10. Extract the selected pairings and independently validate their coverage,
    legality, and total cost before accepting the solution.

The batch runner builds the graphs once, reuses them across attempts,
and saves the lowest-cost validated integer solution. The CLI performs five
attempts by default; the UI lets you choose the number of attempts.

Artificial variables allow the initial LP to be solved even when the
initial pool cannot cover all required flights. They carry a large
penalty in the objective.

The runner proceeds to the final ILP only when all artificial variables
are zero within the configured tolerance. This condition does not
guarantee that the generated pool has a feasible integer solution.

## Crew Legality Rules

The current defaults are defined in `crew_pairing/config.py`.

| Rule | Default |
| --- | --- |
| Minimum connection time within a duty | 30 minutes |
| Maximum connection time within a duty | 8 hours |
| Maximum elapsed duty time | 12 hours |
| Maximum total flight time per duty | 8 hours |
| Maximum flights per duty | 5 |
| Minimum rest between duties | 10 hours |
| Maximum layover between duties | 48 hours |
| Maximum elapsed pairing time | 5 days |
| Maximum duties per pairing | 5 |
| Pairing start and end | Same crew base |

Elapsed duty time includes flights and waiting time between flights.
Elapsed pairing time also includes rest between duties.

These limits are simplified project assumptions. They do not implement
a complete airline agreement or regulatory rule set.

## Optimization and Cost

Each generated pairing has a decision variable.

- Required flights must be covered exactly once.
- Padding flights may be covered at most once and may remain unused.
- Pairing variables are continuous in the restricted master LP and
  binary in the final ILP.

The current pairing cost is:

```text
pairing cost = total rest between duties
             + total waiting time within duties
```

Both components are measured in hours. The resulting objective is a
time-based cost, rather than a monetary crew cost.

The cost function is defined in `crew_pairing/pairing_cost.py`.

The final ILP returns MOSEK's primal objective value. MOSEK may report an
optimal solution or a feasible integer solution without proven optimality;
either is passed to independent validation before acceptance.

## Input Data

The project uses flight data from the GERAD dataset.

The current runner reads:

- [data/flights/instance1_week_3_with_start_end_padding.csv](data/flights/instance1_week_3_with_start_end_padding.csv)
- [data/bases/instance1_listOfBases.csv](data/bases/instance1_listOfBases.csv)

With the current assignments in `crew_pairing/config.py`, the required planning
period is January 15-21, 2000. The active CSV contains **428 flights** departing
January 12-24: **227 required flights** and **201 optional padding flights**,
with three days of padding on each side.

Three archive datasets are also retained in `data/flights/`. Their matching
`*_padding3_config.txt` snippets select the archived CSV and its padding dates:

| Archive dataset | Required departure dates (January 2000) | Required / total flights | Config snippet |
| --- | --- | --- | --- |
| [Instance 1 archive](data/flights/archive_instance1_2000-01-14_padding3_flights.csv) | 14-20 | 230 / 430 | [Config](data/flights/archive_instance1_2000-01-14_padding3_config.txt) |
| [Instance 2 archive](data/flights/archive_instance2_2000-01-06_padding3_flights.csv) | 6-12 | 353 / 650 | [Config](data/flights/archive_instance2_2000-01-06_padding3_config.txt) |
| [Instance 2 archive](data/flights/archive_instance2_2000-01-11_padding3_flights.csv) | 11-17 | 353 / 652 | [Config](data/flights/archive_instance2_2000-01-11_padding3_config.txt) |

Each archived schedule also has three days of padding on each side. The
230-required / 430-total figures describe the instance 1 archive above; the
active schedule is configured directly in `crew_pairing/config.py`.

Flight CSV files must contain:

| Column | Description |
| --- | --- |
| `leg_nb` | Unique flight identifier |
| `airport_dep` | Departure airport |
| `date_dep` | Departure date, in `YYYY-MM-DD` format |
| `hour_dep` | Departure time, in `HH:MM` format |
| `airport_arr` | Arrival airport |
| `date_arr` | Arrival date, in `YYYY-MM-DD` format |
| `hour_arr` | Arrival time, in `HH:MM` format |

Crew-base CSV files must contain:

| Column | Description |
| --- | --- |
| `airport` | Airport identifier |
| `status` | `1` for a crew base, `0` otherwise |

### Padding Flights

Flights before and after the main planning period can be included to allow
pairings to start at and return to their original base across the period boundaries.

For the active dataset, departures on January 12-14 and January 22-24, 2000,
are treated as padding. These ranges are inclusive.
All other loaded flights are treated as required.

To switch to a retained archive dataset, replace `FLIGHTS_FILE_PATH`,
`HUBS_FILE_PATH`, and `PADDING_DATE_RANGES` in `crew_pairing/config.py` with the
assignments from its matching config snippet. For another dataset, set those
assignments directly and align the padding dates with its schedule. Restart the
UI server after changing configuration. Required/padding classification follows
the configured departure-date intervals, rather than the CSV filename.

## Installation

### Requirements

- Python 3.12 or later, using a version supported by the pinned dependencies.
  Python 3.12 is the verified version; the pinned NumPy requires at least 3.12.
- NumPy and the MOSEK Python package.
- Streamlit and Plotly for the UI.
- A valid MOSEK license.

### Clone the Main Branch

```bash
git clone --branch main https://github.com/keren17b/Flight-Scheduling-ILP.git
cd Flight-Scheduling-ILP
```

### Create a Virtual Environment

```bash
python -m venv .venv
```

Activate it on Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

Or on Linux/macOS:

```bash
source .venv/bin/activate
```

### Install Dependencies

For command-line use:

```bash
python -m pip install -r requirements.txt
```

For the UI:

```bash
python -m pip install -r UI/requirements.txt
```

The UI requirements also install the solver dependencies. Use the requirements
files to install the project's pinned versions.

### Configure the MOSEK License

Place your `mosek.lic` file in the standard license location:

- Windows: `%USERPROFILE%\mosek\mosek.lic`
- Linux/macOS: `$HOME/mosek/mosek.lic`

See the [MOSEK installation guide](https://docs.mosek.com/latest/install/installation.html)
for licensing and installation details.

## Running from the Command Line

Run commands from the repository root:

```bash
python main.py
```

This builds the graphs once and runs five attempts with an initial seed of 42.
The runner prints progress during graph construction, duty generation,
pairing searches, and optimization, then saves the best validated solution.

To choose the initial seed and number of attempts, call the Python entry point:

```bash
python -c "import main; main.main(seed=42, num_runs=1)"
```

Change `seed` and `num_runs` as needed. The CLI uses one seeded random generator
whose state advances across all attempts.

When the final ILP produces a solution and validation succeeds, the console
output includes:

- Number of generated pairing columns.
- Restricted master LP objective.
- `Solution validation: VALID`.
- Number of pairing decision variables.
- Total cost reported by MOSEK and checked against the selected pairings,
  in sitting + rest hours.
- Number of selected pairings.

If validation fails, the runner prints `Solution validation: INVALID` and all
validation errors. It returns before printing the accepted solution's variable
count, cost, and selected count, or preparing its pairing records. The failed
attempt is excluded from Best Run and retained in the comparison JSON.

If artificial variables remain, the runner prints their flight IDs
with artificial values and duals, then skips the integer solve for that attempt.
The batch continues with the remaining attempts and records each outcome in the
comparison JSON.

If MOSEK reports that the generated pool is integer-infeasible, the runner
prints that conclusion and records it without calling the validator. Other
attempt exceptions retain their traceback, and the batch continues. Shared
graph-preparation errors stop the batch.

If no attempt produces an accepted, validated integer solution, the batch saves
its comparison without a best-solution file. See [Saved Results](#saved-results)
for the output format.

To disable progress messages in Windows PowerShell:

```powershell
$env:ILP_PROGRESS = '0'
python main.py
```

Or on Linux/macOS:

```bash
ILP_PROGRESS=0 python main.py
```

This suppresses progress messages; result summaries and errors remain visible.

## Running the UI

With the UI dependencies installed, run from the repository root:

```bash
python -m streamlit run UI/app.py
```

Open the local URL printed by Streamlit, normally `http://localhost:8501`.

1. Set **Initial seed** and **Number of runs** (defaults: 42 and 1).
2. Click **Run optimization**. While it runs, the UI shows the current stage
   and elapsed time, and disables the run controls.
3. Review the best solution's total sitting + rest cost and selected pairing count.
4. Filter by departure base and click a blue duty bar to select its pairing.
   Tan bars show rest intervals; an amber outline marks the selected pairing.
5. Expand duties in **Pairing details** to inspect their flights, airports, and times.
6. Click **Download solution JSON** to download the complete saved best result.

The timeline has one row per pairing and includes selected padding flights.
Filtering, selecting pairings, expanding details, and downloading reuse the
completed result without rerunning optimization. If no attempt produces an
accepted solution, the UI shows `No run produced a feasible integer solution.`
without displaying a timeline or download. Execution errors may also be shown.

Validation uses the shared pipeline and adds no new UI fields or layout changes.
Detailed validation messages appear in the terminal and comparison JSON. The
solution JSON download includes the saved validation report.

The UI uses the configured inputs and legality/search limits. Only the initial
seed and run count are editable in the UI. Like the CLI, the UI initializes one
random generator with the chosen seed and advances its state across all attempts,
without resetting it. The same seed, run count, inputs, and settings produce the
same random search sequence in both modes. Different attempts can still return
the same solution.

### Preview a Saved Solution

Use an existing best-result JSON path printed by a completed batch:

```bash
python -m streamlit run UI/app.py -- --result results/runs/best_<batch_id>.json
```

Replace `best_<batch_id>.json` with an actual filename. Previewing a saved result
does not start a solve or require a MOSEK license. A standalone pairing export
is also supported; the batch comparison JSON is not a solution preview.
Previewing reads stored records without rerunning scheduling validation.

Stop Streamlit with **Ctrl+C**. Restart it after changing Python modules or
configuration so the next run uses the updated settings. Server shutdown
interrupts an active optimization. See [UI/README.md](UI/README.md) for UI details.

## Saved Results

Both modes write to `results/runs/` (created automatically and ignored by Git):

| File | Contents |
| --- | --- |
| `best_<batch_id>.json` | Lowest-cost validated run, solver statuses, validation report, timings, seed, cost, and selected pairings with nested duties and flights |
| `comparison_<batch_id>.json` | Batch timing, seed strategy, compact summaries of all attempts, validation reports, outcomes, and best-result path when available |

The first lowest-cost validated attempt wins a tie. The runner saves the winning
run in full and records the other attempts in the comparison. The UI download
contains the exact saved best-result bytes, including all pairings regardless
of the current base filter.

Outcome codes distinguish `integer_solution_found`, `lp_artificials_remaining`,
`generated_pool_integer_infeasible`, `solver_no_conclusion`,
`solution_validation_failed`, and `execution_error`.
The comparison also records errors and solver statuses when available.
Remaining artificials or an infeasible generated pool do not prove that the
full crew-pairing problem is infeasible.

Each run record includes `ilp.validation`, containing `is_valid` and the list
of validation `errors`, or `null` if validation did not run. Validation failures
have `integer_solution: null` and remain in the comparison. That comparison
omits the full pairing records, which are saved only for the accepted winner.
No separate validator output file is created.

`integer_solution.cost` is sitting + rest hours. `lp.objective_value` also
includes artificial-variable penalties when artificial coverage remains.

## Configuration

| File | Settings |
| --- | --- |
| `crew_pairing/config.py` | Input paths, duty and pairing limits, connection times, rest limits, padding dates |
| `column_generation/config.py` | Initial pool limits, pricing budgets, pricing seed default, iteration limit, artificial penalty, tolerances, output directory |
| `main.py` | CLI batch defaults (`seed=42`, `num_runs=5`) and shared batch orchestration |

The seed controls the randomized search order. Each attempt reuses its random
generator across pricing iterations and retries.

## Project Structure

| Path | Responsibility |
| --- | --- |
| `crew_pairing/` | Flight loading, connection graphs, duties, pairings, legality settings, costs, and independent solution validation |
| `column_generation/` | Initial pairing pool, master LP, pricing search, column generation loop, and final ILP |
| `UI/` | Streamlit app, background optimization job, and timeline |
| `data/bases/` | Crew-base files for the retained instances |
| `data/flights/` | Active week 3 flight dataset and three archive datasets with matching archive config snippets |
| `diagnostics/` | Coverage analysis and witness report |
| `experiments/` | Pricing configuration benchmarks |
| `main.py` | CLI entry point, shared graph preparation, batch selection, and persistence |
| `airline_crew_pairing_project_flow.md` | Detailed design and pipeline documentation |
| `run_progress.py` | Progress reporting |
| `results/runs/` | Generated solution and comparison JSON files (ignored by Git) |

The current optimization path builds a flight-to-pairing coverage
index directly, without constructing a dense coverage matrix.

## Current Limitations

- Initial pool generation and pricing use bounded searches. Pricing explores
  only a ranked subset of successors, so finding no new improving pairing
  does not prove that none exists.
- The final ILP optimizes over the generated pairing pool. An optimal status
  applies to that pool; a feasible status does not prove even pool optimality.
  Global optimality over all feasible pairings is not guaranteed.
- Remaining artificials, an integer-infeasible generated pool, or failed
  validation do not establish infeasibility of the full crew-pairing problem.
- Duty generation enumerates feasible flight sequences, and graph construction
  compares pairs of nodes. Both can become expensive on larger datasets.
- The cost model and legality rules are simplified. Validation checks these
  configured rules and cost consistency, rather than global optimality or a
  complete airline agreement or regulatory rule set.
- Individual crew assignment and deadheading are not modeled.
- The UI is a local Streamlit app with session-based state and
  a background worker. It has no cancellation control or durable job queue;
  a new browser session or server restart clears the displayed result.

## References

- Barnhart et al., *Airline Crew Scheduling* (2003).
- [MOSEK Fusion API for Python](https://docs.mosek.com/latest/pythonfusion/index.html).
- [Project planning and flow](airline_crew_pairing_project_flow.md).
