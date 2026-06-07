"""
秋葵主产区冷库布局与容量优化 — 单层MIP基线模型 v2.1
Single-Level MIP Baseline v2.1 — gurobipy Direct API

改进(v2→v2.1):
- 改用 gurobipy 直接建模求解，绕过 Pyomo SolverFactory 的许可证问题
- 确保使用 NODE 许可证(无变量限制)
- 性能更好(gurobipy 原生 API 比 Pyomo→LP→Gurobi 更快)

Author: 小彩 💫 | Date: 2026-05-26
"""

import os
from pathlib import Path
import json
import sys
import time
import numpy as np
import pandas as pd


def _bootstrap_gurobi_license() -> str:
    """尽早绑定可用的 Gurobi 许可证，避免误用 site-packages 内置 PIP 许可。"""
    normalized_site_pkg = r"site-packages\gurobipy\gurobi.lic"
    current = os.environ.get("GRB_LICENSE_FILE")
    if current:
        current_norm = current.replace("/", "\\").lower()
        if current_norm.endswith("gurobi.lic") and normalized_site_pkg not in current_norm and Path(current).is_file():
            os.environ["GRB_LICENSE_FILE"] = current
            return current

    node_license = r"D:\Gurobi1300\win64\bin\gurobi.lic"
    if Path(node_license).is_file():
        os.environ["GRB_LICENSE_FILE"] = node_license
        return node_license

    raise FileNotFoundError(
        "未找到可用的 Gurobi NODE 许可证，请确认 D:\\Gurobi1300\\win64\\bin\\gurobi.lic 可访问。"
    )


_GUROBI_LICENSE_PATH = _bootstrap_gurobi_license()

import gurobipy as gp
from gurobipy import GRB


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
        
        # 候选点
        self.candidates = self.nodes[self.nodes['is_candidate']].reset_index(drop=True)
        
        # 需求点
        self.demands = self.nodes[self.nodes['okra_production_ton'] > 0].reset_index(drop=True)
        
        # 冷库类型
        self.storage_types = list(self.params['cold_storage_types'].keys())
        
        # node_id → index
        self.id2idx = {nid: i for i, nid in enumerate(self.node_ids)}
        
        # 容量等级索引
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
                    'energy_cost_per_ton': sp['energy_cost_per_ton'],
                    'carbon_factor': sp['carbon_factor'],
                })
            self.capacity_index[t] = levels
    
    def get_demand(self, node_id: str) -> float:
        row = self.nodes[self.nodes['node_id'] == node_id]
        return float(row['okra_production_ton'].values[0]) if len(row) > 0 else 0.0
    
    def get_dist(self, id1: str, id2: str) -> float:
        return self.distance[self.id2idx[id1]][self.id2idx[id2]]
    
    def get_time(self, id1: str, id2: str) -> float:
        return self.transport_time[self.id2idx[id1]][self.id2idx[id2]]
    
    def get_storage_params(self, stype: str) -> dict:
        return self.params['cold_storage_types'][stype]
    
    def get_preservation_params(self) -> dict:
        return self.params['okra_preservation']


# ============================================================
# 单层MIP v2.1 — gurobipy 直接建模
# ============================================================

def build_and_solve_v2(config: DataConfig,
                       carbon_price: float = 50.0,
                       loss_price: float = 3000.0,
                       max_facilities: int = 8,
                       candidate_ids: list = None,
                       demand_ids: list = None,
                       time_limit: int = 300,
                       mip_gap: float = 0.01,
                       threads: int = 8,
                       verbose: bool = True):
    """
    用 gurobipy 直接构建并求解单层MIP v2.1
    
    决策变量:
    - z[j,t,c] = 1: 在候选点j建设t类型、第c个容量等级的冷库
    - x[i,j,t] = 1: 需求点i的秋葵分配到j点t类型的冷库
    """
    
    if candidate_ids is None:
        candidate_ids = list(config.candidates['node_id'])
    if demand_ids is None:
        demand_ids = list(config.demands['node_id'])
    
    storage_types = config.storage_types
    pp = config.get_preservation_params()
    
    # 存储损耗率(按类型)
    storage_loss_rate = {
        'precool': pp['precool_loss_rate'],
        'cold': pp['cold_storage_loss_weekly'] * 2,
        'ca': pp['ca_storage_loss_weekly'] * 2,
        'frozen': pp['cold_storage_loss_weekly'] * 0.5,
    }
    
    # 索引映射
    j_idx = {j: idx for idx, j in enumerate(candidate_ids)}
    i_idx = {i: idx for idx, i in enumerate(demand_ids)}
    t_idx = {t: idx for idx, t in enumerate(storage_types)}
    
    # 需求量
    demand = {i: config.get_demand(i) for i in demand_ids}
    
    # 运输碳排放因子
    transport_carbon_factor = 0.1  # kgCO₂/吨·km
    
    # ===== 创建模型 =====
    model = gp.Model("OkraColdStorage_MIP_v2_1")
    model.setParam('TimeLimit', time_limit)
    model.setParam('MIPGap', mip_gap)
    model.setParam('Threads', threads)
    model.setParam('OutputFlag', 1 if verbose else 0)
    
    # ===== 决策变量 =====
    
    # z[j,t,c]: 是否在j建t类型c容量等级冷库
    z = {}
    for j in candidate_ids:
        for t in storage_types:
            for c_idx, cap_info in enumerate(config.capacity_index[t]):
                z[j, t, c_idx] = model.addVar(
                    vtype=GRB.BINARY,
                    name=f"z_{j}_{t}_{c_idx}"
                )
    
    # x[i,j,t]: 需求点i分配到j点t类型冷库
    x = {}
    for i in demand_ids:
        for j in candidate_ids:
            for t in storage_types:
                x[i, j, t] = model.addVar(
                    vtype=GRB.BINARY,
                    name=f"x_{i}_{j}_{t}"
                )
    
    model.update()
    
    # ===== 约束 =====
    
    # C1: 每个需求点恰好分配到一个冷库
    for i in demand_ids:
        model.addConstr(
            gp.quicksum(x[i, j, t] for j in candidate_ids for t in storage_types) == 1,
            name=f"assign_once_{i}"
        )
    
    # C2: 只能分配到已建的冷库类型
    for i in demand_ids:
        for j in candidate_ids:
            for t in storage_types:
                model.addConstr(
                    x[i, j, t] <= gp.quicksum(z[j, t, c] for c in range(len(config.capacity_index[t]))),
                    name=f"assign_open_{i}_{j}_{t}"
                )
    
    # C3: 每个候选点最多建一个冷库(一种类型+一个容量等级)
    for j in candidate_ids:
        model.addConstr(
            gp.quicksum(z[j, t, c] for t in storage_types 
                       for c in range(len(config.capacity_index[t]))) <= 1,
            name=f"one_facility_{j}"
        )
    
    # C4: 最大设施数
    model.addConstr(
        gp.quicksum(z[j, t, c] for j in candidate_ids for t in storage_types
                   for c in range(len(config.capacity_index[t]))) <= max_facilities,
        name="max_facilities"
    )
    
    # C5: 预冷时间约束 — 分配到预冷库的运输时间≤2h
    # 使用大M法: travel_time[i,j] - precool_limit <= M*(1 - x[i,j,'precool'])
    big_m = 20.0
    for i in demand_ids:
        for j in candidate_ids:
            travel = config.get_time(i, j)
            model.addConstr(
                travel * x[i, j, 'precool'] <= pp['precool_time_limit_h'] * x[i, j, 'precool'] + big_m * (1 - x[i, j, 'precool']),
                name=f"precool_{i}_{j}"
            )
    
    # C6: 容量约束 — 分配到某冷库的总需求≤选中容量等级
    for j in candidate_ids:
        for t in storage_types:
            total_assigned = gp.quicksum(x[i, j, t] * demand[i] for i in demand_ids)
            total_capacity = gp.quicksum(z[j, t, c] * config.capacity_index[t][c]['capacity'] 
                                         for c in range(len(config.capacity_index[t])))
            model.addConstr(
                total_assigned <= total_capacity,
                name=f"capacity_{j}_{t}"
            )
    
    # ===== 目标函数 =====
    
    # 1. 建设成本(固定) — 万元→元
    fixed_cost = gp.quicksum(
        z[j, t, c] * config.capacity_index[t][c]['fixed_cost'] * 10000
        for j in candidate_ids for t in storage_types
        for c in range(len(config.capacity_index[t]))
    )
    
    # 2. 运营成本(年) — 万元→元
    operate_cost = gp.quicksum(
        z[j, t, c] * config.capacity_index[t][c]['operate_cost'] * 10000
        for j in candidate_ids for t in storage_types
        for c in range(len(config.capacity_index[t]))
    )
    
    # 3. 运输成本
    transport_cost = gp.quicksum(
        x[i, j, t] * demand[i] * config.get_dist(i, j) * 1.2
        for i in demand_ids for j in candidate_ids for t in storage_types
    )
    
    # 4. 损耗成本
    loss_cost = gp.quicksum(
        x[i, j, t] * demand[i] * (
            config.get_time(i, j) * pp['transport_loss_per_hour'] +  # 运输损耗
            storage_loss_rate[t]  # 存储损耗
        ) * loss_price
        for i in demand_ids for j in candidate_ids for t in storage_types
    )
    
    # 5. 碳排放成本
    # 静态碳排(冷库运营能耗)
    static_carbon = gp.quicksum(
        x[i, j, t] * demand[i] * config.capacity_index[t][0]['energy_cost_per_ton'] * 
        config.capacity_index[t][0]['carbon_factor'] / 1000 * carbon_price
        for i in demand_ids for j in candidate_ids for t in storage_types
    )
    
    # 动态碳排(运输)
    dynamic_carbon = gp.quicksum(
        x[i, j, t] * demand[i] * config.get_dist(i, j) * transport_carbon_factor / 1000 * carbon_price
        for i in demand_ids for j in candidate_ids for t in storage_types
    )
    
    carbon_cost = static_carbon + dynamic_carbon
    
    # 总目标
    model.setObjective(fixed_cost + operate_cost + transport_cost + loss_cost + carbon_cost, GRB.MINIMIZE)
    
    model.update()
    
    # ===== 求解 =====
    if verbose:
        print(f"\n{'='*60}")
        print(f"  求解: OkraColdStorage_MIP_v2_1")
        print(f"  变量数: {model.NumVars} | 约束数: {model.NumConstrs}")
        print(f"  候选点: {len(candidate_ids)} | 需求点: {len(demand_ids)}")
        print(f"  TimeLimit={time_limit}s, MIPGap={mip_gap}")
        print(f"{'='*60}\n")
    
    start = time.time()
    model.optimize()
    elapsed = time.time() - start
    
    if verbose:
        print(f"\n{'='*60}")
        print(f"  求解完成! 耗时: {elapsed:.1f}s")
        if model.SolCount > 0:
            print(f"  目标值: {model.ObjVal:,.0f}")
            print(f"  上下界: {model.ObjBound:,.0f} ~ {model.ObjVal:,.0f}")
            print(f"  Gap: {model.MIPGap*100:.2f}%")
        print(f"  状态: {model.Status}")
        print(f"{'='*60}")
    
    return model, z, x, elapsed


def analyze_results(model, z, x, config: DataConfig,
                    candidate_ids, demand_ids,
                    carbon_price=50.0, loss_price=3000.0,
                    verbose: bool = True):
    """分析求解结果"""
    storage_types = config.storage_types
    pp = config.get_preservation_params()
    demand = {i: config.get_demand(i) for i in demand_ids}
    
    storage_loss_rate = {
        'precool': pp['precool_loss_rate'],
        'cold': pp['cold_storage_loss_weekly'] * 2,
        'ca': pp['ca_storage_loss_weekly'] * 2,
        'frozen': pp['cold_storage_loss_weekly'] * 0.5,
    }
    
    if verbose:
        print("\n" + "="*60)
        print("  📊 基线模型 v2.1 求解结果")
        print("="*60)
    
    # 1. 各项成本
    fixed_total = sum(
        z[j, t, c].X * config.capacity_index[t][c]['fixed_cost'] * 10000
        for j in candidate_ids for t in storage_types
        for c in range(len(config.capacity_index[t]))
    )
    operate_total = sum(
        z[j, t, c].X * config.capacity_index[t][c]['operate_cost'] * 10000
        for j in candidate_ids for t in storage_types
        for c in range(len(config.capacity_index[t]))
    )
    transport_total = sum(
        x[i, j, t].X * demand[i] * config.get_dist(i, j) * 1.2
        for i in demand_ids for j in candidate_ids for t in storage_types
    )
    loss_total = sum(
        x[i, j, t].X * demand[i] * (
            config.get_time(i, j) * pp['transport_loss_per_hour'] +
            storage_loss_rate[t]
        ) * loss_price
        for i in demand_ids for j in candidate_ids for t in storage_types
    )
    carbon_total = sum(
        x[i, j, t].X * demand[i] * config.capacity_index[t][0]['energy_cost_per_ton'] *
        config.capacity_index[t][0]['carbon_factor'] / 1000 * carbon_price
        for i in demand_ids for j in candidate_ids for t in storage_types
    ) + sum(
        x[i, j, t].X * demand[i] * config.get_dist(i, j) * 0.1 / 1000 * carbon_price
        for i in demand_ids for j in candidate_ids for t in storage_types
    )
    
    obj_val = fixed_total + operate_total + transport_total + loss_total + carbon_total
    
    if verbose:
        print(f"\n🎯 总成本: {obj_val:,.0f} 元")
        print(f"   建设成本: {fixed_total:,.0f} 元")
        print(f"   运营成本: {operate_total:,.0f} 元")
        print(f"   运输成本: {transport_total:,.0f} 元")
        print(f"   损耗成本: {loss_total:,.0f} 元")
        print(f"   碳排放成本: {carbon_total:,.0f} 元")

        total = obj_val if obj_val > 0 else 1
        print(f"\n   📈 成本结构:")
        for name, val in [("建设", fixed_total), ("运营", operate_total),
                           ("运输", transport_total), ("损耗", loss_total),
                           ("碳排", carbon_total)]:
            pct = val / total * 100
            bar = "█" * int(pct / 2) + "░" * (25 - int(pct / 2))
            print(f"      {name}: {bar} {pct:.1f}%")
    
    # 2. 冷库选址方案
    if verbose:
        print(f"\n🏗️ 冷库选址方案:")
    opened = []
    for j in candidate_ids:
        for t in storage_types:
            for c in range(len(config.capacity_index[t])):
                if z[j, t, c].X > 0.5:
                    cap_info = config.capacity_index[t][c]
                    sp = config.get_storage_params(t)
                    
                    total_demand = sum(
                        x[i, j, t].X * demand[i] for i in demand_ids
                    )
                    util_rate = total_demand / cap_info['capacity'] * 100
                    
                    if verbose:
                        print(f"   📦 {j}: {sp['name']} | 容量:{cap_info['capacity']}吨 | "
                              f"建设:{cap_info['fixed_cost']}万 | 运营:{cap_info['operate_cost']}万/年 | "
                              f"分配:{total_demand:.1f}吨 | 利用率:{util_rate:.1f}%")
                    opened.append({
                        'site': j, 'type': t, 'type_name': sp['name'],
                        'capacity': cap_info['capacity'],
                        'capacity_idx': c,
                        'fixed_cost': cap_info['fixed_cost'],
                        'operate_cost': cap_info['operate_cost'],
                        'assigned_demand': total_demand,
                        'utilization': util_rate
                    })
    
    if verbose:
        print(f"\n   开放冷库总数: {len(opened)}")
    
    # 3. 分配详情
    if verbose:
        print(f"\n📋 分配详情:")
    for i in demand_ids:
        for j in candidate_ids:
            for t in storage_types:
                if x[i, j, t].X > 0.5:
                    dist = config.get_dist(i, j)
                    ttime = config.get_time(i, j)
                    sp = config.get_storage_params(t)
                    if verbose:
                        print(f"   {i} → {j}({sp['name']}) | "
                              f"产量:{demand[i]:.1f}吨 | 距离:{dist:.1f}km | 时间:{ttime:.2f}h")
    
    # 4. 预冷时间检查
    if verbose:
        print(f"\n⏱️ 预冷时间约束检查:")
    violations = 0
    for i in demand_ids:
        for j in candidate_ids:
            if x[i, j, 'precool'].X > 0.5:
                ttime = config.get_time(i, j)
                if ttime > pp['precool_time_limit_h']:
                    if verbose:
                        print(f"   ❌ {i}→{j}: {ttime:.2f}h > {pp['precool_time_limit_h']}h 违反!")
                    violations += 1
                else:
                    if verbose:
                        print(f"   ✅ {i}→{j}: {ttime:.2f}h ≤ {pp['precool_time_limit_h']}h")
    if violations == 0 and verbose:
        print("   所有预冷时间约束均满足 ✅")
    
    # 5. 碳排放汇总
    if verbose:
        print(f"\n🌱 碳排放汇总:")
    static_c = sum(
        x[i, j, t].X * demand[i] * config.capacity_index[t][0]['energy_cost_per_ton'] *
        config.capacity_index[t][0]['carbon_factor'] / 1000
        for i in demand_ids for j in candidate_ids for t in storage_types
    )
    dynamic_c = sum(
        x[i, j, t].X * demand[i] * config.get_dist(i, j) * 0.1 / 1000
        for i in demand_ids for j in candidate_ids for t in storage_types
    )
    if verbose:
        print(f"   静态碳排放(冷库运营): {static_c:.2f} 吨CO₂/年")
        print(f"   动态碳排放(运输): {dynamic_c:.2f} 吨CO₂/年")
        print(f"   总碳排放: {static_c + dynamic_c:.2f} 吨CO₂/年")
    
    # 6. 损耗汇总
    if verbose:
        print(f"\n📉 损耗汇总:")
    transport_loss = sum(
        x[i, j, t].X * demand[i] * config.get_time(i, j) * pp['transport_loss_per_hour']
        for i in demand_ids for j in candidate_ids for t in storage_types
    )
    storage_loss = sum(
        x[i, j, t].X * demand[i] * storage_loss_rate[t]
        for i in demand_ids for j in candidate_ids for t in storage_types
    )
    if verbose:
        print(f"   运输损耗: {transport_loss:.2f} 吨/年")
        print(f"   存储损耗: {storage_loss:.2f} 吨/年")
        print(f"   总损耗: {transport_loss + storage_loss:.2f} 吨/年 "
              f"({(transport_loss + storage_loss)/sum(demand.values())*100:.1f}%)")
    
    # 7. 与v1对比
    if verbose:
        print(f"\n📊 v1 vs v2.1 对比:")
        print(f"   {'指标':<12} {'v1(缩减9点)':<18} {'v2.1(全部27点)':<18}")
        print(f"   {'-'*48}")
        print(f"   {'候选点数':<12} {'9':<18} {len(candidate_ids):<18}")
        print(f"   {'需求点数':<12} {'39':<18} {len(demand_ids):<18}")
        print(f"   {'容量选择':<12} {'平均值':<18} {'显式等级':<18}")
        print(f"   {'运营成本':<12} {'未计入':<18} {'已计入':<18}")
    
    return {
        'total_cost': obj_val,
        'fixed_cost': fixed_total,
        'operate_cost': operate_total,
        'transport_cost': transport_total,
        'loss_cost': loss_total,
        'carbon_cost': carbon_total,
        'num_facilities': len(opened),
        'facilities': opened,
        'precool_violations': violations,
        'static_carbon': static_c,
        'dynamic_carbon': dynamic_c,
        'transport_loss': transport_loss,
        'storage_loss': storage_loss,
    }


# ============================================================
# 主程序
# ============================================================

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding='utf-8')

    print("="*60)
    print("  🌿 秋葵冷库布局优化 — 单层MIP基线模型 v2.1")
    print("  Week 1, Day 2: Explicit Capacity + gurobipy Direct API")
    print(f"  Gurobi License: {_GUROBI_LICENSE_PATH}")
    print("="*60)
    
    # 加载数据
    config = DataConfig()
    print(f"\n📦 数据加载完成:")
    print(f"   节点数: {len(config.nodes)}")
    print(f"   候选点: {len(config.candidates)} (全部)")
    print(f"   需求点: {len(config.demands)}")
    print(f"   冷库类型: {config.storage_types}")
    print(f"   总产量: {config.nodes['okra_production_ton'].sum():.1f} 吨/年")
    
    # 容量等级
    print(f"\n📊 冷库类型与容量等级:")
    for t in config.storage_types:
        sp = config.get_storage_params(t)
        levels = [f"{c}吨({sp['fixed_cost'][str(int(c))]}万/{sp['operate_cost'][str(int(c))]}万运营)" 
                  for c in sp['capacity_levels']]
        print(f"   {sp['name']}: {', '.join(levels)}")
    
    # 全部候选点！
    all_candidate_ids = list(config.candidates['node_id'])
    all_demand_ids = list(config.demands['node_id'])
    
    print(f"\n🔧 构建单层MIP模型v2.1(全部{len(all_candidate_ids)}候选点 × "
          f"{len(all_demand_ids)}需求点)...")
    
    model, z, x, elapsed = build_and_solve_v2(
        config,
        carbon_price=50.0,
        loss_price=3000.0,
        max_facilities=8,
        candidate_ids=all_candidate_ids,
        demand_ids=all_demand_ids,
        time_limit=300,
        mip_gap=0.01,
        threads=8
    )
    
    # 分析结果
    if model.SolCount > 0:
        analysis = analyze_results(
            model, z, x, config,
            candidate_ids=all_candidate_ids,
            demand_ids=all_demand_ids
        )
        
        # 保存结果
        import pickle
        results_dir = r"D:\秋葵冷库优化项目\results"
        os.makedirs(results_dir, exist_ok=True)
        with open(os.path.join(results_dir, "baseline_v2_1_result.pkl"), 'wb') as f:
            pickle.dump({'analysis': analysis, 'elapsed': elapsed}, f)
        print(f"\n💾 结果已保存到 {results_dir}/baseline_v2_1_result.pkl")
    else:
        print(f"\n❌ 求解失败: 状态={model.Status}")
