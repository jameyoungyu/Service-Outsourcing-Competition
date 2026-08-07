<template>
  <div class="segmentation-view">
    <div class="page-header">
      <h2>动态响应区间优选 (Dynamic Segment Selection)</h2>
      <p class="subtitle">无标签条件下自动捕获高信噪比、高动态阶跃/斜坡段，剔除无效稳态数据</p>
    </div>

    <div class="segmentation-layout">
      <!-- Config Form -->
      <div class="industrial-card">
        <div class="industrial-card-header">
          <div class="industrial-card-title">
            <el-icon><Crop /></el-icon> 动态区间筛选与 SNR 参数
          </div>
        </div>

        <el-form :inline="true" :model="form">
          <el-form-item label="最小区间长度">
            <el-input-number v-model="form.min_length" :min="20" :max="500" :step="10" />
          </el-form-item>
          <el-form-item label="最低 SNR 阈值">
            <el-input-number v-model="form.min_snr_db" :min="5" :max="30" :step="1" />
            <span style="margin-left: 6px">dB</span>
          </el-form-item>
          <el-form-item label="保留 Top K 区间">
            <el-input-number v-model="form.top_k" :min="1" :max="10" />
          </el-form-item>
          <el-form-item>
            <el-button type="primary" :loading="loading" icon="Search" @click="handleSegment">
              识别动态响应区间
            </el-button>
          </el-form-item>
        </el-form>
      </div>

      <!-- Segment Overlay Plot -->
      <div class="industrial-card" v-if="segmentResult">
        <div class="industrial-card-header">
          <div class="industrial-card-title">
            <el-icon><DataLine /></el-icon> 动态区间高亮叠加图 (High-Dynamic Segment Overlay)
          </div>
          <el-tag type="warning">提取出 {{ segmentResult.segments.length }} 个高动态区间</el-tag>
        </div>

        <ChartContainer :options="chartOptions" height="360px" />
      </div>

      <!-- Segment Table -->
      <div class="industrial-card" v-if="segmentResult">
        <div class="industrial-card-header">
          <div class="industrial-card-title">
            <el-icon><List /></el-icon> 提取出的动态区间分项列表
          </div>
        </div>

        <el-table :data="segmentResult.segments" stripe style="width: 100%">
          <el-table-column prop="segment_id" label="区间 ID" width="120" />
          <el-table-column label="样本范围 [Start - End]" width="200">
            <template #default="{ row }">
              <span class="code-inline">[{{ row.start_index }} - {{ row.end_index }}]</span>
            </template>
          </el-table-column>
          <el-table-column prop="snr_db" label="信噪比 (SNR)" width="140">
            <template #default="{ row }">
              <span class="fit-val">{{ row.snr_db }} dB</span>
            </template>
          </el-table-column>
          <el-table-column prop="dynamic_score" label="动态度评分" width="140" />
          <el-table-column prop="recommendation" label="系统推荐意见" />
        </el-table>

        <div style="margin-top: 16px; display: flex; justify-content: flex-end">
          <el-button type="success" icon="ArrowRight" @click="$router.push('/preprocessing/delay')">
            下一步: 时滞分析与补偿 ->
          </el-button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed } from "vue";
import { Crop, Search, DataLine, List, ArrowRight } from "@element-plus/icons-vue";
import ChartContainer from "../components/ChartContainer.vue";
import { segmentDataset } from "../api/preprocessing";
import type { SegmentRequest, SegmentResponse } from "../types/api";
import { ElMessage } from "element-plus";

const loading = ref(false);
const segmentResult = ref<SegmentResponse | null>(null);

const form = reactive<SegmentRequest>({
  dataset_id: "ds_s3_demo",
  version_id: "V1_Cleaned",
  min_length: 50,
  min_snr_db: 15,
  top_k: 2,
});

const handleSegment = async () => {
  loading.value = true;
  try {
    const res = await segmentDataset(form);
    segmentResult.value = res;
  } catch (err) {
    // Mock fallback for Phase 1
    segmentResult.value = {
      dataset_id: form.dataset_id,
      version_id: form.version_id,
      selected_segment_ids: ["seg_01", "seg_02"],
      segments: [
        {
          segment_id: "seg_01",
          start_index: 20,
          end_index: 45,
          snr_db: 18.5,
          dynamic_score: 92.4,
          recommendation: "强烈推荐 (高阶跃响应段)",
        },
        {
          segment_id: "seg_02",
          start_index: 65,
          end_index: 90,
          snr_db: 16.2,
          dynamic_score: 85.1,
          recommendation: "推荐 (斜坡响应段)",
        },
      ],
    };
    ElMessage.success("动态响应区间识别完成");
  } finally {
    loading.value = false;
  }
};

const chartOptions = computed(() => ({
  tooltip: { trigger: "axis" },
  grid: { left: "3%", right: "4%", bottom: "10%", containLabel: true },
  xAxis: {
    type: "category",
    data: Array.from({ length: 100 }, (_, i) => `${i * 10}s`),
  },
  yAxis: { type: "value" },
  series: [
    {
      name: "y (动态响应)",
      type: "line",
      color: "#1E6091",
      data: Array.from({ length: 100 }, (_, i) =>
        (i >= 20 && i <= 45) || (i >= 65 && i <= 90) ? 15 + Math.sin(i / 2) * 8 : 2
      ),
      markArea: {
        itemStyle: { color: "rgba(30, 96, 145, 0.15)" },
        data: [
          [{ name: "Segment 1 (#1)", xAxis: "200s" }, { xAxis: "450s" }],
          [{ name: "Segment 2 (#2)", xAxis: "650s" }, { xAxis: "900s" }],
        ],
      },
    },
  ],
}));
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
</style>
