# IndusOpt 算法规范 v0.2 增量

编号：`ALG-0.2`
状态：候选冻结，待开发者确认
基线：`docs/algorithms/algorithm-specification.md`（`ALG-0.1`）
依据：`docs/innovation/differentiation-blueprint.md`（`INNO-1.0`）、`docs/experiments/identifiability-ablation.md`（`EXP-1.1`）

本文件**只描述相对 `ALG-0.1` 的变更**。未提及的部分（工具契约、错误码语义、清洗、共线性等）保持 `ALG-0.1` 不变。变更项标注 `[改]`（替换原口径）、`[增]`（新增能力）、`[留]`（保留但降级用途）。

---

## 1. 变更摘要

| 章节 | 对应 ALG-0.1 | 变更 | 理由 |
|---|---|---|---|
| §2 动态区间优选 | §6 | `[改]` 主口径改为 D-最优子模优选 | 逐窗口打分无法表达信息冗余，异构激励下秩亏（EXP-1.1 §3；同场景下加权分与能量法同样失效） |
| §3 持续激励 | 无 | `[增]` PE 阶次前置判据 | 回答"数据够不够辨识 n 阶模型" |
| §4 时滞估计 | §7 | `[改]` 候选生成改用预白化互相关 | 输出自相关制造伪峰 |
| §5 模型评价 | §11 | `[改]` 主指标改为自由仿真 FIT，增稳定性/增益/白度 | 一步预测 FIT 区分度仅为 1/27.7（EXP-1.1 §5） |
| §6 约束辨识 | §10 | `[增]` 先验约束最小二乘 | 噪声下模型违反物理常识 |
| §7 闭环优化 | §12 | `[改]` 目标函数改写 + 缓存 + 多保真 + 热启动 | 目标函数无区分度；Trial 太慢 |
| §8 报告生成 | 无 | `[增]` 占位符渲染与数字字面量校验 | LLM 篡改数值 |
| §9 合规证明 | §13 | `[增]` 计划 DAG 静态数据流分析 | 把规范升级为机制 |
| §10 错误码 | §14 | `[增]` 6 个新错误码 | 覆盖新失败模式 |

---

## 2. `[改]` 动态区间优选 `detect_dynamic_segments`

### 2.1 主口径：D-最优子模优选

设 ARX 结构 `(na, nb, nk)` 固定，训练区间的回归矩阵为 `Φ`，候选窗口 `W` 的信息块 `A_W = Φ_Wᵀ Φ_W`。目标函数

```text
J(S) = log det( λI + Σ_{W∈S} A_W ),   λ = ridge > 0
```

`λ > 0` 是必需的，否则空集的 `log det` 无定义、贪心无法启动。

**求解**：lazy greedy（CELF）。边际增益用矩阵行列式引理，`M = LLᵀ` 时

```text
Δ(W | S) = log det(M + A_W) - log det(M) = log det( I + L⁻¹ A_W L⁻ᵀ )
```

每候选 `O(p³)`，`A_W` 全程只算一次。

**保证**：`J` 单调子模，等长窗口 + 基数约束下贪心解不劣于最优解的 `1 - 1/e`。lazy greedy 与朴素贪心**逐窗口结果相同**，实测候选求值减少 4.5–4.8 倍。

### 2.2 参数

| 参数 | 类型 | 默认 | 边界 | 说明 |
|---|---|---|---|---|
| `window_size` | int | 60 | [10, 2000] | 候选窗口长度（样本数） |
| `stride` | int | `window_size/2` | ≥1 | 窗口步长，重叠时按唯一行计预算 |
| `budget_rows` | int\|null | null | ≥`window_size` | 与 `budget_windows` 二选一 |
| `budget_windows` | int\|null | null | ≥1 | 与 `budget_rows` 二选一 |
| `ridge` | float | 1e-6 | >0 | 信息矩阵正则项 |
| `min_information_gain_bits` | float | 0.0 | ≥0 | 增益低于此值即停止，防止用稳态窗口凑数 |

**约束**：候选窗口不得跨训练/验证/测试分区边界；选择过程只在训练区间内进行。

### 2.3 输出

```text
selected_windows[]: {rank, window_index, start_index, end_index, n_rows,
                     information_gain_nats, information_gain_bits,
                     cumulative_log_det, input_energy, output_energy}
selected_rows, coverage_ratio, baseline_log_det, selected_log_det,
information_retention, candidate_count, evaluated_candidates,
naive_candidate_evaluations, lazy_speedup, stopped_reason, excitation{...}
```

`stopped_reason ∈ {budget_reached, row_budget_reached, information_gain_below_threshold, candidates_exhausted}`，必须在报告中展示。

**信息增益以 bit 为单位呈现**：这是每个数据段"教给模型多少信息"的物理量，取代不可解释的加权分数。

### 2.4 `[留]` 加权质量分的新用途

`ALG-0.1` §6.2 的加权分 `Q` **保留但降级**：不再决定选择结果，仅作为报告中的可解释性对照列，与信息增益并排展示。原因是工程师习惯看"能量/信噪比/响应关联"这类物理量，而信息增益是决策依据。两者并排时，二者不一致的窗口本身就是有价值的诊断信息。

实现见 `algorithms/identifiability/weighted_score.py`，按 §6.2 原始权重执行，权重由测试锁定。

**降级的依据是实测，不是设想**（`EXP-1.1` §3–§4、`EXP-2.1` §2，10 组种子）：

| 条件 | 加权分 `Q` | D-最优 `log det` |
|---|---|---|
| 同构激励、干净数据（S3） | 参数误差 3.75%，**四种策略中最好** | 4.80%，末位 |
| 异构激励（S6） | 14.81 ± 0.06%，**秩亏** | 3.49 ± 1.97%，满秩 |

即：`Q` 不是"更差的分数"，而是**在一类数据上更好、在另一类数据上结构性失效**。失效的根源是所有分量都逐窗口独立计算，公式里没有任何一项能表达"这个窗口与已选窗口信息重复"；`log det` 的增量形式天然表达这一点。主口径选 `log det` 是接受"在同构数据上让出约 1 个百分点"来换"在异构数据上不崩掉 11 个百分点并保住满秩"。

另有一条与原判断相反的实测：`EXP-1.0` §7 曾预判"完整加权分应优于纯能量法"，10 组种子实测显示两者无差异（S6 14.81% vs 14.82%，S3 1.99% vs 1.98%）。原因是干净数据上 `input_energy` / `output_energy` / `snr` 三个分量同时饱和、彼此共线，而异常率与缺失率惩罚项恒为 0。因此"加权分比能量法强"这一常见直觉在未污染数据上不成立。

---

## 3. `[增]` 持续激励判据 `profile_excitation`

信号 `u` 是 `n` 阶持续激励，当且仅当 `[u(k),...,u(k-n+1)]` 的协方差矩阵正定。有限样本下采用条件数判据：

```text
PE_order(u) = max{ n ≤ max_order : λ_min(R_n) > tol · λ_max(R_n) }
```

`tol` 默认 `1e-3`（`DEFAULT_EXCITATION_TOLERANCE`），在 S1–S6 上标定，复现教科书结论"m 次电平变化 → m 阶"（标定表见 `EXP-1.1` §6）。

**辨识 `(na, nb_j, nk_j)` 所需阶次**：`required_j = na + nb_j`。

**门限行为（本版据实修订，原口径被实测推翻）**

`ALG-0.2` 初版规定：`PE_order(u_j) < required_j` 时 `fit_arx` 返回 `INSUFFICIENT_EXCITATION` 并**阻断**建模。实现该阻断后立即在真实形态数据上失败，测量结果表明这条判据无法承担阻断的责任：

| 输入电平数 | tol=1e-3 的 PE 阶次 | tol=1e-4 的 PE 阶次 | 所需阶次 | 自由仿真 FIT |
|---:|---:|---:|---:|---:|
| 2 | 1 | 1 | 4 | −0.52% |
| 3 | 1 | **4（达标）** | 4 | **0.21%** |
| 4 | 1 | 4 | 4 | 97.37% |
| 8 | **1（不达标）** | 8 | 4 | **95.82%** |
| 20 | 3 | 8 | 4 | 98.83% |

两个方向都错：

- 在标定容差 `1e-3` 下，**8 电平输入报出阶次 1**（远低于所需 4），而它的模型自由仿真 FIT 有 95.82%——按原口径会被阻断的是一个好模型；
- 放松到 `1e-4` 后，**3 电平输入报出阶次 4（达标）**，而它的模型自由仿真 FIT 只有 0.21%——按原口径会被放行的是一个废模型。而且 `1e-4` 同时破坏了 §6 的教科书标定（单次阶跃变成 5 阶）。

**没有任何容差能把可用与不可用分开。** 因此本版把该判据降级为**诊断**：`fit_arx` 在响应的 `validation.excitation_shortfall` 中给出不达标通道的实际/所需阶次，供工程师判断，但不阻断。

真正阻断的是**设计矩阵秩亏**（`DESIGN_MATRIX_RANK_DEFICIENT`）——这也是 `EXP-1.1`、`EXP-3.0` 中实测到的真实失效模式。由 `TestExcitationIsReportedNotEnforced` 四项测试锁定，防止被悄悄改回阻断。

> 这条修订也限定了 §6 那张标定表的适用范围：`1e-3` 精确复现的是**教科书信号上的教科书结论**，不代表该估计量在真实多电平输入上同样准确。

同时输出：`log_det`、条件数、`λ_min`、A-最优值 `trace(M⁻¹)`、秩、是否秩亏。

---

## 4. `[改]` 时滞估计 `estimate_delays`

`ALG-0.1` §7.1 第 4 步「计算 lag ∈ [0, max_lag] 的互相关」替换为**预白化互相关**（Box-Jenkins prewhitening）：

1. 对输入 `u_j` 拟合 AR(p) 模型 `α_j(q)`（`p` 由 AIC 在 [1, 20] 内选择）；
2. 用 `α_j(q)` 同时滤波 `u_j` 与 `y`，得 `ũ_j`、`ỹ_j`；
3. 在 `ũ_j` 与 `ỹ_j` 之间计算互相关，取候选峰。

**理由**：输出 `y` 的强自相关会在原始互相关函数上制造宽而偏移的伪峰，多输入时该偏差是系统性的。预白化把输入滤成近似白噪声，互相关函数才正比于脉冲响应。

`ALG-0.1` §7.2 的"验证集 ARX 复核 + 不确定性上报"保持不变——预白化改善候选质量，不取代复核。

---

## 5. `[改]` 模型评价 `evaluate_model`

### 5.1 主指标改为自由仿真

```text
ŷ_sim(k) = -Σ_{i=1..na} a_i ŷ_sim(k-i) + Σ_j Σ_{l} b_{j,l} u_j(k-nk_j-l)
```

前 `max_history` 个样本用实测输出热启动，之后**只用模型自身的历史预测**，不再喂入实测 `y`。

```text
FIT_sim = 100 · (1 - ‖y - ŷ_sim‖₂ / ‖y - ȳ‖₂),  下限截断至 -100
```

一步预测 FIT **保留但降级**为诊断量。报告必须同时展示两者及其差值 `fit_gap`：**`fit_gap` 大意味着模型在靠自相关"抄答案"，是过拟合的直接信号。**

### 5.2 新增入库前检查

| 检查 | 判据 | 不通过的处理 |
|---|---|---|
| 稳定性 | `A(q)` 全部极点模 < 1 | 拒绝入库，`MODEL_UNSTABLE` |
| 稳态增益 | `K_j = Σb_j / (1 + Σa)` | 与先验冲突时 `PRIOR_CONSTRAINT_VIOLATED` |
| 残差白度 | 自相关落在 `±1.96/√N` 内的滞后比例 | < 0.6 时告警，不阻断 |

对开环不稳定或积分型过程，自由仿真会发散：此时改用 `N` 步预测 FIT（默认 `N = 20`，可配置），并在报告中标注所用口径。

---

## 6. `[增]` 先验约束辨识

工程师先验经 Agent 解析为结构化约束：

```json
{
  "gain_sign":   {"u1": "positive"},
  "gain_bounds": {"u1": [0.5, 2.0]},
  "delay_min":   {"u1": 6},
  "require_stable": true
}
```

| 约束 | 数学形式 | 作用位置 |
|---|---|---|
| 增益符号 | `sign(Σb_j / (1+Σa)) = s_j` | 带线性约束最小二乘；不可行时 Trial 拒绝 |
| 增益区间 | `K_min ≤ K_j ≤ K_max` | 同上 |
| 时滞下界 | `nk_j ≥ n_min` | 时滞搜索空间下界 |
| 稳定性 | `A(q)` 极点在单位圆内 | 入库前拒绝 |

**实现优先级**：优先用投影法/等式消元（无新依赖）；SciPy QP 作为可选路径。增益约束在 `1+Σa` 已知时对 `b` 是线性的，可用交替方案：先无约束估计 `a`，再在固定 `a` 下对 `b` 做约束最小二乘，迭代至收敛。

**审计要求**：每条先验必须记录来源（用户原话、解析结果、确认时间）并出现在报告中。先验是**可追溯的工程输入**，不是隐藏的调参手段。

---

## 7. `[改]` 闭环优化 `optimize_pipeline`

### 7.1 目标函数

`ALG-0.1` §12.2 的目标函数替换为：

```text
objective = 0.45 · clip(FIT_sim_val / 100, -1, 1)
          - 0.20 · clip(NRMSE_sim_val, 0, 3)
          - 0.15 · gain_prior_penalty
          - 0.10 · (1 - residual_whiteness_ratio)
          - 0.10 · complexity_penalty
```

其中 `FIT_sim_val` 是**验证集自由仿真 FIT**。不稳定模型直接判为失败 Trial（不参与排序）。

测试集不进入目标函数这一条不变。

### 7.2 多目标（可选）

支持 NSGA-II 三目标：`max FIT_sim_val`、`min gain_error`、`min complexity`。输出 Pareto 前沿供工程师选点，而非用一组加权系数替工程师决定。默认仍走单目标 TPE，多目标为高级选项。

### 7.3 血缘即缓存

数据版本键定义为

```text
version_key = SHA256( parent_key ‖ tool_name ‖ tool_version ‖ canonical_json(params) ‖ code_commit )
```

`canonical_json` 为键排序、浮点定精度序列化。Trial 执行时逐步查表命中即复用中间版本，不重算。

**这不是新增缓存系统**：`scope-freeze.md` §2.3 已要求数据版本保存父版本、参数、代码版本与校验和，本节只是把这套血缘元数据直接当作内容寻址键使用。

必须上报：`cache_hit_rate`、`speedup_ratio`、`mean_trial_seconds`、`pruned_trial_ratio`。

### 7.4 多保真与热启动

- **剪枝**：Optuna `HyperbandPruner`。Trial 先在 25% 窗口预算上评估，达标才提升到全预算。
- **热启动**：由数据画像指纹 k-NN 检索策略记忆库，经 `study.enqueue_trial()` 注入初始 Trial。
- **回退**：若热启动 Trial 在 10 轮内未超越默认基线，回退到默认搜索空间并记录该事件。

### 7.5 策略记忆库

```text
fingerprint = [sample_period, missing_rate, irregular_rate, snr_estimate,
               dynamic_ratio, n_inputs, collinearity_condition_number,
               delay_spread, pe_order_min, pe_order_max]
```

分量按训练集稳健分位数归一化后取欧氏距离。记录 `(fingerprint, best_params, achieved_metrics, dataset_id, created_at)`。

**防泄漏**：记忆库只保存参数与训练/验证指标，不保存任何测试集信息。跨数据集复用参数不构成测试集泄漏，但同一数据集的历史记录不得用于该数据集自身的热启动。

出厂预置 S1–S6 的寻优结果，避免冷启动时功能不可见。

---

## 8. `[增]` 报告生成 `generate_report`

**LLM 禁止输出数字字面量。** 只能输出占位符：

```text
{{run:<run_id>.<path>}}      例：{{run:r_8f2a.metrics.free_run_fit}}
{{chart:<artifact_id>}}
```

渲染流程：

1. LLM 产出带占位符的报告草稿；
2. **校验器扫描草稿，检测未被占位符包裹的数字字面量**（允许白名单：条目编号、章节号）；
3. 命中即判违规，记录审计日志并触发重新生成（最多 3 次，仍失败则回退到模板化报告）；
4. 渲染器从运行数据库解析占位符，替换为真实值，附 `run_id` 与输入校验和的可点击溯源。

错误码：`REPORT_CONTAINS_UNBOUND_NUMERAL`。

---

## 9. `[增]` 合规证明

`ALG-0.1` §13 的 Validator 扩展为执行前的**静态数据流分析**，产出机器可检验证明：

| 检查项 | 分析方式 |
|---|---|
| 工具白名单 | 计划 DAG 节点名集合 ⊆ 白名单 |
| 测试集零触及 | 沿 DAG 追踪数据版本的分区标签，任一节点读入 `test` 即失败 |
| 拟合型变换仅用训练集 | 标注哪些工具参数是"拟合得到的"，检查其估计来源分区 |
| 无跨分区插值 | 检查插值工具的输入区间与分区边界 |
| 高影响操作已确认 | 变量删除、覆盖导出、长任务启动节点必须有确认记录 id |
| DAG 无环、依赖完备 | 拓扑排序 |

证明体包含检查项、结论、覆盖的中间版本数、`sha256` 签名与代码版本，附在报告首页。任一项失败则计划不得执行，返回对应错误码。

---

## 10. `[增]` 新增错误码

| 错误码 | 含义 |
|---|---|
| `INSUFFICIENT_EXCITATION` | 持续激励阶次低于所选模型阶次所需 |
| `MODEL_UNSTABLE` | `A(q)` 存在单位圆外极点 |
| `PRIOR_CONSTRAINT_VIOLATED` | 辨识结果与工程师先验冲突 |
| `SELECTION_BUDGET_INVALID` | `budget_rows` 与 `budget_windows` 未二选一或越界 |
| `REPORT_CONTAINS_UNBOUND_NUMERAL` | LLM 报告草稿含未溯源的数字字面量 |
| `COMPLIANCE_PROOF_FAILED` | 计划未通过静态数据流分析 |

`ALG-0.1` §14 的既有错误码全部保留。

---

## 11. 已实现与待实现

**已实现并通过测试**（`backend/algorithms/identifiability/`，27 个 Pytest、Ruff、Mypy 通过）：

- §2 D-最优子模优选（含 lazy greedy 与 energy 对照基线）
- §3 持续激励判据与信息矩阵画像
- §5.1 自由仿真 FIT、`fit_gap`
- §5.2 稳定性检查、稳态增益、残差白度

**待实现**：§4 预白化时滞、§5.2 与先验的联动、§6 约束辨识、§7 全部、§8、§9。

**接入点**：现有 `app/services/identification_service.py` 与 `algorithms/identifiability/regressor.py` 的回归矩阵口径一致（同样的 `-y(k-lag)` 与 `u(k-nk-l)` 布局、同样的分区保护间隔语义），阶段 5–7 可直接复用，无需重写。
