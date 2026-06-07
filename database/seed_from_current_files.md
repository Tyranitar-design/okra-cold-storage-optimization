# 从当前项目文件导入 PostgreSQL 的种子流程

更新日期：2026-05-27

本文件描述如何把当前已经验证过的文件资产导入 `okra` schema。当前阶段已补充 Python 导入脚本，支持 dry-run 审计和 PostgreSQL upsert 写入。

## 1. 初始化 schema

```powershell
psql "$env:OKRA_DATABASE_URL" -f database/schema.sql
```

也可以由种子脚本在写入前自动执行：

```powershell
python scripts/seed_postgres_from_current_files.py --apply --init-schema
```

`OKRA_DATABASE_URL` 示例：

```text
postgresql://okra_user:password@127.0.0.1:5432/okra_cold_storage
```

## 2. 数据源登记

导入文件：

```text
docs/data_evidence_registry.csv
```

目标表：

```text
okra.data_sources
```

主键为 `source_id`。重复导入时应使用 upsert。

## 3. 节点与候选点

导入文件：

```text
data/nodes.csv
```

目标表：

```text
okra.nodes
okra.candidate_sites
```

规则：

1. 每一行导入 `okra.nodes`。
2. `is_candidate = true` 的行额外导入 `okra.candidate_sites`。
3. `source_id` 使用 `DS-C-001`。

## 4. 距离矩阵与运输时间矩阵

导入文件：

```text
data/distance_matrix.csv
data/transport_time_matrix.csv
```

目标表：

```text
okra.distance_matrix
okra.transport_time_matrix
```

规则：

1. 宽表矩阵需要展开为 `(origin_node_id, destination_node_id, value)` 长表。
2. 距离矩阵 source_id 使用 `DS-C-002`。
3. 运输时间矩阵 source_id 使用 `DS-C-003`。

## 5. 冷库类型与容量参数

导入文件：

```text
data/params.json
```

目标表：

```text
okra.cold_storage_types
okra.capacity_options
okra.parameter_evidence
```

规则：

1. `cold_storage_types` 下每个 type 导入一行。
2. `capacity_levels` 与 `fixed_cost` / `operate_cost` / `variable_cost` 展开到 `capacity_options`。
3. 金额保留原始“万元”单位字段，同时模型层继续负责换算为元。
4. source_id 使用 `DS-CD-004`。

## 6. 基线结果

导入文件：

```text
results/baseline_v2_1_result.pkl
```

目标表：

```text
okra.optimization_experiments
okra.optimization_runs
okra.solution_metrics
okra.solution_facilities
```

推荐 experiment_key：

```text
baseline_v2_1_39_nodes_27_candidates
```

## 7. 场景与灵敏度结果

导入文件：

```text
results/experiments/scenarios/scenario_comparison.csv
results/experiments/sensitivity/sensitivity_all.csv
```

目标表：

```text
okra.optimization_experiments
okra.optimization_runs
okra.solution_metrics
okra.sensitivity_results
```

## 8. 方法层结果

导入文件：

```text
results/experiments/method_smoke/method_smoke_summary.csv
results/spo_smoke/spo_summary.json
```

目标表：

```text
okra.optimization_experiments
okra.optimization_runs
okra.spo_training_runs
```

注意：这些当前是 smoke test，不应在论文中作为完整算法优势证据。

## 9. 后续导入脚本要求

当前 Python seed 脚本：

```powershell
python scripts/seed_postgres_from_current_files.py --dry-run
```

会输出当前文件可导入的行数，用于审计，不连接数据库。最近一次验证的核心行数包括：

| 目标 | 行数 |
| --- | ---: |
| `okra.data_sources` | 12 |
| `okra.nodes` | 39 |
| `okra.candidate_sites` | 27 |
| `okra.distance_matrix` | 1521 |
| `okra.transport_time_matrix` | 1521 |
| `okra.optimization_experiments` | 2 |
| `okra.optimization_runs` | 7 |
| `okra.sensitivity_results` | 23 |
| `okra.spo_training_runs` | 1 |
| `okra.method_runs` | 5 |
| `okra.ai_benders_cut_scores` | 14 |
| `okra.parameter_evidence` | 16 |

真实写库命令：

```powershell
$env:OKRA_DATABASE_URL="postgresql://okra_user:password@127.0.0.1:5432/okra_cold_storage"
python scripts/seed_postgres_from_current_files.py --apply --init-schema
```

当前 Python seed 脚本已满足：

1. 幂等：重复运行不会重复插入。
2. 保留 source_id。
3. 每一步输出导入数量；遇到异常会显式中断，不静默跳过。
4. 对金额单位做显式记录。
5. 对缺失字段不虚构填补。

仍需继续增强：

1. 对矩阵维度做更严格校验。
2. 对异常行输出更细的 warning 文件。
3. 接入真实 PostgreSQL 后补一轮 `--apply` 运行截图/日志。
4. 后续如接真实企业数据，必须新增 source_id 和许可/脱敏说明。

## 10. 真实外部数据扩展

从 2026-05-27 起，seed 流程已经预留真实外部数据的四张扩展表和对应的 `SeedItem`：

```text
okra.market_price_observations
okra.weather_daily_observations
okra.osm_features
okra.road_network_edges
```

它们分别对应农业农村部价格、中国气象/ERA5、Overpass/OSM 路网与 POI 数据。当前 seed-preview 仅会把这些条目标记为 0 行，因为 `data/raw/...` 与 `data/processed/real_data/...` 目录下尚未提供对应 raw/cleaned 文件；这种 0 行状态是正确的，表示系统已经认识到目标表，但没有伪造数据。

当后续真实数据文件到位时，优先顺序应是：

1. 下载或导出 raw 文件并保留原始副本。
2. 运行清洗脚本或人工清洗生成 cleaned 文件。
3. 通过 `scripts/validate_real_data_ingestion_files.py` 检查必需列。
4. 在 `probe_ok=true` 且数据库可连通后执行 `--apply --init-schema`。

没有 raw/cleaned 文件时，seed-preview 中这四张表维持 0 行，不影响现有基线、SPO 或 AI-Benders 的文件导入逻辑。

补充说明：`okra.market_price_observations` 的唯一键采用 `(source_id, observation_date, commodity_name, market_name, province)`，其中 `market_name` 与 `province` 在种子链路里默认空字符串，以保证即使来源页不提供完整市场维度，也能稳定去重和 upsert。对应的 SQL `ON CONFLICT` 也已与这组普通列唯一键对齐，不再使用表达式写法。
