# IndusOpt 阶段 3 数据资产与质量诊断

版本：`v0.4.0-data-quality-candidate`

本交付包在阶段 1 工程骨架与阶段 2 仿真/ARX 基线的基础上，完成 A14「IndusOpt 工模智优」阶段 3 的真实 CSV 数据资产、PostgreSQL 版本元数据和工业时序质量诊断后端。

## 交付状态

- 阶段 0–1 的需求、前后端骨架与 API 契约：已完成。
- S1–S5 仿真 CSV、真值 JSON 和版本清单：已实现并可通过 `seed` 重现。
- MISO ARX OLS/Ridge、时间顺序分区、指标、残差与模型结果持久化：已实现。
- CSV 上传、SHA-256 去重、UTF-8/GBK/GB2312 编码和逗号/分号/Tab 识别：已实现。
- PostgreSQL 数据集/版本/列/Profile/处理运行表、真实数据集 API 与质量画像：已实现。
- OpenAPI 3.1.0：已重新导出至 `backend/openapi.json`，并保持已有字段兼容。
- 仍待阶段 4+ 实现：清洗、优选、时滞、共线性和闭环寻优；阶段 3 前端需按交接文档接入真实数据资产 API。

## 文件目录

```text
.
├── README.md
├── PHASE_STATUS.md
├── CHANGELOG.md
├── docker-compose.yml
├── backend
│   ├── app
│   ├── alembic
│   ├── tests
│   ├── Dockerfile
│   ├── pyproject.toml
│   └── openapi.json
└── docs
    ├── api
    │   ├── api-conventions.md
    │   ├── error-codes.md
    │   └── openapi-plan.md
    ├── algorithms
    │   └── algorithm-specification.md
    ├── architecture
    │   ├── data-flow.md
    │   └── system-architecture.md
    ├── handoff
    │   └── PHASE_0_GPT_TO_GEMINI.md
    ├── requirements
    │   ├── official-requirements.md
    │   ├── scope-freeze.md
    │   └── use-cases.md
    └── testing
        └── evaluation-protocol.md
```

## 使用方式

后端的本地启动、测试、OpenAPI 导出和 Docker Compose 说明位于 [`backend/README.md`](backend/README.md)。算法实现与基线结果见 [`docs/algorithms/phase-2-simulation-arx-baseline.md`](docs/algorithms/phase-2-simulation-arx-baseline.md)，前端交接见 [`docs/handoff/PHASE_2_GPT_TO_GEMINI.md`](docs/handoff/PHASE_2_GPT_TO_GEMINI.md)。

建议提交信息：

```bash
git add backend docs docker-compose.yml README.md PHASE_STATUS.md CHANGELOG.md
git commit -m "feat(backend): add phase 3 dataset quality service"
git tag v0.4.0-data-quality
```

在打标签前，必须由前端完成真实上传、列表、Profile 和版本 DAG 的阶段 3 联调。
