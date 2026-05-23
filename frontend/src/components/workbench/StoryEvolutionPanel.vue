<!-- frontend/src/components/workbench/StoryEvolutionPanel.vue -->
<template>
  <div class="story-evolution-panel">
    <header class="story-evolution-banner" role="region" aria-label="故事演进说明">
      <div class="story-evolution-banner__head">
        <div class="story-evolution-banner__title">
          <n-icon size="15" class="story-evolution-banner__icon"><PulseOutline /></n-icon>
          <n-text strong>故事演进</n-text>
          <n-tag v-if="currentChapter" size="small" round :bordered="false" type="info" style="margin-left:2px">
            第 {{ currentChapter }} 章
          </n-tag>
        </div>
        <n-space size="small" align="center" wrap>
          <n-button-group size="small">
            <n-button
              :type="activeTab === 'state' ? 'primary' : 'default'"
              @click="activeTab = 'state'"
            >
              <template #icon><n-icon><PulseOutline /></n-icon></template>
              状态机
            </n-button>
            <n-button
              :type="activeTab === 'timeline' ? 'primary' : 'default'"
              @click="activeTab = 'timeline'"
            >
              <template #icon><n-icon><ReorderFourOutline /></n-icon></template>
              时间轴
            </n-button>
            <n-button
              :type="activeTab === 'worldline' ? 'primary' : 'default'"
              @click="activeTab = 'worldline'"
            >
              <template #icon><n-icon><GitNetworkOutline /></n-icon></template>
              世界线
            </n-button>
          </n-button-group>
          <n-button size="tiny" secondary @click="openCharacterAnchor">角色档案</n-button>
        </n-space>
      </div>
    </header>

    <!-- 世界线 DAG 模式 -->
    <WorldlineDAG
      v-if="activeTab === 'worldline'"
      :slug="slug"
      @checkpoint-restored="onCheckpointRestored"
    />

    <div v-else-if="activeTab === 'state'" class="evolution-console">
      <section class="evolution-col">
        <div class="evolution-col__head">
          <n-text strong>状态树</n-text>
          <n-tag size="small" :type="latestSnapshot?.status === 'blocked' ? 'error' : 'success'" :bordered="false">
            {{ latestSnapshot ? `第 ${latestSnapshot.chapter_number} 章` : '未生成' }}
          </n-tag>
        </div>
        <n-empty v-if="!latestSnapshot" description="保存章节后生成演进快照" />
        <template v-else>
          <n-descriptions size="small" :column="1" bordered>
            <n-descriptions-item label="Schema">{{ latestSnapshot.schema_version }}</n-descriptions-item>
            <n-descriptions-item label="状态">{{ latestSnapshot.status }}</n-descriptions-item>
            <n-descriptions-item label="时空">
              {{ sceneState.time_anchor || '未标定' }} / {{ sceneState.location || '未标定' }}
            </n-descriptions-item>
            <n-descriptions-item label="情绪余波">{{ sceneState.emotional_residue || '无' }}</n-descriptions-item>
          </n-descriptions>
          <n-divider />
          <n-scrollbar class="state-list">
            <div v-for="[id, char] in characterRows" :key="id" class="state-row">
              <div class="state-row__main">
                <n-text strong>{{ char.name || id }}</n-text>
                <span>{{ char.status || 'alive' }} · {{ char.location || '未知地点' }}</span>
              </div>
              <n-dropdown
                trigger="click"
                :options="characterStatusOptions"
                @select="(status: string | number) => updateCharacterStatus(id, String(status))"
              >
                <n-button size="tiny" quaternary>状态</n-button>
              </n-dropdown>
            </div>
          </n-scrollbar>
        </template>
      </section>

      <section class="evolution-col">
        <div class="evolution-col__head">
          <n-text strong>状态流</n-text>
          <n-button size="tiny" secondary :loading="snapshotsLoading" @click="loadEvolutionSnapshots">刷新</n-button>
        </div>
        <n-alert v-if="gateReport" :type="gateReport.is_pass ? 'success' : 'warning'" class="gate-alert">
          Gate {{ gateReport.is_pass ? '通过' : '存在风险' }} · {{ gateReport.violations.length }} 项
        </n-alert>
        <n-input
          v-model:value="gateOutline"
          type="textarea"
          size="small"
          :autosize="{ minRows: 3, maxRows: 6 }"
          placeholder="粘贴下一章大纲，执行写前 Gate"
        />
        <n-space size="small" wrap>
          <n-button
            v-for="tag in gateBypassTags"
            :key="tag"
            size="tiny"
            secondary
            @click="appendGateTag(tag)"
          >
            {{ tag }}
          </n-button>
        </n-space>
        <n-button size="small" type="primary" secondary :loading="gateLoading" @click="runGate">
          写前 Gate
        </n-button>
        <n-scrollbar class="action-list">
          <div v-for="action in latestActions" :key="action.action_id" class="action-row">
            <n-tag size="small" :bordered="false">{{ action.type }}</n-tag>
            <code>{{ action.action_id }}</code>
          </div>
          <div v-for="violation in gateReport?.violations || []" :key="violation.type + violation.message" class="violation-row">
            <n-tag size="small" :type="violation.level === 'blocking' ? 'error' : 'warning'" :bordered="false">
              {{ violation.level }}
            </n-tag>
            <span>{{ violation.message }}</span>
          </div>
        </n-scrollbar>
      </section>

      <section class="evolution-col">
        <div class="evolution-col__head">
          <n-text strong>证据</n-text>
          <n-tag size="small" :bordered="false">Graph-backed</n-tag>
        </div>
        <n-scrollbar class="evidence-list">
          <div v-for="item in evidenceRows" :key="item.label" class="evidence-row">
            <n-text strong>{{ item.label }}</n-text>
            <span>{{ item.value }}</span>
          </div>
        </n-scrollbar>
      </section>
    </div>

    <!-- 传统时间轴模式（外：导航略收窄，为「时间轴 + 详情」留出宽度；内：提高右栏默认占比，避免详情过窄） -->
    <n-split
      v-else
      direction="horizontal"
      :default-size="0.24"
      :min="0.17"
      :max="0.34"
    >
      <!-- 左栏：故事导航 -->
      <template #1>
        <StoryNavigator
          :slug="slug"
          :current-chapter="currentChapter"
          :evolution-bundle="bundle"
          :evolution-loading="bundleLoading"
          @select-storyline="onSelectStoryline"
        />
      </template>

      <!-- 中栏 + 右栏 -->
      <template #2>
        <n-split direction="horizontal" :default-size="0.55" :min="0.40" :max="0.68">
          <!-- 中栏：时间轴 -->
          <template #1>
            <StoryTimeline
              :slug="slug"
              :highlight-range="highlightRange"
              :chronicles-from-bundled-parent="true"
              :bundled-chronicle-rows="bundledChronicleRows"
              @select-event="onSelectEvent"
              @select-snapshot="onSelectSnapshot"
              @request-bundle-refresh="loadBundle"
            />
          </template>

          <!-- 右栏：详情面板 -->
          <template #2>
            <StoryDetailPanel
              :slug="slug"
              :selected-item="selectedItem"
              @refresh="onCheckpointRestored"
            />
          </template>
        </n-split>
      </template>
    </n-split>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { PulseOutline, ReorderFourOutline, GitNetworkOutline } from '@vicons/ionicons5'
import {
  WORKBENCH_CHAPTER_DESK_CHANGE_EVENT,
  WORKBENCH_OPEN_SETTINGS_PANEL_EVENT,
} from '@/workbench/deskEvents'
import { narrativeEngineApi, type StoryEvolutionReadModel } from '@/api/narrativeEngine'
import { evolutionApi, type EvolutionGateReport, type EvolutionSnapshot } from '@/api/evolution'
import type { ChronicleRow } from '@/api/chronicles'
import { useWorkbenchPlotTimelineReload } from '@/composables/useWorkbenchNarrativeSync'
import StoryNavigator from './StoryNavigator.vue'
import StoryTimeline from './StoryTimeline.vue'
import StoryDetailPanel from './StoryDetailPanel.vue'
import WorldlineDAG from './WorldlineDAG.vue'

interface Props {
  slug: string
  currentChapter: number | null
}

const props = defineProps<Props>()

const bundle = ref<StoryEvolutionReadModel | null>(null)
const bundleLoading = ref(false)

// 活跃 tab
const activeTab = ref<'state' | 'timeline' | 'worldline'>('state')

// 高亮范围（选中故事线时高亮对应章节）
const highlightRange = ref<{ start: number; end: number } | null>(null)

// 选中的项目（事件或快照）
const selectedItem = ref<any>(null)
const snapshots = ref<EvolutionSnapshot[]>([])
const snapshotsLoading = ref(false)
const gateOutline = ref('')
const gateLoading = ref(false)
const gateReport = ref<EvolutionGateReport | null>(null)
const overrideLoading = ref(false)
const gateBypassTags = ['[TimeSkip]', '[HardCut]', '[POVSwitch]', '[AmbiguousFate]']
const characterStatusOptions = [
  { label: 'alive', key: 'alive' },
  { label: 'dead', key: 'dead' },
  { label: 'missing', key: 'missing' },
  { label: 'ambiguous', key: 'ambiguous' },
  { label: 'severely_injured', key: 'severely_injured' },
]

async function loadBundle() {
  bundleLoading.value = true
  bundle.value = null
  try {
    bundle.value = await narrativeEngineApi.getStoryEvolution(props.slug)
  } catch {
    bundle.value = null
  } finally {
    bundleLoading.value = false
  }
}

async function loadEvolutionSnapshots() {
  snapshotsLoading.value = true
  try {
    const result = await evolutionApi.listSnapshots(props.slug)
    snapshots.value = result.snapshots || []
  } catch {
    snapshots.value = []
  } finally {
    snapshotsLoading.value = false
  }
}

async function runGate() {
  if (!props.currentChapter) return
  gateLoading.value = true
  try {
    gateReport.value = await evolutionApi.gate(props.slug, {
      chapter_number: props.currentChapter,
      outline_content: gateOutline.value,
      branch_id: 'main',
      tags: [],
    })
  } finally {
    gateLoading.value = false
  }
}

function appendGateTag(tag: string) {
  if (gateOutline.value.includes(tag)) return
  gateOutline.value = `${tag} ${gateOutline.value || ''}`.trim()
}

function escapeJsonPointer(value: string) {
  return value.replace(/~/g, '~0').replace(/\//g, '~1')
}

async function updateCharacterStatus(characterId: string, status: string) {
  const snapshot = latestSnapshot.value
  if (!snapshot || overrideLoading.value) return
  overrideLoading.value = true
  try {
    await evolutionApi.applyOverrides(props.slug, snapshot.chapter_number, [
      {
        op: 'replace',
        path: `/characters/${escapeJsonPointer(characterId)}/status`,
        value: status,
      },
    ])
    await loadEvolutionSnapshots()
  } finally {
    overrideLoading.value = false
  }
}

const bundledChronicleRows = computed((): ChronicleRow[] => {
  const raw = bundle.value?.chronotope?.rows
  if (!Array.isArray(raw)) return []
  return raw as ChronicleRow[]
})

const latestSnapshot = computed(() => snapshots.value[0] || null)
const sceneState = computed(() => (latestSnapshot.value?.ending_state?.scene || {}) as Record<string, any>)
const characterRows = computed(() => Object.entries((latestSnapshot.value?.ending_state?.characters || {}) as Record<string, any>).slice(0, 16))
const latestActions = computed(() => latestSnapshot.value?.delta_actions || [])
const evidenceRows = computed(() => {
  const snapshot = latestSnapshot.value
  if (!snapshot) return [{ label: '状态', value: '暂无证据' }]
  return [
    { label: 'Source refs', value: `${snapshot.source_refs.length} 条` },
    { label: 'Conflicts', value: `${snapshot.conflicts.length} 条` },
    { label: 'Active', value: bundle.value?.evolution_surface?.active_snapshot?.summary || '暂无水化摘要' },
    { label: 'Actions', value: `${snapshot.delta_actions.length} 条标准动作` },
  ]
})

watch(
  () => props.slug,
  () => {
    highlightRange.value = null
    selectedItem.value = null
    void loadBundle()
    void loadEvolutionSnapshots()
  },
  { immediate: true },
)

useWorkbenchPlotTimelineReload(() => {
  void loadBundle()
  void loadEvolutionSnapshots()
})

// 选中故事线时高亮章节范围
function onSelectStoryline(storyline: { startChapter: number; endChapter: number }) {
  highlightRange.value = {
    start: storyline.startChapter,
    end: storyline.endChapter,
  }
}

// 选中剧情事件
function onSelectEvent(event: any) {
  selectedItem.value = { type: 'event', data: event }
}

// 选中快照
function onSelectSnapshot(snapshot: any) {
  selectedItem.value = { type: 'snapshot', data: snapshot }
}

/** 快照回滚等：与 Workbench 整桌同步（章节树、正文、伏笔 tick 等） */
function onCheckpointRestored() {
  highlightRange.value = null
  selectedItem.value = null
  window.dispatchEvent(new CustomEvent(WORKBENCH_CHAPTER_DESK_CHANGE_EVENT))
  void loadEvolutionSnapshots()
}

function openCharacterAnchor() {
  window.dispatchEvent(
    new CustomEvent(WORKBENCH_OPEN_SETTINGS_PANEL_EVENT, { detail: { panel: 'sandbox' } }),
  )
}
</script>

<style scoped>
.story-evolution-panel {
  height: 100%;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: var(--app-surface);
}

.story-evolution-banner {
  flex-shrink: 0;
  padding: 8px 12px;
  border-bottom: 1px solid var(--app-border, rgba(0, 0, 0, 0.08));
  background: var(--app-surface-elevated, var(--app-surface));
}

.story-evolution-banner__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  flex-wrap: wrap;
}

.story-evolution-banner__title {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 14px;
  min-width: 0;
}

.story-evolution-banner__icon {
  color: var(--color-brand);
  opacity: 0.8;
  flex-shrink: 0;
}

.story-evolution-panel :deep(.n-split) {
  flex: 1;
  min-height: 0;
  height: auto;
}

.story-evolution-panel :deep(.n-split-pane-1),
.story-evolution-panel :deep(.n-split-pane-2) {
  min-height: 0;
  overflow: hidden;
}

.evolution-console {
  flex: 1;
  min-height: 0;
  display: grid;
  grid-template-columns: minmax(240px, 0.9fr) minmax(280px, 1.1fr) minmax(240px, 0.9fr);
  gap: 0;
  overflow: hidden;
}

.evolution-col {
  min-width: 0;
  min-height: 0;
  padding: 12px;
  border-right: 1px solid var(--app-border, rgba(0, 0, 0, 0.08));
  display: flex;
  flex-direction: column;
  gap: 10px;
  overflow: hidden;
}

.evolution-col:last-child {
  border-right: 0;
}

.evolution-col__head {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.state-list,
.action-list,
.evidence-list {
  flex: 1;
  min-height: 0;
}

.state-row,
.action-row,
.violation-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 7px 0;
  border-bottom: 1px solid var(--app-border-soft, rgba(0, 0, 0, 0.06));
  font-size: 12px;
}

.state-row {
  justify-content: space-between;
}

.state-row__main {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.state-row span,
.violation-row span {
  min-width: 0;
  overflow-wrap: anywhere;
  color: var(--app-text-muted, rgba(0, 0, 0, 0.58));
}

.action-row code {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--app-text-muted, rgba(0, 0, 0, 0.58));
}

.gate-alert {
  flex-shrink: 0;
}

.evidence-row {
  padding: 8px 0;
  border-bottom: 1px solid var(--app-border-soft, rgba(0, 0, 0, 0.06));
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 12px;
}

.evidence-row span {
  color: var(--app-text-muted, rgba(0, 0, 0, 0.58));
  line-height: 1.5;
  overflow-wrap: anywhere;
}

@media (max-width: 900px) {
  .evolution-console {
    grid-template-columns: 1fr;
    overflow: auto;
  }

  .evolution-col {
    min-height: 260px;
    border-right: 0;
    border-bottom: 1px solid var(--app-border, rgba(0, 0, 0, 0.08));
  }
}
</style>
