# IndusOpt 数据流与状态流

版本：`DF-0.1`

## 1. 主数据流

```text
[CSV/仿真配置]
      │
      ▼
文件校验与 SHA-256 去重
      │
      ▼
原始文件 + 数据集字段映射
      │
      ▼
RAW 不可变数据版本
      │
      ├──► 质量诊断 Profile
      │
      ▼
时间规整 / 清洗 ──────────────► 新数据版本 V1/V2...
      │                               │
      ▼                               ▼
动态区间集合                    数据血缘与审计
      │
      ▼
时滞候选 → 验证集复核 → 补偿版本
      │
      ▼
共线性分析 → 用户确认 → 变量集合
      │
      ▼
训练/验证 ARX → 模型指标
      │
      ▼
Optuna 读取指标并生成下一 Trial
      │
      ├── 成功 Trial：保存中间版本、模型和指标
      └── 失败 Trial：保存参数、失败原因和耗时
      │
      ▼
冻结最佳方案 → 一次性测试集评估
      │
      ▼
优选 CSV + 流水线 JSON + 模型 JSON + 图表 + 报告
```

## 2. 控制流与数据流分离

- Agent 产生的是**控制计划**：工具名称、参数、依赖和停止条件。
- Algorithm Tool 产生的是**计算结果**：版本、区间、时滞、参数、预测和指标。
- Controller 只能依据结构化结果作出继续/停止决策。
- 报告生成器只能引用已登记的结构化结果，不能补写不存在的指标。

## 3. 数据版本状态

```text
UPLOADED
  → PENDING_CONFIGURATION
  → READY
  → PROCESSING
  → AVAILABLE
  → INVALID_FOR_MODELING
  → ARCHIVED
```

规则：

- `RAW` 版本创建后不可修改；
- `PROCESSING` 输出不可用于正式建模；
- 只有校验和、列结构和时间范围验证通过后进入 `AVAILABLE`；
- `INVALID_FOR_MODELING` 可用于查看和修复，但不能直接训练正式模型；
- `ARCHIVED` 只隐藏，不代表物理删除。

## 4. 处理运行状态

```text
PENDING → QUEUED → RUNNING → SUCCEEDED
                       ├──→ FAILED
                       ├──→ CANCEL_REQUESTED → CANCELLED
                       └──→ RETRYING → RUNNING
```

每次状态变更记录时间、触发者和原因。

## 5. 优化任务状态

```text
DRAFT → QUEUED → RUNNING → PAUSED → RUNNING
                         ├──→ COMPLETED
                         ├──→ CANCELLED
                         └──→ FAILED
```

Trial 状态：`WAITING/RUNNING/COMPLETE/PRUNED/FAIL/CANCELLED`。

- 暂停只阻止新 Trial 启动，不强行终止当前原子算法步骤。
- 取消通过 Worker 检查点协作完成。
- 恢复使用 PostgreSQL 中的 Optuna Study 和已登记中间版本。

## 6. Agent 运行状态

```text
RECEIVED
→ PLANNING
→ VALIDATING
→ AWAITING_CONFIRMATION（可选）
→ EXECUTING
→ CONTROLLING
→ COMPLETED / FAILED / CANCELLED
```

每个 Agent Step 必须保存：

- 工具名与版本；
- 输入参数；
- 输入对象 ID；
- 输出对象 ID；
- 开始与结束时间；
- 状态与错误；
- 决策理由。

## 7. 训练、验证和测试数据流

```text
完整时间轴
  ├─ Train 60%：拟合阈值、标准化、模型参数
  ├─ Gap：最大时滞 + 最大阶次保护区
  ├─ Validation 20%：选时滞、变量、阶次和寻优参数
  ├─ Gap：最大时滞 + 最大阶次保护区
  └─ Test 20%：最佳方案冻结后仅评估一次
```

任何 Trial 若请求测试集指标，Validator 必须拒绝并记录 `TEST_SET_LEAKAGE_ATTEMPT`。

## 8. 文件产物流

| 产物 | 生成时机 | 完整性校验 |
|---|---|---|
| 原始 CSV | 上传/仿真 | SHA-256、大小、编码 |
| 版本数据 | 每个处理步骤 | 行列数、列 schema、时间单调性、SHA-256 |
| 模型 JSON | 模型成功 | schema、参数数量、输入变量一致性 |
| 预测/残差文件 | 模型成功 | 时间索引与分区一致 |
| 图表 PNG/SVG | 报告任务 | 引用 run_id、指标一致 |
| 报告 HTML/PDF | 报告任务 | 引用对象完整、章节检查 |
| 导出 ZIP | 用户导出 | manifest + 每个文件 SHA-256 |

## 9. 失败时的数据保护

- 算法失败：临时输出删除或隔离，数据库保存失败记录。
- 数据库提交失败：文件保持临时态，清理任务回收。
- Worker 崩溃：超时检测将任务标记为 `ORPHANED`，允许重试。
- LLM 失败：保留结构化算法结果，报告自然语言部分可后补。
- 导出失败：不影响源数据、模型或报告记录。
