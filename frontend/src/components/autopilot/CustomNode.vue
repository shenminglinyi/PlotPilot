<template>
  <div
    class="dag-custom-node"
    :class="[statusClass, { 'node-selected': data.isSelected }]"
    @contextmenu.prevent="$emit('contextmenu', $event)"
  >
    <!-- 头部：图标 + 名称 + 状态徽章 -->
    <div class="node-header" :style="{ borderColor: categoryColor }">
      <span class="node-icon">{{ meta?.icon || '📦' }}</span>
      <span class="node-label">{{ data.label || meta?.display_name || data.id }}</span>
      <n-tag size="tiny" :type="statusTagType" round>{{ statusLabel }}</n-tag>
      <n-tag v-if="!data.enabled" size="tiny" type="default" round>禁用</n-tag>
    </div>

    <!-- 主体：节点类型特化渲染 -->
    <div class="node-body">
      <!-- 运行中：进度指示 -->
      <div v-if="isRunning" class="node-running-indicator">
        <n-spin :size="14" />
        <span class="running-text">执行中...</span>
        <div v-if="runState?.progress > 0" class="progress-bar">
          <div class="progress-fill" :style="{ width: `${runState.progress * 100}%` }" />
        </div>
      </div>

      <!-- 指标展示 -->
      <div v-else-if="displayMetrics.length > 0" class="node-metrics">
        <div v-for="m in displayMetrics" :key="m.key" class="metric-item">
          <span class="metric-key">{{ m.label }}</span>
          <span class="metric-value" :style="{ color: m.color }">{{ m.value }}</span>
        </div>
      </div>

      <!-- 默认：类型描述 -->
      <div v-else class="node-desc">
        <n-text depth="3" style="font-size: 11px">{{ meta?.display_name || data.type }}</n-text>
      </div>
    </div>

    <!-- 输入/输出端口 -->
    <div class="node-ports">
      <Handle
        v-for="port in meta?.input_ports"
        :key="`in-${port.name}`"
        type="target"
        :position="Position.Left"
        :id="port.name"
        :style="portStyle(port.data_type)"
      />
      <Handle
        v-for="port in meta?.output_ports"
        :key="`out-${port.name}`"
        type="source"
        :position="Position.Right"
        :id="port.name"
        :style="portStyle(port.data_type)"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { Handle, Position } from '@vue-flow/core'
import type { NodeProps } from '@vue-flow/core'
import { useDAGStore } from '@/stores/dagStore'
import type { NodeMeta, NodeStatus, PortDataType } from '@/types/dag'
import {
  STATUS_COLORS,
  STATUS_BG_COLORS,
  STATUS_LABELS,
  CATEGORY_COLORS,
} from '@/types/dag'

const props = defineProps<NodeProps>()

const dagStore = useDAGStore()

// ─── 计算属性 ───

const data = computed(() => props.data as {
  id: string
  type: string
  label: string
  enabled: boolean
  runState?: { status: NodeStatus; metrics: Record<string, number>; progress: number; duration_ms: number }
  isEditing: boolean
  isSelected: boolean
  [key: string]: unknown
})

const meta = computed((): NodeMeta | null => {
  const nodeType = data.value.type
  return dagStore.nodeTypeRegistry[nodeType] || null
})

const runState = computed(() => data.value.runState)

const status = computed((): NodeStatus => {
  if (!data.value.enabled) return 'disabled'
  return runState.value?.status || 'idle'
})

const isRunning = computed(() => status.value === 'running')

const statusClass = computed(() => `node-${status.value}`)

const statusLabel = computed(() => STATUS_LABELS[status.value] || status.value)

const statusTagType = computed(() => {
  const map: Record<string, 'default' | 'info' | 'success' | 'warning' | 'error'> = {
    idle: 'default',
    pending: 'default',
    running: 'info',
    success: 'success',
    warning: 'warning',
    error: 'error',
    bypassed: 'default',
    disabled: 'default',
    completed: 'success',
  }
  return map[status.value] || 'default'
})

const categoryColor = computed(() => {
  const cat = meta.value?.category
  return cat ? CATEGORY_COLORS[cat] : '#6366f1'
})

// ─── 指标展示 ───

const displayMetrics = computed(() => {
  if (!runState.value?.metrics) return []
  const metrics = runState.value.metrics
  const items: { key: string; label: string; value: string; color: string }[] = []

  // 根据节点类型选择展示的指标
  const type = data.value.type
  if (type === 'val_style') {
    if (metrics.drift_score !== undefined) {
      items.push({
        key: 'drift_score',
        label: '偏离度',
        value: metrics.drift_score.toFixed(2),
        color: metrics.drift_score > 0.5 ? '#f59e0b' : '#22c55e',
      })
    }
  } else if (type === 'val_tension') {
    if (metrics.composite !== undefined) {
      items.push({
        key: 'composite',
        label: '综合张力',
        value: metrics.composite.toFixed(0),
        color: metrics.composite < 30 ? '#f59e0b' : '#22c55e',
      })
    }
  } else if (type === 'val_anti_ai') {
    if (metrics.severity_score !== undefined) {
      items.push({
        key: 'severity_score',
        label: 'AI味',
        value: metrics.severity_score.toFixed(1),
        color: metrics.severity_score > 5 ? '#ef4444' : '#22c55e',
      })
    }
  } else if (type === 'exec_writer') {
    if (metrics.word_count !== undefined) {
      items.push({
        key: 'word_count',
        label: '字数',
        value: String(Math.round(metrics.word_count)),
        color: '#3b82f6',
      })
    }
  }

  // 通用：显示耗时
  if (runState.value.duration_ms > 0) {
    items.push({
      key: 'duration',
      label: '耗时',
      value: runState.value.duration_ms > 1000
        ? `${(runState.value.duration_ms / 1000).toFixed(1)}s`
        : `${runState.value.duration_ms}ms`,
      color: '#94a3b8',
    })
  }

  return items.slice(0, 3) // 最多展示3个指标
})

// ─── 端口样式 ───

function portStyle(dataType: PortDataType) {
  const colors: Record<string, string> = {
    text: '#3b82f6',
    json: '#8b5cf6',
    score: '#f59e0b',
    boolean: '#22c55e',
    list: '#ec4899',
    prompt: '#6366f1',
  }
  return {
    background: colors[dataType] || '#94a3b8',
    width: '8px',
    height: '8px',
    border: '2px solid var(--n-color, #1a1a2e)',
  }
}
</script>

<style scoped>
.dag-custom-node {
  min-width: 160px;
  max-width: 220px;
  border-radius: 8px;
  border: 2px solid #94a3b8;
  background: var(--n-color, #1e1e2e);
  font-size: 12px;
  transition: border-color 0.3s, box-shadow 0.3s;
  position: relative;
}

.dag-custom-node.node-selected {
  box-shadow: 0 0 0 2px #3b82f6;
}

.dag-custom-node.node-running {
  border-color: #3b82f6;
  background: rgba(59,130,246,0.08);
  animation: pulse-border 2s ease-in-out infinite;
}

.dag-custom-node.node-success {
  border-color: #22c55e;
  background: rgba(34,197,94,0.06);
}

.dag-custom-node.node-warning {
  border-color: #f59e0b;
  background: rgba(245,158,11,0.06);
}

.dag-custom-node.node-error {
  border-color: #ef4444;
  background: rgba(239,68,68,0.08);
  animation: blink-border 1s ease-in-out infinite;
}

.dag-custom-node.node-bypassed {
  border-color: #6b7280;
  border-style: dashed;
  background: rgba(107,114,128,0.04);
}

.dag-custom-node.node-disabled {
  border-color: #d1d5db;
  background: rgba(209,213,219,0.04);
  opacity: 0.6;
}

.node-header {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 10px;
  border-bottom: 1px solid rgba(255,255,255,0.06);
  border-top: 3px solid;
}

.node-icon {
  font-size: 14px;
}

.node-label {
  flex: 1;
  font-weight: 600;
  font-size: 12px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.node-body {
  padding: 6px 10px;
  min-height: 24px;
}

.node-running-indicator {
  display: flex;
  align-items: center;
  gap: 6px;
}

.running-text {
  font-size: 11px;
  color: #3b82f6;
}

.progress-bar {
  flex: 1;
  height: 3px;
  background: rgba(59,130,246,0.2);
  border-radius: 2px;
  overflow: hidden;
}

.progress-fill {
  height: 100%;
  background: #3b82f6;
  border-radius: 2px;
  transition: width 0.3s;
}

.node-metrics {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.metric-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 11px;
}

.metric-key {
  color: #94a3b8;
}

.metric-value {
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}

.node-desc {
  padding: 2px 0;
}

.node-ports {
  position: relative;
}

@keyframes pulse-border {
  0%, 100% { border-color: #3b82f6; }
  50% { border-color: rgba(59,130,246,0.4); }
}

@keyframes blink-border {
  0%, 100% { border-color: #ef4444; }
  50% { border-color: rgba(239,68,68,0.3); }
}
</style>
