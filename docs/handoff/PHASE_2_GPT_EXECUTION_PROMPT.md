# 阶段 2：交给 GPT 的完整执行与开发指令 (GPT Execution Prompt for Phase 2)

> **使用方法**：将本文档的全部内容直接复制并发送给 **GPT**，指示其开始执行 IndusOpt 项目的**阶段 2（仿真数据生成与 ARX 基线）**后端算法开发。

---

```text
你现在担任 IndusOpt (工模智优) 项目的后端、算法与架构专家角色 (GPT)。

项目阶段：阶段 2 (仿真数据生成与 ARX 基线)
当前状态：阶段 1 (工程骨架、OpenAPI Schema 冻结、FastAPI/PostgreSQL/Redis 搭建及 Gemini 前端全量构建) 已 100% 验收通过！

Gemini 已完成前端全部 13 个 View 和 API 客户端的对接（已通过 Vitest 与 Vite Production 构建验证）。
相关交接文档：
- docs/handoff/PHASE_1_GEMINI_TO_GPT.md

================================================================================
【GPT 阶段 2 核心任务与算法边界】
================================================================================

在阶段 2 中，你需要将阶段 1 的 schema-valid contract stubs 替换为**真实的 Python 工业仿真与 ARX 辨识算法实现**：

1. 实现真实仿真数据集生成引擎 (`backend/app/services/simulation_service.py` 或 `backend/algorithms/simulation/`)：
   支持生成 5 种预设场景，保存生成的 CSV 文件到 `data/simulation/` 并生成配套真值 JSON：

   - 场景 S1 (基础单输入): 单输入单输出 MISO_ARX，低噪声 (σ=0.01)，已知真值 na=2, nb=2, delay=3。用于验证基础辨识正确性。
   - 场景 S2 (多输入不同滞后): 2~4 个输入变量，不同输入具有不同真实时滞 (如 d_u1=3, d_u2=8)。
   - 场景 S3 (长稳态短动态): 大量稳态区间 (80% 样本)，少量阶跃/斜坡/脉冲响应 (20% 样本)。
   - 场景 S4 (污染数据): 注入缺失值、尖峰异常、冻结值段、漂移与强噪声 (σ=0.2)。
   - 场景 S5 (高共线性): 构造高度相关的输入变量 (如 u2 = 0.95 * u1 + noise)，用于后续变量筛选。

   每个生成的仿真数据集包含一个结构化真值文件 `data/simulation/{dataset_id}_ground_truth.json`：
   {
     "system_type": "MISO_ARX",
     "true_na": 2,
     "true_nb": [2, 2],
     "true_delays": [3, 8],
     "true_parameters": { "a1": -1.4, "a2": 0.48, "b1_0": 0.3, "b2_0": 0.15 },
     "dynamic_segments": [{ "start_idx": 200, "end_idx": 500, "snr_db": 18.5 }],
     "noise_level": 0.1,
     "seed": 42
   }

2. 实现真实 ARX 系统辨识与多分区评价引擎 (`backend/app/services/identification_service.py` 或 `backend/algorithms/identification/`):
   - 离散时间 MISO ARX 方程:
     y(t) + a_1 y(t-1) + ... + a_{na} y(t-na) = b_{1,0} u_1(t-d_1) + ... + b_{m,0} u_m(t-d_m) + ... + e(t)
   - 滞后回归矩阵 X 构造。
   - 参数估计方法:
     - 普通最小二乘 (OLS): θ = (X^T X)^{-1} X^T Y
     - 岭回归 (Ridge): θ = (X^T X + α I)^{-1} X^T Y
   - 数据严格按时间顺序划分 (绝不随机打乱!):
     - Train (前 60%)
     - Validation (中间 20%)
     - Test (后 20%)
   - 计算指标: RMSE, MAE, R², FIT = 100 * (1 - ||y - y_hat|| / ||y - mean(y)||)。
   - 输出实际 y(t) 与预测 ŷ(t) 序列、残差 e(t) 数组，支持前端 ECharts 对比图。

3. 更新 API 路由接口并保留全局契约:
   - `POST /api/v1/simulation/generate`: 触发真实仿真算法生成并返回真实 Ground Truth 结构。
   - `POST /api/v1/modeling/arx/fit`: 触发真实 ARX 矩阵求解并返回拟合指标与对齐序列。

4. 编写自动化算法测试 (`backend/tests/test_simulation.py` & `test_arx.py`):
   - 验证无噪声条件下的 S1 场景辨识出的参数误差 < 1%。
   - 验证数据划分未打乱时间顺序。
   - 验证固定 random seed 后的结果可完全复现。

================================================================================
【约束与协作规则】
================================================================================
1. 保持 API 路径和数据结构与阶段 1 `backend/openapi.json` 完全兼容。
2. 不修改 `frontend/` 目录。
3. 算法代码放在 `backend/algorithms/` 或 `backend/app/services/` 中。
4. 完成后运行:
   - cd backend && .venv/bin/pytest
   - 更新 PHASE_STATUS.md 进入阶段 2 验收。

请现在开始编写阶段 2 仿真与 ARX 辨识算法代码！
```
