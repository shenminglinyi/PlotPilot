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
  margin-top: 10px;
  padding: 12px 14px;
  border-radius: 10px;
  border: 1px solid color-mix(in srgb, var(--color-brand, #6366f1) 35%, transparent);
  background: linear-gradient(
    145deg,
    color-mix(in srgb, var(--color-brand, #6366f1) 8%, var(--card-color)) 0%,
    color-mix(in srgb, #8b5cf6 6%, var(--card-color)) 100%
  );
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
  font-size: 13px;
  font-weight: 700;
  letter-spacing: 0.04em;
  color: var(--app-text-primary, #0f172a);
}

.spo__badge {
  font-size: 10px;
  font-weight: 700;
  padding: 2px 7px;
  border-radius: 999px;
  background: rgba(34, 197, 94, 0.18);
  color: #16a34a;
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
  color: var(--app-text-secondary, #64748b);
}

.spo__track-wrap {
  overflow-x: auto;
  padding-bottom: 4px;
  scrollbar-width: thin;
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
  border-radius: 8px;
  border: 1px solid color-mix(in srgb, var(--app-border, #cbd5e1) 80%, transparent);
  background: var(--card-color, #fff);
  transition: border-color 0.2s, box-shadow 0.2s, opacity 0.2s;
}

.spo-step__ix {
  font-size: 10px;
  font-weight: 800;
  color: var(--app-text-muted, #94a3b8);
}

.spo-step__label {
  margin-top: 2px;
  font-size: 11px;
  line-height: 1.35;
  font-weight: 600;
  color: var(--app-text-primary, #1e293b);
}

.spo-step__ok {
  position: absolute;
  top: 4px;
  right: 4px;
  font-size: 10px;
  color: #22c55e;
  font-weight: 800;
}

.spo-step--current {
  border-color: color-mix(in srgb, var(--color-brand, #6366f1) 70%, transparent);
  box-shadow: 0 0 0 1px color-mix(in srgb, var(--color-brand, #6366f1) 35%, transparent);
}

.spo-step--done {
  opacity: 0.92;
}

.spo-step--pending {
  opacity: 0.55;
}

.spo-step--muted {
  opacity: 0.5;
}

.spo-events {
  margin-top: 10px;
  font-size: 11px;
  color: var(--app-text-secondary, #475569);
}

.spo-events summary {
  cursor: pointer;
  font-weight: 600;
  color: var(--app-text-muted, #64748b);
}

.spo-events__list {
  margin: 8px 0 0;
  padding-left: 18px;
  max-height: 140px;
  overflow-y: auto;
}

.spo-events__item {
  margin-bottom: 4px;
  line-height: 1.45;
}

.spo-events__t {
  color: var(--app-text-muted, #94a3b8);
  margin-right: 6px;
  font-variant-numeric: tabular-nums;
}

.spo-events__wave {
  margin-right: 6px;
  font-weight: 600;
}

.spo-events__sub {
  display: inline-block;
  margin-left: 6px;
  font-size: 10px;
  opacity: 0.75;
}

.mono {
  font-family: var(--font-mono, monospace);
}

.spo-events-lite {
  margin-top: 8px;
  font-size: 11px;
  color: var(--app-text-muted, #64748b);
}
</style>
