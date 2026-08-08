# IndusOpt 错误码字典

版本：`ERR-1.1`（2026-08-08 与实现对齐）
状态：阶段 1 冻结的语义不变，本版补入阶段 4–11 新增的错误码，并如实标注哪些是"已规划未实现"。
所有错误均遵循 [`api-conventions.md`](api-conventions.md) 的 `ErrorEnvelope`。

> **本版做的事**：把字典与代码逐条对了一遍。阶段 4–11 新增了 10 个实际会返回的错误码，
> 此前从未写进字典；同时字典里有 12 个是阶段 0/1 规划的、代码中并不存在，
> 照原样留着会让接入方为不会发生的分支写处理逻辑。两类都标出来了。

| 错误码 | HTTP | 含义 | 客户端建议 |
|---|---:|---|---|
| `REQUEST_VALIDATION_FAILED` | 422 | 请求字段、类型或范围不合法 | 标记对应表单字段并显示 `details.issues`。 |
| `ROUTE_NOT_FOUND` | 404 | 路由不存在 | 检查 API 基础路径和前端生成客户端版本。 |
| `DATASET_NOT_FOUND` | 404 | 数据集不存在或已删除 | 返回数据资产页重新选择数据集。 |
| `DATASET_VERSION_NOT_FOUND` | 404 | 数据版本不存在 | 刷新版本血缘并选择有效节点。 |
| `DATASET_VERSION_MISMATCH` | 400 | 请求的数据集 ID 不属于给定版本 | 使用仿真生成响应中同一组 `dataset_id` / `version_id`。 |
| `INVALID_DATASET_SCHEMA` | 400 | CSV 列角色、类型或单位不合法 | 打开列映射配置。 |
| `TIMESTAMP_PARSE_FAILED` | 400 | 时间列无法解析 | 提示时间格式或错误行。 |
| `DATASET_FILE_TYPE_INVALID` | 400 | 上传文件不是 `.csv` | 选择 CSV 文件后重新上传。 |
| `DATASET_MIME_TYPE_INVALID` | 400 | 上传 MIME 类型不属于受支持的 CSV 类型 | 导出为标准 CSV 后重试。 |
| `DATASET_FILE_TOO_LARGE` | 413 | 上传文件超过 100 MiB | 拆分文件或先在本地筛选数据。 |
| `CSV_ENCODING_UNSUPPORTED` | 400 | 文件编码无法识别或读取 | 使用 UTF-8、GBK 或 GB2312 重新导出。 |
| `DATASET_ARTIFACT_MISSING` | 404 | 已登记数据集的原始文件不可读取 | 提供 `request_id` 并联系维护者。 |
| `DATASET_PROFILE_NOT_FOUND` | 404 | 版本尚未生成质量画像 | 重新上传或检查版本状态。 |
| `INSUFFICIENT_ROWS` | 400 | 有效样本不足以执行算法 | 调整范围或使用更长数据。 |
| `IRREGULAR_SAMPLING_UNRESOLVED` | 400 | 未规整的不规则采样不能进入算法 | 先执行时间规整。 |
| `TOO_MUCH_MISSING_DATA` | 400 | 缺失率超过算法阈值 | 调整插值策略或排除区间。 |
| `NO_DYNAMIC_SEGMENT_FOUND` | 400 | 未发现合格动态区间 | 降低阈值并保留质量告警。 |
| `DELAY_UNCERTAIN` | 400 | 多个时滞候选难以区分 | 请求人工确认候选时滞。 |
| `COLLINEARITY_UNRESOLVED` | 400 | 高共线性尚未处理或确认 | 在 VIF / 相关矩阵页确认变量集。 |
| `DESIGN_MATRIX_RANK_DEFICIENT` | 400 | ARX 设计矩阵秩不足 | 减少变量或使用 Ridge。 |
| `NUMERICAL_INSTABILITY` | 400 | 估计过程数值不稳定 | 检查尺度、阶次与样本量。 |
| `SINGULAR_MATRIX` | 400 | 回归矩阵奇异 | 处理共线性后重试。 |
| `TEST_SET_LEAKAGE_ATTEMPT` | 400 | 试图用测试集调参 | 返回验证集配置。 |
| `OPTIMIZATION_NOT_FOUND` | 404 | Study 不存在 | 刷新寻优任务列表。 |
| `TASK_NOT_FOUND` | 404 | 后台任务不存在 | 刷新全局任务状态。 |
| `TASK_CANCELLED` | 409 | 任务已经被用户取消 | 显示已保存的中间产物。 |
| `TOOL_NOT_ALLOWED` | 400 | Agent 请求非白名单工具 | 仅展示白名单计划步骤。 |
| `AGENT_PLAN_INVALID` | 400 | Agent 计划存在循环、非法依赖或参数 | 请求重新规划或改用手动流程。 |
| `CONFIRMATION_NOT_FOUND` | 404 | 人工确认点不存在或已过期 | 刷新 Copilot 计划。 |
| `SYSTEM_NOT_READY` | 503 | PostgreSQL 或 Redis 不可用 | 重试就绪检查；不要提交算法任务。 |
| `SYSTEM_INTERNAL_ERROR` | 500 | 未预期服务端错误 | 呈现 `request_id` 并联系维护者。 |
| `HTTP_ERROR` | 4xx | 未映射的 HTTP 请求错误 | 显示可读提示并记录 `request_id`。 |

## 阶段 4–11 新增（已实现）

| 错误码 | HTTP | 含义 | 客户端建议 |
|---|---:|---|---|
| `PARAMETER_OUT_OF_RANGE` | 400 | 算法参数越界或互斥参数冲突 | 读 `details` 中的字段名与边界，修正后重试。 |
| `MODEL_UNSTABLE` | 400 | 辨识所得 `A(q)` 有极点在单位圆外 | 降低 `na`、增大正则，或检查数据。 |
| `PRIOR_CONSTRAINT_VIOLATED` | 400 | 模型违反工程师给定的增益符号/区间先验 | 同时复核数据与先验——两者都可能错。 |
| `NO_NUMERIC_SIGNAL` | 400 | 版本中没有可用的数值列 | 检查列角色配置是否指对了输入/输出列。 |
| `OPTIMIZATION_STUDY_NOT_FOUND` | 404 | 寻优任务不存在 | 刷新任务列表；注意后台执行的任务需用返回的 study_id 轮询。 |
| `STUDY_EXECUTION_FAILED` | 500 | 寻优执行中途失败，研究行已置为 `failed` | 查看研究状态中的 `statistics.error_code`。 |
| `REPORT_NO_RUNS` | 400 | 该版本没有可供报告引用的运行记录 | 先执行优选/辨识，再生成报告。 |
| `REPORT_CONTAINS_UNBOUND_NUMERAL` | 400 | 报告草稿含未绑定到运行记录的数字 | 系统会自动重试并最终回退到模板化结论，通常无需人工干预。 |
| `EXPORT_NO_SELECTION` | 400 | 尚未执行优选，无可导出内容 | 先在优选页产出结果。 |
| `BENCHMARK_GENERATION_FAILED` | 400 | 自评测基准的场景生成失败 | 降低样本数或更换场景后重试。 |

## 已规划但当前未实现

下列错误码在阶段 0/1 的设计中定义，**代码中不存在**，接入方不必为其编写处理分支。
保留在字典中是因为它们描述的失败模式仍然真实，将来可能实现。

`IRREGULAR_SAMPLING_UNRESOLVED`、`TOO_MUCH_MISSING_DATA`、`DELAY_UNCERTAIN`、
`COLLINEARITY_UNRESOLVED`、`SINGULAR_MATRIX`、`TEST_SET_LEAKAGE_ATTEMPT`、
`OPTIMIZATION_NOT_FOUND`（实际使用 `OPTIMIZATION_STUDY_NOT_FOUND`）、
`TASK_NOT_FOUND`、`TASK_CANCELLED`、`TOOL_NOT_ALLOWED`、`AGENT_PLAN_INVALID`、
`CONFIRMATION_NOT_FOUND`。

> Agent 的非法计划当前不通过错误码上报：计划由静态合规校验拦截，
> 校验结论以 `compliance.checks` 的逐项结果与签名证明返回，不通过即回退到规则计划。
> 这比抛一个错误码信息量更大，因此没有实现 `AGENT_PLAN_INVALID` / `TOOL_NOT_ALLOWED`。

## 关于持续激励

`INSUFFICIENT_EXCITATION` **不是错误码**。该判据曾按 `ALG-0.2` 初版实现为阻断，
实测证明它无法区分可用与不可用的数据（详见 `ALG-0.2` §3 的数据表），
因此降级为诊断字段 `validation.excitation_shortfall`，不阻断建模。

---

错误码可在后续阶段新增，但已冻结代码的语义和 HTTP 类别不得变更；如需不兼容字段或语义改动，必须提升 `/api` 主版本。
