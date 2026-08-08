<template>
  <div class="segmentation-view">
    <div class="page-header">
      <h2>质量约束 D-最优动态区间优选</h2>
      <p class="subtitle">
        先做质量门控（缺失 / 异常 / 稳态 / 信噪比），再在合格窗口上按 Fisher 信息增益贪心优选
      </p>
    </div>

    <div class="segmentation-layout">
      <div class="industrial-card">
        <div class="industrial-card-header">
          <div class="industrial-card-title">
            <el-icon><Crop /></el-icon> 数据版本与优选参数
          </div>
        </div>

        <el-form :inline="true" :model="form" label-width="110px">
          <el-form-item label="数据版本 ID">
            <el-input v-model="form.version_id" placeholder="version_id" style="width: 320px" />
          </el-form-item>
          <el-form-item label="输入变量">
            <el-input
              v-model="inputColumnsText"
              placeholder="u1,u2,u3"
              style="width: 200px"
            />
          </el-form-item>
          <el-form-item label="输出变量">
            <el-input v-model="form.output_column" placeholder="y" style="width: 120px" />
          </el-form-item>
          <el-form-item label="窗口长度">
            <el-input-number v-model="form.window_size" :min="5" :max="2000" :step="10" />
          </el-form-item>
          <el-form-item label="保留区间数">
            <el-input-number v-model="form.max_segments" :min="1" :max="100" />
          </el-form-item>
          <el-form-item label="最低 SNR">
            <el-input-number v-model="form.min_snr_db" :min="-20" :max="60" :step="1" />
            <span style="margin-left: 6px">dB</span>
          </el-form-item>
          <el-form-item label="最大缺失率">
            <el-input-number
              v-model="form.max_missing_ratio"
              :min="0"
              :max="1"
              :step="0.05"
              :precision="2"
            />
          </el-form-item>
          <el-form-item label="最大异常率">
            <el-input-number
              v-model="form.max_anomaly_ratio"
              :min="0"
              :max="1"
              :step="0.05"
              :precision="2"
            />
          </el-form-item>
          <el-form-item>
            <el-button type="primary" :loading="loading" icon="Search" @click="handleSegment">
              执行门控与信息增益优选
            </el-button>
          </el-form-item>
        </el-form>

        <el-alert v-if="errorMessage" type="error" :closable="false" show-icon class="alert-gap">
          <template #title>优选失败：{{ errorMessage }}</template>
        </el-alert>
      </div>

      <template v-if="result && result.selection">
        <div class="industrial-card">
          <div class="industrial-card-header">
            <div class="industrial-card-title">
              <el-icon><TrendCharts /></el-icon> 优选结论
            </div>
            <el-tag :type="result.selection.excitation_satisfied ? 'success' : 'danger'">
              {{ result.selection.excitation_satisfied ? "持续激励条件满足" : "持续激励不足" }}
            </el-tag>
          </div>

          <el-descriptions :column="4" border size="small">
            <el-descriptions-item label="候选窗口">
              {{ result.selection.candidate_count }}
            </el-descriptions-item>
            <el-descriptions-item label="通过门控">
              {{ result.selection.gated_count }}
            </el-descriptions-item>
            <el-descriptions-item label="最终选中">
              {{ result.selection.selected_count }}
            </el-descriptions-item>
            <el-descriptions-item label="采样占比">
              {{ percent(result.selection.coverage_ratio) }}
            </el-descriptions-item>
            <el-descriptions-item label="信息保留率">
              {{
                result.selection.information_retention === null
                  ? "—"
                  : percent(result.selection.information_retention)
              }}
            </el-descriptions-item>
            <el-descriptions-item label="设计矩阵条件数">
              {{ formatNumber(result.selection.condition_number) }}
            </el-descriptions-item>
            <el-descriptions-item label="CELF 求值加速">
              {{ result.selection.lazy_speedup.toFixed(2) }}×
            </el-descriptions-item>
            <el-descriptions-item label="停止原因">
              <span class="code-inline">{{ result.selection.stopped_reason }}</span>
            </el-descriptions-item>
          </el-descriptions>

          <el-alert
            v-if="result.selection.budget_advisory"
            type="warning"
            :closable="false"
            show-icon
            class="advisory"
          >
            <template #title>{{ result.selection.budget_advisory }}</template>
          </el-alert>

          <div v-if="rejectionRows.length" class="rejection-block">
            <span class="rejection-title">门控剔除统计：</span>
            <el-tag
              v-for="row in rejectionRows"
              :key="row.reason"
              type="info"
              effect="plain"
              class="rejection-tag"
            >
              {{ reasonLabel(row.reason) }} × {{ row.count }}
            </el-tag>
          </div>

          <div v-if="excitationRows.length" class="rejection-block">
            <span class="rejection-title">持续激励阶次（实际 / 所需）：</span>
            <el-tag
              v-for="row in excitationRows"
              :key="row.column"
              :type="row.actual >= row.required ? 'success' : 'danger'"
              effect="plain"
              class="rejection-tag"
            >
              {{ row.column }}: {{ row.actual }} / {{ row.required }}
            </el-tag>
          </div>
        </div>

        <div class="industrial-card">
          <div class="industrial-card-header">
            <div class="industrial-card-title">
              <el-icon><DataLine /></el-icon> 优选区间高亮叠加图
            </div>
            <el-tag type="warning">选中 {{ result.segments.length }} 个高信息量区间</el-tag>
          </div>
          <ChartContainer :options="chartOptions" height="380px" />
        </div>

        <div class="industrial-card">
          <div class="industrial-card-header">
            <div class="industrial-card-title">
              <el-icon><List /></el-icon> 选中区间与信息增益
            </div>
          </div>

          <el-table :data="result.segments" stripe style="width: 100%">
            <el-table-column prop="rank" label="选中次序" width="90" />
            <el-table-column prop="segment_id" label="区间 ID" width="110" />
            <el-table-column label="样本范围" width="180">
              <template #default="{ row }">
                <span class="code-inline">[{{ row.start_index }} - {{ row.end_index }}]</span>
              </template>
            </el-table-column>
            <el-table-column label="信息增益" width="140">
              <template #default="{ row }">
                <span class="fit-val">{{ formatNumber(row.information_gain_bits) }} bit</span>
              </template>
            </el-table-column>
            <el-table-column label="信噪比" width="120">
              <template #default="{ row }">{{ formatNumber(row.snr_db) }} dB</template>
            </el-table-column>
            <el-table-column label="缺失率" width="100">
              <template #default="{ row }">{{ percent(row.missing_ratio) }}</template>
            </el-table-column>
            <el-table-column label="异常率" width="100">
              <template #default="{ row }">{{ percent(row.anomaly_ratio) }}</template>
            </el-table-column>
            <el-table-column prop="recommendation" label="推荐意见" />
          </el-table>

          <div class="footer-actions">
            <el-button
              type="success"
              icon="ArrowRight"
              @click="$router.push('/preprocessing/delay')"
            >
              下一步: 时滞分析与补偿 →
            </el-button>
          </div>
        </div>

        <div class="industrial-card">
          <div class="industrial-card-header">
            <div class="industrial-card-title">
              <el-icon><Filter /></el-icon> 质量门控明细（含被剔除窗口）
            </div>
          </div>
          <el-table :data="result.gated_windows" stripe height="320" style="width: 100%">
            <el-table-column prop="window_index" label="窗口" width="80" />
            <el-table-column label="样本范围" width="170">
              <template #default="{ row }">
                <span class="code-inline">[{{ row.start_index }} - {{ row.end_index }}]</span>
              </template>
            </el-table-column>
            <el-table-column label="结果" width="100">
              <template #default="{ row }">
                <el-tag :type="row.accepted ? 'success' : 'info'" size="small">
                  {{ row.accepted ? "通过" : "剔除" }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="缺失率" width="100">
              <template #default="{ row }">{{ percent(row.missing_ratio) }}</template>
            </el-table-column>
            <el-table-column label="异常率" width="100">
              <template #default="{ row }">{{ percent(row.anomaly_ratio) }}</template>
            </el-table-column>
            <el-table-column label="SNR" width="110">
              <template #default="{ row }">{{ formatNumber(row.snr_db) }} dB</template>
            </el-table-column>
            <el-table-column label="剔除原因">
              <template #default="{ row }">
                <span v-if="!row.rejection_reasons.length">—</span>
                <el-tag
                  v-for="reason in row.rejection_reasons"
                  :key="reason"
                  size="small"
                  type="warning"
                  effect="plain"
                  class="rejection-tag"
                >
                  {{ reasonLabel(reason) }}
                </el-tag>
              </template>
            </el-table-column>
          </el-table>
        </div>
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, reactive, ref } from "vue";
import { ArrowRight, Crop, DataLine, Filter, List, Search, TrendCharts } from "@element-plus/icons-vue";
import ChartContainer from "../components/ChartContainer.vue";
import { segmentDataset } from "../api/preprocessing";
import type { SegmentRequest, SegmentResponse } from "../types/api";
import { ApiError } from "../api/client";
import { ElMessage } from "element-plus";

const REASON_LABELS: Record<string, string> = {
  missing_ratio_exceeded: "缺失率超限",
  anomaly_ratio_exceeded: "异常率超限",
  snr_below_threshold: "信噪比不足",
  steady_state_segment: "稳态段",
  no_input_excitation: "输入无激励",
};

const loading = ref(false);
const result = ref<SegmentResponse | null>(null);
const errorMessage = ref("");
const inputColumnsText = ref("u1,u2,u3");

const form = reactive<SegmentRequest>({
  version_id: "",
  input_columns: [],
  output_column: "y",
  window_size: 60,
  max_segments: 8,
  min_snr_db: 0,
  max_missing_ratio: 0.2,
  max_anomaly_ratio: 0.1,
});

const handleSegment = async () => {
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
    result.value = await segmentDataset(form);
    ElMessage.success(
      `优选完成：${result.value.selection?.selected_count ?? 0} 个区间，采样占比 ${percent(
        result.value.selection?.coverage_ratio ?? 0
      )}`
    );
  } catch (err) {
    // No mock fallback: a failed run must read as a failure, never as fabricated results.
    result.value = null;
    errorMessage.value = err instanceof ApiError ? err.message : String(err);
  } finally {
    loading.value = false;
  }
};

const outputSeries = computed<(number | null)[]>(() => {
  if (!result.value) return [];
  return result.value.series[form.output_column] ?? [];
});

const chartOptions = computed(() => {
  const values = outputSeries.value;
  const marks = (result.value?.segments ?? []).map((segment) => [
    { name: `#${segment.rank ?? ""}`, xAxis: segment.start_index },
    { xAxis: segment.end_index },
  ]);
  return {
    tooltip: { trigger: "axis" },
    grid: { left: "3%", right: "4%", bottom: "10%", containLabel: true },
    dataZoom: [{ type: "inside" }, { type: "slider" }],
    xAxis: { type: "category", data: values.map((_, index) => index) },
    yAxis: { type: "value", scale: true },
    series: [
      {
        name: form.output_column,
        type: "line",
        showSymbol: false,
        color: "#1E6091",
        data: values,
        markArea: {
          itemStyle: { color: "rgba(230, 145, 56, 0.22)" },
          data: marks,
        },
      },
    ],
  };
});

const rejectionRows = computed(() =>
  Object.entries(result.value?.selection?.rejection_counts ?? {}).map(([reason, count]) => ({
    reason,
    count,
  }))
);

const excitationRows = computed(() => {
  const actual = result.value?.selection?.persistent_excitation_order ?? {};
  const required = result.value?.selection?.required_excitation_order ?? {};
  return Object.keys(required).map((column) => ({
    column,
    actual: actual[column] ?? 0,
    required: required[column],
  }));
});

const reasonLabel = (reason: string) => REASON_LABELS[reason] ?? reason;

const percent = (value: number | null | undefined) =>
  value === null || value === undefined ? "—" : `${(value * 100).toFixed(2)}%`;

const formatNumber = (value: number | null | undefined) => {
  if (value === null || value === undefined || !Number.isFinite(value)) return "—";
  if (Math.abs(value) >= 10000) return value.toExponential(2);
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

.segmentation-layout {
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

.advisory {
  margin-top: 14px;
}

.rejection-block {
  margin-top: 14px;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
}

.rejection-title {
  font-size: 13px;
  color: var(--text-secondary);
}

.rejection-tag {
  margin-right: 4px;
}

.footer-actions {
  margin-top: 16px;
  display: flex;
  justify-content: flex-end;
}
</style>
