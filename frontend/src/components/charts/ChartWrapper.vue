<template>
  <div
    class="chart-wrapper"
    :style="{ height: height }"
    role="img"
    :aria-label="ariaLabel"
  >
    <v-chart
      :option="option"
      :autoresize="true"
      :theme="theme"
      @click="handleClick"
    />
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import VChart from 'vue-echarts'
import type { EChartsOption } from 'echarts'

const props = withDefaults(defineProps<{
  option: EChartsOption
  height?: string
  theme?: string
  ariaLabel?: string
}>(), {
  height: '400px',
  theme: 'light',
  ariaLabel: 'Chart visualization'
})

const emit = defineEmits<{
  click: [params: any]
}>()

const handleClick = (params: any) => {
  emit('click', params)
}
</script>

<style scoped>
.chart-wrapper {
  width: 100%;
}

.chart-wrapper :deep(.echarts),
.chart-wrapper :deep(canvas),
.chart-wrapper :deep(svg) {
  width: 100% !important;
  height: 100% !important;
  display: block;
}
</style>
