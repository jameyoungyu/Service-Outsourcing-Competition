<template>
  <div class="deliverables-view">
    <div class="page-header">
      <h2>报告与交付中心 (Deliverables & Export Hub)</h2>
      <p class="subtitle">预览包含完整证据链的工程分析报告并下载优选建模数据集 CSV</p>
    </div>

    <div class="deliverables-layout">
      <!-- Export Dataset Card -->
      <div class="industrial-card">
        <div class="industrial-card-header">
          <div class="industrial-card-title">
            <el-icon><Download /></el-icon> 优选数据集导出 (Export Datasets)
          </div>
        </div>

        <el-descriptions border :column="2">
          <el-descriptions-item label="当前导出版本">
            <span class="code-inline">V4_Optimal_Selected</span>
          </el-descriptions-item>
          <el-descriptions-item label="保留样本行数">1,850 行 (有效高动态段)</el-descriptions-item>
          <el-descriptions-item label="变量对齐">u1 (delay=5 步补偿), y (目标)</el-descriptions-item>
          <el-descriptions-item label="验证集 FIT">89.2% (最佳辨识模型)</el-descriptions-item>
        </el-descriptions>

        <div style="margin-top: 16px; display: flex; gap: 12px">
          <el-button type="primary" icon="Download" @click="handleDownloadCSV">
            一键下载优选数据集 CSV
          </el-button>
          <el-button type="success" icon="Printer" @click="handleDownloadReport">
            导出工程分析报告 (PDF)
          </el-button>
        </div>
      </div>

      <!-- Report Preview -->
      <div class="industrial-card">
        <div class="industrial-card-header">
          <div class="industrial-card-title">
            <el-icon><Document /></el-icon> 自动化工程建模报告预览
          </div>
          <el-tag type="info">系统生成于 {{ new Date().toLocaleDateString() }}</el-tag>
        </div>

        <div class="report-content">
          <h3>IndusOpt 流程工业系统辨识与数据智能优选工程报告</h3>
          <hr />
          <h4>1. 项目与数据概览</h4>
          <p>针对数据集 <code>S3_Simulation_Bench</code>，系统自动调度数据质量诊断工具，发现 14 处 Hampel 离群点，并完成了 1.0s 周期重采样规整。</p>

          <h4>2. 动态响应区间筛选</h4>
          <p>在无标签条件下提取到 2 个高信噪比 (SNR > 16dB) 动态段，消除了 55% 的无响应稳态干扰。</p>

          <h4>3. 时滞与共线性分析</h4>
          <p>多变量交叉相关计算表明过程变量 <code>u1</code> 存在 5 步响应滞后，变量 <code>u2</code> 存在严重共线性 (r=0.96) 并被成功剔除。</p>

          <h4>4. Optuna 闭环寻优结论</h4>
          <p>经过 30 次 Trial 闭环参数迭代，最优预处理与 ARX 模型 (na=2, nb=2) 在盲测验证集上的 FIT 拟合度从基线 42.1% 提升至 <strong>89.2%</strong>。</p>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { Download, Printer, Document } from "@element-plus/icons-vue";
import { ElMessage } from "element-plus";

const handleDownloadCSV = () => {
  ElMessage.success("已开始下载优选数据集 CSV 文件: IndusOpt_V4_Optimal.csv");
};

const handleDownloadReport = () => {
  ElMessage.success("已开始生成并下载工程分析报告 PDF");
};
</script>

<style scoped>
.page-header {
  margin-bottom: 20px;
}

.subtitle {
  font-size: 13px;
  color: var(--text-secondary);
  margin-top: 4px;
}

.deliverables-layout {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.report-content {
  line-height: 1.8;
  color: var(--text-primary);
}

.report-content h3 {
  margin-bottom: 12px;
  color: var(--color-primary);
}

.report-content h4 {
  margin: 16px 0 8px 0;
}
</style>
