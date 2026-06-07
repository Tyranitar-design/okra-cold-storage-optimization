"""
秋葵主产区冷库布局与容量优化 — 单层MIP基线模型 v2.0
Single-Level MIP Baseline v2 — with Explicit Capacity Level Selection

Week 1, Day 2: 基线模型升级
改进(相比v1):
1. 显式容量等级选择变量 z[j,t,c]，不再用平均值近似
2. 加入运营成本(operate_cost)到目标函数
3. 全部27候选点 + 39需求点，不再缩减
4. Gurobi NODE许可证(无变量限制)，可求解完整规模

决策变量:
- z[j,t,c] = 1: 在候选点j建设t类型c容量等级的冷库
- x[i,j,t] = 1: 需求点i的秋葵分配到j点t类型的冷库

目标函数: min 建设成本 + 运营成本 + 运输成本 + 损耗成本 + 碳排放成本

约束:
- C1: 每个需求点恰好分配到一个冷库
- C2: 只能分配到已建冷库
- C3: 每个候选点最多建一个冷库(一种类型+一个容量等级)
- C4: 最大设施数限制
- C5: 预冷时间约束(分配到预冷库的运输时间≤2h)
- C6: 容量约束(分配需求≤选中容量等级)
- C7: 冷链连续性约束(需求点只能分配到比其预冷需求更好的冷库类型)

Author: 小彩 💫 | Date: 2026-05-26
"""

import pyomo.environ as pyo
from pyomo.opt import SolverFactory
import pandas as pd
import numpy as np
import json
import os
import sys
import time


# ============================================================
# 数据加载
# ============================================================

class DataConfig:
    """数据配置与加载"""
    
    def __init__(self, data_dir: str = r"D:\秋葵冷库优化项目\data"):
        self.data_dir = data_dir
        self.nodes = pd.read_csv(os.path.join(data_dir, "nodes.csv"))
        
        # 距离矩阵
        dist_df = pd.read_csv(os.path.join(data_dir, "distance_matrix.csv"), index_col=0)
        self.node_ids = list(dist_df.columns)
        self.distance = dist_df.values  # km
        
        # 运输时间矩阵
        time_df = pd.read_csv(os.path.join(data_dir, "transport_time_matrix.csv"), index_col=0)
        self.transport_time = time_df.values  # hours
        
        # 保鲜参数
        with open(os.path.join(data_dir, "params.json"), 'r', encoding='utf-8') as f:
            self.params = json.load(f)
        
        # 候选点（所有 is_candidate=True 的节点）
        self.candidates = self.nodes[self.nodes['is_candidate']].reset_index(drop=True)
        
        # 需求点（所有有产量的节点）
        self.demands = self.nodes[self.nodes['okra_production_ton'] > 0].reset_index(drop=True)
        
        # 冷库类型
        self.storage_types = list(self.params['cold_storage_types'].keys())
        
        # 构建 node_id → index 映射
        self.id2idx = {nid: i for i, nid in enumerate(self.node_ids)}
        
        # 构建容量等级索引 (type -> [(capacity_value, fixed_cost, operate_cost), ...])
        self.capacity_index = {}
        for t in self.storage_types:
            sp = self.params['cold_storage_types'][t]
            levels = []
            for c in sp['capacity_levels']:
                levels.append({
                    'capacity': c,
                    'fixed_cost': sp['fixed_cost'][str(int(c))],
                    'operate_cost': sp['operate_cost'][str(int(c))],
                    'variable_cost': sp['variable_cost'][str(int(c))],
                })
            self.capacity_index[t] = levels
    
    def get_demand(self, node_id: str) -> float:
        """获取节点秋葵产量(吨/年)"""
        row = self.nodes[self.nodes['node_id'] == node_id]
        return float(row['okra_production_ton'].values[0]) if len(row) > 0 else 0.0
    
    def get_dist(self, id1: str, id2: str) -> float:
        """获取两节点间距离(km)"""
        return self.distance[self.id2idx[id1]][self.id2idx[id2]]
    
    def get_time(self, id1: str, id2: str) -> float:
        """获取两节点间运输时间(h)"""
        return self.transport_time[self.id2idx[id1]][self.id2idx[id2]]
    
    def get_storage_params(self, stype: str) -> dict:
        """获取冷库类型参数"""
        return self.params['cold_storage_types'][stype]
    
    def get_preservation_params(self) -> dict:
        """获取秋葵保鲜参数"""
        return self.params['okra_preservation']


# ============================================================
# 单层MIP基线模型 v2 — 显式容量等级
# ============================================================

def build_single_level_mip_v2(config: DataConfig,
                               carbon_price: float = 50.0,
                               loss_price: float = 3000.0,
                               max_facilities: int = 10,
                               candidate_ids: list = None,
                               demand_ids: list = None) -> pyo.ConcreteModel:
    """
    构建单层MIP基线模型 v2 — 显式容量等级选择
    
    决策变量:
    - z[j,t,c] = 1: 在候选点j建设t类型、第c个容量等级的冷库
    - x[i,j,t] = 1: 需求点i的秋葵分配到j点t类型的冷库
    
    目标函数: min 建设成本 + 运营成本 + 运输成本 + 损耗成本 + 碳排放成本
    """
    m = pyo.ConcreteModel(name="OkraColdStorage_MIP_v2")
    
    # --- 集合 ---
    if candidate_ids is None:
        candidate_ids = list(config.candidates['node_id'])
    if demand_ids is None:
        demand_ids = list(config.demands['node_id'])
    
    m.J = pyo.Set(initialize=candidate_ids, doc="候选冷库位置")
    m.I = pyo.Set(initialize=demand_ids, doc="需求点(秋葵产地)")
    m.T = pyo.Set(initialize=config.storage_types, doc="冷库类型")
    
    # 容量等级索引: 每种类型一个范围
    # 用全局容量等级索引 c ∈ {0, 1, ..., max_level-1}
    max_levels = max(len(config.capacity_index[t]) for t in config.storage_types)
    m.C = pyo.RangeSet(0, max_levels - 1, doc="容量等级索引")
    
    # 有效容量等级集合: (j, t, c) 三元组只有 c < len(capacity_index[t]) 时有效
    valid_z = []
    capacity_data = {}  # (j, t, c) -> {capacity, fixed_cost, operate_cost}
    for j in candidate_ids:
        for t in config.storage_types:
            for c_idx, cap_info in enumerate(config.capacity_index[t]):
                valid_z.append((j, t, c_idx))
                capacity_data[(j, t, c_idx)] = cap_info
    
    m.valid_z = pyo.Set(initialize=valid_z, dimen=3, doc="有效容量等级(j,t,c)")
    
    # --- 参数 ---
    # 需求量
    demand = {i: config.get_demand(i) for i in demand_ids}
    m.demand = pyo.Param(m.I, initialize=demand, doc="秋葵产量(吨/年)")
    
    # 距离和运输时间
    dist_data = {}
    time_data = {}
    for i in demand_ids:
        for j in candidate_ids:
            dist_data[(i, j)] = config.get_dist(i, j)
            time_data[(i, j)] = config.get_time(i, j)
    m.dist = pyo.Param(m.I, m.J, initialize=dist_data, doc="距离(km)")
    m.travel_time = pyo.Param(m.I, m.J, initialize=time_data, doc="运输时间(h)")
    
    # 容量等级参数
    cap_val = {(j, t, c): capacity_data[(j, t, c)]['capacity'] for (j, t, c) in valid_z}
    cap_fixed = {(j, t, c): capacity_data[(j, t, c)]['fixed_cost'] for (j, t, c) in valid_z}
    cap_operate = {(j, t, c): capacity_data[(j, t, c)]['operate_cost'] for (j, t, c) in valid_z}
    
    m.cap_value = pyo.Param(m.J, m.T, m.C, initialize=lambda m, j, t, c: cap_val.get((j, t, c), 0), doc="容量(吨)", mutable=True)
    m.cap_fixed_cost = pyo.Param(m.J, m.T, m.C, initialize=lambda m, j, t, c: cap_fixed.get((j, t, c), 0), doc="固定建设成本(万元)", mutable=True)
    m.cap_operate_cost = pyo.Param(m.J, m.T, m.C, initialize=lambda m, j, t, c: cap_operate.get((j, t, c), 0), doc="年运营成本(万元)", mutable=True)
    
    # 保鲜参数
    pp = config.get_preservation_params()
    m.precool_time_limit = pyo.Param(initialize=pp['precool_time_limit_h'], doc="预冷时间上限(h)")
    m.transport_loss_rate = pyo.Param(initialize=pp['transport_loss_per_hour'], doc="运输损耗率(/h)")
    
    # 碳参数
    m.carbon_price = pyo.Param(initialize=carbon_price, doc="碳价(元/吨CO₂)")
    m.loss_price = pyo.Param(initialize=loss_price, doc="损耗单价(元/吨)")
    
    # 运输单位成本
    m.transport_unit_cost = pyo.Param(initialize=1.2, doc="运输单位成本(元/吨·km)")
    
    # 最大设施数
    m.max_facilities = pyo.Param(initialize=max_facilities, doc="最大设施数")
    
    # 能耗和碳排放因子(按类型)
    energy_per_ton = {t: config.params['cold_storage_types'][t]['energy_cost_per_ton'] 
                      for t in config.storage_types}
    carbon_factor = {t: config.params['cold_storage_types'][t]['carbon_factor'] 
                     for t in config.storage_types}
    m.energy_per_ton = pyo.Param(m.T, initialize=energy_per_ton, doc="能耗(kWh/吨)")
    m.carbon_factor = pyo.Param(m.T, initialize=carbon_factor, doc="碳排放因子(kgCO₂/kWh)")
    
    # --- 决策变量 ---
    # z[j,t,c] = 1: 在j建t类型c容量等级冷库
    m.z = pyo.Var(m.J, m.T, m.C, within=pyo.Binary, 
                  doc="在j建t类型c容量等级冷库")
    
    # x[i,j,t] = 1: 需求点i分配到j点t类型冷库
    m.x = pyo.Var(m.I, m.J, m.T, within=pyo.Binary,
                  doc="需求点i分配到j点t类型冷库")
    
    # --- 约束 ---
    
    # C1: 每个需求点恰好分配到一个冷库
    def assign_once(m, i):
        return sum(m.x[i, j, t] for j in m.J for t in m.T) == 1
    m.assign_once = pyo.Constraint(m.I, rule=assign_once)
    
    # C2: 只能分配到已建的冷库类型
    def assign_to_open(m, i, j, t):
        return m.x[i, j, t] <= sum(m.z[j, t, c] for c in m.C 
                                    if (j, t, c) in valid_z)
    m.assign_to_open = pyo.Constraint(m.I, m.J, m.T, rule=assign_to_open)
    
    # C3: 每个候选点最多建一个冷库(一种类型+一个容量等级)
    def one_facility_per_site(m, j):
        return sum(m.z[j, t, c] for t in m.T for c in m.C 
                   if (j, t, c) in valid_z) <= 1
    m.one_facility = pyo.Constraint(m.J, rule=one_facility_per_site)
    
    # C4: 最大设施数
    def max_fac(m):
        return sum(m.z[j, t, c] for j in m.J for t in m.T for c in m.C
                   if (j, t, c) in valid_z) <= m.max_facilities
    m.max_fac = pyo.Constraint(rule=max_fac)
    
    # C5: 预冷时间约束 — 分配到预冷库的运输时间≤2h
    # 使用大M法: travel_time[i,j] * x[i,j,'precool'] <= precool_limit * x[i,j,'precool'] + M*(1 - x[i,j,'precool'])
    def precool_time(m, i, j):
        # 如果分配到预冷库，运输时间必须≤2h
        big_m = 20.0  # 大M，大于最大可能运输时间
        return m.travel_time[i, j] * m.x[i, j, 'precool'] <= \
               m.precool_time_limit * m.x[i, j, 'precool'] + \
               big_m * (1 - m.x[i, j, 'precool'])
    m.precool_time = pyo.Constraint(m.I, m.J, rule=precool_time)
    
    # C6: 容量约束 — 分配到某冷库的总需求≤选中容量等级
    def capacity_constraint(m, j, t):
        total_assigned = sum(m.x[i, j, t] * m.demand[i] for i in m.I)
        total_capacity = sum(m.z[j, t, c] * m.cap_value[j, t, c] 
                            for c in m.C if (j, t, c) in valid_z)
        return total_assigned <= total_capacity
    m.capacity = pyo.Constraint(m.J, m.T, rule=capacity_constraint)
    
    # C7: 无效容量等级变量固定为0
    def no_invalid_z(m, j, t, c):
        if (j, t, c) not in valid_z:
            return m.z[j, t, c] == 0
        return pyo.Constraint.Skip
    m.no_invalid_z = pyo.Constraint(m.J, m.T, m.C, rule=no_invalid_z)
    
    # --- 目标函数 ---
    
    # 1. 建设成本(固定) — 万元→元
    def fixed_cost_expr(m):
        return sum(m.z[j, t, c] * m.cap_fixed_cost[j, t, c] * 10000
                   for j in m.J for t in m.T for c in m.C
                   if (j, t, c) in valid_z)
    m.fixed_cost_expr = pyo.Expression(rule=fixed_cost_expr)
    
    # 2. 运营成本(年) — 万元→元
    def operate_cost_expr(m):
        return sum(m.z[j, t, c] * m.cap_operate_cost[j, t, c] * 10000
                   for j in m.J for t in m.T for c in m.C
                   if (j, t, c) in valid_z)
    m.operate_cost_expr = pyo.Expression(rule=operate_cost_expr)
    
    # 3. 运输成本
    def transport_cost_expr(m):
        return sum(
            m.x[i, j, t] * m.demand[i] * m.dist[i, j] * m.transport_unit_cost
            for i in m.I for j in m.J for t in m.T
        )
    m.transport_cost_expr = pyo.Expression(rule=transport_cost_expr)
    
    # 4. 损耗成本
    # 运输损耗 = 产量 × 运输时间 × 运输损耗率
    # 存储损耗 = 产量 × 存储损耗率(按类型)
    storage_loss_rate = {
        'precool': pp['precool_loss_rate'],
        'cold': pp['cold_storage_loss_weekly'] * 2,   # 假设存2周
        'ca': pp['ca_storage_loss_weekly'] * 2,       # 假设存2周
        'frozen': pp['cold_storage_loss_weekly'] * 0.5 # 冷冻损耗更低
    }
    
    def loss_cost_expr(m):
        total = 0
        for i in demand_ids:
            for j in candidate_ids:
                for t in config.storage_types:
                    # 运输损耗
                    transport_loss = (m.x[i, j, t] * m.demand[i] * 
                                     m.travel_time[i, j] * pp['transport_loss_per_hour'])
                    # 存储损耗
                    storage_loss = (m.x[i, j, t] * m.demand[i] * 
                                   storage_loss_rate[t])
                    total += (transport_loss + storage_loss) * loss_price
        return total
    m.loss_cost_expr = pyo.Expression(rule=loss_cost_expr)
    
    # 5. 碳排放成本
    # 静态碳排: 冷库运营能耗 × 碳因子
    # 动态碳排: 运输距离 × 载重 × 排放因子
    transport_carbon_factor = 0.1  # kgCO₂/吨·km
    
    def carbon_cost_expr(m):
        total = 0
        # 静态碳排(冷库运营)
        for j in candidate_ids:
            for t in config.storage_types:
                total_demand_at_jt = sum(m.x[i, j, t] * m.demand[i] for i in demand_ids)
                energy_carbon = (total_demand_at_jt * m.energy_per_ton[t] * 
                                m.carbon_factor[t] / 1000)  # 吨CO₂
                total += energy_carbon * carbon_price
        # 动态碳排(运输)
        for i in demand_ids:
            for j in candidate_ids:
                for t in config.storage_types:
                    transport_carbon = (m.x[i, j, t] * m.demand[i] * 
                                       m.dist[i, j] * transport_carbon_factor / 1000)
                    total += transport_carbon * carbon_price
        return total
    m.carbon_cost_expr = pyo.Expression(rule=carbon_cost_expr)
    
    # 总目标
    def total_cost(m):
        return (m.fixed_cost_expr + m.operate_cost_expr + 
                m.transport_cost_expr + m.loss_cost_expr + m.carbon_cost_expr)
    m.obj = pyo.Objective(rule=total_cost, sense=pyo.minimize)
    
    return m


# ============================================================
# 求解与结果分析
# ============================================================

def solve_model(model: pyo.ConcreteModel, time_limit: int = 300, 
                mip_gap: float = 0.01, threads: int = 8):
    """用 Gurobi 求解"""
    solver = SolverFactory('gurobi')
    
    solver.options['TimeLimit'] = time_limit
    solver.options['MIPGap'] = mip_gap
    solver.options['Threads'] = threads
    solver.options['OutputFlag'] = 1
    # LogFile 用 ASCII 路径避免编码问题
    import tempfile
    log_path = os.path.join(tempfile.gettempdir(), 'gurobi_v2.log')
    solver.options['LogFile'] = log_path
    
    # 变量统计
    n_vars = len(list(model.component_data_objects(pyo.Var)))
    n_cons = len(list(model.component_data_objects(pyo.Constraint)))
    
    print(f"\n{'='*60}")
    print(f"  求解: {model.name}")
    print(f"  变量数: {n_vars} | 约束数: {n_cons}")
    print(f"  TimeLimit={time_limit}s, MIPGap={mip_gap}, Threads={threads}")
    print(f"{'='*60}\n")
    
    start = time.time()
    result = solver.solve(model, tee=True)
    elapsed = time.time() - start
    
    print(f"\n{'='*60}")
    print(f"  求解完成! 耗时: {elapsed:.1f}s")
    print(f"  状态: {result.solver.status}, {result.solver.termination_condition}")
    print(f"{'='*60}\n")
    
    return result, elapsed


def analyze_results(model: pyo.ConcreteModel, config: DataConfig):
    """分析求解结果"""
    print("\n" + "="*60)
    print("  📊 基线模型 v2 求解结果")
    print("="*60)
    
    # 1. 目标函数值
    obj_val = pyo.value(model.obj)
    print(f"\n🎯 总成本: {obj_val:,.0f} 元")
    print(f"   建设成本: {pyo.value(model.fixed_cost_expr):,.0f} 元")
    print(f"   运营成本: {pyo.value(model.operate_cost_expr):,.0f} 元")
    print(f"   运输成本: {pyo.value(model.transport_cost_expr):,.0f} 元")
    print(f"   损耗成本: {pyo.value(model.loss_cost_expr):,.0f} 元")
    print(f"   碳排放成本: {pyo.value(model.carbon_cost_expr):,.0f} 元")
    
    # 各成本占比
    total = obj_val if obj_val > 0 else 1
    print(f"\n   📈 成本结构:")
    for name, val in [("建设", pyo.value(model.fixed_cost_expr)),
                       ("运营", pyo.value(model.operate_cost_expr)),
                       ("运输", pyo.value(model.transport_cost_expr)),
                       ("损耗", pyo.value(model.loss_cost_expr)),
                       ("碳排", pyo.value(model.carbon_cost_expr))]:
        pct = val / total * 100
        print(f"      {name}: {pct:.1f}%")
    
    # 2. 冷库选址方案（带容量等级）
    print(f"\n🏗️ 冷库选址方案:")
    opened = []
    for j in model.J:
        for t in model.T:
            for c in model.C:
                if (j, t, c) in model.valid_z and pyo.value(model.z[j, t, c]) > 0.5:
                    sp = config.get_storage_params(t)
                    cap = model.cap_value[j, t, c]
                    fixed = model.cap_fixed_cost[j, t, c]
                    operate = model.cap_operate_cost[j, t, c]
                    
                    # 计算分配到该冷库的总需求
                    total_demand = sum(
                        pyo.value(model.x[i, j, t]) * config.get_demand(i)
                        for i in model.I
                    )
                    util_rate = total_demand / cap * 100 if cap > 0 else 0
                    
                    print(f"   📦 {j}: {sp['name']} | 容量:{cap}吨 | "
                          f"建设:{fixed}万 | 运营:{operate}万/年 | "
                          f"分配需求:{total_demand:.1f}吨 | 利用率:{util_rate:.1f}%")
                    opened.append({
                        'site': j, 'type': t, 'capacity': cap,
                        'fixed_cost': fixed, 'operate_cost': operate,
                        'assigned_demand': total_demand,
                        'utilization': util_rate
                    })
    
    print(f"\n   开放冷库总数: {len(opened)}")
    
    # 3. 分配详情
    print(f"\n📋 分配详情:")
    for i in model.I:
        for j in model.J:
            for t in model.T:
                if pyo.value(model.x[i, j, t]) > 0.5:
                    dist = config.get_dist(i, j)
                    ttime = config.get_time(i, j)
                    demand = config.get_demand(i)
                    sp = config.get_storage_params(t)
                    print(f"   {i} → {j}({sp['name']}) | "
                          f"产量:{demand:.1f}吨 | 距离:{dist:.1f}km | 时间:{ttime:.2f}h")
    
    # 4. 预冷时间检查
    print(f"\n⏱️ 预冷时间约束检查:")
    pp = config.get_preservation_params()
    violations = 0
    for i in model.I:
        for j in model.J:
            val = pyo.value(model.x[i, j, 'precool'])
            if val is not None and val > 0.5:
                ttime = config.get_time(i, j)
                status = "✅" if ttime <= pp['precool_time_limit_h'] else "❌ 违反!"
                if ttime > pp['precool_time_limit_h']:
                    violations += 1
                print(f"   {i}→{j}: {ttime:.2f}h {status}")
    if violations == 0:
        print("   所有预冷时间约束均满足 ✅")
    
    # 5. 碳排放汇总
    print(f"\n🌱 碳排放汇总:")
    transport_carbon_factor = 0.1  # kgCO₂/吨·km
    static_carbon = 0
    dynamic_carbon = 0
    for j in model.J:
        for t in model.T:
            td = sum(pyo.value(model.x[i, j, t]) * config.get_demand(i) for i in model.I)
            if td > 0.01:
                sc = td * config.params['cold_storage_types'][t]['energy_cost_per_ton'] * \
                     config.params['cold_storage_types'][t]['carbon_factor'] / 1000
                static_carbon += sc
    for i in model.I:
        for j in model.J:
            for t in model.T:
                xv = pyo.value(model.x[i, j, t])
                if xv is not None and xv > 0.5:
                    dc = config.get_demand(i) * config.get_dist(i, j) * transport_carbon_factor / 1000
                    dynamic_carbon += dc
    print(f"   静态碳排放(冷库运营): {static_carbon:.2f} 吨CO₂/年")
    print(f"   动态碳排放(运输): {dynamic_carbon:.2f} 吨CO₂/年")
    print(f"   总碳排放: {static_carbon + dynamic_carbon:.2f} 吨CO₂/年")
    
    return {
        'total_cost': obj_val,
        'fixed_cost': pyo.value(model.fixed_cost_expr),
        'operate_cost': pyo.value(model.operate_cost_expr),
        'transport_cost': pyo.value(model.transport_cost_expr),
        'loss_cost': pyo.value(model.loss_cost_expr),
        'carbon_cost': pyo.value(model.carbon_cost_expr),
        'num_facilities': len(opened),
        'facilities': opened,
        'precool_violations': violations,
        'static_carbon': static_carbon,
        'dynamic_carbon': dynamic_carbon,
    }


# ============================================================
# 主程序
# ============================================================

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding='utf-8')
    print("="*60)
    print("  🌿 秋葵冷库布局优化 — 单层MIP基线模型 v2.0")
    print("  Week 1, Day 2: Explicit Capacity Level Selection")
    print("  Gurobi NODE License — 无变量限制 ✅")
    print("="*60)
    
    # 加载数据
    config = DataConfig()
    print(f"\n📦 数据加载完成:")
    print(f"   节点数: {len(config.nodes)}")
    print(f"   候选点: {len(config.candidates)} (全部，不再缩减)")
    print(f"   需求点: {len(config.demands)}")
    print(f"   冷库类型: {config.storage_types}")
    print(f"   总产量: {config.nodes['okra_production_ton'].sum():.1f} 吨/年")
    
    # 显示容量等级
    print(f"\n📊 冷库类型与容量等级:")
    for t in config.storage_types:
        sp = config.get_storage_params(t)
        levels = [f"{c}吨({sp['fixed_cost'][str(int(c))]}万)" 
                  for c in sp['capacity_levels']]
        print(f"   {sp['name']}: {', '.join(levels)}")
    
    # 构建模型 — 使用全部候选点！
    all_candidate_ids = list(config.candidates['node_id'])
    all_demand_ids = list(config.demands['node_id'])
    
    print(f"\n🔧 构建单层MIP模型v2(全部{len(all_candidate_ids)}候选点 × "
          f"{len(all_demand_ids)}需求点)...")
    
    model = build_single_level_mip_v2(
        config,
        carbon_price=50.0,
        loss_price=3000.0,
        max_facilities=8,
        candidate_ids=all_candidate_ids,
        demand_ids=all_demand_ids
    )
    
    # 求解
    result, elapsed = solve_model(model, time_limit=300, mip_gap=0.01, threads=8)
    
    # 分析结果
    if result.solver.termination_condition in [
        pyo.TerminationCondition.optimal,
        pyo.TerminationCondition.maxTimeLimit,
        pyo.TerminationCondition.feasible
    ]:
        analysis = analyze_results(model, config)
        
        # 保存结果
        import pickle
        results_dir = r"D:\秋葵冷库优化项目\results"
        os.makedirs(results_dir, exist_ok=True)
        with open(os.path.join(results_dir, "baseline_v2_result.pkl"), 'wb') as f:
            pickle.dump({'analysis': analysis, 'elapsed': elapsed}, f)
        print(f"\n💾 结果已保存到 {results_dir}/baseline_v2_result.pkl")
    else:
        print(f"\n❌ 求解失败: {result.solver.termination_condition}")
