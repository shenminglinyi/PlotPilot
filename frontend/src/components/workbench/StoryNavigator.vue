<!-- frontend/src/components/workbench/StoryNavigator.vue -->
<template>
  <div class="story-navigator">
    <!-- 故事阶段 -->
    <div class="phase-section">
      <div class="section-header">
        <span class="section-icon">📊</span>
        <span class="section-title">故事阶段</span>
      </div>
      <n-spin :show="phaseLoading">
        <div v-if="phase" class="phase-visual">
          <div class="phase-track">
            <div
              v-for="s in PHASE_STAGES"
              :key="s.key"
              class="phase-stage"
              :class="{
                'phase-stage--active': s.key === phase.phase,
                'phase-stage--past': isPhasePast(s.key, phase.phase),
              }"
            >
              <div class="stage-dot" />
              <n-text depth="3" style="font-size: 10px">{{ s.label }}</n-text>
            </div>
          </div>
          <n-progress
            type="line"
            :percentage="Math.round(phase.progress * 100)"
            :height="6"
            :show-indicator="false"
            style="margin-top: 8px"
          />
        </div>
      </n-spin>
    </div>

    <!-- 故事线树 -->
    <div class="storylines-section">
      <div class="section-header">
        <span class="section-icon">📖</span>
        <span class="section-title">故事线</span>
        <n-button size="tiny" quaternary @click="openAddModal(null)">+</n-button>
      </div>

      <n-spin :show="storylinesLoading">
        <div v-if="allStorylines.length === 0" class="empty-state">
          <n-text depth="3" style="font-size: 12px">暂无故事线</n-text>
          <n-text depth="3" style="font-size: 11px; display: block; margin-top: 6px; line-height: 1.5">
            点击「+」手动创建，或在创建向导完成后自动出现。
          </n-text>
        </div>

        <div v-else class="storylines-tree">
          <!-- 主线节点 + 其子故事线 -->
          <template v-for="node in storylineTree" :key="node.sl.id">
            <div
              class="storyline-item storyline-item--main"
              :class="{ 'storyline-item--active': selectedStorylineId === node.sl.id }"
              @click="selectStoryline(node.sl)"
            >
              <div class="storyline-item__row">
                <n-tag type="success" size="small" round>主线</n-tag>
                <span class="storyline-name">{{ node.sl.name || `故事线 ${node.sl.id.slice(0,8)}` }}</span>
                <n-tag :type="getStatusColor(node.sl.status)" size="tiny" round>{{ getStatusLabel(node.sl.status) }}</n-tag>
              </div>
              <n-text depth="3" style="font-size: 11px; margin-left: 4px">
                第 {{ node.sl.estimated_chapter_start }}–{{ node.sl.estimated_chapter_end }} 章
              </n-text>
            </div>

            <!-- 子故事线 -->
            <div
              v-for="child in node.children"
              :key="child.id"
              class="storyline-item storyline-item--child"
              :class="{ 'storyline-item--active': selectedStorylineId === child.id }"
              @click="selectStoryline(child)"
            >
              <div class="storyline-item__row">
                <span class="child-indent">└─</span>
                <n-tag :type="getRoleColor(child.role)" size="small" round>{{ getRoleLabel(child.role) }}</n-tag>
                <span class="storyline-name">{{ child.name || `故事线 ${child.id.slice(0,8)}` }}</span>
                <n-tooltip v-if="confluenceMap[child.id]" trigger="hover">
                  <template #trigger>
                    <span class="confluence-badge">
                      {{ confluenceMap[child.id].merge_type === 'reveal' ? '◎' : '▶' }}
                      第{{ confluenceMap[child.id].target_chapter }}章
                    </span>
                  </template>
                  {{ confluenceMap[child.id].merge_type === 'reveal' ? '揭露点' : '汇流至主线' }}：{{ confluenceMap[child.id].context_summary }}
                </n-tooltip>
              </div>
              <n-text depth="3" style="font-size: 11px; margin-left: 28px">
                第 {{ child.estimated_chapter_start }}–{{ child.estimated_chapter_end }} 章
              </n-text>
            </div>

            <!-- 添加子故事线按钮 -->
            <div class="add-child-btn" @click="openAddModal(node.sl.id)">
              <n-text depth="3" style="font-size: 11px; cursor: pointer">└─ + 添加支线/暗线</n-text>
            </div>
          </template>

          <!-- 无父级的非主线（孤立故事线） -->
          <div
            v-for="sl in orphanLines"
            :key="sl.id"
            class="storyline-item"
            :class="{ 'storyline-item--active': selectedStorylineId === sl.id }"
            @click="selectStoryline(sl)"
          >
            <div class="storyline-item__row">
              <n-tag :type="getRoleColor(sl.role)" size="small" round>{{ getRoleLabel(sl.role) }}</n-tag>
              <span class="storyline-name">{{ sl.name || `故事线 ${sl.id.slice(0,8)}` }}</span>
            </div>
            <n-text depth="3" style="font-size: 11px; margin-left: 4px">
              第 {{ sl.estimated_chapter_start }}–{{ sl.estimated_chapter_end }} 章
            </n-text>
          </div>
        </div>
      </n-spin>
    </div>

    <!-- 汇流点轴 -->
    <div v-if="confluenceList.length > 0" class="confluence-axis-section">
      <div class="section-header">
        <span class="section-icon">⑂</span>
        <span class="section-title">汇流轴</span>
      </div>
      <div class="confluence-axis">
        <div
          v-for="cp in confluenceList"
          :key="cp.id"
          class="confluence-marker"
          :class="{
            'confluence-marker--resolved': cp.resolved,
            'confluence-marker--reveal': cp.merge_type === 'reveal',
          }"
        >
          <n-tooltip trigger="hover">
            <template #trigger>
              <div class="marker-dot">{{ cp.merge_type === 'reveal' ? '◎' : '▶' }}</div>
            </template>
            <div>第{{ cp.target_chapter }}章</div>
            <div>{{ cp.context_summary }}</div>
          </n-tooltip>
          <span class="marker-ch">{{ cp.target_chapter }}</span>
        </div>
      </div>
    </div>

    <!-- 新建故事线弹窗 -->
    <n-modal
      v-model:show="showAddModal"
      preset="card"
      title="新建故事线"
      style="width: 480px"
      :mask-closable="false"
      @after-leave="resetAddForm"
    >
      <n-form label-placement="left" label-width="80" size="small">
        <n-form-item label="结构角色">
          <n-radio-group v-model:value="addForm.role" size="small">
            <n-radio-button value="main">主线</n-radio-button>
            <n-radio-button value="sub">支线</n-radio-button>
            <n-radio-button value="dark">暗线</n-radio-button>
          </n-radio-group>
        </n-form-item>
        <n-form-item label="主题">
          <n-select v-model:value="addForm.storyline_type" :options="themeOptions" />
        </n-form-item>
        <n-form-item label="名称">
          <n-input v-model:value="addForm.name" placeholder="可选，便于识别" clearable />
        </n-form-item>
        <n-form-item label="说明">
          <n-input
            v-model:value="addForm.description"
            type="textarea"
            placeholder="可选"
            :autosize="{ minRows: 2, maxRows: 4 }"
          />
        </n-form-item>
        <n-form-item v-if="addForm.role !== 'main'" label="归属主线">
          <n-select
            v-model:value="addForm.parent_id"
            :options="mainlineOptions"
            placeholder="选择归属的主线（可选）"
            clearable
          />
        </n-form-item>
        <n-form-item label="章节起">
          <n-input-number v-model:value="addForm.estimated_chapter_start" :min="1" style="width: 100%" />
        </n-form-item>
        <n-form-item label="章节止">
          <n-input-number v-model:value="addForm.estimated_chapter_end" :min="1" style="width: 100%" />
        </n-form-item>

        <!-- 汇流点设置（支线/暗线专有） -->
        <template v-if="addForm.role !== 'main'">
          <n-divider style="margin: 8px 0">汇流点设置</n-divider>
          <n-form-item label="汇流类型">
            <n-select v-model:value="addForm.confluence_merge_type" :options="mergeTypeOptions" />
          </n-form-item>
          <n-form-item label="汇流章节">
            <n-input-number
              v-model:value="addForm.confluence_chapter"
              :min="addForm.estimated_chapter_start || 1"
              placeholder="预计在第几章汇流"
              style="width: 100%"
            />
          </n-form-item>
          <n-form-item label="汇流描述">
            <n-input
              v-model:value="addForm.confluence_summary"
              type="textarea"
              placeholder="汇流时发生什么（供 AI 参考）"
              :autosize="{ minRows: 2, maxRows: 4 }"
            />
          </n-form-item>
          <!-- 暗线专有：行为禁忌 -->
          <template v-if="addForm.role === 'dark'">
            <n-form-item label="揭露前提示">
              <n-input
                v-model:value="addForm.pre_reveal_hint"
                type="textarea"
                placeholder="告诉 AI 有个秘密在运行，但不说内容"
                :autosize="{ minRows: 2, maxRows: 3 }"
              />
            </n-form-item>
            <n-form-item label="行为禁忌">
              <div class="guards-list">
                <div v-for="(g, idx) in addForm.behavior_guards" :key="idx" class="guard-row">
                  <n-input v-model:value="addForm.behavior_guards[idx]" size="small" placeholder="禁止 AI 做的事" />
                  <n-button size="tiny" quaternary @click="addForm.behavior_guards.splice(idx, 1)">×</n-button>
                </div>
                <n-button size="tiny" dashed @click="addForm.behavior_guards.push('')">+ 添加禁忌</n-button>
              </div>
            </n-form-item>
          </template>
        </template>
      </n-form>
      <template #footer>
        <n-space justify="end">
          <n-button quaternary @click="showAddModal = false">取消</n-button>
          <n-button type="primary" :loading="addSubmitting" @click="submitAddStoryline">创建</n-button>
        </n-space>
      </template>
    </n-modal>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useMessage } from 'naive-ui'
import { storyPhaseApi, type StoryPhaseDTO } from '@/api/engineCore'
import { workflowApi, type StorylineDTO, confluenceApi, type ConfluencePointDTO } from '@/api/workflow'
import { narrativeEngineApi, type StoryEvolutionReadModel } from '@/api/narrativeEngine'
import { useWorkbenchRefreshStore } from '@/stores/workbenchRefreshStore'

interface Props {
  slug: string
  currentChapter: number | null
  evolutionBundle: StoryEvolutionReadModel | null
  evolutionLoading: boolean
}

const props = defineProps<Props>()
const emit = defineEmits<{
  selectStoryline: [storyline: { startChapter: number; endChapter: number }]
}>()

const message = useMessage()
const refreshStore = useWorkbenchRefreshStore()

const phaseLoading = ref(false)
const storylinesLoading = ref(false)
const phase = ref<StoryPhaseDTO | null>(null)
const allStorylines = ref<StorylineDTO[]>([])
const confluenceList = ref<ConfluencePointDTO[]>([])
const selectedStorylineId = ref<string | null>(null)
const showAddModal = ref(false)
const addSubmitting = ref(false)

const addForm = ref({
  role: 'sub' as 'main' | 'sub' | 'dark',
  storyline_type: 'general',
  name: '',
  description: '',
  parent_id: null as string | null,
  estimated_chapter_start: 1,
  estimated_chapter_end: 10,
  confluence_merge_type: 'absorb' as 'intersect' | 'absorb' | 'reveal',
  confluence_chapter: null as number | null,
  confluence_summary: '',
  pre_reveal_hint: '',
  behavior_guards: [] as string[],
})

function resetAddForm() {
  addForm.value = {
    role: 'sub', storyline_type: 'general', name: '', description: '',
    parent_id: null, estimated_chapter_start: 1, estimated_chapter_end: 10,
    confluence_merge_type: 'absorb', confluence_chapter: null, confluence_summary: '',
    pre_reveal_hint: '', behavior_guards: [],
  }
}

function openAddModal(parentId: string | null) {
  const ch = props.currentChapter ?? 1
  addForm.value = {
    ...addForm.value,
    role: parentId ? 'sub' : 'main',
    parent_id: parentId,
    estimated_chapter_start: ch,
    estimated_chapter_end: Math.max(ch, ch + 9),
    confluence_chapter: null,
    confluence_summary: '',
    pre_reveal_hint: '',
    behavior_guards: [],
  }
  showAddModal.value = true
}

const themeOptions = [
  { label: '通用', value: 'general' },
  { label: '情感', value: 'romance' },
  { label: '复仇', value: 'revenge' },
  { label: '悬疑', value: 'mystery' },
  { label: '成长', value: 'growth' },
  { label: '政治', value: 'political' },
  { label: '冒险', value: 'adventure' },
  { label: '家族', value: 'family' },
  { label: '友情', value: 'friendship' },
]

const mergeTypeOptions = [
  { label: '吸收（支线完结并入主线）', value: 'absorb' },
  { label: '交叉（两线继续并行）', value: 'intersect' },
  { label: '揭露（暗线首次显现）', value: 'reveal' },
]

const mainlineOptions = computed(() =>
  allStorylines.value
    .filter(s => s.role === 'main' || s.storyline_type === 'MAIN_PLOT' || s.storyline_type === 'main_plot')
    .map(s => ({ label: s.name || `主线 ${s.id.slice(0, 8)}`, value: s.id }))
)

// confluenceMap: storyline.id → nearest unresolved confluence point
const confluenceMap = computed(() => {
  const map: Record<string, ConfluencePointDTO> = {}
  for (const cp of confluenceList.value) {
    if (cp.resolved) continue
    const prev = map[cp.source_storyline_id]
    if (!prev || cp.target_chapter < prev.target_chapter) {
      map[cp.source_storyline_id] = cp
    }
  }
  return map
})

// Build tree: main storylines with their children
const storylineTree = computed(() => {
  const mains = allStorylines.value.filter(
    s => s.role === 'main' || s.storyline_type === 'MAIN_PLOT' || s.storyline_type === 'main_plot'
  )
  return mains.map(main => ({
    sl: main,
    children: allStorylines.value.filter(s => s.parent_id === main.id),
  }))
})

// Storylines without a parent that are not main
const orphanLines = computed(() =>
  allStorylines.value.filter(s => {
    const isMain = s.role === 'main' || s.storyline_type === 'MAIN_PLOT' || s.storyline_type === 'main_plot'
    return !isMain && !s.parent_id
  })
)

async function submitAddStoryline() {
  const f = addForm.value
  if (f.estimated_chapter_end < f.estimated_chapter_start) {
    message.warning('结束章节不能小于起始章节')
    return
  }
  addSubmitting.value = true
  try {
    const created = await workflowApi.createStoryline(props.slug, {
      storyline_type: f.storyline_type,
      role: f.role,
      parent_id: f.parent_id ?? undefined,
      estimated_chapter_start: f.estimated_chapter_start,
      estimated_chapter_end: f.estimated_chapter_end,
      name: f.name?.trim() || undefined,
      description: f.description?.trim() || undefined,
    })

    const newId = created?.id
    if (newId && f.role !== 'main' && f.confluence_chapter) {
      const mainId = f.parent_id || mainlineOptions.value[0]?.value
      if (mainId) {
        await confluenceApi.create(props.slug, {
          source_storyline_id: newId,
          target_storyline_id: mainId,
          target_chapter: f.confluence_chapter,
          merge_type: f.confluence_merge_type,
          context_summary: f.confluence_summary,
          pre_reveal_hint: f.role === 'dark' ? f.pre_reveal_hint : '',
          behavior_guards: f.role === 'dark' ? f.behavior_guards.filter(Boolean) : [],
        })
      }
    }

    message.success('故事线已创建')
    showAddModal.value = false
    await loadData()
    refreshStore.bumpDesk()
  } catch (err: any) {
    const detail = err?.response?.data?.detail
    message.error(typeof detail === 'string' ? detail : err?.message || '创建失败')
  } finally {
    addSubmitting.value = false
  }
}

async function loadData() {
  phaseLoading.value = true
  storylinesLoading.value = true
  try {
    if (props.evolutionBundle) {
      phase.value = props.evolutionBundle.life_cycle
      allStorylines.value = (props.evolutionBundle.plot_spine as any)?.storylines || []
      confluenceList.value = (props.evolutionBundle.plot_spine as any)?.confluence_points || []
    } else {
      const bundle = await narrativeEngineApi.getStoryEvolution(props.slug)
      phase.value = bundle.life_cycle
      allStorylines.value = (bundle.plot_spine as any)?.storylines || []
      confluenceList.value = (bundle.plot_spine as any)?.confluence_points || []
    }
  } catch {
    try {
      phase.value = await storyPhaseApi.get(props.slug)
      allStorylines.value = (await workflowApi.getStorylines(props.slug)) || []
      confluenceList.value = await confluenceApi.list(props.slug)
    } catch {
      message.error('故事线加载失败')
    }
  } finally {
    phaseLoading.value = false
    storylinesLoading.value = false
  }
}

watch(
  () => [props.slug, props.evolutionBundle, props.evolutionLoading] as const,
  () => { void loadData() },
  { immediate: true },
)

function selectStoryline(sl: StorylineDTO) {
  selectedStorylineId.value = sl.id
  emit('selectStoryline', {
    startChapter: sl.estimated_chapter_start,
    endChapter: sl.estimated_chapter_end,
  })
}

function getRoleColor(role?: string): 'success' | 'warning' | 'info' | 'default' {
  const map: Record<string, 'success' | 'warning' | 'info' | 'default'> = {
    main: 'success', sub: 'warning', dark: 'info',
    MAIN_PLOT: 'success', SUB_PLOT: 'warning', DARK_LINE: 'info',
  }
  return map[role || ''] ?? 'default'
}

function getRoleLabel(role?: string): string {
  const map: Record<string, string> = {
    main: '主线', sub: '支线', dark: '暗线',
    MAIN_PLOT: '主线', SUB_PLOT: '支线', DARK_LINE: '暗线',
  }
  return map[role || ''] || role || '未知'
}

function getStatusColor(status: string): 'success' | 'warning' | 'default' {
  const map: Record<string, 'success' | 'warning' | 'default'> = {
    ACTIVE: 'warning', active: 'warning', COMPLETED: 'success', completed: 'success',
  }
  return map[status] ?? 'default'
}

function getStatusLabel(status: string): string {
  const map: Record<string, string> = {
    ACTIVE: '进行中', active: '进行中', COMPLETED: '已完结', completed: '已完结',
  }
  return map[status] || status
}

const PHASE_STAGES = [
  { key: 'opening', label: '开局' },
  { key: 'development', label: '发展' },
  { key: 'convergence', label: '收敛' },
  { key: 'finale', label: '终局' },
]
const PHASE_ORDER = PHASE_STAGES.map(s => s.key)

function isPhasePast(key: string, current: string): boolean {
  return PHASE_ORDER.indexOf(key) < PHASE_ORDER.indexOf(current)
}
</script>

<style scoped>
.story-navigator {
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: var(--app-surface);
  border-right: 1px solid var(--plotpilot-split-border);
}
.phase-section {
  padding: 12px;
  border-bottom: 1px solid var(--plotpilot-split-border);
  flex-shrink: 0;
}
.storylines-section {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 12px;
}
.confluence-axis-section {
  padding: 10px 12px;
  border-top: 1px solid var(--plotpilot-split-border);
  flex-shrink: 0;
}
.section-header {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 10px;
}
.section-icon { font-size: 14px; }
.section-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--app-text-secondary);
  flex: 1;
}
.phase-visual {
  padding: 8px;
  background: var(--app-page-bg);
  border-radius: 6px;
}
.phase-track {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 4px;
}
.phase-stage {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
}
.stage-dot {
  width: 8px; height: 8px;
  border-radius: 50%;
  background: var(--n-border-color);
  transition: all 0.3s;
}
.phase-stage--past .stage-dot { background: var(--n-primary-color); }
.phase-stage--active .stage-dot {
  width: 12px; height: 12px;
  background: var(--n-primary-color);
  box-shadow: 0 0 0 4px rgba(24, 144, 255, 0.2);
}
.storylines-tree {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.storyline-item {
  padding: 8px 10px;
  border-radius: 6px;
  border: 1px solid var(--n-border-color);
  background: var(--app-surface);
  cursor: pointer;
  transition: all 0.2s;
}
.storyline-item--main { border-left: 3px solid var(--n-success-color); }
.storyline-item--child {
  margin-left: 8px;
  border-left: 3px solid var(--n-warning-color);
}
.storyline-item:hover {
  border-color: var(--n-primary-color-hover);
  box-shadow: 0 2px 8px rgba(0,0,0,0.06);
}
.storyline-item--active {
  border-color: var(--n-primary-color);
  background: rgba(24, 144, 255, 0.04);
}
.storyline-item__row {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}
.storyline-name {
  font-size: 13px;
  font-weight: 500;
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.child-indent {
  color: var(--app-text-muted);
  font-size: 12px;
  font-family: monospace;
}
.confluence-badge {
  font-size: 11px;
  color: var(--n-primary-color);
  background: rgba(24, 144, 255, 0.08);
  padding: 1px 5px;
  border-radius: 4px;
  cursor: default;
  flex-shrink: 0;
}
.add-child-btn {
  margin-left: 8px;
  padding: 4px 10px;
  opacity: 0.6;
  cursor: pointer;
}
.add-child-btn:hover { opacity: 1; }
.empty-state { padding: 24px; text-align: center; }
.confluence-axis {
  display: flex;
  align-items: center;
  gap: 12px;
  overflow-x: auto;
  padding: 4px 0;
  scrollbar-width: none;
}
.confluence-axis::-webkit-scrollbar { display: none; }
.confluence-marker {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
  cursor: pointer;
  flex-shrink: 0;
}
.marker-dot {
  width: 22px; height: 22px;
  border-radius: 50%;
  background: rgba(24, 144, 255, 0.12);
  border: 1px solid var(--n-primary-color);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  color: var(--n-primary-color);
}
.confluence-marker--reveal .marker-dot {
  background: rgba(250, 173, 20, 0.12);
  border-color: var(--n-warning-color);
  color: var(--n-warning-color);
}
.confluence-marker--resolved .marker-dot { opacity: 0.4; }
.marker-ch { font-size: 10px; color: var(--app-text-muted); }
.guards-list { display: flex; flex-direction: column; gap: 6px; width: 100%; }
.guard-row { display: flex; align-items: center; gap: 4px; }
</style>
