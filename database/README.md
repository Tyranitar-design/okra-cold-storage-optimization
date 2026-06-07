# Database Layer

本目录存放秋葵冷库优化管理信息系统的数据库设计与初始化说明。

## 文件

| 文件 | 用途 |
| --- | --- |
| `schema.sql` | PostgreSQL/PostGIS 可执行 schema |
| `../src/api/database/alembic.ini` | Alembic 配置入口 |
| `../src/api/database/env.py` | Alembic 运行环境 (raw SQL 模式) |
| `../src/api/database/versions/` | 迁移版本文件目录 |
| `seed_from_current_files.md` | 如何从当前 CSV/PKL/JSON 结果导入数据库 |
| `../scripts/seed_postgres_from_current_files.py` | 从当前项目文件 dry-run 审计或 upsert 写入 PostgreSQL |

## 推荐数据库

- PostgreSQL 15+
- PostGIS 3+

如果本机 PostgreSQL 暂时未启动，当前 FastAPI 仍可继续读取文件结果运行；数据库层先作为后续 MIS 升级的稳定契约。**只有显式配置 `OKRA_DATABASE_URL` 时，API 才会启用数据库模式。**

## 连通性探测

FastAPI 提供独立探测接口：

```powershell
GET /api/v1/db/probe
```

该接口会返回 `probe_attempted`、`probe_ok`、`probe_current_database`、`probe_current_user` 和 `probe_elapsed_ms` 等字段，用于区分“已配置连接串”和“已真实连通数据库”。前端 MIS 的数据库状态面板会优先展示该探测结果。

## 入库预览

在真正执行 `--apply` 前，系统还提供只读预览：

```powershell
GET /api/v1/db/seed-preview
```

该接口会返回 `total_rows`、`table_counts`、`non_empty_tables`、`sql_preview` 和 `seed_items`，用于在写库前审计行数和目标表分布。它只说明预计导入规模，不代表数据库已经实际写入。

## 当前导入状态

已具备两种模式：

```powershell
python scripts/seed_postgres_from_current_files.py --dry-run
```

只审计当前文件可导入的行数，不连接数据库。

```powershell
$env:OKRA_DATABASE_URL="postgresql+psycopg://okra_user:password@127.0.0.1:5432/okra_cold_storage"
python scripts/seed_postgres_from_current_files.py --apply --init-schema
```

执行 `database/schema.sql` 并按稳定主键/upsert 导入当前项目文件。当前写入范围包括证据源、文献占位、节点、候选点、冷库类型、容量参数、距离/时间矩阵、基线实验、Benders cut-ranking 对比实验、灵敏度结果、SPO smoke、方法 smoke、Benders cut score 和参数证据。

注意：`--apply` 只表示把已验证文件资产写入 PostgreSQL；不等同于已经接入真实企业数据，也不改变论文中的证据边界。

若 `probe_ok` 为 `false`，应先检查 `OKRA_DATABASE_URL`、`psycopg` 驱动和 PostgreSQL 服务，再执行 `--apply`。

## 真实外部数据扩展表

`schema.sql` 已预留 P0 真实数据接入表：

| 表 | 来源 | 用途 | 当前边界 |
| --- | --- | --- | --- |
| `okra.market_price_observations` | 农业农村部数据平台 / 重点农产品市场信息平台 | 价格情景、损耗价值、市场侧敏感性 | schema-ready，尚未下载或入库 |
| `okra.weather_daily_observations` | 中国气象数据网 / ERA5-Land | 温湿度、降水、极端天气与 SPO 特征 | schema-ready，尚未下载或入库 |
| `okra.osm_features` | Overpass API / OpenStreetMap | 地图图层、POI、仓储/市场候选要素 | schema-ready，尚未下载或入库 |
| `okra.road_network_edges` | Overpass API / OpenStreetMap | 路网边、道路等级、时间矩阵校正 | schema-ready，尚未下载或入库 |

这些表对应 `docs/真实数据字段映射与入库验收清单_v1.md`。正式写入前必须先保留原始文件或 raw JSON，并在 `docs/data_evidence_registry.csv` 中登记新的运行证据。没有 raw 文件、清洗产物和 `probe_ok=true` 的写库记录时，论文中只能表述为“真实数据接入表结构与质量闸门已建立”，不能表述为“真实数据已接入”。

此外，`scripts/seed_postgres_from_current_files.py` 已把这四张表加入 seed-preview / apply 预留链路。由于当前 `data/raw/...` 与 `data/processed/real_data/...` 目录中还没有对应文件，`seed-preview` 对这四张表返回 0 行是预期结果，不是遗漏；这意味着系统已经能识别目标表，但不会伪造数据。
