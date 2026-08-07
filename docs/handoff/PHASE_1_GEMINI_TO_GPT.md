# 阶段 1：Gemini → GPT 前端完成确认与阶段 2 交接文档

**项目**：IndusOpt 工模智优  
**交接版本**：`HANDOFF-GEMINI-1.0`  
**交接状态**：阶段 1 (工程骨架与接口契约) 已经全量完成并经过打包验证。进入阶段 2 (仿真数据生成与 ARX 基线) 后端开发交接。

---

## 1. Gemini (前端) 阶段 1 落实总结

前端已成功根据 GPT 在阶段 1 导出的 `backend/openapi.json` 建立了全量 Vue 3 + TypeScript 代码库：

1. **类型与 API 客户端**：
   - 提取了 OpenAPI 3.1.0 的全量类型定义 (`src/types/api.ts`)。
   - 封装了 Axios 响应拦截器 (`src/api/client.ts`)，能够自动解析 `success: true/false` 信封、捕捉 `request_id` 并精准处理 4xx/5xx `ErrorEnvelope`。
2. **完整页面路由与组件**：
   - 实现了 13 个业务 View 以及 403/404/500 错误视图。
   - 实现了 12 状态矩阵通用组件 (`StateView.vue`)，支持空状态、处理中、排队中、失败重试与人工确认 (HITL)。
   - 实现了 ECharts 图表通用容器 (`ChartContainer.vue`)。
3. **测试与打包**：
   - Vitest 单元测试通过 (`3 passed`)。
   - Vite 生产环境打包通过 (`built in 1.02s`)。

---

## 2. 阶段 2 给 GPT 的任务交接

阶段 1 中后端暴露的 API 均为 Schema-valid Stubs。在阶段 2 中，GPT 需要将以下路由替换为**真实的 Python 工业算法实现**：

### 2.1 仿真数据引擎 (`backend/app/services/simulation_service.py`)
- **场景 S1**：单输入单输出，低噪声，已知真值参数与滞后。
- **场景 S2**：多输入，不同输入具有不同真实时滞 ($d_1 \neq d_2$)。
- **场景 S3**：长稳态 + 短阶跃/斜坡响应。
- **场景 S4**：污染数据 (缺失值、尖峰异常、冻结段、强噪声)。
- **场景 S5**：高共线性 (构造相关系数 $r > 0.95$ 的输入变量)。
- **真值文件落盘**：包含 `system_type`, `true_na`, `true_nb`, `true_delays`, `true_parameters`, `dynamic_segments` 等。

### 2.2 ARX 系统辨识与评价 (`backend/app/services/identification_service.py`)
- 构造离散时间 ARX 滞后矩阵 $X = [y(t-1), \dots, u(t-d_1), \dots]$。
- 实现普通最小二乘 (OLS) $\hat{\theta} = (X^T X)^{-1} X^T Y$。
- 实现岭回归 (Ridge) $\hat{\theta} = (X^T X + \alpha I)^{-1} X^T Y$。
- 实现严格按时间顺序的数据划分：前 60% 训练集 (Train)、中间 20% 验证集 (Validation)、后 20% 测试集 (Test)。
- 计算真实物理指标：$RMSE, MAE, R^2, FIT = 100 \times \left(1 - \frac{\|y - \hat{y}\|}{\|y - \bar{y}\|}\right)$。
- 返回实际与预测对比数据数组 `y_true`, `y_pred`, `residuals` 供前端 ECharts 渲染。

---

## 3. 验收条件

- `pytest` 覆盖 S1-S5 仿真生成与 ARX 辨识测试（无噪声下估计参数收敛至真值）。
- `backend/openapi.json` 保持兼容。
- 阶段 2 结束时更新 `PHASE_STATUS.md` 并提交。
