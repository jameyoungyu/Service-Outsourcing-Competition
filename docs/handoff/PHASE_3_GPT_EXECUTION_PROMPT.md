# 阶段 3：交给 GPT 的完整执行与开发指令 (GPT Execution Prompt for Phase 3)

> **使用方法**：将本文档的全部内容直接复制并发送给 **GPT**，指示其开始执行 IndusOpt 项目的**阶段 3（数据集管理与质量诊断）**后端开发。

---

```text
你现在担任 IndusOpt (工模智优) 项目的后端、算法与架构专家角色 (GPT)。

项目阶段：阶段 3 (数据集管理与质量诊断)
当前状态：阶段 2 (真实 S1-S5 仿真生成器与 MISO ARX 系统辨识基线，验证集 FIT > 99.9999%) 前后端联调已 100% 验收通过！

Gemini 已完成阶段 2 前端代码与真实后端 API 的全量绑定，并通过了 Vitest 与 Vite Production 编译校验。
相关交接文档：
- docs/handoff/PHASE_2_GEMINI_TO_GPT.md

================================================================================
【GPT 阶段 3 核心任务与数据库/诊断算法边界】
================================================================================

在阶段 3 中，你需要将阶段 1 的数据集相关 Schema Stubs 升级为**基于 PostgreSQL 数据库持久化与真实工业时序质量诊断引擎**的正式后端服务：

1. 实现 CSV 文件上传、健壮解析与去重服务 (`POST /api/v1/datasets/upload`)：
   - 支持 `multipart/form-data` 上传文件。
   - 文件校验：只允许 `.csv` 扩展名、文件大小限制 (如 100MB)。
   - 去重机制：计算文件 SHA-256 哈希，重复文件避免二次存储。
   - 编码与分隔符识别：使用 `chardet` 识别文件编码 (UTF-8, GBK, GB2312, ASCII)；自动推断分隔符 (逗号, 分号, Tab)。
   - 原始文件安全保存在 `data/uploads/{dataset_id}_raw.csv`，原始数据严禁覆盖！

2. 实现数据集列配置与 Schema 提取 (`POST /api/v1/datasets/{id}/config`)：
   - 自动解析前 100 行样本，推断列数据类型 (float, int, datetime, string)。
   - 支持配置列角色：
     - `time`: 唯一的单时间戳列 (识别 ISO8601, `YYYY-MM-DD HH:mm:ss`, Unix 时间戳)。
     - `input`: 过程输入变量 (支持一个或多个)。
     - `output`: 控制目标输出变量 (支持单输出 MISO)。
     - `ignored`: 忽略/辅助列。

3. 实现真实工业数据质量诊断引擎 (`GET /api/v1/datasets/{id}/profile`)：
   计算真实物理指标并返回 `DatasetProfile` 结构：
   - 样本规模：总行数 `total_rows`、总列数 `total_cols`、时间范围 [start_time, end_time]。
   - 采样周期分析：估计期望采样周期 T_s (秒)，计算采样间隔分布直方图数组 `interval_histogram` (供前端柱状图渲染)，计算不规则采样频次偏离比例。
   - 缺失与异常点检测：各列缺失率 `missing_rates`、最大连续缺失长度、重复时间戳计数、冻结段计数 (连续死值)。
   - 统计量计算：均值、标准差、极值 (min, max)、分位数 (25%, 50%, 75%)。
   - 综合评分与诊断建议：计算 `quality_score` (0-100 分)，并生成规则诊断建议 `recommendations: string[]`（如：“检测到 4.8% 缺失，推荐执行 1.0s 重采样”）。

4. 实现 PostgreSQL 数据库持久化与版本血缘：
   - 创建 Alembic 迁移脚本 `0002_datasets_and_profiles.py`。
   - 建立数据表：`datasets`, `dataset_versions`, `dataset_columns`, `dataset_profiles`, `processing_runs`。
   - 实现 `GET /api/v1/datasets` 列表查询、`GET /api/v1/datasets/{id}` 详情、`DELETE /api/v1/datasets/{id}` 级联删除及 `GET /api/v1/datasets/{id}/versions` 版本血缘 DAG 查询。

5. 编写健壮性异常单元测试 (`backend/tests/test_datasets.py`):
   - 测试无时间列 CSV、非法时间字符串、全空列、重复列名的拦截与 ErrorEnvelope (400) 返回。
   - 测试正常 CSV 上传与质量 Profile 指标计算的正确性。

================================================================================
【约束与协作规则】
================================================================================
1. 保持 API 路径和数据结构与阶段 1 `backend/openapi.json` 完全兼容。
2. 不修改 `frontend/` 目录。
3. 代码组织放在 `backend/app/services/` 和 `backend/algorithms/cleaning/` 中。
4. 完成后运行:
   - cd backend && .venv/bin/pytest
   - 更新 PHASE_STATUS.md 进入阶段 3 验收。

请现在开始编写阶段 3 数据库迁移、CSV 上传解析与数据质量诊断代码！
```
