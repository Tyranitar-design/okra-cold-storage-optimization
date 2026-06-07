# AI 决策 Agent 证据卡

更新日期：2026-06-05

## 核心定位

“秋葵决策助手”已升级为证据驱动的科研决策 Agent v2。本轮采用规则意图识别、结构化证据读取和安全动作建议，不接入外部大模型，不引入 LangChain/LangGraph，不自动运行 Gurobi、Optuna 或数据库写入。

Agent 的作用不是替代优化模型，而是把 MIS、Optuna AI warm start、AI-Benders/cut ranking、Gurobi 认证结果和论文证据包串成可解释的交互层。

## 当前能力

- 系统状态：只读检查数据库、Gurobi、地图和论文证据包。
- Optuna warm start：解释正式 best trial、5.6498x speedup、固定复核 4.8364x、未刷新 7.18x 历史最高。
- AI 融合：解释 ML、DL、RL、Optuna 与 Gurobi 的分层关系。
- AI-Benders：给出 cut ranking / robustness 口径，不写成显著加速。
- 论文口径：区分“可写”和“不可写”的创新表述。
- 下一步建议：基于当前证据链建议复核、展示和后续 DRL-lite 扩展。
- 可控动作：刷新看板、跳转页面；导出和求解仅返回确认跳转，不直接执行。

## 证据来源

- `/api/v1/experiments/ai-warmstart-report`
- `/api/v1/ai/fusion`
- `/api/v1/analysis/benders-convergence`
- `/api/v1/experiments/paper-evidence-pack`
- `/api/v1/dashboard/bootstrap`
- `docs/Optuna_AI_WarmStart_证据卡.md`

## 安全边界

- `read_only=true`
- 不读取本地密钥。
- 不调用外部网络。
- 不直接运行 Gurobi/Optuna。
- 不写数据库。
- 不直接下载文件。
- 不修改核心参数。

导出、实时求解和后续复核都必须由用户确认后，在对应页面或脚本中手动执行。

## 参考理念

本 Agent 借鉴 12-factor agents 的工程原则：上下文结构化、工具结果显式、人类确认、可控动作和清晰边界。本项目不复制外部仓库代码，也不新增外部 Agent 框架依赖。

## 论文/汇报表述

可写：

> 系统进一步构建了证据驱动的科研决策 Agent，将 Optuna warm start、Benders cut ranking、Gurobi 认证和论文证据包统一为可交互解释层；Agent 默认只读，并对导出、求解等动作要求人工确认。

不可写：

> Agent 自动替代优化专家完成求解。

> Agent 自动运行 Gurobi/Optuna 并修改模型参数。

> AI-Benders 已证明通用显著加速。
