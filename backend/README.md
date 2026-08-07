# IndusOpt Backend

阶段 3 后端实现，使用 FastAPI、Pydantic v2、SQLAlchemy Async、Alembic、PostgreSQL 与 Redis/RQ。它包含可复现的 S1-S5 仿真、真实 MISO ARX（OLS/Ridge）基线，以及真实 CSV 数据资产与质量诊断服务。

## 本地运行

需要 Python 3.11 或更高版本：

```bash
cd backend
python3.11 -m venv .venv
.venv/bin/pip install -e '.[dev]'
.venv/bin/uvicorn app.main:app --reload
```

本地 Uvicorn 默认监听 `http://127.0.0.1:8000`，OpenAPI 位于 `/openapi.json`。

```bash
cd backend
.venv/bin/pytest
.venv/bin/ruff check .
.venv/bin/mypy app
.venv/bin/python scripts/export_openapi.py
```

完整本地依赖栈：

```bash
docker compose up --build
```

Compose 默认将 API 暴露在 `http://127.0.0.1:18000`，避免与本机已有开发服务冲突；可用
`INDUSOPT_BACKEND_PORT=8000 docker compose up --build` 覆盖。

运行迁移：

```bash
cd backend
alembic upgrade head
```

`backend/openapi.json` 是前端接口的机器可读来源。阶段 3 已把上传、数据集列表/详情、字段配置、Profile 和版本 DAG 替换为 PostgreSQL 持久化实现；预处理、Optuna 与 Copilot 仍保留稳定的契约骨架，等待对应后续阶段替换。

## 阶段 2 真实算法

`POST /api/v1/simulation/generate` 会将 CSV、真值 JSON 和版本清单写入 `backend/data/simulation/`；`POST /api/v1/modeling/arx/fit` 读取生成版本并将模型参数和指标写入 `backend/data/models/`。这些运行产物不纳入 Git，能通过固定 `seed` 重现。

ARX 严格按时间顺序分为 60% 训练、20% 验证、20% 测试，且在边界两侧移除 `max_lag` 保护区。真实算法说明和实验基线见 [`../docs/algorithms/phase-2-simulation-arx-baseline.md`](../docs/algorithms/phase-2-simulation-arx-baseline.md)。

## 阶段 3 数据资产与质量诊断

`POST /api/v1/datasets/upload` 流式接收单个 CSV（100 MiB 上限），校验扩展名/MIME、计算 SHA-256 去重，自动识别 UTF-8/GBK/GB2312 和逗号、分号或 Tab 分隔符。原文件只会首次写入 `data/uploads/{dataset_id}_raw.csv`，后续读取、预览和 Profile 都只读该文件。

上传会同步写入 PostgreSQL 的 `datasets`、`dataset_versions`、`dataset_columns`、`dataset_profiles` 和 `processing_runs` 表（迁移 `0002_datasets_and_profiles`）。响应仍为既有的 `202 + parse_task` 信封，但 `parse_task.status` 已为 `succeeded`。数据画像包括缺失、连续缺失、时间范围、采样间隔直方图、不规则率、重复时间戳、冻结段、IQR 候选异常、统计量、评分和建议。

列语义通过 `POST /api/v1/datasets/{dataset_id}/config` 确认。请求必须最终拥有一个时间列、至少一个输入列和一个输出列；请求体和前端适配说明见 [`../docs/handoff/PHASE_3_GPT_TO_GEMINI.md`](../docs/handoff/PHASE_3_GPT_TO_GEMINI.md)。
