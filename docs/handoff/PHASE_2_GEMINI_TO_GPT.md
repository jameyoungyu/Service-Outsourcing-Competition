# 阶段 2：Gemini → GPT 前端端到端联调完成与阶段 3 反向交接文档

**项目**：IndusOpt 工模智优  
**交接版本**：`HANDOFF-GEMINI-2.0`  
**交接状态**：阶段 2 (仿真数据生成与 ARX 基线) 前后端联调已 100% 通过验证。现进入阶段 3 (数据集管理与质量诊断) 开发交接。

---

## 1. 本阶段 (阶段 2) Gemini 已完成的工作

1. **真实 API 绑定与适配**：
   - 彻底移除 `SimulationView.vue` 与 `ARXModelingView.vue` 中所有 catch 随机 Mock 回退代码。
   - 成功将前端 `datasetStore` 与真实后端的 `dataset_id`、`version_id`、`input_columns` 动态响应绑定。
2. **端到端验证通过**：
   - 生成无噪声 S1 场景仿真数据集（`noise_level=0`, `num_samples=1500`, `seed=42`）。
   - 在 ARX 视图下求解 OLS 基线，真实测试集拟合度 FIT 达到 **99.9999%**，预测曲线与实测输出完全吻合。
3. **测试与构建校验**：
   - 前端 Vitest 单元测试 `3 passed`。
   - 前端 Production Bundle 构建成功 (耗时 `400ms`)。
   - 后端 17 个 Pytest 单元测试全部通过。

---

## 2. 阶段 3 (数据集管理与质量诊断) 给 GPT 的核心任务

在阶段 3 中，GPT 需要将当前数据资产 Hub 接口从阶段 1 Stub 升级为**基于 PostgreSQL 持久化与真实 Python 质量诊断引擎**的正式服务：

### 2.1 CSV 上传、解析与去重 (`POST /api/v1/datasets/upload`)
- 支持 `multipart/form-data` 真实上传 CSV。
- 实现扩展名校验 (`.csv`)、MIME 校验、SHA-256 文件哈希去重与大小限制 (100MB)。
- 实现智能编码识别 (`chardet`: UTF-8 / GBK / GB2312) 与分隔符自动推断 (逗号/分号/Tab)。

### 2.2 字段映射与 Schema 配置 (`POST /api/v1/datasets/{id}/config`)
- 解析时间戳列 (识别 ISO 8601, `YYYY-MM-DD HH:mm:ss`, Unix 时间戳等)。
- 配置列角色：`time` (单时间列), `input` (多输入), `output` (单目标), `ignored`。

### 2.3 真实数据质量诊断 (`GET /api/v1/datasets/{id}/profile`)
计算并返回真实的工业时序质量分析指标：
- 基础维度：行数、列数、时间跨度。
- 采样周期分析：估计期望周期 $T_s$，计算不规则采样偏离比例与采样间隔直方图数组 `interval_histogram`。
- 缺失与异常：各列缺失率 `missing_rates`、最大连续缺失长度、重复时间戳计数、冻结段计数 (连续不变的死值)。
- 统计特征：均值、标准差、极值 (min/max)、分位数 (25%, 50%, 75%)。
- 综合评分：计算 `quality_score` (0-100 分) 并生成智能诊断建议 `recommendations`。

### 2.4 数据持久化与版本血缘 (`GET /api/v1/datasets/{id}/versions`)
- SQLAlchemy 表结构落盘：`datasets`, `dataset_versions`, `dataset_columns`, `dataset_profiles`, `processing_runs`。
- 保障原始数据文件不可覆盖，处理产生新版本。

---

## 3. 验收条件

- `pytest` 涵盖 CSV 各种异常格式 (无时间列、非法时间、非 UTF-8、全空列) 的鲁棒性测试。
- 前端能够通过 `/api/v1/datasets` 读取真实上传的数据集，并在详情页展示真实的缺失率柱状图与诊断建议。
- 更新 `PHASE_STATUS.md` 并提交代码。
