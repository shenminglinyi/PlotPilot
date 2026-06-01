<template>
  <div class="trace-panel">
    <div class="trace-header">
      <n-text strong style="font-size: 14px">🔍 引擎溯源</n-text>
      <n-space :size="8">
        <n-select
          v-if="activeTab === 'engine'"
          v-model:value="filterNodeType"
          :options="nodeTypeOptions"
          placeholder="节点类型"
          clearable
          size="small"
          style="width: 110px"
        />
        <n-select
          v-if="activeTab === 'ai'"
          v-model:value="filterStage"
          :options="stageFilterOptions"
          placeholder="阶段筛选"
          clearable
          filterable
          size="small"
          style="width: 140px"
        />
        <n-button size="small" :loading="loading" @click="load">刷新</n-button>
      </n-space>
    </div>

    <n-tabs v-model:value="activeTab" size="small" animated type="bar">
      <!-- Tab 1: 旧版引擎溯源 -->
      <n-tab-pane name="engine" tab="引擎操作">
        <n-spin :show="loading">
          <n-card v-if="stats" size="small" :bordered="true" class="stats-card">
            <template #header><span class="card-title">统计概览</span></template>
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
            <div v-if="Object.keys(stats.by_node_type).length > 0" class="stats-breakdown">
              <n-text depth="3" style="font-size: 11px; display: block; margin-bottom: 4px">节点分布</n-text>
              <n-space :size="6">
                <n-tag v-for="(count, type) in stats.by_node_type" :key="String(type)" size="tiny" round>
                  {{ nodeTypeLabel(String(type)) }}: {{ count }}
                </n-tag>
              </n-space>
            </div>
          </n-card>

          <div v-if="traces.length > 0" class="trace-list">
            <div v-for="t in traces" :key="t.trace_id" class="trace-item">
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

          <n-empty v-else-if="!loading" description="暂无溯源记录" size="small" style="margin-top: 24px" />
        </n-spin>
      </n-tab-pane>

      <!-- Tab 2: AI 调用链路 -->
      <n-tab-pane name="ai" tab="AI 调用">
        <n-spin :show="loading">
          <!-- AI 阶段分布 -->
          <n-card v-if="aiStages.length > 0" size="small" :bordered="true" class="stats-card">
            <template #header><span class="card-title">阶段分布</span></template>
            <n-space :size="6">
              <n-tag
                v-for="s in aiStages.slice(0, 12)"
                :key="s.stage"
                size="tiny"
                round
                :type="stageTagType(s.stage)"
                style="cursor: pointer"
                @click="filterStage = s.stage"
              >
                {{ s.stage_label || s.stage }}: {{ s.cnt }}
              </n-tag>
              <n-text v-if="aiStages.length > 12" depth="3" style="font-size: 11px">
                +{{ aiStages.length - 12 }} 更多
              </n-text>
            </n-space>
          </n-card>

          <!-- AI Span 列表 -->
          <div v-if="aiSpans.length > 0" class="trace-list">
            <div v-for="s in aiSpans" :key="`${s.trace_id}-${s.span_id}`" class="trace-item">
              <div class="trace-meta">
                <n-tag :type="stageTagType(s.stage)" size="tiny" round>
                  {{ s.stage_label || stageLabel(s.stage) || s.phase }}
                </n-tag>
                <n-tag v-if="s.model" size="tiny" :bordered="false">{{ s.model }}</n-tag>
                <n-text v-if="s.token_input" depth="3" style="font-size: 10px">
                  in:{{ s.token_input }} out:{{ s.token_output }}
                </n-text>
                <n-text depth="3" style="font-size: 10px">{{ s.latency_ms }}ms</n-text>
                <n-tag v-if="s.error" type="error" size="tiny" round>error</n-tag>
              </div>
              <!-- prompt/response preview (expandable) -->
              <n-collapse v-if="s.prompt_preview || s.response_preview">
                <n-collapse-item title="查看 Prompt / Response" size="small">
                  <div v-if="s.prompt_preview" class="code-block">
                    <n-text depth="3" style="font-size: 10px; font-weight: 600">Prompt</n-text>
                    <n-text code style="font-size: 11px; white-space: pre-wrap; word-break: break-all">
                      {{ typeof s.prompt_preview === 'string' ? s.prompt_preview : JSON.stringify(s.prompt_preview, null, 2) }}
                    </n-text>
                  </div>
                  <div v-if="s.response_preview" class="code-block" style="margin-top: 8px">
                    <n-text depth="3" style="font-size: 10px; font-weight: 600">Response</n-text>
                    <n-text code style="font-size: 11px; white-space: pre-wrap; word-break: break-all">
                      {{ typeof s.response_preview === 'string' ? s.response_preview : JSON.stringify(s.response_preview, null, 2) }}
                    </n-text>
                  </div>
                </n-collapse-item>
              </n-collapse>
              <n-text v-if="s.error" depth="3" style="font-size: 10px; color: #ef4444">{{ s.error }}</n-text>
              <n-text depth="3" style="font-size: 10px">{{ formatTime(s.created_at) }}</n-text>
            </div>
          </div>

          <n-empty v-else-if="!loading" description="暂无 AI 调用记录" size="small" style="margin-top: 24px" />
        </n-spin>
      </n-tab-pane>
    </n-tabs>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, computed } from 'vue'
import { storeToRefs } from 'pinia'
import {
  traceApi,
  type TraceDTO,
  type TraceStatsDTO,
  type AiTraceSpanDTO,
  type AiStageDTO,
} from '@/api/engineCore'
import { useWorkbenchRefreshStore } from '@/stores/workbenchRefreshStore'
import { stageLabel, STAGE_BY_KEY, type StageDef } from '@/constants/aiCallStages'

const props = defineProps<{ slug: string }>()

const workbenchRefresh = useWorkbenchRefreshStore()
const { deskTick } = storeToRefs(workbenchRefresh)

const activeTab = ref<'engine' | 'ai'>('ai')
const loading = ref(false)

// ── 旧版引擎 ──
const traces = ref<TraceDTO[]>([])
const stats = ref<TraceStatsDTO | null>(null)
const filterNodeType = ref<string | null>(null)

// ── AI Trace ──
const aiSpans = ref<AiTraceSpanDTO[]>([])
const aiStages = ref<AiStageDTO[]>([])
const filterStage = ref<string | null>(null)

const nodeTypeOptions = [
  { label: 'DAG 节点', value: 'dag_node' },
  { label: '质量护栏', value: 'guardrail' },
  { label: 'Checkpoint', value: 'checkpoint' },
  { label: '角色心理', value: 'character_psyche' },
]

const NODE_TYPE_LABELS: Record<string, string> = {
  dag_node: 'DAG',
  guardrail: '护栏',
  checkpoint: '快照',
  character_psyche: '心理画像',
}

const stageFilterOptions = computed(() => {
  const items: { label: string; value: string }[] = aiStages.value.map(s => ({
    label: `${s.stage_label || s.stage} (${s.cnt})`,
    value: s.stage,
  }))
  for (const sd of Object.values(STAGE_BY_KEY)) {
    if (!items.find(i => i.value === sd.key)) {
      items.push({ label: `${sd.label} (0)`, value: sd.key })
    }
  }
  return items
})

function nodeTypeLabel(type: string): string {
  return NODE_TYPE_LABELS[type] || type
}

function nodeTypeTagType(type: string): 'default' | 'info' | 'success' | 'warning' | 'error' {
  const map: Record<string, 'default' | 'info' | 'success' | 'warning' | 'error'> = {
    dag_node: 'info',
    guardrail: 'warning',
    checkpoint: 'success',
    character_psyche: 'error',
  }
  return map[type] || 'default'
}

function stageTagType(stage: string): 'default' | 'info' | 'success' | 'warning' | 'error' {
  const sd = STAGE_BY_KEY[stage]
  if (!sd) return 'default'
  const map: Record<string, 'default' | 'info' | 'success' | 'warning' | 'error'> = {
    plan: 'info',
    write: 'success',
    audit: 'warning',
    sync: 'default',
    review: 'error',
    generate: 'info',
  }
  return map[sd.semantic] || 'default'
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
    if (activeTab.value === 'engine') {
      const params: Record<string, unknown> = { limit: 50 }
      if (filterNodeType.value) params.node_type = filterNodeType.value
      const [traceRes, statsRes] = await Promise.all([
        traceApi.list(props.slug, params),
        traceApi.stats(props.slug).catch(() => null),
      ])
      traces.value = traceRes?.traces || []
      stats.value = statsRes
    } else {
      const [stagesRes, spansRes] = await Promise.all([
        traceApi.stages(props.slug).catch(() => null),
        filterStage.value
          ? traceApi.byStage(props.slug, filterStage.value, 50)
          : traceApi.listAi(props.slug, { limit: 1 }).then(async (list) => {
              if (list.traces.length > 0) {
                const t = list.traces[0]
                return traceApi.timeline(props.slug, t.trace_id)
              }
              return { spans: [], total: 0, trace_id: '' }
            }),
      ])
      aiStages.value = stagesRes?.stages || []
      aiSpans.value = spansRes?.spans || []
    }
  } catch {
    traces.value = []
    stats.value = null
    aiSpans.value = []
    aiStages.value = []
  } finally {
    loading.value = false
  }
}

watch(
  () => [props.slug, deskTick.value, activeTab.value, filterNodeType.value, filterStage.value] as const,
  () => { void load() },
  { immediate: true },
)
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

.code-block {
  max-height: 300px;
  overflow-y: auto;
}
</style>
