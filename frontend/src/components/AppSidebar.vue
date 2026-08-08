<template>
  <aside class="app-sidebar" :class="{ collapsed: isCollapsed }">
    <div class="toggle-btn" @click="isCollapsed = !isCollapsed">
      <el-icon><Fold v-if="!isCollapsed" /><Expand v-else /></el-icon>
    </div>

    <el-menu
      :default-active="activePath"
      class="sidebar-menu"
      :collapse="isCollapsed"
      router
    >
      <el-menu-item index="/dashboard">
        <el-icon><Odometer /></el-icon>
        <template #title>工作台概览</template>
      </el-menu-item>

      <el-menu-item index="/simulation">
        <el-icon><Cpu /></el-icon>
        <template #title>仿真生成器</template>
      </el-menu-item>

      <el-menu-item index="/datasets">
        <el-icon><FolderOpened /></el-icon>
        <template #title>数据资产 Hub</template>
      </el-menu-item>

      <el-sub-menu index="/preprocessing">
        <template #title>
          <el-icon><Operation /></el-icon>
          <span>数据优选与规整</span>
        </template>
        <el-menu-item index="/preprocessing/cleaning">时间规整与清洗</el-menu-item>
        <el-menu-item index="/preprocessing/segmentation">动态响应区间优选</el-menu-item>
        <el-menu-item index="/preprocessing/delay">多变量时滞分析</el-menu-item>
        <el-menu-item index="/preprocessing/collinearity">共线性与变量筛选</el-menu-item>
      </el-sub-menu>

      <el-sub-menu index="/modeling">
        <template #title>
          <el-icon><TrendCharts /></el-icon>
          <span>系统辨识与闭环</span>
        </template>
        <el-menu-item index="/modeling/arx">ARX 系统辨识</el-menu-item>
        <el-menu-item index="/modeling/optimization">Optuna 闭环寻优</el-menu-item>
      </el-sub-menu>

      <el-menu-item index="/copilot">
        <el-icon><ChatDotSquare /></el-icon>
        <template #title>Agent 工作台</template>
      </el-menu-item>

      <el-menu-item index="/benchmark">
        <el-icon><Odometer /></el-icon>
        <template #title>一键自评测基准</template>
      </el-menu-item>

      <el-menu-item index="/deliverables">
        <el-icon><Document /></el-icon>
        <template #title>报告与交付中心</template>
      </el-menu-item>

      <el-menu-item index="/settings">
        <el-icon><Setting /></el-icon>
        <template #title>系统配置</template>
      </el-menu-item>
    </el-menu>
  </aside>
</template>

<script setup lang="ts">
import { ref, computed } from "vue";
import { useRoute } from "vue-router";
import {
  Odometer,
  Cpu,
  FolderOpened,
  Operation,
  TrendCharts,
  ChatDotSquare,
  Document,
  Setting,
  Fold,
  Expand,
} from "@element-plus/icons-vue";

const route = useRoute();
const isCollapsed = ref(false);

const activePath = computed(() => route.path);
</script>

<style scoped>
.app-sidebar {
  width: 220px;
  background: var(--bg-sidebar);
  transition: width 0.2s ease;
  display: flex;
  flex-direction: column;
  height: 100%;
}

.app-sidebar.collapsed {
  width: 64px;
}

.toggle-btn {
  height: 40px;
  display: flex;
  align-items: center;
  justify-content: flex-end;
  padding: 0 16px;
  color: #8d96a0;
  cursor: pointer;
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
}

.sidebar-menu {
  border-right: none;
  background: transparent;
  flex: 1;
}

:deep(.el-menu) {
  background: transparent;
}

:deep(.el-menu-item), :deep(.el-sub-menu__title) {
  color: #a0aec0;
}

:deep(.el-menu-item:hover), :deep(.el-sub-menu__title:hover) {
  background: rgba(255, 255, 255, 0.06) !important;
  color: #ffffff;
}

:deep(.el-menu-item.is-active) {
  color: #ffffff !important;
  background: var(--color-primary) !important;
  font-weight: 600;
}
</style>
