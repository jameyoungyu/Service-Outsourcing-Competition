<template>
  <div class="chart-wrapper">
    <div ref="chartRef" class="chart-canvas" :style="{ height: height || '350px' }"></div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount, watch } from "vue";
import * as echarts from "echarts";

const props = defineProps<{
  options: echarts.EChartsOption;
  height?: string;
}>();

const chartRef = ref<HTMLDivElement | null>(null);
let chartInstance: echarts.ECharts | null = null;

const initChart = () => {
  if (!chartRef.value) return;
  chartInstance = echarts.init(chartRef.value);
  chartInstance.setOption(props.options);
};

const handleResize = () => {
  chartInstance?.resize();
};

watch(
  () => props.options,
  (newOpt) => {
    chartInstance?.setOption(newOpt, true);
  },
  { deep: true }
);

onMounted(() => {
  initChart();
  window.addEventListener("resize", handleResize);
});

onBeforeUnmount(() => {
  window.removeEventListener("resize", handleResize);
  chartInstance?.dispose();
});
</script>

<style scoped>
.chart-wrapper {
  width: 100%;
}
.chart-canvas {
  width: 100%;
}
</style>
