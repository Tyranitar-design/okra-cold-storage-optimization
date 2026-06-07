# AI Warm Start Optuna Report

- Built at: `2026-06-05T14:20:21Z`
- Single-objective trials: `24/24` complete
- Multi-objective trials: `6/6` complete
- Pareto front size: `1`
- Cold baseline elapsed: `180.06` s
- Cold baseline gap: `1.6912` %
- Best trial: `#21`
- Best elapsed: `31.87` s
- Best speedup vs cold: `5.6498` x
- Best gap: `0.0` %
- Objective consistent: `True`
- Warm strategy: `V2 site + type`
- Historical best speedup reference: `7.18` x
- Exceeds historical best: `False`

## Formal Conclusion

Optuna completed a `24`-trial single-objective tuning study and found trial `#21` with `5.6498`x speedup against the cold baseline while preserving the certified objective value. This is clean acceleration evidence for the v3.0 county-case pipeline.

The run improves on the earlier smoke result, but it does not exceed the historical `7.18`x warm-start record. The honest claim is Optuna-backed reproducible tuning evidence, not a new project-wide speedup record.

## Best Trial Configuration

- XGBoost: `n_estimators=84`, `max_depth=5`, `learning_rate=0.1236013350161545`
- Warm start: `warm_strategy=site_type`, `top_k=7`
- Gurobi: `MIPFocus=1`, `Cuts=2`, `Heuristics=0.05146208328996727`, `Presolve=1`

## Claim Boundary

Optuna tunes XGBoost ranker parameters, warm-start construction, and selected Gurobi parameters for the v3.0 AI warm-start pipeline. Gurobi remains responsible for feasibility and configured-gap certification; this is county-case acceleration evidence, not enterprise-scale generalization or proof that AI replaces exact optimization.
