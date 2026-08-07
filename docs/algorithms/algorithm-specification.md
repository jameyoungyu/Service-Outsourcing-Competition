# IndusOpt 算法规范

版本：`ALG-0.1`  
状态：接口语义冻结，具体实现参数将在对应阶段通过仿真实验校准。

## 1. 通用工具契约

所有算法工具遵循以下逻辑接口：

```python
class AlgorithmTool:
    name: str
    version: str
    input_schema: type
    parameter_schema: type
    output_schema: type

    def execute(self, context, parameters):
        ...
```

通用要求：

- 输入对象必须是已校验、不可变的数据版本；
- 参数由 Pydantic 2 校验；
- 输出包含状态、摘要、产物引用、告警和运行统计；
- 算法不得直接修改数据库或覆盖文件；
- 随机算法必须显式接收 `random_seed`；
- 每次运行记录工具版本、代码提交、参数和输入校验和；
- 异常使用稳定错误码，不把 Python 堆栈直接暴露给前端。

## 2. 数据质量诊断 `profile_dataset`

**输入**：数据版本、时间列、输入列、输出列。  
**参数**：冻结阈值、常量容差、采样间隔容差。  
**输出**：行列数、时间范围、采样间隔统计、不规则比例、缺失率、最长缺失、重复时间戳、常量列、冻结段、分位数、基础相关性、质量问题列表、完整性评分。  
**异常**：`TIMESTAMP_PARSE_FAILED`、`NO_NUMERIC_SIGNAL`、`INSUFFICIENT_ROWS`。

完整性评分必须输出分量，不使用不可解释的单一分数。初始建议：

```text
completeness_score = 100
  - missing_penalty
  - duplicate_timestamp_penalty
  - irregular_sampling_penalty
  - constant_or_freeze_penalty
  - invalid_value_penalty
```

## 3. 时间规整 `align_and_resample`

**输入**：数据版本。  
**核心参数**：目标采样周期、聚合方式、重复时间戳策略、插值方式、最大连续插值长度。  
**输出**：规整版本、时间戳修改统计、插值掩码、丢弃行统计。  
**规则**：

- 先排序，再处理重复，再重采样；
- 输入变量默认可使用前向填充或线性插值；输出变量默认仅线性插值；
- 超过最大连续缺失长度的区间保持缺失并标记不可用；
- 不允许跨训练/验证/测试边界插值。

## 4. 异常检测 `detect_anomalies`

第一版方法：

- IQR：基于训练集分位数；
- Z-score：基于训练集均值和标准差；
- Hampel：滚动中位数与 MAD；
- 冻结值：窗口内极差低于容差；
- 漂移：滚动均值相对基线的持续偏移；
- Isolation Forest 为 P1。

**输出**：每个点的异常类型、检测器、分数、阈值和证据。  
**关键规则**：检测与处理分离；检测结果不自动替换原值。

## 5. 清洗 `clean_data`

**输入**：数据版本、异常检测结果。  
**参数**：每类异常的处理策略：保留、置空、局部中位数、线性插值、截尾。  
**输出**：清洗版本、变更明细、处理前后统计。  
**禁止**：对冻结段或长缺失段无条件插值；把正常阶跃当作尖峰批量删除。

## 6. 动态区间检测 `detect_dynamic_segments`

### 6.1 特征

在长度为 `W` 的滑动窗口内计算：

- 输入变化能量：`E_u = mean(sum_j (Δu_j)^2)`；
- 输出变化能量：`E_y = mean((Δy)^2)`；
- 滚动方差和局部线性斜率；
- 估计 SNR；
- 输入变化与滞后输出变化的响应关联；
- 异常比例和缺失比例；
- 稳态持续时间。

### 6.2 质量分数

所有分量先使用训练集稳健分位数归一化到 `[0,1]`：

```text
Q = 0.25 * input_energy
  + 0.20 * output_energy
  + 0.20 * snr
  + 0.20 * response_association
  + 0.15 * duration_score
  - 0.25 * anomaly_ratio
  - 0.20 * missing_ratio
  - 0.20 * steady_state_penalty
  - 0.10 * short_segment_penalty
```

权重是第一版默认值，可由阶段 5 的 S3 仿真实验校准；报告必须同时展示所有分量和最终权重。

### 6.3 区间后处理

- 连续高分窗口合并；
- 间隔小于 `merge_gap` 的区间可合并；
- 小于 `min_segment_length` 的区间默认删除；
- 不跨数据分区边界合并；
- 区间集合可由用户启用/禁用，不改写源数据。

## 7. 时滞估计 `estimate_delays`

### 7.1 候选生成

训练集上对输入和输出执行：

1. 缺失处理；
2. 稳健标准化；
3. 去趋势或一阶差分；
4. 计算 `lag ∈ [0, max_lag]` 的互相关；
5. 提取局部峰、绝对相关和置信度；
6. 为每个输入保留 Top-K 候选。

### 7.2 最终选择

对于候选时滞组合：

- 在训练集拟合固定低阶 ARX；
- 在验证集比较 FIT、NRMSE 和残差相关；
- 以验证目标最优且复杂度合理的组合作为最终时滞；
- 若候选性能差异小于容差，输出不确定性并要求确认。

互相关最大值不得直接作为最终答案。

### 7.3 补偿

按每个输入的最终 `nk` 构造对齐视图，裁剪无效边界，不进行循环移位或未来信息填充。

## 8. 共线性分析 `analyze_collinearity`

**指标**：Pearson、Spearman、VIF、设计矩阵条件数。  
**默认告警阈值**：`|r| ≥ 0.90`、`VIF ≥ 10`、条件数 `≥ 30`；阈值可配置并必须在报告中记录。  
**输出**：变量对、相关组、VIF 排名、矩阵稳定性、建议和理由。

VIF 定义：

```text
VIF_j = 1 / (1 - R_j²)
```

## 9. 变量选择 `select_variables`

第一版采用规则 + 验证集复核：

1. 从每个高相关组中生成保留候选；
2. 优先保留工业意义明确、缺失少、动态贡献高的变量；
3. 比较删除前后验证集 FIT、NRMSE、参数条件数；
4. 只有指标不显著恶化且稳定性改善时给出删除建议；
5. 正式删除需用户确认。

PCA、PLS、Lasso 不进入 MVP 主流程。

## 10. ARX 辨识 `fit_arx`

### 10.1 模型

对于 `m` 个输入：

```text
y(k) + a1 y(k-1) + ... + a_na y(k-na)
= Σ[j=1..m] Σ[l=1..nb_j] b[j,l] * u_j(k - nk_j - l + 1) + e(k)
```

其中：

- `na ≥ 1`；
- 每个输入有独立 `nb_j ≥ 1`；
- 每个输入有独立 `nk_j ≥ 0`；
- 阶次上限由样本量约束；
- 第一版支持 OLS 与 Ridge。

### 10.2 回归矩阵

- 只使用历史输出和历史/当前允许输入；
- 构造完成后统一裁剪前导无效样本；
- 保存特征列顺序和参数映射；
- 训练、验证、测试使用相同 schema。

### 10.3 数值稳定性

- OLS 使用稳定的最小二乘求解，不直接求逆；
- Ridge 不惩罚截距；
- 检查秩、条件数、有限值和样本参数比；
- 失败模型不进入正式版本。

## 11. 模型评价 `evaluate_model`

按 train/validation/test 分区分别保存：

```text
RMSE = sqrt(mean((y - ŷ)^2))
MAE  = mean(abs(y - ŷ))
R²   = 1 - SSE / SST
NRMSE = RMSE / (P95(y) - P05(y))
FIT = 100 * (1 - ||y - ŷ||₂ / ||y - mean(y)||₂)
AIC = n * ln(RSS/n) + 2p
BIC = n * ln(RSS/n) + p * ln(n)
```

使用 P95-P05 的稳健范围定义 NRMSE；范围为零时返回不可定义错误，不用无穷值代替。

P1 残差评价：残差均值、Ljung-Box、残差自相关、残差与输入互相关。

## 12. 闭环优化 `optimize_pipeline`

### 12.1 搜索空间

可包含：

- 重采样周期；
- 插值方式与最大插值长度；
- 异常检测算法和阈值；
- 平滑窗口；
- 动态窗口、质量阈值、最短区间；
- 候选时滞；
- 变量策略；
- `na`、`nb`、`nk`；
- Ridge `alpha`。

搜索空间必须有工程边界，禁止无限范围。

### 12.2 目标函数

最大化：

```text
objective = 0.45 * clip(FIT_val / 100, -1, 1)
          - 0.25 * clip(NRMSE_val, 0, 3)
          - 0.15 * residual_correlation_penalty
          - 0.10 * complexity_penalty
          - 0.05 * insufficient_data_penalty
```

- 测试集指标不进入目标函数；
- 不可定义或数值不稳定的 Trial 失败或被剪枝；
- 每个 Trial 保存完整参数、输入版本、中间版本、训练/验证指标、耗时和失败原因；
- 最佳方案冻结后才计算测试指标。

### 12.3 停止条件

满足任一条件：最大 Trial 数、超时、连续若干 Trial 无提升、用户取消、达到预设验证目标。

## 13. Agent 结构化计划

计划必须符合：

```json
{
  "goal": "string",
  "dataset_id": "uuid",
  "steps": [
    {
      "step_id": "s1",
      "tool": "profile_dataset",
      "depends_on": [],
      "parameters": {},
      "requires_confirmation": false
    }
  ],
  "stop_conditions": [],
  "assumptions": []
}
```

Validator 必须检查：工具白名单、依赖无环、数据集存在、参数合法、前置产物存在、测试集泄漏、高影响确认和资源预算。

## 14. 标准错误码

| 错误码 | 含义 |
|---|---|
| `INVALID_DATASET_SCHEMA` | 字段角色或类型不合法 |
| `INSUFFICIENT_ROWS` | 有效样本不足 |
| `TIMESTAMP_PARSE_FAILED` | 时间戳解析失败 |
| `IRREGULAR_SAMPLING_UNRESOLVED` | 不规则采样尚未处理 |
| `TOO_MUCH_MISSING_DATA` | 缺失超过允许阈值 |
| `NO_DYNAMIC_SEGMENT_FOUND` | 无合格动态区间 |
| `DELAY_UNCERTAIN` | 最终时滞不确定 |
| `COLLINEARITY_UNRESOLVED` | 共线性未处理或未确认 |
| `DESIGN_MATRIX_RANK_DEFICIENT` | ARX 矩阵秩不足 |
| `NUMERICAL_INSTABILITY` | 求解不稳定 |
| `TEST_SET_LEAKAGE_ATTEMPT` | 尝试使用测试集调参 |
| `TOOL_NOT_ALLOWED` | Agent 调用非白名单工具 |
| `PARAMETER_OUT_OF_RANGE` | 参数越界 |
| `TASK_CANCELLED` | 用户取消任务 |
