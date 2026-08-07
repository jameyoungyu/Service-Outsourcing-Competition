# IndusOpt API 通用约定

版本：`API-1.0`  
状态：阶段 1 已冻结。字段、可选性和 HTTP 状态码以 [`backend/openapi.json`](../../backend/openapi.json) 为唯一机器可读来源。

## 基础规则

- 基础路径为 `/api/v1`；JSON 属性名均使用 `snake_case`。
- 资源 ID、`request_id`、`task_id`、`study_id`、`model_id` 均为 UUID。时间均为带时区的 ISO 8601 / RFC 3339 字符串。
- CORS 允许本地 Vite 开发源 `5173` 与 `3000`；响应附带 `X-Request-ID`，且与 body 中的 `request_id` 相同。
- 文件上传使用 `multipart/form-data`，字段名为 `file`，可选显示名字段为 `name`。阶段 3 在请求内完成 CSV 校验、落盘和画像计算，但为兼容已冻结契约仍返回 HTTP `202` 和已完成的 `data.parse_task`。

## 响应信封

所有 v1 路由（包括健康检查）使用同一顶层结构。HTTP 成功时：

```json
{
  "success": true,
  "data": {},
  "error": null,
  "request_id": "e4f83cf8-538b-4f7e-b96c-0dc0687f0dd1"
}
```

HTTP 4xx/5xx 时：

```json
{
  "success": false,
  "data": null,
  "error": {
    "code": "DATASET_NOT_FOUND",
    "message": "数据集不存在",
    "details": {"dataset_id": "..."}
  },
  "request_id": "e4f83cf8-538b-4f7e-b96c-0dc0687f0dd1"
}
```

客户端必须以 HTTP 状态码和 `success` 共同判断结果，不能解析 Python 异常文本。`details` 仅放机器可读的补充数据；它可以为空对象。

## 状态码与异步任务

- `200`：读取、确认、取消请求已完成。
- `201`：仿真数据资源已创建。
- `202`：已排入后台处理队列；`data.task` 是后续轮询与取消的统一资源。
- `400`：领域规则或参数组合不成立。
- `404`：资源不存在或已删除。
- `413`：文件超过配置限制。
- `422`：路径、查询或请求体未通过 Pydantic 校验，错误码为 `REQUEST_VALIDATION_FAILED`。
- `503`：就绪检查的 PostgreSQL 或 Redis 不可用。

所有任务资源都有 `queued`、`running`、`waiting_confirmation`、`succeeded`、`partial_success`、`failed`、`cancelled` 状态，以及可直接渲染的 `progress`。取消是协作式的：`POST /tasks/{task_id}/cancel` 只表示取消请求已经登记，worker 会在检查点停止。

## 数据与图表

- 后端返回结构化序列、指标、区间和版本 DAG，不返回 ECharts option。
- 可能很长的图表数据带有 `recommended_downsample_factor`。客户端下采样不改变真实数据版本。
- `train`、`validation` 和 `test` 指标严格分区；Optuna 目标只能读取验证集，测试集指标仅在模型冻结后产生。
- 原始上传数据不可覆盖。清洗等处理输出新的 `derived_version_id`；版本图通过 `nodes` 和 `edges` 表示。

## 阶段 1 实现说明

阶段 2 已将 `POST /simulation/generate` 与 `POST /modeling/arx/fit` 替换为真实的同步计算和本地受控产物持久化。两者仍使用阶段 1 的成功信封；ARX 结果中的 `task.status` 为 `succeeded`，表示本次同步运行已经完成。

阶段 3 已实现 `POST /datasets/upload`、`GET /datasets`、`GET /datasets/{id}`、`DELETE /datasets/{id}`、`POST /datasets/{id}/config`、`GET /datasets/{id}/profile` 和 `GET /datasets/{id}/versions`。上传原文件只读保存在 `data/uploads/`；删除会级联删除数据库元数据，原始文件保留为不可变审计证据，不会出现在任何列表中。

预处理、Optuna 和 Copilot 路由仍是阶段 1 的 schema-valid stub。空数组、空指标或 `queued` 任务表示“接口字段已冻结，业务实现待后续阶段接入”，不代表算法结果。
