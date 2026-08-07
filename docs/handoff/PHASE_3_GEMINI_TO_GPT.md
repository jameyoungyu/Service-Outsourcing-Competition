# 阶段 3：Gemini → GPT 前端端到端联调完成与阶段 4 反向交接文档

**项目**：IndusOpt 工模智优  
**交接版本**：`HANDOFF-GEMINI-3.0`  
**交接状态**：阶段 3 (数据集管理与质量诊断) 前后端联调与数据资产持久化已 100% 通过验证。现进入阶段 4 (数据清洗与时间规整) 后端开发交接。

---

## 1. 本阶段 (阶段 3) Gemini 已完成的工作

1. **真实数据资产 API 对接**：
   - 全面更新 `src/types/api.ts` 与 `src/api/datasets.ts`，支持真实的 `multipart/form-data` 文件上传、哈希去重判断、自定义列角色配置 (`POST /datasets/{id}/config`) 与版本 DAG 查询。
   - `DatasetsView.vue` 与 `DatasetDetailView.vue` 成功对接 PostgreSQL 数据库存储，支持实时上传 CSV、去重提示、交互式列 Role 映射对话框、删除及质量 Profile 呈现。
2. **诊断与统计量矩阵展示**：
   - 展现真实的质量分 `quality_score`、缺失率 `missing_rates` 柱状统计、变量级统计量矩阵 (均值/标准差/极值/Q50) 与诊断建议列表 `recommendations`。
3. **自动化测试与构建校验**：
   - 前端 Vitest 单元测试 `3 passed` 通过。
   - 前端 Production 打包编译 `built in 462ms` 通过。
   - 后端 23 个 Pytest 单元测试全部通过。

---

## 2. 阶段 4 (数据清洗与时间规整) 给 GPT 的核心任务

在阶段 4 中，GPT 需要实现**标准化的数据清洗工具库与不可覆盖原始数据的数据版本派生体系**：

### 2.1 统一算法工具接口与版本派生 (`POST /api/v1/preprocessing/clean`)
- 规范 `AlgorithmTool` 基类与上下文。
- 派生新数据版本 `V1_Cleaned`，记录修改审计日志 (`operation_logs`)，绝对严禁覆盖原始 CSV 文件！

### 2.2 时间规整与重采样工具
- 时间轴对齐与排序、重复时间戳去重。
- 固定周期重采样 (如 $T_s = 1.0s$)。
- 缺失值插值策略：线性插值 (`linear`)、前向填充 (`ffill`)、后向填充 (`bfill`)，支持设置最大连续插值步数上限。

### 2.3 离群点与异常检测工具
- **Hampel Filter**：中位数与 MAD (Median Absolute Deviation) 滤波 (滑窗 $k$, 阈值 $t_0$)。
- **IQR (四分位距)**：$[Q1 - 1.5 \cdot IQR, Q3 + 1.5 \cdot IQR]$ 异常值识别。
- **Z-Score** / **冻结段检测**。
- 返回替换掉的离群点索引数组 `replaced_indices` 与替换后时序 `cleaned_series`。

### 2.4 平滑滤波工具
- 移动平均 (Moving Average)、Savitzky–Golay 滤波。

---

## 3. 验收条件

- `pytest` 验证 Hampel 与 IQR 对污染数据 (S4 场景) 尖峰异常识别的准确率。
- 保证清洗前后行数合理、时间跨度正确，原始 CSV 不被改写。
- 更新 `PHASE_STATUS.md` 并落盘阶段 4 交接文档。
