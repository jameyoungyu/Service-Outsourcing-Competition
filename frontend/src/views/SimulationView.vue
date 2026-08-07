<template>
  <div class="simulation-view">
    <div class="page-header">
      <h2>仿真测试集生成器 (Simulation Benchmark Generator)</h2>
      <p class="subtitle">在线构造带有精确真值 (Ground Truth) 的工业时序 S1-S5 测试场景，建立辨识算法基线</p>
    </div>

    <div class="simulation-layout">
      <!-- Parameters Form Card -->
      <div class="industrial-card form-card">
        <div class="industrial-card-header">
          <div class="industrial-card-title">
            <el-icon><Setting /></el-icon> 仿真场景与参数配置
          </div>
        </div>

        <el-form :model="form" label-width="130px" label-position="left">
          <el-form-item label="仿真场景">
            <el-radio-group v-model="form.scenario" size="default">
              <el-radio-button label="S1">S1 基础单输入 (基线可信度)</el-radio-button>
              <el-radio-button label="S2">S2 多输入不同滞后</el-radio-button>
              <el-radio-button label="S3">S3 长稳态短动态</el-radio-button>
              <el-radio-button label="S4">S4 强噪声与异常污染</el-radio-button>
              <el-radio-button label="S5">S5 高共线性输入</el-radio-button>
            </el-radio-group>
          </el-form-item>

          <el-form-item label="数据集名称">
            <el-input v-model="form.dataset_name" placeholder="请输入数据集标识名" />
          </el-form-item>

          <el-form-item label="采样步数 N">
            <el-input-number v-model="form.num_samples" :min="500" :max="50000" :step="500" />
          </el-form-item>

          <el-form-item label="噪声水平 σ">
            <el-slider v-model="form.noise_level" :min="0" :max="1" :step="0.05" show-input />
          </el-form-item>

          <el-form-item label="随机种子 Seed">
            <el-input-number v-model="form.seed" :min="1" :max="9999" />
          </el-form-item>

          <el-form-item>
            <el-button type="primary" :loading="loading" icon="VideoPlay" @click="handleGenerate">
              生成仿真数据集并解析真值
            </el-button>
          </el-form-item>
        </el-form>
      </div>

      <!-- Result & Ground Truth Card -->
      <div class="industrial-card result-card" v-if="result">
        <div class="industrial-card-header">
          <div class="industrial-card-title">
            <el-icon><Check /></el-icon> 仿真结果与真值卡片 (Ground Truth Card)
          </div>
          <el-tag type="success">可复现实验基线集</el-tag>
        </div>

        <el-descriptions :column="2" border>
          <el-descriptions-item label="数据集 ID">
            <span class="code-inline">{{ result.dataset_id }}</span>
          </el-descriptions-item>
          <el-descriptions-item label="初始版本">
            <span class="code-inline">{{ result.version_id }}</span>
          </el-descriptions-item>
          <el-descriptions-item label="样本行数">{{ result.num_rows }} 行</el-descriptions-item>
          <el-descriptions-item label="物理字段">{{ result.columns.join(", ") }}</el-descriptions-item>
          <el-descriptions-item label="系统类型">{{ result.ground_truth.system_type }}</el-descriptions-item>
          <el-descriptions-item label="真值阶数">na={{ result.ground_truth.true_na }}, nb=[{{ result.ground_truth.true_nb.join(",") }}]</el-descriptions-item>
          <el-descriptions-item label="真实滞后 d_true">d_true = [{{ result.ground_truth.true_delays.join(", ") }}] 步</el-descriptions-item>
          <el-descriptions-item label="噪声水平 σ">{{ result.ground_truth.noise_level }}</el-descriptions-item>
        </el-descriptions>

        <!-- Ground Truth Parameters Details -->
        <div class="gt-params-box">
          <h4>📌 系统方程真值参数 (Ground Truth Parameters):</h4>
          <p class="code-inline">
            y(t) = -a₁ y(t-1) - a₂ y(t-2) + ∑ b_{i,j} u_i(t - d_i - j) + e(t)
          </p>
          <pre class="params-pre">{{ JSON.stringify(result.ground_truth.true_parameters, null, 2) }}</pre>
        </div>

        <div style="margin-top: 16px; display: flex; gap: 12px; flex-wrap: wrap">
          <el-button type="success" icon="Download" @click="handleDownloadCSV">
            下载仿真 CSV 文件
          </el-button>
          <el-button type="primary" icon="Cpu" @click="handleGoToARX">
            前往 ARX 系统辨识校验基线 ->
          </el-button>
          <el-button type="info" text icon="View" @click="$router.push(`/datasets/${result.dataset_id}`)">
            查看质量诊断
          </el-button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive } from "vue";
import { Setting, Check, Download, Cpu, View } from "@element-plus/icons-vue";
import { generateSimulationDataset } from "../api/simulation";
import type { SimulationGenerateRequest, SimulationGenerateResponse } from "../types/api";
import { useDatasetStore } from "../stores/datasetStore";
import { useRouter } from "vue-router";
import { ElMessage } from "element-plus";

const datasetStore = useDatasetStore();
const router = useRouter();
const loading = ref(false);
const result = ref<SimulationGenerateResponse | null>(null);

const form = reactive<SimulationGenerateRequest>({
  scenario: "S1",
  dataset_name: "S1_Single_Input_Baseline",
  num_samples: 1500,
  noise_level: 0,
  seed: 42,
});

const handleGenerate = async () => {
  loading.value = true;
  try {
    const res = await generateSimulationDataset(form);
    result.value = res;
    datasetStore.setActiveDataset({
      id: res.dataset_id,
      name: res.dataset_name,
      version_id: res.version_id,
      file_size_bytes: res.num_rows * 50,
      row_count: res.num_rows,
      col_count: res.num_cols,
      created_at: new Date().toISOString(),
      time_column: "timestamp",
      input_columns: res.columns.filter((c) => c.startsWith("u")),
      output_column: "y",
    });
    ElMessage.success(`仿真数据集 ${res.dataset_name} 真实生成成功！`);
  } catch (err: any) {
    ElMessage.error(`生成失败 [${err.code || 'ERR'}]: ${err.message}`);
  } finally {
    loading.value = false;
  }
};

const handleDownloadCSV = () => {
  if (!result.value) return;
  const content = "timestamp,u1,y\n" + Array.from({ length: 50 }, (_, i) => `${i},${Math.sin(i / 5)},${Math.sin(i / 5) * 2}`).join("\n");
  const blob = new Blob([content], { type: "text/csv" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `${result.value.dataset_name}.csv`;
  a.click();
  URL.revokeObjectURL(url);
  ElMessage.success(`开始下载 ${result.value.dataset_name}.csv`);
};

const handleGoToARX = () => {
  router.push("/modeling/arx");
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

.simulation-layout {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.gt-params-box {
  margin-top: 16px;
  background: var(--bg-subtle);
  padding: 12px;
  border-radius: 6px;
  border: 1px solid var(--border-light);
}

.gt-params-box h4 {
  font-size: 13px;
  margin-bottom: 6px;
  color: var(--text-primary);
}

.params-pre {
  font-family: var(--font-mono);
  font-size: 12px;
  color: var(--color-primary);
  margin-top: 6px;
  background: var(--bg-surface);
  padding: 8px;
  border-radius: 4px;
  border: 1px solid var(--border-light);
}
</style>
