# 阶段 2：GPT → Gemini 真实仿真与 ARX 基线交接

**项目**：IndusOpt 工模智优  
**交接版本**：`HANDOFF-GPT-2.0`  
**状态**：阶段 2 后端实现、算法测试和 Docker 验证已完成；请 Gemini 将现有页面从演示/回退数据切换为真实 API 结果。

## 1. 已交付的后端能力

1. `POST /api/v1/simulation/generate` 真实生成 S1–S5，返回数据集 ID、版本 ID、列、行数和完整真值；同时写入受控本地产物。
2. `POST /api/v1/modeling/arx/fit` 真实读取生成版本，执行 MISO ARX OLS/Ridge，按时间顺序分区并返回真实指标、预测、残差和 ACF。
3. 真值、CSV、版本清单、模型结果分别存入 `backend/data/simulation/` 和 `backend/data/models/`；数据目录不会提交 Git，但固定 `seed` 可重建。
4. `backend/openapi.json` 已重新导出，机器字段来源仍以此文件为准。

## 2. Gemini 需要处理的前端绑定

`frontend/src/views/SimulationView.vue` 现有表单字段已经兼容：

```ts
{ scenario, dataset_name, num_samples, noise_level, seed }
```

后端也兼容较早字段名，但 Gemini 应保留上面的页面字段。响应中页面当前使用的 `dataset_id`、`dataset_name`、`version_id`、`num_rows`、`num_cols`、`columns`、`ground_truth.true_na/true_nb/true_delays/noise_level` 均为真实值。

`frontend/src/views/ARXModelingView.vue` 必须完成两处替换：

1. 去除 `catch` 中的随机 Mock 结果；失败时改用 API 的 `ErrorEnvelope` 提示和 `request_id`。
2. 从 `datasetStore` 读取当前真实 `dataset_id`、`version_id` 和输入列；调用参数使用 `na`、`nb`、`delays`、`estimation_method`。S1 默认结构为 `na=2, nb=[2], delays=[3]`；S2/S3/S5 需为每个输入提供同序数组（例如 `[2, 2]`、`[3, 8]`）。

ARX 真实响应中同时提供当前前端类型所需字段：

```ts
{
  model_id, a_coefficients, b_coefficients,
  metrics: { train_r2, train_fit, val_r2, val_fit, test_r2, test_fit, rmse },
  plot_data: { indices, y_true, y_pred, residuals, split_indices }
}
```

此外还提供 `task`（本同步运行中状态为 `succeeded`）、`residual_diagnostics` 和受控 `artifact_uri`。请重新依据 `backend/openapi.json` 生成或校对 TypeScript 类型，避免继续维护与后端不一致的手写字段。

## 3. 可验证接口流程

1. 在仿真页生成 S1，设 `noise_level=0`、`num_samples >= 1500`、任意固定 `seed`。
2. 将响应的 `dataset_id`/`version_id` 写入 Pinia 当前数据集。
3. 在 ARX 页以 S1 结构运行 OLS；预期测试 FIT > 99.99%，参数与真值接近。
4. S4 的未清洗 ARX 基线可能为负 FIT，这是故意保留的污染对照；不应回退到随机假数据掩盖它。

## 4. 未完成项与下一阶段边界

- 数据集列表、详情、上传、Profile、版本 DAG 仍为阶段 1 Schema Stub，属于阶段 3。
- 清洗、动态段、时滞、共线性、Optuna 仍未实现，后续依次属于阶段 4–8。
- 阶段 2 不需要 Gemini 修改后端或实现算法；若发现字段不足，记录后反馈给 GPT，不要在前端伪造算法输出。

## 5. 验证记录

- 后端：`17 passed`；Ruff、Mypy、OpenAPI JSON 校验通过。
- Docker Compose：后端、PostgreSQL、Redis、worker 及 Alembic `0001_operation_logs` 已验证。
- 算法基线：详见 [`../algorithms/phase-2-simulation-arx-baseline.md`](../algorithms/phase-2-simulation-arx-baseline.md)。
