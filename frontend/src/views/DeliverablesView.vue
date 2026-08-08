<template>
  <div class="deliverables-view">
    <div class="page-header">
      <h2>报告生成与数据交付</h2>
      <p class="subtitle">
        报告中的每一个数值都由运行记录解析而来；大模型只负责组织语言，不产生任何数字
      </p>
    </div>

    <div class="deliverables-layout">
      <div class="industrial-card">
        <div class="industrial-card-header">
          <div class="industrial-card-title">
            <el-icon><Document /></el-icon> 交付参数
          </div>
        </div>

        <el-form :inline="true" :model="form" label-width="110px">
          <el-form-item label="数据版本 ID">
            <el-input v-model="form.version_id" placeholder="version_id" style="width: 320px" />
          </el-form-item>
          <el-form-item label="寻优任务 ID">
            <el-input v-model="studyId" placeholder="可选" style="width: 320px" />
          </el-form-item>
          <el-form-item label="输入变量">
            <el-input v-model="inputColumnsText" placeholder="u1,u2" style="width: 180px" />
          </el-form-item>
          <el-form-item label="输出变量">
            <el-input v-model="outputColumn" placeholder="y" style="width: 110px" />
          </el-form-item>
          <el-form-item>
            <el-button
              type="primary"
              :loading="reporting"
              icon="Document"
              @click="handleReport"
            >
              生成图文报告
            </el-button>
            <el-button
              type="success"
              :loading="exporting"
              icon="Download"
              @click="handleExport"
            >
              导出优选数据集
            </el-button>
          </el-form-item>
        </el-form>

        <el-alert v-if="errorMessage" type="error" :closable="false" show-icon class="alert-gap">
          <template #title>{{ errorMessage }}</template>
        </el-alert>
      </div>

      <div class="industrial-card" v-if="exportResult">
        <div class="industrial-card-header">
          <div class="industrial-card-title">
            <el-icon><Download /></el-icon> 优选数据集
          </div>
          <el-tag type="success">
            {{ exportResult.exported_rows }} / {{ exportResult.source_rows }} 行
          </el-tag>
        </div>
        <el-descriptions border :column="3" size="small">
          <el-descriptions-item label="采样占比">
            {{ (exportResult.coverage_ratio * 100).toFixed(2) }}%
          </el-descriptions-item>
          <el-descriptions-item label="CSV 路径">
            <span class="code-inline">{{ exportResult.csv_uri }}</span>
          </el-descriptions-item>
          <el-descriptions-item label="溯源清单">
            <span class="code-inline">{{ exportResult.manifest_uri }}</span>
          </el-descriptions-item>
          <el-descriptions-item label="导出列" :span="3">
            <span class="code-inline">{{ exportResult.columns.join(", ") }}</span>
          </el-descriptions-item>
        </el-descriptions>
      </div>

      <template v-if="report">
        <div class="industrial-card">
          <div class="industrial-card-header">
            <div class="industrial-card-title">
              <el-icon><Finished /></el-icon> 数值溯源
            </div>
            <el-tag :type="report.fully_resolved ? 'success' : 'warning'">
              {{ report.bindings.length }} 个数值已绑定运行记录
              {{ report.fully_resolved ? "" : `，${report.unresolved.length} 个未解析` }}
            </el-tag>
          </div>
          <el-alert type="info" :closable="false" class="alert-gap">
            <template #title>
              报告草稿中禁止出现任何未绑定的数字字面量；校验不通过将拒绝渲染并要求重新生成。
              下表列出了报告里每个数字的来源运行记录与字段路径。
            </template>
          </el-alert>
          <el-table :data="report.bindings" stripe height="300" style="width: 100%">
            <el-table-column label="占位符" width="330">
              <template #default="{ row }">
                <span class="code-inline">{{ row.placeholder }}</span>
              </template>
            </el-table-column>
            <el-table-column prop="run_id" label="来源运行" width="120" />
            <el-table-column prop="path" label="字段路径" />
            <el-table-column label="解析值" width="180">
              <template #default="{ row }">
                <span class="fit-val">{{ row.value }}</span>
              </template>
            </el-table-column>
          </el-table>
        </div>

        <div class="industrial-card">
          <div class="industrial-card-header">
            <div class="industrial-card-title">
              <el-icon><Printer /></el-icon> {{ report.title }}
            </div>
            <el-tag type="info">引用运行记录 {{ report.cited_runs.length }} 条</el-tag>
          </div>
          <div class="report-content">
            <section v-for="section in report.sections" :key="section.key">
              <h4>{{ section.title }}</h4>
              <p>{{ resolvedBody(section.body) }}</p>
            </section>
          </div>
          <p class="artifact-path" v-if="report.artifact_uri">
            报告文件：<span class="code-inline">{{ report.artifact_uri }}</span>
          </p>
        </div>
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref } from "vue";
import { Document, Download, Finished, Printer } from "@element-plus/icons-vue";
import { exportDataset, generateReport } from "../api/delivery";
import type { ExportDatasetResponse, ReportRequest, ReportResponse } from "../types/api";
import { ApiError } from "../api/client";
import { ElMessage } from "element-plus";

const reporting = ref(false);
const exporting = ref(false);
const errorMessage = ref("");
const report = ref<ReportResponse | null>(null);
const exportResult = ref<ExportDatasetResponse | null>(null);
const studyId = ref("");
const inputColumnsText = ref("u1,u2");
const outputColumn = ref("y");

const form = reactive<ReportRequest>({ version_id: "" });

const handleReport = async () => {
  errorMessage.value = "";
  if (!form.version_id) {
    errorMessage.value = "请先填写数据版本 ID。";
    return;
  }
  reporting.value = true;
  try {
    report.value = await generateReport({
      version_id: form.version_id,
      study_id: studyId.value || null,
    });
    ElMessage.success(`报告已生成，${report.value.bindings.length} 个数值完成溯源`);
  } catch (err) {
    report.value = null;
    errorMessage.value = err instanceof ApiError ? err.message : String(err);
  } finally {
    reporting.value = false;
  }
};

const handleExport = async () => {
  errorMessage.value = "";
  if (!form.version_id) {
    errorMessage.value = "请先填写数据版本 ID。";
    return;
  }
  exporting.value = true;
  try {
    exportResult.value = await exportDataset({
      version_id: form.version_id,
      input_columns: inputColumnsText.value
        .split(",")
        .map((name) => name.trim())
        .filter(Boolean),
      output_column: outputColumn.value || null,
    });
    ElMessage.success(`已导出 ${exportResult.value.exported_rows} 行优选数据`);
  } catch (err) {
    exportResult.value = null;
    errorMessage.value = err instanceof ApiError ? err.message : String(err);
  } finally {
    exporting.value = false;
  }
};

/** The API returns the already-rendered markdown; sections keep their template form. */
const resolvedBody = (body: string) => {
  if (!report.value) return body;
  let text = body;
  for (const binding of report.value.bindings) {
    text = text.split(binding.placeholder).join(binding.value);
  }
  return text;
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

.deliverables-layout {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.alert-gap {
  margin: 12px 0;
}

.report-content {
  line-height: 1.8;
  color: var(--text-primary);
}

.report-content h4 {
  margin: 16px 0 6px;
  color: var(--color-primary);
}

.fit-val {
  font-weight: 600;
  color: var(--color-primary);
  font-family: var(--font-mono);
}

.artifact-path {
  margin-top: 14px;
  font-size: 12px;
  color: var(--text-secondary);
}
</style>
