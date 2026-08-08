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
- 差异化创新蓝图 `INNO-1.0`（7 个创新点、评分标准映射、排期增量与降级顺序）；
- 算法口径增量规范 `ALG-0.2`（D-最优数据优选、持续激励判据、预白化时滞、控制相关验收、约束辨识、血缘缓存、策略记忆库、零幻觉报告、合规证明、6 个新错误码）；
- `algorithms/identifiability` 算法包：ARX 回归矩阵、Fisher 信息与 `log det`、持续激励阶次、矩阵行列式引理增量增益、lazy greedy 子模窗口优选、energy 对照基线、自由仿真、稳态增益、稳定性判别、残差白度；
- 消融实验执行器 `scripts/benchmark_identifiability.py`（多种子聚合、JSON 输出）与实验报告 `EXP-1.0`；
- S6 异构激励仿真场景定义（S1–S5 均为同构激励，无法暴露按能量选段的失效模式）。

### Changed

- 阶段 5 动态区间优选主口径由加权质量分改为 Fisher 信息 D-最优子模优选，加权分降级为可解释性对照；
- 阶段 7/8 模型主指标与闭环目标函数由一步预测 FIT 改为自由仿真 FIT（实测区分度相差 27.7 倍）；
- 阶段 9 Validator 升级为静态数据流分析并出具合规证明；
- 阶段 10 报告生成改为占位符渲染 + 数字字面量校验；
- `pyproject.toml` 的 Ruff `src` 增加 `algorithms`，使首方包导入排序正确。

### Added (phases 4-11, 2026-08-07)

- 阶段 4：`/preprocessing/clean` 接入真实清洗流水线并派生不可变版本；
- 阶段 5：`algorithms/identifiability/gating.py` 质量门控（缺失/异常/稳态/信噪比）与
  `segment_service.py` 质量约束 D-最优优选，门控先于信息准则执行；
- 阶段 5：`app/services/version_data.py` 统一数值视图，上传 CSV 与仿真产物走同一条路径；
- 阶段 6：`delay.py` 预白化互相关 + 验证集自由仿真复核；`collinearity.py` Pearson/Spearman/VIF/条件数；
- 阶段 7：`modeling_service.py` 统一辨识内核，自由仿真 FIT 为主指标，先验（增益符号/区间/稳定性）为硬约束；
- 阶段 8：`optimization_service.py` 分级闭环寻优、血缘缓存、策略记忆库热启动；
  新增 `optimization_studies` / `optimization_trials` / `strategy_memory` 表与 Alembic `0003`；
- 阶段 9：`algorithms/agent/` 意图解析、白名单计划与机器可检验合规证明；`agent_service.py` 四层编排；
- 阶段 10：`algorithms/report/provenance.py` 数值溯源绑定（LLM 禁写数字）与 `report_service.py` 报告/导出；
- 阶段 11：`benchmark_service.py` 产品内一键自评测基准；`S6` 异构激励场景并入仿真服务；
- 新增 API：`/reports/generate`、`/delivery/export`、`/benchmark/run`；
- 前端：清洗、优选、时滞、共线性、辨识、寻优、Agent、交付、基准共 9 个视图改为真实数据绑定，
  新增「一键自评测基准」页面；全部 mock 回退已删除。

### Changed (phases 4-11)

- 闭环搜索由扁平采样改为分级搜索：采样器探索昂贵的门控/优选头部，每个 trial 对单次优选结果
  扫描完整模型结构网格。实测昂贵环节摊薄 24 倍，最优自由仿真 FIT 由 95.12 提升至 97.86；
- 门控阈值在搜索空间中量化（实测扁平采样下内容寻址缓存命中率为 0%，量化后 120 trial 仅 1.7%，
  据实上报，真正的节省来自分级搜索）；
- `free_run_simulate` 增加发散钳位，不稳定模型给出有限的差评分而非溢出为 inf；
- 合规校验 `high_impact_confirmed` 改为 `high_impact_gated`：证明的性质是"高影响操作不会未经批准执行"，
  而非"一切已预先批准"，否则工程师无法先看到支撑决策的诊断结果；
- `identification_service` 由 452 行缩减至 183 行，委托给统一内核。

### Fixed (phases 4-11)

- `write_derived_csv` 会对时间戳列做长度校验，而该列由 `timestamps` 重新生成、从不读自 `values`，
  导致每次派生版本写入都抛 `KeyError`；
- 稳态参考尺度取自逐样本差分，在 90% 稳态的记录上恒为 0，使所有窗口都被判为"活跃"；改为窗口活跃度的分位数；
- 报告按外键筛选运行记录时找不到 S1–S6 基准的运行（这些版本在 `dataset_versions` 中无行，外键为空），
  改为同时匹配运行记录自身的参数；
- 数字校验的列表标记豁免要求尾随空格，导致中文枚举「3、第三条」被误判为未绑定数据；
- `algorithms/cleaning/pipeline.py` 中循环变量在两种元素类型间复用引发的类型错误。

### Verification

- pytest `6 passed`、Ruff、Mypy、OpenAPI JSON 校验通过；
- Docker Compose 镜像构建、依赖健康检查和 Alembic 迁移通过。
- 阶段 2 pytest `17 passed`，涵盖 S1–S5、随机种子重现、无噪声参数恢复、时间顺序与真实 API 闭环。
- 阶段 3 pytest `23 passed`，新增 CSV 异常、GBK/分号识别、去重、真实 Profile、列映射、版本与删除路由测试；PostgreSQL Docker 迁移和 multipart 上传闭环通过。
- 创新原型 pytest `27 passed`（`tests/test_identifiability.py`），Ruff 与 Mypy 通过；消融实验覆盖 10 组随机种子 × 2 场景 × 3 策略。
- 阶段 4–11：后端 pytest `185 passed`，Ruff 与 Mypy 全部通过（65 个源文件）；
  前端 Vite 构建通过、`vue-tsc --noEmit` 退出码 0、Vitest `3 passed`；
  Alembic 单一 head `0003_optimization_and_memory`；
  Docker Compose 因本开发环境无 Docker 守护进程未实机验证（见 PHASE_STATUS）。

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
