"""
秋葵主产区冷库布局与容量优化 — 数据处理模块
Data processing for Okra Cold Storage Layout Optimization

Phase 0: 基于Huang(2025)数据结构构建数据集
"""

import pandas as pd
import numpy as np
from dataclasses import dataclass, field
from typing import List, Dict, Tuple, Optional
import json
import os

# ============================================================
# 秋葵采后保鲜参数（基于文献）
# ============================================================

@dataclass
class OkraPreservationParams:
    """秋葵采后保鲜参数 — 基于采后生理学文献"""
    # 温度参数
    ambient_temp: float = 35.0          # 采摘时环境温度(°C)
    precool_temp_range: Tuple = (0, 5)   # 预冷温度区间(°C)
    cold_storage_temp_range: Tuple = (2, 8)  # 冷藏温度区间(°C)
    ca_storage_temp_range: Tuple = (2, 5)    # 气调温度区间(°C)
    frozen_temp_range: Tuple = (-25, -18)    # 冷冻温度区间(°C)
    
    # 时间参数
    precool_time_limit: float = 2.0      # 采后预冷时限(h) — 硬约束！
    cold_storage_days: Tuple = (7, 14)    # 冷藏保鲜天数
    ca_storage_days: Tuple = (20, 30)     # 气调保鲜天数
    frozen_storage_days: Tuple = (30, 90) # 冷冻保鲜天数
    ambient_browning_hours: Tuple = (6, 12)  # 常温褐变时间(h)
    
    # 损耗参数
    precool_loss_rate: float = 0.01       # 预冷损耗率(1%)
    cold_storage_loss_weekly: float = 0.03  # 冷藏每周损耗率(3%)
    ca_storage_loss_weekly: float = 0.015   # 气调每周损耗率(1.5%)
    transport_loss_per_hour: float = 0.02   # 常温运输每小时损耗(2%)
    
    # 呼吸热
    respiration_heat: float = 150.0       # 呼吸热 kJ/(kg·d)
    
    # 损耗成本函数参数（Fujiwara指数模型）
    loss_alpha_1: float = 0.8            # 一级→二级损耗系数α
    loss_alpha_2: float = 0.4            # 二级→三级损耗系数α
    loss_beta_1: float = 0.15            # 一级→二级损耗系数β
    loss_beta_2: float = 0.08            # 二级→三级损耗系数β


# ============================================================
# 冷库类型参数
# ============================================================

@dataclass
class ColdStorageType:
    """冷库类型参数"""
    type_id: str               # 类型编号
    type_name: str             # 类型名称
    temp_range: Tuple          # 温度区间(°C)
    capacity_levels: List[float]  # 可选容量等级(吨)
    fixed_cost: Dict[float, float]  # 容量→固定建设成本(万元)
    variable_cost: Dict[float, float]  # 容量→单位可变成本(元/吨)
    operate_cost: Dict[float, float]   # 容量→年运营成本(万元)
    energy_cost_per_ton: float  # 制冷能耗(元/吨/天)
    carbon_factor: float        # 碳排放因子(kgCO₂/吨/天)


# 预定义四种冷库类型
COLD_STORAGE_TYPES = {
    "precool": ColdStorageType(
        type_id="precool", type_name="预冷库",
        temp_range=(0, 5),
        capacity_levels=[5, 10, 20, 50],
        fixed_cost={5: 8, 10: 14, 20: 24, 50: 52},
        variable_cost={5: 1600, 10: 1400, 20: 1200, 50: 1000},
        operate_cost={5: 2.4, 10: 4.0, 20: 6.8, 50: 14.0},
        energy_cost_per_ton=3.5,
        carbon_factor=0.8
    ),
    "cold": ColdStorageType(
        type_id="cold", type_name="冷藏库",
        temp_range=(2, 8),
        capacity_levels=[10, 30, 50, 100, 200],
        fixed_cost={10: 18, 30: 42, 50: 65, 100: 110, 200: 190},
        variable_cost={10: 1500, 30: 1300, 50: 1200, 100: 1000, 200: 800},
        operate_cost={10: 4.5, 30: 10.0, 50: 15.0, 100: 26.0, 200: 42.0},
        energy_cost_per_ton=2.8,
        carbon_factor=0.6
    ),
    "ca": ColdStorageType(
        type_id="ca", type_name="气调库",
        temp_range=(2, 5),
        capacity_levels=[10, 30, 50, 100],
        fixed_cost={10: 35, 30: 80, 50: 120, 100: 200},
        variable_cost={10: 2800, 30: 2500, 50: 2200, 100: 1800},
        operate_cost={10: 8.0, 30: 18.0, 50: 26.0, 100: 45.0},
        energy_cost_per_ton=4.0,
        carbon_factor=0.9
    ),
    "frozen": ColdStorageType(
        type_id="frozen", type_name="冷冻库",
        temp_range=(-25, -18),
        capacity_levels=[20, 50, 100, 200],
        fixed_cost={20: 30, 50: 60, 100: 100, 200: 170},
        variable_cost={20: 1600, 50: 1400, 100: 1200, 200: 1000},
        operate_cost={20: 6.0, 50: 12.0, 100: 20.0, 200: 34.0},
        energy_cost_per_ton=3.2,
        carbon_factor=0.7
    ),
}


# ============================================================
# 产区节点数据结构
# ============================================================

@dataclass
class ProductionNode:
    """产地节点"""
    node_id: str
    name: str
    level: int                    # 1=村, 2=乡镇, 3=县
    lat: float                    # 纬度
    lon: float                    # 经度
    okra_production: float        # 秋葵产量(吨/年)
    is_candidate: bool = True     # 是否为冷库候选点
    population: float = 0         # 服务人口
    road_access: bool = True      # 是否有公路通达


# ============================================================
# 数据集生成器
# ============================================================

class OkraDatasetGenerator:
    """秋葵冷库优化数据集生成器"""
    
    def __init__(self, params: OkraPreservationParams = OkraPreservationParams()):
        self.params = params
        self.nodes: List[ProductionNode] = []
        self.distance_matrix: Optional[np.ndarray] = None
    
    def generate_j_county_data(self, n_villages: int = 30, n_towns: int = 8, n_county: int = 1):
        """
        生成湖南省J县模拟数据集
        基于Huang(2025)的J县行政结构
        """
        np.random.seed(42)
        self.nodes = []
        node_counter = 0
        
        # 县级节点(1个)
        for i in range(n_county):
            self.nodes.append(ProductionNode(
                node_id=f"C{i+1}",
                name=f"J县县城",
                level=3,
                lat=29.35 + np.random.uniform(-0.05, 0.05),  # J县大致纬度
                lon=111.68 + np.random.uniform(-0.05, 0.05),  # J县大致经度
                okra_production=np.random.uniform(50, 100),
                is_candidate=True,
                population=np.random.uniform(80000, 120000)
            ))
            node_counter += 1
        
        # 乡镇级节点(8个)
        for i in range(n_towns):
            self.nodes.append(ProductionNode(
                node_id=f"T{i+1}",
                name=f"乡镇{i+1}",
                level=2,
                lat=29.35 + np.random.uniform(-0.3, 0.3),
                lon=111.68 + np.random.uniform(-0.3, 0.3),
                okra_production=np.random.uniform(20, 60),
                is_candidate=True,
                population=np.random.uniform(15000, 40000)
            ))
            node_counter += 1
        
        # 村级节点(30个)
        for i in range(n_villages):
            self.nodes.append(ProductionNode(
                node_id=f"V{i+1}",
                name=f"村{i+1}",
                level=1,
                lat=29.35 + np.random.uniform(-0.4, 0.4),
                lon=111.68 + np.random.uniform(-0.4, 0.4),
                okra_production=np.random.uniform(2, 15),
                is_candidate=np.random.random() > 0.3,  # 70%为候选点
                population=np.random.uniform(500, 3000)
            ))
            node_counter += 1
        
        # 生成距离矩阵(基于经纬度的近似距离)
        self._compute_distance_matrix()
        
        return self
    
    def _compute_distance_matrix(self):
        """基于经纬度计算距离矩阵(近似公路距离)"""
        n = len(self.nodes)
        self.distance_matrix = np.zeros((n, n))
        
        for i in range(n):
            for j in range(n):
                if i != j:
                    # Haversine近似
                    lat1, lon1 = np.radians(self.nodes[i].lat), np.radians(self.nodes[i].lon)
                    lat2, lon2 = np.radians(self.nodes[j].lat), np.radians(self.nodes[j].lon)
                    dlat = lat2 - lat1
                    dlon = lon2 - lon1
                    a = np.sin(dlat/2)**2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon/2)**2
                    c = 2 * np.arcsin(np.sqrt(a))
                    straight_dist = 6371 * c  # km
                    
                    # 公路距离约为直线距离的1.3-1.5倍
                    road_factor = np.random.uniform(1.3, 1.5)
                    self.distance_matrix[i][j] = straight_dist * road_factor
    
    def compute_transport_time(self, avg_speed: float = 40.0) -> np.ndarray:
        """计算运输时间矩阵(小时)"""
        return self.distance_matrix / avg_speed
    
    def to_dataframe(self) -> pd.DataFrame:
        """导出节点数据为DataFrame"""
        return pd.DataFrame([
            {
                'node_id': n.node_id,
                'name': n.name,
                'level': n.level,
                'level_name': {1: '村级', 2: '乡镇级', 3: '县级'}[n.level],
                'lat': n.lat,
                'lon': n.lon,
                'okra_production_ton': n.okra_production,
                'is_candidate': n.is_candidate,
                'population': n.population,
                'road_access': n.road_access
            }
            for n in self.nodes
        ])
    
    def save_dataset(self, output_dir: str):
        """保存数据集到文件"""
        os.makedirs(output_dir, exist_ok=True)
        
        # 节点数据
        df = self.to_dataframe()
        df.to_csv(os.path.join(output_dir, 'nodes.csv'), index=False, encoding='utf-8-sig')
        df.to_excel(os.path.join(output_dir, 'nodes.xlsx'), index=False)
        
        # 距离矩阵
        if self.distance_matrix is not None:
            node_ids = [n.node_id for n in self.nodes]
            dist_df = pd.DataFrame(self.distance_matrix, index=node_ids, columns=node_ids)
            dist_df.to_csv(os.path.join(output_dir, 'distance_matrix.csv'), encoding='utf-8-sig')
            
            # 运输时间矩阵
            time_matrix = self.compute_transport_time()
            time_df = pd.DataFrame(time_matrix, index=node_ids, columns=node_ids)
            time_df.to_csv(os.path.join(output_dir, 'transport_time_matrix.csv'), encoding='utf-8-sig')
        
        # 保鲜参数
        params_dict = {
            'okra_preservation': {
                'precool_time_limit_h': self.params.precool_time_limit,
                'cold_storage_days': list(self.params.cold_storage_days),
                'ca_storage_days': list(self.params.ca_storage_days),
                'frozen_storage_days': list(self.params.frozen_storage_days),
                'precool_loss_rate': self.params.precool_loss_rate,
                'cold_storage_loss_weekly': self.params.cold_storage_loss_weekly,
                'ca_storage_loss_weekly': self.params.ca_storage_loss_weekly,
                'transport_loss_per_hour': self.params.transport_loss_per_hour,
                'loss_alpha_1': self.params.loss_alpha_1,
                'loss_alpha_2': self.params.loss_alpha_2,
                'loss_beta_1': self.params.loss_beta_1,
                'loss_beta_2': self.params.loss_beta_2,
            },
            'cold_storage_types': {
                k: {
                    'name': v.type_name,
                    'temp_range': list(v.temp_range),
                    'capacity_levels': v.capacity_levels,
                    'fixed_cost': v.fixed_cost,
                    'variable_cost': v.variable_cost,
                    'operate_cost': v.operate_cost,
                    'energy_cost_per_ton': v.energy_cost_per_ton,
                    'carbon_factor': v.carbon_factor,
                }
                for k, v in COLD_STORAGE_TYPES.items()
            }
        }
        with open(os.path.join(output_dir, 'params.json'), 'w', encoding='utf-8') as f:
            json.dump(params_dict, f, ensure_ascii=False, indent=2)
        
        print(f"[OK] Dataset saved to {output_dir}/")
        print(f"   - nodes.csv/xlsx ({len(self.nodes)}个节点)")
        print(f"   - distance_matrix.csv")
        print(f"   - transport_time_matrix.csv")
        print(f"   - params.json")


# ============================================================
# 主程序
# ============================================================

if __name__ == "__main__":
    # 生成J县数据集
    gen = OkraDatasetGenerator()
    gen.generate_j_county_data(n_villages=30, n_towns=8, n_county=1)
    gen.save_dataset("D:/秋葵冷库优化项目/data")
    
    # 打印数据摘要
    df = gen.to_dataframe()
    print("\n=== Data Summary ===")
    print(f"总节点数: {len(df)}")
    print(f"村级: {len(df[df.level==1])} | 乡镇级: {len(df[df.level==2])} | 县级: {len(df[df.level==3])}")
    print(f"候选点: {df.is_candidate.sum()}")
    print(f"秋葵总产量: {df.okra_production_ton.sum():.1f} 吨/年")
    print(f"\n各层级产量分布:")
    for level, name in [(1, '村级'), (2, '乡镇级'), (3, '县级')]:
        subset = df[df.level == level]
        print(f"  {name}: {len(subset)}个节点, 产量{subset.okra_production_ton.sum():.1f}吨/年, "
              f"候选点{subset.is_candidate.sum()}个")
