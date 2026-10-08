# Airline Crew Pairing Optimization

The solver loads scheduled flights, builds a flight connection graph, generates
legal duties, and builds a duty connection graph. It then generates an initial
pairing pool, adds columns through heuristic pricing and a restricted master LP,
and solves a final binary ILP over the generated pairings using MOSEK Fusion.
The objective minimizes sitting time within duties plus rest between duties,
measured in hours.

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

Both required CSV files are version controlled:

- `data/generated/week_3_with_start_end_padding.csv`: 428 flights departing
  January 12-24, 2000. The 227 flights departing January 15-21 are required;
  the remaining 201 flights are optional start/end padding.
- `data/inputs/listOfBases.csv`: airport codes and crew-base status.

Required flights must be covered exactly once. Padding flights may support
pairings and are covered at most once. Classification uses departure dates.

`crew_pairing/config.py` contains crew legality limits and padding intervals.
`column_generation/config.py` contains input paths, initial-pool and pricing
budgets, the random seed, and solver/runner settings. When selecting another
dataset, update its path and padding intervals together.

The flight CSV fields are `leg_nb`, `airport_dep`, `date_dep`, `hour_dep`,
`airport_arr`, `date_arr`, and `hour_arr`. Dates and times use `YYYY-MM-DD` and
`HH:MM`. The bases CSV fields used by the solver are `airport` and `status`
(`1` for a crew base, `0` otherwise).

## Run the solver

Run from the repository root so package imports resolve:

```powershell
.\.venv\Scripts\python.exe -m column_generation.main_column_generation
```

Progress messages are enabled by default. To silence them:

```powershell
$env:ILP_PROGRESS = '0'
.\.venv\Scripts\python.exe -m column_generation.main_column_generation
```

## Results

Results are printed to the terminal: generated column count, restricted master
LP objective, final solution dimensions, total cost, and selected pairing count.
The runner does not write result files. To save its terminal output, redirect it:

```powershell
.\.venv\Scripts\python.exe -m column_generation.main_column_generation > solver-output.log
```

If required flights still have positive artificial coverage in the restricted
master LP, the runner prints those flights and stops before the final ILP.
Pricing is a bounded heuristic; the final ILP optimizes over the generated
columns and does not establish global optimality over all possible pairings.
