<template>
  <section class="spo" aria-label="StoryPipeline 管线可观测">
    <header class="spo__head">
      <div class="spo__titles">
        <span class="spo__title">StoryPipeline · 一章十步</span>
        <span class="spo__badge">实时</span>
      </div>
      <div v-if="dwellLine" class="spo__dwell">{{ dwellLine }}</div>
    </header>

    <div class="spo__track-wrap">
      <div class="spo__track">
        <div
          v-for="w in STORY_PIPELINE_WAVES"
          :key="w.id"
          class="spo-step"
          :class="stepClass(w.index)"
        >
          <div class="spo-step__ix">{{ w.index }}</div>
          <div class="spo-step__label">{{ w.label }}</div>
          <div v-if="doneCheck(w.index)" class="spo-step__ok" aria-hidden="true">✓</div>
        </div>
      </div>
    </div>

    <!-- 节点卡（仅在 wave 4 生成步骤时显示） -->
    <div v-if="currentIx === 4 && beatCard.active_action" class="spo-beatcard">
      <div class="spo-beatcard__head">
        <span class="spo-beatcard__beat-pill">
          节拍 {{ beatCard.beatNum }}/{{ beatCard.totalBeats || '?' }}
        </span>
        <span v-if="beatCard.approxWords" class="spo-beatcard__words-hint">
          ≈{{ beatCard.approxWords }} 字/次
        </span>
      </div>
      <div class="spo-beatcard__action">{{ beatCard.active_action }}</div>
      <div class="spo-beatcard__chips">
        <span v-if="beatCard.emotion_gap" class="spo-beatcard__chip">
          <em class="spo-beatcard__chip-tag">缺</em>{{ beatCard.emotion_gap }}
        </span>
        <span v-if="beatCard.forbidden_drift" class="spo-beatcard__chip spo-beatcard__chip--warn">
          <em class="spo-beatcard__chip-tag">禁</em>{{ beatCard.forbidden_drift }}
        </span>
      </div>
    </div>

    <div v-if="showAftermathCard" class="spo-aftermath" aria-label="章后管线细分">
      <header class="spo-aftermath__head">
        <span class="spo-aftermath__title">章后管线 · 叙事 / 向量 / KG</span>
        <span class="spo-aftermath__hint">{{ aftermathSummary }}</span>
      </header>
      <div class="spo-aftermath__grid">
        <div
          v-for="step in aftermathSteps"
          :key="step.id"
          class="spo-aftermath-step"
          :class="`spo-aftermath-step--${step.state}`"
        >
          <span class="spo-aftermath-step__ix">{{ step.index }}</span>
          <span class="spo-aftermath-step__text">
            <span class="spo-aftermath-step__label">{{ step.label }}</span>
            <span class="spo-aftermath-step__detail">{{ step.detail }}</span>
          </span>
          <span v-if="step.state === 'done'" class="spo-aftermath-step__mark">✓</span>
          <span v-else-if="step.state === 'current'" class="spo-aftermath-step__pulse" />
          <span v-else-if="step.state === 'fail'" class="spo-aftermath-step__mark spo-aftermath-step__mark--fail">!</span>
        </div>
      </div>
    </div>

    <details v-if="events.length > 1" class="spo-events">
      <summary>事件轨迹（{{ events.length }}）</summary>
      <ol class="spo-events__list">
        <li v-for="(ev, idx) in displayEvents" :key="idx" class="spo-events__item">
          <span class="spo-events__t">{{ fmtRel(ev.t) }}</span>
          <span class="spo-events__wave">波次 {{ ev.wave }}</span>
          <span class="spo-events__label">{{ ev.label }}</span>
          <span v-if="ev.substep" class="spo-events__sub mono">{{ ev.substep }}</span>
        </li>
      </ol>
    </details>
    <p v-else-if="events.length === 1" class="spo-events-lite mono">
      {{ events[0].label }}
    </p>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { STORY_PIPELINE_WAVES } from '@/constants/storyPipelineWaves'

/** /status 中 StoryPipeline 相关字段（松散类型以兼容运行时） */
interface StatusLike {
  story_pipeline_wave_index?: number | null
  story_pipeline_wave_entered_at?: number | null
  story_pipeline_events?: Array<{
    t: number
    wave?: number
    wave_id?: string
    substep?: string
    label?: string
  }>
  // 节点卡字段（wave 4 时非空）
  beat_active_action?: string
  beat_emotion_gap?: string
  beat_forbidden_drift?: string
  current_beat_index?: number | null
  total_beats?: number | null
  chapter_target_words?: number | null
  writing_substep?: string
  writing_substep_label?: string
  current_chapter_number?: number | null
  aftermath_live_status?: 'running' | 'done' | 'failed' | string | null
  aftermath_live_chapter_number?: number | null
  narrative_sync_ok?: boolean
  vector_stored?: boolean
  foreshadow_stored?: boolean
  triples_extracted?: boolean
  causal_edges_stored?: boolean
  character_mutations_stored?: boolean
  debt_updated?: boolean
  character_reconcile_ok?: boolean
  evolution_snapshot_ok?: boolean
  last_chapter_audit?: {
    narrative_sync_ok?: boolean
    vector_stored?: boolean
    foreshadow_stored?: boolean
    triples_extracted?: boolean
    causal_edges_stored?: boolean
    character_mutations_stored?: boolean
    debt_updated?: boolean
    character_reconcile_ok?: boolean
    evolution_snapshot_ok?: boolean
  } | null
}

const props = defineProps<{
  status: StatusLike | null | undefined
}>()

const tick = ref(0)
let timer: ReturnType<typeof setInterval> | null = null

onMounted(() => {
  timer = setInterval(() => {
    tick.value += 1
  }, 1000)
})
onUnmounted(() => {
  if (timer) clearInterval(timer)
})

const currentIx = computed(() => {
  const n = Number(props.status?.story_pipeline_wave_index)
  return Number.isFinite(n) && n >= 1 && n <= 10 ? n : 0
})

const enteredAt = computed(() => {
  const t = props.status?.story_pipeline_wave_entered_at
  return typeof t === 'number' && Number.isFinite(t) ? t : null
})

// tick 触发重算 dwell
const dwellLine = computed(() => {
  void tick.value
  const ea = enteredAt.value
  if (ea === null || currentIx.value < 1) return ''
  const s = Math.max(0, Math.floor(Date.now() / 1000 - ea))
  if (s < 60) return `本步已停留 ${s} 秒`
  const m = Math.floor(s / 60)
  const r = s % 60
  return `本步已停留 ${m} 分 ${r} 秒`
})

function stepClass(ix: number) {
  const c = currentIx.value
  if (c <= 0) return 'spo-step--muted'
  if (ix === c) return 'spo-step--current'
  if (ix < c) return 'spo-step--done'
  return 'spo-step--pending'
}

function doneCheck(ix: number) {
  const c = currentIx.value
  return c > 0 && ix < c
}

const events = computed(() => {
  const e = props.status?.story_pipeline_events
  return Array.isArray(e) ? e : []
})

const displayEvents = computed(() => {
  const e = [...events.value]
  return e.slice(-12).reverse()
})

const beatCard = computed(() => {
  const totalBeats = Number(props.status?.total_beats || 0)
  const beatNum = Number(props.status?.current_beat_index ?? 0) + 1
  const chapterTarget = Number(props.status?.chapter_target_words || 0)
  const approxWords = totalBeats > 0 && chapterTarget > 0
    ? Math.round(chapterTarget / totalBeats)
    : 0
  return {
    active_action: props.status?.beat_active_action || '',
    emotion_gap: props.status?.beat_emotion_gap || '',
    forbidden_drift: props.status?.beat_forbidden_drift || '',
    beatNum,
    totalBeats,
    approxWords,
  }
})

type AftermathState = 'done' | 'current' | 'pending' | 'fail'

interface AftermathStep {
  index: number
  id: string
  label: string
  detail: string
  state: AftermathState
}

const aftermathLiveStatus = computed(() => String(props.status?.aftermath_live_status || ''))

const liveAftermathMatchesChapter = computed(() => {
  const liveChapter = props.status?.aftermath_live_chapter_number
  const currentChapter = props.status?.current_chapter_number
  if (liveChapter == null || currentChapter == null) return true
  return Number(liveChapter) === Number(currentChapter)
})

const aftermathSource = computed(() => {
  if (aftermathRunning.value && aftermathLiveStatus.value !== 'done') return null
  if (aftermathLiveStatus.value === 'done' && liveAftermathMatchesChapter.value) {
    return props.status ?? null
  }
  return props.status?.last_chapter_audit ?? props.status ?? null
})

function stepState(value: boolean | undefined, failWhenFalse = false): AftermathState {
  if (value === true) return 'done'
  if (value === false && failWhenFalse) return 'fail'
  return 'pending'
}

const aftermathRunning = computed(() => {
  const sub = String(props.status?.writing_substep || '')
  return currentIx.value === 8 || sub === 'audit_aftermath' || sub === 'chapter_aftermath' || sub === 'chapter_aftermath_done'
})

const activeAftermathIndex = computed(() => {
  if (!aftermathRunning.value || aftermathLiveStatus.value === 'done') return 0
  void tick.value
  const ea = enteredAt.value
  if (ea === null) return 1
  const elapsed = Math.max(0, Math.floor(Date.now() / 1000 - ea))
  return Math.min(8, Math.floor(elapsed / 3) + 1)
})

const aftermathSteps = computed<AftermathStep[]>(() => {
  const s = aftermathSource.value
  const steps: AftermathStep[] = [
    { index: 1, id: 'summary', label: '摘要事件', detail: '摘要 / 事件 / 场景信号', state: stepState(s?.narrative_sync_ok, aftermathLiveStatus.value === 'failed') },
    { index: 2, id: 'beats', label: '叙事节拍', detail: 'beat_sections 对齐', state: stepState(s?.narrative_sync_ok, aftermathLiveStatus.value === 'failed') },
    { index: 3, id: 'vector', label: '向量索引', detail: '语义检索落库', state: stepState(s?.vector_stored) },
    { index: 4, id: 'foreshadow', label: '伏笔账本', detail: '埋线 / 兑现记录', state: stepState(s?.foreshadow_stored) },
    { index: 5, id: 'kg', label: 'KG 三元组', detail: '实体关系抽取', state: stepState(s?.triples_extracted) },
    { index: 6, id: 'causal', label: '因果边', detail: '动作后果链路', state: stepState(s?.causal_edges_stored) },
    {
      index: 7,
      id: 'character',
      label: '角色状态',
      detail: '立场 / 情绪投影',
      state: stepState(s?.character_mutations_stored ?? s?.character_reconcile_ok),
    },
    {
      index: 8,
      id: 'debt',
      label: '叙事债务',
      detail: '承诺 / 风险更新',
      state: stepState(s?.debt_updated ?? s?.evolution_snapshot_ok),
    },
  ]

  if (aftermathRunning.value && aftermathLiveStatus.value !== 'done') {
    const ix = activeAftermathIndex.value
    return steps.map(step => {
      if (step.state === 'done' || step.state === 'fail') return step
      if (step.index < ix) return { ...step, state: 'done' }
      if (step.index === ix) return { ...step, state: 'current' }
      return step
    })
  }
  return steps
})

const showAftermathCard = computed(() => {
  if (currentIx.value === 8) return true
  if (currentIx.value > 8 && aftermathSteps.value.some(step => step.state === 'done' || step.state === 'fail')) return true
  return aftermathRunning.value
})

const aftermathSummary = computed(() => {
  const failed = aftermathSteps.value.filter(step => step.state === 'fail').length
  const done = aftermathSteps.value.filter(step => step.state === 'done').length
  if (aftermathRunning.value && aftermathLiveStatus.value !== 'done') {
    const current = aftermathSteps.value.find(step => step.state === 'current')
    return current ? `正在处理：${current.label}` : (props.status?.writing_substep_label || '实时处理中')
  }
  if (failed > 0) return `${failed} 项需复查`
  if (done > 0) return `${done}/${aftermathSteps.value.length} 已确认`
  return '等待章后结果'
})

function fmtRel(t?: number): string {
  if (typeof t !== 'number' || !Number.isFinite(t)) return '—'
  void tick.value
  const s = Math.max(0, Math.floor(Date.now() / 1000 - t))
  if (s < 45) return `${s}s 前`
  if (s < 3600) return `${Math.floor(s / 60)}m 前`
  return `${Math.floor(s / 3600)}h 前`
}
</script>

<style scoped>
.spo {
  --spo-accent: var(--color-brand);
  --spo-accent-dim: var(--color-brand-light);
  --spo-accent-border: var(--color-brand-border);
  --spo-surface: var(--app-surface-raised, var(--app-surface));
  --spo-surface-subtle: var(--app-surface-subtle);
  --spo-text: var(--app-text-primary);
  --spo-text-muted: var(--app-text-muted);
  --spo-text-secondary: var(--app-text-secondary);
  --spo-success: var(--color-success);
  --spo-success-dim: var(--color-success-dim);
  --spo-danger: var(--color-danger);
  --spo-danger-dim: var(--color-danger-dim);

  margin-top: 10px;
  padding: 12px 14px;
  border-radius: var(--app-radius-md, 10px);
  border: 1px solid var(--spo-accent-border);
  background: linear-gradient(
    145deg,
    color-mix(in srgb, var(--spo-accent) 7%, var(--spo-surface)) 0%,
    color-mix(in srgb, var(--color-purple, #8b5cf6) 4%, var(--spo-surface-subtle)) 100%
  );
  box-shadow: var(--app-shadow-sm);
  transition:
    background 0.3s ease,
    border-color 0.3s ease,
    color 0.3s ease;
}

.spo__head {
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  align-items: baseline;
  gap: 8px;
  margin-bottom: 10px;
}

.spo__titles {
  display: flex;
  align-items: center;
  gap: 8px;
}

.spo__title {
  font-size: var(--font-size-sm, 13px);
  font-weight: 700;
  letter-spacing: 0.04em;
  color: var(--spo-text);
}

.spo__badge {
  font-size: 10px;
  font-weight: 700;
  padding: 2px 7px;
  border-radius: 999px;
  background: var(--spo-success-dim);
  color: var(--spo-success);
  border: 1px solid color-mix(in srgb, var(--spo-success) 22%, transparent);
  animation: spo-pulse 2.2s ease-in-out infinite;
}

@keyframes spo-pulse {
  0%,
  100% {
    opacity: 1;
  }
  50% {
    opacity: 0.55;
  }
}

.spo__dwell {
  font-size: 11px;
  font-variant-numeric: tabular-nums;
  color: var(--spo-text-secondary);
}

.spo__track-wrap {
  overflow-x: auto;
  padding-bottom: 4px;
  scrollbar-width: thin;
  scrollbar-color: var(--spo-accent-border) transparent;
}

.spo__track {
  display: flex;
  gap: 8px;
  min-width: min-content;
}

.spo-step {
  position: relative;
  flex: 0 0 auto;
  width: 86px;
  padding: 8px 6px 10px;
  border-radius: var(--app-radius-sm, 8px);
  border: 1px solid var(--app-border);
  background: var(--spo-surface);
  transition:
    border-color var(--app-transition, 0.18s ease),
    box-shadow var(--app-transition, 0.18s ease),
    opacity var(--app-transition, 0.18s ease),
    background var(--app-transition, 0.18s ease);
}

.spo-step__ix {
  font-size: 10px;
  font-weight: 800;
  color: var(--spo-text-muted);
}

.spo-step__label {
  margin-top: 2px;
  font-size: 11px;
  line-height: 1.35;
  font-weight: 600;
  color: var(--spo-text);
}

.spo-step__ok {
  position: absolute;
  top: 4px;
  right: 4px;
  font-size: 10px;
  color: var(--spo-success);
  font-weight: 800;
}

.spo-step--current {
  border-color: var(--spo-accent-border);
  background: var(--spo-accent-dim);
  box-shadow: 0 0 0 1px var(--spo-accent-border);
}

.spo-step--current .spo-step__ix,
.spo-step--current .spo-step__label {
  color: var(--spo-accent);
}

.spo-step--done {
  opacity: 0.95;
  border-color: color-mix(in srgb, var(--spo-success) 28%, var(--app-border));
  background: color-mix(in srgb, var(--spo-success) 6%, var(--spo-surface));
}

.spo-step--done .spo-step__ix {
  color: var(--spo-success);
}

.spo-step--pending {
  opacity: 0.58;
}

.spo-step--muted {
  opacity: 0.48;
}

.spo-beatcard {
  margin-top: 8px;
  padding: 7px 10px;
  border-radius: var(--app-radius-sm, 8px);
  background: var(--spo-accent-dim);
  border: 1px solid var(--spo-accent-border);
  display: flex;
  flex-direction: column;
  gap: 4px;
}

/* 头部：节拍计数 + 字数估算 */
.spo-beatcard__head {
  display: flex;
  align-items: center;
  gap: 8px;
}

.spo-beatcard__beat-pill {
  font-size: 10px;
  font-weight: 700;
  padding: 1px 6px;
  border-radius: 999px;
  background: color-mix(in srgb, var(--spo-accent) 15%, transparent);
  color: var(--spo-accent);
  border: 1px solid var(--spo-accent-border);
  letter-spacing: 0.03em;
}

.spo-beatcard__words-hint {
  font-size: 10px;
  color: var(--spo-text-muted);
  font-variant-numeric: tabular-nums;
}

/* 主行为文字（2 行截断） */
.spo-beatcard__action {
  font-size: 11px;
  line-height: 1.5;
  color: var(--spo-text);
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

/* 缺口 / 禁止 芯片行（横向，各自单行截断） */
.spo-beatcard__chips {
  display: flex;
  gap: 6px;
  flex-wrap: nowrap;
  overflow: hidden;
}

.spo-beatcard__chip {
  display: flex;
  align-items: baseline;
  gap: 4px;
  font-size: 10.5px;
  color: var(--spo-text-secondary);
  min-width: 0;
  flex: 1 1 0;
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}

.spo-beatcard__chip--warn {
  color: color-mix(in srgb, var(--spo-danger) 80%, var(--spo-text-secondary));
}

.spo-beatcard__chip-tag {
  flex-shrink: 0;
  font-style: normal;
  font-size: 9px;
  font-weight: 800;
  padding: 0px 4px;
  border-radius: 3px;
  background: color-mix(in srgb, var(--spo-accent) 12%, transparent);
  color: var(--spo-accent);
  border: 1px solid var(--spo-accent-border);
  letter-spacing: 0.02em;
}

.spo-beatcard__chip--warn .spo-beatcard__chip-tag {
  background: var(--spo-danger-dim);
  color: var(--spo-danger);
  border-color: color-mix(in srgb, var(--spo-danger) 25%, transparent);
}

.spo-aftermath {
  margin-top: 8px;
  padding: 9px 10px;
  border-radius: var(--app-radius-sm, 8px);
  border: 1px solid var(--spo-accent-border);
  background: color-mix(in srgb, var(--spo-accent) 5%, var(--spo-surface));
}

.spo-aftermath__head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 8px;
}

.spo-aftermath__title {
  font-size: 11px;
  font-weight: 800;
  color: var(--spo-text);
}

.spo-aftermath__hint {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 10px;
  color: var(--spo-text-muted);
}

.spo-aftermath__grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 6px;
}

.spo-aftermath-step {
  min-width: 0;
  display: flex;
  align-items: flex-start;
  gap: 6px;
  padding: 7px 6px;
  border-radius: 7px;
  border: 1px solid var(--app-border);
  background: var(--spo-surface);
  opacity: 0.72;
}

.spo-aftermath-step__ix {
  flex: 0 0 auto;
  width: 18px;
  height: 18px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 999px;
  font-size: 9px;
  font-weight: 900;
  color: var(--spo-text-muted);
  border: 1px solid var(--app-border);
  background: var(--spo-surface-subtle);
  font-variant-numeric: tabular-nums;
}

.spo-aftermath-step__text {
  min-width: 0;
  flex: 1;
}

.spo-aftermath-step__label,
.spo-aftermath-step__detail {
  display: block;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.spo-aftermath-step__label {
  font-size: 10.5px;
  font-weight: 800;
  color: var(--spo-text);
}

.spo-aftermath-step__detail {
  margin-top: 2px;
  font-size: 9.5px;
  color: var(--spo-text-muted);
}

.spo-aftermath-step__mark {
  flex: 0 0 auto;
  font-size: 10px;
  font-weight: 900;
  color: var(--spo-success);
}

.spo-aftermath-step__mark--fail {
  color: var(--color-warning, #f59e0b);
}

.spo-aftermath-step__pulse {
  flex: 0 0 auto;
  width: 7px;
  height: 7px;
  margin-top: 5px;
  border-radius: 999px;
  background: var(--spo-accent);
  box-shadow: 0 0 0 4px color-mix(in srgb, var(--spo-accent) 14%, transparent);
  animation: spo-pulse 1.4s ease-in-out infinite;
}

.spo-aftermath-step--done {
  opacity: 1;
  border-color: color-mix(in srgb, var(--spo-success) 28%, var(--app-border));
  background: color-mix(in srgb, var(--spo-success) 6%, var(--spo-surface));
}

.spo-aftermath-step--done .spo-aftermath-step__ix {
  color: var(--spo-success);
  border-color: color-mix(in srgb, var(--spo-success) 32%, var(--app-border));
  background: var(--spo-success-dim);
}

.spo-aftermath-step--current {
  opacity: 1;
  border-color: var(--spo-accent-border);
  background: var(--spo-accent-dim);
  box-shadow: 0 0 0 1px var(--spo-accent-border);
}

.spo-aftermath-step--current .spo-aftermath-step__ix,
.spo-aftermath-step--current .spo-aftermath-step__label {
  color: var(--spo-accent);
}

.spo-aftermath-step--fail {
  opacity: 1;
  border-color: color-mix(in srgb, var(--color-warning, #f59e0b) 34%, var(--app-border));
  background: color-mix(in srgb, var(--color-warning, #f59e0b) 7%, var(--spo-surface));
}

.spo-events {
  margin-top: 10px;
  font-size: 11px;
  color: var(--spo-text-secondary);
}

.spo-events summary {
  cursor: pointer;
  font-weight: 600;
  color: var(--spo-text-muted);
}

.spo-events summary:hover {
  color: var(--spo-accent);
}

.spo-events__list {
  margin: 8px 0 0;
  padding-left: 18px;
  max-height: 140px;
  overflow-y: auto;
  scrollbar-color: var(--spo-accent-border) transparent;
}

.spo-events__item {
  margin-bottom: 4px;
  line-height: 1.45;
}

.spo-events__t {
  color: var(--spo-text-muted);
  margin-right: 6px;
  font-variant-numeric: tabular-nums;
}

.spo-events__wave {
  margin-right: 6px;
  font-weight: 600;
  color: var(--spo-accent);
}

.spo-events__sub {
  display: inline-block;
  margin-left: 6px;
  font-size: 10px;
  opacity: 0.75;
  color: var(--spo-text-muted);
}

.mono {
  font-family: var(--font-mono, monospace);
}

.spo-events-lite {
  margin-top: 8px;
  font-size: 11px;
  color: var(--spo-text-muted);
}
</style>
