<template>
  <div class="collinearity-view">
    <div class="page-header">
      <h2>共线性检测与冗余变量处理</h2>
      <p class="subtitle">
        Pearson / Spearman 相关、方差膨胀因子 VIF 与设计矩阵条件数；剔除建议需人工确认后生效
      </p>
    </div>

    <div class="collinearity-layout">
      <div class="industrial-card">
        <div class="industrial-card-header">
          <div class="industrial-card-title">
            <el-icon><Share /></el-icon> 诊断参数
          </div>
        </div>

        <el-form :inline="true" :model="form" label-width="110px">
          <el-form-item label="数据版本 ID">
            <el-input v-model="form.version_id" placeholder="version_id" style="width: 320px" />
          </el-form-item>
          <el-form-item label="输入变量">
            <el-input v-model="inputColumnsText" placeholder="u1,u2,u3" style="width: 220px" />
          </el-form-item>
          <el-form-item label="相关阈值">
            <el-input-number
              v-model="form.correlation_threshold"
              :min="0.5"
              :max="1"
              :step="0.01"
              :precision="2"
            />
          </el-form-item>
          <el-form-item label="VIF 阈值">
            <el-input-number v-model="form.vif_threshold" :min="1.5" :max="100" :step="0.5" />
          </el-form-item>
          <el-form-item>
            <el-button type="primary" :loading="loading" icon="Search" @click="handleAnalyze">
              执行共线性诊断
            </el-button>
          </el-form-item>
        </el-form>

        <el-alert v-if="errorMessage" type="error" :closable="false" show-icon class="alert-gap">
          <template #title>诊断失败：{{ errorMessage }}</template>
        </el-alert>
      </div>

      <template v-if="result">
        <div class="industrial-card">
          <div class="industrial-card-header">
            <div class="industrial-card-title">
              <el-icon><TrendCharts /></el-icon> 矩阵稳定性
            </div>
            <el-tag :type="conditionSeverity">
              条件数 {{ formatNumber(result.condition_number) }}
            </el-tag>
          </div>

          <el-descriptions :column="3" border size="small">
            <el-descriptions-item label="变量数">
              {{ result.variables.length }}
            </el-descriptions-item>
            <el-descriptions-item label="高相关变量组">
              {{ result.correlated_groups.length }}
            </el-descriptions-item>
            <el-descriptions-item label="建议剔除">
              {{ dropCount }}
            </el-descriptions-item>
          </el-descriptions>

          <div v-if="result.correlated_groups.length" class="group-block">
            <span class="group-title">高相关变量组：</span>
            <el-tag
              v-for="(group, index) in result.correlated_groups"
              :key="index"
              type="warning"
              effect="plain"
              class="group-tag"
            >
              {{ group.join(" ↔ ") }}
            </el-tag>
          </div>
        </div>

        <div class="industrial-card">
          <div class="industrial-card-header">
            <div class="industrial-card-title">
              <el-icon><Grid /></el-icon> Pearson 相关性热力图
            </div>
          </div>
          <ChartContainer :options="heatmapOptions" height="380px" />
        </div>

        <div class="industrial-card">
          <div class="industrial-card-header">
            <div class="industrial-card-title">
              <el-icon><Histogram /></el-icon> 方差膨胀因子 (VIF)
            </div>
          </div>
          <ChartContainer :options="vifOptions" height="300px" />
        </div>

        <div class="industrial-card">
          <div class="industrial-card-header">
            <div class="industrial-card-title">
              <el-icon><List /></el-icon> 变量处理建议（需人工确认）
            </div>
          </div>
          <el-table :data="result.recommendations" stripe style="width: 100%">
            <el-table-column prop="variable" label="变量" width="140" />
            <el-table-column label="建议动作" width="120">
              <template #default="{ row }">
                <el-tag :type="actionType(row.action)" size="small">
                  {{ actionLabel(row.action) }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="VIF" width="120">
              <template #default="{ row }">
                {{ formatNumber(result?.vif_scores[row.variable]) }}
              </template>
            </el-table-column>
            <el-table-column prop="reason" label="理由" />
          </el-table>

          <div class="footer-actions">
            <el-button
              type="success"
              icon="ArrowRight"
              @click="$router.push('/modeling/arx')"
            >
              下一步: 系统辨识 →
            </el-button>
          </div>
        </div>
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, reactive, ref } from "vue";
import {
  ArrowRight,
  Grid,
  Histogram,
  List,
  Search,
  Share,
  TrendCharts,
} from "@element-plus/icons-vue";
import ChartContainer from "../components/ChartContainer.vue";
import { calculateCollinearity } from "../api/preprocessing";
import type { CollinearityRequest, CollinearityResponse } from "../types/api";
import { ApiError } from "../api/client";
import { ElMessage } from "element-plus";

const ACTION_LABELS: Record<string, string> = {
  keep: "保留",
  drop: "建议剔除",
  merge: "建议合并",
  review: "需复核",
};

const loading = ref(false);
const result = ref<CollinearityResponse | null>(null);
const errorMessage = ref("");
const inputColumnsText = ref("u1,u2,u3");

const form = reactive<CollinearityRequest>({
  version_id: "",
  input_columns: [],
  correlation_threshold: 0.9,
  vif_threshold: 10,
});

const handleAnalyze = async () => {
  errorMessage.value = "";
  if (!form.version_id) {
    errorMessage.value = "请先填写数据版本 ID。";
    return;
  }
  form.input_columns = inputColumnsText.value
    .split(",")
    .map((name) => name.trim())
    .filter(Boolean);
  if (form.input_columns.length < 2) {
    errorMessage.value = "共线性分析至少需要两个输入变量。";
    return;
  }

  loading.value = true;
  try {
    result.value = await calculateCollinearity(form);
    ElMessage.success("共线性诊断完成");
  } catch (err) {
    // No mock fallback: a fabricated correlation matrix could justify deleting a real tag.
    result.value = null;
    errorMessage.value = err instanceof ApiError ? err.message : String(err);
  } finally {
    loading.value = false;
  }
};

const dropCount = computed(
  () => (result.value?.recommendations ?? []).filter((item) => item.action === "drop").length
);

const conditionSeverity = computed(() => {
  const value = result.value?.condition_number;
  if (value === null || value === undefined) return "info";
  if (value >= 100) return "danger";
  if (value >= 30) return "warning";
  return "success";
});

const heatmapOptions = computed(() => {
  if (!result.value) return {};
  const names = result.value.variables;
  const data: [number, number, number][] = [];
  result.value.matrix.forEach((row, i) => {
    row.forEach((value, j) => data.push([j, i, Number(value.toFixed(3))]));
  });
  return {
    tooltip: {
      formatter: (params: any) =>
        `${names[params.value[1]]} × ${names[params.value[0]]}<br/>r = ${params.value[2]}`,
    },
    grid: { left: "12%", right: "10%", bottom: "12%", top: "6%" },
    xAxis: { type: "category", data: names, splitArea: { show: true } },
    yAxis: { type: "category", data: names, splitArea: { show: true } },
    visualMap: {
      min: -1,
      max: 1,
      calculable: true,
      orient: "vertical",
      right: "2%",
      top: "middle",
      inRange: { color: ["#457B9D", "#F1FAEE", "#E63946"] },
    },
    series: [
      {
        type: "heatmap",
        data,
        label: { show: names.length <= 8 },
        emphasis: { itemStyle: { shadowBlur: 10 } },
      },
    ],
  };
});

const vifOptions = computed(() => {
  if (!result.value) return {};
  const names = result.value.variables;
  const threshold = form.vif_threshold ?? 10;
  return {
    tooltip: { trigger: "axis" },
    grid: { left: "3%", right: "4%", bottom: "10%", containLabel: true },
    xAxis: { type: "category", data: names },
    yAxis: { type: "value", name: "VIF" },
    series: [
      {
        type: "bar",
        data: names.map((name) => {
          const value = result.value!.vif_scores[name] ?? 0;
          return {
            value: Number.isFinite(value) ? value : 0,
            itemStyle: { color: value >= threshold ? "#E63946" : "#2A9D8F" },
          };
        }),
        markLine: {
          symbol: "none",
          data: [{ yAxis: threshold, name: "阈值" }],
          lineStyle: { type: "dashed", color: "#E76F51" },
        },
      },
    ],
  };
});

const actionLabel = (action: string) => ACTION_LABELS[action] ?? action;

const actionType = (action: string) =>
  action === "drop" ? "danger" : action === "review" ? "warning" : "success";

const formatNumber = (value: number | null | undefined) => {
  if (value === null || value === undefined || !Number.isFinite(value)) return "—";
  if (Math.abs(value) >= 10000) return value.toExponential(2);
  return value.toFixed(2);
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

.collinearity-layout {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.alert-gap {
  margin-top: 12px;
}

.group-block {
  margin-top: 14px;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
}

.group-title {
  font-size: 13px;
  color: var(--text-secondary);
}

.group-tag {
  margin-right: 4px;
}

.footer-actions {
  margin-top: 16px;
  display: flex;
  justify-content: flex-end;
}
</style>
