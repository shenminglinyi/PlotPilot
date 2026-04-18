<template>
  <div class="hc-panel">
    <header class="hc-head">
      <div>
        <h3 class="hc-title">全息编年史</h3>
        <p class="hc-lead">
          中轴为章进度锚点：<strong>左</strong>里世界剧情时间，<strong>右</strong>表世界快照（存档）。
          悬浮右侧快照节点时高亮本行左侧剧情；回滚将删除快照未包含的章节（不可撤销）。
        </p>
      </div>
      <n-button size="small" type="primary" :loading="loading" @click="load">刷新</n-button>
    </header>

    <n-alert v-if="noteText" type="default" :show-icon="true" class="hc-note" style="font-size: 11px">
      {{ noteText }}
    </n-alert>

    <n-radio-group v-model:value="hcView" size="small" class="hc-mode-switch">
      <n-radio-button value="helix">双螺旋概览</n-radio-button>
      <n-radio-button value="timeline">剧情时间线 · 列表编辑（Bible）</n-radio-button>
    </n-radio-group>

    <div class="hc-view-body">
      <n-spin v-show="hcView === 'helix'" :show="loading" class="hc-spin">
        <div v-if="rows.length === 0 && !loading" class="hc-empty-wrap">
          <n-empty
            description="暂无编年节点：可切换到「剧情时间线 · 列表编辑」维护 Bible 时间线，或在后端创建 novel_snapshots"
          >
            <template #icon><span style="font-size: 40px">🧬</span></template>
          </n-empty>
        </div>

        <div v-else class="helix-wrap">
        <div class="helix-header">
          <span class="helix-header-spine">进度</span>
          <span class="helix-header-left">里世界 · 剧情</span>
          <span class="helix-header-right">表世界 · 快照</span>
        </div>

        <div
          v-for="row in rows"
          :key="row.chapter_index"
          class="helix-row"
          :class="{ 'helix-row--hot': hoverChapter === row.chapter_index }"
        >
          <div class="helix-chapter">
            <span class="helix-dot" />
            <span class="helix-ch-num">第 {{ row.chapter_index }} 章</span>
          </div>

          <div class="helix-cell helix-cell--story">
            <div
              v-for="ev in row.story_events"
              :key="ev.note_id"
              class="story-node"
            >
              <n-tag type="success" size="tiny" round>{{ ev.time }}</n-tag>
              <div class="story-title">{{ ev.title }}</div>
              <div v-if="ev.description" class="story-desc">{{ ev.description }}</div>
            </div>
            <n-text v-if="row.story_events.length === 0" depth="3" style="font-size: 11px">—</n-text>
          </div>

          <div class="helix-cell helix-cell--snap">
            <div
              v-for="sn in row.snapshots"
              :key="sn.id"
              class="snap-node"
              :title="snapTooltip(sn)"
              @mouseenter="hoverChapter = row.chapter_index"
              @mouseleave="onSnapNodeLeave"
            >
              <n-tag :type="sn.kind === 'MANUAL' ? 'warning' : 'info'" size="tiny" round>
                {{ sn.kind === 'MANUAL' ? '🟣 Manual' : '🔵 Auto' }}
              </n-tag>
              <span class="snap-name">{{ sn.name }}</span>
              <n-button
                size="tiny"
                quaternary
                :loading="rollbackId === sn.id"
                title="删除快照未收录的章节，恢复至该存档时的章节集合"
                @click.stop="confirmRollback(sn)"
              >
                回滚
              </n-button>
            </div>
            <n-text v-if="row.snapshots.length === 0" depth="3" style="font-size: 11px">—</n-text>
          </div>
        </div>

        <div class="axis-footer">
          书目已展开至第 <strong>{{ maxChapter }}</strong> 章（章号来自章节表；编年条仅包含有数据的章位）
        </div>
        </div>
      </n-spin>

      <div v-show="hcView === 'timeline'" class="hc-view-embed">
        <TimelinePanel :slug="slug" />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { useWorkbenchRefreshStore } from '../../stores/workbenchRefreshStore'
import { useDialog, useMessage } from 'naive-ui'
import { chroniclesApi } from '../../api/chronicles'
import type { ChronicleRow, ChronicleSnapshot } from '../../api/chronicles'
import TimelinePanel from './TimelinePanel.vue'

const props = defineProps<{ slug: string }>()
const message = useMessage()
const dialog = useDialog()

type HcView = 'helix' | 'timeline'
const hcView = ref<HcView>('helix')

const loading = ref(false)
const rows = ref<ChronicleRow[]>([])
const maxChapter = ref(1)
const noteText = ref('')
const hoverChapter = ref<number | null>(null)
const rollbackId = ref<string | null>(null)

const refreshStore = useWorkbenchRefreshStore()
const { chroniclesTick } = storeToRefs(refreshStore)

function snapTooltip(sn: ChronicleSnapshot): string {
  const parts = [sn.name, sn.description, sn.created_at].filter(Boolean)
  return parts.join(' · ')
}

/** 从快照节点移入同章左侧剧情时不熄灭高亮 */
function onSnapNodeLeave(ev: MouseEvent) {
  const rowEl = (ev.currentTarget as HTMLElement | null)?.closest('.helix-row')
  const to = ev.relatedTarget as Node | null
  if (rowEl && to && rowEl.contains(to)) return
  hoverChapter.value = null
}

function confirmRollback(sn: ChronicleSnapshot) {
  dialog.warning({
    title: '确认回滚到此快照？',
    content:
      `将删除当前作品中未包含在该快照「章节指针」内的章节正文（${sn.name || sn.id}）。此操作不可撤销。`,
    positiveText: '回滚',
    negativeText: '取消',
    onPositiveClick: async () => {
      rollbackId.value = sn.id
      try {
        const res = await chroniclesApi.rollbackToSnapshot(props.slug, sn.id)
        message.success(`已回滚，移除 ${res.deleted_count} 个章节`)
        refreshStore.bumpAfterChapterDeskChange()
        await load()
      } catch {
        message.error('回滚失败，请查看后端日志')
        return false
      } finally {
        rollbackId.value = null
      }
    },
  })
}

async function load() {
  loading.value = true
  try {
    const res = await chroniclesApi.get(props.slug)
    rows.value = res.rows
    maxChapter.value = res.max_chapter_in_book
    noteText.value = res.note
  } catch {
    rows.value = []
    noteText.value = ''
    message.error('编年史加载失败，请确认后端已包含 /chronicles 接口')
  } finally {
    loading.value = false
  }
}

watch(() => props.slug, () => void load(), { immediate: true })

watch(chroniclesTick, () => {
  void load()
})
</script>

<style scoped>
.hc-panel {
  height: 100%;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  padding: 16px;
  background: linear-gradient(to bottom, var(--n-color-modal) 0%, rgba(99, 102, 241, 0.02) 100%);
}

.hc-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
  margin-bottom: 14px;
  flex-shrink: 0;
}

.hc-title {
  margin: 0 0 8px;
  font-size: 18px;
  font-weight: 700;
  background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}

.hc-lead {
  margin: 0;
  font-size: 12px;
  line-height: 1.6;
  color: var(--n-text-color-3);
  max-width: 540px;
}

.hc-note {
  flex-shrink: 0;
  margin-bottom: 12px;
  border-radius: 8px;
}

.hc-mode-switch {
  width: 100%;
  margin-bottom: 12px;
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  flex-shrink: 0;
}

.hc-mode-switch :deep(.n-radio-group) {
  display: flex;
  flex-wrap: wrap;
  width: 100%;
  gap: 4px;
}

.hc-mode-switch :deep(.n-radio-button) {
  flex: 1 1 auto;
  min-width: 0;
}

.hc-mode-switch :deep(.n-radio-button__state-border) {
  white-space: normal;
  text-align: center;
  line-height: 1.25;
  padding: 6px 8px;
}

.hc-view-body {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.hc-spin {
  flex: 1;
  min-height: 0;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

/* 双螺旋随章数变长时不人为限高；在标签页可视区内滚动 */
.hc-spin :deep(.n-spin-content) {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
}

.hc-view-embed {
  flex: 1;
  min-height: 360px;
  height: min(65vh, 640px);
  max-height: 720px;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.hc-view-embed :deep(.timeline-panel) {
  flex: 1;
  min-height: 0;
  border-radius: 12px;
  overflow: hidden;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.06);
}

.hc-empty-wrap {
  padding: 32px 0;
}

.helix-wrap {
  position: relative;
  padding: 12px 8px 16px;
  border: 1px solid var(--n-border-color);
  border-radius: 12px;
  background: var(--n-color-modal);
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.06);
}

.helix-header {
  display: grid;
  grid-template-columns: 64px 1fr 1fr;
  gap: 12px;
  align-items: center;
  padding: 8px 6px 12px;
  margin-bottom: 6px;
  border-bottom: 2px solid var(--n-border-color);
  position: sticky;
  top: 0;
  z-index: 2;
  background: var(--n-color-modal);
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  color: var(--n-text-color-2);
}

.helix-header-spine {
  text-align: center;
  font-size: 10px;
}

.helix-header-left {
  text-align: left;
  padding-left: 6px;
  color: #18a058;
}

.helix-header-right {
  text-align: left;
  padding-left: 8px;
  color: #6366f1;
}

.helix-row {
  display: grid;
  grid-template-columns: 64px 1fr 1fr;
  gap: 12px;
  align-items: start;
  padding: 14px 0;
  border-bottom: 1px dashed rgba(99, 102, 241, 0.15);
  transition: all 0.2s ease;
}

.helix-row--hot {
  background: linear-gradient(to right, rgba(24, 160, 88, 0.06), rgba(99, 102, 241, 0.08));
  border-radius: 8px;
  padding-left: 6px;
  padding-right: 6px;
  margin-left: -6px;
  margin-right: -6px;
}

.helix-chapter {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  padding-top: 6px;
}

.helix-dot {
  width: 12px;
  height: 12px;
  border-radius: 50%;
  background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%);
  box-shadow: 0 0 0 4px rgba(99, 102, 241, 0.2), 0 2px 8px rgba(99, 102, 241, 0.3);
  transition: all 0.3s ease;
}

.helix-row--hot .helix-dot {
  transform: scale(1.2);
  box-shadow: 0 0 0 6px rgba(99, 102, 241, 0.3), 0 4px 12px rgba(99, 102, 241, 0.5);
}

.helix-ch-num {
  font-size: 11px;
  font-weight: 600;
  color: var(--n-text-color-2);
  writing-mode: vertical-rl;
  text-orientation: mixed;
  max-height: 80px;
  line-height: 1.3;
}

.helix-cell {
  min-width: 0;
}

.helix-cell--story {
  border-right: 3px solid rgba(24, 160, 88, 0.4);
  padding-right: 12px;
}

.helix-cell--snap {
  padding-left: 8px;
}

.story-node {
  margin-bottom: 10px;
  padding: 10px 12px;
  border-radius: 8px;
  background: linear-gradient(135deg, rgba(24, 160, 88, 0.08), rgba(24, 160, 88, 0.12));
  border: 1px solid rgba(24, 160, 88, 0.25);
  box-shadow: 0 2px 6px rgba(24, 160, 88, 0.1);
  transition: all 0.2s ease;
}

.story-node:hover {
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(24, 160, 88, 0.2);
}

.story-title {
  font-size: 13px;
  font-weight: 600;
  margin-top: 6px;
  line-height: 1.5;
  color: var(--n-text-color-1);
}

.story-desc {
  font-size: 12px;
  color: var(--n-text-color-2);
  margin-top: 5px;
  line-height: 1.5;
}

.snap-node {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
  padding: 10px 12px;
  border-radius: 8px;
  background: linear-gradient(135deg, rgba(99, 102, 241, 0.08), rgba(139, 92, 246, 0.12));
  border: 1px solid rgba(99, 102, 241, 0.3);
  box-shadow: 0 2px 6px rgba(99, 102, 241, 0.1);
  transition: all 0.2s ease;
  cursor: pointer;
}

.snap-node:hover {
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(99, 102, 241, 0.25);
  border-color: rgba(99, 102, 241, 0.5);
}

.snap-name {
  flex: 1;
  min-width: 0;
  font-size: 13px;
  font-weight: 600;
  color: var(--n-text-color-1);
}

.axis-footer {
  font-size: 11px;
  color: var(--n-text-color-3);
  padding: 12px 10px 6px;
  border-top: 2px solid var(--n-border-color);
  background: linear-gradient(to top, rgba(99, 102, 241, 0.03), transparent);
}

.hc-panel :deep(.n-alert) {
  border-radius: 8px;
}
</style>
