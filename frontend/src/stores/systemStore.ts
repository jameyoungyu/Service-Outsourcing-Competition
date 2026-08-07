import { defineStore } from "pinia";
import { ref } from "vue";
import type { LivenessData, ReadinessData, SystemInfoData } from "../types/api";

export const useSystemStore = defineStore("system", () => {
  const liveness = ref<LivenessData | null>(null);
  const readiness = ref<ReadinessData | null>(null);
  const systemInfo = ref<SystemInfoData | null>(null);
  const isHealthy = ref<boolean>(true);

  function setHealth(live: LivenessData, ready: ReadinessData) {
    liveness.value = live;
    readiness.value = ready;
    isHealthy.value = ready.status === "healthy";
  }

  function setSystemInfo(info: SystemInfoData) {
    systemInfo.value = info;
  }

  return {
    liveness,
    readiness,
    systemInfo,
    isHealthy,
    setHealth,
    setSystemInfo,
  };
});
