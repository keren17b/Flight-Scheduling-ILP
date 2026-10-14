# Restoration verification — October 9, 2026

Recovered the script and both historical CSVs from `a564e63`; the CSVs are byte-for-byte unchanged. The folder was deleted in `fcc8a78`.

Updated imports to the current input configuration, the initial-pool two-value return, and the final ILP `None` result. Pricing now calls the production implementation, with a shared RNG per configuration, current global state budgets, and empty-pricing retries. Configuration inputs remain isolated. New output folders preserve the historical results.

Four regression cases passed using real MOSEK solves: reproducible pricing reaching binary feasibility without mutating the shared inputs; fractional feasibility with integer infeasibility; skipping the binary solver; and empty-pricing retries with uncovered flights. Syntax checks and CSV accounting checks also passed.

The full LP-only sweep completed with exit code 0 on the active dataset (428 flights, 3,086 duties, 1,355 shared initial columns). All nine configurations ran; eight reached zero artificials. Each iteration CSV agrees with its summary column counts and final artificial counts, and LP objectives did not increase when columns were added.

Command:

```powershell
python experiments/pricing_configuration_benchmark/benchmark_pricing_configuration.py --skip-final-ilp --output-dir experiments/pricing_configuration_benchmark/runs/verification_lp
```

| Configuration | Additions | Final columns | Positive artificials | LP feasible |
| --- | ---: | ---: | ---: | --- |
| K20_S500_P500_G2000 | 5 | 11355 | 0 | True |
| K20_S1000_P500_G2000 | 7 | 15355 | 0 | True |
| K20_S2000_P500_G2000 | 10 | 21355 | 0 | True |
| K20_S3000_P500_G2000 | 9 | 19355 | 0 | True |
| K10_S2000_P500_G2000 | 6 | 13355 | 0 | True |
| K30_S2000_P500_G2000 | 9 | 19355 | 0 | True |
| K20_S2000_P100_G2000 | 4 | 9355 | 0 | True |
| K20_S2000_P500_G500 | 10 | 6355 | 62 | False |
| K20_S2000_P500_G5000 | 5 | 26355 | 0 | True |

[LP summary CSV](runs/verification_lp/pricing_configuration_benchmark_results.csv) · [LP iteration CSV](runs/verification_lp/pricing_configuration_benchmark_iterations.csv)

The initial run with binary checks completed the first two configurations: both reached LP feasibility and MOSEK proved their generated pools integer-infeasible. These were recorded correctly, and the script continued. The third binary solve was interrupted because it was taking substantially longer. The complete nine-configuration binary sweep was not verified. The subsequent full sweep above intentionally used `--skip-final-ilp`.

[Partial binary summary CSV](runs/verification/pricing_configuration_benchmark_results.csv) contains only the two completed configurations; it is not a complete sweep.

Per-config timing is from one run and is not a statistical performance comparison. LP feasibility is not a guarantee of binary feasibility or global optimality. The experiment stops at LP feasibility, while the production loop can continue improving its columns. Existing solver modules and defaults were unchanged.
