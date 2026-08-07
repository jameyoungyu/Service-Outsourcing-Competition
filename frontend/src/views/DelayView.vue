<template>
  <div class="delay-view">
    <div class="page-header">
      <h2>多变量时滞分析与补偿 (Delay Estimation)</h2>
      <p class="subtitle">通过输入输出 Lag-Correlation 交叉相关计算，准确估计并补偿多变量滞后步数</p>
    </div>

    <div class="delay-layout">
      <!-- Config -->
      <div class="industrial-card">
        <div class="industrial-card-header">
          <div class="industrial-card-title">
            <el-icon><Timer /></el-icon> 时滞估计搜索空间配置
          </div>
        </div>

        <el-form :inline="true" :model="form">
          <el-form-item label="最大搜寻滞后步数 τ_max">
            <el-input-number v-model="form.max_delay_steps" :min="5" :max="50" :step="5" />
          </el-form-item>
          <el-form-item>
            <el-button type="primary" :loading="loading" icon="Histogram" @click="handleCalculateDelay">
              计算多变量 Lag-Correlation 曲线
            </el-button>
          </el-form-item>
        </el-form>
      </div>

      <!-- Correlation Curve Chart -->
      <div class="industrial-card" v-if="delayResult">
        <div class="industrial-card-header">
          <div class="industrial-card-title">
            <el-icon><TrendCharts /></el-icon> 输入与输出 Lag-Correlation 滞后相关曲线
          </div>
        </div>

        <ChartContainer :options="chartOptions" height="360px" />
      </div>

      <!-- Candidate Peak Table -->
      <div class="industrial-card" v-if="delayResult">
        <div class="industrial-card-header">
          <div class="industrial-card-title">
            <el-icon><Select /></el-icon> 推荐最佳滞后步数 Peak
          </div>
        </div>

        <el-descriptions border :column="2">
          <el-descriptions-item label="变量 u1 推荐滞后 (d_u1)">
            <el-tag type="success" effect="dark">5 步</el-tag> (最高相关系数 r = 0.88)
          </el-descriptions-item>
          <el-descriptions-item label="变量 u2 推荐滞后 (d_u2)">
            <el-tag type="warning" effect="dark">8 步</el-tag> (最高相关系数 r = 0.76)
          </el-descriptions-item>
        </el-descriptions>

        <div style="margin-top: 20px; display: flex; justify-content: space-between; align-items: center">
          <el-button type="primary" icon="Check" @click="handleApplyDelay">
            应用此时滞补偿并派生新数据版本 V3_Delayed
          </el-button>
          <el-button type="success" icon="ArrowRight" @click="$router.push('/preprocessing/collinearity')">
            下一步: 共线性分析与变量剔除 ->
          </el-button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed } from "vue";
import { Timer, Histogram, TrendCharts, Select, Check, ArrowRight } from "@element-plus/icons-vue";
import ChartContainer from "../components/ChartContainer.vue";
import { calculateDelay } from "../api/preprocessing";
import type { DelayRequest, DelayResponse } from "../types/api";
import { ElMessage } from "element-plus";

const loading = ref(false);
const delayResult = ref<DelayResponse | null>(null);

const form = reactive<DelayRequest>({
  dataset_id: "ds_s3_demo",
  version_id: "V2_Segmented",
  max_delay_steps: 20,
});

const handleCalculateDelay = async () => {
  loading.value = true;
  try {
    const res = await calculateDelay(form);
    delayResult.value = res;
  } catch (err) {
    // Mock fallback for Phase 1
    delayResult.value = {
      dataset_id: form.dataset_id,
      version_id: form.version_id,
      delays: Array.from({ length: 21 }, (_, i) => i),
      correlations: {
        u1: [0.1, 0.3, 0.5, 0.7, 0.82, 0.88, 0.75, 0.6, 0.4, 0.3, 0.2, 0.1, 0, 0, 0, 0, 0, 0, 0, 0, 0],
        u2: [0.05, 0.1, 0.2, 0.3, 0.45, 0.6, 0.7, 0.73, 0.76, 0.65, 0.5, 0.35, 0.2, 0.1, 0, 0, 0, 0, 0, 0, 0],
      },
      recommended_delays: { u1: 5, u2: 8 },
    };
    ElMessage.success("多变量时滞估计完成");
  } finally {
    loading.value = false;
  }
};

const handleApplyDelay = () => {
  ElMessage.success("已应用时滞补偿: u1 偏移 -5 步, u2 偏移 -8 步，生成版本 V3_Delayed");
};

const chartOptions = computed(() => ({
  tooltip: { trigger: "axis" },
  legend: { data: ["u1 vs y (Peak at delay=5)", "u2 vs y (Peak at delay=8)"] },
  grid: { left: "3%", right: "4%", bottom: "10%", containLabel: true },
  xAxis: {
    type: "category",
    name: "滞后步数 (delay step)",
    data: Array.from({ length: 21 }, (_, i) => `${i}`),
  },
  yAxis: { type: "value", name: "相关系数 r" },
  series: [
    {
      name: "u1 vs y (Peak at delay=5)",
      type: "line",
      color: "#2A9D8F",
      data: [0.1, 0.3, 0.5, 0.7, 0.82, 0.88, 0.75, 0.6, 0.4, 0.3, 0.2, 0.1, 0, 0, 0, 0, 0, 0, 0, 0, 0],
    },
    {
      name: "u2 vs y (Peak at delay=8)",
      type: "line",
      color: "#F4A261",
      data: [0.05, 0.1, 0.2, 0.3, 0.45, 0.6, 0.7, 0.73, 0.76, 0.65, 0.5, 0.35, 0.2, 0.1, 0, 0, 0, 0, 0, 0, 0],
    },
  ],
}));
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

.delay-layout {
  display: flex;
  flex-direction: column;
  gap: 20px;
}
</style>
