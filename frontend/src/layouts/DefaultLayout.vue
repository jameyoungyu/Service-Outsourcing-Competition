<template>
  <div class="default-layout">
    <AppHeader @toggle-copilot="isCopilotOpen = !isCopilotOpen" />

    <div class="layout-body">
      <AppSidebar />

      <main class="layout-main">
        <router-view />
      </main>

      <!-- Copilot Drawer -->
      <el-drawer
        v-model="isCopilotOpen"
        title="Agent 智能工作台 Copilot"
        direction="rtl"
        size="420px"
        :with-header="true"
      >
        <CopilotView />
      </el-drawer>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from "vue";
import AppHeader from "../components/AppHeader.vue";
import AppSidebar from "../components/AppSidebar.vue";
import CopilotView from "../views/CopilotView.vue";

const isCopilotOpen = ref(false);
</script>

<style scoped>
.default-layout {
  display: flex;
  flex-direction: column;
  height: 100vh;
  width: 100vw;
  overflow: hidden;
}

.layout-body {
  display: flex;
  flex: 1;
  overflow: hidden;
}

.layout-main {
  flex: 1;
  padding: 20px;
  overflow-y: auto;
  background-color: var(--bg-app);
}
</style>
