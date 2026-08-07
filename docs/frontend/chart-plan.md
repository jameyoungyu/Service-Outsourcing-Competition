# IndusOpt 工模智优 - 数据可视化与图表规划 (Chart Plan)

**文档版本**：`v0.1.0`  
**适用阶段**：阶段 0（需求与设计冻结）  
**责任角色**：Gemini (前端与可视化架构师)  

---

## 1. 可视化规划原则

IndusOpt 项目的核心算法价值必须通过**高质量的数据可视化证据**向建模工程师和答辩评审呈现。所有图表采用 **ECharts 5** 实现，并遵循：
* **数据线索一致性**：同一变量（如 $u_1$）在数据预览、时滞、共线性与 ARX 辨识图中保持统一颜色（亮绿 `#2A9D8F`）。
* **真实后端映射**：前端图表不伪造随机噪点或死数据，所有绘制数据数组（`xData`, `seriesData`）必须由后端 OpenAPI 的计算结果填充。

---

## 2. 核心图表设计明细表

| 图表 ID | 业务场景 | 图表类型 (ECharts) | 必须包含的视觉元素 | 后端 API 数据字段映射需求 |
|---|---|---|---|---|
| **CHT-01** | 多变量原始时序总览 | 多 Y 轴折线图 (`line`) | - 多变量上下叠加/多 Y 轴<br>- `dataZoom` 时间轴缩放<br>- 图例开关 (Legend)<br>- 下采样 (LTTB) 标记 | `timestamps: string[]`<br>`inputs: Record<string, number[]>`<br>`output: number[]` |
| **CHT-02** | 质量诊断 - 缺失率与异常 | 柱状图 (`bar`) + 散点标记 | - 缺失率百分比柱<br>- 异常点定位 Scatter 点<br>- 警戒线 (`10%` 缺失率) | `profile.missing_rates: Record<string, number>`<br>`profile.anomaly_counts: Record<string, number>` |
| **CHT-03** | 采样间隔分布 | 直方图 (`bar`) | - 期望采样周期 $T_s$ 标记<br>- 偏离频次分布 | `profile.interval_histogram: { bin: number, count: number }[]` |
| **CHT-04** | 清洗前后对比 | 叠加双折线 (`line`) + 离群点标记 | - 原始数据 (半透明灰色)<br>- 清洗后数据 (高亮深蓝)<br>- 被剔除异常点 (红色 `x` 标记) | `raw_series: number[]`<br>`cleaned_series: number[]`<br>`replaced_indices: number[]` |
| **CHT-05** | 动态响应区间优选 | 时序折线 + 背景半透明矩形 (`markArea`) | - 提取出的动态段背景高亮<br>- 各区间 SNR 与动态度 Score Badge<br>- 丢弃的稳态段背景灰化 | `series: number[]`<br>`segments: { start_idx: number, end_idx: number, snr: number, score: number }[]` |
| **CHT-06** | 时滞 Lag-Correlation | 多系列折线图 (`line`) | - 横轴: 滞后步数 $\tau \in [0, \tau_{max}]$<br>- 纵轴: 相关系数 $r$<br>- 最佳 Peak 点 Marked Pin | `delays: number[]`<br>`correlations: Record<string, number[]>`<br>`best_delays: Record<string, number>` |
| **CHT-07** | 共线性 Pearson 矩阵 | 2D 热力图 (`heatmap`) | - 颜色渐变 (白 -> 浅红 -> 深红)<br>- 单元格内浮显数值 $r \in [-1, 1]$<br>- 强相关格子 ($r>0.85$) 红色边框 | `variables: string[]`<br>`matrix: number[][]` |
| **CHT-08** | VIF 方差膨胀因子 | 水平条形图 (`bar`) | - 横轴: VIF 数值<br>- $VIF=10$ 红色虚线警戒线<br>- 超过 10 的变量标红警告 | `vif_scores: Record<string, number>` |
| **CHT-09** | ARX 模型拟合与预测 | 叠加折线图 (`line`) + 残差子图 | - 上图: 实际输出 $y(t)$ vs 预测 $\hat{y}(t)$<br>- 下图: 残差 $e(t) = y(t) - \hat{y}(t)$<br>- 划分线 (Train | Validation | Test) | `y_true: number[]`<br>`y_pred: number[]`<br>`residuals: number[]`<br>`split_indices: { train: number, val: number, test: number }` |
| **CHT-10** | 残差自相关 ACF | 垂直棒图 (`stem/bar`) | - 滞后阶数 $k$<br>- 95% 置信区间上下包络线 ($\pm 1.96/\sqrt{N}$) | `acf_values: number[]`<br>`confidence_interval: number` |
| **CHT-11** | Optuna 寻优收敛曲线 | 散点图 + 历史最佳折线 (`scatter + line`) | - 横轴: Trial 序号<br>- 纵轴: 拟合度 FIT / $R^2$<br>- 所有 Trial 灰色散点, 历次 Best 绿线 | `trials: { trial_id: number, value: number, params: Record<string, any> }[]`<br>`best_curve: number[]` |
| **CHT-12** | 超参数重要性分析 | 水平百分比条形图 (`bar`) | - 横轴: 贡献度比例 (%)<br>- 参数名: `delay_u1`, `window_size` | `param_importances: Record<string, number>` |
| **CHT-13** | 数据版本血缘树 | 拓扑图 (`graph / tree`) | - 节点: 数据版本 ($V_0, V_1, ...$)<br>- 边: 调用的算法工具与参数<br>- 点击节点切换当前全局激活版本 | `nodes: { id: string, name: string, tool: string }[]`<br>`edges: { source: string, target: string }[]` |

---

## 3. 典型核心图表 JSON / Data Contract 示例

### 3.1 动态区间高亮 (CHT-05) 后端响应格式契约

```json
{
  "dataset_id": "S3_Simulation",
  "version_id": "V2_Segmented",
  "timestamps": ["2026-07-28T00:00:00Z", "..."],
  "series": {
    "y": [12.1, 12.3, 25.4, 28.1, 27.9],
    "u1": [1.0, 1.0, 5.0, 5.0, 5.0]
  },
  "segments": [
    {
      "segment_id": "seg_01",
      "start_index": 200,
      "end_index": 530,
      "start_time": "2026-07-28T00:03:20Z",
      "end_time": "2026-07-28T00:08:50Z",
      "snr_db": 18.5,
      "dynamic_score": 92.4,
      "recommendation": "strongly_recommended"
    }
  ]
}
```

### 3.2 ARX 实际 vs 预测对比 (CHT-09) 后端响应格式契约

```json
{
  "model_id": "arx_model_opt_v1",
  "metrics": {
    "train_r2": 0.942,
    "train_fit": 0.915,
    "val_r2": 0.895,
    "val_fit": 0.862,
    "test_r2": 0.881,
    "test_fit": 0.854
  },
  "plot_data": {
    "indices": [0, 1, 2, "...", 1000],
    "y_true": [10.2, 10.5, 14.8, "..."],
    "y_pred": [10.1, 10.6, 14.5, "..."],
    "residuals": [0.1, -0.1, 0.3, "..."],
    "splits": {
      "train_end": 600,
      "val_end": 800,
      "test_end": 1000
    }
  }
}
```
