<template>
  <div class="dashboard-view">
    <div class="page-header">
      <h2>工作台概览 (Dashboard Overview)</h2>
      <p class="subtitle">面向流程工业系统辨识的自主建模数据工程师 Agent 系统</p>
    </div>

    <!-- Stat Cards -->
    <div class="stat-cards">
      <div class="industrial-card stat-card">
        <div class="stat-title">活跃数据集</div>
        <div class="stat-val">{{ datasetStore.datasetsList.length || 5 }} <span class="unit">个</span></div>
        <div class="stat-sub">最新数据: S4_Noise_Data</div>
      </div>
      <div class="industrial-card stat-card">
        <div class="stat-title">最高辨识 FIT 拟合度</div>
        <div class="stat-val highlight">89.2%</div>
        <div class="stat-sub">数据集: S3_Simulation_Opt</div>
      </div>
      <div class="industrial-card stat-card">
        <div class="stat-title">已执行闭环 Trial</div>
        <div class="stat-val">128 <span class="unit">次</span></div>
        <div class="stat-sub">收敛率: 94.2%</div>
      </div>
      <div class="industrial-card stat-card">
        <div class="stat-title">Agent 调度状态</div>
        <div class="stat-val success-text">Standby</div>
        <div class="stat-sub">白名单工具 12 个就绪</div>
      </div>
    </div>

    <!-- Quick Actions -->
    <div class="industrial-card">
      <div class="industrial-card-header">
        <div class="industrial-card-title">
          <el-icon><Lightning /></el-icon> 快捷行动入口
        </div>
      </div>
      <div class="action-buttons">
        <el-button type="primary" size="large" icon="Plus" @click="$router.push('/simulation')">
          新建 S1-S5 仿真数据集
        </el-button>
        <el-button type="success" size="large" icon="Upload" @click="$router.push('/datasets')">
          上传工业 CSV 数据集
        </el-button>
        <el-button type="warning" size="large" icon="ChatDotSquare" @click="$router.push('/copilot')">
          启动 Agent 智能闭环建模
        </el-button>
      </div>
    </div>

    <!-- Leaderboard Table -->
    <div class="industrial-card">
      <div class="industrial-card-header">
        <div class="industrial-card-title">
          <el-icon><Trophy /></el-icon> 预处理与辨识效果 Leaderboard
        </div>
        <el-tag type="info">按验证集 FIT 排名</el-tag>
      </div>
      <el-table :data="leaderboardData" stripe style="width: 100%">
        <el-table-column prop="name" label="数据集名称" width="180" />
        <el-table-column prop="baselineFit" label="基线 FIT" width="120" />
        <el-table-column prop="optimizedFit" label="优化后 FIT" width="130">
          <template #default="{ row }">
            <span class="fit-val">{{ row.optimizedFit }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="improvement" label="提升幅度" width="120">
          <template #default="{ row }">
            <span class="improvement-text">+{{ row.improvement }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="keyAction" label="主要优化贡献步骤" />
        <el-table-column label="操作" width="120">
          <template #default="{ row }">
            <el-button type="primary" text size="small" @click="$router.push(`/datasets/${row.id}`)">查看细节</el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from "vue";
import { Lightning, Trophy } from "@element-plus/icons-vue";
import { useDatasetStore } from "../stores/datasetStore";

const datasetStore = useDatasetStore();

const leaderboardData = ref([
  { id: "ds_s3", name: "S3_Simulation", baselineFit: "42.1%", optimizedFit: "89.2%", improvement: "47.1%", keyAction: "动态截取 + 时滞补偿 (delay=5)" },
  { id: "ds_s4", name: "S4_Noise_Data", baselineFit: "31.0%", optimizedFit: "78.5%", improvement: "47.5%", keyAction: "Hampel 异常清洗 + Ridge 估计" },
  { id: "ds_s2", name: "S2_Multi_Input", baselineFit: "55.4%", optimizedFit: "84.1%", improvement: "28.7%", keyAction: "共线性剔除 U2 + 滞后步数对齐" },
]);
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

.stat-cards {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
}

.stat-card {
  margin-bottom: 20px;
}

.stat-title {
  font-size: 13px;
  color: var(--text-secondary);
}

.stat-val {
  font-size: 28px;
  font-weight: 700;
  color: var(--text-primary);
  margin: 6px 0;
  font-family: var(--font-mono);
}

.stat-val.highlight {
  color: var(--color-primary);
}

.stat-val.success-text {
  color: var(--color-success);
}

.unit {
  font-size: 14px;
  font-weight: 400;
  color: var(--text-secondary);
}

.stat-sub {
  font-size: 12px;
  color: var(--text-muted);
}

.action-buttons {
  display: flex;
  gap: 16px;
}

.fit-val {
  font-weight: 600;
  color: var(--color-primary);
  font-family: var(--font-mono);
}

.improvement-text {
  color: var(--color-success);
  font-weight: 600;
  font-family: var(--font-mono);
}
</style>
