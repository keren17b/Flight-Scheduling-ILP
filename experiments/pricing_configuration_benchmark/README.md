# Pricing configuration benchmark

Recovered from commit `a564e63` (deleted in `fcc8a78`) and adapted to the current
project. The two CSVs beside the script are unchanged historical results from
the original pricing implementation and dataset. Current runs use the active
paths and padding rules in `crew_pairing/config.py`.

From the repository root, with the project dependencies and a valid MOSEK license:

```powershell
python experiments/pricing_configuration_benchmark/benchmark_pricing_configuration.py
```

The script also works when launched from the experiment folder or by absolute
path from any other directory. All nine historical configurations run by default,
with ten column additions per configuration and an optional final binary solve
once LP artificials disappear. To run a smaller comparison:

```powershell
python experiments/pricing_configuration_benchmark/benchmark_pricing_configuration.py --config K20_S500_P500_G2000 --iterations 10 --skip-final-ilp
```

Repeat `--config` to select multiple configurations. Use `--output-dir` to choose
where to write results; otherwise each invocation creates a fresh folder under
`runs/`. Summary and iteration CSVs are saved after each configuration. An
iteration CSV is written only when at least one column addition occurs.

Each configuration starts with copies of the same initial columns, signatures,
and first LP result, and its own RNG with the configured project seed. The RNG
continues across iterations and empty-pricing retries. The experiment calls
`generate_pricing_pairings` directly, including the current global DFS budget,
cached rankings, feasibility filtering before Top-K, and reduced-cost tolerance.
It no longer maintains a separate DFS implementation or reports counters from
that old implementation.

This experiment measures time to feasibility. It stops when LP artificials reach
zero; the production column-generation loop can keep improving the objective
after that point. LP feasibility does not imply binary feasibility: a failed
binary solve is recorded in `final_ilp_error`, and the comparison continues.
Shared graph/initial-pool/first-LP preparation time is excluded from per-config
times and included in the total benchmark wall time. Solver defaults are not
automatically tuned by the benchmark.

Run the small regression cases (also requiring MOSEK):

```powershell
python -m unittest discover -s experiments/pricing_configuration_benchmark -p test_benchmark.py
```

See [verification.md](verification.md) for the checks and saved results from the
restoration on October 9, 2026.
