# AI-Benders 可解释 cut ranking 原型：方法与阶段实验

## 方法定位

本研究中的 AI-Benders 并不替代经典 Benders 分解的数学正确性，而是作为一种 AI4OPT 风格的 cut ranking 原型，用于探索在冷库布局与需求分配分解框架中，如何利用问题图结构和历史 cut 特征为后续 cut 选择、cut 排序和求解加速提供可解释信息。该定位有助于避免将尚处原型阶段的学习模块过度表述为“已证明优于经典精确算法”的结论。现阶段，经典 Benders 仍负责产生主问题、子问题、对偶信息和可行 cut；AI 模块只在 cut 历史已经产生之后，对候选 cut 进行评分、排序和解释。

具体而言，冷库布局问题首先被表示为需求节点与候选设施节点构成的二分图。需求节点包含行政层级、产量、候选属性、人口和经纬度等特征，候选设施节点保留同构的空间与业务属性；边特征由需求点到候选设施点之间的距离、运输时间和需求量构成。图编码器采用轻量级消息传递结构，在不依赖 PyTorch Geometric 的前提下形成问题级 graph embedding。该设计当前主要服务于工程可运行性与可解释性，后续可替换为 PyTorch Geometric 的 GCN、GraphSAGE 或 GAT 编码器，以进一步提升模型表达能力。

在 cut 表征方面，每条 Benders cut 被转化为固定维度的数值特征，包括右端项、系数个数、系数绝对值均值、标准差、最大值、最小值、L1/L2 范数、正负系数比例、迭代编号、主问题目标值、子问题目标值、当前 gap 和累计 cut 数量。随后，系统将 graph embedding 与 cut feature 拼接，输入轻量 MLP 型 contextual bandit scorer，学习历史迭代中 cut 与 gap 改善之间的关系。当前评分公式统一写为 `0.40 * rhs + 0.25 * coef_l1 + 0.20 * gap_pct + 0.15 * compactness`，其中 `compactness = 1 / (1 + coef_count)`，这样可以保证 cut score 的可解释性和可复现性。由于当前训练样本仍较少，该 scorer 的主要价值是产生结构化 cut score、selected cut、feature importance 和 selection_summary，而不是直接声称能够稳定提升求解效率。

## 实验设置

为了从单条 smoke test 进一步提升到可审计的阶段实验，本研究新增了 `experiments/ai_benders_comparison.py`。该脚本在三个小中规模配置下同时运行经典 Benders 和 AI-Benders，配置分别为 5 个候选点/6 个需求点、7 个候选点/8 个需求点、9 个候选点/10 个需求点。三个配置均采用较严格的 `mip_gap = 0.001`，最大迭代次数为 5，并分别设置 60、90 和 120 秒时间限制。实验输出包括 Benders 与 AI-Benders 的上界、下界、最终 gap、cut 数量、迭代次数和运行时间，同时保存 AI-Benders cut score 明细。

本阶段实验的主要结果文件位于 `results/experiments/ai_benders_comparison/`。其中，`ai_benders_comparison.csv` 和 `ai_benders_comparison.md` 记录方法对比汇总，`ai_benders_cut_scores.csv` 记录 14 条 cut score，`ai_benders_comparison_summary.json` 保存完整结构化结果，便于后端 API 和数据库种子脚本读取。对应 API 已在 FastAPI 中开放为 `/api/v1/algorithms/ai-benders/comparison` 与 `/api/v1/algorithms/ai-benders/comparison/cut-scores`；前者返回 case-level 的 `summary_rows` 和 `cut_score_rows`，后者返回 cut-level 的 `selection_summary`、`feature_importance_top` 与评分明细，用于后续 Web 管理后台的算法分析页面。

## 阶段结果

在三个测试配置中，经典 Benders 与 AI-Benders 的上界、最终 gap、cut 数量和迭代次数保持一致。这说明当前 AI-Benders 原型并未改变 Benders 分解的求解轨迹，也尚未形成严格意义上的加速效果证明。在 5 候选/6 需求配置下，两种方法均得到 2,589,474.25 元的上界，最终 gap 为 0.27%，cut 数为 5，迭代数为 5；在 7 候选/8 需求配置下，上界为 3,268,228.33 元，最终 gap 为 0.04%，cut 数为 4，迭代数为 4；在 9 候选/10 需求配置下，上界为 4,122,831.73 元，最终 gap 为 0.15%，cut 数为 5，迭代数为 5。运行时间方面，9 候选/10 需求配置中 AI-Benders 用时约 0.16 秒，经典 Benders 约 0.23 秒，但该差异来自小样本短运行环境，不能作为显著加速结论。

更重要的是，AI-Benders 原型已经能够为每个配置输出 cut-level 评分证据。三组实验共生成 14 条 cut score，记录了 cut 右端项、系数数量、当前 gap、是否被策略选中以及 policy name，同时还输出了 `score_formula`、`score_components`、`dominant_factors` 和 `selection_summary`。对于 5 候选/6 需求配置，模型在 5 条 cut 中选择了第二条 cut；对于 7 候选/8 需求配置，模型在 4 条 cut 中选择了第一条 cut；对于 9 候选/10 需求配置，模型在 5 条 cut 中选择了第四条 cut。这些结果表明，当前 AI 模块已经可以形成“问题图编码—cut 特征抽取—cut 打分—可解释输出”的闭环。

## 学术边界

当前结果可以支持的结论是：本项目已经实现了一个与经典 Benders 兼容的 AI-Benders 可解释 cut ranking 原型，并在多个小中规模配置上生成了结构化 cut score 证据、评分公式和双层展示接口。该原型为后续引入 PyTorch Geometric 图神经网络、Stable-Baselines3 强化学习策略或更大规模 benchmark 训练提供了工程接口和实验基础。

当前结果不能支持的结论是：AI-Benders 已经显著优于经典 Benders，或者已经在真实企业大样本场景下证明了求解加速效果。原因在于本阶段对比实验规模仍较小，cut score 只有 14 条，且 AI 模块尚未真正改变主问题中 cut 的加入顺序或筛选策略。论文中应将其表述为“AI-enhanced Benders prototype”或“可解释 cut ranking 原型”，而不是“成熟加速算法”。后续若要支撑更强结论，需要在公开 LRP benchmark 和更大规模冷链扩展实例上进行系统对比，并记录每轮 cut selection 对下界提升、gap 收敛和运行时间的影响。

## 第二阶段：AI-active Benders 设计

在完成可解释 cut ranking 原型之后，项目进一步设计了 AI-active Benders 第二阶段，用于检验 AI 评分是否能够从“事后解释”推进到“主动参与 cut 选择”的机制层面。具体做法是先利用 classic Benders 的 cut history 对同一实例进行校准，学习每条 cut 的结构特征、排序分数和主导因子，再在第二轮 Benders 迭代中仅保留被策略选中的 active cuts，并通过 `active_cut_budget` 控制每轮进入主问题的有效 cut 数量。该设计把 AI 模块从旁路解释器提升为主问题 cut 管理器，但仍保留经典 Benders 的子问题、对偶信息和收敛判断作为数学主干。

当前代码已在 `experiments/benchmark_benders_comparison.py` 中加入 `ai_active_benders` 分支，并同步预留 `active_cut_budget`、`active_cut_count`、`active_cut_scores`、`termination_reason` 与 `ai_active_summary` 等输出字段，便于记录每个公开 benchmark 实例的 cut 选择轨迹、上下界变化和终止原因。与此同时，项目新增 `src/api/benchmark_benders_validation.py` 与 `scripts/validate_benchmark_benders.py`，将 AI-active 结果判定逻辑固化为共享验收器；后端接口 `/api/v1/benchmarks/lrp/benders-validation` 和 MIS 前端验收区块会直接展示 `state`、`evidence_level`、结果文件和声明边界。最新公开 benchmark 运行已生成 `ai_active_benders` 方法行、迭代行与 cut score 行，`results/experiments/benchmark_benders_comparison/ai_active_validation.json|md` 的状态已更新为 `verified_result_present`。因此这一分支现在可以表述为“机制验证已跑通”，但仍不能写成已经证明加速或优于经典 Benders。

后续验证顺序应当是先完成 `py_compile`，再在公开 benchmark small 层上运行 `classic_benders`、`ai_benders` 和 `ai_active_benders` 三组配置，比较 objective、gap、cut 数、selected cut 数、lower bound 轨迹和耗时，并检查 `ai_active_summary` 中的终止原因是否稳定。若该机制在多实例上都表现出更快的 gap 收敛或更少的主问题 cut 负担，才有资格进一步讨论 AI-active Benders 的加速价值。

## 可复现路径

本节对应代码为 `src/algorithms/benders.py`、`src/algorithms/benders_ai.py`、`src/algorithms/cut_features.py`、`src/algorithms/gnn_encoder.py` 和 `src/algorithms/rl_agent.py`。核心实验脚本为 `experiments/ai_benders_comparison.py` 与 `experiments/benchmark_benders_comparison.py`。执行前者后，将生成 `results/experiments/ai_benders_comparison/ai_benders_comparison.csv`、`ai_benders_comparison.md`、`ai_benders_cut_scores.csv` 和 `ai_benders_comparison_summary.json`；执行后者后，将进一步生成 `benchmark_benders_comparison.csv`、`benchmark_benders_iterations.csv`、`benchmark_benders_cut_scores.csv` 和 `benchmark_benders_summary.json`，并为 AI-active Benders 记录 `ai_active_benders`、`active_cut_budget` 与 `ai_active_summary` 结构。数据库种子脚本 `scripts/seed_postgres_from_current_files.py --dry-run` 已能识别 14 条 AI-Benders cut score，并将其映射到 `okra.ai_benders_cut_scores` 的目标结构；AI-active 分支现在也已产生公开 benchmark 结果，并通过 `python scripts/validate_benchmark_benders.py` 验证为 `verified_result_present`。论文结果部分仍应保留边界，明确 AI-active 只是同实例机制验证，不是完整 routing LRP 或稳定加速证明。
