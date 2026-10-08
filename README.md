# Flight-Scheduling-ILP
Solving the flight scheduling problem using Integer Linear Programming (ILP), based on real-world flight data, to generate optimal flight routes and schedules.

## Project layout

- `crew_pairing/`: flight graph, duties, pairings, costs, and shared data paths.
- `column_generation/`: pricing, restricted master LP, final ILP, and the current runner.
- `historical_code/`: the earlier matrix-based solver and its runner.
- `tests/`: unit tests; `tests/diagnostics/` contains coverage and tracing tools.
- `data/inputs/`: flight and crew-base CSV files; `data/generated/` contains the padded weeks. The original archive can be kept locally in `data/source/` and is ignored by Git.
- `docs/`: design notes; `reports/column_generation/`: saved summaries.

Edit `crew_pairing/config.py` for crew legality limits and padding dates. Edit `column_generation/config.py` for initial pool, pricing, solver, and runner defaults. Function arguments can still override many limits for an individual call. CSV column names remain with the CSV parser.

The active input is `data/generated/week_3_with_start_end_padding.csv`: January
15-21, 2000 is required, January 12-14 is start padding, and January 22-24 is end
padding. `PADDING_DATE_RANGES` defines inclusive intervals by departure date.
Padding flights can support pairings but are covered at most once; required
flights must be covered exactly once. When changing datasets, update both the
input path and the padding intervals. For the original week-one padded CSV,
use the single interval January 8-10, 2000.

Run commands from this directory using module names so package imports resolve:

```powershell
python -m unittest discover -s tests -p 'test_*.py'
python -m column_generation.main_column_generation
python -m tests.diagnostics.diagnose_pairing_coverage
```

The runner prints `[ILP PROGRESS +...s]` messages as it works, including timed
updates during long graph and pairing searches. Set `ILP_PROGRESS=0` to silence
all of these messages without changing the normal result output:

```powershell
$env:ILP_PROGRESS = '0'
python -m column_generation.main_column_generation
```

The progress code is contained in `run_progress.py`; search for `run_progress`
to find its imports if you later want to remove it entirely.

The optimization runner and its LP/ILP tests require MOSEK. The diagnostic command uses `data/inputs/week_1.csv` by default; you can pass another CSV path as its argument.
