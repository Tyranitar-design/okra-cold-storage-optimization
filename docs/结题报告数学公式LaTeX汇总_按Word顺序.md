# 结题报告数学公式 LaTeX 汇总（按 Word 正文顺序）

对应文件：`SRT项目文件/秋葵冷库优化项目结题报告_论文级方法学详版.docx`

说明：本文档严格按照 Word 正文中的章节与公式编号顺序整理。Word 中部分公式是以简写文本形式排版，例如 `sum_{i,j,t}`、`theta`、`epsilon`，这里统一转换为更规范的 LaTeX 写法。复制时建议连同 `\tag{}` 一起复制，便于与报告中的公式编号对应。

## 三、双层多目标冷库选址-定容数学模型

### 3.3 双层模型结构

#### 式(1)：上层多目标优化总式

用途：说明上层决策变量为设施选址与容量配置 `z`，目标是同时优化成本、损耗和碳排放三个目标。这里的 `x^\star(z)` 表示给定上层布局后，下层分配问题的最优响应。

```latex
\[
\begin{aligned}
\min_{\boldsymbol z}\quad
&\boldsymbol F\!\left(\boldsymbol z,\boldsymbol x^\star(\boldsymbol z)\right)
=
\left(
Z_1\!\left(\boldsymbol z,\boldsymbol x^\star\right),
Z_2\!\left(\boldsymbol z,\boldsymbol x^\star\right),
Z_3\!\left(\boldsymbol z,\boldsymbol x^\star\right)
\right).
\end{aligned}
\tag{1}
\]
```

转换说明：原文写作 `Upper: min_z F(z,x*(z)) = (...)`，论文公式中建议去掉 `Upper:`，用正文说明“上层模型”即可。

#### 式(2)：下层最优响应约束

用途：说明上层不能任意选择 `x`，而必须接受下层分配模型在给定 `z` 后的最优解。

```latex
\[
\begin{aligned}
\mathrm{s.t.}\quad
&\boldsymbol z\in\mathcal Z,\\
&\boldsymbol x^\star(\boldsymbol z)
\in
\operatorname*{arg\,min}_{\boldsymbol x\in\mathcal X(\boldsymbol z)}
\Phi(\boldsymbol z,\boldsymbol x).
\end{aligned}
\tag{2}
\]
```

转换说明：`argmin` 推荐写成 `\operatorname*{arg\,min}`，这样下标会在公式环境中显示在正下方，更像论文格式。`\in` 表示下层最优解可能不唯一。

### 3.4 上层选址-定容模型

#### 式(3)：单候选点唯一建设约束

用途：每个候选点最多只能建设一种类型、一个容量等级的冷库，避免同一地点重复建设。

```latex
\[
\sum_{t\in T}\sum_{c\in C_t} z_{jtc}\le 1,
\qquad \forall j\in J.
\tag{3}
\]
```

#### 式(4)：最大设施数量约束

用途：控制全网络建设设施总数，体现投资预算、管理复杂度或规划规模限制。

```latex
\[
\sum_{j\in J}\sum_{t\in T}\sum_{c\in C_t} z_{jtc}
\le N_{\max}.
\tag{4}
\]
```

#### 式(5)：类型开放变量与容量等级变量的关系

用途：把容量等级变量 `z_{jtc}` 聚合成类型开放变量 `y_{jt}`。后续分配约束只需要判断某地点某类型是否开放。

```latex
\[
y_{jt}=\sum_{c\in C_t}z_{jtc},
\qquad
y_{jt}\in\{0,1\},\quad z_{jtc}\in\{0,1\}.
\tag{5}
\]
```

转换说明：如果老师要求变量域单独列出，也可以把 `y,z` 的二元约束放到“变量域”公式中。

### 3.5 下层需求分配模型

#### 式(6)：通道份额平衡约束

用途：每个需求节点 `i` 在每个温度链通道 `t` 上的需求份额必须完整分配给候选设施。

```latex
\[
\sum_{j\in J}x_{ijt}=s_t,
\qquad \forall i\in I,\ t\in T.
\tag{6}
\]
```

说明：`s_t` 是通道份额，例如预冷、冷藏、气调、冷冻等服务比例。

#### 式(7)：分配-开放联动约束

用途：需求只能分配给已经开放的对应类型设施。如果 `y_{jt}=0`，则所有 `x_{ijt}` 必须为 0。

```latex
\[
0\le x_{ijt}\le y_{jt},
\qquad \forall i\in I,\ j\in J,\ t\in T.
\tag{7}
\]
```

#### 式(8)：预冷时限约束

用途：秋葵采后预冷具有强时效性，如果需求点到候选点的运输时间超过阈值 `\tau`，则该预冷分配不可发生。

```latex
\[
x_{ij,\mathrm{precool}}=0,
\qquad \text{if } \mathrm{time}_{ij}>\tau.
\tag{8}
\]
```

可选更严格写法：

```latex
\[
x_{ij,\mathrm{precool}}\le a_{ij}^{\mathrm{pre}},
\qquad
a_{ij}^{\mathrm{pre}}=
\begin{cases}
1, & \mathrm{time}_{ij}\le \tau,\\
0, & \mathrm{time}_{ij}>\tau,
\end{cases}
\qquad \forall i\in I,\ j\in J.
\]
```

转换说明：报告正文中用简写 `if time_ij > tau`。如果老师更偏好标准 MILP 形式，建议使用上面的 `a_{ij}^{pre}` 参数形式。

#### 式(9)：峰值库存容量约束

用途：这是 v3.0 容量链模型的核心。它不是简单要求“容量大于年产量”，而是把年产量通过储藏/周转天数、采收窗口和峰值因子换算成旺季峰值库存压力。

```latex
\[
\sum_{i\in I}
d_i x_{ijt}\frac{L_t}{H}\gamma
\le
\sum_{c\in C_t}\mathrm{cap}_{tc}z_{jtc},
\qquad \forall j\in J,\ t\in T.
\tag{9}
\]
```

说明：`d_i` 为需求量或产量，`L_t` 为通道 `t` 的储藏/周转天数，`H` 为采收窗口天数，`\gamma` 为峰值因子，`\mathrm{cap}_{tc}` 为类型 `t`、容量等级 `c` 的冷库容量。

### 3.6 多目标函数

#### 式(10)：总成本目标

用途：总成本目标聚合建设成本、运营成本、运输成本，以及损耗和碳排放的货币化成本，是项目主要求解目标。

```latex
\[
\min Z_1
=
\sum_{j\in J}\sum_{t\in T}\sum_{c\in C_t}
\left(f_{tc}+o_{tc}\right)z_{jtc}
+
\sum_{i\in I}\sum_{j\in J}\sum_{t\in T}
d_i\,\mathrm{dist}_{ij}\,c^{\mathrm{tr}}\,x_{ijt}
+
\lambda_L Z_2+\lambda_C Z_3.
\tag{10}
\]
```

说明：前一项是设施固定与运营成本，第二项是运输成本，后两项把损耗吨数和碳排放吨数折算成经济成本。

#### 式(11)：损耗目标

用途：刻画运输时间、设施类型和保鲜参数对秋葵采后数量损失的影响。

```latex
\[
\min Z_2
=
\sum_{i\in I}\sum_{j\in J}\sum_{t\in T}
d_i x_{ijt}
\left(
\alpha_i\,\mathrm{time}_{ij}\,m_t+\beta_t
\right).
\tag{11}
\]
```

说明：`\alpha_i` 可理解为需求节点或批次相关的时间敏感损耗系数，`m_t` 表示不同温度链类型的损耗调节因子，`\beta_t` 表示类型 `t` 的基础损耗项。

#### 式(12)：碳排放目标

用途：同时考虑冷库运行能耗排放和运输距离排放。

```latex
\[
\min Z_3
=
\sum_{i\in I}\sum_{j\in J}\sum_{t\in T}
d_i x_{ijt}
\left(
\frac{e_t}{1000}
+
\frac{\eta\,\mathrm{dist}_{ij}}{1000}
\right).
\tag{12}
\]
```

说明：`e_t` 为类型 `t` 的单位运行排放或能耗折算排放，`\eta` 为单位距离运输排放系数。除以 1000 通常用于单位换算，例如 kg 到 t。

### 3.7 完整单层容量链 MIP 形式

#### 式(13)：主求解模型目标的紧凑写法

用途：说明工程实现中可以求单目标成本模型，也可以用多目标形式生成 Pareto 前沿。

```latex
\[
\min_{\boldsymbol z,\boldsymbol x}\ Z_1(\boldsymbol z,\boldsymbol x),
\quad \text{or}\quad
\min_{\boldsymbol z,\boldsymbol x}
\left[
Z_1(\boldsymbol z,\boldsymbol x),
Z_2(\boldsymbol z,\boldsymbol x),
Z_3(\boldsymbol z,\boldsymbol x)
\right].
\tag{13}
\]
```

#### 式(14)：完整模型约束和变量域

用途：将前面式(3)-式(9)的约束统一作为主模型可行域。

```latex
\[
\mathrm{s.t.}\quad
(3)\text{--}(9),\qquad
z_{jtc}\in\{0,1\},\quad
y_{jt}\in\{0,1\},\quad
0\le x_{ijt}\le 1.
\tag{14}
\]
```

说明：式(13)-(14)是 Gurobi 直解、AI warm start、增广 epsilon 约束、NSGA-III/ALNS 共享评估器和 Optuna 调参的共同基础。

## 四、数学转化与求解方法

### 4.1 KKT 条件转化：双层模型到单层 MILP

### 4.1.1 下层 LP 与拉格朗日函数

#### 式(15)：给定上层布局后的下层 LP 目标

用途：把下层需求分配问题抽象为线性规划，`\boldsymbol c` 是单位分配成本向量。

```latex
\[
\mathrm{LL}(\boldsymbol z):\quad
\min_{\boldsymbol x}\ \boldsymbol c^\top\boldsymbol x.
\tag{15}
\]
```

#### 式(16)：下层 LP 约束矩阵形式

用途：用矩阵形式统一表示需求平衡、开放设施联动、容量和时限等约束。

```latex
\[
\mathrm{s.t.}\quad
A\boldsymbol x=\boldsymbol b,\qquad
G\boldsymbol x\le \boldsymbol h(\boldsymbol z),\qquad
\boldsymbol x\ge \boldsymbol 0.
\tag{16}
\]
```

说明：`A\boldsymbol x=\boldsymbol b` 通常对应式(6)的需求平衡；`G\boldsymbol x\le h(z)` 对应开放设施、容量和时限等由 `z` 决定的约束。

#### 式(17)：拉格朗日函数

用途：为下层 LP 引入对偶变量，准备写 KKT 条件。

```latex
\[
\mathcal L(\boldsymbol x,\boldsymbol u,\boldsymbol v,\boldsymbol\pi\mid\boldsymbol z)
=
\boldsymbol c^\top\boldsymbol x
+
\boldsymbol u^\top(A\boldsymbol x-\boldsymbol b)
+
\boldsymbol v^\top(G\boldsymbol x-\boldsymbol h(\boldsymbol z))
-
\boldsymbol\pi^\top\boldsymbol x.
\tag{17}
\]
```

说明：`\boldsymbol u` 对应等式约束，可取自由符号；`\boldsymbol v\ge 0` 对应一般不等式约束；`\boldsymbol\pi\ge0` 对应非负变量约束。

### 4.1.2 KKT 条件系统

#### 式(18)：原始可行性

用途：要求下层分配变量满足原下层 LP 的全部约束。

```latex
\[
A\boldsymbol x^\star=\boldsymbol b,\qquad
G\boldsymbol x^\star\le \boldsymbol h(\boldsymbol z),\qquad
\boldsymbol x^\star\ge \boldsymbol 0.
\tag{18}
\]
```

#### 式(19)：对偶可行性

用途：要求不等式约束和非负约束对应的对偶变量满足非负性。

```latex
\[
\boldsymbol v^\star\ge \boldsymbol 0,\qquad
\boldsymbol\pi^\star\ge \boldsymbol 0.
\tag{19}
\]
```

#### 式(20)：驻点条件

用途：由拉格朗日函数对 `x` 求一阶导数并令其为 0 得到，表示最优点处目标梯度与约束梯度平衡。

```latex
\[
\boldsymbol c
+A^\top\boldsymbol u^\star
+G^\top\boldsymbol v^\star
-\boldsymbol\pi^\star
=\boldsymbol 0.
\tag{20}
\]
```

#### 式(21)：互补松弛条件

用途：表示不等式约束的松弛量与对应对偶变量不能同时为正。

```latex
\[
v_\ell^\star
\left[
h_\ell(\boldsymbol z)-G_\ell\boldsymbol x^\star
\right]=0,\qquad
\pi_k^\star x_k^\star=0.
\tag{21}
\]
```

说明：这一步是 KKT 单层化里最容易弄错的地方。互补松弛是乘积等于 0，因此本身不是线性的，需要后续大 `M` 线性化。

### 4.1.3 大 M 线性化与单层 MILP

#### 式(22)：一般互补关系的大 M 线性化

用途：把 `a b=0`、`a\ge0`、`b\ge0` 转换成线性约束。

```latex
\[
0\le a\le Mr,\qquad
0\le b\le M(1-r),\qquad
r\in\{0,1\}.
\tag{22}
\]
```

说明：当 `r=0` 时，`a=0`；当 `r=1` 时，`b=0`，从而实现二者不能同时为正。

#### 式(23)：非负变量与其对偶变量的互补线性化

用途：处理 `\pi_k x_k=0`。

```latex
\[
0\le x_k\le M b_k^x,\qquad
0\le \pi_k\le M(1-b_k^x),\qquad
b_k^x\in\{0,1\}.
\tag{23}
\]
```

#### 式(24)：容量/开放等不等式约束的互补线性化

用途：处理一般不等式松弛量与对应对偶变量的互补关系。

```latex
\[
0\le h_\ell(\boldsymbol z)-G_\ell\boldsymbol x
\le M b_\ell^{\mathrm{cap}},\qquad
0\le v_\ell
\le M(1-b_\ell^{\mathrm{cap}}),\qquad
b_\ell^{\mathrm{cap}}\in\{0,1\}.
\tag{24}
\]
```

说明：式(22)-(24)合并上层约束、下层原始可行性、对偶可行性和驻点条件后，即得到单层 MILP。

### 4.2 增广 epsilon 约束：多目标到单目标序列求解

#### 式(25)：增广 epsilon 约束的主目标

用途：以成本 `Z_1` 为主目标，同时加入尺度化松弛惩罚，降低弱 Pareto 解风险。

```latex
\[
\min_{\boldsymbol z,\boldsymbol x,s_2,s_3}
Z_1(\boldsymbol z,\boldsymbol x)
+
\rho\left(
\frac{s_2}{R_2}
+
\frac{s_3}{R_3}
\right).
\tag{25}
\]
```

说明：`\rho` 是很小的正数，`R_2,R_3` 是损耗和碳排放目标的尺度范围。

#### 式(26)：损耗和碳排放的 epsilon 约束

用途：把另外两个目标转化为阈值约束，通过不同阈值组合扫描 Pareto 前沿。

```latex
\[
Z_2(\boldsymbol z,\boldsymbol x)
\le \varepsilon_2^k+s_2,\qquad
Z_3(\boldsymbol z,\boldsymbol x)
\le \varepsilon_3^k+s_3.
\tag{26}
\]
```

#### 式(27)：松弛变量与可行域

用途：声明松弛变量非负，并保留原模型可行域。

```latex
\[
s_2\ge0,\qquad s_3\ge0,\qquad
(\boldsymbol z,\boldsymbol x)\in\mathcal X,\qquad
k\in\mathcal K.
\tag{27}
\]
```

转换说明：原文写 `x in X`。如果保持与前文一致，建议写成 `(\boldsymbol z,\boldsymbol x)\in\mathcal X` 或 `\boldsymbol z\in\mathcal Z,\boldsymbol x\in\mathcal X(\boldsymbol z)`。

### 4.3 Gurobi 直解与 AI warm start

#### 式(28)：候选点开放概率预测

用途：AI 模型只预测候选点开放概率或排序分数，不直接给最终优化解。

```latex
\[
p_j
=
\Pr\!\left(y_j=1\mid \boldsymbol\psi_j;\Theta_{\mathrm{XGB}}\right),
\qquad j\in J.
\tag{28}
\]
```

说明：`\boldsymbol\psi_j` 是候选点 `j` 的结构特征向量，例如产量覆盖、距离、中心性、经纬度等；`\Theta_{\mathrm{XGB}}` 为 XGBoost 模型参数。

#### 式(29)：Top-K 候选点构造 MIP Start

用途：把 AI 预测概率最高的候选点转化为 Gurobi 初始解。

```latex
\[
S_K=\operatorname*{TopK}_{j\in J}(p_j),
\qquad
z_{jtc}^{\mathrm{Start}}=
\begin{cases}
1, & (j,t,c)\in\mathcal W(S_K),\\
0, & \text{otherwise}.
\end{cases}
\tag{29}
\]
```

说明：`\mathcal W(S_K)` 表示由 Top-K 站点进一步匹配类型和容量等级后得到的 warm-start 设施集合。Gurobi 后续仍负责可行性修复和最优性认证。

### 4.4 Benders 分解与 AI cut 管理

#### 式(30)：Benders 主问题

用途：主问题保留上层设施变量，并用 `\theta` 表示子问题运营价值函数的下界。

```latex
\[
\begin{aligned}
\mathrm{Master}:\quad
\min_{\boldsymbol z,\theta}\quad
& f(\boldsymbol z)+\theta\\
\mathrm{s.t.}\quad
& \boldsymbol z\in\mathcal Z,\\
& \theta\ge \mathrm{cuts}(\boldsymbol z).
\end{aligned}
\tag{30}
\]
```

更展开的 cut 集合写法：

```latex
\[
\theta\ge \alpha^r+(\boldsymbol\beta^r)^\top\boldsymbol z,
\qquad r\in\mathcal C.
\]
```

#### 式(31)：给定布局后的 Benders 子问题

用途：固定主问题给出的设施布局 `\bar z` 后，求解连续分配/运输评估问题。

```latex
\[
Q(\bar{\boldsymbol z})
=
\min_{\boldsymbol x}
\left\{
\boldsymbol q^\top\boldsymbol x
\ \middle|\
A\boldsymbol x=\boldsymbol b,\quad
G\boldsymbol x\le \boldsymbol h(\bar{\boldsymbol z}),\quad
\boldsymbol x\ge\boldsymbol0
\right\}.
\tag{31}
\]
```

#### 式(32)：Benders cut

用途：由子问题对偶信息生成可行性 cut 或最优性 cut，用来逐步收紧主问题。

```latex
\[
\theta
\ge
\alpha^r+(\boldsymbol\beta^r)^\top\boldsymbol z.
\tag{32}
\]
```

说明：`\alpha^r` 是 cut 的常数项，`\boldsymbol\beta^r` 是与设施变量相关的系数向量。

#### 式(33)：AI cut 评分函数

用途：对候选 cut 进行可解释排序，优先保留预计贡献较高的 cut。

```latex
\[
\mathrm{score}(c)
=
0.40\,\mathrm{rhs}(c)
+0.25\,\|\boldsymbol\beta_c\|_1
+0.20\,\mathrm{gap\_pct}(c)
+0.15\,\mathrm{compactness}(c).
\tag{33}
\]
```

可补充紧凑度定义：

```latex
\[
\mathrm{compactness}(c)
=
\frac{1}{1+\mathrm{nnz}(\boldsymbol\beta_c)}.
\]
```

说明：这条公式只用于 cut ranking / active cut 管理，不表示 AI 改写了原优化模型，也不能写成 AI 直接保证收敛或全局加速。

### 4.5 NSGA-III 与 ALNS 元启发式基线

正文这一节没有编号公式，主要是算法机制描述。若需要在论文中补数学表达，可以用下面两条作为补充，但它们不对应 Word 中的原编号公式：

```latex
\[
\tilde Z_m(\boldsymbol s)
=
\frac{Z_m(\boldsymbol s)-Z_m^{\min}}
{Z_m^{\max}-Z_m^{\min}+\epsilon},
\qquad m=1,2,3.
\]
```

```latex
\[
\boldsymbol s'
=
R_\ell\!\left(D_k(\boldsymbol s)\right),
\qquad
D_k\in\mathcal D,\quad R_\ell\in\mathcal R_{\mathrm{repair}}.
\]
```

### 4.6 Optuna 调参增强

#### 式(34)：Optuna 调参目标

用途：在超参数空间中寻找更短运行时间，同时要求目标值不劣化、gap 满足限制。

```latex
\[
\boldsymbol h^\star
=
\operatorname*{arg\,min}_{\boldsymbol h\in\mathcal H}
\mathrm{runtime}(\boldsymbol h)
\quad
\mathrm{s.t.}\quad
\mathrm{objective}(\boldsymbol h)
\le
\mathrm{objective}_{\mathrm{base}}+\delta,\qquad
\mathrm{gap}(\boldsymbol h)\le \mathrm{gap}_{\mathrm{limit}}.
\tag{34}
\]
```

说明：`\boldsymbol h` 表示待搜索的超参数组合，包括 XGBoost 参数、Top-K/warm-start 策略和部分 Gurobi 参数。该公式的重点是“加速不能以目标劣化和 gap 失控为代价”。

## 五、实验结果、成功说明与证据化成果

正文第五章没有新的编号公式，主要由图表和证据编号组成。如果需要把表格指标转换成公式，可选用：

```latex
\[
\mathrm{Speedup}
=
\frac{T_{\mathrm{cold}}}{T_{\mathrm{warm}}}.
\]
```

```latex
\[
\mathrm{CostDev}(m)
=
\frac{Z_1^m-Z_1^{\mathrm{exact}}}
{Z_1^{\mathrm{exact}}}\times100\%.
\]
```

```latex
\[
\mathrm{MIPGap}
=
\frac{|\mathrm{UB}-\mathrm{LB}|}{|\mathrm{UB}|+\epsilon}.
\]
```

这些是解释表格结果用的指标公式，不属于 Word 原正文的式(1)-式(34)编号序列。

## 六、MIS 管理信息系统设计说明

正文第六章主要是需求分析、系统架构、功能模块、业务流程、数据库/E-R、接口与测试说明，没有新的编号数学公式。若要补测试评价表达式，可用：

```latex
\[
\mathrm{PassRate}
=
\frac{N_{\mathrm{passed}}}{N_{\mathrm{total}}}\times100\%.
\]
```

```latex
\[
\mathrm{Availability}
=
\frac{T_{\mathrm{total}}-T_{\mathrm{down}}}{T_{\mathrm{total}}}\times100\%.
\]
```

```latex
\[
\mathrm{Latency}_{95}
=
\operatorname{Percentile}_{95}
\left(
t_{\mathrm{response}}^{(1)},t_{\mathrm{response}}^{(2)},\ldots,t_{\mathrm{response}}^{(n)}
\right).
\]
```

## 七至十章与附录

第七章微信小程序/App、第八章创新点与局限性、第九章成员分工、第十章项目总结，以及附录 A/B 主要是系统说明、代码索引和项目结构树，没有新的编号数学公式。

附录 B 的项目结构树不建议转换为数学公式；如果需要排成论文附录，可保留为等宽文本或改成树状图。

