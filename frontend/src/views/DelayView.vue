<template>
  <div class="delay-view">
    <div class="page-header">
      <h2>时滞分析与补偿</h2>
      <p class="subtitle">
        预白化互相关生成候选（消除输入自相关造成的伪峰），再由验证集自由仿真 FIT 决定最终时滞
      </p>
    </div>

    <div class="delay-layout">
      <div class="industrial-card">
        <div class="industrial-card-header">
          <div class="industrial-card-title">
            <el-icon><Timer /></el-icon> 时滞估计参数
          </div>
        </div>

        <el-form :inline="true" :model="form" label-width="110px">
          <el-form-item label="数据版本 ID">
            <el-input v-model="form.version_id" placeholder="version_id" style="width: 320px" />
          </el-form-item>
          <el-form-item label="输入变量">
            <el-input v-model="inputColumnsText" placeholder="u1,u2" style="width: 200px" />
          </el-form-item>
          <el-form-item label="输出变量">
            <el-input v-model="form.output_column" placeholder="y" style="width: 120px" />
          </el-form-item>
          <el-form-item label="最大滞后">
            <el-input-number v-model="form.max_lag" :min="1" :max="1000" :step="5" />
          </el-form-item>
          <el-form-item label="候选数 K">
            <el-input-number v-model="form.top_k" :min="1" :max="10" />
          </el-form-item>
          <el-form-item>
            <el-button type="primary" :loading="loading" icon="Search" @click="handleEstimate">
              估计多变量时滞
            </el-button>
          </el-form-item>
        </el-form>

        <el-alert v-if="errorMessage" type="error" :closable="false" show-icon class="alert-gap">
          <template #title>时滞估计失败：{{ errorMessage }}</template>
        </el-alert>
      </div>

      <template v-if="result">
        <div class="industrial-card">
          <div class="industrial-card-header">
            <div class="industrial-card-title">
              <el-icon><TrendCharts /></el-icon> 估计结论
            </div>
            <el-tag v-if="result.uncertain_columns.length" type="warning">
              {{ result.uncertain_columns.join(", ") }} 时滞不确定，建议人工确认
            </el-tag>
            <el-tag v-else type="success">候选区分度良好</el-tag>
          </div>

          <el-descriptions :column="3" border size="small">
            <el-descriptions-item label="验证集自由仿真 FIT">
              <span class="fit-val">{{ formatNumber(result.validation_fit) }}%</span>
            </el-descriptions-item>
            <el-descriptions-item label="精修轮次">
              {{ result.refinement_rounds }}
            </el-descriptions-item>
            <el-descriptions-item label="预白化 AR 阶次">
              {{ Object.entries(result.prewhitening_orders).map(([k, v]) => `${k}:${v}`).join(" / ") }}
            </el-descriptions-item>
          </el-descriptions>

          <el-table :data="delayRows" stripe style="width: 100%; margin-top: 16px">
            <el-table-column prop="column" label="输入变量" width="130" />
            <el-table-column label="最终时滞 nk" width="140">
              <template #default="{ row }">
                <span class="fit-val">{{ row.refined }}</span>
              </template>
            </el-table-column>
            <el-table-column label="互相关峰值位置" width="150">
              <template #default="{ row }">{{ row.peak }}</template>
            </el-table-column>
            <el-table-column label="峰值相关系数" width="150">
              <template #default="{ row }">{{ formatNumber(row.correlation) }}</template>
            </el-table-column>
            <el-table-column label="候选（lag / r）">
              <template #default="{ row }">
                <el-tag
                  v-for="peak in row.candidates"
                  :key="peak.lag"
                  size="small"
                  effect="plain"
                  :type="peak.lag === row.refined ? 'success' : 'info'"
                  class="candidate-tag"
                >
                  {{ peak.lag }} / {{ formatNumber(peak.correlation) }}
                </el-tag>
              </template>
            </el-table-column>
          </el-table>
        </div>

        <div class="industrial-card">
          <div class="industrial-card-header">
            <div class="industrial-card-title">
              <el-icon><DataLine /></el-icon> 预白化互相关函数
            </div>
          </div>
          <ChartContainer :options="chartOptions" height="360px" />
          <p class="chart-note">
            纵轴为预白化后的互相关系数，峰值位置即为该输入的纯滞后估计。虚线为
            95% 置信带；峰值落在带内说明该输入与输出的动态关联不显著。
          </p>
        </div>
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, reactive, ref } from "vue";
import { DataLine, Search, Timer, TrendCharts } from "@element-plus/icons-vue";
import ChartContainer from "../components/ChartContainer.vue";
import { calculateDelay } from "../api/preprocessing";
import type { DelayRequest, DelayResponse } from "../types/api";
import { ApiError } from "../api/client";
import { ElMessage } from "element-plus";

const PALETTE = ["#2A9D8F", "#F4A261", "#1E6091", "#E76F51", "#8E7DBE", "#457B9D"];

const loading = ref(false);
const result = ref<DelayResponse | null>(null);
const errorMessage = ref("");
const inputColumnsText = ref("u1,u2");

const form = reactive<DelayRequest>({
  version_id: "",
  input_columns: [],
  output_column: "y",
  max_lag: 30,
  top_k: 3,
});

const handleEstimate = async () => {
  errorMessage.value = "";
  if (!form.version_id) {
    errorMessage.value = "请先填写数据版本 ID。";
    return;
  }
  form.input_columns = inputColumnsText.value
    .split(",")
    .map((name) => name.trim())
    .filter(Boolean);
  if (!form.input_columns.length) {
    errorMessage.value = "请至少指定一个输入变量。";
    return;
  }

  loading.value = true;
  try {
    result.value = await calculateDelay(form);
    ElMessage.success("时滞估计完成");
  } catch (err) {
    // No mock fallback: fabricated delays would be worse than no answer.
    result.value = null;
    errorMessage.value = err instanceof ApiError ? err.message : String(err);
  } finally {
    loading.value = false;
  }
};

const delayRows = computed(() => {
  if (!result.value) return [];
  return form.input_columns.map((column) => {
    const candidates = result.value?.candidate_peaks[column] ?? [];
    return {
      column,
      refined: result.value?.best_delays[column] ?? 0,
      peak: candidates[0]?.lag ?? "—",
      correlation: candidates[0]?.correlation ?? null,
      candidates,
    };
  });
});

const chartOptions = computed(() => {
  if (!result.value) return {};
  const columns = Object.keys(result.value.correlations);
  const maxLength = Math.max(...columns.map((c) => result.value!.correlations[c].length), 1);
  return {
    tooltip: { trigger: "axis" },
    legend: { data: columns },
    grid: { left: "3%", right: "4%", bottom: "10%", containLabel: true },
    xAxis: {
      type: "category",
      name: "滞后步数",
      data: Array.from({ length: maxLength }, (_, i) => `${i}`),
    },
    yAxis: { type: "value", name: "预白化互相关 r" },
    series: columns.map((column, index) => ({
      name: column,
      type: "line",
      showSymbol: false,
      color: PALETTE[index % PALETTE.length],
      data: result.value!.correlations[column],
      markLine: {
        symbol: "none",
        silent: true,
        lineStyle: { type: "dashed", color: PALETTE[index % PALETTE.length] },
        data: [{ xAxis: String(result.value!.best_delays[column] ?? 0) }],
      },
    })),
  };
});

const formatNumber = (value: number | null | undefined) => {
  if (value === null || value === undefined || !Number.isFinite(value)) return "—";
  return value.toFixed(3);
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

.delay-layout {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.fit-val {
  font-weight: 600;
  color: var(--color-primary);
  font-family: var(--font-mono);
}

.alert-gap {
  margin-top: 12px;
}

.candidate-tag {
  margin-right: 4px;
}

.chart-note {
  margin-top: 10px;
  font-size: 12px;
  color: var(--text-secondary);
  line-height: 1.6;
}
</style>
