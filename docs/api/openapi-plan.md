# IndusOpt OpenAPI 规划

版本：`API-PLAN-0.1`（阶段 0 历史资源规划）  
状态：字段级契约已在阶段 1 冻结；机器可读唯一来源为 [`backend/openapi.json`](../../backend/openapi.json)，通用规则见 [`api-conventions.md`](api-conventions.md)。

## 1. 通用约定

- 基础路径：`/api/v1`；
- JSON 字段使用 `snake_case`；
- 时间使用 ISO 8601；
- 资源 ID 使用 UUID；
- 所有响应包含 `request_id`；
- 长任务创建返回 `202 Accepted` 和任务资源；
- 文件下载通过受控 artifact endpoint，不暴露真实路径；
- 分页使用 `page/page_size`，后续大表可切换 cursor；
- 幂等创建可使用 `Idempotency-Key`。

统一成功响应：

```json
{
  "success": true,
  "data": {},
  "error": null,
  "request_id": "uuid"
}
```

统一错误响应：

```json
{
  "success": false,
  "data": null,
  "error": {
    "code": "INSUFFICIENT_ROWS",
    "message": "有效样本不足",
    "details": {
      "required": 200,
      "actual": 86
    }
  },
  "request_id": "uuid"
}
```

## 2. 阶段 1 基础接口

```text
GET /health/live
GET /health/ready
GET /system/info
```

## 3. 资源规划

### 3.1 仿真

```text
POST /simulations
GET  /simulations/{job_id}
GET  /simulation-scenarios
```

### 3.2 数据集

阶段 3 已实现并导出以下冻结兼容路径：

```text
POST   /datasets/upload
GET    /datasets
GET    /datasets/{dataset_id}
DELETE /datasets/{dataset_id}
POST   /datasets/{dataset_id}/config
GET    /datasets/{dataset_id}/profile
GET    /datasets/{dataset_id}/versions
```

下列为后续资源细化时的候选 REST 资源，不是当前 `backend/openapi.json` 的实际路径：

```text
PATCH  /datasets/{dataset_id}
GET    /datasets/{dataset_id}/columns
GET    /datasets/{dataset_id}/versions
GET    /dataset-versions/{version_id}
GET    /dataset-versions/{version_id}/preview
GET    /dataset-versions/{version_id}/lineage
```

### 3.3 质量诊断与清洗

```text
POST /dataset-versions/{version_id}/profiles
GET  /profiles/{profile_id}
POST /dataset-versions/{version_id}/resampling-runs
POST /dataset-versions/{version_id}/anomaly-runs
POST /dataset-versions/{version_id}/cleaning-runs
GET  /processing-runs/{run_id}
POST /processing-runs/{run_id}/cancel
POST /processing-runs/{run_id}/retry
```

### 3.4 动态区间

```text
POST  /dataset-versions/{version_id}/segment-detection-runs
GET   /segment-sets/{segment_set_id}
PATCH /segment-sets/{segment_set_id}/segments/{segment_id}
POST  /segment-sets/{segment_set_id}/finalize
```

### 3.5 时滞和共线性

```text
POST /dataset-versions/{version_id}/delay-analyses
GET  /delay-analyses/{analysis_id}
POST /delay-analyses/{analysis_id}/apply
POST /dataset-versions/{version_id}/collinearity-analyses
GET  /collinearity-analyses/{analysis_id}
POST /collinearity-analyses/{analysis_id}/variable-sets
```

### 3.6 ARX 模型

```text
POST /models/arx/runs
GET  /model-runs/{model_run_id}
GET  /models/{model_id}
GET  /models/{model_id}/metrics
GET  /models/{model_id}/predictions
POST /models/{model_id}/finalize
POST /models/{model_id}/test-evaluation
```

测试集评估 endpoint 必须检查模型已冻结且此前未用于调参。

### 3.7 闭环寻优

```text
POST /optimization-studies
GET  /optimization-studies
GET  /optimization-studies/{study_id}
GET  /optimization-studies/{study_id}/trials
POST /optimization-studies/{study_id}/pause
POST /optimization-studies/{study_id}/resume
POST /optimization-studies/{study_id}/cancel
POST /optimization-studies/{study_id}/finalize-best
POST /optimization-studies/{study_id}/replay-best
```

### 3.8 Agent

```text
POST /agent-runs
GET  /agent-runs/{agent_run_id}
GET  /agent-runs/{agent_run_id}/steps
POST /agent-runs/{agent_run_id}/confirmations/{confirmation_id}
POST /agent-runs/{agent_run_id}/cancel
```

### 3.9 报告和产物

```text
POST /reports
GET  /reports
GET  /reports/{report_id}
POST /reports/{report_id}/retry
GET  /artifacts/{artifact_id}/download
POST /exports
GET  /exports/{export_id}
```

## 4. 长任务状态模型

所有异步资源至少包含：

```json
{
  "id": "uuid",
  "status": "queued",
  "progress": {
    "current": 2,
    "total": 8,
    "percent": 25,
    "stage": "detect_dynamic_segments",
    "message": "正在计算窗口质量分数"
  },
  "created_at": "2026-07-27T12:00:00Z",
  "started_at": null,
  "finished_at": null,
  "error": null
}
```

这是阶段 0 的长任务资源规划。阶段 1 已以 `backend/openapi.json` 冻结实际字段；前端不得从本节推断或自行扩展字段。

## 5. 图表数据原则

后端优先返回结构化序列，不返回 ECharts option：

```json
{
  "x": ["2026-01-01T00:00:00Z"],
  "series": [
    {
      "name": "u1",
      "unit": "%",
      "values": [1.2]
    }
  ],
  "annotations": []
}
```

- 采样点过多时后端提供下采样；
- 图表数据包含单位、分区、时间范围和生成来源；
- 指标接口明确 `partition`，避免训练/验证/测试混淆。

## 6. 错误码分类

- `DATASET_*`：上传、字段、版本；
- `PROCESSING_*`：清洗、区间、时滞、共线性；
- `MODEL_*`：ARX 和评价；
- `OPTIMIZATION_*`：Study/Trial；
- `AGENT_*`：计划、工具和确认；
- `REPORT_*`：报告和导出；
- `SYSTEM_*`：依赖、配置、超时。

## 7. Gemini 使用限制

阶段 0：只做信息架构、流程、低保真原型、状态和图表规划。  
阶段 1 起：必须以生成的 `backend/openapi.json` 为唯一字段来源，不得根据本规划文件自行创建 TypeScript 业务类型或假接口。
