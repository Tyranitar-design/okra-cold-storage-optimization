# Model v3.0 Gap-Closure Report

## Summary

- profile_count: 4
- run_count: 2
- baseline_status: TIME_LIMIT
- baseline_mip_gap_pct: 6.106300572603626
- best_objective_profile: bound_focus_60s
- best_objective: 4205367.9926100625
- best_bound_profile: extended_bound_900s
- best_bound: 4163496.4284208757
- smallest_gap_profile: extended_bound_900s
- smallest_gap_pct: 0.9956694458788419
- gap_improved_vs_baseline: True
- any_gap_satisfied: True
- evidence_state: gap_satisfied

## Runs

- bound_focus_60s: status=TIME_LIMIT, objective=4205367.9926100625, bound=4028748.6082075206, gap=4.199855630063971
- extended_bound_900s: status=OPTIMAL, objective=4205367.9926100625, bound=4163496.4284208757, gap=0.9956694458788419

## Boundary

Gap-closure runs are solver-profile experiments for the existing v3.0 scenario model. They can improve optimization evidence, but they do not replace real enterprise channel data or justify an optimality claim unless solver status and MIP gap support it.

## Next Action

Use the gap-satisfied profile as current v3.0 solver evidence, then run v3.0 scenario/sensitivity and real-parameter calibration.
