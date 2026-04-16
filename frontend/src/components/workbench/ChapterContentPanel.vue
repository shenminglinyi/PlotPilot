<template>
  <div class="cc-panel" ref="panelRef">
    <n-empty v-if="!currentChapterNumber" description="请先从左侧选择一个章节" style="margin-top: 40px" />

    <n-scrollbar v-else class="cc-scroll">
      <n-space vertical :size="12" style="padding: 8px 4px 16px">
        <n-alert v-if="readOnly" type="warning" :show-icon="true" size="small">
          托管运行中：仅可查看
        </n-alert>

        <!-- 正文内容 -->
        <n-card v-if="content" size="small" :bordered="true">
          <template #header>
            <span class="card-title">📖 正文内容</span>
          </template>
          <div
            class="cc-content-body"
            ref="contentBodyRef"
            @mouseup="handleMouseUp"
          >{{ content }}</div>
        </n-card>

        <!-- 本章规划 -->
        <n-card v-if="chapterPlan" size="small" :bordered="true" class="cc-card-plan">
          <template #header>
            <span class="card-title">📋 本章规划</span>
          </template>
          <n-descriptions :column="1" label-placement="left" size="small" label-style="white-space: nowrap">
            <n-descriptions-item label="标题">{{ chapterPlan.title || '—' }}</n-descriptions-item>
            <n-descriptions-item v-if="chapterPlan.outline" label="大纲">
              <n-text style="font-size: 12px; white-space: pre-wrap">{{ chapterPlan.outline }}</n-text>
            </n-descriptions-item>
            <n-descriptions-item v-if="chapterPlan.pov_character_id" label="视角">
              {{ getCharacterName(chapterPlan.pov_character_id) }}
            </n-descriptions-item>
            <n-descriptions-item v-if="chapterPlan.timeline_start || chapterPlan.timeline_end" label="时间线">
              {{ chapterPlan.timeline_start || '—' }} → {{ chapterPlan.timeline_end || '—' }}
            </n-descriptions-item>
            <n-descriptions-item v-if="planMoodLine" label="基调">
              {{ planMoodLine }}
            </n-descriptions-item>
          </n-descriptions>
        </n-card>

        <!-- 节拍规划 -->
        <n-card v-if="showBeatsCard" size="small" :bordered="true">
          <template #header>
            <span class="card-title">🎬 节拍规划</span>
          </template>
          <n-tabs type="segment" size="small" animated>
            <n-tab-pane name="macro" tab="宏观">
              <n-text depth="3" style="font-size: 11px; display: block; margin-bottom: 8px">
                来自章节大纲，用于叙事摘要和向量检索
              </n-text>
              <ol v-if="beatLines.length" class="cc-beat-list">
                <li v-for="(line, bi) in beatLines" :key="bi">{{ line }}</li>
              </ol>
              <n-empty v-else description="暂无宏观节拍" size="small" />
            </n-tab-pane>

            <n-tab-pane name="micro" tab="微观">
              <n-text depth="3" style="font-size: 11px; display: block; margin-bottom: 8px">
                写作时智能拆分，控制节奏和感官细节
              </n-text>
              <n-space v-if="microBeats.length" vertical :size="8" style="margin-top: 12px">
                <div v-for="(beat, i) in microBeats" :key="i" class="micro-beat-item">
                  <div class="micro-beat-header">
                    <n-tag :type="getBeatTypeColor(beat.focus)" size="small" round>
                      {{ beat.focus }}
                    </n-tag>
                    <n-text strong style="margin-left: 8px">Beat {{ i + 1 }}</n-text>
                    <n-text depth="3" style="margin-left: 8px; font-size: 12px">
                      ({{ beat.target_words }}字)
                    </n-text>
                  </div>
                  <div class="micro-beat-desc">{{ beat.description }}</div>
                </div>
              </n-space>
              <n-empty v-else description="章节生成时自动创建微观节拍" size="small" />
            </n-tab-pane>
          </n-tabs>
        </n-card>

        <!-- 本章总结 -->
        <n-card v-if="hasSummaryBlock" size="small" :bordered="true">
          <template #header>
            <span class="card-title">📝 本章总结</span>
          </template>
          <n-descriptions
            v-if="knowledgeChapter && (knowledgeChapter.summary || knowledgeChapter.key_events || knowledgeChapter.consistency_note)"
            :column="1"
            label-placement="left"
            size="small"
          >
            <n-descriptions-item v-if="knowledgeChapter.summary" label="摘要">
              <n-text style="font-size: 12px; white-space: pre-wrap">{{ knowledgeChapter.summary }}</n-text>
            </n-descriptions-item>
            <n-descriptions-item v-if="knowledgeChapter.key_events" label="关键事件">
              <n-text style="font-size: 12px; white-space: pre-wrap">{{ knowledgeChapter.key_events }}</n-text>
            </n-descriptions-item>
            <n-descriptions-item v-if="knowledgeChapter.consistency_note" label="一致性">
              <n-text style="font-size: 12px; white-space: pre-wrap">{{ knowledgeChapter.consistency_note }}</n-text>
            </n-descriptions-item>
          </n-descriptions>
          <n-text v-else-if="chapterPlan?.description" style="font-size: 12px; white-space: pre-wrap">
            {{ chapterPlan.description }}
          </n-text>
        </n-card>

        <n-alert v-else-if="storyNodeNotFound" type="warning" :show-icon="true">
          未在结构树中找到第 {{ currentChapterNumber }} 章的规划节点
        </n-alert>

        <!-- 全托管管线摘要 -->
        <n-card
          v-if="autopilotChapterReview && currentChapterNumber === autopilotChapterReview.chapter_number"
          size="small"
          :bordered="true"
        >
          <template #header>
            <span class="card-title">🤖 自动审阅</span>
          </template>
          <n-space vertical :size="8">
            <div class="review-row">
              <n-text depth="3">张力</n-text>
              <div class="tension-bar">
                <div class="tension-fill" :style="{ width: `${autopilotChapterReview.tension * 10}%` }"></div>
                <n-text class="tension-value">{{ autopilotChapterReview.tension }}/10</n-text>
              </div>
            </div>
            <div class="review-row">
              <n-text depth="3">叙事同步</n-text>
              <n-tag
                :type="autopilotChapterReview.narrative_sync_ok ? 'success' : 'warning'"
                size="small"
                round
              >
                {{ autopilotChapterReview.narrative_sync_ok ? '已落库' : '异常' }}
              </n-tag>
            </div>
            <div class="review-row">
              <n-text depth="3">文风相似度</n-text>
              <n-text>
                {{
                  autopilotChapterReview.similarity_score != null
                    ? Number(autopilotChapterReview.similarity_score).toFixed(3)
                    : '—'
                }}
              </n-text>
            </div>
            <div class="review-row">
              <n-text depth="3">漂移告警</n-text>
              <n-tag :type="autopilotChapterReview.drift_alert ? 'error' : 'success'" size="small" round>
                {{ autopilotChapterReview.drift_alert ? '是' : '否' }}
              </n-tag>
            </div>
            <div v-if="autopilotChapterReview.at" class="review-row">
              <n-text depth="3">审阅时间</n-text>
              <n-text depth="3" style="font-size: 12px">{{ formatTime(autopilotChapterReview.at) }}</n-text>
            </div>
          </n-space>
        </n-card>
      </n-space>
    </n-scrollbar>

    <!-- 浮动工具栏 -->
    <Teleport to="body">
      <div
        v-if="showToolbar && selectedText && !rewriteLoading && !showDiff"
        class="rewrite-toolbar"
        :style="toolbarStyle"
      >
        <n-button
          v-for="mode in rewriteModes"
          :key="mode"
          size="tiny"
          :type="activeMode === mode ? 'primary' : 'default'"
          @click="handleRewriteClick(mode)"
        >
          {{ REWRITE_MODE_LABELS[mode] }}
        </n-button>
      </div>
    </Teleport>

    <!-- Diff 视图弹窗 -->
    <n-modal
      v-model:show="showDiff"
      preset="card"
      title="改写结果对比"
      style="width: min(780px, 96vw); max-height: min(85vh, 800px)"
      :mask-closable="false"
    >
      <n-scrollbar style="max-height: min(70vh, 650px)">
        <div class="diff-container">
          <div class="diff-column">
            <div class="diff-label">原文</div>
            <div class="diff-content diff-old">{{ selectedText }}</div>
          </div>
          <div class="diff-column">
            <div class="diff-label">新文</div>
            <div class="diff-content diff-new">{{ rewrittenText }}</div>
          </div>
        </div>
      </n-scrollbar>
      <template #footer>
        <n-space justify="end">
          <n-button @click="handleReject">拒绝</n-button>
          <n-button type="primary" @click="handleAccept">接受</n-button>
        </n-space>
      </template>
    </n-modal>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, onMounted, computed, onBeforeUnmount, nextTick } from 'vue'
import { storeToRefs } from 'pinia'
import { useWorkbenchRefreshStore } from '../../stores/workbenchRefreshStore'
import { planningApi } from '../../api/planning'
import type { StoryNode } from '../../api/planning'
import { knowledgeApi } from '../../api/knowledge'
import type { ChapterSummary } from '../../api/knowledge'
import { bibleApi, type CharacterDTO } from '../../api/bible'
import type { AutopilotChapterAudit } from './ChapterStatusPanel.vue'
import {
  consumeRewriteStream,
  REWRITE_MODE_LABELS,
  type RewriteMode,
} from '../../api/rewrite'

const props = withDefaults(
  defineProps<{
    slug: string
    currentChapterNumber?: number | null
    readOnly?: boolean
    autopilotChapterReview?: AutopilotChapterAudit | null
    content?: string
  }>(),
  {
    currentChapterNumber: null,
    readOnly: false,
    autopilotChapterReview: null,
    content: '',
  }
)

const emit = defineEmits<{
  'content-replace': [original: string, replacement: string]
}>()

const panelRef = ref<HTMLElement | null>(null)
const contentBodyRef = ref<HTMLElement | null>(null)
const storyNodeNotFound = ref(false)
const chapterPlan = ref<StoryNode | null>(null)
const knowledgeChapter = ref<ChapterSummary | null>(null)
const bibleCharacters = ref<CharacterDTO[]>([])

const selectedText = ref('')
const showToolbar = ref(false)
const toolbarPos = ref({ x: 0, y: 0 })
const rewriteLoading = ref(false)
const showDiff = ref(false)
const rewrittenText = ref('')
const activeMode = ref<RewriteMode | null>(null)
const rewriteAbortCtrl = ref<AbortController | null>(null)

const rewriteModes: RewriteMode[] = ['rewrite', 'expand', 'shrink', 'polish', 'continue']

const toolbarStyle = computed(() => ({
  position: 'fixed' as const,
  left: `${toolbarPos.value.x}px`,
  top: `${toolbarPos.value.y}px`,
  zIndex: 9999,
}))

const getCharacterName = (charId: string): string => {
  const char = bibleCharacters.value.find(c => c.id === charId)
  return char ? char.name : charId
}

const planMoodLine = computed(() => {
  const m = chapterPlan.value?.metadata
  if (!m || typeof m !== 'object') return ''
  const mood = m.mood ?? m.emotion ?? m.tone
  if (typeof mood === 'string' && mood.trim()) return mood
  if (Array.isArray(m.moods) && m.moods.length) return m.moods.join('、')
  return ''
})

const beatLines = computed(() => {
  const k = knowledgeChapter.value
  if (k?.beat_sections?.length) {
    return k.beat_sections.map(s => String(s || '').trim()).filter(Boolean)
  }
  const ol = chapterPlan.value?.outline?.trim()
  if (!ol) return []
  return ol.split(/\n+/).map(s => s.trim()).filter(s => s.length > 0)
})

const showBeatsCard = computed(() => {
  if (!props.currentChapterNumber) return false
  if (beatLines.value.length > 0) return true
  return !!(chapterPlan.value?.outline?.trim() || knowledgeChapter.value)
})

interface MicroBeat {
  description: string
  target_words: number
  focus: string
}

const microBeats = computed<MicroBeat[]>(() => {
  const k = knowledgeChapter.value
  if (k?.micro_beats && Array.isArray(k.micro_beats)) {
    return k.micro_beats as MicroBeat[]
  }
  return []
})

const getBeatTypeColor = (focus: string): 'success' | 'warning' | 'error' | 'info' | 'default' => {
  const colorMap: Record<string, 'success' | 'warning' | 'error' | 'info' | 'default'> = {
    sensory: 'info',
    dialogue: 'success',
    action: 'warning',
    emotion: 'error',
  }
  return colorMap[focus] || 'default'
}

const hasSummaryBlock = computed(() => {
  if (!props.currentChapterNumber) return false
  const k = knowledgeChapter.value
  if (k && (k.summary?.trim() || k.key_events?.trim() || k.consistency_note?.trim())) return true
  return !!chapterPlan.value?.description?.trim()
})

function formatTime(t: string) {
  try {
    return new Date(t).toLocaleString('zh-CN', {
      month: 'numeric',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    })
  } catch {
    return t
  }
}

function findChapterNode(nodes: StoryNode[], num: number): StoryNode | null {
  for (const node of nodes) {
    if (node.node_type === 'chapter' && node.number === num) return node
    if (node.children?.length) {
      const found = findChapterNode(node.children, num)
      if (found) return found
    }
  }
  return null
}

const resolveStoryNode = async () => {
  chapterPlan.value = null
  storyNodeNotFound.value = false
  if (!props.currentChapterNumber) return
  try {
    const res = await planningApi.getStructure(props.slug)
    const roots = res.data?.nodes ?? []
    const node = findChapterNode(roots, props.currentChapterNumber)
    if (node) {
      chapterPlan.value = node
    } else {
      storyNodeNotFound.value = true
    }
  } catch {
    storyNodeNotFound.value = true
  }
}

async function loadKnowledgeChapter() {
  knowledgeChapter.value = null
  if (!props.slug || !props.currentChapterNumber) return
  try {
    const k = await knowledgeApi.getKnowledge(props.slug)
    const row = k.chapters?.find(c => c.chapter_id === props.currentChapterNumber)
    knowledgeChapter.value = row ?? null
  } catch {
    knowledgeChapter.value = null
  }
}

async function loadBible() {
  try {
    const bible = await bibleApi.getBible(props.slug)
    bibleCharacters.value = bible.characters || []
  } catch {
    bibleCharacters.value = []
  }
}

function handleMouseUp() {
  const sel = window.getSelection()
  if (!sel || sel.isCollapsed || !sel.toString().trim()) {
    showToolbar.value = false
    selectedText.value = ''
    return
  }
  const text = sel.toString().trim()
  if (!text) {
    showToolbar.value = false
    return
  }
  selectedText.value = text
  const range = sel.getRangeAt(0)
  const rect = range.getBoundingClientRect()
  const toolbarWidth = 280
  const toolbarHeight = 44
  let x = rect.left + rect.width / 2 - toolbarWidth / 2
  let y = rect.top - toolbarHeight - 8
  if (y < 8) {
    y = rect.bottom + 8
  }
  if (x < 8) x = 8
  if (x + toolbarWidth > window.innerWidth - 8) {
    x = window.innerWidth - toolbarWidth - 8
  }
  toolbarPos.value = { x, y }
  showToolbar.value = true
}

function closeToolbar() {
  showToolbar.value = false
  selectedText.value = ''
}

async function handleRewriteClick(mode: RewriteMode) {
  if (!selectedText.value || props.readOnly) return
  activeMode.value = mode
  showToolbar.value = false
  rewriteLoading.value = true
  rewrittenText.value = ''

  const ctrl = new AbortController()
  rewriteAbortCtrl.value = ctrl

  const contextText = props.content
    ? props.content.slice(0, Math.max(0, props.content.indexOf(selectedText.value)))
    : ''

  try {
    await consumeRewriteStream(
      {
        text: selectedText.value,
        mode,
        context: contextText.slice(-500),
      },
      {
        signal: ctrl.signal,
        onChunk: (chunk) => {
          rewrittenText.value += chunk
        },
        onDone: () => {
          rewriteLoading.value = false
          showDiff.value = true
        },
        onError: (msg) => {
          rewriteLoading.value = false
          rewrittenText.value = ''
          window.$message?.error(msg || '改写失败，请重试')
        },
      }
    )
  } catch {
    rewriteLoading.value = false
  } finally {
    rewriteAbortCtrl.value = null
  }
}

function handleAccept() {
  if (selectedText.value && rewrittenText.value) {
    emit('content-replace', selectedText.value, rewrittenText.value)
  }
  resetRewriteState()
}

function handleReject() {
  resetRewriteState()
}

function resetRewriteState() {
  showDiff.value = false
  rewrittenText.value = ''
  selectedText.value = ''
  activeMode.value = null
  rewriteLoading.value = false
}

function onDocumentClick(e: MouseEvent) {
  if (showToolbar.value && panelRef.value && !panelRef.value.contains(e.target as Node)) {
    closeToolbar()
  }
}

watch(() => props.slug, async (slug) => {
  if (slug) {
    chapterPlan.value = null
    storyNodeNotFound.value = false
    await Promise.all([
      loadBible(),
      resolveStoryNode(),
      loadKnowledgeChapter()
    ])
  }
})

watch(() => props.currentChapterNumber, async () => {
  await resolveStoryNode()
  await loadKnowledgeChapter()
}, { immediate: false })

const refreshStore = useWorkbenchRefreshStore()
const { deskTick } = storeToRefs(refreshStore)
watch(deskTick, async () => {
  await resolveStoryNode()
  await loadKnowledgeChapter()
})

onMounted(async () => {
  await loadBible()
  await resolveStoryNode()
  await loadKnowledgeChapter()
  document.addEventListener('mousedown', onDocumentClick)
})

onBeforeUnmount(() => {
  document.removeEventListener('mousedown', onDocumentClick)
  rewriteAbortCtrl.value?.abort()
})
</script>

<style scoped>
.cc-panel {
  padding: 0;
  height: 100%;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.cc-scroll {
  flex: 1;
  min-height: 0;
}

.card-title {
  font-size: 13px;
  font-weight: 600;
}

.cc-content-body {
  font-size: 14px;
  line-height: 1.9;
  white-space: pre-wrap;
  word-break: break-all;
  user-select: text;
  cursor: text;
  min-height: 60px;
  padding: 4px 0;
}

.cc-beat-list {
  margin: 8px 0 0;
  padding-left: 1.2em;
  font-size: 12px;
  line-height: 1.8;
}

.micro-beat-item {
  padding: 12px 14px;
  border-radius: 10px;
  background: linear-gradient(135deg, rgba(99, 102, 241, 0.04) 0%, rgba(139, 92, 246, 0.02) 100%);
  border: 1px solid rgba(99, 102, 241, 0.1);
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

.micro-beat-item:hover {
  border-color: rgba(99, 102, 241, 0.2);
  background: linear-gradient(135deg, rgba(99, 102, 241, 0.06) 0%, rgba(139, 92, 246, 0.04) 100%);
}

.micro-beat-header {
  display: flex;
  align-items: center;
  margin-bottom: 8px;
}

.micro-beat-desc {
  margin-top: 6px;
  padding-left: 12px;
  font-size: 13px;
  line-height: 1.6;
  color: var(--n-text-color-2);
  border-left: 2px solid var(--n-border-color);
}

.micro-beat-item:hover .micro-beat-desc {
  border-left-color: var(--n-primary-color);
}

.review-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
}

.tension-bar {
  position: relative;
  width: 100px;
  height: 20px;
  background: var(--n-color-modal);
  border-radius: 10px;
  overflow: hidden;
  border: 1px solid var(--n-border-color);
}

.tension-fill {
  height: 100%;
  background: linear-gradient(90deg, #10b981, #f59e0b, #ef4444);
  border-radius: 10px;
  transition: width 0.3s ease;
}

.tension-value {
  position: absolute;
  right: 8px;
  top: 50%;
  transform: translateY(-50%);
  font-size: 11px;
  font-weight: 600;
  color: var(--n-text-color-1);
}

.diff-container {
  display: flex;
  gap: 16px;
}

.diff-column {
  flex: 1;
  min-width: 0;
}

.diff-label {
  font-size: 13px;
  font-weight: 600;
  margin-bottom: 8px;
  color: var(--n-text-color-2);
}

.diff-content {
  font-size: 14px;
  line-height: 1.8;
  white-space: pre-wrap;
  word-break: break-all;
  padding: 12px;
  border-radius: 8px;
}

.diff-old {
  background: rgba(239, 68, 68, 0.06);
  border: 1px solid rgba(239, 68, 68, 0.15);
}

.diff-new {
  background: rgba(16, 185, 129, 0.06);
  border: 1px solid rgba(16, 185, 129, 0.15);
}
</style>

<style>
.rewrite-toolbar {
  display: flex;
  gap: 4px;
  padding: 6px 8px;
  background: var(--n-color-popover);
  border-radius: 8px;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.12), 0 1px 4px rgba(0, 0, 0, 0.08);
  border: 1px solid var(--n-border-color);
  transform: translateX(-50%);
}
</style>
