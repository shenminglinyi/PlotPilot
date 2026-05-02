<template>
  <div class="coc-canon-panel">
    <header class="panel-header">
      <div class="header-main">
        <div class="title-row">
          <h3 class="panel-title">CoC正典</h3>
          <n-tag size="small" round :bordered="false">防设定漂移</n-tag>
        </div>
        <p class="panel-lead">
          记录可公开事实与隐藏真相，按锁级别控制可变范围；用事件追踪章节内的兑现、修正与冲突处理。
        </p>
      </div>
      <n-space :size="8">
        <n-select
          v-model:value="selectedPresetKey"
          size="small"
          class="preset-select"
          :options="presetOptions"
          :disabled="presetLoading || loading"
          placeholder="选择模板"
        />
        <n-button size="small" type="primary" secondary :loading="loading" @click="loadOverview">
          刷新
        </n-button>
        <n-button size="small" type="info" secondary :loading="presetLoading" @click="applyInitialPreset">
          导入模板
        </n-button>
      </n-space>
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
            <n-card size="small" title="新增 / 更新正典条目" :bordered="false">
              <n-space vertical :size="12">
                <n-grid :cols="2" :x-gap="8" :y-gap="8">
                  <n-grid-item>
                    <n-select v-model:value="entryForm.canon_type" :options="canonTypeOptions" />
                  </n-grid-item>
                  <n-grid-item>
                    <n-select v-model:value="entryForm.lock_level" :options="lockLevelOptions" />
                  </n-grid-item>
                  <n-grid-item :span="2">
                    <n-input v-model:value="entryForm.title" placeholder="条目标题，如：第17分钟失忆机制" />
                  </n-grid-item>
                  <n-grid-item :span="2">
                    <n-select v-model:value="entryForm.status" :options="statusOptions" />
                  </n-grid-item>
                </n-grid>
                <n-input
                  v-model:value="entryForm.public_facts"
                  type="textarea"
                  placeholder="可公开事实（角色/读者可直接得知）"
                  :autosize="{ minRows: 2, maxRows: 5 }"
                />
                <n-input
                  v-model:value="entryForm.hidden_truth"
                  type="textarea"
                  placeholder="隐藏真相（暂不公开的底层真相）"
                  :autosize="{ minRows: 2, maxRows: 5 }"
                />
                <n-input
                  v-model:value="entryForm.mutable_notes"
                  type="textarea"
                  placeholder="可变注记（允许后续微调的边界）"
                  :autosize="{ minRows: 2, maxRows: 5 }"
                />
                <n-space justify="end">
                  <n-button
                    type="primary"
                    secondary
                    :loading="savingEntry"
                    :disabled="!entryForm.title.trim()"
                    @click="saveEntry"
                  >
                    保存正典条目
                  </n-button>
                </n-space>
              </n-space>
            </n-card>

            <n-card size="small" title="正典条目" :bordered="false">
              <n-empty v-if="!overview.entries.length" description="暂无正典条目" size="small" />
              <n-space v-else vertical :size="8">
                <button
                  v-for="entry in overview.entries"
                  :key="entry.id"
                  class="entry-row"
                  type="button"
                  @click="fillEntryForm(entry)"
                >
                  <n-space justify="space-between" align="center">
                    <span class="entry-title">
                      <strong>{{ entry.title }}</strong>
                      <small>{{ canonTypeLabel(entry.canon_type) }} · {{ statusLabel(entry.status) }}</small>
                    </span>
                    <n-tag size="small" round :type="lockTagType(entry.lock_level)">
                      {{ lockLevelLabel(entry.lock_level) }}
                    </n-tag>
                  </n-space>
                  <n-text depth="3" style="font-size:12px">
                    公开：{{ entry.public_facts || '未记录' }}
                  </n-text>
                  <n-text depth="3" style="font-size:12px">
                    隐藏：{{ entry.hidden_truth || '未记录' }}
                  </n-text>
                </button>
              </n-space>
            </n-card>

            <n-card size="small" title="记录正典事件" :bordered="false">
              <n-space vertical :size="12">
                <n-grid :cols="2" :x-gap="8" :y-gap="8">
                  <n-grid-item>
                    <n-input v-model:value="eventForm.title" placeholder="事件标题（可选）" />
                  </n-grid-item>
                  <n-grid-item>
                    <n-select
                      v-model:value="eventForm.entry_id"
                      :options="entryOptions"
                      clearable
                      placeholder="关联条目（可选）"
                    />
                  </n-grid-item>
                  <n-grid-item>
                    <n-input-number v-model:value="eventForm.chapter_number" :min="1" style="width: 100%" placeholder="章节号" />
                  </n-grid-item>
                  <n-grid-item>
                    <n-select v-model:value="eventForm.event_type" :options="eventTypeOptions" />
                  </n-grid-item>
                </n-grid>
                <n-input
                  v-model:value="eventForm.evidence"
                  type="textarea"
                  placeholder="正文证据（相关段落、动作或对白）"
                  :autosize="{ minRows: 2, maxRows: 5 }"
                />
                <n-input
                  v-model:value="eventForm.notes"
                  type="textarea"
                  placeholder="备注（例如冲突处理、补偿信息）"
                  :autosize="{ minRows: 2, maxRows: 5 }"
                />
                <n-space justify="end">
                  <n-button type="primary" secondary :loading="savingEvent" @click="saveEvent">
                    记录正典事件
                  </n-button>
                </n-space>

                <n-empty v-if="!overview.recent_events.length" description="暂无正典事件" size="small" />
                <n-timeline v-else size="small">
                  <n-timeline-item
                    v-for="event in overview.recent_events"
                    :key="event.id"
                    type="info"
                    :title="event.title || eventEntryTitle(event.entry_id)"
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

        <n-empty v-else-if="!loadError" description="暂无 CoC 正典数据" size="small" />
      </n-spin>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useMessage } from 'naive-ui'
import { cocCanonApi, type CocCanonEntry, type CocCanonOverview, type CocPresetTemplate } from '@/api/cocCanon'

const props = defineProps<{
  slug: string
  currentChapter?: number | null
}>()

const message = useMessage()
const loading = ref(false)
const presetLoading = ref(false)
const savingEntry = ref(false)
const savingEvent = ref(false)
const loadError = ref('')
const actionError = ref('')
const overview = ref<CocCanonOverview | null>(null)
const presetTemplates = ref<CocPresetTemplate[]>([])
const selectedPresetKey = ref('fog-harbor-gray-card')

const canonTypeOptions = [
  { label: '世界规则', value: 'world_rule' },
  { label: '人物设定', value: 'character_truth' },
  { label: '关键道具', value: 'artifact' },
  { label: '时间线', value: 'timeline' },
  { label: '其他', value: 'other' },
]

const lockLevelOptions = [
  { label: '柔性锁（soft）', value: 'soft' },
  { label: '严格锁（strict）', value: 'strict' },
  { label: '绝对锁（absolute）', value: 'absolute' },
]

const statusOptions = [
  { label: '生效中', value: 'active' },
  { label: '草稿', value: 'draft' },
  { label: '已归档', value: 'archived' },
]

const eventTypeOptions = [
  { label: '提及', value: 'mention' },
  { label: '揭示', value: 'reveal' },
  { label: '修正', value: 'retcon' },
  { label: '冲突', value: 'conflict' },
  { label: '回收', value: 'resolve' },
]

const entryForm = reactive({
  canon_type: 'world_rule',
  title: '',
  lock_level: 'soft',
  public_facts: '',
  hidden_truth: '',
  mutable_notes: '',
  status: 'active',
})

const eventForm = reactive({
  title: '',
  entry_id: null as string | null,
  chapter_number: props.currentChapter || 1,
  event_type: 'mention',
  evidence: '',
  notes: '',
})

const entryOptions = computed(() =>
  (overview.value?.entries || []).map(item => ({
    label: item.title,
    value: item.id,
  })),
)

const presetOptions = computed(() =>
  presetTemplates.value.map(item => ({
    label: `${item.name}（正典${item.canon_count} / 线索${item.clue_count} / 道具${item.prop_count || 0}）`,
    value: item.key,
  })),
)

function canonTypeLabel(value: string) {
  return canonTypeOptions.find(item => item.value === value)?.label || value
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

function eventEntryTitle(entryId: string | null) {
  if (!entryId) return '未命名事件'
  const matched = overview.value?.entries.find(item => item.id === entryId)
  return matched?.title || '未命名事件'
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
    overview.value = await cocCanonApi.getOverview(props.slug)
  } catch (error) {
    overview.value = null
    loadError.value = getErrorMessage(error, '加载 CoC 正典失败，请稍后重试')
  } finally {
    loading.value = false
  }
}

async function loadPresetTemplates() {
  if (!props.slug) return
  try {
    presetTemplates.value = await cocCanonApi.listPresetTemplates(props.slug)
    if (!presetTemplates.value.some(item => item.key === selectedPresetKey.value)) {
      selectedPresetKey.value = presetTemplates.value.find(item => item.key === 'fog-harbor-gray-card')?.key
        || presetTemplates.value[0]?.key
        || 'analysis-loop-721'
    }
  } catch {
    presetTemplates.value = []
  }
}

function fillEntryForm(entry: CocCanonEntry) {
  entryForm.canon_type = entry.canon_type || 'other'
  entryForm.title = entry.title || ''
  entryForm.lock_level = entry.lock_level || 'soft'
  entryForm.public_facts = entry.public_facts || ''
  entryForm.hidden_truth = entry.hidden_truth || ''
  entryForm.mutable_notes = entry.mutable_notes || ''
  entryForm.status = entry.status || 'active'
  eventForm.entry_id = entry.id
  if (!eventForm.title.trim()) {
    eventForm.title = entry.title
  }
}

function resetEntryForm() {
  entryForm.canon_type = 'world_rule'
  entryForm.title = ''
  entryForm.lock_level = 'soft'
  entryForm.public_facts = ''
  entryForm.hidden_truth = ''
  entryForm.mutable_notes = ''
  entryForm.status = 'active'
}

async function saveEntry() {
  if (!entryForm.title.trim()) {
    message.warning('请先填写条目标题')
    return
  }
  savingEntry.value = true
  actionError.value = ''
  try {
    await cocCanonApi.upsertEntry(props.slug, {
      ...entryForm,
      title: entryForm.title.trim(),
    })
    message.success('正典条目已保存')
    resetEntryForm()
    await loadOverview()
  } catch (error) {
    const detail = getErrorMessage(error, '保存正典条目失败')
    actionError.value = detail
    if (detail.toLowerCase().includes('absolute')) {
      message.error(`绝对锁条目不允许改核心字段：${detail}`)
    } else {
      message.error(detail)
    }
  } finally {
    savingEntry.value = false
  }
}

async function saveEvent() {
  if (!eventForm.entry_id && !eventForm.title.trim()) {
    message.warning('请至少填写事件标题或选择关联条目')
    return
  }
  savingEvent.value = true
  actionError.value = ''
  try {
    await cocCanonApi.createEvent(props.slug, {
      title: eventForm.title.trim() || undefined,
      entry_id: eventForm.entry_id || undefined,
      chapter_number: eventForm.chapter_number || 1,
      event_type: eventForm.event_type,
      evidence: eventForm.evidence,
      notes: eventForm.notes,
    })
    message.success('正典事件已记录')
    eventForm.title = ''
    eventForm.evidence = ''
    eventForm.notes = ''
    await loadOverview()
  } catch (error) {
    const detail = getErrorMessage(error, '记录正典事件失败')
    actionError.value = detail
    message.error(detail)
  } finally {
    savingEvent.value = false
  }
}

async function applyInitialPreset() {
  if (!props.slug) return
  presetLoading.value = true
  actionError.value = ''
  try {
    if (!presetTemplates.value.length) {
      await loadPresetTemplates()
    }
    const presetKey = selectedPresetKey.value || presetTemplates.value[0]?.key || 'analysis-loop-721'
    const result = await cocCanonApi.applyPreset(props.slug, {
      preset_key: presetKey,
      overwrite_existing: false,
    })
    message.success(`模板导入完成：正典 +${result.created_canon}，线索 +${result.created_clues}，道具 +${result.created_props || 0}，跳过 ${result.skipped}`)
    await loadOverview()
  } catch (error) {
    const detail = getErrorMessage(error, '导入初始模板失败')
    actionError.value = detail
    message.error(detail)
  } finally {
    presetLoading.value = false
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
  void loadPresetTemplates()
  void loadOverview()
})
</script>

<style scoped>
.coc-canon-panel {
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

.preset-select {
  width: 260px;
}

.panel-content {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
}

.section-alert {
  margin-bottom: 12px;
}

.entry-row {
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

.entry-row:hover {
  border-color: var(--primary-color);
}

.entry-title strong,
.entry-title small {
  display: block;
}

.entry-title small {
  margin-top: 3px;
  color: var(--text-color-3);
  font-size: 11px;
}
</style>
