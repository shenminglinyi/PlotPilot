<template>
  <div v-if="isWritingContent" class="writing-stream-bar">
    <div class="stream-header-line">
      <span class="stream-info">
        正在生成第 {{ writingChapterNumber }} 章
        <span v-if="writingChapterNumber > 0" class="beat-badge">节拍 {{ (writingBeatIndex || 0) + 1 }}</span>
        <!-- ★ V9 子步骤徽章 -->
        <span v-if="substepLabel" class="substep-indicator" :class="substepClass">{{ substepLabel }}</span>
      </span>
      <span class="stream-stats">
        {{ writingWordCount }} 字
        <span v-if="writingSpeed > 0" class="speed">· {{ writingSpeed }} 字/秒</span>
      </span>
    </div>
    <!-- ★ V9 细化进度条 -->
    <div v-if="progressPct > 0" class="stream-progress-bar">
      <div class="stream-progress-fill" :style="{ width: progressPct + '%' }"></div>
      <span class="stream-progress-label">{{ progressPct }}%</span>
    </div>
    <div ref="scrollContainer" class="stream-content-preview">
      <pre class="content-text">{{ displayedText }}<span class="cursor-inline">▋</span></pre>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, nextTick, onUnmounted } from 'vue'

const props = defineProps<{
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
}>()

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

const isWritingContent = computed(
  () =>
    !!props.writingContent &&
    props.writingContent.length > 0 &&
    (props.writingChapterNumber || 0) > 0
)
const writingWordCount = computed(() => props.writingContent?.length || 0)
const writingChapterNumber = computed(() => props.writingChapterNumber || 0)
const writingBeatIndex = computed(() => props.writingBeatIndex || 0)

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

/** ★ V9 字数进度百分比 */
const progressPct = computed(() => {
  const acc = props.accumulatedWords || 0
  const target = props.chapterTargetWords || 0
  if (target <= 0 || acc <= 0) return 0
  return Math.min(100, Math.round(acc / target * 100))
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
.writing-stream-bar {
  margin-top: 4px;
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
</style>
