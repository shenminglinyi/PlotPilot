<template>
  <n-modal
    v-model:show="visible"
    preset="card"
    title="📖 阅读模式"
    :style="modalStyle"
    :class="{ 'reading-modal-fullscreen': isFullscreen }"
    :segmented="{ content: true, footer: 'soft' }"
    :mask-closable="!isFullscreen"
  >
    <template #header-extra>
      <n-space :size="8">
        <n-button-group size="small">
          <n-button
            :disabled="!prevChapter"
            @click="goToPrevChapter"
          >
            ← 上一章
          </n-button>
          <n-button
            :disabled="!nextChapter"
            @click="goToNextChapter"
          >
            下一章 →
          </n-button>
        </n-button-group>
        <n-button-group size="small">
          <n-button
            :disabled="fontSize <= 14"
            @click="fontSize = Math.max(14, fontSize - 2)"
          >
            A-
          </n-button>
          <n-button
            :disabled="fontSize >= 28"
            @click="fontSize = Math.min(28, fontSize + 2)"
          >
            A+
          </n-button>
        </n-button-group>
        <n-button size="small" @click="toggleTheme">
          {{ theme === 'light' ? '🌙 深色' : '☀️ 浅色' }}
        </n-button>
        <n-button size="small" @click="toggleFullscreen">
          {{ isFullscreen ? '⛶ 退出全屏' : '⛶ 全屏' }}
        </n-button>
      </n-space>
    </template>

    <n-scrollbar ref="scrollbarRef" :style="scrollbarStyle">
      <div
        class="reading-container"
        :class="[`theme-${theme}`, { 'reading-container-fullscreen': isFullscreen }]"
        :style="{ fontSize: `${fontSize}px` }"
      >
        <div class="reading-header">
          <h2 class="reading-chapter-title">
            {{ chapterTitle }}
          </h2>
          <n-text depth="3" class="reading-word-count">
            字数: {{ wordCount }}
          </n-text>
        </div>
        <div class="reading-content">
          <div
            v-for="(paragraph, index) in paragraphs"
            :key="index"
            class="reading-paragraph"
          >
            {{ paragraph }}
          </div>
          <div v-if="paragraphs.length === 0" class="reading-empty">
            <n-empty description="暂无内容" />
          </div>
        </div>
      </div>
    </n-scrollbar>

    <template #footer>
      <n-space justify="end">
        <n-button @click="visible = false">关闭</n-button>
      </n-space>
    </template>
  </n-modal>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch, nextTick } from 'vue'

interface Chapter {
  id: number
  number: number
  title: string
  word_count: number
  content?: string
}

interface ReadingModeProps {
  show: boolean
  chapterTitle: string
  content: string
  chapters: Chapter[]
  currentChapterNumber: number
}

const props = defineProps<ReadingModeProps>()

const emit = defineEmits<{
  'update:show': [value: boolean]
  'chapter-change': [chapterNumber: number]
}>()

const visible = computed({
  get: () => props.show,
  set: (val) => emit('update:show', val)
})

const fontSize = ref(18)
const theme = ref<'light' | 'dark'>('light')
const isFullscreen = ref(false)
const scrollbarRef = ref<any>(null)

const modalStyle = computed(() => {
  if (isFullscreen.value) {
    return {
      width: '100vw',
      maxWidth: '100vw',
      height: '100vh',
      maxHeight: '100vh',
      borderRadius: 0
    }
  }
  return {
    width: 'min(900px, 96vw)',
    maxHeight: 'min(92vh, 900px)'
  }
})

const handleFullscreenChange = () => {
  isFullscreen.value = !!document.fullscreenElement
}

const scrollbarStyle = computed(() => {
  if (isFullscreen.value) {
    return {
      maxHeight: 'calc(100vh - 180px)',
      height: 'calc(100vh - 180px)'
    }
  }
  return {
    maxHeight: 'min(78vh, 760px)'
  }
})

const paragraphs = computed(() => {
  if (!props.content) return []
  return props.content
    .split('\n')
    .map(line => line.trim())
    .filter(line => line.length > 0)
})

const wordCount = computed(() => props.content?.length || 0)

const toggleTheme = () => {
  theme.value = theme.value === 'light' ? 'dark' : 'light'
}

const sortedChapters = computed(() => {
  return [...props.chapters].sort((a, b) => a.number - b.number)
})

const prevChapter = computed(() => {
  const index = sortedChapters.value.findIndex(ch => ch.number === props.currentChapterNumber)
  return index > 0 ? sortedChapters.value[index - 1] : null
})

const nextChapter = computed(() => {
  const index = sortedChapters.value.findIndex(ch => ch.number === props.currentChapterNumber)
  return index < sortedChapters.value.length - 1 ? sortedChapters.value[index + 1] : null
})

const goToPrevChapter = () => {
  if (prevChapter.value) {
    emit('chapter-change', prevChapter.value.number)
  }
}

const goToNextChapter = () => {
  if (nextChapter.value) {
    emit('chapter-change', nextChapter.value.number)
  }
}

const toggleFullscreen = async () => {
  if (!document.fullscreenElement) {
    try {
      await document.documentElement.requestFullscreen()
      isFullscreen.value = true
    } catch (err) {
      console.error('全屏失败:', err)
    }
  } else {
    try {
      await document.exitFullscreen()
      isFullscreen.value = false
    } catch (err) {
      console.error('退出全屏失败:', err)
    }
  }
}

const scrollToTop = () => {
  nextTick(() => {
    scrollbarRef.value?.scrollTo({ top: 0, left: 0 })
  })
}

watch(
  () => props.currentChapterNumber,
  () => {
    scrollToTop()
  }
)

watch(
  () => props.content,
  () => {
    scrollToTop()
  }
)

onMounted(() => {
  document.addEventListener('fullscreenchange', handleFullscreenChange)
})

onUnmounted(() => {
  document.removeEventListener('fullscreenchange', handleFullscreenChange)
})
</script>

<style scoped>
.reading-container {
  padding: 24px;
  min-height: 400px;
  transition: background-color 0.3s, color 0.3s;
}

.reading-container-fullscreen {
  padding: 40px 80px;
}

.theme-light {
  background-color: #faf8f5;
  color: #2d2d2d;
}

.theme-dark {
  background-color: #1a1a1a;
  color: #e0e0e0;
}

.reading-header {
  text-align: center;
  margin-bottom: 32px;
  padding-bottom: 16px;
  border-bottom: 1px solid rgba(0, 0, 0, 0.1);
}

.theme-dark .reading-header {
  border-bottom-color: rgba(255, 255, 255, 0.1);
}

.reading-chapter-title {
  margin: 0 0 8px 0;
  font-size: 1.5em;
  font-weight: 600;
}

.reading-word-count {
  font-size: 0.9em;
}

.reading-content {
  line-height: 1.9;
}

.reading-paragraph {
  margin-bottom: 1.5em;
  text-indent: 2em;
  text-align: justify;
}

.reading-empty {
  padding: 60px 0;
}
</style>

<style>
.reading-modal-fullscreen {
  top: 0 !important;
  left: 0 !important;
  right: 0 !important;
  bottom: 0 !important;
  padding: 0 !important;
  margin: 0 !important;
}

.reading-modal-fullscreen .n-card {
  border-radius: 0 !important;
  height: 100vh !important;
  max-height: 100vh !important;
  box-shadow: none !important;
}

.reading-modal-fullscreen .n-card__header {
  border-bottom: none !important;
}

.reading-modal-fullscreen .n-card__content {
  padding: 0 !important;
}
</style>
