<template>
  <n-drawer :show="true" :width="340" placement="right" @update:show="$emit('close')">
    <n-drawer-content :title="prop.name" closable>
      <n-space vertical :size="12">
        <n-space align="center">
          <n-tag :type="LIFECYCLE_TAG_TYPES[prop.lifecycle_state]" size="small">
            {{ LIFECYCLE_LABELS[prop.lifecycle_state] }}
          </n-tag>
          <n-tag size="small" type="default">{{ CATEGORY_ICONS[prop.prop_category] }} {{ CATEGORY_LABELS[prop.prop_category] }}</n-tag>
        </n-space>
        <n-text depth="3" style="font-size:12px">{{ prop.description || '暂无描述' }}</n-text>
        <div v-if="prop.holder_character_id">
          <n-text>持有者: </n-text>
          <n-text strong>{{ holderName }}</n-text>
        </div>

        <n-space v-if="prop.lifecycle_state === 'DAMAGED'" :size="8">
          <n-button size="small" type="primary" ghost :loading="acting" @click="quickEvent('REPAIRED')">
            🔧 修复
          </n-button>
        </n-space>

        <n-divider style="margin:4px 0">事件时间线</n-divider>
        <n-spin :show="eventsLoading">
          <n-empty v-if="!eventsLoading && events.length === 0" description="暂无事件记录" size="small" />
          <n-timeline v-else>
            <n-timeline-item
              v-for="ev in events"
              :key="ev.id"
              :type="eventTagType(ev.event_type)"
              :title="`第${ev.chapter_number}章 · ${EVENT_LABELS[ev.event_type] ?? ev.event_type}`"
            >
              <n-text depth="3" style="font-size:11px">
                {{ ev.description }}
                <n-tag size="tiny" :type="ev.source === 'MANUAL' ? 'warning' : 'default'" style="margin-left:4px">
                  {{ ev.source === 'MANUAL' ? '手动' : ev.source === 'AUTO_LLM' ? 'AI' : '标记' }}
                </n-tag>
              </n-text>
            </n-timeline-item>
          </n-timeline>
        </n-spin>

        <n-button size="small" ghost block @click="showAddEvent = true">＋ 手动记录事件</n-button>
      </n-space>

      <n-modal v-model:show="showAddEvent" preset="dialog" title="记录事件" positive-text="保存" @positive-click="submitEvent">
        <n-form size="small" label-placement="top">
          <n-form-item label="章节">
            <n-input-number v-model:value="eventForm.chapter_number" :min="1" style="width:100%" />
          </n-form-item>
          <n-form-item label="事件类型">
            <n-select v-model:value="eventForm.event_type" :options="eventTypeOptions" />
          </n-form-item>
          <n-form-item label="描述">
            <n-input v-model:value="eventForm.description" placeholder="一句话描述" />
          </n-form-item>
        </n-form>
      </n-modal>
    </n-drawer-content>
  </n-drawer>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useMessage } from 'naive-ui'
import {
  propApi, type PropDTO, type PropEventDTO,
  LIFECYCLE_LABELS, LIFECYCLE_TAG_TYPES, CATEGORY_LABELS, CATEGORY_ICONS,
} from '@/api/propApi'

const props = defineProps<{
  prop: PropDTO
  slug: string
  charOptions: { label: string; value: string }[]
}>()
const emit = defineEmits<{ close: []; updated: [] }>()
const message = useMessage()

const events = ref<PropEventDTO[]>([])
const eventsLoading = ref(false)
const showAddEvent = ref(false)
const acting = ref(false)
const eventForm = ref({ chapter_number: 1, event_type: 'USED', description: '' })

const EVENT_LABELS: Record<string, string> = {
  INTRODUCED: '登场', USED: '使用', TRANSFERRED: '转移',
  DAMAGED: '损毁', REPAIRED: '修复', UPGRADED: '强化', RESOLVED: '结局',
}

const eventTypeOptions = Object.entries(EVENT_LABELS).map(([v, l]) => ({ label: l, value: v }))

const holderName = computed(() => {
  if (!props.prop.holder_character_id) return ''
  return props.charOptions.find(c => c.value === props.prop.holder_character_id)?.label ?? props.prop.holder_character_id.slice(0, 8)
})

function eventTagType(t: string): 'default' | 'info' | 'success' | 'warning' | 'error' {
  if (t === 'DAMAGED') return 'error'
  if (t === 'REPAIRED' || t === 'INTRODUCED') return 'success'
  if (t === 'TRANSFERRED') return 'warning'
  return 'info'
}

async function loadEvents() {
  eventsLoading.value = true
  try {
    events.value = await propApi.listEvents(props.slug, props.prop.id)
  } finally {
    eventsLoading.value = false
  }
}

async function quickEvent(type: string) {
  acting.value = true
  try {
    await propApi.createEvent(props.slug, props.prop.id, {
      chapter_number: 1,
      event_type: type,
      description: `手动标记: ${EVENT_LABELS[type] ?? type}`,
    })
    message.success('已记录')
    emit('updated')
    await loadEvents()
  } catch {
    message.error('操作失败')
  } finally {
    acting.value = false
  }
}

async function submitEvent() {
  try {
    await propApi.createEvent(props.slug, props.prop.id, eventForm.value)
    message.success('已记录')
    showAddEvent.value = false
    emit('updated')
    await loadEvents()
  } catch {
    message.error('保存失败')
    return false
  }
}

onMounted(() => void loadEvents())
</script>
