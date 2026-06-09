<template>
  <div v-if="isVisible" class="ap-stream">
    <div class="stream-header">
      <span class="pulse-dot"></span>
      正在生成第 {{ chapterNumber }} 章 · {{ stageLabel }}
      <span class="word-count">{{ wordCount }} 字</span>
    </div>
    <div ref="streamEl" class="stream-body">
      <div class="stream-text">{{ displayContent }}</div>
      <span class="cursor">▋</span>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, nextTick } from 'vue'
import { chapterApi } from '../../api/chapter'
import { runtimePerformance } from '../../config/performance'
import { usePolling } from '../../composables/usePolling'

const props = defineProps({
  novelId: String,
  currentStage: String,
  completedChapters: Number,
  currentBeatIndex: Number,
})

const isVisible = computed(() => props.currentStage === 'writing')
const displayContent = ref('')
const chapterNumber = ref(0)
const beatIndex = computed(() => props.currentBeatIndex || 0)
const wordCount = computed(() => displayContent.value.length)

const stageLabel = computed(() => '正文撰写中')
const streamEl = ref(null)

async function fetchLatestDraft() {
  // 取最新 draft 章节的内容
  const ch = await chapterApi.getLatestDraftChapter(props.novelId)
  if (ch) {
    displayContent.value = ch.content || ''
    chapterNumber.value = ch.number
    // 自动滚到底
    await nextTick()
    if (streamEl.value) {
      streamEl.value.scrollTop = streamEl.value.scrollHeight
    }
  }
}

const polling = usePolling(fetchLatestDraft, runtimePerformance.autopilotPanel.draftStreamPollMs)

watch(() => props.currentStage, (stage) => {
  if (stage === 'writing') {
    polling.restart({ immediate: true })
  } else {
    polling.stop()
  }
}, { immediate: true })
</script>

<style scoped>
.ap-stream {
  background: var(--card-color);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  overflow: hidden;
  font-family: 'Courier New', monospace;
}
.stream-header {
  display: flex; align-items: center; gap: 8px;
  padding: 8px 14px;
  background: var(--card-color); border-bottom: 1px solid var(--border-color);
  font-size: 12px; color: var(--text-color-2);
}
.pulse-dot {
  width: 7px; height: 7px; border-radius: 50%;
  background: #18a058;
  animation: pulse 1s infinite;
}
@keyframes pulse { 0%,100%{opacity:1} 50%{opacity:.3} }
.word-count { margin-left: auto; color: var(--text-color-3); }
.stream-body {
  height: 200px; overflow-y: auto;
  padding: 12px 16px;
}
.stream-text { color: var(--text-color-1); font-size: 13px; line-height: 1.8; white-space: pre-wrap; }
.cursor { color: #18a058; animation: blink 1s step-end infinite; }
@keyframes blink { 50%{opacity:0} }
</style>
