"""
秋葵主产区冷库布局与容量优化 — 单层MIP基线模型
Single-Level MIP Baseline for Cold Storage Layout Optimization

Week 1, Day 1-2: 基线模型
- 决策：冷库选址 + 类型 + 容量 + 客户分配
- 目标：min(建设成本 + 运营成本 + 运输成本 + 损耗成本 + 碳排放成本)
- 方法：Pyomo + Gurobi 精确求解
- 参考：Cavagnini et al. (2026) 标准 LRP 建模 + Huang et al. (2025) J县案例

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
        
        # 候选点（乡镇+县级，部分村）
        self.candidates = self.nodes[self.nodes['is_candidate']].reset_index(drop=True)
        
        # 需求点（所有有产量的节点）
        self.demands = self.nodes[self.nodes['okra_production_ton'] > 0].reset_index(drop=True)
        
        # 冷库类型
        self.storage_types = list(self.params['cold_storage_types'].keys())
        
        # 构建 node_id → index 映射
        self.id2idx = {nid: i for i, nid in enumerate(self.node_ids)}
    
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
# 单层MIP基线模型
# ============================================================

def build_single_level_mip(config: DataConfig, 
                           carbon_price: float = 50.0,
                           loss_price: float = 3000.0,
                           max_facilities: int = 10,
                           candidate_ids: list = None,
                           time_limit: int = 300) -> pyo.ConcreteModel:
    """
    构建单层MIP基线模型
    
    决策变量:
    - z[j,t,c] = 1 如果在候选点j建设t类型c容量的冷库
    - x[i,j,t] = 1 如果需求点i的秋葵分配到j点t类型的冷库
    
    目标函数: min 建设成本 + 运营成本 + 运输成本 + 损耗成本 + 碳排放成本
    """
    m = pyo.ConcreteModel(name="OkraColdStorage_MIP_Baseline")
    
    # --- 集合 ---
    # 候选点（可外部指定）
    if candidate_ids is None:
        candidate_ids = list(config.candidates['node_id'])
    m.J = pyo.Set(initialize=candidate_ids, doc="候选冷库位置")
    
    # 需求点
    demand_ids = list(config.demands['node_id'])
    m.I = pyo.Set(initialize=demand_ids, doc="需求点(秋葵产地)")
    
    # 冷库类型
    m.T = pyo.Set(initialize=config.storage_types, doc="冷库类型")
    
    # 每种类型的容量等级
    capacity_levels = {}
    for t in config.storage_types:
        sp = config.get_storage_params(t)
        capacity_levels[t] = [float(c) for c in sp['capacity_levels']]
    
    m.C = pyo.Set(m.T, initialize=lambda m, t: capacity_levels[t], doc="容量等级(按类型)")
    
    # --- 参数 ---
    # 需求量
    demand = {i: config.get_demand(i) for i in demand_ids}
    m.demand = pyo.Param(m.I, initialize=demand, doc="秋葵产量(吨/年)")
    
    # 冷库固定建设成本
    fixed_cost = {}
    for j in candidate_ids:
        for t in config.storage_types:
            sp = config.get_storage_params(t)
            for c in sp['capacity_levels']:
                fixed_cost[(j, t, float(c))] = sp['fixed_cost'][str(int(c))]
    m.fixed_cost = pyo.Param(m.J, m.T, pyo.RangeSet(1, 5), initialize=0, doc="固定建设成本(万元)")
    
    # 运营成本
    operate_cost = {}
    for j in candidate_ids:
        for t in config.storage_types:
            sp = config.get_storage_params(t)
            for c in sp['capacity_levels']:
                operate_cost[(j, t, float(c))] = sp['operate_cost'][str(int(c))]
    
    # 运输成本 (元/吨·km)
    m.transport_unit_cost = pyo.Param(initialize=1.2, doc="运输单位成本(元/吨·km)")
    
    # 损耗参数
    pp = config.get_preservation_params()
    m.precool_time_limit = pyo.Param(initialize=pp['precool_time_limit_h'], doc="预冷时间上限(h)")
    m.transport_loss_rate = pyo.Param(initialize=pp['transport_loss_per_hour'], doc="运输损耗率(/h)")
    
    # 碳参数
    m.carbon_price = pyo.Param(initialize=carbon_price, doc="碳价(元/吨CO₂)")
    
    # --- 决策变量 ---
    # z[j,t,c] = 1: 在j建t类型c容量冷库
    # 简化：用 (j,t) 对，容量选择用整数变量
    m.z = pyo.Var(m.J, m.T, within=pyo.Binary, doc="是否在j建t类型冷库")
    
    # 容量选择：c_idx[j,t] ∈ {0,1,...,len(capacity_levels)} 选择第几档容量
    # 简化为：选定类型后自动分配最小满足需求的容量
    # 更好的方式：显式容量等级选择
    
    # x[i,j,t] = 1: 需求点i分配到j点t类型冷库
    m.x = pyo.Var(m.I, m.J, m.T, within=pyo.Binary, doc="需求点i分配到j点t类型冷库")
    
    # --- 约束 ---
    
    # C1: 每个需求点必须分配到恰好一个冷库
    def assign_once(m, i):
        return sum(m.x[i, j, t] for j in m.J for t in m.T) == 1
    m.assign_once = pyo.Constraint(m.I, rule=assign_once, doc="每个需求点恰好分配一次")
    
    # C2: 只有建了冷库才能分配需求
    def assign_to_open(m, i, j, t):
        return m.x[i, j, t] <= m.z[j, t]
    m.assign_to_open = pyo.Constraint(m.I, m.J, m.T, rule=assign_to_open, 
                                       doc="只能分配到已建冷库")
    
    # C3: 每个候选点最多建一种类型的冷库
    def one_type_per_site(m, j):
        return sum(m.z[j, t] for t in m.T) <= 1
    m.one_type_per_site = pyo.Constraint(m.J, rule=one_type_per_site, 
                                          doc="每个点最多建一种类型冷库")
    
    # C4: 最大设施数
    def max_fac(m):
        return sum(m.z[j, t] for j in m.J for t in m.T) <= max_facilities
    m.max_fac = pyo.Constraint(rule=max_fac, doc="最大设施数限制")
    
    # C5: 预冷时间约束 — 分配到预冷库的需求点运输时间≤2h
    def precool_time(m, i):
        # 如果分配到预冷库，运输时间必须≤2h
        return sum(m.x[i, j, 'precool'] * config.get_time(i, j) 
                   for j in m.J) <= pp['precool_time_limit_h'] * \
               sum(m.x[i, j, 'precool'] for j in m.J) + \
               999 * (1 - sum(m.x[i, j, 'precool'] for j in m.J))
    m.precool_time = pyo.Constraint(m.I, rule=precool_time, doc="预冷时间≤2h")
    
    # C6: 容量约束 — 分配到某冷库的总需求不超过其容量
    # 简化版：每种类型取最大容量等级
    max_cap_by_type = {}
    for t in config.storage_types:
        sp = config.get_storage_params(t)
        max_cap_by_type[t] = max(sp['capacity_levels'])
    
    def capacity_constraint(m, j, t):
        total_assigned = sum(m.x[i, j, t] * m.demand[i] for i in m.I)
        return total_assigned <= max_cap_by_type[t] * m.z[j, t]
    m.capacity = pyo.Constraint(m.J, m.T, rule=capacity_constraint, doc="容量约束")
    
    # --- 目标函数 ---
    
    # 1. 建设成本（固定）— 用每种类型的平均建设成本近似
    avg_fixed_by_type = {}
    for t in config.storage_types:
        sp = config.get_storage_params(t)
        avg_fixed_by_type[t] = sum(sp['fixed_cost'].values()) / len(sp['fixed_cost'])
    
    def fixed_cost_expr(m):
        return sum(avg_fixed_by_type[t] * m.z[j, t] * 10000  # 万元→元
                   for j in candidate_ids for t in config.storage_types)
    m.fixed_cost_expr = pyo.Expression(rule=fixed_cost_expr, doc="建设成本")
    
    # 2. 运输成本
    def transport_cost_expr(m):
        return sum(
            m.x[i, j, t] * m.demand[i] * config.get_dist(i, j) * m.transport_unit_cost
            for i in demand_ids for j in candidate_ids for t in config.storage_types
        )
    m.transport_cost_expr = pyo.Expression(rule=transport_cost_expr, doc="运输成本")
    
    # 3. 损耗成本
    def loss_cost_expr(m):
        total_loss = 0
        for i in demand_ids:
            for j in candidate_ids:
                for t in config.storage_types:
                    # 运输损耗 = 产量 × 运输时间 × 运输损耗率
                    transport_loss = m.x[i, j, t] * m.demand[i] * config.get_time(i, j) * pp['transport_loss_per_hour']
                    # 存储损耗（根据冷库类型不同）
                    if t == 'precool':
                        storage_loss_rate = pp['precool_loss_rate']
                    elif t == 'cold':
                        storage_loss_rate = pp['cold_storage_loss_weekly'] * 2  # 假设存2周
                    elif t == 'ca':
                        storage_loss_rate = pp['ca_storage_loss_weekly'] * 2
                    else:  # frozen
                        storage_loss_rate = pp['cold_storage_loss_weekly'] * 0.5  # 冷冻损耗更低
                    storage_loss = m.x[i, j, t] * m.demand[i] * storage_loss_rate
                    total_loss += (transport_loss + storage_loss) * loss_price
        return total_loss
    m.loss_cost_expr = pyo.Expression(rule=loss_cost_expr, doc="损耗成本")
    
    # 4. 碳排放成本
    def carbon_cost_expr(m):
        carbon = 0
        for j in candidate_ids:
            for t in config.storage_types:
                sp = config.get_storage_params(t)
                # 静态碳排放：冷库运营能耗
                total_demand_at_j = sum(m.x[i, j, t] * m.demand[i] for i in demand_ids)
                energy_carbon = total_demand_at_j * sp['energy_cost_per_ton'] * sp['carbon_factor'] / 1000  # 吨CO₂
                carbon += energy_carbon * carbon_price
                # 动态碳排放：运输
        for i in demand_ids:
            for j in candidate_ids:
                for t in config.storage_types:
                    # 运输碳排放 ≈ 距离 × 载重 × 排放因子
                    transport_carbon = m.x[i, j, t] * m.demand[i] * config.get_dist(i, j) * 0.1 / 1000  # 0.1kgCO₂/吨·km
                    carbon += transport_carbon * carbon_price
        return carbon
    m.carbon_cost_expr = pyo.Expression(rule=carbon_cost_expr, doc="碳排放成本")
    
    # 总目标
    def total_cost(m):
        return m.fixed_cost_expr + m.transport_cost_expr + m.loss_cost_expr + m.carbon_cost_expr
    m.obj = pyo.Objective(rule=total_cost, sense=pyo.minimize, doc="最小化总成本")
    
    return m


# ============================================================
# 求解与结果分析
# ============================================================

def solve_model(model: pyo.ConcreteModel, time_limit: int = 300, mip_gap: float = 0.01):
    """用 Gurobi 求解"""
    solver = SolverFactory('gurobi')
    
    # Gurobi 选项
    solver.options['TimeLimit'] = time_limit
    solver.options['MIPGap'] = mip_gap
    solver.options['Threads'] = 4
    solver.options['OutputFlag'] = 1
    
    print(f"\n{'='*60}")
    print(f"  求解: {model.name}")
    print(f"  TimeLimit={time_limit}s, MIPGap={mip_gap}")
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
    print("  📊 基线模型求解结果")
    print("="*60)
    
    # 1. 目标函数值
    obj_val = pyo.value(model.obj)
    print(f"\n🎯 总成本: {obj_val:,.0f} 元")
    print(f"   建设成本: {pyo.value(model.fixed_cost_expr):,.0f} 元")
    print(f"   运输成本: {pyo.value(model.transport_cost_expr):,.0f} 元")
    print(f"   损耗成本: {pyo.value(model.loss_cost_expr):,.0f} 元")
    print(f"   碳排放成本: {pyo.value(model.carbon_cost_expr):,.0f} 元")
    
    # 2. 冷库选址方案
    print(f"\n🏗️ 冷库选址方案:")
    opened = []
    for j in model.J:
        for t in model.T:
            if pyo.value(model.z[j, t]) > 0.5:
                sp = config.get_storage_params(t)
                # 计算分配到该冷库的总需求
                total_demand = sum(
                    pyo.value(model.x[i, j, t]) * config.get_demand(i)
                    for i in model.I
                )
                print(f"   {j}: {sp['name']} | 分配需求: {total_demand:.1f}吨")
                opened.append((j, t, total_demand))
    
    print(f"\n   开放冷库总数: {len(opened)}")
    
    # 3. 分配详情
    print(f"\n📋 分配详情 (仅显示非零):")
    for i in model.I:
        for j in model.J:
            for t in model.T:
                if pyo.value(model.x[i, j, t]) > 0.5:
                    dist = config.get_dist(i, j)
                    ttime = config.get_time(i, j)
                    demand = config.get_demand(i)
                    print(f"   {i} → {j}({config.get_storage_params(t)['name']}) | "
                          f"产量:{demand:.1f}吨 | 距离:{dist:.1f}km | 时间:{ttime:.2f}h")
    
    # 4. 预冷时间检查
    print(f"\n⏱️ 预冷时间约束检查:")
    pp = config.get_preservation_params()
    violations = 0
    for i in model.I:
        for j in model.J:
            val = pyo.value(model.x[i, j, 'precool'])
            if val > 0.5:
                ttime = config.get_time(i, j)
                status = "✅" if ttime <= pp['precool_time_limit_h'] else "❌ 违反!"
                if ttime > pp['precool_time_limit_h']:
                    violations += 1
                print(f"   {i}→{j}: {ttime:.2f}h {status}")
    if violations == 0:
        print("   所有预冷时间约束均满足 ✅")
    
    return {
        'total_cost': obj_val,
        'fixed_cost': pyo.value(model.fixed_cost_expr),
        'transport_cost': pyo.value(model.transport_cost_expr),
        'loss_cost': pyo.value(model.loss_cost_expr),
        'carbon_cost': pyo.value(model.carbon_cost_expr),
        'num_facilities': len(opened),
        'facilities': opened,
        'precool_violations': violations
    }


# ============================================================
# 主程序
# ============================================================

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding='utf-8')
    print("="*60)
    print("  🌿 秋葵冷库布局优化 — 单层MIP基线模型")
    print("  Week 1, Day 1: Baseline Model")
    print("="*60)
    
    # 加载数据
    config = DataConfig()
    print(f"\n📦 数据加载完成:")
    print(f"   节点数: {len(config.nodes)}")
    print(f"   候选点: {len(config.candidates)}")
    print(f"   需求点: {len(config.demands)}")
    print(f"   冷库类型: {config.storage_types}")
    print(f"   总产量: {config.nodes['okra_production_ton'].sum():.1f} 吨/年")
    
    # 构建模型 — 用乡镇+县级做候选点（缩小规模以适配Gurobi免费版）
    town_county_ids = list(config.candidates[
        config.candidates['level'] >= 2
    ]['node_id'])
    print(f"\n🔧 构建单层MIP模型(缩减候选点={len(town_county_ids)}个)...")
    model = build_single_level_mip(config, 
                                     carbon_price=50.0, 
                                     loss_price=3000.0,
                                     max_facilities=5,
                                     candidate_ids=town_county_ids)
    
    # 求解
    result, elapsed = solve_model(model, time_limit=300, mip_gap=0.01)
    
    # 分析结果
    if result.solver.termination_condition == pyo.TerminationCondition.optimal or \
       result.solver.termination_condition == pyo.TerminationCondition.maxTimeLimit:
        analysis = analyze_results(model, config)
        
        # 保存结果
        import pickle
        results_dir = r"D:\秋葵冷库优化项目\results"
        os.makedirs(results_dir, exist_ok=True)
        with open(os.path.join(results_dir, "baseline_s1_result.pkl"), 'wb') as f:
            pickle.dump({'analysis': analysis, 'elapsed': elapsed}, f)
        print(f"\n💾 结果已保存到 {results_dir}/baseline_s1_result.pkl")
    else:
        print(f"\n❌ 求解失败: {result.solver.termination_condition}")
