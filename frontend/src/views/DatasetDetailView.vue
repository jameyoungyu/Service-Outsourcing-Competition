<template>
  <div class="dataset-detail-view">
    <div class="page-header" v-if="dataset">
      <h2>数据集详情: {{ dataset.name }}</h2>
      <p class="subtitle">
        ID: {{ dataset.id }} | 激活版本: <span class="code-inline">{{ dataset.version_id || dataset.latest_version_id }}</span> |
        来源: <el-tag size="small" type="info">{{ dataset.source || 'upload' }}</el-tag>
      </p>
    </div>

    <el-tabs v-model="activeTab" type="card" class="detail-tabs">
      <!-- Tab 1: Overview & Time-Series Plot -->
      <el-tab-pane label="概览与多变量时序预览" name="overview">
        <div class="industrial-card" v-if="dataset">
          <div class="industrial-card-header">
            <div class="industrial-card-title">
              <el-icon><DataLine /></el-icon> 多变量数据前 100 行预览
            </div>
          </div>

          <el-table v-if="dataset.preview && dataset.preview.length > 0" :data="dataset.preview" stripe style="width: 100%; max-height: 300px">
            <el-table-column v-for="col in Object.keys(dataset.preview[0])" :key="col" :prop="col" :label="col" />
          </el-table>
          <div v-else style="padding: 20px 0; text-align: center; color: var(--text-secondary)">
            无数据行预览
          </div>
        </div>
      </el-tab-pane>

      <!-- Tab 2: Quality Profile -->
      <el-tab-pane label="★ 真实数据质量诊断报告" name="profile">
        <StateView v-if="profileLoading" state="loading" title="正在生成真实数据质量 Profile..." />

        <div class="industrial-card" v-else-if="profile">
          <div class="profile-score-box">
            <div class="score-num" :class="{ warning: profile.quality_score < 80 }">
              {{ profile.quality_score }} <span class="max">/ 100 分</span>
            </div>
            <div class="score-desc">
              <div class="title">数据质量诊断结论: {{ profile.quality_score >= 80 ? '良好' : '存在质量缺陷 (需清洗规整)' }}</div>
              <p>
                总体缺失率: {{ (profile.missing_rate * 100).toFixed(2) }}% |
                不规则采样率: {{ ((profile.irregular_sampling_rate || 0) * 100).toFixed(2) }}% |
                死值冻结段: {{ profile.frozen_segments || 0 }} 处
              </p>
            </div>
          </div>

          <el-divider />

          <!-- Column Missing Rates Breakdown -->
          <div style="margin-bottom: 20px">
            <h4>📊 各变量缺失率分布 (Missing Rates):</h4>
            <el-row :gutter="16" style="margin-top: 10px">
              <el-col :span="6" v-for="(rate, col) in profile.missing_rates" :key="col">
                <div class="stat-mini-card">
                  <div class="col-name">{{ col }}</div>
                  <div class="rate-val">{{ (rate * 100).toFixed(2) }}%</div>
                  <div class="sub-info">异常点: {{ profile.anomaly_counts[col] || 0 }}</div>
                </div>
              </el-col>
            </el-row>
          </div>

          <!-- Column Statistics Table -->
          <div style="margin-bottom: 20px" v-if="profile.column_statistics">
            <h4>📐 变量统计量矩阵 (Column Statistics):</h4>
            <el-table :data="formattedColStats" stripe style="width: 100%; margin-top: 10px">
              <el-table-column prop="col" label="变量名" width="120" />
              <el-table-column prop="count" label="有效行" width="100" />
              <el-table-column prop="mean" label="均值 (Mean)" />
              <el-table-column prop="std" label="标准差 (Std)" />
              <el-table-column prop="min" label="最小值 (Min)" />
              <el-table-column prop="max" label="最大值 (Max)" />
              <el-table-column prop="q50" label="中位数 (Q50)" />
            </el-table>
          </div>

          <!-- Recommendations -->
          <div class="recommendations">
            <h4>💡 智能预处理建议 (Recommendations)：</h4>
            <ul>
              <li v-for="(rec, idx) in profile.recommendations" :key="idx">{{ rec }}</li>
            </ul>
          </div>

          <div style="margin-top: 20px">
            <el-button type="primary" icon="ArrowRight" @click="$router.push('/preprocessing/cleaning')">
              前往执行时间规整与异常清洗
            </el-button>
          </div>
        </div>
      </el-tab-pane>

      <!-- Tab 3: Version Lineage DAG -->
      <el-tab-pane label="数据版本血缘 (DAG)" name="versions">
        <div class="industrial-card">
          <div class="industrial-card-header">
            <div class="industrial-card-title">
              <el-icon><Share /></el-icon> 真实版本演化拓扑 (Dataset Version Nodes)
            </div>
          </div>
          <el-timeline v-if="versionNodes.length > 0">
            <el-timeline-item
              v-for="node in versionNodes"
              :key="node.version_id"
              :timestamp="node.created_at"
              :type="node.version_id === (dataset?.version_id || dataset?.latest_version_id) ? 'primary' : 'info'"
              placement="top"
            >
              <el-card>
                <h4>{{ node.operation_name }} (<span class="code-inline">{{ node.version_id }}</span>)</h4>
                <p v-if="node.parent_version_id">父版本: <span class="code-inline">{{ node.parent_version_id }}</span></p>
                <p v-if="node.parameters">参数: {{ JSON.stringify(node.parameters) }}</p>
              </el-card>
            </el-timeline-item>
          </el-timeline>
          <div v-else style="padding: 20px 0; text-align: center; color: var(--text-secondary)">
            暂无派生版本记录
          </div>
        </div>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed } from "vue";
import { useRoute } from "vue-router";
import { DataLine, Share, ArrowRight } from "@element-plus/icons-vue";
import StateView from "../components/StateView.vue";
import { getDatasetDetail, getDatasetProfile, getDatasetVersions } from "../api/datasets";
import type { DatasetItem, DatasetProfile, DatasetVersionNode } from "../types/api";
import { ElMessage } from "element-plus";

const route = useRoute();
const activeTab = ref("overview");
const datasetId = (route.params.id as string) || "ds_s1";

const dataset = ref<DatasetItem | null>(null);
const profile = ref<DatasetProfile | null>(null);
const profileLoading = ref(false);
const versionNodes = ref<DatasetVersionNode[]>([]);

const fetchDetail = async () => {
  try {
    const res = await getDatasetDetail(datasetId);
    dataset.value = res;
  } catch (err: any) {
    ElMessage.error(`获取数据集详情失败 [${err.code || 'ERR'}]: ${err.message}`);
  }
};

const fetchProfile = async () => {
  profileLoading.value = true;
  try {
    const res = await getDatasetProfile(datasetId);
    profile.value = res;
  } catch (err: any) {
    ElMessage.error(`获取数据质量 Profile 失败 [${err.code || 'ERR'}]: ${err.message}`);
  } finally {
    profileLoading.value = false;
  }
};

const fetchVersions = async () => {
  try {
    const res = await getDatasetVersions(datasetId);
    versionNodes.value = res.nodes || [];
  } catch (err: any) {
    // Keep empty array
  }
};

const formattedColStats = computed(() => {
  if (!profile.value || !profile.value.column_statistics) return [];
  return Object.entries(profile.value.column_statistics).map(([col, stat]) => ({
    col,
    count: stat.count,
    mean: stat.mean !== null ? stat.mean.toFixed(4) : "-",
    std: stat.std !== null ? stat.std.toFixed(4) : "-",
    min: stat.min !== null ? stat.min.toFixed(4) : "-",
    max: stat.max !== null ? stat.max.toFixed(4) : "-",
    q50: stat.q50 !== null ? stat.q50.toFixed(4) : "-",
  }));
});

onMounted(() => {
  fetchDetail();
  fetchProfile();
  fetchVersions();
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

.profile-score-box {
  display: flex;
  align-items: center;
  gap: 24px;
}

.score-num {
  font-size: 42px;
  font-weight: 800;
  color: var(--color-success);
  font-family: var(--font-mono);
}

.score-num.warning {
  color: var(--color-warning-dark);
}

.max {
  font-size: 16px;
  color: var(--text-secondary);
  font-weight: 400;
}

.score-desc .title {
  font-size: 18px;
  font-weight: 600;
  color: var(--text-primary);
}

.stat-mini-card {
  background: var(--bg-subtle);
  border: 1px solid var(--border-light);
  border-radius: 6px;
  padding: 10px;
  text-align: center;
}

.col-name {
  font-weight: 600;
  font-size: 13px;

  color: var(--text-primary);
}

.rate-val {
  font-size: 18px;
  font-weight: 700;
  color: var(--color-primary);
  font-family: var(--font-mono);
  margin: 4px 0;
}

.sub-info {
  font-size: 11px;
  color: var(--text-muted);
}

.recommendations h4 {
  margin-bottom: 8px;
  color: var(--text-primary);
}

.recommendations ul {
  padding-left: 20px;
  color: var(--text-secondary);
  font-size: 14px;
  line-height: 1.8;
}
</style>
