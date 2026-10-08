# Full timing experiments for LEG_02_27

The production column-generation pipeline was run in two isolated scenarios with its existing pricing budgets, seeds, initial-pool settings, and maximum of 100 iterations. Experiments changed in-memory copies only; the production configuration and input CSV remain unchanged. MOSEK was installed in a temporary workspace dependency directory and used the existing local license.

**9h58m minimum rest, original flight times:** the LP first achieved full required coverage at iteration 10. Pricing later stopped with 24,742 columns after 55 column-addition iterations. The final binary ILP successfully selected 72 pairings, covering all 234 required flights exactly once and padding flights at most once. Artificial sum is zero. The objective is 821.716667 under the production rest-plus-sitting cost model.

The selected solution includes:

| Pairing | Duties | Connection/rest |
|---|---:|---|
| LEG_01_30 → LEG_01_28 | 1 | 1h14m connection |
| LEG_02_25 → LEG_02_27 | 2 | 9h59m rest |

The shortest inter-duty rest in the complete returned binary schedule is 599 minutes. Consequently, this same schedule is also feasible with a 9h59m minimum. This conclusion comes from validating the returned schedule, rather than running a third optimization experiment.

**One-minute delay of LEG_02_27, original 10-hour minimum rest:** departure was changed from 13:45 to 13:46, and arrival from 16:34 to 16:35, preserving flight duration. Exact search verifies that LEG_01_30 → LEG_01_28 and LEG_02_25 → LEG_02_27 are now two disjoint legal pairings. The latter has exactly 10 hours rest. Pricing stopped after 97 column-addition iterations with 20,195 columns and LP objective 1,000,900.433333. Both requested flights have real coverage 1 and artificial value 0. The only remaining artificial is **LEG_03_27 = 1.000000**. The final binary ILP was skipped, following the production runner's rule while artificials remain. Final per-flight values and selected LP columns are recorded in `delay_one_minute/summary.json`.

There is an independent proof that delaying this one flight cannot make the entire schedule feasible. Consider these four required returns from AIR12:

```
LEG_01_28, LEG_02_27 (delayed), LEG_02_28, LEG_03_27
```

Only these three operating arrivals can supply their crews under the 10-hour rule:

```
LEG_01_30, LEG_02_25, LEG_02_30
```

Every return needs a distinct preceding arrival in a chronological crew path. LEG_03_25 arrives at 03:46 on January 3, and LEG_03_27 departs at 13:45: the same 599-minute gap excludes this fourth supply. Therefore at least one of those four returns must remain artificial. `delay_one_minute/bottleneck.json` records the verified same-duty and previous-duty arrival candidates.

Reproduce the experiments from the repository root, with MOSEK installed in the Python environment or supplied through `--deps`:

```powershell
python -m tests.diagnostics.compare_flight_timing rest_9h58
python -m tests.diagnostics.compare_flight_timing delay_one_minute
```

Raw results:

- `rest_9h58/summary.json`: full LP history and final binary result.
- `rest_9h58/selected_pairings.json`: all 72 selected binary pairings.
- `delay_one_minute/summary.json`: full LP history, final artificial values, duals, and target/competitor coverage.
- `delay_one_minute/bottleneck.json`: structural four-return/three-arrival proof.
