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
- 大模型接入：`algorithms/agent/llm.py`（OpenAI 兼容 Provider，覆盖 DeepSeek / Ollama / vLLM /
  Xinference / 自建 ChatGLM·LLaMA）与 `algorithms/agent/llm_planner.py`（LLM 计划与报告结论撰写）；
  未配置 Provider 时系统完整可用，这是离线部署的默认状态而非降级；
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
- `identification_service` 由 452 行缩减至 183 行，委托给统一内核；
- Agent 计划改由大模型提议、规则实现兜底：大模型计划须通过与规则计划**完全相同**的白名单、
  DAG、时序与合规静态校验，不通过即回退并在响应中给出原因；
  `requires_confirmation` 一律取自白名单而非模型输出，模型无法借此解锁未确认的导出；
- 报告结论段落改由大模型撰写，但被禁止书写任何数字：草稿经数值校验，含未溯源数字即拒绝并要求重写，
  连续 3 次不合规回退到模板化结论。

### Fixed (phases 4-11)

- `write_derived_csv` 会对时间戳列做长度校验，而该列由 `timestamps` 重新生成、从不读自 `values`，
  导致每次派生版本写入都抛 `KeyError`；
- 稳态参考尺度取自逐样本差分，在 90% 稳态的记录上恒为 0，使所有窗口都被判为"活跃"；改为窗口活跃度的分位数；
- 报告按外键筛选运行记录时找不到 S1–S6 基准的运行（这些版本在 `dataset_versions` 中无行，外键为空），
  改为同时匹配运行记录自身的参数；
- 数字校验的列表标记豁免要求尾随空格，导致中文枚举「3、第三条」被误判为未绑定数据；
- `algorithms/cleaning/pipeline.py` 中循环变量在两种元素类型间复用引发的类型错误。

### Added (2026-08-08)

- `algorithms/identifiability/weighted_score.py`：`ALG-0.1` §6.2 完整加权质量分按原始权重实现，
  作为数据优选的第三条对照基线（此前只对照"纯输入变化能量"，属于稻草人对照）；
  权重由测试锁定，任何为让对照难看而调权的改动都会让测试失败；
- 自评测基准新增 `weighted` 策略与 `rank_deficient` 秩状态列；前端基准表格策略名改为中文全称、
  秩状态以标签渲染；
- 实验报告修订为 `EXP-1.1` 与 `EXP-2.1`，补入 10 组种子的 `weighted` 对照数据。

### Changed (2026-08-08)

- **实测推翻了 `EXP-1.0` §7 的预判**：原文写"完整加权分表现应优于 energy，但核心缺陷不变"，
  实测是连"优于"都没有发生——S6 上参数误差 14.81 ± 0.06% vs energy 的 14.82 ± 0.07%，
  自由仿真 FIT 同为 77.05 ± 2.65，同样秩亏。原因是干净数据上 `input_energy` / `output_energy` /
  `snr` 三个分量同时饱和、彼此共线，而异常率与缺失率惩罚项恒为 0；
- **同时补充了一条对 D-最优不利的实测结果**：S3（同构激励）产品内基准上 `weighted` 参数误差 3.75%
  优于全量的 3.76% 与 D-最优的 4.80%，即在同构且干净的数据上完整加权分是四种策略中最好的一个。
  已写入 `EXP-2.1` §2 结论 3 与 README，并标注该幅度小于 10 种子波动（±0.51%）、强度仅到"不劣于"。

### Fixed (2026-08-08)

- 基准接口的条件数在设计矩阵奇异时为 `float("inf")`，而 Pydantic 会将非有限浮点数序列化为
  JSON `null`——最有力的证据（秩亏）反而在前端显示为空白。改为在 `1e12` 处封顶并单列
  `rank_deficient` 承载事实本身。

### Added (2026-08-08，敏感性扫描)

- `scripts/sweep_selection_sensitivity.py` 与实验报告 `EXP-3.0`：窗口长度 × 样本预算敏感性扫描，
  200 个测量点（5 窗长 × 4 预算 × 5 种子 × 2 场景），收敛 `EXP-1.1` §7 最后一条遗留威胁；
- `selection.take_top_k` 与 `budget_rows` 入口：`energy` / `weighted` 两条逐窗口基线改为与
  D-最优共用同一套预算消耗逻辑。窗长变化时按"窗口数"给预算是不可比的（长度 30 与 180 的窗口
  买到的样本量差 6 倍），按行数给才使"同等预算、不同方法"成为一句真话；
- `SelectionResult.budget_advisory` 与 `MIN_WINDOWS_FOR_COVERAGE`：预算过小时接口返回提示，
  前端优选页以警告条展示。刻意做成提示而非阻断——有时两个窗口就是这段记录的全部。

### Changed (2026-08-08，敏感性扫描)

- **`EXP-1.1` 的结论在 20 个工作点上得到验证，同时暴露了 D-最优自身的失效边界（本轮主要发现）**：
  S6 上 `ids` 参数误差最优 18/20、满秩 16/20，而 `energy` 满秩 1/20、`weighted` 2/20；
  但当预算只够装下约 2 个窗口时（预算/窗长 ≤ 2.3），`ids` 同样 5/5 次秩亏。
  分界干净地落在 2.3 与 3.5 之间，无交叉点。含义是预算不足而非准则失灵——
  信息准则不能凭空造出数据里没有的激励。该边界已写进产品提示；
- S3 上 `energy` 参数误差最优次数最多（10/20，`ids` 7/20、`weighted` 3/20），差距在种子波动内，
  照实记录。20 个工作点全部满秩，无策略崩溃。

### Added (2026-08-08，端到端测试)

- 前端 E2E 测试套件（Playwright + 预装 Chromium，9 项）：真实浏览器驱动真实后端，无任何 mock。
  一个只对着 mock 断言的 UI 测试只能证明 mock 正确，因此宁可慢——套件里跑的是真实 ARX 拟合与
  真实贪心优选。断言刻意不锁定具体指标值，只检查流水线产出结构合理且 UI 如实呈现，
  否则 E2E 会退化成基准测试的副本、并成为每次正常数值变动的绊线；
- `backend/scripts/serve_e2e.py`：用完即弃的 SQLite 实例跑同一套应用代码，使 E2E 不依赖 Docker。
  该脚本用 `metadata.create_all` 建表而非 Alembic，因此**不能**用 E2E 来声称迁移可用；
- `vite.config.ts` 增加 dev/preview 的 `/api/v1` 代理：此前 `npm run dev` 会对着 Vite 自己发请求、
  得到一片 404，每个开发者都要重新发现同一个修法。

### Fixed (2026-08-08，端到端测试发现)

- 仿真页只提供 S1–S5 单选项，**后端支持 S6 已久而前端从未暴露**——S6 正是整套差异化论证的支点。
  已补上单选项，副标题的"S1-S5"同步更正为"S1-S6"，并由 E2E 断言六个场景全部可见，防止再次漂移。

### Added (2026-08-08，长任务后台化)

- `app/services/job_queue.py` 与 `app/worker.py`：闭环寻优可交由 RQ Worker 执行，
  HTTP 请求不再为一次 120 trial 的寻优挂住数分钟。API 与 Worker 走**同一个**
  `execute_study` 内核——一个算得和 API 不一样的 Worker 比没有 Worker 更糟；
- 研究行在任何耗时工作开始**之前**就以 `queued` 写入，`/status` 立即可查。
  否则客户端拿到的 study_id 在整个有用窗口内都返回 404；
- 队列不可用时自动回退为同步执行，并在返回消息中说明走的是哪条路径。
  与大模型同一套原则：队列是优化项而非依赖项，赛场可能没有 Redis。
  唯一不允许发生的是"报告成功但工作被悄悄丢弃"；
- `INDUSOPT_BACKGROUND_OPTIMIZATION` 开关，默认**关闭**：单机离线部署没有 Worker 进程，
  一个被排队却永远无人执行的任务比一个阻塞的请求更糟；
- `tests/test_worker_queue.py`：真实 Redis + 真实 `rq worker` 子进程的往返验证。
  无 Redis 时跳过——跳过是诚实的行为，但跳过也不构成验证，因此交接报告如实记录它实际跑过的环境。

### Fixed (2026-08-08，长任务后台化)

- **`docker-compose.yml` 的 worker 监听默认队列，而任务入的是 `indusopt` 队列**——
  该 Worker 永远不会取到任何任务，寻优会无声地堆积。已改为 `rq worker indusopt`；
- 研究执行中途崩溃会把行永久卡在 `running`，轮询的客户端无法区分"还在跑"与"一小时前就死了"。
  现在失败会落 `failed` 并记录错误码；
- `_persist_study` 由插入改为按 study_id 更新，并先清掉旧 trial：Worker 崩溃后 RQ 重试
  不会为同一次请求留下两条研究记录；
- 最终统计中保留 `target_trials`：请求 50 个 trial 实际完成 12 个，与请求 12 个完成 12 个，
  是两件不同的事，只看最终统计分不出来。

### Verification

- pytest `6 passed`、Ruff、Mypy、OpenAPI JSON 校验通过；
- Docker Compose 镜像构建、依赖健康检查和 Alembic 迁移通过。
- 阶段 2 pytest `17 passed`，涵盖 S1–S5、随机种子重现、无噪声参数恢复、时间顺序与真实 API 闭环。
- 阶段 3 pytest `23 passed`，新增 CSV 异常、GBK/分号识别、去重、真实 Profile、列映射、版本与删除路由测试；PostgreSQL Docker 迁移和 multipart 上传闭环通过。
- 创新原型 pytest `27 passed`（`tests/test_identifiability.py`），Ruff 与 Mypy 通过；消融实验覆盖 10 组随机种子 × 2 场景 × 3 策略。
- 阶段 4–11：后端 pytest `233 passed`（含 2 项端到端用例验收、21 项大模型集成测试、10 项
  加权分对照基线测试、7 项行预算/预算提示测试，以及 2 项**真实 Redis + 真实 RQ Worker**
  往返验证），Ruff 与 Mypy 全部通过（69 个源文件）；
  前端 Vite 构建通过、`vue-tsc --noEmit` 退出码 0、Vitest `3 passed`、
  Playwright E2E `9 passed`（真实浏览器 + 真实后端，冷启动约 15 秒）；
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
