<template>
  <div class="prop-ledger-panel">
    <header class="panel-header">
      <div class="header-main">
        <div class="title-row">
          <h3 class="panel-title">道具账本</h3>
          <n-tag size="small" round :bordered="false">防写丢</n-tag>
        </div>
        <p class="panel-lead">
          手动记录关键道具当前持有人、位置、状态与最近章节；章节生成会读取这里的当前状态。
        </p>
      </div>
      <n-button size="small" type="primary" secondary :loading="loading" @click="loadOverview">
        刷新
      </n-button>
      <n-button size="small" secondary :disabled="!overview?.items.length" @click="copyPropPrompt">
        复制道具约束
      </n-button>
    </header>

    <div class="panel-content">
      <n-spin :show="loading">
        <n-alert v-if="loadError" type="error" :show-icon="true" class="section-alert">
          {{ loadError }}
        </n-alert>

        <template v-else>
          <n-space vertical :size="14">
            <n-alert
              v-for="warning in overview?.warnings || []"
              :key="`${warning.title}-${warning.message}`"
              :type="warningType(warning.severity)"
              :title="warning.title"
              class="section-alert"
            >
              {{ warning.message }}
            </n-alert>

            <n-card size="small" title="登记 / 更新道具" :bordered="false">
              <n-space vertical :size="12">
                <n-grid :cols="2" :x-gap="8" :y-gap="8">
                  <n-grid-item>
                    <n-input v-model:value="itemForm.name" placeholder="道具名，如青铜钥匙" />
                  </n-grid-item>
                  <n-grid-item>
                    <n-select v-model:value="itemForm.importance" :options="importanceOptions" />
                  </n-grid-item>
                  <n-grid-item>
                    <n-input v-model:value="itemForm.category" placeholder="类型：钥匙/信物/武器/证物" />
                  </n-grid-item>
                  <n-grid-item>
                    <n-input v-model:value="itemForm.status" placeholder="当前状态：未使用/损坏/封存" />
                  </n-grid-item>
                  <n-grid-item>
                    <n-input v-model:value="itemForm.current_holder" placeholder="当前持有人" />
                  </n-grid-item>
                  <n-grid-item>
                    <n-input v-model:value="itemForm.current_location" placeholder="当前位置" />
                  </n-grid-item>
                  <n-grid-item>
                    <n-input-number v-model:value="itemForm.first_seen_chapter" :min="1" style="width: 100%" placeholder="首次出现章节" />
                  </n-grid-item>
                  <n-grid-item>
                    <n-input-number v-model:value="itemForm.last_seen_chapter" :min="1" style="width: 100%" placeholder="最近出现章节" />
                  </n-grid-item>
                </n-grid>
                <n-input v-model:value="itemForm.description" type="textarea" placeholder="道具作用/来历/限制" :autosize="{ minRows: 2, maxRows: 5 }" />
                <n-input v-model:value="itemForm.notes" type="textarea" placeholder="写作提醒：下次使用前要交代什么" :autosize="{ minRows: 2, maxRows: 5 }" />
                <n-space justify="end">
                  <n-button type="primary" secondary :loading="savingItem" :disabled="!itemForm.name.trim()" @click="saveItem">
                    保存道具状态
                  </n-button>
                </n-space>
              </n-space>
            </n-card>

            <n-card size="small" title="当前道具状态" :bordered="false">
              <n-empty v-if="!overview?.items.length" description="暂无道具" size="small" />
              <n-space v-else vertical :size="8">
                <button
                  v-for="item in overview.items"
                  :key="item.id"
                  class="prop-row"
                  type="button"
                  @click="fillItemForm(item)"
                >
                  <n-space justify="space-between" align="center">
                    <span class="prop-title">
                      <strong>{{ item.name }}</strong>
                      <small>{{ item.category || '未分类' }} · 最近{{ chapterLabel(item.last_seen_chapter) }}</small>
                    </span>
                    <n-tag size="small" round :type="item.importance === 'major' ? 'warning' : 'info'">
                      {{ importanceLabel(item.importance) }}
                    </n-tag>
                  </n-space>
                  <n-text depth="3" style="font-size:12px">
                    状态：{{ item.status || '未记录' }} ｜ 持有人：{{ item.current_holder || '未记录' }} ｜ 位置：{{ item.current_location || '未记录' }}
                  </n-text>
                  <n-text v-if="item.notes" depth="3" style="font-size:12px">
                    提醒：{{ item.notes }}
                  </n-text>
                </button>
              </n-space>
            </n-card>

            <n-card size="small" title="记录道具事件" :bordered="false">
              <n-space vertical :size="12">
                <n-grid :cols="2" :x-gap="8" :y-gap="8">
                  <n-grid-item>
                    <n-input v-model:value="eventForm.prop_name" placeholder="道具名" />
                  </n-grid-item>
                  <n-grid-item>
                    <n-input-number v-model:value="eventForm.chapter_number" :min="1" style="width: 100%" placeholder="章节号" />
                  </n-grid-item>
                  <n-grid-item>
                    <n-select v-model:value="eventForm.event_type" :options="eventTypeOptions" />
                  </n-grid-item>
                  <n-grid-item>
                    <n-input v-model:value="eventForm.status" placeholder="事件后状态" />
                  </n-grid-item>
                  <n-grid-item>
                    <n-input v-model:value="eventForm.holder" placeholder="事件后持有人" />
                  </n-grid-item>
                  <n-grid-item>
                    <n-input v-model:value="eventForm.location" placeholder="事件后位置" />
                  </n-grid-item>
                </n-grid>
                <n-input v-model:value="eventForm.evidence" type="textarea" placeholder="正文证据：哪一章如何出现/转移/使用" :autosize="{ minRows: 2, maxRows: 5 }" />
                <n-input v-model:value="eventForm.notes" type="textarea" placeholder="后续提醒" :autosize="{ minRows: 2, maxRows: 5 }" />
                <n-space justify="end">
                  <n-button type="primary" secondary :loading="savingEvent" :disabled="!eventForm.prop_name.trim()" @click="saveEvent">
                    记录道具事件
                  </n-button>
                </n-space>

                <n-empty v-if="!overview?.recent_events.length" description="暂无道具事件" size="small" />
                <n-timeline v-else size="small">
                  <n-timeline-item
                    v-for="event in overview.recent_events"
                    :key="event.id"
                    type="info"
                    :title="`${event.prop_name} · ${event.status || event.event_type}`"
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
      </n-spin>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref, watch } from 'vue'
import { useMessage } from 'naive-ui'
import { propLedgerApi, type PropLedgerItem, type PropLedgerOverview } from '@/api/propLedger'

const props = defineProps<{
  slug: string
  currentChapter?: number | null
}>()

const message = useMessage()
const loading = ref(false)
const savingItem = ref(false)
const savingEvent = ref(false)
const loadError = ref('')
const overview = ref<PropLedgerOverview | null>(null)

const importanceOptions = [
  { label: '关键道具', value: 'major' },
  { label: '普通道具', value: 'normal' },
  { label: '次要道具', value: 'minor' },
]

const eventTypeOptions = [
  { label: '提及', value: 'mention' },
  { label: '获得', value: 'acquire' },
  { label: '转交', value: 'transfer' },
  { label: '使用', value: 'use' },
  { label: '损坏/丢失', value: 'lost_or_broken' },
  { label: '封存', value: 'sealed' },
]

const itemForm = reactive({
  name: '',
  category: '',
  status: '',
  current_holder: '',
  current_location: '',
  first_seen_chapter: null as number | null,
  last_seen_chapter: null as number | null,
  importance: 'normal',
  description: '',
  notes: '',
})

const eventForm = reactive({
  prop_name: '',
  chapter_number: props.currentChapter || 1,
  event_type: 'mention',
  holder: '',
  location: '',
  status: '',
  evidence: '',
  notes: '',
})

function warningType(value: string) {
  if (value === 'error') return 'error'
  if (value === 'warning') return 'warning'
  return 'info'
}

function importanceLabel(value: string) {
  if (value === 'major') return '关键'
  if (value === 'minor') return '次要'
  return '普通'
}

function eventTypeLabel(value: string) {
  return eventTypeOptions.find(item => item.value === value)?.label || value
}

function chapterLabel(value: number | null) {
  return value ? `第${value}章` : '未登记'
}

async function loadOverview() {
  if (!props.slug) return
  loading.value = true
  loadError.value = ''
  try {
    overview.value = await propLedgerApi.getOverview(props.slug)
  } catch {
    overview.value = null
    loadError.value = '加载道具账本失败，请稍后重试'
  } finally {
    loading.value = false
  }
}

function fillItemForm(item: PropLedgerItem) {
  itemForm.name = item.name
  itemForm.category = item.category
  itemForm.status = item.status
  itemForm.current_holder = item.current_holder
  itemForm.current_location = item.current_location
  itemForm.first_seen_chapter = item.first_seen_chapter
  itemForm.last_seen_chapter = item.last_seen_chapter
  itemForm.importance = item.importance || 'normal'
  itemForm.description = item.description
  itemForm.notes = item.notes
  eventForm.prop_name = item.name
  eventForm.holder = item.current_holder
  eventForm.location = item.current_location
  eventForm.status = item.status
}

function resetItemForm() {
  itemForm.name = ''
  itemForm.category = ''
  itemForm.status = ''
  itemForm.current_holder = ''
  itemForm.current_location = ''
  itemForm.first_seen_chapter = null
  itemForm.last_seen_chapter = null
  itemForm.importance = 'normal'
  itemForm.description = ''
  itemForm.notes = ''
}

async function saveItem() {
  savingItem.value = true
  try {
    await propLedgerApi.saveItem(props.slug, { ...itemForm })
    message.success('道具状态已保存')
    resetItemForm()
    await loadOverview()
  } catch {
    message.error('保存道具状态失败')
  } finally {
    savingItem.value = false
  }
}

async function saveEvent() {
  savingEvent.value = true
  try {
    await propLedgerApi.createEvent(props.slug, { ...eventForm })
    message.success('道具事件已记录')
    eventForm.evidence = ''
    eventForm.notes = ''
    await loadOverview()
  } catch {
    message.error('记录道具事件失败')
  } finally {
    savingEvent.value = false
  }
}

async function copyPropPrompt() {
  const items = overview.value?.items || []
  const text = [
    '【道具账本】',
    '写到以下道具时必须保持当前状态、持有人和位置一致；除非正文明确交代，不得凭空改变。',
    ...items.map(item =>
      `- ${item.name}｜状态：${item.status || '未记录'}｜持有人：${item.current_holder || '未记录'}｜位置：${item.current_location || '未记录'}｜最近：${chapterLabel(item.last_seen_chapter)}`
    ),
  ].join('\n')
  await navigator.clipboard.writeText(text)
  message.success('已复制道具约束')
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
.prop-ledger-panel {
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
  margin: 0;
}

.prop-row {
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

.prop-row:hover {
  border-color: var(--primary-color);
}

.prop-title strong,
.prop-title small {
  display: block;
}

.prop-title small {
  margin-top: 3px;
  color: var(--text-color-3);
  font-size: 11px;
}
</style>
