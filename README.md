# Flight-Scheduling-ILP
Solving the flight scheduling problem using Integer Linear Programming (ILP), based on real-world flight data, to generate optimal flight routes and schedules.

## Project layout

- `crew_pairing/`: flight graph, duties, pairings, costs, and shared data paths.
- `column_generation/`: pricing, restricted master LP, final ILP, and the current runner.
- `historical_code/`: the earlier matrix-based solver and its runner.
- `tests/`: unit tests; `tests/diagnostics/` contains coverage and tracing tools.
- `data/inputs/`: flight and crew-base CSV files; `data/generated/` contains the padded week. The original archive can be kept locally in `data/source/` and is ignored by Git.
- `docs/`: design notes; `reports/column_generation/`: saved summaries.

Run commands from this directory using module names so package imports resolve:

```powershell
python -m unittest discover -s tests -p 'test_*.py'
python -m column_generation.main_column_generation
python -m tests.diagnostics.diagnose_pairing_coverage
```

The optimization runner and its LP/ILP tests require MOSEK. The diagnostic command uses `data/inputs/week_1.csv` by default; you can pass another CSV path as its argument.
