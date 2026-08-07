<template>
  <div class="copilot-view">
    <div class="chat-history">
      <div v-for="(msg, idx) in messages" :key="idx" class="msg-bubble" :class="msg.sender">
        <div class="sender-name">{{ msg.sender === 'user' ? '用户' : 'Agent Copilot' }}</div>
        <div class="msg-text">{{ msg.text }}</div>

        <!-- Plan DAG Nodes Card if present -->
        <div v-if="msg.planNodes && msg.planNodes.length > 0" class="plan-dag-card">
          <div class="dag-header">🎯 Agent 编排执行计划 DAG (5 节点)</div>
          <div class="node-list">
            <div v-for="node in msg.planNodes" :key="node.step_id" class="node-item" :class="node.status">
              <span class="status-icon">
                <el-icon v-if="node.status === 'completed'"><Check /></el-icon>
                <el-icon v-else-if="node.status === 'running'"><Loading /></el-icon>
                <el-icon v-else-if="node.status === 'waiting_confirmation'"><Warning /></el-icon>
                <el-icon v-else><Clock /></el-icon>
              </span>
              <span class="node-title">{{ node.title }}</span>
              <span class="node-tool code-inline">{{ node.tool_name }}</span>
            </div>
          </div>
        </div>

        <!-- HITL Confirmation Card -->
        <div v-if="msg.hitlConfirmation" class="hitl-card">
          <StateView
            state="hitl_wait"
            description="Agent 识别出 2 个高动态区间，是否截取以丢弃稳态段?"
            impact-summary="数据量减少 45%，预计 FIT 指标提升从 42% 到 85% 以上"
            @approve="handleApprove(msg)"
            @reject="handleReject(msg)"
          />
        </div>
      </div>
    </div>

    <!-- Input Footer -->
    <div class="chat-input-area">
      <el-input
        v-model="inputPrompt"
        type="textarea"
        :rows="3"
        placeholder="例如: 对数据集 S3 提取高信噪比段，自动完成清洗与 Optuna 寻优..."
        @keyup.enter.exact="handleSend"
      />
      <div class="input-actions">
        <el-button type="primary" :loading="sending" icon="Promotion" @click="handleSend">
          发送指令给 Agent
        </el-button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from "vue";
import { Check, Loading, Warning, Clock, Promotion } from "@element-plus/icons-vue";
import StateView from "../components/StateView.vue";
import { chatWithCopilot, confirmCopilotStep } from "../api/copilot";
import type { CopilotStepNode } from "../types/api";
import { ElMessage } from "element-plus";

interface MessageItem {
  sender: "user" | "agent";
  text: string;
  planNodes?: CopilotStepNode[];
  hitlConfirmation?: boolean;
  sessionId?: string;
  stepId?: string;
}

const sending = ref(false);
const inputPrompt = ref("");
const messages = ref<MessageItem[]>([
  {
    sender: "agent",
    text: "你好！我是 IndusOpt 自主建模数据工程师 Agent。你可以用自然语言告诉我你的建模或处理需求。",
  },
]);

const handleSend = async () => {
  if (!inputPrompt.value.trim()) return;
  const userText = inputPrompt.value;
  messages.value.push({ sender: "user", text: userText });
  inputPrompt.value = "";
  sending.value = true;

  try {
    const res = await chatWithCopilot({ prompt: userText });
    messages.value.push({
      sender: "agent",
      text: res.reply_text,
      planNodes: res.plan_nodes,
      sessionId: res.session_id,
    });
  } catch (err) {
    // Mock fallback response for Phase 1 demo
    messages.value.push({
      sender: "agent",
      text: "已收到指令。我为你解析并编排了包含数据诊断、清洗、动态截取、时滞补偿和 Optuna 寻优的结构化工作流计划：",
      sessionId: "sess_demo_101",
      stepId: "step_03",
      hitlConfirmation: true,
      planNodes: [
        { step_id: "step_01", title: "1. 工业数据质量诊断", tool_name: "data_profile", status: "completed", requires_hitl: false },
        { step_id: "step_02", title: "2. Hampel 异常值清洗", tool_name: "clean_hampel", status: "completed", requires_hitl: false },
        { step_id: "step_03", title: "3. 动态响应区间筛选", tool_name: "segment_select", status: "waiting_confirmation", requires_hitl: true },
        { step_id: "step_04", title: "4. 时滞估算与补偿", tool_name: "delay_estimate", status: "pending", requires_hitl: false },
        { step_id: "step_05", title: "5. Optuna 闭环寻优", tool_name: "optuna_study", status: "pending", requires_hitl: false },
      ],
    });
  } finally {
    sending.value = false;
  }
};

const handleApprove = async (msg: MessageItem) => {
  try {
    if (msg.sessionId && msg.stepId) {
      await confirmCopilotStep({ session_id: msg.sessionId, step_id: msg.stepId, approved: true });
    }
  } catch (err) {
    // Ignore error in stub mode
  }
  msg.hitlConfirmation = false;
  if (msg.planNodes && msg.planNodes[2]) {
    msg.planNodes[2].status = "completed";
    msg.planNodes[3].status = "running";
  }
  ElMessage.success("已批准人工确认点，Agent 继续调度下一步！");
};

const handleReject = (msg: MessageItem) => {
  msg.hitlConfirmation = false;
  ElMessage.info("已拒绝截取，Agent 将在全量数据上继续处理");
};
</script>

<style scoped>
.copilot-view {
  display: flex;
  flex-direction: column;
  height: 100%;
}

.chat-history {
  flex: 1;
  overflow-y: auto;
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.msg-bubble {
  max-width: 90%;
  padding: 12px 14px;
  border-radius: 8px;
  font-size: 13px;
  line-height: 1.5;
}

.msg-bubble.user {
  align-self: flex-end;
  background: var(--color-primary);
  color: #ffffff;
}

.msg-bubble.agent {
  align-self: flex-start;
  background: var(--bg-subtle);
  border: 1px solid var(--border-light);
  color: var(--text-primary);
}

.sender-name {
  font-size: 11px;
  font-weight: 600;
  margin-bottom: 4px;
  opacity: 0.8;
}

.plan-dag-card {
  margin-top: 10px;
  background: var(--bg-surface);
  border: 1px solid var(--border-light);
  border-radius: 6px;
  padding: 10px;
}

.dag-header {
  font-weight: 600;
  font-size: 12px;
  margin-bottom: 8px;
}

.node-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.node-item {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  padding: 4px 8px;
  border-radius: 4px;
  background: var(--bg-app);
}

.node-item.completed { color: var(--color-success); }
.node-item.running { color: var(--color-primary); }
.node-item.waiting_confirmation { color: var(--color-warning-dark); font-weight: 600; }

.chat-input-area {
  padding-top: 12px;
  border-top: 1px solid var(--border-light);
}

.input-actions {
  display: flex;
  justify-content: flex-end;
  margin-top: 8px;
}
</style>
