# 结题报告数学公式 LaTeX 汇总

本文档按论文级详版结题报告的正文顺序整理数学公式与可转换表达式，便于复制到 Word 公式、MathType 或 LaTeX 环境中。

## 1. 集合、参数与变量域

```latex
\[
I=\{1,\ldots,n_I\},\quad
J=\{1,\ldots,n_J\},\quad
T=\{\mathrm{precool},\mathrm{cold},\mathrm{ca},\mathrm{frozen}\},\quad
C_t=\{1,\ldots,n_t\}.
\]
```

```latex
\[
z_{jtc}\in\{0,1\},\quad
y_{jt}=\sum_{c\in C_t}z_{jtc},\quad
x_{ijt}\in[0,1],
\qquad i\in I,\ j\in J,\ t\in T,\ c\in C_t .
\]
```

```latex
\[
a_{ij}^{\mathrm{pre}}=
\begin{cases}
1, & \mathrm{time}_{ij}\le \tau,\\
0, & \mathrm{time}_{ij}> \tau,
\end{cases}
\qquad \tau=2\ \mathrm{h}.
\]
```

## 2. 双层多目标模型总式

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
\right)\\
\mathrm{s.t.}\quad
&\boldsymbol z\in\mathcal Z,\\
&\boldsymbol x^\star(\boldsymbol z)\in
\operatorname*{arg\,min}_{\boldsymbol x\in\mathcal X(\boldsymbol z)}
\Phi(\boldsymbol z,\boldsymbol x).
\end{aligned}
\tag{1}
\]
```

```latex
\[
\mathcal Z=
\left\{
\boldsymbol z\ \middle|\
\sum_{t\in T}\sum_{c\in C_t}z_{jtc}\le 1,\ \forall j\in J;\ 
\sum_{j\in J}\sum_{t\in T}\sum_{c\in C_t}z_{jtc}\le N_{\max};\
z_{jtc}\in\{0,1\}
\right\}.
\]
```

```latex
\[
\mathcal X(\boldsymbol z)=
\left\{
\boldsymbol x\ \middle|\
\sum_{j\in J}x_{ijt}=s_t,\ \forall i,t;\
0\le x_{ijt}\le y_{jt},\ \forall i,j,t;\
x_{ij,\mathrm{precool}}\le a_{ij}^{\mathrm{pre}},\ \forall i,j;\
\sum_{i\in I}d_i x_{ijt}\frac{L_t}{H}\gamma
\le \sum_{c\in C_t}\mathrm{cap}_{tc}z_{jtc},\ \forall j,t
\right\}.
\]
```

## 3. 上层选址与容量约束

```latex
\[
\sum_{t\in T}\sum_{c\in C_t}z_{jtc}\le 1,\qquad \forall j\in J.
\tag{2}
\]
```

```latex
\[
\sum_{j\in J}\sum_{t\in T}\sum_{c\in C_t}z_{jtc}\le N_{\max}.
\tag{3}
\]
```

```latex
\[
y_{jt}=\sum_{c\in C_t}z_{jtc},\qquad
y_{jt}\in\{0,1\},\quad z_{jtc}\in\{0,1\}.
\tag{4}
\]
```

## 4. 下层分配与容量链约束

```latex
\[
\sum_{j\in J}x_{ijt}=s_t,\qquad \forall i\in I,\ t\in T.
\tag{5}
\]
```

```latex
\[
0\le x_{ijt}\le y_{jt},\qquad \forall i\in I,\ j\in J,\ t\in T.
\tag{6}
\]
```

```latex
\[
x_{ij,\mathrm{precool}}\le a_{ij}^{\mathrm{pre}},
\qquad \forall i\in I,\ j\in J.
\tag{7}
\]
```

```latex
\[
\sum_{i\in I}d_i x_{ijt}\frac{L_t}{H}\gamma
\le
\sum_{c\in C_t}\mathrm{cap}_{tc}z_{jtc},
\qquad \forall j\in J,\ t\in T.
\tag{8}
\]
```

## 5. 三目标函数

```latex
\[
\min Z_1=
\sum_{j\in J}\sum_{t\in T}\sum_{c\in C_t}
\left(f_{tc}+o_{tc}\right)z_{jtc}
+
\sum_{i\in I}\sum_{j\in J}\sum_{t\in T}
d_i\,\mathrm{dist}_{ij}\,c^{\mathrm{tr}}\,x_{ijt}
+
\lambda_L Z_2+\lambda_C Z_3.
\tag{9}
\]
```

```latex
\[
\min Z_2=
\sum_{i\in I}\sum_{j\in J}\sum_{t\in T}
d_i x_{ijt}\left(\alpha_i\,\mathrm{time}_{ij}\,m_t+\beta_t\right).
\tag{10}
\]
```

```latex
\[
\min Z_3=
\sum_{i\in I}\sum_{j\in J}\sum_{t\in T}
d_i x_{ijt}
\left(
\frac{e_t}{1000}
+
\frac{\eta\,\mathrm{dist}_{ij}}{1000}
\right).
\tag{11}
\]
```

```latex
\[
\min_{\boldsymbol z,\boldsymbol x}
\left[
Z_1(\boldsymbol z,\boldsymbol x),
Z_2(\boldsymbol z,\boldsymbol x),
Z_3(\boldsymbol z,\boldsymbol x)
\right]
\quad
\mathrm{s.t.}\quad
\boldsymbol z\in\mathcal Z,\ \boldsymbol x\in\mathcal X(\boldsymbol z).
\tag{12}
\]
```

## 6. KKT 单层化

```latex
\[
\mathrm{LL}(\boldsymbol z):\quad
\min_{\boldsymbol x}\ \boldsymbol c^\top\boldsymbol x
\quad
\mathrm{s.t.}\quad
A\boldsymbol x=\boldsymbol b,\quad
G\boldsymbol x\le \boldsymbol h(\boldsymbol z),\quad
\boldsymbol x\ge \boldsymbol 0.
\tag{13}
\]
```

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
\tag{14}
\]
```

```latex
\[
A\boldsymbol x^\star=\boldsymbol b,\qquad
G\boldsymbol x^\star\le \boldsymbol h(\boldsymbol z),\qquad
\boldsymbol x^\star\ge \boldsymbol 0.
\tag{15}
\]
```

```latex
\[
\boldsymbol v^\star\ge \boldsymbol 0,\qquad
\boldsymbol\pi^\star\ge \boldsymbol 0.
\tag{16}
\]
```

```latex
\[
\boldsymbol c+A^\top\boldsymbol u^\star+G^\top\boldsymbol v^\star-\boldsymbol\pi^\star=\boldsymbol 0.
\tag{17}
\]
```

```latex
\[
v_\ell^\star\left[h_\ell(\boldsymbol z)-G_\ell\boldsymbol x^\star\right]=0,\qquad
\pi_k^\star x_k^\star=0.
\tag{18}
\]
```

```latex
\[
0\le a\le Mr,\qquad
0\le b\le M(1-r),\qquad
r\in\{0,1\}.
\tag{19}
\]
```

```latex
\[
0\le x_k\le M b_k^x,\qquad
0\le \pi_k\le M(1-b_k^x),\qquad
b_k^x\in\{0,1\}.
\tag{20}
\]
```

```latex
\[
0\le h_\ell(\boldsymbol z)-G_\ell\boldsymbol x\le M b_\ell^{\mathrm{cap}},\qquad
0\le v_\ell\le M(1-b_\ell^{\mathrm{cap}}),\qquad
b_\ell^{\mathrm{cap}}\in\{0,1\}.
\tag{21}
\]
```

```latex
\[
\begin{aligned}
\min_{\boldsymbol z,\boldsymbol x,\boldsymbol u,\boldsymbol v,\boldsymbol\pi,\boldsymbol b}
\quad & Z_m(\boldsymbol z,\boldsymbol x)\\
\mathrm{s.t.}\quad
& \boldsymbol z\in\mathcal Z,\\
& A\boldsymbol x=\boldsymbol b,\quad G\boldsymbol x\le \boldsymbol h(\boldsymbol z),\quad \boldsymbol x\ge \boldsymbol0,\\
& \boldsymbol v\ge \boldsymbol0,\quad \boldsymbol\pi\ge \boldsymbol0,\\
& \boldsymbol c+A^\top\boldsymbol u+G^\top\boldsymbol v-\boldsymbol\pi=\boldsymbol0,\\
& \text{constraints }(19)\text{--}(21).
\end{aligned}
\tag{22}
\]
```

## 7. 增广 epsilon 约束法

```latex
\[
\min_{\boldsymbol z,\boldsymbol x} Z_1(\boldsymbol z,\boldsymbol x)
\quad
\mathrm{s.t.}\quad
Z_2(\boldsymbol z,\boldsymbol x)\le \varepsilon_2,\quad
Z_3(\boldsymbol z,\boldsymbol x)\le \varepsilon_3,\quad
\boldsymbol z\in\mathcal Z,\ \boldsymbol x\in\mathcal X(\boldsymbol z).
\tag{23}
\]
```

```latex
\[
R_m=Z_m^{\max}-Z_m^{\min},\qquad m=2,3.
\tag{24}
\]
```

```latex
\[
\min_{\boldsymbol z,\boldsymbol x,s_2,s_3}
Z_1(\boldsymbol z,\boldsymbol x)
+
\rho\left(\frac{s_2}{R_2}+\frac{s_3}{R_3}\right).
\tag{25}
\]
```

```latex
\[
Z_2(\boldsymbol z,\boldsymbol x)\le \varepsilon_2^k+s_2,\qquad
Z_3(\boldsymbol z,\boldsymbol x)\le \varepsilon_3^k+s_3,\qquad
s_2,s_3\ge 0.
\tag{26}
\]
```

```latex
\[
\varepsilon_m^k
=
Z_m^{\min}
+
\frac{k}{K_m-1}
\left(Z_m^{\max}-Z_m^{\min}\right),
\qquad k=0,1,\ldots,K_m-1,\quad m=2,3.
\tag{27}
\]
```

```latex
\[
\boldsymbol a\prec \boldsymbol b
\Longleftrightarrow
\left[
Z_m(\boldsymbol a)\le Z_m(\boldsymbol b),\ \forall m
\right]
\land
\left[
\exists m,\ Z_m(\boldsymbol a)<Z_m(\boldsymbol b)
\right].
\tag{28}
\]
```

## 8. Gurobi 与 AI Warm Start

```latex
\[
\boldsymbol\psi_j=
\left[
\mathrm{production}_j,\ \max_i\mathrm{dist}_{ij},\ \mathrm{dist}_{j,C1},\
\mathrm{lat}_j,\ \mathrm{lon}_j,\ \ldots
\right]^\top .
\tag{29}
\]
```

```latex
\[
p_j=
\Pr(y_j=1\mid \boldsymbol\psi_j;\Theta_{\mathrm{XGB}}).
\tag{30}
\]
```

```latex
\[
S_K=\operatorname*{TopK}_{j\in J}(p_j).
\tag{31}
\]
```

```latex
\[
z_{jtc}^{\mathrm{Start}}=
\begin{cases}
1, & (j,t,c)\in \mathcal W(S_K),\\
0, & \text{otherwise},
\end{cases}
\tag{32}
\]
```

```latex
\[
\mathrm{Speedup}=\frac{T_{\mathrm{cold}}}{T_{\mathrm{warm}}},\qquad
\Delta Z=
\frac{\left|Z_{\mathrm{warm}}-Z_{\mathrm{cold}}\right|}
{\left|Z_{\mathrm{cold}}\right|+\epsilon}.
\tag{33}
\]
```

```latex
\[
\mathrm{MIPGap}=
\frac{\left|\mathrm{UB}-\mathrm{LB}\right|}
{\left|\mathrm{UB}\right|+\epsilon}.
\tag{34}
\]
```

## 9. Benders 分解与 AI Cut 管理

```latex
\[
\begin{aligned}
\mathrm{Master}:\quad
\min_{\boldsymbol z,\theta}\quad
& f(\boldsymbol z)+\theta\\
\mathrm{s.t.}\quad
& \boldsymbol z\in\mathcal Z,\\
& \theta\ge \alpha^r+(\boldsymbol\beta^r)^\top\boldsymbol z,
\qquad r\in\mathcal C.
\end{aligned}
\tag{35}
\]
```

```latex
\[
Q(\bar{\boldsymbol z})=
\min_{\boldsymbol x}
\left\{
\boldsymbol q^\top\boldsymbol x
\ \middle|\
A\boldsymbol x=\boldsymbol b,\ 
G\boldsymbol x\le \boldsymbol h(\bar{\boldsymbol z}),\
\boldsymbol x\ge \boldsymbol0
\right\}.
\tag{36}
\]
```

```latex
\[
\theta\ge \alpha^r+(\boldsymbol\beta^r)^\top\boldsymbol z.
\tag{37}
\]
```

```latex
\[
\mathrm{score}(c)=
0.40\,\mathrm{rhs}(c)
+0.25\,\|\boldsymbol\beta_c\|_1
+0.20\,\mathrm{gap\_pct}(c)
+0.15\,\mathrm{compactness}(c).
\tag{38}
\]
```

```latex
\[
\mathrm{compactness}(c)=\frac{1}{1+\mathrm{nnz}(\boldsymbol\beta_c)}.
\tag{39}
\]
```

```latex
\[
\mathcal C_K^r=
\operatorname*{TopK}_{c\in\mathcal C^r}
\left(\mathrm{score}(c)\right).
\tag{40}
\]
```

```latex
\[
\left|\theta^r-Q(\boldsymbol z^r)\right|\le \epsilon_B.
\tag{41}
\]
```

## 10. NSGA-III 基线

```latex
\[
\tilde Z_m(\boldsymbol s)=
\frac{Z_m(\boldsymbol s)-Z_m^{\min}}
{Z_m^{\max}-Z_m^{\min}+\epsilon},
\qquad m=1,2,3.
\tag{42}
\]
```

```latex
\[
r^\star(\boldsymbol s)=
\operatorname*{arg\,min}_{r\in\mathcal R}
\operatorname{dist}\left(\tilde{\boldsymbol F}(\boldsymbol s),r\right).
\tag{43}
\]
```

```latex
\[
\mathcal P_{g+1}
=
\operatorname{Select}_{N}
\left(
\operatorname{NDSort}
\left(\mathcal P_g\cup\mathcal Q_g\right),
\mathcal R
\right).
\tag{44}
\]
```

## 11. ALNS 基线

```latex
\[
\boldsymbol s'=
R_\ell\!\left(D_k(\boldsymbol s)\right),
\qquad
D_k\in\mathcal D,\ R_\ell\in\mathcal R_{\mathrm{repair}}.
\tag{45}
\]
```

```latex
\[
P_{\mathrm{acc}}(\boldsymbol s\to\boldsymbol s')
=
\min\left\{
1,\ 
\exp\left(
-\frac{Z_1(\boldsymbol s')-Z_1(\boldsymbol s)}{T_g}
\right)
\right\}.
\tag{46}
\]
```

```latex
\[
w_o^{g+1}
=(1-\xi)w_o^g
+
\xi\frac{\mathrm{score}_o^g}{n_o^g+\epsilon},
\qquad o\in\mathcal D\cup\mathcal R_{\mathrm{repair}}.
\tag{47}
\]
```

## 12. Optuna 调参与搜索目标

```latex
\[
\boldsymbol h^\star=
\operatorname*{arg\,min}_{\boldsymbol h\in\mathcal H}
\mathrm{runtime}(\boldsymbol h)
\quad
\mathrm{s.t.}\quad
Z(\boldsymbol h)\le Z_{\mathrm{base}}+\delta,\quad
\mathrm{gap}(\boldsymbol h)\le \mathrm{gap}_{\max}.
\tag{48}
\]
```

```latex
\[
\min_{\boldsymbol h\in\mathcal H}
\left(
\mathrm{runtime}(\boldsymbol h),\
\mathrm{gap}(\boldsymbol h)
\right).
\tag{49}
\]
```

```latex
\[
\boldsymbol h_{n+1}
=
\operatorname*{arg\,max}_{\boldsymbol h\in\mathcal H}
\frac{\ell(\boldsymbol h)}{g(\boldsymbol h)}.
\tag{50}
\]
```

## 13. 对比实验评价指标

```latex
\[
\mathrm{Dev}_{\mathrm{cost}}(m)=
\frac{Z_1^{m}-Z_1^{\mathrm{exact}}}
{Z_1^{\mathrm{exact}}}\times 100\%.
\tag{51}
\]
```

```latex
\[
\mathrm{HV}(\mathcal P)
=
\lambda\left(
\bigcup_{\boldsymbol p\in\mathcal P}
\left[
\boldsymbol F(\boldsymbol p),\boldsymbol r
\right]
\right),
\tag{52}
\]
```

```latex
\[
\mathrm{HV\ Ratio}(m)=
\frac{\mathrm{HV}(\mathcal P_m)}
{\mathrm{HV}(\mathcal P_{\mathrm{exact}})}.
\tag{53}
\]
```

```latex
\[
\mathrm{Converged}
=
\mathbb I
\left(
\mathrm{gap}\le \epsilon_{\mathrm{gap}}
\right).
\tag{54}
\]
```

## 14. MIS 测试与运行评价表达式

```latex
\[
\mathrm{PassRate}=
\frac{N_{\mathrm{passed}}}{N_{\mathrm{total}}}\times 100\%.
\tag{55}
\]
```

```latex
\[
\mathrm{Availability}=
\frac{T_{\mathrm{total}}-T_{\mathrm{down}}}{T_{\mathrm{total}}}\times 100\%.
\tag{56}
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
\tag{57}
\]
```

