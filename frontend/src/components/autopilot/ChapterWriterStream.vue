<template>
  <div v-if="isVisible" class="chapter-writer-stream">
    <div class="stream-header">
      <span class="pulse-dot"></span>
      <span class="header-text">
        正在生成第 {{ chapterNumber }} 章
        <span v-if="beatIndex > 0" class="beat-badge">节拍 {{ beatIndex }}</span>
      </span>
      <span class="word-count">{{ wordCount }} 字</span>
    </div>
    <div ref="contentEl" class="stream-content">
      <pre class="content-text">{{ displayContent }}</pre>
      <span class="cursor">▋</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onUnmounted, nextTick } from 'vue'
import { subscribeChapterStream } from '../../api/config'

const props = defineProps<{
  novelId: string
  isWriting: boolean
}>()

const emit = defineEmits<{
  (e: 'content-update', data: { chapterNumber: number; content: string; wordCount: number }): void
}>()

const isVisible = computed(() => props.isWriting)
const displayContent = ref('')
const chapterNumber = ref(0)
const beatIndex = ref(0)
const wordCount = computed(() => displayContent.value.length)
const contentEl = ref<HTMLElement | null>(null)

let abortCtrl: AbortController | null = null

function startStream() {
  if (abortCtrl) {
    abortCtrl.abort()
  }

  displayContent.value = ''
  chapterNumber.value = 0
  beatIndex.value = 0

  abortCtrl = subscribeChapterStream(props.novelId, {
    onChapterStart: (num) => {
      chapterNumber.value = num
      displayContent.value = ''
      beatIndex.value = 0
    },
    // 🔥 流式增量文字：直接追加显示
    onChapterChunk: (chunk, beatIdx) => {
      displayContent.value += chunk
      beatIndex.value = beatIdx

      // 自动滚动到底部
      nextTick(() => {
        if (contentEl.value) {
          contentEl.value.scrollTop = contentEl.value.scrollHeight
        }
      })
    },
    onChapterContent: (data) => {
      chapterNumber.value = data.chapterNumber
      // 兜底：如果增量漏了，用完整内容覆盖
      if (data.content && data.content.length > displayContent.value.length) {
        displayContent.value = data.content
      }
      beatIndex.value = data.beatIndex

      // 向父组件发送内容更新
      emit('content-update', {
        chapterNumber: data.chapterNumber,
        content: displayContent.value,
        wordCount: displayContent.value.length
      })
    },
    onAutopilotStopped: () => {
      // 停止时清理
    },
    onError: (err) => {
      console.error('Chapter stream error:', err)
    }
  })
}

function stopStream() {
  if (abortCtrl) {
    abortCtrl.abort()
    abortCtrl = null
  }
}

watch(
  () => props.isWriting,
  (writing) => {
    if (writing) {
      startStream()
    } else {
      stopStream()
    }
  },
  { immediate: true }
)

onUnmounted(() => {
  stopStream()
})
</script>

<style scoped>
.chapter-writer-stream {
  background: var(--card-color);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  overflow: hidden;
  margin-top: 8px;
  font-family: var(--font-mono);
}

.stream-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 14px;
  background: linear-gradient(135deg, rgba(24, 160, 88, 0.08) 0%, rgba(24, 160, 88, 0.02) 100%);
  border-bottom: 1px solid var(--border-color);
  font-size: 12px;
  color: var(--text-color-2);
}

.pulse-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #18a058;
  animation: pulse 1s infinite;
  flex-shrink: 0;
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.3; }
}

.header-text {
  flex: 1;
  display: flex;
  align-items: center;
  gap: 8px;
}

.beat-badge {
  font-size: 10px;
  padding: 1px 6px;
  border-radius: 4px;
  background: rgba(24, 160, 88, 0.15);
  color: #18a058;
}

.word-count {
  color: var(--text-color-3);
  font-variant-numeric: tabular-nums;
}

.stream-content {
  height: 200px;
  overflow-y: auto;
  padding: 12px 16px;
  position: relative;
}

.content-text {
  margin: 0;
  white-space: pre-wrap;
  word-wrap: break-word;
  font-size: 13px;
  line-height: 1.8;
  color: var(--text-color-1);
}

.cursor {
  color: #18a058;
  animation: blink 1s step-end infinite;
  font-size: 14px;
}

@keyframes blink {
  50% { opacity: 0; }
}
</style>
