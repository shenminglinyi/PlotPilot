<template>
  <div class="coc-clue-panel">
    <header class="panel-header">
      <div class="header-main">
        <div class="title-row">
          <h3 class="panel-title">CoC线索</h3>
          <n-tag size="small" round :bordered="false">线索账本</n-tag>
        </div>
        <p class="panel-lead">
          记录线索可见范围、已知角色和可信度，按章节持续追踪线索的推进与揭示事件。
        </p>
      </div>
      <n-button size="small" type="primary" secondary :loading="loading" @click="loadOverview">
        刷新
      </n-button>
    </header>

    <div class="panel-content">
      <n-spin :show="loading">
        <n-alert v-if="loadError" type="error" :show-icon="true" class="section-alert">
          {{ loadError }}
        </n-alert>
        <n-alert v-if="actionError" type="error" :show-icon="true" class="section-alert">
          {{ actionError }}
        </n-alert>

        <template v-if="overview">
          <n-space vertical :size="14">
            <n-card size="small" title="认知三层快照" :bordered="false">
              <n-grid :cols="3" :x-gap="8" :y-gap="8">
                <n-grid-item>
                  <div class="cognition-box">
                    <h4>读者已知</h4>
                    <n-empty
                      v-if="!overview.cognition_layers?.reader_known?.length"
                      description="暂无"
                      size="small"
                    />
                    <ul v-else class="cognition-list">
                      <li v-for="line in overview.cognition_layers.reader_known.slice(0, 6)" :key="`r-${line}`">
                        {{ line }}
                      </li>
                    </ul>
                  </div>
                </n-grid-item>
                <n-grid-item>
                  <div class="cognition-box">
                    <h4>角色已知</h4>
                    <n-empty
                      v-if="!overview.cognition_layers?.character_known?.length"
                      description="暂无"
                      size="small"
                    />
                    <ul v-else class="cognition-list">
                      <li v-for="line in overview.cognition_layers.character_known.slice(0, 6)" :key="`c-${line}`">
                        {{ line }}
                      </li>
                    </ul>
                  </div>
                </n-grid-item>
                <n-grid-item>
                  <div class="cognition-box cognition-box--author">
                    <h4>作者真相（禁直出）</h4>
                    <n-empty
                      v-if="!overview.cognition_layers?.author_truth?.length"
                      description="暂无"
                      size="small"
                    />
                    <ul v-else class="cognition-list">
                      <li v-for="line in overview.cognition_layers.author_truth.slice(0, 6)" :key="`a-${line}`">
                        {{ line }}
                      </li>
                    </ul>
                  </div>
                </n-grid-item>
              </n-grid>
            </n-card>

            <n-card size="small" title="新增 / 更新线索" :bordered="false">
              <n-space vertical :size="12">
                <n-grid :cols="2" :x-gap="8" :y-gap="8">
                  <n-grid-item>
                    <n-input v-model:value="itemForm.clue_key" placeholder="线索键，如 clue-ch04-keycard" />
                  </n-grid-item>
                  <n-grid-item>
                    <n-select v-model:value="itemForm.visibility" :options="visibilityOptions" />
                  </n-grid-item>
                  <n-grid-item :span="2">
                    <n-input v-model:value="itemForm.clue_text" placeholder="线索内容：读者当前可获知的信息" />
                  </n-grid-item>
                  <n-grid-item>
                    <n-input-number
                      v-model:value="itemForm.reveal_chapter"
                      :min="1"
                      style="width: 100%"
                      placeholder="揭示章节（可选）"
                    />
                  </n-grid-item>
                  <n-grid-item>
                    <n-input-number
                      v-model:value="itemForm.confidence"
                      :min="0"
                      :max="1"
                      :step="0.05"
                      style="width: 100%"
                      placeholder="可信度 0-1"
                    />
                  </n-grid-item>
                  <n-grid-item>
                    <n-select v-model:value="itemForm.lock_level" :options="lockLevelOptions" />
                  </n-grid-item>
                  <n-grid-item>
                    <n-select v-model:value="itemForm.status" :options="statusOptions" />
                  </n-grid-item>
                </n-grid>
                <n-input
                  v-model:value="knownByInput"
                  placeholder="已知角色（逗号分隔），如：林岚, 顾川"
                />
                <n-input
                  v-model:value="itemForm.notes"
                  type="textarea"
                  placeholder="备注：线索来源、误导设计、后续兑现计划"
                  :autosize="{ minRows: 2, maxRows: 5 }"
                />
                <n-space justify="end">
                  <n-button
                    type="primary"
                    secondary
                    :loading="savingItem"
                    :disabled="!itemForm.clue_key.trim() || !itemForm.clue_text.trim()"
                    @click="saveItem"
                  >
                    保存线索
                  </n-button>
                </n-space>
              </n-space>
            </n-card>

            <n-card size="small" title="线索列表" :bordered="false">
              <n-empty v-if="!overview.items.length" description="暂无线索" size="small" />
              <n-space v-else vertical :size="8">
                <button
                  v-for="item in overview.items"
                  :key="item.id"
                  class="item-row"
                  type="button"
                  @click="fillItemForm(item)"
                >
                  <n-space justify="space-between" align="center">
                    <span class="item-title">
                      <strong>{{ item.clue_key }}</strong>
                      <small>{{ visibilityLabel(item.visibility) }} · {{ statusLabel(item.status) }}</small>
                    </span>
                    <n-tag size="small" round :type="lockTagType(item.lock_level)">
                      {{ lockLevelLabel(item.lock_level) }}
                    </n-tag>
                  </n-space>
                  <n-text depth="3" style="font-size:12px">
                    {{ item.clue_text || '未记录线索内容' }}
                  </n-text>
                  <n-text depth="3" style="font-size:12px">
                    已知角色：{{ renderKnownBy(item.known_by) || '未记录' }} ｜ 可信度：{{ confidenceLabel(item.confidence) }}
                  </n-text>
                </button>
              </n-space>
            </n-card>

            <n-card size="small" title="记录线索事件" :bordered="false">
              <n-space vertical :size="12">
                <n-grid :cols="2" :x-gap="8" :y-gap="8">
                  <n-grid-item>
                    <n-select
                      v-model:value="eventForm.clue_id"
                      :options="itemOptions"
                      clearable
                      placeholder="关联线索（clue_id，可选）"
                    />
                  </n-grid-item>
                  <n-grid-item>
                    <n-input v-model:value="eventForm.clue_key" placeholder="线索键（clue_key，可选）" />
                  </n-grid-item>
                  <n-grid-item>
                    <n-input-number
                      v-model:value="eventForm.chapter_number"
                      :min="1"
                      style="width: 100%"
                      placeholder="章节号"
                    />
                  </n-grid-item>
                  <n-grid-item>
                    <n-select v-model:value="eventForm.event_type" :options="eventTypeOptions" />
                  </n-grid-item>
                </n-grid>
                <n-input
                  v-model:value="eventForm.evidence"
                  type="textarea"
                  placeholder="正文证据：动作、对话、细节线索"
                  :autosize="{ minRows: 2, maxRows: 5 }"
                />
                <n-input
                  v-model:value="eventForm.notes"
                  type="textarea"
                  placeholder="备注：冲突处理、线索偏差、后续动作"
                  :autosize="{ minRows: 2, maxRows: 5 }"
                />
                <n-space justify="end">
                  <n-button type="primary" secondary :loading="savingEvent" @click="saveEvent">
                    记录线索事件
                  </n-button>
                </n-space>

                <n-empty v-if="!overview.recent_events.length" description="暂无线索事件" size="small" />
                <n-timeline v-else size="small">
                  <n-timeline-item
                    v-for="event in overview.recent_events"
                    :key="event.id"
                    type="info"
                    :title="event.clue_key || eventClueKey(event.clue_id)"
                    :time="`第${event.chapter_number}章 · ${eventTypeLabel(event.event_type)}`"
                  >
                    <n-text depth="3" style="font-size:12px">
                      {{ event.evidence || '未记录正文证据' }}
                    </n-text>
                  </n-timeline-item>
                </n-timeline>
              </n-space>
            </n-card>
          </n-space>
        </template>

        <n-empty v-else-if="!loadError" description="暂无 CoC 线索数据" size="small" />
      </n-spin>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useMessage } from 'naive-ui'
import { cocClueApi, type CocClueItem, type CocClueOverview } from '@/api/cocClue'

const props = defineProps<{
  slug: string
  currentChapter?: number | null
}>()

const message = useMessage()
const loading = ref(false)
const savingItem = ref(false)
const savingEvent = ref(false)
const loadError = ref('')
const actionError = ref('')
const overview = ref<CocClueOverview | null>(null)
const knownByInput = ref('')

const visibilityOptions = [
  { label: '读者可见', value: 'reader_known' },
  { label: '主角已知', value: 'protagonist_known' },
  { label: '仅作者可见', value: 'author_only' },
]

const lockLevelOptions = [
  { label: '柔性锁（soft）', value: 'soft' },
  { label: '严格锁（strict）', value: 'strict' },
  { label: '绝对锁（absolute）', value: 'absolute' },
]

const statusOptions = [
  { label: '进行中', value: 'active' },
  { label: '已回收', value: 'resolved' },
  { label: '已证伪', value: 'refuted' },
]

const eventTypeOptions = [
  { label: '提及', value: 'mention' },
  { label: '误导', value: 'mislead' },
  { label: '校正', value: 'correct' },
  { label: '揭示', value: 'reveal' },
  { label: '回收', value: 'resolve' },
]

const itemForm = reactive({
  clue_key: '',
  clue_text: '',
  visibility: 'reader_known',
  reveal_chapter: null as number | null,
  confidence: 0.6 as number | null,
  lock_level: 'soft',
  status: 'active',
  notes: '',
})

const eventForm = reactive({
  clue_id: null as string | null,
  clue_key: '',
  chapter_number: props.currentChapter || 1,
  event_type: 'mention',
  evidence: '',
  notes: '',
})

const itemOptions = computed(() =>
  (overview.value?.items || []).map(item => ({
    label: `${item.clue_key} · ${item.clue_text || '未记录内容'}`,
    value: item.id,
  })),
)

function visibilityLabel(value: string) {
  return visibilityOptions.find(item => item.value === value)?.label || value
}

function lockLevelLabel(value: string) {
  return lockLevelOptions.find(item => item.value === value)?.label || value
}

function statusLabel(value: string) {
  return statusOptions.find(item => item.value === value)?.label || value
}

function eventTypeLabel(value: string) {
  return eventTypeOptions.find(item => item.value === value)?.label || value
}

function lockTagType(value: string) {
  if (value === 'absolute') return 'error'
  if (value === 'strict') return 'warning'
  return 'info'
}

function parseKnownBy(value: string) {
  return value
    .split(',')
    .map(name => name.trim())
    .filter(Boolean)
    .join(', ')
}

function renderKnownBy(value: string[] | string | null | undefined) {
  if (!value) return ''
  if (Array.isArray(value)) return value.filter(Boolean).join(', ')
  if (typeof value === 'string') return value
  return ''
}

function confidenceLabel(value: number | null) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '未记录'
  return `${Math.round(Math.max(0, Math.min(1, Number(value))) * 100)}%`
}

function eventClueKey(clueId: string | null) {
  if (!clueId) return '未命名线索事件'
  const matched = overview.value?.items.find(item => item.id === clueId)
  return matched?.clue_key || '未命名线索事件'
}

function getErrorMessage(error: unknown, fallback: string) {
  const response = (error as {
    response?: { data?: { detail?: unknown; message?: unknown; error?: unknown } | string }
  }).response
  const payload = response?.data
  if (typeof payload === 'string' && payload.trim()) return payload
  if (!payload || typeof payload !== 'object') return fallback

  const detail = payload.detail
  if (typeof detail === 'string' && detail.trim()) return detail
  if (Array.isArray(detail)) {
    const first = detail[0]
    if (typeof first === 'string' && first.trim()) return first
    if (first && typeof first === 'object') {
      const msg = (first as { msg?: unknown }).msg
      if (typeof msg === 'string' && msg.trim()) return msg
    }
  }

  const messageText = payload.message
  if (typeof messageText === 'string' && messageText.trim()) return messageText
  const errorText = payload.error
  if (typeof errorText === 'string' && errorText.trim()) return errorText
  return fallback
}

async function loadOverview() {
  if (!props.slug) return
  loading.value = true
  loadError.value = ''
  actionError.value = ''
  try {
    overview.value = await cocClueApi.getOverview(props.slug)
  } catch (error) {
    overview.value = null
    loadError.value = getErrorMessage(error, '加载 CoC 线索失败，请稍后重试')
  } finally {
    loading.value = false
  }
}

function fillItemForm(item: CocClueItem) {
  itemForm.clue_key = item.clue_key || ''
  itemForm.clue_text = item.clue_text || ''
  itemForm.visibility = item.visibility || 'reader_known'
  itemForm.reveal_chapter = item.reveal_chapter
  itemForm.confidence = item.confidence
  itemForm.lock_level = item.lock_level || 'soft'
  itemForm.status = item.status || 'active'
  itemForm.notes = item.notes || ''
  knownByInput.value = renderKnownBy(item.known_by)
  eventForm.clue_id = item.id
  if (!eventForm.clue_key.trim()) {
    eventForm.clue_key = item.clue_key || ''
  }
}

function resetItemForm() {
  itemForm.clue_key = ''
  itemForm.clue_text = ''
  itemForm.visibility = 'reader_known'
  itemForm.reveal_chapter = null
  itemForm.confidence = 0.6
  itemForm.lock_level = 'soft'
  itemForm.status = 'active'
  itemForm.notes = ''
  knownByInput.value = ''
}

async function saveItem() {
  if (!itemForm.clue_key.trim() || !itemForm.clue_text.trim()) {
    message.warning('请先填写线索键和线索内容')
    return
  }
  savingItem.value = true
  actionError.value = ''
  try {
    await cocClueApi.upsertItem(props.slug, {
      clue_key: itemForm.clue_key.trim(),
      clue_text: itemForm.clue_text.trim(),
      visibility: itemForm.visibility,
      reveal_chapter: itemForm.reveal_chapter,
      known_by: parseKnownBy(knownByInput.value),
      confidence: itemForm.confidence,
      lock_level: itemForm.lock_level,
      status: itemForm.status,
      notes: itemForm.notes,
    })
    message.success('线索已保存')
    resetItemForm()
    await loadOverview()
  } catch (error) {
    const detail = getErrorMessage(error, '保存线索失败')
    actionError.value = detail
    if (detail.toLowerCase().includes('lock') || detail.toLowerCase().includes('locked')) {
      message.error(`锁定线索不允许改写核心字段：${detail}`)
    } else {
      message.error(detail)
    }
  } finally {
    savingItem.value = false
  }
}

async function saveEvent() {
  if (!eventForm.clue_id && !eventForm.clue_key.trim()) {
    message.warning('请至少填写 clue_id 或 clue_key')
    return
  }
  savingEvent.value = true
  actionError.value = ''
  try {
    const useClueId = !!eventForm.clue_id
    await cocClueApi.createEvent(props.slug, {
      clue_id: useClueId ? eventForm.clue_id || undefined : undefined,
      clue_key: useClueId ? undefined : eventForm.clue_key.trim() || undefined,
      chapter_number: eventForm.chapter_number || 1,
      event_type: eventForm.event_type,
      evidence: eventForm.evidence,
      notes: eventForm.notes,
    })
    message.success('线索事件已记录')
    eventForm.evidence = ''
    eventForm.notes = ''
    await loadOverview()
  } catch (error) {
    const detail = getErrorMessage(error, '记录线索事件失败')
    actionError.value = detail
    message.error(detail)
  } finally {
    savingEvent.value = false
  }
}

watch(() => props.slug, () => {
  void loadOverview()
})

watch(() => props.currentChapter, value => {
  if (value) {
    eventForm.chapter_number = value
  }
})

onMounted(() => {
  void loadOverview()
})
</script>

<style scoped>
.coc-clue-panel {
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: var(--aitext-panel-muted);
}

.panel-header {
  padding: 16px;
  border-bottom: 1px solid var(--aitext-split-border);
  background: var(--app-surface);
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
}

.header-main {
  flex: 1;
  min-width: 0;
}

.title-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.panel-title {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: var(--text-color-1);
}

.panel-lead {
  margin: 0;
  font-size: 13px;
  line-height: 1.5;
  color: var(--text-color-3);
}

.panel-content {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
}

.section-alert {
  margin-bottom: 12px;
}

.item-row {
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 10px;
  border: 1px solid var(--aitext-split-border);
  border-radius: 8px;
  background: var(--app-surface);
  text-align: left;
  cursor: pointer;
}

.item-row:hover {
  border-color: var(--primary-color);
}

.item-title strong,
.item-title small {
  display: block;
}

.item-title small {
  margin-top: 3px;
  color: var(--text-color-3);
  font-size: 11px;
}

.cognition-box {
  min-height: 124px;
  padding: 8px;
  border: 1px solid var(--aitext-split-border);
  border-radius: 8px;
  background: var(--aitext-panel-muted);
}

.cognition-box h4 {
  margin: 0 0 6px;
  font-size: 12px;
  color: var(--text-color-2);
}

.cognition-box--author h4 {
  color: #b45309;
}

.cognition-list {
  margin: 0;
  padding-left: 16px;
  font-size: 12px;
  line-height: 1.45;
  color: var(--text-color-3);
}
</style>
