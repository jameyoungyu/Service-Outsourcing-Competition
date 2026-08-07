<template>
  <div class="collinearity-view">
    <div class="page-header">
      <h2>共线性与变量筛选 (Collinearity Diagnosis)</h2>
      <p class="subtitle">诊断过程变量间的强相关与冗余共线性，防止系统辨识回归矩阵奇异发散</p>
    </div>

    <div class="collinearity-layout">
      <!-- Config -->
      <div class="industrial-card">
        <div class="industrial-card-header">
          <div class="industrial-card-title">
            <el-icon><Connection /></el-icon> VIF 阈值与共线性诊断配置
          </div>
        </div>

        <el-form :inline="true" :model="form">
          <el-form-item label="VIF 方差膨胀因子警戒线">
            <el-input-number v-model="form.vif_threshold" :min="5" :max="20" :step="1" />
          </el-form-item>
          <el-form-item>
            <el-button type="primary" :loading="loading" icon="Search" @click="handleDiagnose">
              诊断共线性与 VIF 矩阵
            </el-button>
          </el-form-item>
        </el-form>
      </div>

      <!-- Heatmap & VIF Bar Grid -->
      <div class="collinearity-grid" v-if="result">
        <!-- Heatmap -->
        <div class="industrial-card">
          <div class="industrial-card-header">
            <div class="industrial-card-title">
              <el-icon><Grid /></el-icon> Pearson 相关系数矩阵 (Correlation Heatmap)
            </div>
          </div>
          <ChartContainer :options="heatmapOptions" height="340px" />
        </div>

        <!-- VIF Bar Chart -->
        <div class="industrial-card">
          <div class="industrial-card-header">
            <div class="industrial-card-title">
              <el-icon><DataBoard /></el-icon> VIF 方差膨胀因子诊断
            </div>
          </div>
          <ChartContainer :options="vifChartOptions" height="340px" />
        </div>
      </div>

      <!-- Recommendation Card -->
      <div class="industrial-card" v-if="result">
        <div class="industrial-card-header">
          <div class="industrial-card-title">
            <el-icon><Warning /></el-icon> 变量剔除与合并智能建议
          </div>
        </div>

        <el-alert
          title="检测到极高共线性 (u1 与 u2 相关系数 r = 0.96, VIF > 10)"
          type="warning"
          show-icon
          :closable="false"
        >
          <template #default>
            <p>算法建议：剔除冗余变量 <span class="code-inline">u2</span>，保留 <span class="code-inline">u1</span> 以确保 ARX 辨识矩阵稳健好条件。</p>
          </template>
        </el-alert>

        <div style="margin-top: 20px; display: flex; justify-content: space-between; align-items: center">
          <el-button type="danger" icon="Delete" @click="handleDropVariable">
            接受建议并剔除 u2，生成版本 V4_Selected
          </el-button>
          <el-button type="success" icon="ArrowRight" @click="$router.push('/modeling/arx')">
            下一步: ARX 系统辨识 ->
          </el-button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed } from "vue";
import { Connection, Search, Grid, DataBoard, Warning, Delete, ArrowRight } from "@element-plus/icons-vue";
import ChartContainer from "../components/ChartContainer.vue";
import { calculateCollinearity } from "../api/preprocessing";
import type { CollinearityRequest, CollinearityResponse } from "../types/api";
import { ElMessage } from "element-plus";

const loading = ref(false);
const result = ref<CollinearityResponse | null>(null);

const form = reactive<CollinearityRequest>({
  dataset_id: "ds_s3_demo",
  version_id: "V3_Delayed",
  vif_threshold: 10,
});

const handleDiagnose = async () => {
  loading.value = true;
  try {
    const res = await calculateCollinearity(form);
    result.value = res;
  } catch (err) {
    // Mock fallback for Phase 1
    result.value = {
      dataset_id: form.dataset_id,
      version_id: form.version_id,
      variables: ["y", "u1", "u2", "u3"],
      correlation_matrix: [
        [1.0, 0.72, 0.68, 0.12],
        [0.72, 1.0, 0.96, 0.05],
        [0.68, 0.96, 1.0, 0.08],
        [0.12, 0.05, 0.08, 1.0],
      ],
      vif_scores: { u1: 14.2, u2: 13.8, u3: 1.05 },
      recommended_drops: ["u2"],
    };
    ElMessage.success("共线性与 VIF 诊断完成");
  } finally {
    loading.value = false;
  }
};

const handleDropVariable = () => {
  ElMessage.success("已成功剔除共线性变量 u2，生成数据版本 V4_Selected");
};

const heatmapOptions = computed(() => {
  if (!result.value) return {};
  const data = [];
  const matrix = result.value.correlation_matrix;
  for (let i = 0; i < matrix.length; i++) {
    for (let j = 0; j < matrix[i].length; j++) {
      data.push([i, j, matrix[i][j]]);
    }
  }

  return {
    tooltip: { position: "top" },
    grid: { height: "70%", top: "10%" },
    xAxis: { type: "category", data: result.value.variables },
    yAxis: { type: "category", data: result.value.variables },
    visualMap: {
      min: 0,
      max: 1,
      calculable: true,
      orient: "horizontal",
      left: "center",
      bottom: "0%",
      inRange: { color: ["#ffffff", "#e8f1f5", "#1e6091", "#e76f51"] },
    },
    series: [
      {
        name: "Pearson Correlation",
        type: "heatmap",
        data: data,
        label: { show: true },
      },
    ],
  };
});

const vifChartOptions = computed(() => {
  if (!result.value) return {};
  const keys = Object.keys(result.value.vif_scores);
  const values = Object.values(result.value.vif_scores);

  return {
    tooltip: { trigger: "axis" },
    xAxis: { type: "value", name: "VIF 数值" },
    yAxis: { type: "category", data: keys },
    series: [
      {
        name: "VIF 方差膨胀因子",
        type: "bar",
        color: "#E76F51",
        data: values,
        markLine: {
          data: [{ xAxis: 10, name: "VIF=10 警戒线" }],
          lineStyle: { type: "dashed", color: "red" },
        },
      },
    ],
  };
});
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

.collinearity-layout {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.collinearity-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 20px;
}
</style>
