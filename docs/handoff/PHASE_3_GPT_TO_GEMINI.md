# 阶段 3：GPT → Gemini 数据资产前端接入交接文档

**项目**：IndusOpt 工模智优  
**交接版本**：`HANDOFF-GPT-3.0`  
**后端状态**：已完成并通过 PostgreSQL Docker 闭环验证  
**Gemini 任务**：仅修改 `frontend/`，完成数据资产 Hub 与详情页对真实阶段 3 API 的接入、移除演示回退数据，并回写 `PHASE_3_GEMINI_TO_GPT.md`。

## 1. 本次后端交付

- 真实 `multipart/form-data` CSV 上传，扩展名、MIME、100 MiB、SHA-256 去重校验；支持 UTF-8、GBK、GB2312 和逗号、分号、Tab。
- 原始文件仅首次写入 `backend/data/uploads/{dataset_id}_raw.csv`；读取、预览和画像均不改写原文件。
- Alembic 新版本：`0002_datasets_and_profiles`，含 `datasets`、`dataset_versions`、`dataset_columns`、`dataset_profiles`、`processing_runs`。
- 真正的列表、详情、列映射、质量 Profile、版本 DAG 与删除接口。
- 质量画像：缺失/最大连续缺失、时间跨度、采样周期、直方图、不规则率、重复时间戳、冻结段、IQR 候选异常、均值/标准差/极值/分位数、`quality_score` 和 `recommendations`。

后端没有修改 `frontend/`。完整验证：`23 passed`、Ruff、Mypy、OpenAPI JSON，及 Docker PostgreSQL 上传 → Profile → 配置闭环均通过。

## 2. 必须理解的响应信封

Axios 拦截器会自动从以下响应中返回 `data`：

```json
{"success": true, "data": {"...": "..."}, "error": null, "request_id": "UUID"}
```

因此前端 API 函数拿到的是下列 `data` 对象，而不是最外层信封。

## 3. API 对接表

| 接口 | 实际 `data` 形状 | Gemini 适配要点 |
|---|---|---|
| `POST /datasets/upload` | `{dataset, parse_task, deduplicated}` | 使用 `FormData`，字段名为 `file`，可选 `name`；不要手动设置 multipart `Content-Type`。HTTP 仍为 202，但 `parse_task.status` 已是 `succeeded`。 |
| `GET /datasets?page=1&page_size=20` | `{items: DatasetSummary[], page}` | 现有 `getDatasets(): DatasetItem[]` 不正确，应返回/消费 `data.items`。 |
| `GET /datasets/{id}` | `DatasetDetail` | 有 `columns`、`preview`、时间范围和兼容投影字段。 |
| `POST /datasets/{id}/config` | `{dataset: DatasetDetail, profile: DatasetProfile}` | 配置一个时间列、至少一个输入列、一个输出列。 |
| `GET /datasets/{id}/profile` | `DatasetProfile` | 现有详情页需要删除 mock Profile，直接渲染真实评分和建议。 |
| `GET /datasets/{id}/versions` | `{dataset_id, active_version_id, nodes, edges}` | 现有 API 类型为数组，需改为消费 `nodes`（并可用 `edges` 绘制 DAG）。 |
| `DELETE /datasets/{id}` | `{dataset_id, status: "deleted"}` | 现有类型 `{deleted: boolean}` 不匹配；成功后刷新列表。 |

## 4. 关键字段映射

`DatasetSummary` 保留了阶段 1 字段，也新增了方便当前页面接入的兼容投影：

```ts
{
  id, name, source, status,
  row_count, column_count, latest_version_id,
  created_at, updated_at,
  version_id, file_size_bytes, col_count,
  time_column, input_columns, output_column
}
```

上传完成时只自动确认 `time_column`；`input_columns` 为空、`output_column` 为 `null` 是正常状态。用户完成列配置后，这些字段才会有建模语义。列表页面可显示“待配置”而非模拟变量名。

`DatasetProfile` 的主要前端字段如下：

```ts
{
  dataset_id, version_id,
  total_rows, total_cols, missing_rate, missing_rates,
  max_consecutive_missing, anomaly_counts,
  interval_histogram: Array<{ bin: number; count: number }>,
  duplicate_timestamp_count, irregular_sampling_rate,
  frozen_segments, constant_columns,
  time_range_start, time_range_end, sample_period_seconds,
  column_statistics: Record<string, {
    count: number; mean: number | null; std: number | null;
    min: number | null; max: number | null;
    q25: number | null; q50: number | null; q75: number | null;
  }>,
  quality_score, recommendations, quality_issues
}
```

所有比例（如 `missing_rate`、`irregular_sampling_rate`、各 `missing_rates`）均为 `0–1`，前端显示时乘以 `100` 并格式化。`quality_score` 为 `0–100`。

## 5. 字段配置请求

推荐使用显式形式，角色允许别名 `time` / `ignored`（后端会规范化为 `timestamp` / `ignore`）：

```json
{
  "columns": [
    {"name": "timestamp", "role": "time"},
    {"name": "u1", "role": "input", "unit": "MW"},
    {"name": "u2", "role": "input", "unit": "MW"},
    {"name": "y", "role": "output", "unit": "bar"},
    {"name": "operator_note", "role": "ignored"}
  ]
}
```

也支持紧凑形式：

```json
{
  "time_column": "timestamp",
  "input_columns": ["u1", "u2"],
  "output_column": "y",
  "ignored_columns": ["operator_note"]
}
```

非法映射返回 `INVALID_DATASET_SCHEMA`；时间列不可解析时返回 `TIMESTAMP_PARSE_FAILED`。请用已有 `ApiError.code` 在表单附近显示可读提示，而不要回退到 mock。

## 6. 建议的前端变更范围

1. 在 `frontend/src/api/datasets.ts` 增加真实 `uploadDataset(file, name?)` 和 `configureDataset(id, payload)`，修正列表、版本、删除的返回类型。
2. 在 `frontend/src/types/api.ts` 对齐上述真实字段；保持其余阶段接口不变。
3. 在 `DatasetsView.vue` 将 Element Plus 上传改为自定义请求或 `http-request`，成功后显示去重提示并刷新真实列表；删除 `fetchDatasets` 的 catch mock。
4. 在 `DatasetDetailView.vue` 用路由 ID 获取真实 Detail/Profile/Versions，移除静态曲线、静态质量分和静态版本时间线；暂无配置 UI 时至少显示“待配置”，不要伪造输入/输出变量。
5. 运行 `npm test` 与 `npm run build`，使用一个真实 CSV 手工确认上传、配置、Profile、删除流程。

## 7. 后端运行与验证

```bash
cd /Users/maguayuhui/Documents/竞赛/服外/A14
docker compose up --build -d
docker compose exec -T backend alembic current
# 预期：0002_datasets_and_profiles (head)
docker compose down
```

本地后端回归：

```bash
cd /Users/maguayuhui/Documents/竞赛/服外/A14/backend
.venv/bin/pytest          # 23 passed
.venv/bin/ruff check .
.venv/bin/mypy app algorithms
```

## 8. 已知边界与下一步

- 删除会级联删除 PostgreSQL 中的元数据；原始上传文件保留为不可变审计证据，且不会再出现在 API 列表中。
- 阶段 2 历史仿真清单尚未回填到阶段 3 的 PostgreSQL 数据资产表；仿真/ARX 的既有本地产物和前端联调未受影响。若需要在数据资产 Hub 统一显示仿真数据，应在下一阶段添加显式导入/登记，而不是伪造一份上传记录。
- 本阶段不实现清洗、重采样、动态区间、时滞和共线性算法；完成前端验收后，下一阶段进入预处理。
