# Airline Crew Pairing Optimization

The solver loads scheduled flights, builds a flight connection graph, generates
legal duties, and builds a duty connection graph. It then generates an initial
pairing pool, adds columns through heuristic pricing and a restricted master LP,
and solves a final binary ILP over the generated pairings using MOSEK Fusion.
The objective minimizes sitting time within duties plus rest between duties,
measured in hours.

See [Project Planning and Flow](airline_crew_pairing_project_flow.md) for the
pipeline stages, model constraints, search budgets, and file responsibilities.

## Installation

Use Python 3.12 (the verified version) and install the dependencies from the
repository root:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

A valid MOSEK license is required for LP and ILP solves. Configure it in the
standard MOSEK license location or set `MOSEKLM_LICENSE_FILE` to its path.

## Required inputs and configuration

The current local configuration uses these instance 1 input files:

- `data/generated/instance1_week_3_with_start_end_padding.csv`: 428 flights departing
  January 12-24, 2000. The 227 flights departing January 15-21 are required;
  the remaining 201 flights are optional start/end padding.
- `data/inputs/instance1_listOfBases.csv`: airport codes and crew-base status.

To use another dataset, set both `FLIGHTS_FILE_PATH` and `HUBS_FILE_PATH` in
`crew_pairing/config.py` and align its padding dates with the flight schedule.

`crew_pairing/config.py` contains input paths, crew legality limits, and padding
intervals.
`column_generation/config.py` contains initial-pool and pricing
budgets, the random seed, and solver/runner settings.

The flight CSV fields are `leg_nb`, `airport_dep`, `date_dep`, `hour_dep`,
`airport_arr`, `date_arr`, and `hour_arr`. Dates and times use `YYYY-MM-DD` and
`HH:MM`. The bases CSV fields used by the solver are `airport` and `status`
(`1` for a crew base, `0` otherwise).

## Input Data Assumptions

- Flight IDs are unique strings. Arrival must be strictly after departure;
  the loader rejects duplicate IDs and nonpositive durations.
- Airport codes are consistent across inputs. Base status is `1` for a crew
  base and `0` otherwise; airports not listed as crew bases are non-bases.
- All flight timestamps use a consistent time basis.
- Padding classification uses departure dates. The configured padding date
  ranges must match the active dataset.
- Padding flights are optional and covered at most once. Required flights
  must be covered exactly once.

## Run the solver

For the local Streamlit/Plotly demonstration, see [UI instructions and validation](UI/README.md).
From this repository root:

```powershell
python -m pip install -r UI/requirements.txt
python -m streamlit run UI/app.py
```

The UI delegates execution, best-solution selection, and JSON saving to the
shared run manager, using consecutive seeds beginning with the entered seed.
The command-line default described below continues to use the shared RNG stream.

Run from the repository root so package imports resolve:

```powershell
.\.venv\Scripts\python.exe main.py
```

`main.py` defaults to five attempts sharing one `random.Random(42)` instance.
It loads flights, builds the flight graph, generates duties, and builds the duty
graph once for the batch. Each attempt calls `column_generation/main_column_generation.py`
with the shared prepared inputs and the same RNG, creates a fresh initial pairing
pool, runs CG, and solves the final ILP with the existing per-run search budgets.
Each attempt returns its summary and chosen pairing records in memory.
The RNG is seeded once before the attempts and its state advances across them;
it is not recreated or reseeded between attempts, including after a failed run.
For a different batch seed or run count when calling from Python, use
`main.main(seed=123, num_runs=5)`; use `num_runs=1` for a single attempt.
If `seed=None`, one random seed is generated and recorded for the batch's shared RNG.
Replaying the same batch seed and run order reproduces the random sequence.
An individual later attempt cannot be replayed by reseeding alone: it requires
the preceding attempts' RNG state. Run summaries record the batch seed and the
one-based `batch_run_index` so their position in the shared stream is clear.
The previous `python -m column_generation.main_column_generation` command still
forwards to the root pipeline.

Progress messages are enabled by default. To silence them:

```powershell
$env:ILP_PROGRESS = '0'
.\.venv\Scripts\python.exe main.py
```

## Results

Results are printed to the terminal: generated column count, restricted master
LP objective, final solution dimensions, total cost, and selected pairing count.
At the end of a batch, the runner writes at most two files under `results/runs/`:

- `best_<batch_id>.json`: only the cheapest feasible integer solution, with its
  complete run summary and each chosen pairing's duties and flights under
  `integer_solution.pairings`. Selection compares the final integer solution's
  rest plus sitting hours, rather than the LP objective. Equal costs keep the
  first feasible run. This file is omitted if no attempt produced a solution.
- `comparison_<batch_id>.json`: one compact record per attempt, with run ID,
  batch seed, batch run index, timings, CG results, LP/ILP statuses, cost, selected count, outcome, and
  error details. Full chosen-pairing records are excluded. The comparison also
  records batch start/end dates, shared graph-building time, total batch time,
  and the winning run ID, cost, and full-result path (or `null`).

No individual attempt files are created by the runner. An attempt's execution
error is recorded and its traceback is printed; the remaining attempts continue.
An error while preparing the shared graphs stops the batch, saves a comparison
with the setup error and zero completed attempts, and propagates the exception.
The best saved result retains the existing combined format described below.
The pairing records reuse the existing export serializer. `integer_solution.generated_at`
records the local export date and time in `DD/MM/YY HH:MM` format, for example
`11/10/26 15:30`, without seconds or a timezone suffix.
Files use a unique batch ID and never overwrite an earlier batch's output.
Both batch IDs and run IDs are generated with `uuid.uuid4().hex`; they identify
results independently of the random seed.
Earlier files remain as they are. The full combined result format
uses `schema_version: 4` and contains:

- `run_id`, `started_at` (local `DD/MM/YY HH:MM`), `random_seed` used to initialize
  the shared batch RNG, and one-based `batch_run_index`. Every attempt in the
  batch reports the same seed. A standalone CG call without a supplied RNG
  creates and records its own seeded RNG; its batch run index is `null`.
- `runtime_seconds`: per-attempt elapsed seconds for `initial_pool` (initial
  pairing search), `column_generation` (first restricted LP, pairing pricing
  and all LP re-solves), and `final_ilp` (model construction and solve).
  `build_graphs` is `0` because the attempt reuses the batch's graphs; actual
  input loading, flight graph, duties and duty graph time is recorded once in
  the comparison's batch-level `runtime_seconds.build_graphs`. `total` covers
  the attempt through preparation of the pairing records and excludes shared
  setup and JSON writing. Interrupted phases retain their elapsed time;
  unstarted phases are `null`.
- `column_generation`: completed pricing iterations, latest pairing-pool size,
  and `iteration_limit_reached` or `pricing_found_no_improving_pairings`.
  The initial LP is not an iteration. A completed empty-pricing pass counts as
  one iteration; interrupted iterations do not. If CG is interrupted, the
  termination reason is `null` and partial counts are retained. If an error
  occurs after CG finishes, its completed termination reason remains available.
- `lp`: MOSEK problem, primal solution, and dual solution statuses, objective
  value, and count of artificials strictly above the existing tolerance.
  Unavailable measurements are `null`; a failed new LP does not reuse the
  previous LP's measurements.
- `ilp`: whether the final solve was attempted, why it was skipped, and MOSEK
  problem and primal solution statuses.
- `integer_solution`: cost, selected-pairing count, export timestamp, and the
  chosen `pairings` with nested duties and flights when a feasible solution is
  found; otherwise `null`. No separate pairing export is created by the runner.
  If preparing the pairing records fails, the solution metrics are retained
  with `pairings: null` and the error is recorded. A valid empty selection uses
  `pairings: []`.
- `outcome`, `outcome_detail`, and `error` (type, message, traceback, or `null`).
  Run exceptions retain their traceback and are collected so later attempts
  can continue. Shared setup and file-writing exceptions still propagate.

The descriptive `objective` block is omitted. `integer_solution.cost` measures
rest plus sitting time in hours and is present only when a feasible integer
solution was found. `lp.objective_value` is available when the LP solved,
including runs which later fail. The restricted LP objective contains the configured
artificial-variable penalty; with positive artificials it is not simply a
schedule's rest and sitting hours. Legality and timing constraints remain in
config and are not copied into summaries.

Outcome codes distinguish `integer_solution_found`, `lp_artificials_remaining`,
`generated_pool_integer_infeasible`, `solver_no_conclusion`, and
`execution_error`. Remaining artificials, an integer-infeasible generated pool,
and unresolved solver statuses do not prove that the full problem is infeasible.
LP/ILP unresolved-status errors retain both the reported statuses and exception
details. Status handling follows the
[MOSEK solution-status documentation](https://docs.mosek.com/latest/pythonfusion/accessing-solution.html).

To save terminal output as well, redirect it:

```powershell
.\.venv\Scripts\python.exe main.py > solver-output.log
```

If required flights still have positive artificial coverage in the restricted
master LP, the runner prints those flights and stops before the final ILP.
That attempt is recorded in the comparison and the batch continues.
Pricing is a bounded heuristic; the final ILP optimizes over the generated
columns and does not establish global optimality over all possible pairings.

The restored [pricing configuration benchmark](experiments/pricing_configuration_benchmark/README.md)
compares search budgets using the current pricing implementation and writes CSV
results. Run it from the repository root:

```powershell
python experiments/pricing_configuration_benchmark/benchmark_pricing_configuration.py
```
