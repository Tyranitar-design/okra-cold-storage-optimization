# 秋葵主产区冷库布局与容量优化研究

这是“秋葵冷库优化项目”的 GitHub 精选版，聚焦研究级 MIS 决策展示系统、容量链优化模型、AI warm start / AI-Benders 方法学实验，以及可追溯结果证据。

## 项目定位

本项目面向县域秋葵主产区冷链设施规划，围绕“冷库选址、容量配置、温度链服务、运输成本、损耗与碳排放”构建优化模型，并通过 MIS 系统把离线模型结果转化为可交互的决策驾驶舱。

当前统一口径：

- 主模型：`v3.0 capacity-chain MIP`
- 主求解链条：`direct Gurobi solve`
- AI 增强主证据：`AI-guided warm start`
- 多目标对照：增广 epsilon 约束、NSGA-III、ALNS
- Benders 子线：cut ranking / robustness mechanism study
- 系统定位：研究级 MIS / 答辩展示系统，不宣称为企业生产系统

## 精选版包含内容

```text
.
├── src/                    # FastAPI 后端、模型、算法与证据聚合代码
├── frontend-vue/           # Vue 3 + Vite + Element Plus MIS 前端
├── wechat-miniprogram/     # 移动端/小程序源码，未包含 APK 与私有配置
├── database/               # PostgreSQL / PostGIS schema 与说明
├── alembic/                # 数据库迁移脚本
├── data/                   # 县域案例数据与公开/文件化地理数据
├── experiments/            # 核心实验脚本
├── results/                # 精选 JSON/CSV/MD/PNG 证据，不含大体积 pkl/db/xlsx
├── docs/                   # 方法学、MIS 设计、证据卡与精选报告材料
├── tests/                  # 关键 API / 证据链 / 模型结果回归测试
├── scripts/                # 启动、验收、报告证据生成等辅助脚本
├── Dockerfile
├── docker-compose.yml
├── requirements-api.txt
└── .env.example
```

未包含内容：真实 `.env`、`secrets/`、本地数据库目录、venv、node_modules、dist、APK、部署压缩包、第三方论文全文、临时备份、渲染中间页和大体积求解二进制产物。

## 快速启动

### 1. 后端 API

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-api.txt
python -m uvicorn src.api.main:app --host 127.0.0.1 --port 8014 --reload
```

健康检查：

```text
http://127.0.0.1:8014/health
```

### 2. Vue MIS 前端

```powershell
cd frontend-vue
npm install
npm run dev
```

默认 Vite 地址通常为：

```text
http://127.0.0.1:5173/
```

后端也可服务已构建的前端静态页面，具体以 `src.api.main` 和部署配置为准。

### 3. Docker 演示

```powershell
docker compose up --build
```

Docker 演示主要用于 API + MIS + PostgreSQL/PostGIS 展示；Gurobi 主求解链通常在本地宿主机环境运行，不在轻量容器中强制运行。

## 关键模块

- `src/api/`：FastAPI 后端、证据接口、地图接口、Agent 只读解释接口、MIS 静态资源服务。
- `src/models/`：容量链 MIP、单层模型、求解 profile 等数学模型实现。
- `src/algorithms/`：Benders、AI cut scoring、启发式、warm start、布局评估相关代码。
- `frontend-vue/src/views/`：总览、地图选址、模型说明、求解中心、Pareto、AI 融合、数据证据等 MIS 页面。
- `database/schema.sql`：核心数据库表设计与空间数据支持。
- `experiments/`：Gurobi 直解、AI warm start、Optuna、AI-Benders、NSGA-III/ALNS 等实验脚本。
- `results/experiments/`：精选实验结果摘要和图表，用于复核论文与 MIS 展示口径。

## 证据边界

本仓库保留研究结论的边界说明：

- AI warm start 只提供 MIP Start，最终可行性、目标值和 gap 认证仍由 Gurobi 完成。
- Optuna 用于调参增强，不替代精确优化。
- AI-Benders 当前支持 cut ranking / robustness 机制研究，不写成通用显著加速。
- NSGA-III / ALNS 是同可行域启发式基线，不提供精确最优性证明。
- MIS 是研究展示系统，尚非企业级生产系统。

## 主要文档

- `docs/管理信息系统与数据库设计_v1.md`
- `docs/AI_Benders方法与实验章节_阶段版.md`
- `docs/Optuna_AI_WarmStart_证据卡.md`
- `docs/论文初稿_v3_整合版.md`
- `docs/结题报告数学公式LaTeX汇总_按Word顺序.md`
- `docs/drawio/`
- `docs/solver-evidence-screenshots/`

## 环境变量

复制 `.env.example` 为 `.env` 后填入本地配置。请勿提交真实 `.env`、地图密钥、数据库密码、GitHub token 或服务器凭据。

## 许可说明

本精选版用于课程项目、研究展示与复现实验整理。若需公开复用或二次开发，请先确认数据、第三方依赖和学校/团队要求。
