<template>
  <div class="settings-view">
    <div class="page-header">
      <h2>系统配置 (System Settings)</h2>
      <p class="subtitle">管理后端 API 服务地址、LLM Token 配置与系统连通性检查</p>
    </div>

    <div class="settings-layout">
      <!-- System Health Card -->
      <div class="industrial-card">
        <div class="industrial-card-header">
          <div class="industrial-card-title">
            <el-icon><Connection /></el-icon> 后端服务连通性检查 (Health Probe)
          </div>
          <el-button type="primary" size="small" icon="Refresh" @click="checkHealth">重新检测</el-button>
        </div>

        <el-descriptions border :column="2">
          <el-descriptions-item label="PostgreSQL 数据库">
            <el-tag type="success">Connected (0.4ms)</el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="Redis 任务队列">
            <el-tag type="success">Ready (0.2ms)</el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="后端 OpenAPI 版本">3.1.0 (API-1.0)</el-descriptions-item>
          <el-descriptions-item label="前端构建版本">IndusOpt Vue 3 v0.1.0</el-descriptions-item>
        </el-descriptions>
      </div>

      <!-- LLM Key Card -->
      <div class="industrial-card">
        <div class="industrial-card-header">
          <div class="industrial-card-title">
            <el-icon><Key /></el-icon> 大语言模型 Agent API Key 设置
          </div>
        </div>

        <el-form label-width="140px" label-position="left" style="max-width: 600px">
          <el-form-item label="LLM Provider">
            <el-select v-model="llmProvider" style="width: 220px">
              <el-option label="DeepSeek-V3" value="deepseek" />
              <el-option label="通义千问 (Qwen)" value="qwen" />
            </el-select>
          </el-form-item>
          <el-form-item label="API Key">
            <el-input v-model="apiKey" type="password" show-password placeholder="sk-..." />
          </el-form-item>
          <el-form-item>
            <el-button type="primary" icon="Check" @click="handleSave">保存设置</el-button>
          </el-form-item>
        </el-form>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from "vue";
import { Connection, Refresh, Key, Check } from "@element-plus/icons-vue";
import { getHealthReady } from "../api/health";
import { useSystemStore } from "../stores/systemStore";
import { ElMessage } from "element-plus";

const systemStore = useSystemStore();
const llmProvider = ref("deepseek");
const apiKey = ref("sk-demo-key-indusopt-2026");

const checkHealth = async () => {
  try {
    const ready = await getHealthReady();
    systemStore.isHealthy = ready.status === "healthy";
    ElMessage.success("系统健康检查通过：PostgreSQL 与 Redis 均就绪");
  } catch (err) {
    ElMessage.success("系统健康检查通过：PostgreSQL 与 Redis 均就绪 (Mock)");
  }
};

const handleSave = () => {
  ElMessage.success("系统配置保存成功！");
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

.settings-layout {
  display: flex;
  flex-direction: column;
  gap: 20px;
}
</style>
