<template>
  <div v-if="isWritingContent" class="writing-stream-bar">
    <div class="stream-header-line">
      <span class="stream-info">
        正在生成第 {{ writingChapterNumber }} 章
        <span v-if="writingChapterNumber > 0" class="beat-badge">节拍 {{ (writingBeatIndex || 0) + 1 }}</span>
      </span>
      <span class="stream-stats">
        {{ writingWordCount }} 字
        <span v-if="writingSpeed > 0" class="speed">· {{ writingSpeed }} 字/秒</span>
      </span>
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
}

.beat-badge {
  margin-left: 6px;
  padding: 1px 6px;
  border-radius: 4px;
  background: var(--color-success-light, rgba(34, 197, 94, 0.15));
  color: var(--color-success, #22c55e);
  font-size: 12px;
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
