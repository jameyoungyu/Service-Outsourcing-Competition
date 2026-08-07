# Changelog

本项目采用阶段标签记录竞赛开发过程。

## [Unreleased]

### Added

- 阶段 1 FastAPI、Pydantic v2、SQLAlchemy Async、Alembic、Redis/RQ 工程骨架；
- 统一 JSON 成功/错误信封、request_id、结构化日志、CORS 与健康检查；
- S1-S5 仿真、数据集、预处理、ARX、Optuna、任务和 Copilot 的字段级 OpenAPI 3.1.0 契约；
- Docker Compose 栈和 `0001_operation_logs` PostgreSQL 初始迁移；
- API 约定、错误码字典与后端契约测试。
- 阶段 2 S1–S5 可复现 MISO ARX 仿真、CSV/真值/版本本地产物和污染注入；
- MISO ARX OLS/Ridge、时间顺序分区、指标、残差 ACF、模型结果持久化；
- 阶段 2 算法基线报告和 GPT → Gemini 前端绑定交接文档。
- 阶段 3 真实 CSV multipart 上传、100 MiB 限制、扩展名/MIME 校验、SHA-256 去重和 UTF-8/GBK/GB2312 + 逗号/分号/Tab 自动识别；
- PostgreSQL `datasets`、`dataset_versions`、`dataset_columns`、`dataset_profiles`、`processing_runs` 表及 Alembic `0002_datasets_and_profiles`；
- 数据集列表、详情、配置、Profile、版本 DAG 和删除的真实持久化 API；
- 工业时序质量指标：缺失、连续缺失、重复时间戳、采样间隔、冻结段、IQR 异常、统计特征、评分和建议；
- 阶段 3 GPT → Gemini 前端接入交接文档。

### Verification

- pytest `6 passed`、Ruff、Mypy、OpenAPI JSON 校验通过；
- Docker Compose 镜像构建、依赖健康检查和 Alembic 迁移通过。
- 阶段 2 pytest `17 passed`，涵盖 S1–S5、随机种子重现、无噪声参数恢复、时间顺序与真实 API 闭环。
- 阶段 3 pytest `23 passed`，新增 CSV 异常、GBK/分号识别、去重、真实 Profile、列映射、版本与删除路由测试；PostgreSQL Docker 迁移和 multipart 上传闭环通过。

## [0.1.0-requirements-candidate] - 2026-07-27

### Added

- A14 官方需求和统一评分标准映射；
- 第一版产品范围、数据口径和不做清单；
- Agent 白名单与禁止操作；
- 核心用例；
- 系统架构、数据流和状态机；
- 工业算法规范与统一错误语义；
- 训练/验证/测试防泄漏评测协议；
- OpenAPI 资源规划；
- GPT → Gemini 阶段 0 交接文档；
- 阶段状态记录。

### Not Implemented

- 未创建 backend/frontend 代码；
- 未创建数据库迁移；
- 未生成正式 OpenAPI；
- 未运行代码测试；
- 未完成 Gemini 低保真设计。
