# 当前阶段状态

## 当前阶段

阶段 11：测试与竞赛交付（阶段 4–11 全部开发完成）

## 开始时间

2026-07-28（阶段 4–11 于 2026-08-07 完成）

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

### 阶段 4–11 全流程实现（2026-08-07）

- 阶段 4：`/preprocessing/clean` 接入真实清洗流水线，派生不可变版本并写入血缘 DAG；
- 阶段 5：质量门控 + D-最优子模优选（`gating.py` + `selection.py` + `segment_service.py`），门控先于信息准则执行；
- 阶段 6：预白化互相关时滞估计（`delay.py`）与共线性诊断（`collinearity.py`），均接入真实路由；
- 阶段 7：`modeling_service.fit_arx_core` 统一辨识内核，自由仿真 FIT 为主指标，先验约束为硬约束；
- 阶段 8：Optuna 分级闭环寻优 + 血缘缓存 + 策略记忆库热启动（`optimization_service.py`，新增 3 张表与 Alembic `0003`）；
- 阶段 9：Agent 四层编排与机器可检验合规证明（`algorithms/agent/`、`agent_service.py`）；
- 阶段 10：数值溯源绑定报告与优选数据集导出（`algorithms/report/`、`report_service.py`）；
- 阶段 11：产品内一键自评测基准（`benchmark_service.py`），新增 S6 异构激励场景；
- 大模型接入：`algorithms/agent/llm.py` OpenAI 兼容 Provider（DeepSeek / Ollama / vLLM / Xinference /
  自建 ChatGLM·LLaMA）与 `llm_planner.py`；大模型计划须通过与规则计划相同的合规校验，
  报告结论禁止书写数字、违规草稿自动重试并最终回退；未配置 Provider 时系统完整可用（离线默认）；
- 前端 13 个业务视图全部改为真实数据绑定，删除全部 mock 回退（清洗、优选、时滞、共线性、辨识、寻优、Agent、交付、基准）。

### 差异化创新增补（INNO-1.0，2026-08-07）

- 官方赛题手册 A14 与初赛评分标准复核，识别同质化风险并定义 7 个差异化创新点：`docs/innovation/differentiation-blueprint.md`；
- 算法口径增量规范 `ALG-0.2` 落盘：`docs/algorithms/algorithm-specification-v2.md`；
- **创新 1 原型完成**：`backend/algorithms/identifiability/` —— Fisher 信息矩阵、`log det` D-最优准则、持续激励阶次判据、矩阵行列式引理增量增益、lazy greedy（CELF）子模最大化窗口优选、energy 对照基线；
- **创新 2 原型完成**：自由仿真、稳态增益、`A(q)` 稳定性判别、残差白度；
- 消融实验执行器 `backend/scripts/benchmark_identifiability.py` 与 10 组种子实验报告 `docs/experiments/identifiability-ablation.md` / `.json`；
- 新增 S6 异构激励仿真场景定义（现有 S1–S5 均为同构激励，无法暴露按能量选段的失效模式）；
- 阶段计划已同步创新增补至阶段 2、5、7、8、9、10、11。

## 未完成

- 公开数据集上的外部验证——**本环境内无法完成**：出网策略仅放行 GitHub / PyPI / npm，KU Leuven DaISy、nonlinearbenchmark.org、data.4tu.nl 的连接均被网关 403 拒绝（`nonlinear_benchmarks` 可从 PyPI 装上，但运行时取数同样被拒）。有外网的机器上可直接补做；
- `EXP-1.1` §7 遗留实验已全部补测完成（完整加权分对照、窗口长度与预算敏感性扫描，见 `EXP-3.0`）；
- Docker Compose 启动验证（本开发环境无 Docker 守护进程，见"测试结果"说明）。

## 当前问题

- Docker 守护进程在当前开发沙箱中不可用，因此 `docker compose up` 未能实机验证。
  已验证的替代证据：Dockerfile 复制 `app/`、`algorithms/`、`alembic/` 全部运行期代码；
  `pyproject.toml` 已加入 `optuna>=4.0,<5.0`；Alembic 版本链为单一 head
  (`0003_optimization_and_memory`)，无分叉。首次实机部署时需执行一次
  `docker compose build && docker compose up` 复核。

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
- 长任务采用 Redis + RQ：闭环寻优可后台执行，队列不可用时回退为同步执行并如实说明（`INDUSOPT_BACKGROUND_OPTIMIZATION`，默认关闭）。

## 数据库版本

- Alembic Revision：`0003_optimization_and_memory`（单一 head，链路 0001 → 0002 → 0003）

## API 版本

- OpenAPI Version：`3.1.0`，文件：`backend/openapi.json`

## 测试结果

- pytest：`23 passed`（阶段 1 契约、S1–S5 仿真、无噪声 ARX 参数恢复、时间分区、API 真值闭环，以及 CSV 异常、GBK/分号、去重、Profile、配置、版本、删除）；
- Ruff：通过；
- Mypy：通过（34 source files，含质量诊断算法包）；
- OpenAPI JSON：通过 `json.tool` 校验；
- Docker Compose：阶段 3 镜像构建、本地产物卷挂载、PostgreSQL/Redis 就绪、Alembic `0002_datasets_and_profiles (head)` 通过；容器内真实 multipart CSV 上传 → Profile → 列配置闭环通过；
- 前端 Vitest 测试：`3 passed` (Pinia Store、ApiClient & ApiError)；
- 前端 Vite 构建通过，`vue-tsc --noEmit` 退出码 0；
- **长任务后台化：`tests/test_worker_queue.py` 2 项在真实 Redis 7.0.15 + 真实 `rq worker` 子进程上通过**——API 返回 202/queued 且 `/status` 立即可查，Worker 执行后 trial 与最优值如实落库；无 Redis 环境自动跳过；
- **前端 E2E（Playwright + Chromium）：`9 passed`**，冷启动全流程约 15 秒。真实浏览器驱动真实后端，无任何 mock：仿真六场景暴露、生成 → 门控 → D-最优优选、自评测基准四策略与秩状态、Agent 自然语言编排与合规证明、离线默认走确定性规则、404 与领域错误路径、13 个主视图无控制台异常；
- **阶段 4–11 全量后端测试：`233 passed`**（含清洗路由、门控与优选、时滞与共线性、辨识与先验、闭环寻优与策略记忆、Agent 与合规证明、报告溯源与导出、自评测基准、加权分对照基线）；
- **Ruff 与 Mypy：全部通过（69 个源文件）**；
- Docker Compose：**本环境无 Docker 守护进程，未实机验证**（见"当前问题"）；
- 文档完整性检查：通过；
- 创新原型测试：`tests/test_identifiability.py` `27 passed`（回归矩阵口径、无噪参数恢复、PE 阶次教科书标定、行列式引理与直接 `log det` 差一致性、lazy greedy 与朴素贪心逐窗口一致、信息增益单调不增、分区不越界、异构激励下优于 energy、自由仿真无噪精确复现、一步预测掩盖劣质模型、稳态增益解析值、不稳定多项式检出）；
- 创新原型 Ruff 与 Mypy：通过（`algorithms/identifiability`、`scripts/benchmark_identifiability.py`、`tests/test_identifiability.py`）；
- 消融实验：10 组随机种子 × 2 场景（S3/S6）× **4 策略**（full / energy / weighted / ids），结果见 `docs/experiments/identifiability-ablation.json`；
- `weighted` 为 `ALG-0.1` §6.2 完整加权质量分的原样实现，补测结论**推翻了 `EXP-1.0` 的预判**：它并不优于纯能量法，两者在 S6 上失效方式完全相同（见 `EXP-1.1` §3 结论 2b）；
- 同时补入一条对主口径不利的实测：S3 同构激励下 `weighted` 参数误差 3.75% 优于 D-最优的 4.80%（`EXP-2.1` §2 结论 3），已写入 README 首页结论表。
- 敏感性扫描 `EXP-3.0`：200 个工作点（5 窗长 × 4 预算 × 5 种子 × 2 场景）验证结论适用范围，并发现 **D-最优自身的失效边界**——预算/窗长 ≤ 2.3 时它同样秩亏；该边界已作为 `budget_advisory` 提示写入接口与前端。

## 验收结论

- [x] 通过：阶段 4–11 全部开发完成。CSV 上传 → 清洗规整 → 动态区间检测 → 质量约束 D-最优优选 →
  时滞估计补偿 → 共线性降维 → ARX 辨识 → 一步/自由仿真双评价 → 闭环寻优 → 策略记忆热启动 →
  Agent 自然语言编排（大模型驱动，离线可回退）→ 自动化基准 → 溯源图文报告 → 优选数据集导出，
  全链路已在 233 个自动化测试下贯通。
- [ ] 不通过

## 下一阶段进入条件

- 竞赛交付物：**项目概要、详细方案、产品使用手册、答辩 PPT、分工与过程文档均已完成**（`docs/competition/`、`docs/manual/`）。PPT 未做渲染后视觉复核（本环境 LibreOffice 不可用），请在 PowerPoint 中过一遍；演示视频与交互录屏需在有图形界面的机器上录制；分工表涉及成员身份，须团队人工填写；
- 知识产权：**软著登记材料与专利技术交底书已完成**（`docs/ip/`），登记申请表中涉及权利主体、日期承诺的字段已标 `【待填】`，须由团队人工确认；
- 首次实机部署时补做一次 `docker compose build && docker compose up` 验证；
- 建议补充公开数据集外部验证。
