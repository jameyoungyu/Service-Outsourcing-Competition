<template>
  <div class="datasets-view">
    <div class="page-header">
      <h2>数据资产 Hub (Dataset Management)</h2>
      <p class="subtitle">管理真实上传的工业 CSV、配置列角色并查看关联数据版本</p>
    </div>

    <!-- Upload Card -->
    <div class="industrial-card">
      <div class="industrial-card-header">
        <div class="industrial-card-title">
          <el-icon><Upload /></el-icon> 上传本地工业 CSV 数据文件
        </div>
      </div>
      <el-upload
        class="upload-area"
        drag
        action="#"
        :http-request="customUpload"
        :show-file-list="false"
      >
        <el-icon class="el-icon--upload"><upload-filled /></el-icon>
        <div class="el-upload__text">
          拖拽 CSV 文件到此处或 <em>点击上传</em>
        </div>
        <template #tip>
          <div class="el-upload__tip">
            支持最大 100MB 工业 CSV 文件 (自动识别 UTF-8 / GBK / GB2312 编码与逗号/分号/Tab 分隔符)
          </div>
        </template>
      </el-upload>
    </div>

    <!-- Datasets Table -->
    <div class="industrial-card">
      <div class="industrial-card-header">
        <div class="industrial-card-title">
          <el-icon><List /></el-icon> 数据库已登记数据集列表
        </div>
        <el-button type="primary" size="small" icon="Refresh" @click="fetchDatasets">刷新列表</el-button>
      </div>

      <el-table :data="datasetList" stripe style="width: 100%" v-loading="loading">
        <el-table-column prop="name" label="数据集名称" width="200" />
        <el-table-column prop="version_id" label="激活版本" width="140">
          <template #default="{ row }">
            <span class="code-inline">{{ row.version_id || row.latest_version_id }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="row_count" label="样本行数" width="130" />
        <el-table-column label="列规模" width="100">
          <template #default="{ row }">
            {{ row.col_count || row.column_count }} 列
          </template>
        </el-table-column>
        <el-table-column prop="time_column" label="时间列" width="120">
          <template #default="{ row }">
            <span v-if="row.time_column">{{ row.time_column }}</span>
            <el-tag v-else type="info" size="small">未配置</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="输入/输出变量角色">
          <template #default="{ row }">
            <span v-if="row.input_columns && row.input_columns.length > 0" class="badge-primary industrial-badge">
              In: {{ row.input_columns.join(",") }}
            </span>
            <span v-else class="industrial-badge" style="background: #edf2f7; color: #718096">In: 待配置</span>

            <span v-if="row.output_column" class="badge-success industrial-badge" style="margin-left: 6px">
              Out: {{ row.output_column }}
            </span>
            <span v-else class="industrial-badge" style="margin-left: 6px; background: #edf2f7; color: #718096">Out: 待配置</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="240">
          <template #default="{ row }">
            <el-button type="primary" text size="small" @click="handleSelectDataset(row)">查看诊断</el-button>
            <el-button type="warning" text size="small" @click="openConfigDialog(row)">列配置</el-button>
            <el-button type="danger" text size="small" @click="handleDelete(row.id)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- Column Config Dialog -->
    <el-dialog v-model="configDialogVisible" title="配置数据集列角色 (Schema Mapping)" width="500px">
      <el-form label-width="120px">
        <el-form-item label="时间戳列 (Time)">
          <el-input v-model="configForm.time_column" placeholder="例如: timestamp" />
        </el-form-item>
        <el-form-item label="输入变量 (Inputs)">
          <el-input v-model="configForm.input_columns_str" placeholder="多个以逗号分隔, 如: u1,u2" />
        </el-form-item>
        <el-form-item label="目标输出 (Output)">
          <el-input v-model="configForm.output_column" placeholder="例如: y" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="configDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="configLoading" @click="saveConfig">保存配置</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from "vue";
import { Upload, List, UploadFilled, Refresh } from "@element-plus/icons-vue";
import { useDatasetStore } from "../stores/datasetStore";
import { getDatasets, deleteDataset, uploadDataset, configureDataset } from "../api/datasets";
import type { DatasetItem } from "../types/api";
import { useRouter } from "vue-router";
import { ElMessage } from "element-plus";

const datasetStore = useDatasetStore();
const router = useRouter();

const loading = ref(false);
const datasetList = ref<DatasetItem[]>([]);

const configDialogVisible = ref(false);
const configLoading = ref(false);
const currentDataset = ref<DatasetItem | null>(null);
const configForm = reactive({
  time_column: "timestamp",
  input_columns_str: "u1,u2",
  output_column: "y",
});

const fetchDatasets = async () => {
  loading.value = true;
  try {
    const res = await getDatasets();
    datasetList.value = res.items || [];
    datasetStore.setDatasetsList(datasetList.value);
  } catch (err: any) {
    ElMessage.error(`获取数据集列表失败 [${err.code || 'ERR'}]: ${err.message}`);
  } finally {
    loading.value = false;
  }
};

const customUpload = async (options: any) => {
  try {
    const res = await uploadDataset(options.file, options.file.name);
    if (res.deduplicated) {
      ElMessage.info(`系统匹配到已存在的相同哈希文件，快速关联数据集: ${res.dataset.name}`);
    } else {
      ElMessage.success(`数据集 ${res.dataset.name} 真实上传并解析成功！`);
    }
    fetchDatasets();
  } catch (err: any) {
    ElMessage.error(`上传失败 [${err.code || 'ERR'}]: ${err.message}`);
  }
};

const handleSelectDataset = (row: DatasetItem) => {
  datasetStore.setActiveDataset(row);
  router.push(`/datasets/${row.id}`);
};

const openConfigDialog = (row: DatasetItem) => {
  currentDataset.value = row;
  configForm.time_column = row.time_column || "timestamp";
  configForm.input_columns_str = (row.input_columns || ["u1", "u2"]).join(",");
  configForm.output_column = row.output_column || "y";
  configDialogVisible.value = true;
};

const saveConfig = async () => {
  if (!currentDataset.value) return;
  configLoading.value = true;
  try {
    const inputCols = configForm.input_columns_str.split(",").map((s) => s.trim()).filter(Boolean);
    await configureDataset(currentDataset.value.id, {
      time_column: configForm.time_column,
      input_columns: inputCols,
      output_column: configForm.output_column,
    });
    ElMessage.success("列角色配置保存成功！");
    configDialogVisible.value = false;
    fetchDatasets();
  } catch (err: any) {
    ElMessage.error(`配置保存失败 [${err.code || 'ERR'}]: ${err.message}`);
  } finally {
    configLoading.value = false;
  }
};

const handleDelete = async (id: string) => {
  try {
    await deleteDataset(id);
    ElMessage.success("数据集删除成功");
    fetchDatasets();
  } catch (err: any) {
    ElMessage.error(`删除失败 [${err.code || 'ERR'}]: ${err.message}`);
  }
};

onMounted(() => {
  fetchDatasets();
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

.upload-area {
  width: 100%;
}
</style>
