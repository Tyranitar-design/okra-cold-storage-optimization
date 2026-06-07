# 🌿 秋葵冷库布局优化项目 — 完整技术规格书

> **文件用途**：供代码专家(CodeBuddy Code / Codex)直接上手编写和运行代码
> **编写者**：小彩 💫 | **日期**：2026-05-26
> **版本**：v2.0 — 读完此文件即可开始编码（新增：AI融合、物流集成、应用开发、环境决策）

---

## 一、项目概述

### 1.1 项目名称

**AI-Enhanced Bilevel Multi-Objective MIP for Cold Storage Layout and Capacity Optimization**

中文：基于AI增强双层多目标混合整数规划的秋葵主产区冷库布局与容量优化研究

### 1.2 目标

- **学术目标**：发表SCI核心期刊论文
- **工程目标**：实现完整的优化模型+求解算法+实验系统
- **案例**：湖南省J县（对标 Huang et al. 2025）

### 1.3 核心创新点详解（7大创新 — OR+AI深度融合）

#### 🔵 运筹优化核心（OR Core — 5项）

| # | 创新点 | 类型 | 说明 | 论文贡献 |
|---|--------|------|------|----------|
| 1 | ⭐ 双层规划建模 | OR | 上层：政府/投资者决策（选址+类型+容量，min建设+碳排放）<br>下层：运营方决策（运输+预冷+客户分配，min运营+损耗） | **填补 bilevel+冷链 空白**（Cavagnini2026综述确认：MOLRP精确方法极度稀缺） |
| 2 | ⭐ 多目标帕累托前沿 | OR | 三目标：f1=min成本，f2=min损耗率，f3=min碳排放<br>Augmented ε-约束法(精确帕累托) + NSGA-III(启发式对比) | **三目标LRP帕累托前沿面在冷链领域首次构建** |
| 3 | ⭐ 秋葵专用温度链约束 | OR | 预冷(≤2h,0-5°C)→冷藏(7-10°C)→气调(7-10°C+MAP)→冷冻(-18°C)<br>冷害温度4-5°C避免、预冷时间约束、温度-损耗非线性关系 | **现有LRP文献无秋葵/冷链特定温度链建模** |
| 4 | ⭐ 精确求解算法 | OR | KKT条件将双层MILP→单层MILP + Benders分解加速大规模问题 | **竞品Tang2025/Wang2024都是全启发式，我们全精确求解更优** |
| 5 | ⭐ 功能级系统集成 | OR | 冷库布局结果→物流路径规划系统(VRP)端到端联动<br>选址→容量→分配→配送路径 一条龙 | **从"静态布局"到"动态运营"的闭环** |

#### 🟢 AI增强层（AI4OPT — 2项，核心差异化）

| # | 创新点 | AI技术 | 说明 | 论文贡献 |
|---|--------|--------|------|----------|
| 6 | ⭐ 数据驱动参数学习 | **机器学习**(XGBoost/LightGBM) | **Smart Predict-then-Optimize (SPO)**: 用ML从历史数据学习秋葵损耗参数(α,β)而非手动估算<br>传统：文献给固定α=0.8,β=0.15<br>我们：ML学习→α(i,t,season),β(i,t,season)→更精准的优化输入 | **EJOR综述Fan2026明确指出：AI增强参数生成是未来方向** |
| 7 | ⭐ AI增强Benders分解 | **深度学习**(GNN) + **强化学习**(DQN/PPO) | GNN学习问题结构特征(二分图：候选点-需求点)→预测有潜力的Benders cut<br>RL(DQN)学习cut选择策略：选哪些cut加入主问题→加速收敛<br>传统Benders：所有feasibility cut全加→主问题膨胀<br>我们：AI只选最有价值的cut→主问题更紧凑→更快收敛 | **GNN+RL联合增强Benders在冷链LRP中首次应用** |

#### 🟡 AI融合的额外维度（论文可扩展讨论/未来工作）

| AI技术 | 应用场景 | 具体方式 | 优先级 |
|--------|----------|----------|--------|
| **大数据** | 历史产量+气象+价格数据 | 构建秋葵产区时序数据库→驱动参数学习(创新点6) | P0 |
| **机器学习** | 损耗参数预测 | XGBoost/LightGBM学习 α,β → SPO pipeline | P0 |
| **深度学习(GNN)** | Benders cut选择 | 构建选址-分配二分图→GNN预测cut价值 | P1 |
| **强化学习(DQN/PPO)** | Benders cut策略 | 状态=当前主问题，动作=选哪个cut，奖励=收敛速度 | P1 |
| **深度学习(LSTM)** | 产量/需求预测 | 历史数据→LSTM预测各节点未来产量→动态需求参数 | P2 |
| **计算机视觉** | 秋葵品质检测 | CNN/ResNet检测秋葵冷害/腐烂程度→实时损耗率更新 | P3 |
| **自然语言处理** | 政策/市场信息抽取 | NLP提取冷链政策、市场价格→影响碳价/损耗单价参数 | P3 |

> 💡 **论文叙事**：AI不是替代优化，而是在"参数生成→模型构建→求解加速→结果验证"全链条增强优化。这正是EJOR综述Fan2026的核心观点。

### 1.4 当前阶段

**Week 1, Day 2**：基线模型完善阶段

---

## 二、数据说明

### 2.1 数据位置

```
D:\秋葵冷库优化项目\data\
├── nodes.csv                  ← 39个节点
├── distance_matrix.csv        ← 39×39距离矩阵(km)
├── transport_time_matrix.csv  ← 39×39运输时间矩阵(h)
├── params.json                ← 保鲜参数+冷库类型参数
└── nodes.xlsx                 ← Excel版
```

### 2.2 节点数据 (nodes.csv)

39个节点：1个县级(C1) + 8个乡镇级(T1-T8) + 30个村级(V1-V30)

| 字段 | 说明 | 示例 |
|------|------|------|
| node_id | 节点ID | C1, T1, V1 |
| name | 节点名称 | J县县城 |
| level | 层级(1=村,2=乡镇,3=县) | 3 |
| level_name | 层级名称 | 县级/乡镇级/村级 |
| lat | 纬度 | 29.337 |
| lon | 经度 | 111.725 |
| okra_production_ton | 秋葵年产量(吨) | 86.6 |
| is_candidate | 是否为冷库候选点 | True/False |
| population | 人口 | 103946 |
| road_access | 是否通路 | True |

**关键统计**：
- 候选冷库选址点：27个 (is_candidate=True)
- 有产量的需求点：39个 (所有节点都有产量 > 0)
- 总产量：588.2吨/年
- 县城C1产量最大：86.6吨
- 乡镇级产量：20-58.6吨
- 村级产量：2-14.2吨

### 2.3 冷库类型参数 (params.json → cold_storage_types)

| 类型 | 代码 | 温度范围(°C) | 容量等级(吨) | 固定建设成本(万元) | 年运营成本(万元) | 能耗(kWh/吨) | 碳因子 |
|------|------|-------------|-------------|-------------------|----------------|-------------|--------|
| 预冷库 | precool | 0-5 | 5,10,20,50 | 8,14,24,52 | 2.4,4.0,6.8,14.0 | 3.5 | 0.8 |
| 冷藏库 | cold | 2-8 | 10,30,50,100,200 | 18,42,65,110,190 | 4.5,10.0,15.0,26.0,42.0 | 2.8 | 0.6 |
| 气调库 | ca | 2-5 | 10,30,50,100 | 35,80,120,200 | 8.0,18.0,26.0,45.0 | 4.0 | 0.9 |
| 冷冻库 | frozen | -25~-18 | 20,50,100,200 | 30,60,100,170 | 6.0,12.0,20.0,34.0 | 3.2 | 0.7 |

**注意**：固定建设成本和运营成本单位都是 **万元**，代码中需要 ×10000 转为元。

### 2.4 保鲜参数 (params.json → okra_preservation)

| 参数 | 值 | 说明 |
|------|-----|------|
| precool_time_limit_h | 2.0 | 预冷时间上限(小时) |
| precool_loss_rate | 0.01 | 预冷库存储损耗率 |
| cold_storage_loss_weekly | 0.03 | 冷藏库每周损耗率 |
| ca_storage_loss_weekly | 0.015 | 气调库每周损耗率 |
| transport_loss_per_hour | 0.02 | 运输每小时损耗率 |
| cold_storage_days | [7,14] | 冷藏保鲜天数 |
| ca_storage_days | [20,30] | 气调保鲜天数 |
| frozen_storage_days | [30,90] | 冷冻保鲜天数 |
| loss_alpha_1 | 0.8 | Fujiwara损耗模型参数1 |
| loss_alpha_2 | 0.4 | Fujiwara损耗模型参数2 |
| loss_beta_1 | 0.15 | Fujiwara损耗模型参数3 |
| loss_beta_2 | 0.08 | Fujiwara损耗模型参数4 |

### 2.5 距离与运输时间

- 距离矩阵：39×39，单位 km，基于Haversine公式计算
- 运输时间矩阵：39×39，单位 h，假设平均车速40km/h估算
- 矩阵索引顺序：C1, T1-T8, V1-V30

---

## 三、数学模型

### 3.1 当前基线模型：单层MIP

#### 集合

- **J** = 候选冷库位置集合（27个）
- **I** = 需求点集合（39个，所有有产量的节点）
- **T** = 冷库类型集合 = {precool, cold, ca, frozen}
- **C_t** = 类型t的容量等级集合

#### 参数

| 参数 | 说明 | 单位 |
|------|------|------|
| d_i | 需求点i的秋葵产量 | 吨/年 |
| dist_{ij} | i到j的距离 | km |
| t_{ij} | i到j的运输时间 | h |
| f_{tc} | t类型c容量等级的固定建设成本 | 万元 |
| o_{tc} | t类型c容量等级的年运营成本 | 万元 |
| cap_{tc} | t类型c容量等级的容量 | 吨 |
| c_trans | 运输单位成本 | 1.2 元/吨·km |
| c_loss | 损耗单价 | 3000 元/吨 |
| c_carbon | 碳价 | 50 元/吨CO₂ |
| τ | 预冷时间上限 | 2 h |
| α_transport | 运输损耗率 | 0.02 /h |
| α_storage_t | t类型存储损耗率 | 按类型不同 |
| e_t | t类型能耗 | kWh/吨 |
| γ_t | t类型碳因子 | kgCO₂/kWh |
| ε_transport | 运输碳排放因子 | 0.1 kgCO₂/吨·km |

#### 决策变量

- **z_{j,t,c}** ∈ {0,1}：是否在候选点j建设t类型c容量等级的冷库
- **x_{i,j,t}** ∈ {0,1}：需求点i的秋葵是否分配到j点t类型的冷库

#### 目标函数

**min** Z = Z_fixed + Z_operate + Z_transport + Z_loss + Z_carbon

其中：

- **Z_fixed** = Σ_{j∈J} Σ_{t∈T} Σ_{c∈C_t} z_{j,t,c} · f_{tc} · 10000  (建设成本，万元→元)
- **Z_operate** = Σ_{j∈J} Σ_{t∈T} Σ_{c∈C_t} z_{j,t,c} · o_{tc} · 10000  (运营成本，万元→元)
- **Z_transport** = Σ_{i∈I} Σ_{j∈J} Σ_{t∈T} x_{i,j,t} · d_i · dist_{ij} · c_trans  (运输成本)
- **Z_loss** = Σ_{i∈I} Σ_{j∈J} Σ_{t∈T} x_{i,j,t} · d_i · (t_{ij} · α_transport + α_storage_t) · c_loss  (损耗成本)
- **Z_carbon** = Σ_{i∈I} Σ_{j∈J} Σ_{t∈T} x_{i,j,t} · d_i · (e_t · γ_t / 1000 · c_carbon + dist_{ij} · ε_transport / 1000 · c_carbon)  (碳排放成本)

#### 约束条件

**C1. 分配约束**：每个需求点恰好分配到一个冷库
```
Σ_{j∈J} Σ_{t∈T} x_{i,j,t} = 1  ∀i∈I
```

**C2. 开放约束**：只能分配到已建冷库
```
x_{i,j,t} ≤ Σ_{c∈C_t} z_{j,t,c}  ∀i∈I, j∈J, t∈T
```

**C3. 唯一设施约束**：每个候选点最多建一个冷库
```
Σ_{t∈T} Σ_{c∈C_t} z_{j,t,c} ≤ 1  ∀j∈J
```

**C4. 最大设施数约束**：
```
Σ_{j∈J} Σ_{t∈T} Σ_{c∈C_t} z_{j,t,c} ≤ N_max
```

**C5. 预冷时间约束**（大M法）：
```
t_{ij} · x_{i,j,precool} ≤ τ · x_{i,j,precool} + M · (1 - x_{i,j,precool})  ∀i∈I, j∈J
```
其中 M = 20（大于最大运输时间）

**C6. 容量约束**：
```
Σ_{i∈I} x_{i,j,t} · d_i ≤ Σ_{c∈C_t} z_{j,t,c} · cap_{tc}  ∀j∈J, t∈T
```

### 3.2 未来扩展：双层多目标模型

#### 上层（领导者/政府决策）

- 决策：选址 {z_{j,t,c}} + 类型选择 + 容量等级
- 目标：min 建设成本 + 碳排放（社会效益）
- 约束：C3, C4, C5

#### 下层（跟随者/运营方决策）

- 决策：分配 {x_{i,j,t}}
- 目标：min 运营成本 + 运输成本 + 损耗（经济效益）
- 约束：C1, C2, C6
- **关键**：下层是凸LP（x是连续变量时），KKT条件可线性化

#### 双层→单层转化（KKT）

下层LP的KKT条件：
1. 稳定性条件
2. 原始可行性
3. 对偶可行性
4. 互补松弛条件（用大M法线性化）

→ 转化为单层MILP，可用Gurobi直接求解

### 3.3 AI增强模块（创新点6+7的数学描述）

#### 3.3.1 创新点6：数据驱动损耗参数学习（SPO Pipeline）

**问题**：传统模型用固定参数 α=0.8, β=0.15，但实际损耗率随产地、季节、温度链变化

**SPO框架**：
1. **数据层**：历史产量{i, t, season} + 气象数据 + 运输记录 → 特征矩阵 X
2. **预测层**：ML模型(XGBoost/LightGBM)学习损耗参数
   ```
   α(i,t,season) = ML_α(X_i, X_t, X_season)  # 基础损耗率
   β(i,t,season) = ML_β(X_i, X_t, X_season)  # 时间加速因子
   ```
3. **优化层**：将学习到的参数输入MIP模型
   ```
   Z_loss = Σ x_{i,j,t} · d_i · (α(i,t,season) · e^{β(i,t,season)·t_{ij}} - 1) · c_loss
   ```
4. **决策质量**：用SPO loss而非MSE loss训练，确保预测误差对最终决策影响最小

**实现要点**：
- 数据不足时：用文献参数作为先验，ML输出作为后验修正
- 特征工程：温度、湿度、运输距离、存储时长、冷库类型
- 模型选择：LightGBM(结构化数据) > 神经网络(小数据量)
- SPO Loss：直接优化决策质量，而非单纯预测精度

#### 3.3.2 创新点7：AI增强Benders分解（GNN+RL）

**Benders分解回顾**：
- 主问题(MP)：固定x，求解z（选址）
- 子问题(SP)：固定z，求解x（分配）→ 生成Benders cut
- 经典问题：cut爆炸→主问题膨胀→收敛慢

**AI增强方案**：

**Step 1：GNN编码问题结构**
```
二分图 G = (J ∪ I, E)
- 节点特征：候选点(位置/容量/成本)，需求点(产量/距离)
- 边特征：距离、运输时间、损耗率
- GNN输出：每个候选Benders cut的嵌入表示 h_cut
```

**Step 2：RL学习cut选择策略**
```
- 状态 s_t：当前主问题(MP)的LP松弛解 + 已选cut集合
- 动作 a_t：从候选cut中选择一个加入MP
- 奖励 r_t：MP目标函数改善量 / 迭代收敛速度
- 策略 π(a|s)：DQN或PPO学习
```

**Step 3：联合训练与推理**
```
1. 训练：在多个问题实例上训练GNN+RL
2. 推理：新问题→GNN编码→RL选择cut→加速Benders收敛
```

**实现要点**：
- GNN：GraphSAGE或GAT（我们已有学习基础）
- RL：DQN（离散动作空间=选哪个cut）或PPO
- 训练数据：用lrp-instances benchmark生成训练集
- Baseline对比：经典Benders(全cut) vs 随机选cut vs AI选cut

### 3.4 多目标扩展

三目标：f1=成本, f2=损耗, f3=碳排放

- **主方法**：Augmented ε-约束法
  - 选一个主目标(成本)最小化
  - 其余目标加约束：f2 ≤ ε2, f3 ≤ ε3
  - 变化 ε2, ε3 生成帕累托前沿面
- **对比方法**：NSGA-III（元启发式对比）
- **可视化**：3D帕累托前沿面 + 平行坐标图 + Trade-off分析

---

## 四、实现要求

### 4.1 当前最紧急任务：修复基线模型

#### ⚠️ 核心问题：Gurobi许可证

**现象**：gurobipy 使用的是 PIP 免费许可证（2000变量限制），而非 NODE 正版许可证（无限制）

**根因**：pip 安装的 gurobipy 自带 `gurobi.lic`（PIP类型，2000变量限制），位于：
```
C:\Python314\Lib\site-packages\gurobipy\gurobi.lic  (TYPE=PIP, 限制2000变量)
```

而正版 NODE 许可证位于：
```
D:\Gurobi1300\win64\bin\gurobi.lic  (TYPE=NODE, 256核, 无限制, 到期2056年)
```

**解决方案**：在代码开头强制设置环境变量：
```python
import os
os.environ['GRB_LICENSE_FILE'] = r'D:\Gurobi1300\win64\bin\gurobi.lic'
import gurobipy as gp  # 必须在设置环境变量之后import
```

**验证方法**：
```python
import os
os.environ['GRB_LICENSE_FILE'] = r'D:\Gurobi1300\win64\bin\gurobi.lic'
import gurobipy as gp

m = gp.Model()
x = m.addVars(2001, name='x')
m.setObjective(x.sum())
m.optimize()
print(f"Variables: {m.NumVars}")  # 应输出 2001，无报错
```

**关键**：`os.environ` 设置必须在 `import gurobipy` 之前，或者至少在创建 `gp.Model()` 之前。如果已 import 过 gurobipy 且用了 PIP 许可证，需要重启 Python 进程。

#### 📝 需要实现的基线模型 v2.1

**文件**：`src/models/single_level_mip_v2_1.py`（已写但许可证问题未解决）

**核心改进（相比v1）**：

| 项目 | v1（已完成） | v2.1（需要修复运行） |
|------|-------------|-------------------|
| 候选点 | 9个（乡镇+县级，缩减版） | 27个（全部候选点） |
| 容量选择 | 用平均值近似 | 显式容量等级变量 z[j,t,c] |
| 运营成本 | 未加入 | 已加入目标函数 |
| 变量数 | ~1440 | ~4671 |
| 许可证 | PIP免费版(2000限制) | NODE版(无限制) |

**预期结果**：
- 总成本应比v1（2,688,202元）更优，因为候选点更多、搜索空间更大
- 应该能看到村级预冷库的选址（v1无法看到因为候选点被缩减了）
- 容量利用率应更合理（显式选择而非平均值）

### 4.2 后续实现路线图

#### Week 1 剩余 (Day 3-7)

| 优先级 | 任务 | 文件 | 说明 |
|--------|------|------|------|
| P0 | 基线模型v2.1修复运行 | `single_level_mip_v2_1.py` | 解决Gurobi许可证问题后跑通 |
| P1 | 多场景对比实验 | `run_scenarios.py` | S1(9点)/S2(18点)/S3(27点)对比 |
| P1 | 灵敏度分析 | `sensitivity.py` | 碳价/损耗单价/预冷时间变化 |
| P2 | 双层MIP形式化 | `bilevel_mip.py` | 上层z + 下层x，KKT转化 |
| P2 | KKT转化实现 | `kkt_transform.py` | 互补松弛→大M线性化 |

### 4.3 AI模块实现路线图（Week 2-3）

#### 创新点6：数据驱动损耗参数学习

| 步骤 | 任务 | 文件 | 说明 |
|------|------|------|------|
| 1 | 合成数据生成 | `src/data_driven/synthetic_data.py` | 基于文献参数+随机扰动生成模拟历史数据 |
| 2 | 特征工程 | `src/data_driven/feature_extractor.py` | 提取产地/季节/温度/距离等特征 |
| 3 | ML模型训练 | `src/data_driven/loss_param_learner.py` | LightGBM/XGBoost学习α,β |
| 4 | SPO Loss实现 | `src/data_driven/spo_loss.py` | Smart Predict-then-Optimize损失函数 |
| 5 | 端到端Pipeline | `src/data_driven/spo_pipeline.py` | 数据→训练→预测→优化全流程 |
| 6 | 对比实验 | `experiments/spo_comparison.py` | 固定参数 vs ML参数 vs SPO参数 |

**合成数据策略**（无真实历史数据时的权宜之计）：
```python
# 基于文献参数生成训练数据
for i in demand_points:
    for season in ['spring', 'summer', 'fall']:
        alpha = base_alpha * (1 + noise * np.random.randn())  # 扰动
        beta = base_beta * (1 + noise * np.random.randn())
        features = extract_features(i, season, temperature, humidity)
        label = (alpha, beta)
        # 存入训练集
```

#### 创新点7：AI增强Benders分解

| 步骤 | 任务 | 文件 | 说明 |
|------|------|------|------|
| 1 | 问题实例生成 | `src/data_driven/instance_generator.py` | 用lrp-instances生成训练/测试集 |
| 2 | 二分图构建 | `src/data_driven/graph_builder.py` | 候选点-需求点二分图→GNN输入 |
| 3 | GNN编码器 | `src/algorithms/gnn_encoder.py` | GraphSAGE/GAT编码问题结构 |
| 4 | RL智能体 | `src/algorithms/rl_agent.py` | DQN学习cut选择策略 |
| 5 | AI-Benders联合 | `src/algorithms/benders_ai.py` | GNN+RL+Benders集成 |
| 6 | 对比实验 | `experiments/benders_comparison.py` | 经典Benders vs 随机选cut vs AI选cut |

**技术选型**：
- GNN：PyTorch Geometric (PyG)
- RL：Stable-Baselines3 或 cleanrl
- 训练：先小规模(20节点)验证，再扩展(100+节点)

### 4.4 物流系统集成方案（创新点5）

#### 系统架构

```
┌─────────────────────────────────────────────────────────┐
│                    秋葵冷链优化系统                        │
├──────────────┬──────────────┬────────────────────────────┤
│  冷库布局优化  │  物流路径规划  │      实时运营调度           │
│  (本项目核心)  │  (已有系统)   │    (应用开发目标)           │
├──────────────┼──────────────┼────────────────────────────┤
│ 选址+类型+容量 │ VRP/CVRP/    │  订单管理+车辆调度          │
│ 双层MIP+KKT   │ VRPTW/PDP    │  温度监控+异常报警          │
│ Benders+AI   │ OR-Tools/    │  路径优化+实时重规划         │
│ 帕累托前沿    │ Gurobi       │  数据看板+决策支持           │
├──────────────┴──────────────┴────────────────────────────┤
│                   FastAPI 后端服务层                      │
├──────────────────────────────────────────────────────────┤
│              PostgreSQL + Redis + MinIO 数据层             │
├──────────────────────────────────────────────────────────┤
│           微信小程序 / APP / Web 前端展示层                 │
└──────────────────────────────────────────────────────────┘
```

#### 与已有物流系统的集成接口

**已有物流系统**：`D:\物流路径规划系统项目\`
- 在线演示：https://logistics-demo-yu.top
- 登录：admin / admin123
- 技术栈：Spring Boot + Vue.js + OR-Tools
- 已有功能：VRP/CVRP路径规划、地图可视化、订单管理

**集成方式**：API级集成（非代码合并）

| 接口 | 方向 | 数据格式 | 说明 |
|------|------|----------|------|
| `/api/cold-storage/layout` | 冷库→物流 | JSON | 冷库选址+容量结果推送到物流系统 |
| `/api/cold-storage/capacity` | 物流→冷库 | JSON | 物流系统查询冷库实时容量 |
| `/api/routing/solve` | 冷库→物流 | JSON | 基于冷库布局触发路径规划 |
| `/api/routing/result` | 物流→冷库 | JSON | 路径规划结果回传 |
| `/api/monitor/temperature` | 双向 | JSON | 温度监控数据共享 |
| `/api/carbon/report` | 冷库→应用 | JSON | 碳排放报告生成 |

#### 集成实现步骤

1. **冷库布局结果导出**：优化结果→JSON(冷库位置/类型/容量/分配方案)
2. **物流系统接收**：读取JSON→创建冷库节点→触发VRP求解
3. **路径优化联动**：冷库→需求点的配送路径自动规划
4. **实时数据回传**：路径执行结果→损耗/碳排放实际值→反馈到参数学习

### 4.5 应用开发方案（微信小程序/APP）

#### 应用定位

**"秋葵冷链管家"** — 连接农户、冷库运营方、物流配送的实用工具

#### 核心功能模块

| 模块 | 功能 | 用户 | 技术实现 |
|------|------|------|----------|
| 🏠 首页看板 | 冷库容量/温度/订单概览 | 运营方 | ECharts可视化 |
| 📍 冷库地图 | 冷库位置/类型/空余容量 地图展示 | 所有 | 腾讯地图API + 自定义Marker |
| 📦 订单管理 | 秋葵入库/出库/调拨 | 运营方 | CRUD + 状态机 |
| 🚚 配送追踪 | 冷链车辆位置/温度实时追踪 | 物流方 | WebSocket + GPS |
| 🌡️ 温度监控 | 各冷库/车辆温度曲线+异常报警 | 运营方 | IoT数据 + 阈值报警 |
| 📊 优化建议 | AI推荐最佳冷库+配送路线 | 所有 | 调用后端优化API |
| 🌱 碳排放报告 | 月度/年度碳排放统计+减排建议 | 政府/企业 | 报表生成 |
| 📈 数据分析 | 产量趋势/损耗分析/成本分析 | 政府/企业 | ML预测+可视化 |

#### 技术栈选择

| 层 | 技术选型 | 理由 |
|----|----------|------|
| **小程序前端** | 微信小程序(Taro/uni-app) | 用户量大、无需下载、支持地图/支付 |
| **APP前端(可选)** | Flutter | 跨平台、性能好、IoT功能丰富 |
| **Web管理后台** | React + Ant Design Pro | 复杂数据表格+图表+管理功能 |
| **后端API** | FastAPI(Python) | 直接调用优化模型、异步高性能 |
| **数据库** | PostgreSQL + Redis | 关系数据+缓存 |
| **对象存储** | MinIO | 文件/图片/报告存储 |
| **消息队列** | RabbitMQ/Redis Stream | IoT数据+异步任务 |
| **地图服务** | 腾讯地图API | 小程序原生支持 |
| **IoT接入** | MQTT Broker | 温度传感器数据接入 |
| **部署** | Docker + Nginx | 已有云服务器(122.152.220.116) |

#### 应用开发优先级

| 阶段 | 时间 | 内容 | 优先级 |
|------|------|------|--------|
| V1.0 MVP | Week 3-4 | 冷库地图+优化结果展示+基础看板 | P1 |
| V1.5 | 论文投稿后 | 订单管理+温度监控+配送追踪 | P2 |
| V2.0 | 后续 | 完整小程序+IoT+AI推荐 | P3 |

#### MVP 功能清单（V1.0，论文期间可展示）

```
1. 冷库优化结果地图展示（位置+类型+容量+利用率）
2. 帕累托前沿交互式探索（滑块调碳价/损耗权重）
3. 成本结构饼图+碳排放统计
4. 分配方案详情（哪个村的秋葵去哪个冷库）
5. 与物流系统的路径规划联动展示
```

#### API 接口设计（供前端调用）

```python
# === 冷库优化相关 API ===
POST /api/v1/optimize/layout      # 运行冷库布局优化
GET  /api/v1/optimize/result/{id}  # 获取优化结果
GET  /api/v1/optimize/pareto/{id}  # 获取帕累托前沿

# === 冷库信息 API ===
GET  /api/v1/storages              # 冷库列表(位置/类型/容量/利用率)
GET  /api/v1/storages/{id}/detail   # 冷库详情
GET  /api/v1/storages/map          # 地图数据(GeoJSON)

# === 物流集成 API ===
POST /api/v1/routing/solve        # 触发路径规划
GET  /api/v1/routing/result/{id}  # 路径结果

# === 数据分析 API ===
GET  /api/v1/analysis/carbon      # 碳排放报告
GET  /api/v1/analysis/loss         # 损耗分析
GET  /api/v1/analysis/sensitivity   # 灵敏度分析结果
```

---

## 五、环境配置

### 5.1 Python 环境（⚠️ 重要决策）

#### 方案对比

| 方案 | 优点 | 缺点 | 推荐度 |
|------|------|------|--------|
| **A. 新建专用venv（推荐 ✅）** | 环境隔离、依赖精确控制、避免与数据分析平台冲突 | 需要重新安装包 | ⭐⭐⭐ |
| B. 复用数据分析平台venv | 已有pyomo/gurobipy/sklearn | 环境耦合、版本冲突风险 | ⭐⭐ |
| C. 复用GenericAgent venv311 | 已有深度学习包 | 环境不匹配 | ⭐ |

#### 推荐方案：新建专用虚拟环境

```powershell
# 1. 创建虚拟环境
python -m venv D:\秋葵冷库优化项目\venv

# 2. 激活
& "D:\秋葵冷库优化项目\venv\Scripts\Activate.ps1"

# 3. 安装核心依赖
pip install pyomo==6.10.0
pip install gurobipy==13.0.1
pip install pandas numpy scipy
pip install matplotlib plotly seaborn
pip install scikit-learn xgboost lightgbm

# 4. AI模块依赖（Week 2安装）
pip install torch torchvision  # PyTorch
pip install torch-geometric    # GNN (PyG)
pip install stable-baselines3  # RL
pip install gymnasium          # RL环境

# 5. 应用开发依赖（Week 3安装）
pip install fastapi uvicorn
pip install sqlalchemy psycopg2-binary redis
pip install python-multipart aiofiles
pip install minio               # 对象存储
pip install paho-mqtt           # IoT/MQTT

# 6. 验证
python -c "import pyomo; import gurobipy; import sklearn; print('All OK')"
```

#### 临时方案（如果不想新建venv）

继续用数据分析平台的venv，但要注意：
- 运行命令：`& "D:\智能数据分析平台\backend\venv\Scripts\python.exe"`
- 该环境已有 pyomo/gurobipy/sklearn/xgboost/lightgbm
- 缺少 torch/pyg/sb3（AI模块用，Week 2再装）

#### Gurobi 许可证配置（⚠️ 关键！）

**无论用哪个venv，都必须解决许可证问题！**

**NODE许可证**（无限制）：
```
文件: D:\Gurobi1300\win64\bin\gurobi.lic
类型: TYPE=NODE | CORES=256 | 到期: 2056-05-22
```

**解决步骤（按优先级）**：

```python
# 方法1: 代码中设置环境变量（最优先尝试）
import os
os.environ['GRB_LICENSE_FILE'] = r'D:\Gurobi1300\win64\bin\gurobi.lic'
import gurobipy as gp

# 方法2: 如果方法1不生效，重命名PIP许可证
# PowerShell执行:
# Rename-Item "C:\Python314\Lib\site-packages\gurobipy\gurobi.lic" "gurobi.lic.bak"
# 同样检查venv中的gurobipy目录

# 方法3: 显式创建Gurobi环境
env = gp.Env()
env.setParam('LicenseFile', r'D:\Gurobi1300\win64\bin\gurobi.lic')
m = gp.Model(env=env)
```

**验证命令**：
```python
import os
os.environ['GRB_LICENSE_FILE'] = r'D:\Gurobi1300\win64\bin\gurobi.lic'
import gurobipy as gp
m = gp.Model('test')
x = m.addVars(2001, name='x')
m.setObjective(x.sum())
m.optimize()
print(f'Variables: {m.NumVars}')  # 应输出2001无报错
```

### 5.2 已安装关键包（数据分析平台venv）

| 包 | 版本 | 用途 |
|----|------|------|
| pyomo | 6.10.0 | MIP建模框架 |
| gurobipy | 13.0.1 | Gurobi求解器 |
| pandas | 3.0.2 | 数据处理 |
| numpy | 2.4.4 | 数值计算 |
| scipy | 1.17.1 | 科学计算 |
| matplotlib | 3.10.8 | 绑图 |
| plotly | 6.7.0 | 交互式可视化 |
| scikit-learn | 1.8.0 | 机器学习(AI4OPT用) |
| xgboost | 3.2.0 | 梯度提升(创新点6用) |
| lightgbm | 4.6.0 | 梯度提升(创新点6用) |

### 5.3 待安装包（按阶段）

| 阶段 | 包 | 用途 |
|------|-----|------|
| Week 2(AI模块) | torch, torch-geometric | GNN(创新点7) |
| Week 2(AI模块) | stable-baselines3, gymnasium | RL(创新点7) |
| Week 3(应用) | fastapi, uvicorn | 后端API |
| Week 3(应用) | sqlalchemy, psycopg2-binary | 数据库 |
| Week 3(应用) | minio, paho-mqtt | 存储+IoT |

### 5.4 运行命令

```powershell
# 方案A: 新建venv（推荐）
& "D:\秋葵冷库优化项目\venv\Scripts\Activate.ps1"
Set-Location "D:\秋葵冷库优化项目"
python src\models\single_level_mip_v2_1.py

# 方案B: 用数据分析平台venv（临时）
Set-Location "D:\秋葵冷库优化项目"
& "D:\智能数据分析平台\backend\venv\Scripts\python.exe" src\models\single_level_mip_v2_1.py
```

---

## 六、已有代码说明

### 6.1 已有文件

| 文件 | 说明 | 状态 |
|------|------|------|
| `src/models/single_level_mip.py` | v1基线模型(Pyomo+Gurobi，9候选点，平均值容量) | ✅ 可运行，结果已保存 |
| `src/models/single_level_mip_v2.py` | v2模型(Pyomo，显式容量等级，全部27候选点) | ❌ Pyomo Param不可变错误(已修复) + 许可证问题 |
| `src/models/single_level_mip_v2_1.py` | v2.1模型(gurobipy直接API，绕过Pyomo) | ❌ 许可证问题未解决 |
| `src/utils/data_loader.py` | 数据加载工具 | 未知状态 |
| `results/baseline_s1_result.pkl` | v1基线模型结果 | ✅ |

### 6.2 v1基线模型结果（已验证）

| 指标 | 值 |
|------|-----|
| 总成本 | 2,688,202 元 |
| 建设成本 | 2,550,000 元 (94.8%) |
| 运输成本 | 14,320 元 (0.5%) |
| 损耗成本 | 123,773 元 (4.6%) |
| 碳排放成本 | 109 元 (0.01%) |
| 选址方案 | C1(冷藏库) + T5(冷藏库) + T8(冷藏库) |
| 分配需求 | 197.9吨 + 198.2吨 + 192.0吨 |
| 求解时间 | 0.2秒 |
| Gap | 0.9% |
| 预冷时间约束 | 全部满足 ✅ |

**v1的不足**：
1. 只有9个候选点（乡镇+县级），遗漏了18个村级候选点
2. 容量选择用了平均值，不精确
3. 未计入运营成本
4. 所有冷库都选了冷藏库(cold)类型，没有预冷库、气调库、冷冻库的多样性

### 6.3 v2.1 需要修复的问题

**问题1：Gurobi许可证** — 最关键！

v2.1 已经用了 gurobipy 直接 API，但在 `import gurobipy` 时 Python 自带的 PIP 许可证就已经被加载了。解决方案：

```python
# 方案A：在import之前设环境变量
import os
os.environ['GRB_LICENSE_FILE'] = r'D:\Gurobi1300\win64\bin\gurobi.lic'

# 然后import
import gurobipy as gp
```

**问题2：如果方案A不生效**（因为 gurobipy 在 import 时就加载了 license）

备选方案：
- 方案B：用 `gp.Env()` 显式创建环境并传入 license 文件路径
  ```python
  env = gp.Env(params={'LogFile': 'gurobi.log'})
  env.setParam('OutputFlag', 1)
  m = gp.Model(env=env)
  ```
- 方案C：删除/重命名 PIP 许可证文件，让 gurobipy 找不到它
  ```powershell
  Rename-Item "C:\Python314\Lib\site-packages\gurobipy\gurobi.lic" "gurobi.lic.bak"
  ```
  然后设置 `GRB_LICENSE_FILE` 环境变量指向 NODE 许可证
- 方案D：在 venv 中也安装 gurobipy 并确保使用 NODE 许可证
  ```powershell
  # 先看 venv 的 gurobipy 在哪
  & "D:\智能数据分析平台\backend\venv\Scripts\python.exe" -c "import gurobipy; print(gurobipy.__file__)"
  # 检查那个目录下是否也有 gurobi.lic
  ```

**推荐**：先试方案A，不行试方案C（重命名PIP许可证），最后试方案B。

---

## 七、项目目录结构（当前+预期完整版）

```
D:\秋葵冷库优化项目\
├── PROJECT_SPEC.md                 ← 本文件（完整技术规格书）
├── README.md                        ← 项目概述
├── venv\                            ← [待创建] Python虚拟环境(推荐新建)
│
├── data\                            ← 数据集
│   ├── nodes.csv                     ← 39个节点
│   ├── distance_matrix.csv           ← 39×39距离矩阵
│   ├── transport_time_matrix.csv     ← 39×39运输时间矩阵
│   ├── params.json                   ← 保鲜参数+冷库类型参数
│   ├── nodes.xlsx                    ← Excel版
│   └── synthetic\                    ← [待创建] ML合成训练数据
│
├── src\                             ← 核心源码
│   ├── models\                      ← 数学模型
│   │   ├── single_level_mip.py            ← v1基线(Pyomo, 9点) ✅
│   │   ├── single_level_mip_v2.py         ← v2(Pyomo, 27点) ⚠️
│   │   ├── single_level_mip_v2_1.py       ← v2.1(gurobipy) ⚠️
│   │   ├── bilevel_mip.py                 ← [待实现] 双层MIP
│   │   ├── bilevel_kkt.py                 ← [待实现] KKT转化双层→单层
│   │   └── epsilon_constraint.py           ← [待实现] ε-约束法
│   │
│   ├── algorithms\                   ← 求解算法
│   │   ├── benders.py                     ← [待实现] Benders分解
│   │   ├── benders_ai.py                  ← [待实现] AI增强Benders
│   │   ├── gnn_encoder.py                 ← [待实现] GNN编码器
│   │   ├── rl_agent.py                    ← [待实现] RL智能体
│   │   └── nsga3_baseline.py              ← [待实现] NSGA-III对比
│   │
│   ├── data_driven\                 ← AI数据驱动模块
│   │   ├── synthetic_data.py              ← [待实现] 合成数据生成
│   │   ├── feature_extractor.py           ← [待实现] 特征工程
│   │   ├── loss_param_learner.py          ← [待实现] ML损耗参数学习
│   │   ├── spo_loss.py                     ← [待实现] SPO损失函数
│   │   ├── spo_pipeline.py                ← [待实现] 端到端SPO
│   │   ├── graph_builder.py               ← [待实现] 二分图构建
│   │   └── instance_generator.py          ← [待实现] 问题实例生成
│   │
│   ├── api\                         ← [待实现] FastAPI后端
│   │   ├── main.py                        ← FastAPI应用入口
│   │   ├── routes\                        ← API路由
│   │   │   ├── optimize.py                 ← 优化相关API
│   │   │   ├── storages.py                 ← 冷库信息API
│   │   │   ├── routing.py                  ← 物流集成API
│   │   │   └── analysis.py                 ← 数据分析API
│   │   ├── models\                        ← Pydantic模型
│   │   └── services\                      ← 业务逻辑层
│   │
│   └── utils\
│       └── data_loader.py                 ← 数据处理模块
│
├── app\                             ← [待实现] 前端应用
│   ├── miniprogram\                  ← 微信小程序(uni-app)
│   │   ├── pages\                         ← 页面
│   │   │   ├── index\                      ← 首页看板
│   │   │   ├── map\                        ← 冷库地图
│   │   │   ├── optimize\                   ← 优化结果
│   │   │   ├── monitor\                    ← 温度监控
│   │   │   └── report\                     ← 碳排报告
│   │   ├── components\                    ← 组件
│   │   └── utils\                         ← 工具
│   └── web\                          ← Web管理后台(React)
│
├── docs\                            ← 文献精读笔记（8+个文件）
├── lrp-instances\                   ← Benchmark数据集
├── results\                         ← 实验结果
│   ├── baseline_s1_result.pkl       ← v1结果 ✅
│   └── baseline_v2_1_result.pkl      ← [待生成] v2.1结果
│
├── experiments\                     ← [待创建] 实验脚本
│   ├── run_scenarios.py              ← 多场景对比
│   ├── sensitivity.py                ← 灵敏度分析
│   ├── spo_comparison.py             ← SPO对比实验
│   └── benders_comparison.py         ← Benders对比实验
│
└── deploy\                          ← [待创建] 部署配置
    ├── docker-compose.yml            ← Docker编排
    ├── nginx.conf                    ← Nginx配置
    └── Dockerfile                    ← 容器构建
```

---

## 八、文献参考

### 8.1 核心论文

| 论文 | 年份 | 关键贡献 | 对本项目意义 |
|------|------|---------|-------------|
| Cavagnini et al. | 2026 | EJOR LRP综述Part2，MOLRP仅5篇 | 确认研究空白 |
| Tang et al. | 2025 | 双层2E-MOLRP医疗废物，Gurobi+IALNS | 最直接竞品(全启发式 vs 我们全精确) |
| Wang et al. | 2024 | 双层2E-MOLRP农村物流，OPTICS+MSSMA | 最直接竞品(全启发式 vs 我们全精确) |
| Huang et al. | 2025 | 湖南J县秋葵冷链案例 | 案例数据来源 |
| Zhu et al. | 2023 | 双层冷链网络优化 | KKT转化方法论 |
| Fan et al. | 2026 | EJOR AI4OPT综述 | 创新点6-7理论基础 |
| Ehrgott et al. | 2026 | MOO 50年综述 | 多目标方法论 |
| Cheng et al. | 2018 | 秋葵采后参数实验 | 秋葵参数来源 |

### 8.2 精读笔记位置

```
D:\秋葵冷库优化项目\docs\
├── Cavagnini2026_LRP精读笔记.md        ← LRP综述Part2
├── Tang2025_Wang2024_对比精读.md        ← 双层MOLRP对比
├── 三篇核心论文精读笔记.md               ← Zhu2023/Huang2025/综述
├── AI4OPT精读笔记_人工智能嵌入优化.md    ← AI4OPT方法论
├── Ehrgott2026_MOO_50years_精读笔记.md  ← 多目标方法论
├── Fan2026_AI4OPT_EJOR精读笔记.md       ← AI4OPT精读
├── Huang2025_论文精读笔记.md             ← J县案例
├── 秋葵采后参数汇总.md                    ← 秋葵保鲜参数汇总
└── 文献综述_国内外研究现状.md              ← 完整文献综述
```

---

## 九、代码风格与约定

### 9.1 编码规范

- Python 3.11+
- 类型注解
- 中文注释（项目面向中文论文）
- 函数/类必须有 docstring
- 使用 `sys.stdout.reconfigure(encoding='utf-8')` 避免中文输出乱码

### 9.2 命名约定

| 类型 | 约定 | 示例 |
|------|------|------|
| 集合 | 大写字母 | J, I, T, C |
| 变量 | 小写+下划线 | z_jtc, x_ijt |
| 参数 | 小写+描述 | demand_i, dist_ij |
| 文件 | 小写+下划线 | single_level_mip_v2_1.py |
| 类 | PascalCase | DataConfig |
| 函数 | snake_case | build_and_solve_v2 |

### 9.3 输出要求

- 所有金额单位统一为 **元**（建设/运营成本从万元 ×10000 转换）
- 距离单位 **km**，时间单位 **h**，重量单位 **吨**
- 碳排放单位 **吨CO₂/年**
- 结果保存为 pkl + 控制台打印格式化表格

---

## 十一、完整实现路线图（4周 + 后续）

### Week 1 (5/26-6/1)：模型+基线+环境

| 天 | 任务 | 产出 | 负责人 |
|----|------|------|--------|
| Day1-2 | ✅ Pyomo单层MIP v1 | `single_level_mip.py` | 小彩 |
| Day2 | ✅ v2升级(显式容量+全候选点) | `single_level_mip_v2_1.py` | 小彩 |
| Day2 | ✅ 项目规格书 | `PROJECT_SPEC.md` | 小彩 |
| Day3 | 🔧 修复Gurobi许可证+跑通v2.1 | 验证结果 | CodeBuddy Code |
| Day3 | 🔧 新建venv(可选) | 独立环境 | CodeBuddy Code |
| Day4-5 | 双层MIP形式化+KKT转化 | `bilevel_mip.py` + `bilevel_kkt.py` | CodeBuddy Code |
| Day6-7 | ε-约束法多目标 | `epsilon_constraint.py` + 帕累托前沿 | CodeBuddy Code |

### Week 2 (6/2-6/8)：AI模块+算法

| 天 | 任务 | 产出 |
|----|------|------|
| Day1-2 | Benders分解 | `benders.py` |
| Day3 | 合成数据生成+特征工程 | `synthetic_data.py` + `feature_extractor.py` |
| Day4 | ⭐ ML损耗参数学习(SPO) | `loss_param_learner.py` + `spo_pipeline.py` |
| Day5-6 | ⭐ GNN编码器+RL智能体 | `gnn_encoder.py` + `rl_agent.py` |
| Day7 | ⭐ AI增强Benders集成 | `benders_ai.py` + 对比实验 |

### Week 3 (6/9-6/15)：大规模实验+集成+应用

| 天 | 任务 | 产出 |
|----|------|------|
| Day1-2 | 大规模实验(100+节点) | 扩展性分析 |
| Day3 | ⭐ AI4OPT vs 纯OR对比 | 量化AI增强效果 |
| Day4 | 灵敏度分析 | `sensitivity.py` + 图表 |
| Day5 | FastAPI后端核心 | `api/main.py` + 路由 |
| Day6-7 | MVP前端(地图+结果展示) | 小程序/Web雏形 |

### Week 4 (6/16-6/22)：论文+收尾

| 天 | 任务 | 产出 |
|----|------|------|
| Day1-3 | 论文撰写 | 完整论文初稿 |
| Day4-5 | 实验+图表完善 | 终稿质量图表 |
| Day6 | 应用Demo完善 | 可展示Demo |
| Day7 | 投稿准备 | 投稿材料 |

### 后续（论文投稿后）

| 阶段 | 内容 | 时间 |
|------|------|------|
| V1.5 | 完整小程序+订单管理+温度监控 | 2-3周 |
| V2.0 | IoT接入+实时调度+AI推荐 | 4-6周 |
| V2.5 | 更多农产品(不只是秋葵) | 按需 |
| V3.0 | 多区域扩展+商业化 | 长期 |

---

## 十二、验证清单

### 基线模型v2.1跑通验证

- [ ] Gurobi 许可证显示 NODE 类型（非 PIP）
- [ ] 4671个变量，无变量限制报错
- [ ] 总成本 < v1的2,688,202元（候选点更多应更优）
- [ ] 至少出现1个非cold类型的冷库（预冷库/气调库）
- [ ] 容量利用率 60%-95%（合理范围）
- [ ] 所有预冷时间约束满足
- [ ] 总分配需求 = 588.2吨（与总产量一致）
- [ ] 求解时间 < 60秒
- [ ] MIP Gap < 2%

### AI模块验证

- [ ] ML参数学习：预测α,β的R² > 0.7
- [ ] SPO vs 固定参数：决策成本改善 > 5%
- [ ] GNN编码：cut价值预测准确率 > 70%
- [ ] AI-Benders vs 经典Benders：收敛加速 > 30%
- [ ] NSGA-III帕累托前沿与ε-约束法一致

### 应用验证

- [ ] API响应时间 < 2秒（优化求解除外）
- [ ] 地图加载 < 3秒
- [ ] 小程序冷库地图正常显示
- [ ] 优化结果可交互探索

---

*小彩 💫 2026-05-26 | PROJECT_SPEC.md v2.0 — 含AI融合+物流集成+应用开发+环境决策 — 读完即可开始编码*
