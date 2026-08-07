# 阶段 1：交给 GPT 的完整执行与开发指令 (GPT Execution Instructions for Phase 1)

> **使用方法**：将本文档的全部内容直接复制并发送给 **GPT**，指示其开始执行 IndusOpt 项目的**阶段 1（工程骨架与接口契约）**后端开发。

---

```text
你现在担任 IndusOpt (工模智优) 项目的后端、算法与架构专家角色 (GPT)。

项目阶段：阶段 1 (工程骨架与接口契约)
当前状态：阶段 0 (需求冻结与 Gemini 前端设计) 已 100% 验收完成。
Gemini 已完成全部前端设计文档落盘：
- docs/frontend/user-roles.md
- docs/frontend/information-architecture.md
- docs/frontend/user-flows.md
- docs/frontend/low-fidelity-wireframes.md
- docs/frontend/design-guidelines.md
- docs/frontend/page-state-matrix.md
- docs/frontend/chart-plan.md
- docs/handoff/PHASE_0_GEMINI_TO_GPT.md

================================================================================
【GPT 阶段 1 核心任务边界与目标】
================================================================================

在阶段 1 中，你需要完成后端工程骨架的建立，并冻结与前端 Gemini 交互的 OpenAPI 规范：

1. 搭建完整的后端项目结构：
   - 语言与环境：Python 3.11 或 3.12
   - Web 框架：FastAPI
   - 数据校验：Pydantic v2
   - ORM 与数据库：SQLAlchemy 2.0 (Async) + Alembic + PostgreSQL
   - 任务队列/异步：Redis + RQ 或 FastAPI BackgroundTasks (候选)
   - 代码规范与测试：Ruff + Mypy + pytest
   - 部署：Docker Compose (含有 FastAPI backend + PostgreSQL + Redis)

2. 实现基础与核心框架中间件：
   - 结构化 JSON 日志 (含 request_id 追踪)
   - 全局 CORS 跨域配置 (支持前端 Vite 开发端口 5173/3000)
   - 统一 API 响应包装器 (Success Envelope)
   - 全局异常拦截与统一 Error 结构
   - 健康检查与系统信息接口

3. 规范 API 响应与错误契约：

标准成功响应 (HTTP 200)：
{
  "success": true,
  "data": { ... },
  "error": null,
  "request_id": "req-uuid-v4"
}

标准错误响应 (HTTP 4xx/5xx)：
{
  "success": false,
  "data": null,
  "error": {
    "code": "DATASET_NOT_FOUND",
    "message": "数据集不存在",
    "details": { "dataset_id": "ds_123" }
  },
  "request_id": "req-uuid-v4"
}

4. 导出完整 OpenAPI 规范文件：
   - 导出一份完整的 OpenAPI 3.0/3.1 Schema 到文件：`backend/openapi.json`
   - 编写 API 规范文档：`docs/api/api-conventions.md`
   - 编写错误码字典：`docs/api/error-codes.md`

================================================================================
【阶段 1 必须规划并出现在 openapi.json 中的 Endpoint Schema】
================================================================================

请在 FastAPI 中定义路由和 Pydantic Schema（阶段 1 可先返回 Mock 结构或骨架 Response，但字段名必须精确冻结）：

1. 系统与健康检查类：
   - GET /api/v1/health/live
   - GET /api/v1/health/ready
   - GET /api/v1/system/info

2. 仿真数据生成类 (Simulation)：
   - POST /api/v1/simulation/generate (场景 S1-S5 参数与真值文件 Schema)

3. 数据集与诊断类 (Datasets & Profile)：
   - POST /api/v1/datasets/upload
   - GET  /api/v1/datasets
   - GET  /api/v1/datasets/{id}
   - DELETE /api/v1/datasets/{id}
   - GET  /api/v1/datasets/{id}/profile (缺失率、采样间隔直方图、异常点)
   - GET  /api/v1/datasets/{id}/versions (数据版本 DAG)

4. 预处理与数据优选类 (Preprocessing & Selection)：
   - POST /api/v1/preprocessing/clean (规整、插值、Hampel)
   - POST /api/v1/preprocessing/segment (动态响应区间识别与 SNR 评分)
   - POST /api/v1/preprocessing/delay (多变量 Lag-Correlation 计算)
   - POST /api/v1/preprocessing/collinearity (Pearson 矩阵与 VIF 诊断)

5. 系统辨识与闭环寻优类 (Identification & Optimization)：
   - POST /api/v1/modeling/arx/fit (ARX 辨识, 实际 vs 预测对比数组, FIT/R² 指标)
   - POST /api/v1/optimization/optuna/start (启动 Optuna 闭环寻优)
   - GET  /api/v1/optimization/optuna/{study_id}/status (Trial 进度、收敛曲线、参数重要性)
   - POST /api/v1/tasks/{task_id}/cancel (取消长任务)

6. Agent Copilot 协同类：
   - POST /api/v1/copilot/chat (接收 Prompt，返回结构化 Execution Plan DAG)
   - POST /api/v1/copilot/confirm (Human-in-the-Loop 人工确认)

================================================================================
【协作约束与规范】
================================================================================

1. GPT 不修改 `frontend/` 目录下的任何文件。
2. 所有 Backend 代码放在 `backend/` 目录下。
3. 保证目录结构清晰：
   indusopt/
   ├── backend/
   │   ├── app/
   │   │   ├── api/          # FastAPI 路由
   │   │   ├── core/         # 配置、日志、中间件
   │   │   ├── models/       # DB Models
   │   │   ├── schemas/      # Pydantic Schemas
   │   │   ├── services/     # 业务逻辑服务
   │   │   └── main.py       # FastAPI 启动入口
   │   ├── tests/            # pytest 单元测试
   │   ├── pyproject.toml
   │   ├── Dockerfile
   │   └── openapi.json      # 导出的接口规范
   ├── docker-compose.yml
4. 完成编码后，确保可以通过以下命令运行并通过测试：
   - cd backend && pytest
   - docker compose up --build

请现在开始编写后端骨架代码，导出 backend/openapi.json，并更新 PHASE_STATUS.md 进入阶段 1！
```
