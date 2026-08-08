<template>
  <div class="benchmark-view">
    <div class="page-header">
      <h2>一键自评测基准</h2>
      <p class="subtitle">
        系统用带真值的仿真基准检验自己的技术主张。下表每个数字都在本次请求中实时计算，
        不利的结果同样展示
      </p>
    </div>

    <div class="benchmark-layout">
      <div class="industrial-card">
        <div class="industrial-card-header">
          <div class="industrial-card-title">
            <el-icon><Odometer /></el-icon> 基准配置
          </div>
        </div>

        <el-form :inline="true" :model="form" label-width="100px">
          <el-form-item label="场景">
            <el-select v-model="form.scenarios" multiple style="width: 260px">
              <el-option v-for="name in SCENARIOS" :key="name" :label="name" :value="name" />
            </el-select>
          </el-form-item>
          <el-form-item label="样本数">
            <el-input-number v-model="form.n_samples" :min="500" :max="50000" :step="500" />
          </el-form-item>
          <el-form-item label="随机种子">
            <el-input-number v-model="form.seed" :min="0" :max="99999999" />
          </el-form-item>
          <el-form-item label="窗口长度">
            <el-input-number v-model="form.window_size" :min="10" :max="1000" :step="10" />
          </el-form-item>
          <el-form-item label="窗口预算">
            <el-input-number v-model="form.budget_windows" :min="1" :max="100" />
          </el-form-item>
          <el-form-item>
            <el-button type="primary" :loading="running" icon="VideoPlay" @click="handleRun">
              运行自评测基准
            </el-button>
          </el-form-item>
        </el-form>

        <el-alert v-if="errorMessage" type="error" :closable="false" show-icon class="alert-gap">
          <template #title>基准执行失败：{{ errorMessage }}</template>
        </el-alert>
      </div>

      <template v-if="result">
        <div class="industrial-card" v-for="experiment in result.experiments" :key="experiment.key">
          <div class="industrial-card-header">
            <div class="industrial-card-title">
              <el-icon><DataAnalysis /></el-icon> {{ experiment.title }}
            </div>
            <el-tag type="info">{{ experiment.rows.length }} 组测量</el-tag>
          </div>

          <p class="question">研究问题：{{ experiment.question }}</p>

          <el-table :data="experiment.rows" stripe style="width: 100%">
            <el-table-column prop="scenario" label="场景" width="90" />
            <el-table-column prop="strategy" label="策略 / 通道" width="150" />
            <el-table-column
              v-for="metric in metricsOf(experiment)"
              :key="metric"
              :label="metricLabel(metric)"
            >
              <template #default="{ row }">
                <span :class="{ 'fit-val': isHeadline(metric) }">
                  {{ fmt(row.metrics[metric]) }}
                </span>
              </template>
            </el-table-column>
          </el-table>

          <ul class="notes">
            <li v-for="note in experiment.notes" :key="note">{{ note }}</li>
          </ul>
        </div>

        <div class="industrial-card">
          <p class="footer-note">
            本次基准耗时 {{ result.duration_ms.toFixed(0) }} ms，场景
            {{ result.scenarios.join(" / ") }}，样本数 {{ result.n_samples }}，随机种子
            {{ result.seed }}。基准编号
            <span class="code-inline">{{ result.benchmark_id }}</span>
            已持久化，可被报告引用。
          </p>
        </div>
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref } from "vue";
import { DataAnalysis, Odometer, VideoPlay } from "@element-plus/icons-vue";
import apiClient, { ApiError } from "../api/client";
import { ElMessage } from "element-plus";

const SCENARIOS = ["S1", "S2", "S3", "S4", "S5", "S6"];

const METRIC_LABELS: Record<string, string> = {
  train_rows: "训练样本",
  coverage_ratio: "采样占比",
  parameter_error: "参数误差",
  free_run_fit: "自由仿真 FIT",
  condition_number: "条件数",
  one_step_fit: "一步预测 FIT",
  fit_gap: "FIT 差值",
  true_delay: "真实时滞",
  raw_peak: "朴素峰值",
  prewhitened_peak: "预白化峰值",
  raw_error: "朴素误差",
  prewhitened_error: "预白化误差",
  ar_order: "AR 阶次",
};

const HEADLINE = new Set(["free_run_fit", "parameter_error", "prewhitened_error"]);

interface BenchmarkRow {
  scenario: string;
  strategy: string;
  metrics: Record<string, number>;
}

interface BenchmarkExperiment {
  key: string;
  title: string;
  question: string;
  rows: BenchmarkRow[];
  notes: string[];
}

interface BenchmarkResponse {
  benchmark_id: string;
  scenarios: string[];
  n_samples: number;
  seed: number;
  experiments: BenchmarkExperiment[];
  duration_ms: number;
}

const running = ref(false);
const errorMessage = ref("");
const result = ref<BenchmarkResponse | null>(null);

const form = reactive({
  scenarios: ["S3", "S6"],
  n_samples: 4000,
  seed: 20260807,
  window_size: 60,
  budget_windows: 12,
});

const handleRun = async () => {
  errorMessage.value = "";
  running.value = true;
  try {
    result.value = await apiClient.post<BenchmarkResponse>("/benchmark/run", form);
    ElMessage.success(`自评测完成，耗时 ${result.value.duration_ms.toFixed(0)} ms`);
  } catch (err) {
    result.value = null;
    errorMessage.value = err instanceof ApiError ? err.message : String(err);
  } finally {
    running.value = false;
  }
};

const metricsOf = (experiment: BenchmarkExperiment) =>
  experiment.rows.length ? Object.keys(experiment.rows[0].metrics) : [];

const metricLabel = (metric: string) => METRIC_LABELS[metric] ?? metric;

const isHeadline = (metric: string) => HEADLINE.has(metric);

const fmt = (value: number | undefined) => {
  if (value === undefined || !Number.isFinite(value)) return value === undefined ? "—" : "∞";
  if (Number.isInteger(value)) return String(value);
  if (Math.abs(value) >= 10000) return value.toExponential(2);
  return value.toFixed(4);
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

.benchmark-layout {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.question {
  font-size: 13px;
  color: var(--text-secondary);
  margin: 0 0 12px;
}

.notes {
  margin: 12px 0 0;
  padding-left: 20px;
  font-size: 12px;
  color: var(--text-secondary);
  line-height: 1.8;
}

.fit-val {
  font-weight: 600;
  color: var(--color-primary);
  font-family: var(--font-mono);
}

.alert-gap {
  margin-top: 12px;
}

.footer-note {
  font-size: 12px;
  color: var(--text-secondary);
  margin: 0;
}
</style>
