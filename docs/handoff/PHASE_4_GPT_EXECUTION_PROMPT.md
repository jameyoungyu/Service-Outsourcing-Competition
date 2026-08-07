# 阶段 4：交给 GPT 的完整执行与开发指令 (GPT Execution Prompt for Phase 4)

> **使用方法**：将本文档的全部内容直接复制并发送给 **GPT**，指示其开始执行 IndusOpt 项目的**阶段 4（数据清洗与时间规整）**后端算法与服务开发。

---

```text
你现在担任 IndusOpt (工模智优) 项目的后端、算法与架构专家角色 (GPT)。

项目阶段：阶段 4 (数据清洗与时间规整)
当前状态：阶段 3 (基于 PostgreSQL 持久化的 CSV 上传、列 Schema 配置、数据资产管理与真实 Profile 质量诊断) 前后端联调已 100% 验收通过！

Gemini 已完成阶段 3 前端代码与真实后端 API 的全量绑定，并通过了 Vitest 与 Vite Production 编译校验。
相关交接文档：
- docs/handoff/PHASE_3_GEMINI_TO_GPT.md

================================================================================
【GPT 阶段 4 核心任务与清洗/规整算法边界】
================================================================================

在阶段 4 中，你需要实现**标准化的工业数据清洗工具库、统一算法工具接口与不可覆盖原始数据的数据版本派生体系**：

1. 实现统一算法工具框架与版本派生 (`backend/app/services/cleaning_service.py` & `backend/algorithms/cleaning/`)：
   - 建立统一算法工具抽象基类 `AlgorithmTool`:
     - 属性: `name: str`, `input_schema: type`, `output_schema: type`
     - 方法: `execute(context, parameters)`
   - 绝不覆盖原始数据文件！每次执行清洗都会派生出新的数据版本 ID (如 `V1_Cleaned`)，将处理后的数据保存至本地产物目录，并在 PostgreSQL `dataset_versions` 和 `operation_logs` 表中记录完整的操作日志 (包含输入版本、输出版本、算法名称、参数、异常点数、替代值与执行时间)。

2. 实现时间规整工具 (Time Alignment & Resampling Tools):
   - 时间轴排序与重复时间戳处理 (按首个保留或取均值)。
   - 固定周期重采样 (支持用户指定周期 T_s 秒，如 1.0s)。
   - 缺失值插值算法: 线性插值 (`linear`)、前向填充 (`ffill`)、后向填充 (`bfill`)。支持设置 `max_consecutive_missing` 限制，超限则保留缺失或标记告警。

3. 实现异常检测与清洗工具 (Outlier Detection & Cleaning Tools):
   - **Hampel Filter**: 中位数与 MAD (Median Absolute Deviation) 离群点检测 (滑窗 k, 阈值 t0)。
   - **IQR (四分位距)**: 剔除低于 `Q1 - 1.5*IQR` 或高于 `Q3 + 1.5*IQR` 的离群点。
   - **Z-Score**: 基于均值与标准差阈值的离群点检测。
   - **冻结值/死值检测**: 识别传感器长时间数值冻结不发生变化的死值区间。

4. 实现平滑滤波工具 (Smoothing Tools):
   - 移动平均 (Moving Average)。
   - Savitzky–Golay 滤波 (SavGol)。

5. 实现 API 路由对接 (`POST /api/v1/preprocessing/clean`):
   - 接受参数: `{ dataset_id, version_id, resample_period_s, interpolation_method, outlier_method, hampel_window, hampel_n_sigmas }`
   - 返回结构: `{ dataset_id, new_version_id, raw_series, cleaned_series, replaced_indices, total_cleaned_points }`
   - 替换阶段 1 的 stub 响应，返回真实清洗对比数据！

6. 编写清洗算法与版本派生单元测试 (`backend/tests/test_cleaning.py`):
   - 测试 S4 污染数据集上的 Hampel 滤波与异常点识别率。
   - 验证清洗后的新版本被正确记录入 `dataset_versions`。
   - 验证原始数据文件的只读不可变性。

================================================================================
【约束与协作规则】
================================================================================
1. 保持 API 路径和数据结构与阶段 1 `backend/openapi.json` 完全兼容。
2. 不修改 `frontend/` 目录。
3. 代码组织放在 `backend/algorithms/cleaning/` 和 `backend/app/services/` 中。
4. 完成后运行:
   - cd backend && .venv/bin/pytest
   - 更新 PHASE_STATUS.md 进入阶段 4 验收。

请现在开始编写阶段 4 数据清洗工具库、时间规整算法与版本派生代码！
```
