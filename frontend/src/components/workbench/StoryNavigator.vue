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
                'phase-stage--past': PHASE_ORDER.indexOf(s.key) < PHASE_ORDER.indexOf(phase.phase),
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

    <!-- 故事线列表 -->
    <div class="storylines-section">
      <div class="section-header">
        <span class="section-icon">📖</span>
        <span class="section-title">故事线</span>
        <n-button size="tiny" quaternary @click="showAddModal = true">+</n-button>
      </div>

      <n-spin :show="storylinesLoading">
        <div v-if="storylines.length === 0" class="empty-state">
          <n-text depth="3" style="font-size: 12px">暂无故事线</n-text>
          <n-text depth="3" style="font-size: 11px; display: block; margin-top: 6px; line-height: 1.5">
            点击「+」手动创建，或在创建向导 / 宏观规划完成后会自动出现。
          </n-text>
        </div>

        <div v-else class="storylines-list">
          <div
            v-for="sl in storylines"
            :key="sl.id"
            class="storyline-item"
            :class="{ 'storyline-item--active': selectedStorylineId === sl.id }"
            @click="selectStoryline(sl)"
          >
            <n-tag :type="getTypeColor(sl.storyline_type)" size="small" round>
              {{ getTypeLabel(sl.storyline_type) }}
            </n-tag>
            <div class="storyline-info">
              <n-text class="storyline-name">{{ sl.name || `故事线 ${sl.id.slice(0, 8)}` }}</n-text>
              <n-text depth="3" style="font-size: 11px">
                第 {{ sl.estimated_chapter_start }} - {{ sl.estimated_chapter_end }} 章
              </n-text>
            </div>
            <n-tag :type="getStatusColor(sl.status)" size="tiny" round>
              {{ getStatusLabel(sl.status) }}
            </n-tag>
          </div>
        </div>
      </n-spin>
    </div>

    <n-modal
      v-model:show="showAddModal"
      preset="card"
      title="新建故事线"
      style="width: 420px"
      :mask-closable="false"
      @after-leave="resetAddForm"
    >
      <n-form label-placement="left" label-width="72" size="small">
        <n-form-item label="类型">
          <n-select
            v-model:value="addForm.storyline_type"
            :options="storylineTypeOptions"
          />
        </n-form-item>
        <n-form-item label="名称">
          <n-input v-model:value="addForm.name" placeholder="可选，便于识别" clearable />
        </n-form-item>
        <n-form-item label="说明">
          <n-input
            v-model:value="addForm.description"
            type="textarea"
            placeholder="可选"
            :autosize="{ minRows: 2, maxRows: 5 }"
          />
        </n-form-item>
        <n-form-item label="章节起">
          <n-input-number v-model:value="addForm.estimated_chapter_start" :min="1" :step="1" style="width: 100%" />
        </n-form-item>
        <n-form-item label="章节止">
          <n-input-number v-model:value="addForm.estimated_chapter_end" :min="1" :step="1" style="width: 100%" />
        </n-form-item>
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
import { ref, onMounted, watch } from 'vue'
import { useMessage } from 'naive-ui'
import { storyPhaseApi, type StoryPhaseDTO } from '@/api/engineCore'
import { workflowApi, type StorylineDTO } from '@/api/workflow'
import { narrativeEngineApi } from '@/api/narrativeEngine'
import { useWorkbenchRefreshStore } from '@/stores/workbenchRefreshStore'
import { useWorkbenchDeskTickReload } from '@/composables/useWorkbenchNarrativeSync'

interface Props {
  slug: string
  currentChapter: number | null
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
const storylines = ref<StorylineDTO[]>([])
const selectedStorylineId = ref<string | null>(null)

const showAddModal = ref(false)
const addSubmitting = ref(false)

const storylineTypeOptions = [
  { label: '主线', value: 'MAIN_PLOT' },
  { label: '支线', value: 'SUB_PLOT' },
  { label: '暗线', value: 'DARK_LINE' },
]

const addForm = ref({
  storyline_type: 'SUB_PLOT',
  name: '',
  description: '',
  estimated_chapter_start: 1,
  estimated_chapter_end: 10,
})

function resetAddForm() {
  addForm.value = {
    storyline_type: 'SUB_PLOT',
    name: '',
    description: '',
    estimated_chapter_start: 1,
    estimated_chapter_end: 10,
  }
}

watch(showAddModal, (open) => {
  if (!open) return
  const ch = props.currentChapter != null && props.currentChapter > 0 ? props.currentChapter : 1
  addForm.value = {
    storyline_type: 'SUB_PLOT',
    name: '',
    description: '',
    estimated_chapter_start: ch,
    estimated_chapter_end: Math.max(ch, ch + 9),
  }
})

async function submitAddStoryline() {
  const f = addForm.value
  const start = f.estimated_chapter_start
  const end = f.estimated_chapter_end
  if (start == null || end == null || start < 1 || end < 1) {
    message.warning('请填写有效的章节范围')
    return
  }
  if (end < start) {
    message.warning('结束章节不能小于起始章节')
    return
  }
  addSubmitting.value = true
  try {
    await workflowApi.createStoryline(props.slug, {
      storyline_type: f.storyline_type,
      estimated_chapter_start: start,
      estimated_chapter_end: end,
      name: f.name?.trim() || undefined,
      description: f.description?.trim() || undefined,
    })
    message.success('故事线已创建')
    showAddModal.value = false
    await loadPhaseAndStorylines()
    refreshStore.bumpDesk()
  } catch (err: any) {
    const detail = err?.response?.data?.detail
    message.error(typeof detail === 'string' ? detail : err?.message || '创建失败')
  } finally {
    addSubmitting.value = false
  }
}

// 4阶段模型
const PHASE_STAGES = [
  { key: 'opening', label: '开局' },
  { key: 'development', label: '发展' },
  { key: 'convergence', label: '收敛' },
  { key: 'finale', label: '终局' },
]

const PHASE_ORDER = PHASE_STAGES.map(s => s.key)

/** 优先叙事引擎聚合 GET；失败时降级为 story-phase + storylines 分拆接口 */
async function loadPhaseAndStorylines() {
  phaseLoading.value = true
  storylinesLoading.value = true
  try {
    const bundle = await narrativeEngineApi.getStoryEvolution(props.slug)
    phase.value = bundle.life_cycle
    storylines.value = bundle.plot_spine.storylines || []
  } catch (error) {
    console.error('叙事引擎聚合加载失败，降级为分拆 API:', error)
    try {
      phase.value = await storyPhaseApi.get(props.slug)
    } catch (e) {
      console.error('加载故事阶段失败:', e)
    }
    try {
      const data = await workflowApi.getStorylines(props.slug)
      storylines.value = data || []
    } catch (e) {
      console.error('加载故事线失败:', e)
    }
  } finally {
    phaseLoading.value = false
    storylinesLoading.value = false
  }
}

// 选择故事线
function selectStoryline(sl: StorylineDTO) {
  selectedStorylineId.value = sl.id
  emit('selectStoryline', {
    startChapter: sl.estimated_chapter_start,
    endChapter: sl.estimated_chapter_end,
  })
}

// 类型颜色映射
function getTypeColor(type: string): 'success' | 'warning' | 'info' | 'default' {
  const map: Record<string, 'success' | 'warning' | 'info' | 'default'> = {
    MAIN_PLOT: 'success',
    SUB_PLOT: 'warning',
    DARK_LINE: 'info',
  }
  return map[type] || 'default'
}

function getTypeLabel(type: string): string {
  const map: Record<string, string> = {
    MAIN_PLOT: '主线',
    SUB_PLOT: '支线',
    DARK_LINE: '暗线',
  }
  return map[type] || type
}

function getStatusColor(status: string): 'success' | 'warning' | 'default' {
  const map: Record<string, 'success' | 'warning' | 'default'> = {
    ACTIVE: 'warning',
    COMPLETED: 'success',
  }
  return map[status] || 'default'
}

function getStatusLabel(status: string): string {
  const map: Record<string, string> = {
    ACTIVE: '进行中',
    COMPLETED: '已完结',
  }
  return map[status] || status
}

onMounted(() => {
  loadPhaseAndStorylines()
})

useWorkbenchDeskTickReload(() => {
  void loadPhaseAndStorylines()
})
</script>

<style scoped>
.story-navigator {
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: var(--app-surface);
  border-right: 1px solid var(--aitext-split-border);
}

.phase-section {
  padding: 12px;
  border-bottom: 1px solid var(--aitext-split-border);
}

.section-header {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 10px;
}

.section-icon {
  font-size: 14px;
}

.section-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--app-text-secondary);
}

.phase-visual {
  padding: 8px;
  background: var(--app-page-bg);
  border-radius: 6px;
}

.phase-track {
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  align-items: flex-start;
  gap: 8px 4px;
}

.phase-stage {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
}

.stage-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--n-border-color);
  transition: all 0.3s;
}

.phase-stage--past .stage-dot {
  background: var(--n-primary-color);
}

.phase-stage--active .stage-dot {
  width: 12px;
  height: 12px;
  background: var(--n-primary-color);
  box-shadow: 0 0 0 4px rgba(24, 144, 255, 0.2);
}

.storylines-section {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 12px;
}

.empty-state {
  padding: 24px;
  text-align: center;
}

.storylines-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.storyline-item {
  padding: 10px;
  border-radius: 6px;
  border: 1px solid var(--n-border-color);
  background: var(--app-surface);
  cursor: pointer;
  transition: all 0.2s;
}

.storyline-item:hover {
  border-color: var(--n-primary-color-hover);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
}

.storyline-item--active {
  border-color: var(--n-primary-color);
  background: rgba(24, 144, 255, 0.04);
}

.storyline-info {
  margin-top: 6px;
}

.storyline-name {
  font-size: 13px;
  font-weight: 500;
  display: block;
  margin-bottom: 2px;
}
</style>
