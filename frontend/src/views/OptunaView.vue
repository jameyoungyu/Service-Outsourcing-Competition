<template>
  <div class="optuna-view">
    <div class="page-header">
      <h2>闭环参数自动寻优</h2>
      <p class="subtitle">
        以<strong>验证集自由仿真 FIT</strong> 为反馈目标，自动迭代寻优质量门控阈值、优选预算与
        ARX 模型结构；失败与被剪枝的试验一并保留展示
      </p>
    </div>

    <div class="optuna-layout">
      <div class="industrial-card">
        <div class="industrial-card-header">
          <div class="industrial-card-title">
            <el-icon><RefreshRight /></el-icon> 闭环寻优任务控制台
          </div>
        </div>

        <el-form :inline="true" :model="form" label-width="110px">
          <el-form-item label="数据版本 ID">
            <el-input v-model="form.version_id" placeholder="version_id" style="width: 320px" />
          </el-form-item>
          <el-form-item label="输入变量">
            <el-input v-model="inputColumnsText" placeholder="u1,u2" style="width: 180px" />
          </el-form-item>
          <el-form-item label="输出变量">
            <el-input v-model="form.output_column" placeholder="y" style="width: 110px" />
          </el-form-item>
          <el-form-item label="Trial 次数">
            <el-input-number v-model="form.max_trials" :min="1" :max="500" :step="5" />
          </el-form-item>
          <el-form-item label="随机种子">
            <el-input-number v-model="form.random_seed" :min="0" :max="99999" />
          </el-form-item>
          <el-form-item>
            <el-button
              type="primary"
              :loading="isSearching"
              icon="VideoPlay"
              @click="handleStart"
            >
              开始闭环寻优
            </el-button>
          </el-form-item>
        </el-form>

        <el-alert v-if="errorMessage" type="error" :closable="false" show-icon class="alert-gap">
          <template #title>寻优失败：{{ errorMessage }}</template>
        </el-alert>
        <el-alert v-if="isSearching" type="info" :closable="false" show-icon class="alert-gap">
          <template #title>
            正在执行真实闭环：门控 → D-最优优选 → ARX 结构扫描 → 自由仿真评价，请稍候
          </template>
        </el-alert>
      </div>

      <template v-if="status">
        <div class="industrial-card">
          <div class="industrial-card-header">
            <div class="industrial-card-title">
              <el-icon><Trophy /></el-icon> 寻优结论
            </div>
            <el-tag v-if="status.warm_started_from" type="warning">
              已从历史相似工况热启动
            </el-tag>
            <el-tag v-else type="info">冷启动（策略记忆库中无相似工况）</el-tag>
          </div>

          <el-descriptions border :column="4" size="small">
            <el-descriptions-item label="最佳 Trial">
              #{{ status.best_trial_id ?? "—" }}
            </el-descriptions-item>
            <el-descriptions-item label="最优目标值">
              <span class="fit-val">{{ num(status.best_value) }}</span>
            </el-descriptions-item>
            <el-descriptions-item label="有效 / 剪枝 / 失败">
              {{ stat("completed_trials") }} / {{ stat("pruned_trials") }} /
              {{ stat("failed_trials") }}
            </el-descriptions-item>
            <el-descriptions-item label="单 Trial 平均耗时">
              {{ num(status.statistics.mean_trial_ms) }} ms
            </el-descriptions-item>
            <el-descriptions-item label="模型拟合次数">
              {{ stat("structure_evaluations") }}
            </el-descriptions-item>
            <el-descriptions-item label="区间优选执行次数">
              {{ stat("selection_computations") }}
            </el-descriptions-item>
            <el-descriptions-item label="昂贵环节摊薄倍数">
              <span class="fit-val">{{ num(status.statistics.evaluations_per_selection) }}×</span>
            </el-descriptions-item>
            <el-descriptions-item label="血缘缓存命中率">
              {{ pct(status.statistics.hit_rate) }}
            </el-descriptions-item>
          </el-descriptions>

          <el-alert type="info" :closable="false" class="alert-gap">
            <template #title>
              摊薄倍数 = 模型拟合次数 / 区间优选执行次数。优选是流水线中最昂贵的环节，分级搜索让每次优选服务于整组模型结构评估。血缘缓存命中率在扁平采样下通常很低（实测约
              1.7%），真正的节省来自分级搜索本身。
            </template>
          </el-alert>
        </div>

        <div class="charts-grid">
          <div class="industrial-card">
            <div class="industrial-card-header">
              <div class="industrial-card-title">
                <el-icon><TrendCharts /></el-icon> 历史最佳目标值收敛曲线
              </div>
            </div>
            <ChartContainer :options="convergenceOptions" height="320px" />
          </div>

          <div class="industrial-card">
            <div class="industrial-card-header">
              <div class="industrial-card-title">
                <el-icon><DataBoard /></el-icon> 超参数重要性（秩相关，归一化）
              </div>
            </div>
            <ChartContainer :options="importanceOptions" height="320px" />
          </div>
        </div>

        <div class="industrial-card">
          <div class="industrial-card-header">
            <div class="industrial-card-title">
              <el-icon><Setting /></el-icon> 最优参数组合
            </div>
          </div>
          <el-descriptions border :column="3" size="small">
            <el-descriptions-item
              v-for="(value, key) in status.best_params"
              :key="key"
              :label="String(key)"
            >
              <span class="code-inline">{{ formatParam(value) }}</span>
            </el-descriptions-item>
          </el-descriptions>

          <div class="footer-actions">
            <el-button type="success" icon="Document" @click="$router.push('/deliverables')">
              生成图文报告并导出优选数据集 →
            </el-button>
          </div>
        </div>

        <div class="industrial-card">
          <div class="industrial-card-header">
            <div class="industrial-card-title">
              <el-icon><List /></el-icon> 全部试验记录（含失败与剪枝）
            </div>
          </div>
          <el-table :data="status.trials" stripe height="360" style="width: 100%">
            <el-table-column prop="trial_id" label="Trial" width="90" />
            <el-table-column label="状态" width="110">
              <template #default="{ row }">
                <el-tag :type="stateType(row.state)" size="small">{{ stateLabel(row.state) }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="目标值" width="130">
              <template #default="{ row }">{{ num(row.value) }}</template>
            </el-table-column>
            <el-table-column label="失败原因" width="220">
              <template #default="{ row }">{{ row.error_code || "—" }}</template>
            </el-table-column>
            <el-table-column label="参数">
              <template #default="{ row }">
                <span class="code-inline params-cell">{{ compactParams(row.params) }}</span>
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
import {
  DataBoard,
  Document,
  List,
  RefreshRight,
  Setting,
  TrendCharts,
  Trophy,
  VideoPlay,
} from "@element-plus/icons-vue";
import ChartContainer from "../components/ChartContainer.vue";
import { getOptunaStatus, startOptunaStudy } from "../api/modeling";
import type { OptunaStartRequest, OptunaStatusResponse } from "../types/api";
import { ApiError } from "../api/client";
import { ElMessage } from "element-plus";

const STATE_LABELS: Record<string, string> = {
  complete: "成功",
  pruned: "剪枝",
  failed: "失败",
  running: "运行中",
  queued: "排队",
};

const isSearching = ref(false);
const status = ref<OptunaStatusResponse | null>(null);
const errorMessage = ref("");
const inputColumnsText = ref("u1,u2");

const form = reactive<OptunaStartRequest>({
  version_id: "",
  input_columns: [],
  output_column: "y",
  max_trials: 30,
  random_seed: 42,
});

const handleStart = async () => {
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

  isSearching.value = true;
  status.value = null;
  try {
    const started = await startOptunaStudy(form);
    // No mock convergence loop: the curve shown must come from real trials.
    status.value = await getOptunaStatus(started.study_id);
    ElMessage.success(`闭环寻优完成：最优目标值 ${num(status.value.best_value)}`);
  } catch (err) {
    status.value = null;
    errorMessage.value = err instanceof ApiError ? err.message : String(err);
  } finally {
    isSearching.value = false;
  }
};

const stat = (key: keyof NonNullable<OptunaStatusResponse["statistics"]>) => {
  const value = status.value?.statistics?.[key];
  return value === undefined ? "—" : value;
};

const convergenceOptions = computed(() => {
  if (!status.value) return {};
  const curve = status.value.best_curve;
  return {
    tooltip: { trigger: "axis" },
    grid: { left: "3%", right: "4%", bottom: "10%", containLabel: true },
    xAxis: { type: "category", data: curve.map((_, index) => `#${index}`) },
    yAxis: { type: "value", name: "目标值", scale: true },
    series: [
      {
        name: "历史最佳目标值",
        type: "line",
        step: "end",
        color: "#2A9D8F",
        showSymbol: false,
        data: curve,
      },
      {
        name: "各 Trial 目标值",
        type: "scatter",
        color: "#E76F51",
        symbolSize: 6,
        data: status.value.trials.map((trial) => trial.value),
      },
    ],
  };
});

const importanceOptions = computed(() => {
  if (!status.value) return {};
  const entries = Object.entries(status.value.param_importances).sort((a, b) => b[1] - a[1]);
  return {
    tooltip: { trigger: "axis" },
    grid: { left: "3%", right: "6%", bottom: "6%", containLabel: true },
    xAxis: { type: "value", name: "相对重要性" },
    yAxis: { type: "category", data: entries.map(([name]) => name).reverse() },
    series: [
      {
        type: "bar",
        color: "#1E6091",
        data: entries.map(([, value]) => value).reverse(),
      },
    ],
  };
});

const stateLabel = (state: string) => STATE_LABELS[state] ?? state;

const stateType = (state: string) =>
  state === "complete" ? "success" : state === "failed" ? "danger" : "warning";

const formatParam = (value: unknown) =>
  typeof value === "number" ? num(value) : String(value);

const compactParams = (params: Record<string, unknown>) =>
  Object.entries(params)
    .map(([key, value]) => `${key}=${formatParam(value)}`)
    .join("  ");

const num = (value: number | null | undefined) => {
  if (value === null || value === undefined || !Number.isFinite(value)) return "—";
  if (Number.isInteger(value)) return String(value);
  return value.toFixed(4);
};

const pct = (value: number | null | undefined) =>
  value === null || value === undefined || !Number.isFinite(value)
    ? "—"
    : `${(value * 100).toFixed(1)}%`;
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

.optuna-layout {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.charts-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(420px, 1fr));
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

.footer-actions {
  margin-top: 16px;
  display: flex;
  justify-content: flex-end;
}

.params-cell {
  font-size: 12px;
  word-break: break-all;
}
</style>
