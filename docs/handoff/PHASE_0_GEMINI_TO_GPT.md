# 阶段 0：Gemini → GPT 反向交接与接口契约需求文档

**项目**：IndusOpt 工模智优  
**交接版本**：`HANDOFF-GEMINI-0.1`  
**交接状态**：Gemini 阶段 0 前端产品与可视化设计已全量冻结，准备进入阶段 1 (工程骨架与 OpenAPI 接口契约)。  

---

## 1. 本次 Gemini (前端) 已完成交付物

Gemini 已按照 `PHASE_0_GPT_TO_GEMINI.md` 的指引，完成了全套前端产品设计与交付文件：

1. `docs/frontend/user-roles.md`（用户角色与场景分析，明确建模工程师、评审员与管理员）
2. `docs/frontend/information-architecture.md`（站点导航与 8 大模块信息架构树）
3. `docs/frontend/user-flows.md`（手动精细流、仿真 Benchmark 流、Agent 智能闭环流与异常回滚流）
4. `docs/frontend/low-fidelity-wireframes.md`（6 大核心页面的 ASCII 低保真交互草图）
5. `docs/frontend/design-guidelines.md`（工业级视觉 Token、设计规范、ECharts 规范与微交互）
6. `docs/frontend/page-state-matrix.md`（12 种异步长任务状态矩阵与状态机）
7. `docs/frontend/chart-plan.md`（13 种核心算法图表规范与数据格式契约）
8. `docs/handoff/PHASE_0_GEMINI_TO_GPT.md`（本反向交接文件）

---

## 2. Gemini 给 GPT 的前端依赖与阶段 1 API 需求清单

在阶段 1 (工程骨架与 OpenAPI 契约) 中，请 GPT 在生成 `openapi.json` 时，重点满足并覆盖以下资源路径与响应格式：

### 2.1 系统与仿真数据类 (System & Simulation)
* `GET /api/v1/health/ready`：后端服务与数据库连通性。
* `POST /api/v1/simulation/generate`：生成 S1-S5 仿真数据集。
  * **前端需 GPT 返回**：生成的数据集 ID、真值方程参数 $a_i, b_j$、真值滞后 $d_{true}$、真实动态区间列表、随机种子 `seed`。

### 2.2 数据集管理与质量诊断类 (Dataset & Profile)
* `POST /api/v1/datasets/upload`：CSV 文件上传（支持进度与分块）。
* `GET /api/v1/datasets`：数据集列表。
* `GET /api/v1/datasets/{id}`：数据集详情与字段类型。
* `GET /api/v1/datasets/{id}/profile`：数据质量诊断结果（缺失率、采样间隔直方图、常量列、异常点计数）。
* `GET /api/v1/datasets/{id}/versions`：获取数据版本 DAG 节点与边。

### 2.3 算法与预处理类 (Algorithms & Preprocessing)
* `POST /api/v1/preprocessing/clean`：时间规整、插值与异常清洗 (IQR/Hampel)。
  * **前端需 GPT 返回**：清洗前/后时序对比数组、被替换的异常点索引数组 `replaced_indices`、新派生版本 ID。
* `POST /api/v1/preprocessing/segment`：高信噪比/高动态区间优选。
  * **前端需 GPT 返回**：识别出的区间列表 `[start_idx, end_idx, snr_db, dynamic_score, recommendation]`。
* `POST /api/v1/preprocessing/delay`：多变量 Lag-Correlation 时滞计算。
  * **前端需 GPT 返回**：滞后步数数组 `delays`、各变量相关系数曲线 `correlations`、推荐的最佳 Peak 滞后。
* `POST /api/v1/preprocessing/collinearity`：Pearson 矩阵与 VIF 诊断。
  * **前端需 GPT 返回**：相关系数 2D 矩阵 `matrix`、各变量 `vif_scores`、变量剔除/合并智能建议。

### 2.4 系统辨识与闭环寻优类 (Identification & Optimization)
* `POST /api/v1/modeling/arx/fit`：根据给定版本与结构 (na, nb, delay) 运行 ARX 辨识。
  * **前端需 GPT 返回**：估计参数、Train/Val/Test 划分下的 $R^2$ 与 FIT 指标、实际 vs 预测对比数组 `y_true`, `y_pred`、残差及残差 ACF 数组。
* `POST /api/v1/optimization/optuna/start`：启动 Optuna 闭环自动寻优 Study。
* `GET /api/v1/optimization/optuna/{study_id}/status`：获取当前运行状态、已完成 Trial 列表、收敛曲线数组、参数重要性 `param_importances`。

### 2.5 Agent 协同类 (Copilot & Execution)
* `POST /api/v1/copilot/chat`：自然语言对话输入。
  * **前端需 GPT 返回**：解析出的结构化 Execution Plan（包含工具 Task 节点列表与依赖关系）。
* `POST /api/v1/copilot/confirm`：Human-in-the-Loop 人工确认反馈 (`approved=true/false`)。

---

## 3. Gemini 发现的潜在线索与建议 (Suggestions & Design Notes)

1. **统一错误响应结构**：
   请 GPT 在阶段 1 `openapi-plan.md` 中确保所有错误返回遵循统一 Schema，包含 `error.code`（如 `DATASET_NOT_FOUND`, `SINGULAR_MATRIX`）与 `error.details`，以便前端映射到【状态矩阵 ST-10 (执行失败)】并弹出对应修复建议。
2. **长任务取消机制 (Cancellation)**：
   Optuna 闭环寻优和超大 CSV 诊断可能耗时较长，请 GPT 确保后台 Task (Redis/Celery/BackgroundTasks) 暴露 `POST /api/v1/tasks/{task_id}/cancel` 接口，以便前端触发【状态矩阵 ST-11 (已手动取消)】。
3. **下采样与数据截断 (Downsampling Hint)**：
   当数据行数超过 10,000 行时，前端绘制 ECharts 会使用下采样。后端如果能在 Profile 接口中返回 `recommended_downsample_factor`，将有助于前端保持最佳渲染性能。

---

## 4. 阶段 1 Gemini 入场前提

阶段 0 已完美闭环。当开发者与 GPT 协同完成阶段 1 后端骨架、PostgreSQL 迁移以及正式的 `backend/openapi.json` 导出后，Gemini 将正式开启 Vue 3 + TypeScript 业务前端的编码搭建！
