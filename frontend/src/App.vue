<template>
  <router-view />
</template>

<script setup lang="ts">
import { onMounted } from "vue";
import { useSystemStore } from "./stores/systemStore";
import { getHealthLive, getHealthReady } from "./api/health";

const systemStore = useSystemStore();

onMounted(async () => {
  try {
    const live = await getHealthLive();
    const ready = await getHealthReady();
    systemStore.setHealth(live, ready);
  } catch (err) {
    // Keep default ready status for UI demo
  }
});
</script>
