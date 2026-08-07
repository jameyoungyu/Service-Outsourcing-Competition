# IndusOpt 系统架构

版本：`ARCH-0.1`

## 1. 架构目标

- 将 LLM 的职责限制在意图理解、计划编排和解释，不参与数值真值生成；
- 将工业算法封装为可测试、可复用、参数化的确定性工具；
- 对长任务提供排队、取消、重试和状态恢复；
- 对数据、模型、Trial、报告提供完整血缘；
- 在普通电脑上通过 Docker Compose 本地运行；
- 保证前端只能使用真实 API 和真实任务状态。

## 2. 逻辑架构

```text
┌────────────────────────────────────────────────────────────┐
│ Vue 3 Web                                                   │
│ 数据集 / 算法页面 / Agent 工作台 / 运行记录 / 报告中心    │
└─────────────────────────┬──────────────────────────────────┘
                          │ HTTPS/JSON + SSE/Polling
┌─────────────────────────▼──────────────────────────────────┐
│ FastAPI API                                                │
│ 请求校验 / request_id / 统一错误 / 鉴权预留 / OpenAPI     │
├────────────────────────────────────────────────────────────┤
│ Application Services                                      │
│ Dataset / Pipeline / Model / Optimization / Agent / Report│
├────────────────────────────────────────────────────────────┤
│ Domain & Tool Registry                                     │
│ Pydantic schemas / 状态机 / 权限规则 / 白名单算法工具      │
└──────────────┬───────────────────┬─────────────────────────┘
               │                   │
       ┌───────▼────────┐  ┌──────▼─────────────────────┐
       │ PostgreSQL      │  │ Redis + RQ Workers          │
       │ 元数据/版本/任务│  │ 长任务、取消检查点、重试    │
       │ Optuna Storage  │  │ 算法流水线与报告生成        │
       └───────┬────────┘  └──────┬─────────────────────┘
               │                   │
       ┌───────▼───────────────────▼─────────────────────┐
       │ Algorithms & Simulation                         │
       │ cleaning / segmentation / delay / collinearity │
       │ identification / evaluation / optimization     │
       └───────────────────┬────────────────────────────┘
                           │
       ┌───────────────────▼────────────────────────────┐
       │ Local Artifact Storage                         │
       │ 原始 CSV / 版本数据 / 模型 / 图表 / 报告       │
       └────────────────────────────────────────────────┘

External: DeepSeek/Qwen Provider，仅供 Planner 与报告解释。
```

## 3. 物理部署

Docker Compose 第一版包含：

- `frontend`：Nginx + Vue 静态资源；
- `backend`：FastAPI；
- `worker`：RQ Worker，与 backend 使用同一代码镜像；
- `postgres`：业务数据与 Optuna RDB Storage；
- `redis`：任务队列与短期状态；
- 本地挂载卷：`data/uploads`、`data/results`、PostgreSQL 数据目录。

不引入 Kubernetes、MinIO、消息流平台或 GPU 服务。

## 4. 后端分层

### 4.1 API 层

职责：HTTP、请求响应模型、状态码、分页、request_id、上传流控制。  
禁止：直接写算法逻辑、直接拼 SQL、直接操作文件系统路径。

### 4.2 Application Service 层

职责：用例编排、事务边界、权限检查、任务创建、状态机推进、产物登记。  
示例：`DatasetService`、`PipelineService`、`OptimizationService`、`AgentService`。

### 4.3 Domain 层

职责：领域状态、数据版本规则、模型发布规则、工具白名单、人工确认策略。  
核心状态机：数据集、处理运行、模型运行、优化任务、Agent 运行、报告任务。

### 4.4 Repository 层

职责：SQLAlchemy 数据访问和事务一致性。  
禁止：返回未受控 ORM 对象到 API 层；禁止算法代码直接访问数据库。

### 4.5 Algorithm 层

职责：纯函数或小型对象形式的数值计算。  
约束：输入输出显式、无隐藏全局状态、随机种子可控、无数据库依赖、可单元测试。

### 4.6 Worker 层

职责：从队列取任务、加载稳定输入版本、运行工具、写中间状态、检查取消标志、登记产物。  
约束：任务幂等；重复执行不得覆盖原产物。

### 4.7 LLM Provider 层

职责：统一 DeepSeek/Qwen 调用、超时、重试、结构化输出、脱敏和审计。  
降级：LLM 不可用时用户仍可通过表单手工运行核心算法。

## 5. 关键数据实体规划

阶段 1 后逐步实现，阶段 0 先冻结语义：

| 实体 | 作用 |
|---|---|
| `datasets` | 数据集逻辑身份、名称、来源、状态 |
| `dataset_files` | 原始上传文件、SHA-256、大小、编码 |
| `dataset_columns` | 字段角色、类型、单位、时间格式 |
| `dataset_versions` | 不可变数据版本、父版本、校验和、路径 |
| `processing_runs` | 算法运行、参数、状态、耗时、错误 |
| `version_lineage` | 父子版本和步骤关系 |
| `dataset_profiles` | 质量诊断结果 |
| `segment_sets` | 动态区间集合和评分 |
| `delay_analyses` | 候选与最终时滞 |
| `collinearity_analyses` | 相关性、VIF、建议 |
| `variable_sets` | 确认后的输入变量集合 |
| `models` / `model_runs` | ARX 配置、参数和版本 |
| `model_metrics` | 按 train/validation/test 分区保存指标 |
| `optimization_studies` | 搜索空间、目标、状态、最佳 Trial |
| `optimization_trials` | 每个 Trial 的参数、产物、指标、失败原因 |
| `agent_runs` / `agent_steps` | 指令、计划、工具调用和审计 |
| `reports` / `artifacts` | 报告、图表、导出文件 |
| `operation_logs` | 用户操作与系统审计 |

## 6. 一致性边界

- 数据库记录和文件产物采用“两阶段登记”：先写临时文件，校验成功后原子改名并提交数据库。
- 算法任务成功前，不把输出版本标记为可用。
- Trial 失败必须保留参数和错误，但不得更新 Study 最佳值。
- 模型发布与测试集评估是独立步骤，避免未冻结模型提前读取测试集。
- 报告只读取已完成、可用、校验和匹配的产物。

## 7. 安全边界

- 文件名不直接作为服务器路径；使用 UUID 存储名。
- CSV 按流式上传并限制大小；拒绝路径穿越和压缩炸弹。
- LLM API Key 仅来自环境变量，不入库、不入日志。
- 日志不记录完整工业数据行；只记录摘要、列名和对象 ID。
- Agent 不具备任意代码执行器、数据库连接或文件系统浏览工具。
- 导出前检查数据集敏感标记并要求确认。

## 8. 可观测性

每个 HTTP 请求和后台任务都具有 `request_id`/`run_id`。结构化日志至少包含：

```text
timestamp, level, service, request_id, run_id, dataset_id,
algorithm, duration_ms, status, error_code, code_version
```

禁止在日志中记录 LLM API Key、原始完整 CSV、用户上传内容全文或数据库密码。

## 9. 架构决策理由

- **ARX + 可验证仿真**：便于形成真值闭环和可信实验。
- **PostgreSQL + 本地文件**：兼顾关系审计和大文件成本。
- **Redis + RQ**：比在 FastAPI 进程内执行长任务更可恢复，复杂度低于大型工作流平台。
- **Provider 抽象**：避免绑定单一大模型厂商。
- **工具注册表**：让 Agent 只能调用经过测试的算法。
