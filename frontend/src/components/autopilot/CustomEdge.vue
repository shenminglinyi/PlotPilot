<template>
  <BaseEdge v-bind="props" :style="edgeStyle" />
  <path v-if="isActive" class="edge-flow-dot" :d="pathData" />
  <g v-if="conditionLabel" class="edge-label">
    <text
      :x="labelPos.x"
      :y="labelPos.y"
      class="edge-label-text"
      text-anchor="middle"
      dominant-baseline="middle"
    >
      {{ conditionLabel }}
    </text>
  </g>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { BaseEdge, getBezierPath } from '@vue-flow/core'
import type { EdgeProps } from '@vue-flow/core'

const props = defineProps<EdgeProps>()

const isActive = computed(() => props.data?.isActive)

const conditionLabel = computed(() => {
  const condition = props.data?.condition
  if (!condition || condition === 'always') return ''
  const labels: Record<string, string> = {
    on_success: '✅',
    on_error: '❌',
    on_drift_alert: '⚡文风偏离',
    on_no_drift: '✅文风正常',
    on_breaker_open: '🔴熔断',
    on_breaker_closed: '🟢正常',
    on_review_approved: '✅审批通过',
    on_review_rejected: '❌审批拒绝',
  }
  return labels[condition] || condition
})

const edgeStyle = computed(() => ({
  stroke: props.data?.condition && props.data.condition !== 'always' ? '#94a3b8' : '#555',
  strokeWidth: isActive.value ? 2 : 1,
}))

const pathData = computed(() => {
  const [path] = getBezierPath({
    sourceX: props.sourceX,
    sourceY: props.sourceY,
    sourcePosition: props.sourcePosition,
    targetX: props.targetX,
    targetY: props.targetY,
    targetPosition: props.targetPosition,
  })
  return path
})

const labelPos = computed(() => ({
  x: (props.sourceX + props.targetX) / 2,
  y: (props.sourceY + props.targetY) / 2,
}))
</script>

<style scoped>
.edge-flow-dot {
  fill: none;
  stroke: #3b82f6;
  stroke-width: 3;
  stroke-dasharray: 8 4;
  animation: flow-dash 1s linear infinite;
  opacity: 0.7;
}

.edge-label-text {
  font-size: 10px;
  fill: #94a3b8;
  pointer-events: none;
}

@keyframes flow-dash {
  to {
    stroke-dashoffset: -12;
  }
}
</style>
