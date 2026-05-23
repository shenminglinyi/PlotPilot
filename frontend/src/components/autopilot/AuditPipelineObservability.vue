<template>
  <section class="apo" aria-label="审计管线可观测">
    <header class="apo__head">
      <div class="apo__titles">
        <span class="apo__title">AuditPipeline · 一章审计</span>
        <span class="apo__badge">实时</span>
      </div>
      <div v-if="dwellLine" class="apo__dwell">{{ dwellLine }}</div>
    </header>

    <div class="apo__track-wrap">
      <div class="apo__track">
        <div
          v-for="step in displayedAuditSteps"
          :key="step.id"
          class="apo-step"
          :class="stepClass(step.index)"
        >
          <div class="apo-step__ix">{{ step.index }}</div>
          <div class="apo-step__label">{{ step.label }}</div>
          <div class="apo-step__desc">{{ step.desc }}</div>
          <div v-if="doneCheck(step.index)" class="apo-step__ok" aria-hidden="true">✓</div>
        </div>
      </div>
    </div>

    <div v-if="activeDetail" class="apo-current">
      <span class="apo-current__label">{{ activeDetail.label }}</span>
      <span class="apo-current__text">{{ activeDetail.text }}</span>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'

interface StatusLike {
  current_stage?: string | null
  writing_substep?: string | null
  writing_substep_label?: string | null
  audit_progress?: string | null
  audit_aftermath_reused?: boolean
  last_chapter_audit?: {
    similarity_score?: number | null
    drift_alert?: boolean
    narrative_sync_ok?: boolean
    vector_stored?: boolean
    triples_extracted?: boolean
    tension?: number
  } | null
}

const props = defineProps<{
  status: StatusLike | null | undefined
}>()

const auditSteps = [
  { index: 1, id: 'prepare', label: '审计准备', desc: '锁定章节与正文' },
  { index: 2, id: 'voice', label: '文风预检', desc: '指纹相似度 / 漂移' },
  { index: 3, id: 'aftermath', label: '章后管线', desc: '叙事 / 向量 / KG' },
  { index: 4, id: 'tension', label: '张力打分', desc: '章节压力曲线' },
  { index: 5, id: 'snapshot', label: '审计快照', desc: '结果写入状态面板' },
  { index: 6, id: 'finalize', label: '收尾推进', desc: '进入下一章或停机' },
] as const

const displayedAuditSteps = computed(() =>
  auditSteps.map(step => {
    if (step.id !== 'aftermath' || !props.status?.audit_aftermath_reused) return step
    return { ...step, label: '结果复用', desc: '沿用十步产物' }
  })
)

const tick = ref(0)
const stepEnteredAt = ref(Math.floor(Date.now() / 1000))
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
  const sub = String(props.status?.writing_substep || '')
  const progress = String(props.status?.audit_progress || '')
  const stage = String(props.status?.current_stage || '')

  if (sub === 'pipeline_done') return 1
  if (sub === 'audit_voice_check' || progress === 'voice_check') return 2
  if (sub === 'audit_aftermath' || progress === 'aftermath_pipeline') return 3
  if (sub === 'audit_tension' || progress === 'tension_scoring') return 4
  if (props.status?.last_chapter_audit && stage === 'auditing') return 5
  if (stage === 'auditing') return 1
  return 0
})

watch(currentIx, (next, prev) => {
  if (next !== prev) {
    stepEnteredAt.value = Math.floor(Date.now() / 1000)
  }
})

const dwellLine = computed(() => {
  void tick.value
  if (currentIx.value < 1) return ''
  const s = Math.max(0, Math.floor(Date.now() / 1000 - stepEnteredAt.value))
  if (s < 60) return `本步已停留 ${s} 秒`
  const m = Math.floor(s / 60)
  const r = s % 60
  return `本步已停留 ${m} 分 ${r} 秒`
})

function stepClass(ix: number) {
  const c = currentIx.value
  if (c <= 0) return 'apo-step--muted'
  if (ix === c) return 'apo-step--current'
  if (ix < c) return 'apo-step--done'
  return 'apo-step--pending'
}

function doneCheck(ix: number) {
  const c = currentIx.value
  return c > 0 && ix < c
}

const activeDetail = computed(() => {
  const ix = currentIx.value
  if (ix < 1) return null
  const step = displayedAuditSteps.value.find(s => s.index === ix)
  if (!step) return null
  const label = props.status?.writing_substep_label || step.label
  const audit = props.status?.last_chapter_audit
  if (ix === 2 && audit?.similarity_score != null) {
    return { label, text: `文风相似度 ${Number(audit.similarity_score).toFixed(3)}${audit.drift_alert ? ' · 漂移告警' : ''}` }
  }
  if (ix === 3 && audit) {
    if (props.status?.audit_aftermath_reused) {
      return { label, text: '已复用写作管线第 8 步结果，未重复执行叙事 / 向量 / KG' }
    }
    const flags = [
      audit.narrative_sync_ok ? '叙事已同步' : '',
      audit.vector_stored ? '向量已落库' : '',
      audit.triples_extracted ? 'KG 已抽取' : '',
    ].filter(Boolean)
    return { label, text: flags.length ? flags.join(' · ') : '正在把正文转成叙事、向量与知识图谱资产' }
  }
  if (ix === 3 && props.status?.audit_aftermath_reused) {
    return { label, text: '已复用写作管线第 8 步结果，未重复执行叙事 / 向量 / KG' }
  }
  if (ix === 4 && audit?.tension != null) {
    return { label, text: `张力 ${audit.tension}/100` }
  }
  return { label, text: step.desc }
})
</script>

<style scoped>
.apo {
  --apo-accent: var(--color-warning, #f59e0b);
  --apo-accent-dim: var(--color-warning-dim, rgba(245, 158, 11, 0.12));
  --apo-accent-border: color-mix(in srgb, var(--apo-accent) 26%, var(--app-border));
  --apo-surface: var(--app-surface-raised, var(--app-surface));
  --apo-surface-subtle: var(--app-surface-subtle);
  --apo-text: var(--app-text-primary);
  --apo-text-muted: var(--app-text-muted);
  --apo-text-secondary: var(--app-text-secondary);
  --apo-success: var(--color-success, #22c55e);
  --apo-success-dim: var(--color-success-dim, rgba(34, 197, 94, 0.12));

  margin-top: 10px;
  padding: 12px 14px;
  border-radius: var(--app-radius-md, 10px);
  border: 1px solid var(--apo-accent-border);
  background: linear-gradient(
    145deg,
    color-mix(in srgb, var(--apo-accent) 7%, var(--apo-surface)) 0%,
    color-mix(in srgb, var(--color-brand, #2563eb) 4%, var(--apo-surface-subtle)) 100%
  );
  box-shadow: var(--app-shadow-sm);
}

.apo__head {
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  align-items: baseline;
  gap: 8px;
  margin-bottom: 10px;
}

.apo__titles {
  display: flex;
  align-items: center;
  gap: 8px;
}

.apo__title {
  font-size: var(--font-size-sm, 13px);
  font-weight: 700;
  letter-spacing: 0.04em;
  color: var(--apo-text);
}

.apo__badge {
  font-size: 10px;
  font-weight: 700;
  padding: 2px 7px;
  border-radius: 999px;
  background: var(--apo-success-dim);
  color: var(--apo-success);
  border: 1px solid color-mix(in srgb, var(--apo-success) 22%, transparent);
  animation: apo-pulse 2.2s ease-in-out infinite;
}

.apo__dwell {
  font-size: 11px;
  font-variant-numeric: tabular-nums;
  color: var(--apo-text-secondary);
}

.apo__track-wrap {
  overflow-x: auto;
  padding-bottom: 4px;
  scrollbar-width: thin;
  scrollbar-color: var(--apo-accent-border) transparent;
}

.apo__track {
  display: flex;
  gap: 8px;
  min-width: min-content;
}

.apo-step {
  position: relative;
  flex: 0 0 auto;
  width: 94px;
  padding: 8px 6px 10px;
  border-radius: var(--app-radius-sm, 8px);
  border: 1px solid var(--app-border);
  background: var(--apo-surface);
  transition:
    border-color var(--app-transition, 0.18s ease),
    box-shadow var(--app-transition, 0.18s ease),
    opacity var(--app-transition, 0.18s ease),
    background var(--app-transition, 0.18s ease);
}

.apo-step__ix {
  font-size: 10px;
  font-weight: 800;
  color: var(--apo-text-muted);
}

.apo-step__label {
  margin-top: 2px;
  font-size: 11px;
  line-height: 1.35;
  font-weight: 700;
  color: var(--apo-text);
}

.apo-step__desc {
  margin-top: 3px;
  font-size: 9.5px;
  line-height: 1.35;
  color: var(--apo-text-muted);
}

.apo-step__ok {
  position: absolute;
  top: 4px;
  right: 4px;
  font-size: 10px;
  color: var(--apo-success);
  font-weight: 800;
}

.apo-step--current {
  border-color: var(--apo-accent-border);
  background: var(--apo-accent-dim);
  box-shadow: 0 0 0 1px var(--apo-accent-border);
}

.apo-step--current .apo-step__ix,
.apo-step--current .apo-step__label {
  color: var(--apo-accent);
}

.apo-step--done {
  opacity: 0.95;
  border-color: color-mix(in srgb, var(--apo-success) 28%, var(--app-border));
  background: color-mix(in srgb, var(--apo-success) 6%, var(--apo-surface));
}

.apo-step--done .apo-step__ix {
  color: var(--apo-success);
}

.apo-step--pending {
  opacity: 0.58;
}

.apo-step--muted {
  opacity: 0.48;
}

.apo-current {
  margin-top: 8px;
  padding: 7px 10px;
  border-radius: var(--app-radius-sm, 8px);
  border: 1px solid var(--apo-accent-border);
  background: color-mix(in srgb, var(--apo-accent) 6%, var(--apo-surface));
  display: flex;
  align-items: baseline;
  gap: 8px;
}

.apo-current__label {
  flex: 0 0 auto;
  font-size: 10px;
  font-weight: 800;
  color: var(--apo-accent);
}

.apo-current__text {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 11px;
  color: var(--apo-text-secondary);
}

@keyframes apo-pulse {
  0%,
  100% {
    opacity: 1;
  }
  50% {
    opacity: 0.55;
  }
}
</style>
