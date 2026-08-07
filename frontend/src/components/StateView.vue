<template>
  <div class="state-view-container">
    <!-- Initial Empty State -->
    <div v-if="state === 'empty'" class="state-box empty">
      <el-empty :description="description || '暂无可展示的数据'">
        <slot name="empty-actions">
          <el-button type="primary" @click="$emit('action')">创建/生成数据</el-button>
        </slot>
      </el-empty>
    </div>

    <!-- Loading / Parsing / Queued / Running States -->
    <div v-else-if="['loading', 'parsing', 'queued', 'running'].includes(state)" class="state-box loading">
      <el-icon class="is-loading spin-icon"><Loading /></el-icon>
      <div class="state-title">{{ title || defaultTitle }}</div>
      <div class="state-desc">{{ description || defaultDesc }}</div>
      <el-progress
        v-if="progress !== undefined"
        :percentage="progress"
        :status="state === 'running' ? '' : 'warning'"
        style="width: 300px; margin-top: 12px"
      />
      <el-button v-if="canCancel" type="info" text size="small" style="margin-top: 12px" @click="$emit('cancel')">
        取消操作
      </el-button>
    </div>

    <!-- HITL Waiting Confirmation State -->
    <div v-else-if="state === 'hitl_wait'" class="state-box hitl">
      <el-alert
        title="需要人工确认 (Human-in-the-Loop)"
        type="warning"
        :closable="false"
        show-icon
      >
        <template #default>
          <div class="hitl-content">
            <p class="desc">{{ description || 'Agent 触发高影响数据操作，请审查依据并确认：' }}</p>
            <div v-if="impactSummary" class="impact-box">
              <span class="label">预计影响:</span> {{ impactSummary }}
            </div>
            <div class="hitl-actions">
              <el-button type="success" size="small" @click="$emit('approve')">批准并继续</el-button>
              <el-button type="danger" size="small" text @click="$emit('reject')">拒绝/保留原状</el-button>
            </div>
          </div>
        </template>
      </el-alert>
    </div>

    <!-- Failure / Error State -->
    <div v-else-if="state === 'failure'" class="state-box failure">
      <el-result icon="error" :title="title || '处理失败'" :sub-title="description || '发生未预期的算法或数据错误'">
        <template #extra>
          <div class="error-code" v-if="errorCode">错误代码: {{ errorCode }}</div>
          <el-button type="primary" size="small" @click="$emit('retry')">重试</el-button>
          <el-button size="small" @click="$emit('rollback')">撤销并回退</el-button>
        </template>
      </el-result>
    </div>

    <!-- Default Content when state is success / normal -->
    <div v-else class="content-box">
      <slot></slot>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue";
import { Loading } from "@element-plus/icons-vue";

const props = defineProps<{
  state?: "empty" | "loading" | "parsing" | "config_error" | "queued" | "running" | "partial_success" | "hitl_wait" | "success" | "failure" | "cancelled" | "oversized" | "normal";
  title?: string;
  description?: string;
  progress?: number;
  canCancel?: boolean;
  errorCode?: string;
  impactSummary?: string;
}>();

defineEmits(["action", "cancel", "approve", "reject", "retry", "rollback"]);

const defaultTitle = computed(() => {
  switch (props.state) {
    case "loading": return "正在加载数据...";
    case "parsing": return "正在解析 CSV / 时间戳对齐...";
    case "queued": return "正在任务队列中排队...";
    case "running": return "算法正在计算中...";
    default: return "处理中...";
  }
});

const defaultDesc = computed(() => {
  switch (props.state) {
    case "parsing": return "正在识别文件编码、分隔符与缺失行";
    case "queued": return "前面尚有任务运行，请稍候";
    case "running": return "正在执行 Optuna / 工业预处理工具";
    default: return "请耐心等待后台响应";
  }
});
</script>

<style scoped>
.state-view-container {
  width: 100%;
}

.state-box {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 40px 20px;
  background: var(--bg-surface);
  border: 1px solid var(--border-light);
  border-radius: 6px;
}

.spin-icon {
  font-size: 36px;
  color: var(--color-primary);
  margin-bottom: 12px;
}

.state-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 6px;
}

.state-desc {
  font-size: 13px;
  color: var(--text-secondary);
}

.hitl-content {
  margin-top: 8px;
}

.impact-box {
  background: rgba(233, 196, 106, 0.15);
  padding: 6px 10px;
  border-radius: 4px;
  font-size: 13px;
  margin: 8px 0;
  font-family: var(--font-mono);
}

.hitl-actions {
  display: flex;
  gap: 12px;
  margin-top: 10px;
}

.error-code {
  font-family: var(--font-mono);
  font-size: 12px;
  color: var(--color-danger);
  margin-bottom: 12px;
}
</style>
