<template>
  <div v-if="isVisible" class="ap-stream">
    <div class="stream-header">
      <span class="pulse-dot"></span>
      正在生成第 {{ chapterNumber }} 章 · 节拍 {{ (beatIndex || 0) + 1 }}
      <span class="word-count">{{ wordCount }} 字</span>
    </div>
    <div ref="streamEl" class="stream-body">
      <div class="stream-text">{{ displayContent }}</div>
      <span class="cursor">▋</span>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onUnmounted, nextTick } from 'vue'

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
const streamEl = ref(null)

let pollTimer = null

async function fetchLatestDraft() {
  // 取最新 draft 章节的内容
  const res = await fetch(`/api/v1/novels/${props.novelId}/chapters?status=draft&limit=1`)
  if (!res.ok) return
  const data = await res.json()
  if (data.chapters?.length) {
    const ch = data.chapters[0]
    displayContent.value = ch.content || ''
    chapterNumber.value = ch.number
    // 自动滚到底
    await nextTick()
    if (streamEl.value) {
      streamEl.value.scrollTop = streamEl.value.scrollHeight
    }
  }
}

watch(() => props.currentStage, (stage) => {
  if (stage === 'writing') {
    pollTimer = setInterval(fetchLatestDraft, 5000)
    fetchLatestDraft()
  } else {
    clearInterval(pollTimer)
  }
}, { immediate: true })

onUnmounted(() => clearInterval(pollTimer))
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
