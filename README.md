# IndusOpt 工模智优 — 基于 Agent 的流程工业建模数据智能优选与闭环寻优系统

版本：`v1.0.0-full-pipeline`
赛题：2026「数字马力杯」第十三届浙江省大学生服务外包创新应用大赛 **A14**（和利时）

面向流程工业建模工程师的本地化 Web 系统：通过自然语言驱动受约束的算法工作流，
对多变量时序数据完成规整、清洗、**质量约束 D-最优数据优选**、时滞补偿、共线性处理、
ARX 辨识与闭环寻优，交付可复现的数据版本、模型、指标与**全数值可溯源**的报告。

## 交付状态

阶段 0–11 全部开发完成。完整闭环已在 233 个后端自动化测试下贯通（其中 2 项为端到端用例验收）：

```text
工业 CSV 上传
→ 数据规整与清洗           /preprocessing/clean
→ 动态区间检测 + 质量门控   /preprocessing/segment
→ 质量约束 D-最优数据优选   （同一接口，门控先于信息准则）
→ 时滞估计与补偿           /preprocessing/delay
→ 共线性检测与降维         /preprocessing/collinearity
→ 系统辨识 (ARX)           /modeling/arx/fit
→ 模型评价（一步 + 自由仿真）（同一接口，自由仿真为主指标）
→ 闭环寻优预处理参数        /optimization/optuna/start
→ 历史策略记忆与热启动      （同一接口，跨数据集复用）
→ Agent 自然语言编排        /copilot/chat（大模型编排，回退至确定性规则）
→ 自动化基准               /benchmark/run
→ 真实数据血缘的图文报告    /reports/generate
→ 优选数据集导出           /delivery/export
```

一句自然语言即可驱动全流程，例如：

> 提取 1 号塔高信噪比的动态数据，处理共线性后，通过闭环寻优找出最佳模型数据

Agent 解析意图 → 生成白名单计划 → 静态合规校验并出具签名证明 → 调度真实算法 → 汇报结论。

### 大模型接入

赛题要求接入开源大模型。系统支持任何 **OpenAI 兼容**的 chat/completions 端点，
覆盖 DeepSeek、Ollama、vLLM、Xinference 以及自建 ChatGLM / LLaMA：

```bash
export INDUSOPT_LLM_PROVIDER=ollama
export INDUSOPT_LLM_BASE_URL=http://localhost:11434/v1
export INDUSOPT_LLM_MODEL=qwen2.5:7b
# DeepSeek 云端则另加 INDUSOPT_LLM_API_KEY
```

**未配置时系统仍然完整可用**，这是刻意的：赛场可能没有网络，本地离线部署是硬性要求。
大模型负责*提议*，不负责*授权*——

- 大模型生成的计划要通过与规则计划**完全相同**的白名单、DAG 与合规静态校验；校验不过即回退并说明原因；
- 大模型撰写报告结论时**一个数字都不许写**，只能输出占位符；写了数字的草稿会被拒绝并要求重写，
  连续 3 次不合规则回退到模板化结论。

因此模型不可用、输出畸形、甚至刻意越权，最坏结果都只是"回退 + 说明"，而不是错误的产物。

**尚未完成**：公开数据集外部验证、Docker Compose 实机启动验证
（本开发环境无 Docker 守护进程，详见 `PHASE_STATUS.md`）。

### 长任务后台化

一次 120 trial 的闭环寻优是分钟级的，挂住 HTTP 连接迟早会被前置代理掐断。因此寻优可交给
RQ Worker：

```bash
export INDUSOPT_BACKGROUND_OPTIMIZATION=true
PYTHONPATH=. rq worker indusopt --url redis://localhost:6379/0
```

接口立即返回 `202 queued` 与 study_id，`/optimization/optuna/{id}/status` 从提交那一刻起就可轮询。
**默认关闭**：单机离线部署没有 Worker 进程，一个被排队却永远无人执行的任务比一个阻塞的请求更糟。
Redis 或 Worker 不可用时自动回退为同步执行，并在返回消息里说明走的是哪条路径——
队列是优化项而非依赖项，唯一不允许发生的是"报告成功但工作被悄悄丢弃"。

## 差异化创新

赛题任务清单本身即实现说明书，按字面实现会与其他队伍高度同质化。差异化设计见：

- [`docs/innovation/differentiation-blueprint.md`](docs/innovation/differentiation-blueprint.md)：7 个创新点、评分标准映射、排期增量与降级顺序；
- [`docs/algorithms/algorithm-specification-v2.md`](docs/algorithms/algorithm-specification-v2.md)：相对 `ALG-0.1` 的算法口径增量；
- [`docs/experiments/identifiability-ablation.md`](docs/experiments/identifiability-ablation.md)：10 组种子的离线消融实验证据；
- [`docs/experiments/self-benchmark.md`](docs/experiments/self-benchmark.md)：产品内一键自评测基准的实测结果；
- [`docs/experiments/sensitivity-sweep.md`](docs/experiments/sensitivity-sweep.md)：窗口长度 × 样本预算 200 个工作点的敏感性扫描，含 D-最优自身的失效边界。

核心结论（全部为实测，含不利结果）：

| 结论 | 数据来源 |
|---|---|
| D-最优优选用 **14.3% 的数据**达到全量数据的辨识精度（参数误差 4.54% vs 4.61%，自由仿真 FIT 89.04 vs 89.05），且条件数更优 | `EXP-2.1` S6 |
| 同等预算下能量启发式在异构激励下**失效**：参数误差 15.22%，自由仿真 FIT 掉 13.45 个点，设计矩阵秩亏 | `EXP-2.1` S6 |
| **完整加权质量分同样失效**（15.06%、同样秩亏），且它拿到的样本更多——说明问题不在分量选得好不好，而在逐窗口独立打分无法表达信息冗余 | `EXP-2.1` S6 |
| **一步预测 FIT 区分度仅为自由仿真 FIT 的 1/28.5**，不适合作为闭环目标函数 | `EXP-2.1` S6 |
| 闭环分级搜索使昂贵环节摊薄 **24 倍**，最优自由仿真 FIT 由 95.12 提升至 97.86 | 阶段 8 实测 |
| 预白化互相关在 6 个通道中 **4 胜 1 负 1 平**——占优但非全胜 | `EXP-2.1` |
| 同构激励（S3）下 D-最优**排在末位**（4.80%，落后加权分的 3.75%、全量的 3.76%、能量法的 4.12%）——价值在于"永不崩溃"而非"永远最优" | `EXP-2.1` S3 |
| 原先"完整加权分应优于纯能量法"的预判**被实测证伪**（14.81% vs 14.82%，无差异）；报告按实测改写而非按预期保留 | `EXP-1.1` |
| 结论不是单点巧合：**200 个工作点**（5 窗长 × 4 预算 × 5 种子 × 2 场景）上 D-最优在 S6 参数误差最优 **18/20**、满秩 **16/20**，而两种打分法满秩仅 1/20 与 2/20 | `EXP-3.0` |
| **D-最优自身也有失效边界**：预算只够装下约 2 个窗口时（预算/窗长 ≤ 2.3）它同样秩亏。产品已就此给出提示而非默默出模型 | `EXP-3.0` |
| 内容寻址血缘缓存在扁平采样下命中率仅 **1.7%**，真正的节省来自分级搜索 | 阶段 8 实测 |

复现（产品内点击「一键自评测基准」，或命令行）：

```bash
cd backend
python -m pytest -q                                   # 233 passed
python scripts/benchmark_identifiability.py --repeats 10
python scripts/sweep_selection_sensitivity.py --repeats 5
curl -X POST http://localhost:18000/api/v1/benchmark/run \
  -H 'Content-Type: application/json' \
  -d '{"scenarios":["S3","S6"],"n_samples":4000}'
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
    ├── experiments
    │   ├── identifiability-ablation.md   # EXP-1.1 10 组种子离线消融
    │   ├── self-benchmark.md             # EXP-2.1 产品内自评测基准
    │   └── sensitivity-sweep.md          # EXP-3.0 200 工作点敏感性扫描
    ├── innovation
    │   └── differentiation-blueprint.md
    ├── ip
    │   ├── software-copyright/           # 软著登记材料
    │   └── patent/技术交底书.md           # 专利技术交底（未做检索）
    ├── manual
    │   └── 用户手册.md                    # 产品使用手册
    ├── requirements
    │   ├── official-requirements.md
    │   ├── scope-freeze.md
    │   └── use-cases.md
    └── testing
        └── evaluation-protocol.md
```

## 使用方式

### 本地开发

```bash
# 后端
cd backend
pip install -e ".[dev]"
PYTHONPATH=. uvicorn app.main:app --reload --port 18000

# 前端
cd frontend
npm ci && npm run dev
```

### Docker Compose（离线本地部署）

```bash
docker compose build
docker compose up
# 后端 http://localhost:18000/docs
```

> 本仓库当前开发环境无 Docker 守护进程，Compose 未实机验证。已核对：Dockerfile 复制
> `app/`、`algorithms/`、`alembic/` 全部运行期代码；`pyproject.toml` 含 `optuna`；
> Alembic 为单一 head `0003_optimization_and_memory`。首次部署请复核一次。

### 质量门禁

```bash
cd backend && python -m pytest -q && python -m ruff check app algorithms tests scripts && python -m mypy app algorithms
cd frontend && npx vue-tsc --noEmit && npm run build && npm test
cd frontend && npm run test:e2e     # 真实浏览器 + 真实后端的端到端闭环
```

E2E 不需要 Docker：`playwright.config.ts` 会自行拉起一个用完即弃的 SQLite 实例
（`backend/scripts/serve_e2e.py`）与前端 preview 服务，跑的是同一套应用代码与同一批算法。
PostgreSQL + Alembic 仍是唯一受支持的部署路径——E2E 跳过迁移，因此**不能**用它来证明迁移可用。

## 文档索引

| 文档 | 内容 |
|---|---|
| [产品使用手册](docs/manual/用户手册.md) | 安装、五分钟上手、逐页操作说明、如何读懂系统的判断、已知限制 |
| [差异化创新蓝图](docs/innovation/differentiation-blueprint.md) | 7 个创新点与评分标准映射 |
| [算法口径规范 ALG-0.2](docs/algorithms/algorithm-specification-v2.md) | 相对 `ALG-0.1` 的算法增量 |
| [EXP-1.1 / EXP-2.1 / EXP-3.0](docs/experiments/) | 全部实验证据与原始数据，含不利结果 |
| [知识产权材料](docs/ip/README.md) | 软著登记材料与专利技术交底书 |

算法实现与基线结果见 [`docs/algorithms/phase-2-simulation-arx-baseline.md`](docs/algorithms/phase-2-simulation-arx-baseline.md)
与 [`docs/algorithms/algorithm-specification-v2.md`](docs/algorithms/algorithm-specification-v2.md)；
后端细节见 [`backend/README.md`](backend/README.md)。
