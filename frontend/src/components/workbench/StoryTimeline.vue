<template>
  <div class="story-timeline">
    <div class="timeline-header">
      <n-text strong style="font-size: 14px">时间轴</n-text>
      <n-space :size="8">
        <n-button size="small" :loading="creating" @click="handleCreateSnapshot">
          ＋ 创建快照
        </n-button>
        <n-button size="small" :loading="loading" @click="onHeaderRefresh">刷新</n-button>
      </n-space>
    </div>

    <n-alert v-if="loadError" type="error" :title="loadError" closable @close="loadError = ''" class="timeline-alert" />

    <n-spin :show="loading">
      <div v-if="rows.length > 0" class="timeline-list">
        <div
          v-for="row in rows"
          :key="row.chapter_index"
          class="timeline-chapter"
          :class="{
            'timeline-chapter--highlight': isHighlighted(row.chapter_index)
          }"
        >
          <div class="chapter-header">
            <div class="chapter-dot" />
            <n-text strong>第 {{ row.chapter_index }} 章</n-text>
          </div>

          <div class="chapter-content">
            <!-- 剧情事件 -->
            <div
              v-for="event in row.story_events"
              :key="event.note_id"
              class="timeline-event"
              @click="emit('select-event', event)"
            >
              <n-tag type="success" size="tiny" round>{{ event.time }}</n-tag>
              <div class="event-title">{{ event.title }}</div>
              <div v-if="event.description" class="event-desc">{{ event.description }}</div>
            </div>

            <!-- 版本快照 -->
            <div
              v-for="snapshot in row.snapshots"
              :key="snapshot.id"
              class="timeline-snapshot"
              @click="emit('select-snapshot', snapshot)"
            >
              <n-tag
                :type="snapshot.kind === 'MANUAL' ? 'warning' : 'info'"
                size="tiny"
                round
              >
                {{ snapshot.kind === 'MANUAL' ? '🟣 手动快照' : '🔵 自动快照' }}
              </n-tag>
              <div class="snapshot-name">{{ snapshot.name }}</div>
              <n-text depth="3" style="font-size: 10px">{{ formatTime(snapshot.created_at) }}</n-text>
            </div>

            <n-text v-if="row.story_events.length === 0 && row.snapshots.length === 0" depth="3" style="font-size: 11px">
              —
            </n-text>
          </div>
        </div>
      </div>

      <n-empty
        v-else-if="!loading"
        description="暂无时间轴数据，章节完成后将自动创建快照"
        size="small"
        style="margin-top: 24px"
      />
    </n-spin>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { useMessage, useDialog } from 'naive-ui'
import { chroniclesApi, type ChronicleRow, type ChronicleStoryEvent, type ChronicleSnapshot } from '@/api/chronicles'
import { snapshotApi } from '@/api/snapshot'
import { useWorkbenchPlotTimelineReload } from '@/composables/useWorkbenchNarrativeSync'

interface Props {
  slug: string
  highlightRange: { start: number; end: number } | null
  /** 为 true 时编年史行由父组件 `getStoryEvolution` 注入，与左栏同源且由父级监听 tick 刷新 */
  chroniclesFromBundledParent?: boolean
  /** 与 `chroniclesFromBundledParent` 联用；引用变化时同步到时间轴 */
  bundledChronicleRows?: ChronicleRow[] | null
}

const props = withDefaults(defineProps<Props>(), {
  chroniclesFromBundledParent: false,
  bundledChronicleRows: undefined,
})

const emit = defineEmits<{
  'select-event': [event: ChronicleStoryEvent]
  'select-snapshot': [snapshot: ChronicleSnapshot]
  'request-bundle-refresh': []
}>()

const message = useMessage()
const dialog = useDialog()

const loading = ref(false)
const creating = ref(false)
const rows = ref<ChronicleRow[]>([])
const loadError = ref('')

function isHighlighted(chapterIndex: number): boolean {
  if (!props.highlightRange) return false
  return chapterIndex >= props.highlightRange.start && chapterIndex <= props.highlightRange.end
}

function formatTime(timestamp: string | null): string {
  if (!timestamp) return ''
  const date = new Date(timestamp)
  const now = new Date()
  const diff = now.getTime() - date.getTime()
  if (diff < 0) return date.toLocaleString('zh-CN')
  const minutes = Math.floor(diff / 60000)
  const hours = Math.floor(diff / 3600000)
  const days = Math.floor(diff / 86400000)

  if (minutes < 1) return '刚刚'
  if (minutes < 60) return `${minutes}分钟前`
  if (hours < 24) return `${hours}小时前`
  if (days < 7) return `${days}天前`
  return date.toLocaleDateString('zh-CN')
}

async function load() {
  loading.value = true
  loadError.value = ''
  try {
    const res = await chroniclesApi.get(props.slug)
    rows.value = res.rows
  } catch (err: unknown) {
    const e = err as { message?: string }
    loadError.value = e?.message || '加载失败'
    rows.value = []
  } finally {
    loading.value = false
  }
}

function applyBundledChronicleRows() {
  const b = props.bundledChronicleRows
  rows.value = Array.isArray(b) ? b.map((r) => ({ ...r })) : []
  loadError.value = ''
  loading.value = false
}

function onHeaderRefresh() {
  if (props.chroniclesFromBundledParent) {
    emit('request-bundle-refresh')
  } else {
    void load()
  }
}

watch(
  () => props.slug,
  () => {
    if (!props.chroniclesFromBundledParent) void load()
  },
  { immediate: true },
)

watch(
  () => props.bundledChronicleRows,
  () => {
    if (props.chroniclesFromBundledParent) applyBundledChronicleRows()
  },
  { deep: true, immediate: true },
)

useWorkbenchPlotTimelineReload(() => {
  if (!props.chroniclesFromBundledParent) void load()
})

async function handleCreateSnapshot() {
  dialog.create({
    title: '创建快照',
    content: '将创建当前作品状态的快照，包含章节指针和引擎状态。',
    positiveText: '创建',
    negativeText: '取消',
    onPositiveClick: async () => {
      creating.value = true
      try {
        await snapshotApi.create(props.slug, {
          trigger_type: 'MANUAL',
          name: `手动快照 ${new Date().toLocaleString('zh-CN')}`,
          description: '用户手动创建的快照',
        })
        message.success('快照已创建')
        if (props.chroniclesFromBundledParent) {
          emit('request-bundle-refresh')
        } else {
          await load()
        }
      } catch (err: unknown) {
        const e = err as { message?: string }
        message.error(e?.message || '创建快照失败')
      } finally {
        creating.value = false
      }
    },
  })
}
</script>

<style scoped>
.story-timeline {
  height: 100%;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: var(--app-surface);
  border-right: 1px solid var(--plotpilot-split-border);
}

.timeline-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  flex-wrap: wrap;
  gap: 8px 12px;
  padding: 12px 16px;
  border-bottom: 1px solid var(--plotpilot-split-border);
  flex-shrink: 0;
  min-width: 0;
}

.timeline-header :deep(.n-space) {
  flex-shrink: 0;
}

.timeline-alert {
  margin: 12px 16px;
}

.timeline-list {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 16px;
}

.timeline-chapter {
  margin-bottom: 24px;
  padding: 12px;
  border-radius: 6px;
  border: 1px solid var(--n-border-color);
  background: var(--app-surface);
  transition: all 0.2s;
}

.timeline-chapter--highlight {
  border-color: var(--n-primary-color);
  background: rgba(24, 144, 255, 0.04);
  box-shadow: 0 2px 8px rgba(24, 144, 255, 0.15);
}

.chapter-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
}

.chapter-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--n-primary-color);
}

.chapter-content {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding-left: 16px;
}

.timeline-event,
.timeline-snapshot {
  padding: 8px;
  border-radius: 4px;
  background: var(--app-page-bg);
  cursor: pointer;
  transition: all 0.2s;
}

.timeline-event:hover,
.timeline-snapshot:hover {
  background: rgba(24, 144, 255, 0.08);
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.05);
}

.event-title,
.snapshot-name {
  font-size: 13px;
  font-weight: 500;
  margin: 4px 0;
}

.event-desc {
  font-size: 11px;
  color: var(--app-text-muted);
  margin-top: 2px;
}
</style>
