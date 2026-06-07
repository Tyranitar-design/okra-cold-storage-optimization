# Optuna AI Warm Start 证据卡

更新日期：2026-06-05

## 核心结论

Optuna 自动调参在 v3.0 AI warm start 精确求解链上得到一组可复现、可展示的正式调参证据：在同一县域案例与同一 Gurobi 认证流程下，最佳 trial 将求解时间从 cold baseline 的 180.06s 降至 31.87s，达到 5.6498x 加速，gap 为 0.0%，目标值与 baseline 一致/不劣化。

该结果超过首轮 smoke 的 3.168x，但没有超过项目历史 6.65x/7.18x 最高 warm-start 记录。因此论文和汇报的稳妥表述是：Optuna 自动搜索提供了 5.65x clean speedup evidence，最终解的可行性、目标值与 gap 仍由 Gurobi 认证。

## 正式实验

- 脚本：`experiments/ai_warmstart_optuna.py`
- 命令：`python experiments/ai_warmstart_optuna.py --fresh --n-trials 24 --timeout 7200`
- 单目标 Optuna：24/24 trials complete
- 多目标 Pareto study：6/6 trials complete
- Pareto front size：1
- 结果目录：`results/experiments/ai_warmstart_optuna/`

## 最佳 Trial

- Trial：#21
- Cold baseline：180.06s，gap 1.6912%，status TIME_LIMIT
- Best warm start：31.87s，gap 0.0%
- Speedup vs cold：5.6498x
- Objective：4,433,112.274860297
- Objective consistency：true
- Warm strategy：`site_type`
- Top K：7
- XGBoost：`n_estimators=84`，`max_depth=5`，`learning_rate=0.1236013350161545`
- Gurobi：`MIPFocus=1`，`Cuts=2`，`Heuristics=0.05146208328996727`，`Presolve=1`

## 固定参数复核

- 脚本：`experiments/ai_warmstart_optuna_recheck.py`
- 命令：`python experiments/ai_warmstart_optuna_recheck.py --replications 1 --skip-cold`
- 复核 1 次：37.23s，gap 0.0%，speedup 4.8364x
- Objective consistency：true
- Solved to tolerance：true

复核说明：Gurobi 求解时间存在自然波动，因此复核结果不要求逐秒等同于 Optuna best trial；当前证据支持“固定 best 配置仍能稳定产生 clean acceleration 且目标值不劣化”。

## 产物索引

- `results/experiments/ai_warmstart_optuna/ai_warmstart_optuna_summary.json`
- `results/experiments/ai_warmstart_optuna/ai_warmstart_optuna_trials.csv`
- `results/experiments/ai_warmstart_optuna/ai_warmstart_optuna_pareto.csv`
- `results/experiments/ai_warmstart_optuna/ai_warmstart_optuna.md`
- `results/experiments/ai_warmstart_optuna/ai_warmstart_optuna_recheck_summary.json`
- `results/experiments/ai_warmstart_optuna/ai_warmstart_optuna_recheck_trials.csv`
- `results/experiments/ai_warmstart_optuna/ai_warmstart_optuna_recheck.md`

## 声明边界

AI/Optuna 不替代 Gurobi。Optuna 负责搜索 XGBoost ranker、warm start 构造和部分 Gurobi 参数；最终可行性、目标值一致性与配置 gap 仍由 Gurobi 认证。本证据是县域案例上的精确求解增强证据，不等同于企业级泛化验证，也不能写成 AI 已刷新项目历史最高加速记录。
