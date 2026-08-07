<template>
  <div class="arx-modeling-view">
    <div class="page-header">
      <h2>ARX 系统辨识与模型评价 (ARX System Identification)</h2>
      <p class="subtitle">在精选数据版本上求解离散时间 ARX 结构参数，验证 R²、FIT 拟合度与残差独立性</p>
    </div>

    <div class="modeling-layout">
      <!-- Target Dataset Info -->
      <div class="industrial-card" v-if="activeDataset">
        <div class="industrial-card-header">
          <div class="industrial-card-title">
            <el-icon><FolderOpened /></el-icon> 当前辨识目标数据集: {{ activeDataset.name }}
          </div>
          <el-tag type="primary">ID: {{ activeDataset.id }} (版本: {{ activeDataset.version_id }})</el-tag>
        </div>
        <p class="dataset-meta">
          过程输入 (Inputs): <span class="code-inline">{{ inputCols.join(", ") }}</span> |
          控制输出 (Output): <span class="code-inline">{{ activeDataset.output_column }}</span>
        </p>
      </div>

      <!-- Model Config Card -->
      <div class="industrial-card">
        <div class="industrial-card-header">
          <div class="industrial-card-title">
            <el-icon><Cpu /></el-icon> ARX 模型结构与求解器设置
          </div>
        </div>

        <el-form :inline="true" :model="form">
          <el-form-item label="输出阶数 na">
            <el-input-number v-model="form.na" :min="1" :max="5" />
          </el-form-item>

          <el-form-item
            v-for="(col, idx) in inputCols"
            :key="'nb_' + col"
            :label="`输入 ${col} 阶数 nb`"
          >
            <el-input-number v-model="form.nb[idx]" :min="1" :max="5" />
          </el-form-item>

          <el-form-item
            v-for="(col, idx) in inputCols"
            :key="'delay_' + col"
            :label="`输入 ${col} 滞后 d`"
          >
            <el-input-number v-model="form.delays[idx]" :min="0" :max="20" />
          </el-form-item>

          <el-form-item label="求解算法">
            <el-select v-model="form.estimation_method" style="width: 160px">
              <el-option label="最小二乘 (OLS)" value="ols" />
              <el-option label="岭回归 (Ridge)" value="ridge" />
            </el-select>
          </el-form-item>

          <el-form-item label="岭惩罚 α" v-if="form.estimation_method === 'ridge'">
            <el-input-number v-model="form.ridge_alpha" :min="0.001" :max="10" :step="0.1" />
          </el-form-item>

          <el-form-item>
            <el-button type="primary" :loading="loading" icon="VideoPlay" @click="handleFit">
              运行 ARX 辨识
            </el-button>
          </el-form-item>
        </el-form>
      </div>

      <!-- Evaluation Metrics -->
      <div class="industrial-card" v-if="fitResult">
        <div class="industrial-card-header">
          <div class="industrial-card-title">
            <el-icon><Trophy /></el-icon> 辨识结果与多分区验证指标
          </div>
          <el-tag type="success">验证集 FIT: {{ fitResult.metrics.val_fit }}%</el-tag>
        </div>

        <div class="metrics-grid">
          <div class="metric-box">
            <div class="name">训练集 R²</div>
            <div class="val">{{ fitResult.metrics.train_r2 }}%</div>
          </div>
          <div class="metric-box">
            <div class="name">训练集 FIT</div>
            <div class="val">{{ fitResult.metrics.train_fit }}%</div>
          </div>
          <div class="metric-box highlight">
            <div class="name">验证集 FIT (核心盲测)</div>
            <div class="val">{{ fitResult.metrics.val_fit }}%</div>
          </div>
          <div class="metric-box">
            <div class="name">测试集 FIT (全期终考)</div>
            <div class="val">{{ fitResult.metrics.test_fit }}%</div>
          </div>
          <div class="metric-box">
            <div class="name">均方根误差 (RMSE)</div>
            <div class="val">{{ fitResult.metrics.rmse }}</div>
          </div>
        </div>

        <el-divider />

        <div class="coefficients-box">
          <h4>估计参数方程:</h4>
          <p class="code-inline">
            A(q⁻¹)y(t) = ∑ B_i(q⁻¹)u_i(t-d_i) + e(t)
          </p>
          <p>a 系数: {{ fitResult.a_coefficients.join(", ") }}</p>
          <p>b 系数: {{ JSON.stringify(fitResult.b_coefficients) }}</p>
        </div>
      </div>

      <!-- Fitting Plot -->
      <div class="industrial-card" v-if="fitResult">
        <div class="industrial-card-header">
          <div class="industrial-card-title">
            <el-icon><TrendCharts /></el-icon> 真实实测输出 y(t) vs 辨识预测 ŷ(t) 对比图
          </div>
        </div>
        <ChartContainer :options="plotOptions" height="380px" />

        <div style="margin-top: 16px; display: flex; justify-content: flex-end">
          <el-button type="warning" icon="RefreshRight" @click="$router.push('/modeling/optimization')">
            进入 Optuna 闭环参数自动寻优 ->
          </el-button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, watch, onMounted } from "vue";
import { Cpu, VideoPlay, Trophy, TrendCharts, RefreshRight, FolderOpened } from "@element-plus/icons-vue";
import ChartContainer from "../components/ChartContainer.vue";
import { fitARXModel } from "../api/modeling";
import type { ARXFitRequest, ARXFitResponse } from "../types/api";
import { useDatasetStore } from "../stores/datasetStore";
import { ElMessage } from "element-plus";

const datasetStore = useDatasetStore();
const loading = ref(false);
const fitResult = ref<ARXFitResponse | null>(null);

const activeDataset = computed(() => datasetStore.activeDataset);

const inputCols = computed(() => {
  if (activeDataset.value && activeDataset.value.input_columns.length > 0) {
    return activeDataset.value.input_columns;
  }
  return ["u1"];
});

const form = reactive<ARXFitRequest>({
  dataset_id: "ds_s1",
  version_id: "V0_Original",
  na: 2,
  nb: [2],
  delays: [3],
  estimation_method: "ols",
  ridge_alpha: 0.1,
});

const syncFormWithStore = () => {
  if (activeDataset.value) {
    form.dataset_id = activeDataset.value.id;
    form.version_id = activeDataset.value.version_id;
    const count = inputCols.value.length;
    form.nb = Array(count).fill(2);
    form.delays = Array(count).fill(3);
  }
};

watch(activeDataset, () => {
  syncFormWithStore();
}, { immediate: true });

onMounted(() => {
  syncFormWithStore();
});

const handleFit = async () => {
  loading.value = true;
  try {
    const res = await fitARXModel(form);
    fitResult.value = res;
    ElMessage.success(`ARX 系统辨识成功！验证集 FIT = ${res.metrics.val_fit}%`);
  } catch (err: any) {
    ElMessage.error(`ARX 辨识失败 [${err.code || "ERR"}]: ${err.message}`);
  } finally {
    loading.value = false;
  }
};

const plotOptions = computed(() => {
  if (!fitResult.value) return {};
  const data = fitResult.value.plot_data;
  const xData = data.indices.map((i) => `${i}s`);

  return {
    tooltip: { trigger: "axis" },
    legend: { data: ["实测输出 y(t)", "辨识预测 ŷ(t)"] },
    grid: { left: "3%", right: "4%", bottom: "10%", containLabel: true },
    xAxis: { type: "category", data: xData },
    yAxis: { type: "value" },
    series: [
      {
        name: "实测输出 y(t)",
        type: "line",
        color: "#1E6091",
        data: data.y_true,
      },
      {
        name: "辨识预测 ŷ(t)",
        type: "line",
        color: "#E76F51",
        lineStyle: { type: "dashed" },
        data: data.y_pred,
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

.dataset-meta {
  font-size: 13px;
  color: var(--text-secondary);
}

.modeling-layout {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.metrics-grid {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 16px;
}

.metric-box {
  background: var(--bg-subtle);
  padding: 12px;
  border-radius: 6px;
  border: 1px solid var(--border-light);
  text-align: center;
}

.metric-box.highlight {
  background: var(--color-primary-light);
  border-color: var(--color-primary);
}

.metric-box .name {
  font-size: 12px;
  color: var(--text-secondary);
}

.metric-box .val {
  font-size: 22px;
  font-weight: 700;
  color: var(--text-primary);
  font-family: var(--font-mono);
  margin-top: 4px;
}

.coefficients-box {
  background: var(--bg-subtle);
  padding: 12px;
  border-radius: 6px;
  font-size: 13px;
  color: var(--text-primary);
}
</style>
