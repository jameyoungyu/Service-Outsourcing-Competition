# 当前阶段状态

## 当前阶段

阶段 3：数据集管理与质量诊断

## 开始时间

2026-07-28

## 当前状态

- [ ] 未开始
- [ ] 设计中
- [ ] 后端开发中
- [ ] 后端测试中
- [ ] 前端开发中
- [ ] 联调中
- [ ] 验收中
- [x] 已完成

## 已完成

- 官方 A14 需求与评分标准拆解；
- MVP 范围和第一版算法口径候选冻结；
- 核心用例、系统架构和数据流；
- 算法规范、评测协议和 OpenAPI 规划；
- GPT → Gemini 阶段 0 交接文档；
- Gemini 完成用户角色、信息架构、流程、低保真原型、设计规范、状态矩阵和图表规划；
- Gemini → GPT 阶段 0 反向交接与接口契约需求文档；
- 后端 FastAPI 工程骨架、Pydantic v2 契约与异步 SQLAlchemy 基础设施；
- 结构化 JSON 日志、UUID `request_id`、CORS、统一成功/错误信封与异常处理；
- 全部阶段 1 路由的字段级 Pydantic Schema 与 `backend/openapi.json`（OpenAPI 3.1.0）；
- PostgreSQL / Redis / RQ Docker Compose 栈与 Alembic `0001_operation_logs` 基线迁移；
- API 约定、错误码字典及 6 个后端契约测试；
- 前端 Vue 3 + Vite + TypeScript + Pinia + Vue Router + Element Plus + ECharts 工程搭建；
- 前端全局 Axios 响应拦截器（封装 Success/Error 信封与 Request ID 诊断）；
- 结合前端状态矩阵的 StateView 组件、ECharts 通用 ChartContainer 组件及 AppHeader/AppSidebar/DefaultLayout 主框架；
- 全部 13 个业务视图及 403/404/500 错误视图的完整骨架搭建；
- 前端 Vitest 单元测试通过及 Vite Production 打包验证通过；
- 真实 S1–S5 MISO ARX 仿真生成器，CSV、真值 JSON 和版本清单本地产物；
- S4 缺失、尖峰、冻结、漂移、不规则与重复时间戳污染注入及真值记录；
- S5 高共线性输入和真实变量依赖关系；
- MISO ARX 滞后矩阵、OLS/Ridge、时间顺序 60/20/20 分区和保护区；
- 真实 RMSE、MAE、R²、NRMSE、FIT、预测序列、残差 ACF 与模型产物；
- 阶段 2 算法测试、API 端到端测试、基线实验报告和 GPT → Gemini 交接文档；
- Gemini 前端页面无缝替换随机 Mock 回退，全量绑定真实数据 Store 与 API；
- 仿真视图增强 Ground Truth 方程预览与 CSV 导出功能，ARX 视图支持动态 `nb`/`delays` 数组传参；
- S1 无噪声无失真闭环验证通过（测试集 FIT > 99.9999%），Gemini → GPT 阶段 2 反向交接文档已落盘；
- 阶段 3 后端：CSV 流式上传、100 MiB 限制、扩展名/MIME 校验、SHA-256 去重、UTF-8/GBK/GB2312 与逗号/分号/Tab 自动识别；
- 阶段 3 后端：Alembic `0002_datasets_and_profiles` 和 `datasets`、`dataset_versions`、`dataset_columns`、`dataset_profiles`、`processing_runs` PostgreSQL 表；
- 阶段 3 后端：真实数据集列表、详情、删除、列配置、质量 Profile 与版本 DAG；
- 阶段 3 后端：缺失/连续缺失、时间范围、采样周期/直方图/不规则率、重复时间戳、冻结段、IQR 异常、统计量、评分和建议；
- 阶段 3 后端：23 个 Pytest、Ruff、Mypy、OpenAPI JSON 与 Docker PostgreSQL multipart 上传/配置/Profile 闭环验证通过；
- 阶段 3 GPT → Gemini 前端接入交接文档已落盘；
- 阶段 3 前端：更新 `src/types/api.ts` 与 `src/api/datasets.ts`，全面支持 multipart 文件上传、真实去重判断、自定义列角色 Schema 配置及版本 DAG 图谱；
- 阶段 3 前端：`DatasetsView.vue` 与 `DatasetDetailView.vue` 彻底同步真实后端数据库列表、统计量矩阵与质量分析报告，全量前端构建与测试通过；
- Gemini → GPT 阶段 3 反向交接文档已落盘。

### 差异化创新增补（INNO-1.0，2026-08-07）

- 官方赛题手册 A14 与初赛评分标准复核，识别同质化风险并定义 7 个差异化创新点：`docs/innovation/differentiation-blueprint.md`；
- 算法口径增量规范 `ALG-0.2` 落盘：`docs/algorithms/algorithm-specification-v2.md`；
- **创新 1 原型完成**：`backend/algorithms/identifiability/` —— Fisher 信息矩阵、`log det` D-最优准则、持续激励阶次判据、矩阵行列式引理增量增益、lazy greedy（CELF）子模最大化窗口优选、energy 对照基线；
- **创新 2 原型完成**：自由仿真、稳态增益、`A(q)` 稳定性判别、残差白度；
- 消融实验执行器 `backend/scripts/benchmark_identifiability.py` 与 10 组种子实验报告 `docs/experiments/identifiability-ablation.md` / `.json`；
- 新增 S6 异构激励仿真场景定义（现有 S1–S5 均为同构激励，无法暴露按能量选段的失效模式）；
- 阶段计划已同步创新增补至阶段 2、5、7、8、9、10、11。

## 未完成

- 阶段 4 预处理清洗、时间规整和动态区间选择；
- 创新 1、2 原型接入服务层与 API（阶段 5、7）；
- 创新 3–7 全部待实现（血缘缓存、策略记忆库、零幻觉报告、合规证明、约束辨识、自评测基准 UI）；
- S6 场景并入 `app/services/simulation_service.py` 并输出标准真值文件；
- `EXP-1.0` §7 遗留实验：完整加权分对照、窗口长度/预算敏感性扫描、公开数据集验证。

## 当前问题

- 阶段 3 已全量完成并验证；阶段 4 将正式接入重采样、线性/前向插值、Hampel/IQR 异常清洗及无标签动态区间筛选算法。
- **待开发者确认**（`INNO-1.0` §12）：是否接受 IDS 取代加权质量分作为阶段 5 主口径、自由仿真 FIT 取代一步预测 FIT 作为阶段 7/8 主指标、新增 S6 场景、+13.5 天排期增量，以及是否启动专利申请。未确认前创新 3–7 不进入正式编码。

## 关键决策

- 第一版采用离散时间 MISO ARX；
- 训练/验证/测试按时间顺序划分；
- 动态区间优选以 Fisher 信息 `log det`（D-最优）为主口径，加权质量分降级为可解释性对照（`ALG-0.2` §2）；
- 模型主指标为自由仿真 FIT，一步预测 FIT 降级为诊断量（`ALG-0.2` §5）；
- 持续激励阶次不足时阻断建模，不降级为警告（`ALG-0.2` §3）；
- 报告中 LLM 不得输出数字字面量，只能输出可溯源占位符（`ALG-0.2` §8）；
- 原始数据不可覆盖，处理形成版本血缘；
- Agent 仅调用白名单工具；
- Optuna 不得使用测试集调参；
- MVP 不依赖登录与复杂权限；
- 长任务采用 Redis + RQ 候选架构。

## 数据库版本

- Alembic Revision：`0002_datasets_and_profiles`

## API 版本

- OpenAPI Version：`3.1.0`，文件：`backend/openapi.json`

## 测试结果

- pytest：`23 passed`（阶段 1 契约、S1–S5 仿真、无噪声 ARX 参数恢复、时间分区、API 真值闭环，以及 CSV 异常、GBK/分号、去重、Profile、配置、版本、删除）；
- Ruff：通过；
- Mypy：通过（34 source files，含质量诊断算法包）；
- OpenAPI JSON：通过 `json.tool` 校验；
- Docker Compose：阶段 3 镜像构建、本地产物卷挂载、PostgreSQL/Redis 就绪、Alembic `0002_datasets_and_profiles (head)` 通过；容器内真实 multipart CSV 上传 → Profile → 列配置闭环通过；
- 前端 Vitest 测试：`3 passed` (Pinia Store、ApiClient & ApiError)；
- 前端 Vite 构建：`built in 462ms` (打包验证成功)；
- 文档完整性检查：通过；
- 创新原型测试：`tests/test_identifiability.py` `27 passed`（回归矩阵口径、无噪参数恢复、PE 阶次教科书标定、行列式引理与直接 `log det` 差一致性、lazy greedy 与朴素贪心逐窗口一致、信息增益单调不增、分区不越界、异构激励下优于 energy、自由仿真无噪精确复现、一步预测掩盖劣质模型、稳态增益解析值、不稳定多项式检出）；
- 创新原型 Ruff 与 Mypy：通过（`algorithms/identifiability`、`scripts/benchmark_identifiability.py`、`tests/test_identifiability.py`）；
- 消融实验：10 组随机种子 × 2 场景（S3/S6）× 3 策略，结果见 `docs/experiments/identifiability-ablation.json`。

## 验收结论

- [x] 通过：阶段 3 真实 CSV 上传、列 Schema 配置、PostgreSQL 数据资产持久化与真实 Profile 诊断报告已通过全量验证，准备进入阶段 4 (数据清洗与时间规整)。
- [ ] 不通过

## 下一阶段进入条件

- 阶段 3 数据资产与质量诊断已通过全量验证 (已满足)；
- 开始阶段 4：数据清洗与时间规整开发。
