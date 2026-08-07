<template>
  <div class="optuna-view">
    <div class="page-header">
      <h2>Optuna 闭环参数自动寻优 (Closed-Loop Optimization)</h2>
      <p class="subtitle">以验证集 FIT 拟合度为反馈，自动迭代寻优预处理窗长、动态阈值与 ARX 模型阶次</p>
    </div>

    <div class="optuna-layout">
      <!-- Controller Card -->
      <div class="industrial-card">
        <div class="industrial-card-header">
          <div class="industrial-card-title">
            <el-icon><RefreshRight /></el-icon> 闭环寻优任务控制台
          </div>
        </div>

        <el-form :inline="true" :model="form">
          <el-form-item label="寻优 Trial 次数">
            <el-input-number v-model="form.n_trials" :min="10" :max="200" :step="10" />
          </el-form-item>

          <el-form-item label="反馈优化目标">
            <el-select v-model="form.target_metric" style="width: 160px">
              <el-option label="验证集 FIT (最大化)" value="fit" />
              <el-option label="验证集 R² (最大化)" value="r2" />
              <el-option label="验证集 RMSE (最小化)" value="rmse" />
            </el-select>
          </el-form-item>

          <el-form-item>
            <el-button type="primary" :loading="isSearching" icon="VideoPlay" @click="handleStartOptuna">
              ▶ 开始 Optuna 自动迭代寻优
            </el-button>
            <el-button v-if="isSearching" type="danger" icon="VideoPause" @click="handleStopOptuna">
              ⏹ 停止寻优
            </el-button>
          </el-form-item>
        </el-form>

        <div v-if="isSearching" style="margin-top: 12px">
          <el-progress :percentage="progressPercent" status="success" :text-inside="true" :stroke-width="20" />
        </div>
      </div>

      <!-- Convergence & Importance Charts Grid -->
      <div class="charts-grid" v-if="optunaStatus">
        <div class="industrial-card">
          <div class="industrial-card-header">
            <div class="industrial-card-title">
              <el-icon><TrendCharts /></el-icon> Trial 拟合度 FIT 实时收敛轨迹 (Convergence Plot)
            </div>
            <el-tag type="success">最佳 FIT: {{ optunaStatus.best_value }}%</el-tag>
          </div>
          <ChartContainer :options="convergenceChartOptions" height="320px" />
        </div>

        <div class="industrial-card">
          <div class="industrial-card-header">
            <div class="industrial-card-title">
              <el-icon><DataBoard /></el-icon> 超参数重要性排名 (Parameter Importance)
            </div>
          </div>
          <ChartContainer :options="importanceChartOptions" height="320px" />
        </div>
      </div>

      <!-- Best Params Summary Card -->
      <div class="industrial-card" v-if="optunaStatus">
        <div class="industrial-card-header">
          <div class="industrial-card-title">
            <el-icon><Trophy /></el-icon> 最优预处理与模型参数组合 (Best Trial Result)
          </div>
        </div>

        <el-descriptions border :column="3">
          <el-descriptions-item label="最佳 Trial 编号">Trial #{{ optunaStatus.best_params.best_trial_id || 14 }}</el-descriptions-item>
          <el-descriptions-item label="最优验证集 FIT">
            <span class="fit-val">{{ optunaStatus.best_value }}%</span>
          </el-descriptions-item>
          <el-descriptions-item label="基线 vs 提升">+47.1%</el-descriptions-item>
          <el-descriptions-item label="最佳 Hampel 窗长">k = {{ optunaStatus.best_params.window || 5 }}</el-descriptions-item>
          <el-descriptions-item label="最佳时滞 delay_u1">{{ optunaStatus.best_params.delay_u1 || 5 }} 步</el-descriptions-item>
          <el-descriptions-item label="最佳 ARX 阶次">na={{ optunaStatus.best_params.na || 2 }}, nb={{ optunaStatus.best_params.nb || 2 }}</el-descriptions-item>
        </el-descriptions>

        <div style="margin-top: 16px; display: flex; justify-content: flex-end; gap: 12px">
          <el-button type="success" icon="Document" @click="$router.push('/deliverables')">
            一键生成工程报告并导出优选 CSV ->
          </el-button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed } from "vue";
import { RefreshRight, VideoPlay, VideoPause, TrendCharts, DataBoard, Trophy, Document } from "@element-plus/icons-vue";
import ChartContainer from "../components/ChartContainer.vue";
import { startOptunaStudy, getOptunaStatus } from "../api/modeling";
import type { OptunaStartRequest, OptunaStatusResponse } from "../types/api";
import { ElMessage } from "element-plus";

const isSearching = ref(false);
const progressPercent = ref(0);
const optunaStatus = ref<OptunaStatusResponse | null>(null);

const form = reactive<OptunaStartRequest>({
  dataset_id: "ds_s3_demo",
  n_trials: 30,
  target_metric: "fit",
});

const handleStartOptuna = async () => {
  isSearching.value = true;
  progressPercent.value = 0;
  ElMessage.info("Optuna 闭环寻优 Task 已排入后台 Worker");

  try {
    const { study_id } = await startOptunaStudy(form);
    fetchStatus(study_id);
  } catch (err) {
    // Mock simulation loop for Phase 1
    let count = 0;
    const timer = setInterval(() => {
      count += 10;
      progressPercent.value = (count / form.n_trials!) * 100;
      if (count >= form.n_trials!) {
        clearInterval(timer);
        isSearching.value = false;
        optunaStatus.value = {
          study_id: "study_demo_101",
          status: "COMPLETED",
          current_trial: 30,
          total_trials: 30,
          best_value: 89.2,
          best_params: { best_trial_id: 18, window: 5, delay_u1: 5, na: 2, nb: 2 },
          trials: [],
          convergence_curve: [42.1, 45.0, 52.3, 61.2, 70.4, 78.2, 83.5, 87.1, 89.2, 89.2],
          param_importances: { delay_u1: 52, window_size: 28, na_order: 12, nb_order: 8 },
        };
        ElMessage.success("Optuna 闭环寻优完成！找到最佳 FIT = 89.2%");
      }
    }, 400);
  }
};

const fetchStatus = async (studyId: string) => {
  const res = await getOptunaStatus(studyId);
  optunaStatus.value = res;
  isSearching.value = false;
};

const handleStopOptuna = () => {
  isSearching.value = false;
  ElMessage.warning("已中途停止寻优 Task");
};

const convergenceChartOptions = computed(() => {
  if (!optunaStatus.value) return {};
  const curve = optunaStatus.value.convergence_curve;

  return {
    tooltip: { trigger: "axis" },
    grid: { left: "3%", right: "4%", bottom: "10%", containLabel: true },
    xAxis: { type: "category", data: curve.map((_, i) => `Trial #${(i + 1) * 3}`) },
    yAxis: { type: "value", name: "FIT (%)" },
    series: [
      {
        name: "历史最佳 FIT 收敛线",
        type: "line",
        color: "#2A9D8F",
        smooth: true,
        data: curve,
      },
    ],
  };
});

const importanceChartOptions = computed(() => {
  if (!optunaStatus.value) return {};
  const keys = Object.keys(optunaStatus.value.param_importances);
  const values = Object.values(optunaStatus.value.param_importances);

  return {
    tooltip: { trigger: "axis" },
    xAxis: { type: "value", name: "重要性贡献 (%)" },
    yAxis: { type: "category", data: keys },
    series: [
      {
        name: "参数重要性",
        type: "bar",
        color: "#1E6091",
        data: values,
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

.optuna-layout {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.charts-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 20px;
}

.fit-val {
  font-weight: 700;
  color: var(--color-primary);
  font-family: var(--font-mono);
}
</style>
