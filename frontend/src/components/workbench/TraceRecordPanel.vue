<template>
  <div class="trace-panel">
    <div class="trace-header">
      <n-text strong style="font-size: 14px">🔍 引擎溯源</n-text>
      <n-space :size="8">
        <n-select
          v-model:value="filterNodeType"
          :options="nodeTypeOptions"
          placeholder="节点类型"
          clearable
          size="small"
          style="width: 110px"
        />
        <n-button size="small" :loading="loading" @click="load">刷新</n-button>
      </n-space>
    </div>

    <n-spin :show="loading">
      <!-- 统计概览 -->
      <n-card v-if="stats" size="small" :bordered="true" class="stats-card">
        <template #header>
          <span class="card-title">统计概览</span>
        </template>
        <n-space :size="16" align="center">
          <div class="stat-item">
            <n-text depth="3" style="font-size: 11px">总记录</n-text>
            <n-text strong style="font-size: 18px">{{ stats.total_traces }}</n-text>
          </div>
          <div class="stat-item">
            <n-text depth="3" style="font-size: 11px">平均评分</n-text>
            <n-text strong style="font-size: 18px" :style="{ color: scoreColor(stats.avg_score) }">
              {{ stats.avg_score !== null ? (stats.avg_score * 100).toFixed(0) : '—' }}
            </n-text>
          </div>
          <div class="stat-item">
            <n-text depth="3" style="font-size: 11px">平均耗时</n-text>
            <n-text strong style="font-size: 18px">{{ stats.avg_duration_ms.toFixed(0) }}ms</n-text>
          </div>
        </n-space>
        <!-- 节点类型分布 -->
        <div v-if="Object.keys(stats.by_node_type).length > 0" class="stats-breakdown">
          <n-text depth="3" style="font-size: 11px; display: block; margin-bottom: 4px">节点分布</n-text>
          <n-space :size="6">
            <n-tag v-for="(count, type) in stats.by_node_type" :key="type" size="tiny" round>
              {{ nodeTypeLabel(type as string) }}: {{ count }}
            </n-tag>
          </n-space>
        </div>
      </n-card>

      <!-- 溯源列表 -->
      <div v-if="traces.length > 0" class="trace-list">
        <div
          v-for="t in traces"
          :key="t.trace_id"
          class="trace-item"
        >
          <div class="trace-meta">
            <n-tag :type="nodeTypeTagType(t.node_type)" size="tiny" round>
              {{ nodeTypeLabel(t.node_type) }}
            </n-tag>
            <n-tag size="tiny" :bordered="false">{{ t.operation }}</n-tag>
            <n-text v-if="t.score !== null" depth="3" style="font-size: 11px">
              评分 {{ (t.score * 100).toFixed(0) }}
            </n-text>
            <n-text depth="3" style="font-size: 10px">{{ t.duration_ms }}ms</n-text>
          </div>
          <div v-if="t.input_summary" class="trace-summary">
            <n-text depth="3" style="font-size: 11px">{{ t.input_summary }}</n-text>
          </div>
          <div v-if="t.violations.length > 0" class="trace-violations">
            <n-text style="font-size: 11px; color: #f59e0b">⚠ {{ t.violations.length }} 项违规</n-text>
          </div>
          <n-text depth="3" style="font-size: 10px">{{ formatTime(t.timestamp) }}</n-text>
        </div>
      </div>

      <n-empty v-else-if="!loading" description="暂无溯源记录，引擎操作后将自动记录" size="small" style="margin-top: 24px" />
    </n-spin>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { traceApi, type TraceDTO, type TraceStatsDTO } from '@/api/engineCore'

const props = defineProps<{ slug: string }>()

const loading = ref(false)
const traces = ref<TraceDTO[]>([])
const stats = ref<TraceStatsDTO | null>(null)
const filterNodeType = ref<string | null>(null)

const nodeTypeOptions = [
  { label: 'DAG 节点', value: 'dag_node' },
  { label: '质量护栏', value: 'guardrail' },
  { label: 'Checkpoint', value: 'checkpoint' },
  { label: '角色灵魂', value: 'character_soul' },
]

const NODE_TYPE_LABELS: Record<string, string> = {
  dag_node: 'DAG',
  guardrail: '护栏',
  checkpoint: '快照',
  character_soul: '灵魂',
}

function nodeTypeLabel(type: string): string {
  return NODE_TYPE_LABELS[type] || type
}

function nodeTypeTagType(type: string): 'default' | 'info' | 'success' | 'warning' | 'error' {
  const map: Record<string, 'default' | 'info' | 'success' | 'warning' | 'error'> = {
    dag_node: 'info',
    guardrail: 'warning',
    checkpoint: 'success',
    character_soul: 'error',
  }
  return map[type] || 'default'
}

function scoreColor(score: number | null): string {
  if (score === null) return 'inherit'
  if (score >= 0.75) return '#10b981'
  if (score >= 0.5) return '#f59e0b'
  return '#ef4444'
}

function formatTime(ts: string): string {
  if (!ts) return ''
  try {
    const d = new Date(ts)
    return `${d.getMonth() + 1}/${d.getDate()} ${d.getHours()}:${String(d.getMinutes()).padStart(2, '0')}`
  } catch {
    return ts
  }
}

async function load() {
  if (!props.slug) return
  loading.value = true
  try {
    const params: Record<string, unknown> = { limit: 50 }
    if (filterNodeType.value) params.node_type = filterNodeType.value
    const [traceRes, statsRes] = await Promise.all([
      traceApi.list(props.slug, params),
      traceApi.stats(props.slug).catch(() => null),
    ])
    traces.value = traceRes?.traces || []
    stats.value = statsRes
  } catch {
    traces.value = []
    stats.value = null
  } finally {
    loading.value = false
  }
}

watch(() => filterNodeType.value, () => load())
onMounted(load)
</script>

<style scoped>
.trace-panel {
  height: 100%;
  min-height: 0;
  overflow-y: auto;
  padding: 12px 16px 20px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.trace-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.stats-card {
  transition: all 0.2s ease;
}

.stats-card:hover {
  border-color: var(--n-primary-color-hover);
}

.card-title {
  font-size: 13px;
  font-weight: 600;
}

.stat-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
}

.stats-breakdown {
  margin-top: 10px;
  padding-top: 8px;
  border-top: 1px solid var(--n-border-color);
}

.trace-list {
  display: flex;
  flex-direction: column;
  gap: 0;
}

.trace-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 8px 0;
  border-left: 2px solid var(--n-border-color);
  padding-left: 14px;
  position: relative;
}

.trace-meta {
  display: flex;
  align-items: center;
  gap: 6px;
}

.trace-summary {
  font-size: 11px;
  line-height: 1.4;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 100%;
}

.trace-violations {
  font-size: 11px;
}
</style>
