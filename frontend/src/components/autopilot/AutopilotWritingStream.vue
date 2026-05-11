<template>
  <div class="writing-stream-shell">
    <!-- 流式中：保持原有生成条；间隙/规划/等待首包：同一位置展示「运行态」占位，避免大块空白闪烁 -->
    <div v-if="isStreaming" class="writing-stream-bar mode-streaming">
    <div class="stream-header-line">
      <span class="stream-info">
        正在生成第 {{ writingChapterNumber }} 章
        <span v-if="writingChapterNumber > 0" class="beat-badge">节拍 {{ (writingBeatIndex || 0) + 1 }}</span>
        <span v-if="substepLabel" class="substep-indicator" :class="substepClass">{{ substepLabel }}</span>
      </span>
      <span class="stream-stats">
        <template v-if="chapterTarget > 0">
          <span class="stats-plan">目标 {{ chapterTarget }} 字/章</span>
          <span class="stats-detail">
            · 已定稿 {{ lockedWords }} 字
            <span v-if="streamOverflow > 0" class="stats-extra"> · 流式 +{{ streamOverflow }}（节拍末收束）</span>
          </span>
        </template>
        <template v-else>
          {{ writingWordCount }} 字
        </template>
        <span v-if="writingSpeed > 0" class="speed"> · 约 {{ writingSpeed }} 字/秒</span>
      </span>
    </div>
    <div v-if="chapterTarget > 0 && writingWordCount > 0" class="stream-progress-bar">
      <div class="stream-progress-fill" :class="{ 'is-over': progressOverTarget }" :style="{ width: progressBarWidth + '%' }"></div>
      <span class="stream-progress-label">{{ progressBarLabel }}</span>
    </div>
    <div ref="scrollContainer" class="stream-content-preview">
      <pre class="content-text">{{ displayedText }}<span class="cursor-inline">▋</span></pre>
    </div>
  </div>

  <div v-else class="writing-stream-bar mode-idle">
    <div class="idle-top">
      <div class="idle-headline">
        <span class="idle-glow-dot" aria-hidden="true" />
        <span class="idle-title">{{ idleTitle }}</span>
        <span v-if="idleBeatTag" class="beat-badge beat-badge-muted">{{ idleBeatTag }}</span>
        <span v-if="substepLabel" class="substep-indicator substep-indicator-soft" :class="substepClass">{{
          substepLabel
        }}</span>
      </div>
      <div class="idle-subline">
        <span v-if="showRunnerStageInIdle" class="idle-stage">{{ runnerStageLabelDisplay }}</span>
        <span v-if="showRunnerStageInIdle && chapterTarget > 0" class="idle-dot" aria-hidden="true">·</span>
        <template v-if="chapterTarget > 0">
          <span class="idle-metrics"
            >目标 {{ chapterTarget }} 字/章<span v-if="lockedWords > 0"> · 已定稿 {{ lockedWords }} 字</span></span
          >
        </template>
      </div>
      <p v-if="idleBeatFocusLine" class="idle-beat-focus">{{ idleBeatFocusLine }}</p>
    </div>
    <div v-if="chapterTarget > 0 && displayChapter > 0" class="stream-progress-bar idle-track">
      <div
        class="stream-progress-fill idle-fill"
        :class="{ 'is-over': progressOverTargetIdle }"
        :style="{ width: idleProgressWidth + '%' }"
      ></div>
      <span class="stream-progress-label">{{ idleProgressLabel }}</span>
    </div>
    <div class="idle-body">
      <p v-if="idleBodyPrimary" class="idle-lead">{{ idleBodyPrimary }}</p>
      <p class="idle-hint">{{ idleHint }}</p>
      <div class="idle-skeleton" aria-hidden="true">
        <span class="sk-line" />
        <span class="sk-line sk-mid" />
        <span class="sk-line sk-short" />
      </div>
    </div>
  </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, nextTick, onUnmounted } from 'vue'

const props = withDefaults(
  defineProps<{
    writingContent?: string
    writingChapterNumber?: number
    writingBeatIndex?: number
    /** ★ V9 细化字段 */
    writingSubstep?: string
    writingSubstepLabel?: string
    totalBeats?: number
    accumulatedWords?: number
    chapterTargetWords?: number
    beatFocus?: string
    contextTokens?: number
    /** 顶栏阶段文案（与全托管头一致）；空闲区默认不再重复同一行，避免与顶栏双显 */
    runnerStageLabel?: string
    /** 是否在空闲占位条中再次展示阶段文案（默认 false，与顶栏去重） */
    showRunnerStageInIdle?: boolean
    /** 后端当前章序号，SSE 尚未带上章节时用于展示 */
    statusChapterNumber?: number | null
  }>(),
  {
    showRunnerStageInIdle: false,
  }
)

const scrollContainer = ref<HTMLElement | null>(null)
const sessionStartTime = ref(0)
const sessionStartWordCount = ref(0)
const writingSpeed = ref(0)
const lastContentLength = ref(0)

// 🔥 打字机效果
const displayedText = ref('')
const pendingText = ref('')
let typewriterTimer: ReturnType<typeof setInterval> | null = null
const TYPEWRITER_SPEED = 30 // 每 30ms 显示一个字符

const isStreaming = computed(
  () =>
    !!props.writingContent &&
    props.writingContent.length > 0 &&
    (props.writingChapterNumber || 0) > 0
)
const writingWordCount = computed(() => props.writingContent?.length || 0)
const writingChapterNumber = computed(() => props.writingChapterNumber || 0)
const writingBeatIndex = computed(() => props.writingBeatIndex || 0)

/** 本章目标字数（与后端 chapter_target_words 一致） */
const chapterTarget = computed(() => Math.max(0, Number(props.chapterTargetWords || 0)))
/** 已完成节拍落稿字数（流式中可能小于当前缓冲总长） */
const lockedWords = computed(() => Math.max(0, Number(props.accumulatedWords || 0)))
/** 当前节拍流式超出已定稿的部分（模型常写超，再在节拍末收束） */
const streamOverflow = computed(() => Math.max(0, writingWordCount.value - lockedWords.value))

const displayChapter = computed(() => {
  const w = props.writingChapterNumber || 0
  if (w > 0) return w
  const s = props.statusChapterNumber
  return typeof s === 'number' && s > 0 ? s : 0
})

const idleTitle = computed(() => (displayChapter.value > 0 ? `第 ${displayChapter.value} 章` : '全托管运行中'))

const idleBeatTag = computed(() => {
  const tb = props.totalBeats || 0
  const bi = (props.writingBeatIndex || 0) + 1
  if (tb > 0) return `节拍 ${bi} / ${tb}`
  if (displayChapter.value > 0 && bi > 0) return `节拍 ${bi}`
  return ''
})

const runnerStageLabelDisplay = computed(() => (props.runnerStageLabel || '').trim() || '同步状态…')

const idleBodyPrimary = computed(() => {
  const sub = (props.writingSubstepLabel || '').trim()
  const stage = (props.runnerStageLabel || '').trim()
  if (sub && stage && sub !== stage) return sub
  return ''
})

const beatFocusTrim = computed(() => (props.beatFocus || '').trim())

const PLANNING_SUBSTEPS = new Set(['macro_planning', 'act_planning'])

/** 顶栏已显示阶段名时：仅在宏观/幕级规划子步骤下补充节拍焦点，避免写作等阶段误显旧 focus */
const idleBeatFocusLine = computed(() => {
  const sub = props.writingSubstep || ''
  if (!PLANNING_SUBSTEPS.has(sub)) return ''
  const focus = beatFocusTrim.value
  if (!focus) return ''
  const subLabel = (props.writingSubstepLabel || '').trim()
  if (subLabel && focus === subLabel) return ''
  const lead = idleBodyPrimary.value
  if (lead && focus === lead) return ''
  const stage = (props.runnerStageLabel || '').trim()
  if (stage && focus === stage) return ''
  return focus
})

const idleHint = computed(() => {
  const fallback = '等待流式正文或节拍收束…'
  const subPrimary = idleBodyPrimary.value
  if (!props.showRunnerStageInIdle) {
    if (subPrimary) return '流式正文将出现在下方；当前阶段见顶栏。'
    return fallback
  }
  if (subPrimary) return runnerStageLabelDisplay.value
  return runnerStageLabelDisplay.value || fallback
})

const idleProgressWidth = computed(() => {
  const target = chapterTarget.value
  if (target <= 0) return 0
  const acc = lockedWords.value
  return Math.min(100, Math.round((acc / target) * 100))
})

const progressOverTargetIdle = computed(
  () => chapterTarget.value > 0 && lockedWords.value > chapterTarget.value * 1.02
)

const idleProgressLabel = computed(() => {
  const t = chapterTarget.value
  if (t <= 0) return ''
  const acc = lockedWords.value
  const pct = idleProgressWidth.value
  return `${acc}/${t}（${pct}%）`
})

/** ★ V9 子步骤标签 */
const substepLabel = computed(() => props.writingSubstepLabel || '')

/** ★ V9 子步骤配色 */
const substepClass = computed(() => {
  const sub = props.writingSubstep || ''
  if (sub === 'llm_calling') return 'substep-active'
  if (sub === 'context_assembly' || sub === 'beat_magnification' || sub === 'chapter_found') return 'substep-prepare'
  if (sub === 'soft_landing' || sub === 'persisting' || sub === 'continuity_check' || sub === 'chapter_persist') return 'substep-finish'
  if (sub.startsWith('audit_')) return 'substep-audit'
  if (sub.endsWith('_planning')) return 'substep-plan'
  return ''
})

/** 相对本章目标的进度（按流式总长，封顶 100% 条宽） */
const progressPct = computed(() => {
  const target = chapterTarget.value
  if (target <= 0) return 0
  const live = writingWordCount.value
  return Math.min(100, Math.round((live / target) * 100))
})

const progressOverTarget = computed(
  () => chapterTarget.value > 0 && writingWordCount.value > chapterTarget.value * 1.02
)

const progressBarWidth = computed(() => progressPct.value)

const progressBarLabel = computed(() => {
  const t = chapterTarget.value
  if (t <= 0) return ''
  const live = writingWordCount.value
  const acc = lockedWords.value
  if (live <= Math.ceil(t * 1.03)) {
    return `${live}/${t}（${progressPct.value}%）`
  }
  return `收束中 ${live} 字 → 约 ${t}（已定 ${acc}）`
})

// 🔥 打字机效果：从 displayedText 逐字追赶到 writingContent
function startTypewriter() {
  if (typewriterTimer) return
  typewriterTimer = setInterval(() => {
    if (!props.writingContent) return
    const target = props.writingContent
    const current = displayedText.value

    if (current.length < target.length) {
      // 每次追加 1-3 个字符（加快追赶速度）
      const charsToAdd = Math.min(3, target.length - current.length)
      displayedText.value = target.slice(0, current.length + charsToAdd)

      // 自动滚动
      nextTick(() => {
        if (scrollContainer.value) {
          scrollContainer.value.scrollTop = scrollContainer.value.scrollHeight
        }
      })
    }
  }, TYPEWRITER_SPEED)
}

function stopTypewriter() {
  if (typewriterTimer) {
    clearInterval(typewriterTimer)
    typewriterTimer = null
  }
}

watch(
  () => props.writingContent,
  (content) => {
    if (!content) {
      sessionStartTime.value = 0
      sessionStartWordCount.value = 0
      writingSpeed.value = 0
      lastContentLength.value = 0
      displayedText.value = ''
      stopTypewriter()
      return
    }

    const now = Date.now()
    const currentCount = content.length

    if (sessionStartTime.value === 0) {
      sessionStartTime.value = now
      sessionStartWordCount.value = currentCount
    }

    const totalSeconds = (now - sessionStartTime.value) / 1000
    const totalWords = currentCount - sessionStartWordCount.value
    if (totalSeconds >= 1 && totalWords > 0) {
      writingSpeed.value = Math.round(totalWords / totalSeconds)
    }

    // 🔥 启动打字机效果
    if (currentCount > lastContentLength.value) {
      startTypewriter()
    }
    lastContentLength.value = currentCount
  }
)

watch(
  () => props.writingChapterNumber,
  () => {
    displayedText.value = ''
    lastContentLength.value = 0
    sessionStartTime.value = 0
    sessionStartWordCount.value = 0
    writingSpeed.value = 0
    stopTypewriter()
  }
)

onUnmounted(() => {
  stopTypewriter()
})
</script>

<style scoped>
.writing-stream-shell {
  margin-top: 4px;
}

.writing-stream-bar {
  background: linear-gradient(
    135deg,
    var(--color-success-light, rgba(34, 197, 94, 0.06)) 0%,
    transparent 100%
  );
  border: 1px solid color-mix(in srgb, var(--color-success, #22c55e) 20%, transparent);
  border-radius: 6px;
  overflow: hidden;
}

.stream-header-line {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  font-size: 12px;
}

.stream-cursor {
  color: var(--color-success, #22c55e);
  animation: blink 1s step-end infinite;
  font-size: 14px;
}

@keyframes blink {
  50% {
    opacity: 0;
  }
}

.stream-info {
  flex: 1;
  color: var(--text-color-2);
  display: flex;
  align-items: center;
  gap: 6px;
}

.beat-badge {
  padding: 1px 6px;
  border-radius: 4px;
  background: var(--color-success-light, rgba(34, 197, 94, 0.15));
  color: var(--color-success, #22c55e);
  font-size: 12px;
}

/* ★ V9 子步骤徽章 */
.substep-indicator {
  padding: 1px 6px;
  border-radius: 4px;
  font-size: 10px;
  font-weight: 600;
  background: rgba(99, 102, 241, 0.12);
  color: #6366f1;
}

.substep-indicator.substep-active {
  background: rgba(34, 197, 94, 0.15);
  color: #16a34a;
  animation: pulse-sub 2s infinite;
}

.substep-indicator.substep-prepare {
  background: rgba(59, 130, 246, 0.12);
  color: #3b82f6;
}

.substep-indicator.substep-finish {
  background: rgba(249, 115, 22, 0.12);
  color: #f97316;
}

.substep-indicator.substep-audit {
  background: rgba(234, 179, 8, 0.12);
  color: #ca8a04;
}

.substep-indicator.substep-plan {
  background: rgba(59, 130, 246, 0.12);
  color: #3b82f6;
}

@keyframes pulse-sub {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.65; }
}

/* ★ V9 字数进度条 */
.stream-progress-bar {
  position: relative;
  height: 14px;
  background: rgba(0, 0, 0, 0.04);
  overflow: hidden;
}

.stream-progress-fill {
  height: 100%;
  background: linear-gradient(90deg, rgba(34, 197, 94, 0.25), rgba(34, 197, 94, 0.45));
  transition: width 0.5s ease;
}

.stream-progress-fill.is-over {
  background: linear-gradient(90deg, rgba(234, 179, 8, 0.35), rgba(249, 115, 22, 0.45));
}

.stream-progress-label {
  position: absolute;
  right: 6px;
  top: 50%;
  transform: translateY(-50%);
  font-size: 9px;
  font-weight: 600;
  color: rgba(0, 0, 0, 0.4);
  font-variant-numeric: tabular-nums;
}

.stream-stats {
  color: var(--text-color-3);
  font-variant-numeric: tabular-nums;
  text-align: right;
  max-width: 56%;
  line-height: 1.35;
}

.stats-plan {
  color: var(--text-color-2);
  font-weight: 600;
}

.stats-detail {
  font-weight: 400;
}

.stats-extra {
  color: #b45309;
  font-size: 11px;
}

.speed {
  color: var(--color-success, #22c55e);
}

.stream-content-preview {
  max-height: 140px;
  overflow-y: auto;
  padding: 6px 10px;
  border-top: 1px solid rgba(24, 160, 88, 0.1);
  background: rgba(0, 0, 0, 0.02);
}

.content-text {
  margin: 0;
  white-space: pre-wrap;
  word-wrap: break-word;
  font-size: 12px;
  line-height: 1.7;
  color: var(--text-color-2);
  font-family: var(--font-mono);
}

.cursor-inline {
  color: #18a058;
  animation: blink 1s step-end infinite;
  font-size: 13px;
}

/* 非流式间隙：与全托管顶栏呼应的品牌紫蓝占位，避免空白跳变 */
.writing-stream-bar.mode-idle {
  background: linear-gradient(
    135deg,
    color-mix(in srgb, var(--color-brand, #2563eb) 10%, transparent) 0%,
    color-mix(in srgb, var(--color-purple, #8b5cf6) 6%, transparent) 100%
  );
  border: 1px solid color-mix(in srgb, var(--color-brand, #2563eb) 24%, transparent);
}

.idle-top {
  padding: 10px 12px 6px;
}

.idle-headline {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  margin-bottom: 4px;
}

.idle-title {
  font-size: 13px;
  font-weight: 700;
  letter-spacing: 0.03em;
  color: var(--app-text-primary, #0f172a);
}

.idle-glow-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
  background: linear-gradient(135deg, var(--color-brand, #2563eb), var(--color-purple, #8b5cf6));
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--color-brand, #2563eb) 18%, transparent);
  animation: idle-dot-pulse 2s ease-in-out infinite;
}

@keyframes idle-dot-pulse {
  0%,
  100% {
    opacity: 1;
    transform: scale(1);
  }
  50% {
    opacity: 0.8;
    transform: scale(0.94);
  }
}

.beat-badge-muted {
  background: color-mix(in srgb, var(--color-brand, #2563eb) 14%, transparent);
  color: var(--color-brand, #2563eb);
}

.substep-indicator-soft {
  opacity: 0.95;
}

.idle-subline {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px 6px;
  font-size: 11px;
  line-height: 1.45;
  color: var(--app-text-secondary, #64748b);
}

.idle-stage {
  font-weight: 600;
  color: var(--app-text-secondary, #475569);
}

.idle-metrics {
  font-variant-numeric: tabular-nums;
}

.idle-beat-focus {
  margin: 3px 0 0;
  padding: 0;
  font-size: 10px;
  line-height: 1.45;
  color: var(--app-text-muted, #94a3b8);
  max-width: 100%;
  overflow: hidden;
  display: -webkit-box;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
  word-break: break-word;
}

.idle-dot {
  opacity: 0.45;
}

.idle-track .idle-fill {
  background: linear-gradient(90deg, rgba(37, 99, 235, 0.22), rgba(99, 102, 241, 0.38));
  transition: width 0.45s ease;
}

.idle-body {
  min-height: 104px;
  padding: 8px 12px 10px;
  border-top: 1px solid color-mix(in srgb, var(--color-brand, #2563eb) 12%, transparent);
  background: color-mix(in srgb, var(--app-surface, #fff) 88%, transparent);
}

.idle-lead {
  margin: 0 0 4px;
  font-size: 12px;
  font-weight: 600;
  color: var(--app-text-primary, #1e293b);
  line-height: 1.45;
}

.idle-hint {
  margin: 0 0 8px;
  font-size: 11px;
  color: var(--app-text-muted, #94a3b8);
  line-height: 1.5;
}

.idle-skeleton {
  display: flex;
  flex-direction: column;
  gap: 6px;
  max-height: 72px;
  overflow: hidden;
  opacity: 0.8;
}

.sk-line {
  display: block;
  height: 6px;
  border-radius: 3px;
  background: linear-gradient(
    90deg,
    rgba(15, 23, 42, 0.05) 0%,
    rgba(15, 23, 42, 0.09) 50%,
    rgba(15, 23, 42, 0.05) 100%
  );
  background-size: 220% 100%;
  animation: sk-wave 1.8s ease-in-out infinite;
}

.sk-mid {
  width: 92%;
}
.sk-short {
  width: 58%;
}

@keyframes sk-wave {
  0% {
    background-position: 120% 0;
  }
  100% {
    background-position: -120% 0;
  }
}
</style>
