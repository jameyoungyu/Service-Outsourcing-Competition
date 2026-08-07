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
- 差异化创新蓝图与算法口径增量（`INNO-1.0` / `ALG-0.2`）：已落盘；创新 1、2 原型已实现并通过 27 个测试与消融实验。
- 仍待阶段 4+ 实现：清洗、优选、时滞、共线性和闭环寻优；阶段 3 前端需按交接文档接入真实数据资产 API。

## 差异化创新

赛题任务清单本身即实现说明书，按字面实现会与其他队伍高度同质化。差异化设计见：

- [`docs/innovation/differentiation-blueprint.md`](docs/innovation/differentiation-blueprint.md)：7 个创新点、评分标准映射、排期增量与降级顺序；
- [`docs/algorithms/algorithm-specification-v2.md`](docs/algorithms/algorithm-specification-v2.md)：相对 `ALG-0.1` 的算法口径增量；
- [`docs/experiments/identifiability-ablation.md`](docs/experiments/identifiability-ablation.md)：10 组种子的消融实验证据。

核心结论（实测，非设想）：

- 以 Fisher 信息 `log det`（D-最优）选段，用 **13.5% 的数据**达到全量数据的辨识精度，且设计矩阵条件数更优；
- 同等预算下常规能量启发式在异构激励场景下**崩溃**（自由仿真 FIT 掉 12.83 个百分点，稳态增益误差 100%）；
- **一步预测 FIT 的区分度仅为自由仿真 FIT 的 1/27.7**，不适合作为闭环寻优的目标函数。

复现：

```bash
cd backend
python -m pytest tests/test_identifiability.py -q
python scripts/benchmark_identifiability.py --repeats 10
```

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
