<template>
  <div class="ce-panel">
    <n-empty v-if="!currentChapterNumber" description="请先从左侧选择一个章节" style="margin-top: 40px" />

    <n-scrollbar v-else class="ce-scroll">
      <n-space vertical :size="12" style="padding: 8px 4px 16px">
        <n-alert v-if="readOnly" type="warning" :show-icon="true" size="small">
          托管运行中：仅可查看
        </n-alert>

        <!-- 人物/地点/道具 -->
        <n-card size="small" :bordered="true" class="ce-card-elements">
          <template #header>
            <div class="ce-card-header-row">
              <span class="card-title">👥 人物 / 地点 / 道具</span>
              <n-space :size="6">
                <n-select
                  v-model:value="filterType"
                  :options="elementTypeOptions"
                  size="tiny"
                  style="width: 80px"
                  clearable
                  placeholder="类型"
                  @update:value="loadElements"
                />
                <n-button size="tiny" secondary :loading="loading" @click="loadElements">刷新</n-button>
              </n-space>
            </div>
          </template>
          <template #header-extra>
            <n-text depth="3" style="font-size: 11px">本章涉及的元素，来自叙事同步</n-text>
          </template>

          <n-spin :show="loading">
            <n-space vertical :size="8">
              <n-space v-if="groupedCharacters.length" vertical :size="6">
                <n-text strong class="ce-group-label">👤 人物</n-text>
                <n-space vertical :size="4">
                  <div v-for="elem in groupedCharacters" :key="elem.id" class="ce-item-readonly">
                    <n-text class="ce-element-name">{{ getElementDisplayName(elem.element_id, 'character') }}</n-text>
                    <n-tag size="tiny" round type="default">{{ relationLabel(elem.relation_type) }}</n-tag>
                    <n-tag :type="getImportanceType(elem.importance)" size="tiny" round>
                      {{ importanceLabel(elem.importance) }}
                    </n-tag>
                    <n-text v-if="elem.notes" depth="3" style="font-size: 12px; margin-left: 8px">
                      {{ elem.notes }}
                    </n-text>
                  </div>
                </n-space>
              </n-space>

              <n-space v-if="groupedLocations.length" vertical :size="6">
                <n-text strong class="ce-group-label">📍 地点</n-text>
                <n-space vertical :size="4">
                  <div v-for="elem in groupedLocations" :key="elem.id" class="ce-item-readonly">
                    <n-text class="ce-element-name">{{ getElementDisplayName(elem.element_id, 'location') }}</n-text>
                    <n-tag size="tiny" round type="default">{{ relationLabel(elem.relation_type) }}</n-tag>
                    <n-tag :type="getImportanceType(elem.importance)" size="tiny" round>
                      {{ importanceLabel(elem.importance) }}
                    </n-tag>
                    <n-text v-if="elem.notes" depth="3" style="font-size: 12px; margin-left: 8px">
                      {{ elem.notes }}
                    </n-text>
                  </div>
                </n-space>
              </n-space>

              <n-space v-if="groupedOther.length" vertical :size="6">
                <n-text strong class="ce-group-label">📦 其他</n-text>
                <n-space vertical :size="4">
                  <div v-for="elem in groupedOther" :key="elem.id" class="ce-item-readonly">
                    <n-tag :type="elemTypeColor(elem.element_type)" size="tiny" round>
                      {{ elemTypeLabel(elem.element_type) }}
                    </n-tag>
                    <n-text class="ce-element-name">{{ getElementDisplayName(elem.element_id, elem.element_type) }}</n-text>
                    <n-tag size="tiny" round type="default">{{ relationLabel(elem.relation_type) }}</n-tag>
                    <n-tag :type="getImportanceType(elem.importance)" size="tiny" round>
                      {{ importanceLabel(elem.importance) }}
                    </n-tag>
                    <n-text v-if="elem.notes" depth="3" style="font-size: 12px; margin-left: 8px">
                      {{ elem.notes }}
                    </n-text>
                  </div>
                </n-space>
              </n-space>

              <n-empty v-if="!loading && elements.length === 0" description="暂无关联元素" size="small" />
            </n-space>
          </n-spin>
        </n-card>

        <!-- 伏笔回收建议 -->
        <n-card size="small" :bordered="true">
          <template #header>
            <span class="card-title">🔗 伏笔回收建议</span>
          </template>
          <ForeshadowChapterSuggestionsPanel
            :slug="slug"
            :current-chapter-number="currentChapterNumber"
            :prefill-outline="chapterPlan?.outline || ''"
            embedded
            compact
            auto-run
          />
        </n-card>

        <!-- AI 审阅与质检 -->
        <n-card
          v-if="lastWorkflowResult && qcChapterNumber != null"
          size="small"
          :bordered="true"
        >
          <template #header>
            <span class="card-title">✨ AI 生成质检</span>
          </template>
          <n-space vertical :size="10">
            <n-alert
              v-if="currentChapterNumber !== qcChapterNumber"
              type="info"
              size="small"
            >
              为第 {{ qcChapterNumber }} 章质检结果
            </n-alert>

            <ConsistencyReportPanel
              :report="lastWorkflowResult.consistency_report"
              :token-count="lastWorkflowResult.token_count"
              @location-click="onLocationClick"
            />

            <n-collapse
              v-if="lastWorkflowResult.style_warnings && lastWorkflowResult.style_warnings.length > 0"
              class="qc-collapse"
            >
              <n-collapse-item :title="`俗套句式 ${lastWorkflowResult.style_warnings.length} 处`" name="cliche">
                <n-space vertical :size="6">
                  <n-alert
                    v-for="(w, i) in lastWorkflowResult.style_warnings"
                    :key="i"
                    :type="w.severity === 'warning' ? 'warning' : 'info'"
                    :title="w.pattern"
                    size="small"
                  >
                    「{{ w.text }}」
                  </n-alert>
                </n-space>
              </n-collapse-item>
            </n-collapse>

            <n-collapse v-if="ghostAnnotationLines.length > 0" class="qc-collapse">
              <n-collapse-item :title="`冲突批注 ${ghostAnnotationLines.length} 条`" name="ghost">
                <n-space vertical :size="6">
                  <n-alert
                    v-for="(line, gi) in ghostAnnotationLines"
                    :key="gi"
                    type="warning"
                    size="small"
                  >
                    {{ line }}
                  </n-alert>
                </n-space>
              </n-collapse-item>
            </n-collapse>
          </n-space>
        </n-card>
      </n-space>
    </n-scrollbar>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, onMounted, onUnmounted, computed } from 'vue'
import { storeToRefs } from 'pinia'
import { useWorkbenchRefreshStore } from '../../stores/workbenchRefreshStore'
import { useMessage } from 'naive-ui'
import { chapterElementApi } from '../../api/chapterElement'
import type { ChapterElementDTO, ElementType } from '../../api/chapterElement'
import { planningApi } from '../../api/planning'
import type { StoryNode } from '../../api/planning'
import { bibleApi, type CharacterDTO, type LocationDTO } from '../../api/bible'
import type { GenerateChapterWorkflowResponse } from '../../api/workflow'
import type { AutopilotChapterAudit } from './ChapterStatusPanel.vue'
import ForeshadowChapterSuggestionsPanel from './ForeshadowChapterSuggestionsPanel.vue'
import ConsistencyReportPanel from './ConsistencyReportPanel.vue'

const props = withDefaults(
  defineProps<{
    slug: string
    currentChapterNumber?: number | null
    readOnly?: boolean
    lastWorkflowResult?: GenerateChapterWorkflowResponse | null
    qcChapterNumber?: number | null
    autopilotChapterReview?: AutopilotChapterAudit | null
  }>(),
  {
    currentChapterNumber: null,
    readOnly: false,
    lastWorkflowResult: null,
    qcChapterNumber: null,
    autopilotChapterReview: null,
  }
)

const message = useMessage()

const elements = ref<ChapterElementDTO[]>([])
const loading = ref(false)
const storyNodeId = ref<string | null>(null)
const chapterPlan = ref<StoryNode | null>(null)
const filterType = ref<ElementType | undefined>(undefined)

// Bible 数据用于 ID -> name 映射
const bibleCharacters = ref<CharacterDTO[]>([])
const bibleLocations = ref<LocationDTO[]>([])

const elementTypeOptions = [
  { label: '人物', value: 'character' },
  { label: '地点', value: 'location' },
  { label: '道具', value: 'item' },
  { label: '组织', value: 'organization' },
  { label: '事件', value: 'event' },
]

const relationTypeOptions = [
  { label: '出场', value: 'appears' },
  { label: '提及', value: 'mentioned' },
  { label: '场景', value: 'scene' },
  { label: '使用', value: 'uses' },
  { label: '参与', value: 'involved' },
  { label: '发生', value: 'occurs' },
]

const importanceOptions = [
  { label: '主要', value: 'major' },
  { label: '一般', value: 'normal' },
  { label: '次要', value: 'minor' },
]

const elemTypeLabel = (t: string) => elementTypeOptions.find(o => o.value === t)?.label ?? t
const elemTypeColor = (t: string): 'error' | 'warning' | 'info' | 'success' | 'default' => {
  const map: Record<string, 'error' | 'warning' | 'info' | 'success' | 'default'> = {
    character: 'error', location: 'success', item: 'warning', organization: 'info', event: 'default'
  }
  return map[t] ?? 'default'
}

const importanceLabel = (i: string) => importanceOptions.find(o => o.value === i)?.label ?? i
const relationLabel = (r: string) => relationTypeOptions.find(o => o.value === r)?.label ?? r

const getImportanceType = (importance: string): 'error' | 'warning' | 'info' | 'success' | 'default' => {
  const map: Record<string, 'error' | 'warning' | 'info' | 'success' | 'default'> = {
    major: 'error',
    normal: 'info',
    minor: 'default'
  }
  return map[importance] || 'default'
}

// 获取元素显示名称（从 Bible 映射）
const getElementDisplayName = (elementId: string, type: string): string => {
  if (type === 'character') {
    const char = bibleCharacters.value.find(c => c.id === elementId)
    if (char) return char.name
  }
  if (type === 'location') {
    const loc = bibleLocations.value.find(l => l.id === elementId)
    if (loc) return loc.name
  }
  return elementId
}

const groupedCharacters = computed(() =>
  elements.value.filter(e => e.element_type === 'character')
)
const groupedLocations = computed(() =>
  elements.value.filter(e => e.element_type === 'location')
)
const groupedOther = computed(() =>
  elements.value.filter(e => e.element_type !== 'character' && e.element_type !== 'location')
)

const ghostAnnotationLines = computed(() => {
  const raw = props.lastWorkflowResult?.ghost_annotations
  if (!raw || !Array.isArray(raw) || raw.length === 0) return []
  const lines: string[] = []
  for (const item of raw) {
    if (item == null) continue
    if (typeof item === 'string') {
      lines.push(item)
      continue
    }
    if (typeof item === 'object') {
      const o = item as Record<string, unknown>
      const msg =
        (typeof o.message === 'string' && o.message) ||
        (typeof o.summary === 'string' && o.summary) ||
        (typeof o.text === 'string' && o.text) ||
        JSON.stringify(o)
      lines.push(msg)
    }
  }
  return lines
})

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
  if (!props.currentChapterNumber) {
    storyNodeId.value = null
    chapterPlan.value = null
    return
  }
  try {
    const res = await planningApi.getStructure(props.slug)
    const roots = res.data?.nodes ?? []
    const node = findChapterNode(roots, props.currentChapterNumber)
    if (node) {
      storyNodeId.value = node.id
      chapterPlan.value = node
    } else {
      storyNodeId.value = null
      chapterPlan.value = null
    }
  } catch {
    /* 保留上一份，避免 deskTick 抖动时整块清空 */
  }
}

const loadElements = async () => {
  if (!storyNodeId.value) return
  loading.value = true
  try {
    const res = await chapterElementApi.getElements(storyNodeId.value, filterType.value)
    elements.value = res.data
  } catch {
    message.error('加载章节元素失败')
  } finally {
    loading.value = false
  }
}

// 加载 Bible 数据用于名称映射
async function loadBible() {
  try {
    const bible = await bibleApi.getBible(props.slug)
    bibleCharacters.value = bible.characters || []
    bibleLocations.value = bible.locations || []
  } catch {
    bibleCharacters.value = []
    bibleLocations.value = []
  }
}

function onLocationClick(location: number) {
  message.info(`问题位置约在第 ${location} 字附近`)
}

watch(() => props.slug, async (slug) => {
  if (slug) {
    elements.value = []
    storyNodeId.value = null
    chapterPlan.value = null
    await Promise.all([
      loadBible(),
      resolveStoryNode(),
      loadElements()
    ])
  }
})

watch(() => props.currentChapterNumber, async () => {
  await resolveStoryNode()
  await loadElements()
}, { immediate: false })

const refreshStore = useWorkbenchRefreshStore()
const { deskTick } = storeToRefs(refreshStore)
let deskTickDebounce: ReturnType<typeof setTimeout> | null = null
const DESK_TICK_DEBOUNCE_MS = 450
watch(deskTick, () => {
  if (deskTickDebounce) clearTimeout(deskTickDebounce)
  deskTickDebounce = setTimeout(() => {
    deskTickDebounce = null
    void resolveStoryNode().then(() => loadElements())
  }, DESK_TICK_DEBOUNCE_MS)
})

onMounted(async () => {
  await loadBible()
  await resolveStoryNode()
  await loadElements()
})

onUnmounted(() => {
  if (deskTickDebounce) {
    clearTimeout(deskTickDebounce)
    deskTickDebounce = null
  }
})
</script>

<style scoped>
.ce-panel {
  padding: 0;
  height: 100%;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.ce-scroll {
  flex: 1;
  min-height: 0;
}

.card-title {
  font-size: 13px;
  font-weight: 600;
}

/* 元素分组标签 */
.ce-group-label {
  font-size: 12px;
  font-weight: 600;
  color: var(--n-text-color-1);
}

/* 元素卡片头部 */
.ce-card-header-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  width: 100%;
}

/* 只读元素项 */
.ce-item-readonly {
  display: flex;
  align-items: center;
  padding: 8px 12px;
  border-radius: 8px;
  background: var(--n-color-modal);
  border: 1px solid var(--n-border-color);
  transition: all 0.2s ease;
}

.ce-item-readonly:hover {
  border-color: var(--n-primary-color);
  background: rgba(99, 102, 241, 0.02);
}

.ce-element-name {
  font-size: 13px;
  font-weight: 500;
  color: var(--n-text-color-1);
  margin-right: 8px;
}

/* 质检折叠 */
.qc-collapse :deep(.n-collapse-item__header) {
  font-size: 12px;
}
</style>
