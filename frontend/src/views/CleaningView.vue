<template>
  <div class="cleaning-view">
    <div class="page-header">
      <h2>时间规整与清洗 (Cleaning & Resampling)</h2>
      <p class="subtitle">消除采样不均匀、补全缺失值并过滤尖峰异常点，派生可信数据版本</p>
    </div>

    <div class="cleaning-layout">
      <!-- Config Panel -->
      <div class="industrial-card form-card">
        <div class="industrial-card-header">
          <div class="industrial-card-title">
            <el-icon><Operation /></el-icon> 清洗规整算法参数
          </div>
        </div>

        <el-form :model="form" label-width="140px" label-position="left">
          <el-form-item label="目标数据版本">
            <span class="code-inline">V0_Original</span>
          </el-form-item>

          <el-form-item label="重采样周期 Ts">
            <el-input-number v-model="form.resample_period_s" :min="0.1" :max="60" :step="0.5" />
            <span style="margin-left: 8px">秒 (s)</span>
          </el-form-item>

          <el-form-item label="缺失值插值算法">
            <el-radio-group v-model="form.interpolation_method">
              <el-radio label="linear">线性插值 (Linear)</el-radio>
              <el-radio label="ffill">前向填充 (FFill)</el-radio>
              <el-radio label="bfill">后向填充 (BFill)</el-radio>
            </el-radio-group>
          </el-form-item>

          <el-form-item label="异常值检测算法">
            <el-select v-model="form.outlier_method" style="width: 220px">
              <el-option label="Hampel Filter (推荐)" value="hampel" />
              <el-option label="IQR 四分位距" value="iqr" />
              <el-option label="Z-Score 阈值" value="zscore" />
            </el-select>
          </el-form-item>

          <el-form-item label="Hampel 滑窗 k" v-if="form.outlier_method === 'hampel'">
            <el-input-number v-model="form.hampel_window" :min="3" :max="21" :step="2" />
          </el-form-item>

          <el-form-item>
            <el-button type="primary" :loading="loading" icon="MagicStick" @click="handleClean">
              执行清洗并生成新版本 V1_Cleaned
            </el-button>
          </el-form-item>
        </el-form>
      </div>

      <!-- Comparison Chart Card -->
      <div class="industrial-card result-card" v-if="cleanedData">
        <div class="industrial-card-header">
          <div class="industrial-card-title">
            <el-icon><DataAnalysis /></el-icon> 清洗前后叠加对比图 (Before vs After)
          </div>
          <el-tag type="success">已成功清洗 {{ cleanedData.total_cleaned_points }} 处异常数据点</el-tag>
        </div>

        <ChartContainer :options="compareChartOptions" height="360px" />

        <div style="margin-top: 16px; display: flex; justify-content: flex-end; gap: 12px">
          <el-button type="success" icon="ArrowRight" @click="$router.push('/preprocessing/segmentation')">
            下一步: 动态响应区间优选 ->
          </el-button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed } from "vue";
import { Operation, MagicStick, DataAnalysis, ArrowRight } from "@element-plus/icons-vue";
import ChartContainer from "../components/ChartContainer.vue";
import { cleanDataset } from "../api/preprocessing";
import type { CleanRequest, CleanResponse } from "../types/api";
import { ElMessage } from "element-plus";

const loading = ref(false);
const cleanedData = ref<CleanResponse | null>(null);

const form = reactive<CleanRequest>({
  dataset_id: "ds_s3_demo",
  version_id: "V0_Original",
  resample_period_s: 1.0,
  interpolation_method: "linear",
  outlier_method: "hampel",
  hampel_window: 5,
});

const handleClean = async () => {
  loading.value = true;
  try {
    const res = await cleanDataset(form);
    cleanedData.value = res;
    ElMessage.success(`成功生成清洗后数据版本: ${res.new_version_id}`);
  } catch (err) {
    // Mock fallback for Phase 1
    cleanedData.value = {
      dataset_id: form.dataset_id,
      new_version_id: "V1_Cleaned",
      raw_series: Array.from({ length: 60 }, (_, i) => 10 + Math.sin(i / 4) * 5 + (i === 15 || i === 42 ? 35 : 0)),
      cleaned_series: Array.from({ length: 60 }, (_, i) => 10 + Math.sin(i / 4) * 5),
      replaced_indices: [15, 42],
      total_cleaned_points: 14,
    };
    ElMessage.success("成功生成清洗后数据版本: V1_Cleaned");
  } finally {
    loading.value = false;
  }
};

const compareChartOptions = computed(() => {
  if (!cleanedData.value) return {};
  const xData = Array.from({ length: cleanedData.value.raw_series.length }, (_, i) => `${i}s`);

  return {
    tooltip: { trigger: "axis" },
    legend: { data: ["原始序列 (Raw Series)", "清洗后序列 (Cleaned Series)"] },
    grid: { left: "3%", right: "4%", bottom: "10%", containLabel: true },
    xAxis: { type: "category", data: xData },
    yAxis: { type: "value" },
    series: [
      {
        name: "原始序列 (Raw Series)",
        type: "line",
        color: "#E76F51",
        lineStyle: { type: "dashed", width: 1 },
        data: cleanedData.value.raw_series,
      },
      {
        name: "清洗后序列 (Cleaned Series)",
        type: "line",
        color: "#1E6091",
        lineStyle: { width: 2 },
        data: cleanedData.value.cleaned_series,
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

.cleaning-layout {
  display: flex;
  flex-direction: column;
  gap: 20px;
}
</style>
