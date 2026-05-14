<template>
  <div class="storyline-panel">
    <header class="panel-header">
      <div class="header-main">
        <div class="title-row">
          <h3 class="panel-title">故事线管理</h3>
          <n-tag size="small" round :bordered="false">Storylines</n-tag>
        </div>
        <p class="panel-lead">
          管理小说的<strong>主线、支线与暗线</strong>，规划故事线的起止章节和关键里程碑。
        </p>
      </div>
      <n-space class="header-actions" :size="8" align="center" :wrap="false">
        <n-radio-group v-model:value="viewMode" size="small" class="view-switcher">
          <n-radio-button value="list">列表</n-radio-button>
          <n-radio-button value="graph">Git Graph</n-radio-button>
        </n-radio-group>
        <n-button
          class="panel-header-btn"
          size="small"
          type="primary"
          secondary
          @click="openCreate"
        >
          + 添加故事线
        </n-button>
        <n-button
          class="panel-header-btn"
          size="small"
          quaternary
          :loading="loading"
          :disabled="loading"
          @click="loadStorylines"
        >
          刷新
        </n-button>
      </n-space>
    </header>

    <!-- Git Graph 视图 -->
    <div v-if="viewMode === 'graph'" class="panel-graph">
      <StorylineGitGraph :slug="slug" :current-chapter="currentChapterNumber" />
    </div>

    <!-- 列表视图（折叠面板模式） -->
    <div v-else class="panel-content">
      <n-spin :show="loading">
        <n-empty
          v-if="storylines.length === 0"
          class="panel-empty"
          size="small"
          description="暂无故事线"
        >
          <template #icon>
            <span class="panel-empty-ico" aria-hidden="true">📖</span>
          </template>
          <template #extra>
            <n-text depth="3" style="font-size: 12px; text-align: center; max-width: 280px">
              点击右上角「添加故事线」规划主线/支线，或从宏观规划流程中生成。
            </n-text>
          </template>
        </n-empty>

        <n-collapse v-else :default-expanded-names="[mainPlotId]" accordion class="sl-collapse">
          <n-collapse-item
            v-for="storyline in storylines"
            :key="storyline.id"
            :name="storyline.id"
          >
            <template #header>
              <div class="collapse-header" @click.stop>
                <n-tag :type="getTypeColor(storyline.storyline_type)" size="small" round>
                  {{ getTypeLabel(storyline.storyline_type) }}
                </n-tag>
                <n-text class="collapse-title" strong>
                  {{ (storyline.name || '').trim() || `故事线 ${storyline.id.slice(0, 8)}` }}
                </n-text>
                <n-tag :type="getStatusColor(storyline.status)" size="small" round :bordered="false">
                  {{ getStatusLabel(storyline.status) }}
                </n-tag>
              </div>
            </template>

            <template #header-extra>
              <n-space :size="6" @click.stop>
                <n-button size="tiny" secondary @click="editStoryline(storyline)">编辑</n-button>
                <n-button size="tiny" type="error" secondary @click="deleteStoryline(storyline.id)">删除</n-button>
              </n-space>
            </template>

            <div class="collapse-body">
              <div class="info-row">
                <span class="info-label">章节范围</span>
                <span class="info-value">第 {{ storyline.estimated_chapter_start }} – {{ storyline.estimated_chapter_end }} 章</span>
              </div>
              <div class="info-row" v-if="storyline.description">
                <span class="info-label">描述</span>
                <span class="info-value desc">{{ storyline.description }}</span>
              </div>
              <div class="info-row" v-if="storyline.progress_summary">
                <span class="info-label">进度摘要</span>
                <span class="info-value">{{ storyline.progress_summary }}</span>
              </div>
              <div class="info-row" v-if="storyline.last_active_chapter">
                <span class="info-label">最后活跃</span>
                <span class="info-value">第 {{ storyline.last_active_chapter }} 章</span>
              </div>
              <div class="collapse-milestones" v-if="storyline.milestones?.length">
                <div class="ms-title">里程碑 ({{ storyline.milestones.length }})</div>
                <div class="ms-list">
                  <div v-for="(ms, mi) in storyline.milestones" :key="mi" class="ms-item">
                    <span class="ms-dot" />
                    <span class="ms-name">{{ ms.title }}</span>
                    <span class="ms-range">Ch.{{ ms.target_chapter_start }}–{{ ms.target_chapter_end }}</span>
                  </div>
                </div>
              </div>
            </div>
          </n-collapse-item>
        </n-collapse>
      </n-spin>
    </div>

    <!-- 创建/编辑故事线模态框 -->
    <n-modal v-model:show="showCreateModal" preset="card" :title="editingStoryline ? '编辑故事线' : '添加故事线'" style="width: 600px">
      <n-form ref="formRef" :model="formData" :rules="formRules" label-placement="left" label-width="120">
        <n-form-item label="故事线类型" path="storyline_type">
          <n-select
            v-model:value="formData.storyline_type"
            :options="typeOptions"
            placeholder="选择故事线类型"
          />
        </n-form-item>

        <n-form-item label="开始章节" path="estimated_chapter_start">
          <n-input-number
            v-model:value="formData.estimated_chapter_start"
            :min="1"
            placeholder="起始章节号"
            style="width: 100%"
          />
        </n-form-item>

        <n-form-item label="结束章节" path="estimated_chapter_end">
          <n-input-number
            v-model:value="formData.estimated_chapter_end"
            :min="1"
            placeholder="结束章节号"
            style="width: 100%"
          />
        </n-form-item>
      </n-form>

      <template #action>
        <n-space justify="end">
          <n-button @click="showCreateModal = false">取消</n-button>
          <n-button type="primary" :loading="saving" @click="handleSubmit">确定</n-button>
        </n-space>
      </template>
    </n-modal>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { useMessage, useDialog } from 'naive-ui'
import { workflowApi } from '../../api/workflow'
import type { StorylineDTO } from '../../api/workflow'
import { useWorkbenchRefreshStore } from '../../stores/workbenchRefreshStore'
import StorylineGitGraph from './StorylineGitGraph.vue'

interface Props {
  slug: string
  currentChapter?: number | null
}

const props = defineProps<Props>()
const message = useMessage()

/** 当前章节号（兼容 null/undefined） */
const currentChapterNumber = computed(() => props.currentChapter ?? undefined)
const dialog = useDialog()

const viewMode = ref<'list' | 'graph'>('list')
const loading = ref(false)
const saving = ref(false)
const storylines = ref<StorylineDTO[]>([])

// 自动寻找主线作为默认展开项
const mainPlotId = computed(() => {
  const main = storylines.value.find(s => s.storyline_type === 'main_plot')
  return main ? main.id : storylines.value[0]?.id || ''
})
const showCreateModal = ref(false)
const editingStoryline = ref<StorylineDTO | null>(null)

const formData = ref({
  storyline_type: 'main_plot',
  estimated_chapter_start: 1,
  estimated_chapter_end: 10
})

const formRules = {
  storyline_type: { required: true, message: '请选择故事线类型', trigger: 'change' },
  estimated_chapter_start: { required: true, type: 'number', message: '请输入开始章节', trigger: 'blur' },
  estimated_chapter_end: { required: true, type: 'number', message: '请输入结束章节', trigger: 'blur' }
}

const typeOptions = [
  { label: '主线', value: 'main_plot' },
  { label: '爱情线', value: 'romance' },
  { label: '复仇线', value: 'revenge' },
  { label: '悬疑线', value: 'mystery' },
  { label: '成长线', value: 'growth' },
  { label: '政治线', value: 'political' },
  { label: '冒险线', value: 'adventure' },
  { label: '家庭线', value: 'family' },
  { label: '友情线', value: 'friendship' }
]

const getTypeLabel = (type: string) => {
  const option = typeOptions.find(o => o.value === type)
  return option?.label || type
}

const getTypeColor = (type: string) => {
  const colors: Record<string, any> = {
    main_plot: 'primary',
    romance: 'error',
    revenge: 'warning',
    mystery: 'info',
    growth: 'success'
  }
  return colors[type] || 'default'
}

const getStatusLabel = (status: string) => {
  const labels: Record<string, string> = {
    active: '进行中',
    completed: '已完成',
    abandoned: '已废弃'
  }
  return labels[status] || status
}

const getStatusColor = (status: string) => {
  const colors: Record<string, any> = {
    active: 'success',
    completed: 'info',
    abandoned: 'default'
  }
  return colors[status] || 'default'
}

const loadStorylines = async () => {
  loading.value = true
  try {
    storylines.value = await workflowApi.getStorylines(props.slug)
  } catch (error: any) {
    message.error(error?.response?.data?.detail || '加载故事线失败')
  } finally {
    loading.value = false
  }
}

const openCreate = () => {
  editingStoryline.value = null
  formData.value = { storyline_type: 'main_plot', estimated_chapter_start: 1, estimated_chapter_end: 10 }
  showCreateModal.value = true
}

const handleSubmit = async () => {
  if (formData.value.estimated_chapter_end < formData.value.estimated_chapter_start) {
    message.error('结束章节必须大于等于开始章节')
    return
  }

  saving.value = true
  try {
    if (editingStoryline.value) {
      await workflowApi.updateStoryline(props.slug, editingStoryline.value.id, formData.value)
      message.success('故事线已更新')
    } else {
      await workflowApi.createStoryline(props.slug, formData.value)
      message.success('故事线创建成功')
    }
    showCreateModal.value = false
    await loadStorylines()
  } catch (error: any) {
    message.error(error?.response?.data?.detail || (editingStoryline.value ? '更新失败' : '创建失败'))
  } finally {
    saving.value = false
  }
}

const editStoryline = (storyline: StorylineDTO) => {
  editingStoryline.value = storyline
  formData.value = {
    storyline_type: storyline.storyline_type,
    estimated_chapter_start: storyline.estimated_chapter_start,
    estimated_chapter_end: storyline.estimated_chapter_end,
  }
  showCreateModal.value = true
}

const deleteStoryline = (id: string) => {
  dialog.warning({
    title: '确认删除',
    content: '删除后无法恢复，确定吗？',
    positiveText: '删除',
    negativeText: '取消',
    onPositiveClick: async () => {
      try {
        await workflowApi.deleteStoryline(props.slug, id)
        message.success('已删除')
        await loadStorylines()
      } catch (error: any) {
        message.error(error?.response?.data?.detail || '删除失败')
      }
    },
  })
}

watch(() => props.slug, (slug) => {
  if (slug) loadStorylines()
})

// 🔥 监听 deskTick：autopilot 写作/规划完成后刷新故事线列表
const refreshStore = useWorkbenchRefreshStore()
const { deskTick } = storeToRefs(refreshStore)
watch(deskTick, () => void loadStorylines())

onMounted(() => {
  loadStorylines()
})
</script>

<style scoped>
.storyline-panel {
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: var(--plotpilot-panel-muted);
}

.panel-header {
  padding: 12px 16px;
  border-bottom: 1px solid var(--plotpilot-split-border);
  background: var(--app-surface);
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 16px;
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
  color: var(--app-text-primary);
}

.panel-lead {
  margin: 0;
  font-size: 13px;
  line-height: 1.55;
  color: var(--app-text-secondary);
}

.header-actions {
  flex-shrink: 0;
  align-items: center;
}

.panel-header-btn {
  height: 28px !important;
  min-height: 28px !important;
  padding: 0 12px !important;
}

.panel-content {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
}

.panel-empty {
  padding: 12px 8px !important;
  min-height: auto !important;
}

.panel-empty-ico {
  font-size: 36px;
  line-height: 1;
  opacity: 0.9;
}

.storyline-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  width: 100%;
  flex-wrap: wrap;
}

.storyline-header-main {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 1;
  min-width: 0;
}

.storyline-title {
  font-size: 14px;
  margin: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.storyline-header-actions {
  flex-shrink: 0;
}

.view-switcher {
  flex-shrink: 0;
}

.view-switcher :deep(.n-radio-button) {
  --padding: 0 10px;
}

/* ==================== 折叠面板样式 ==================== */
.sl-collapse {
  padding: 4px 0;
}

.sl-collapse :deep(.n-collapse-item) {
  border-radius: 10px;
  margin-bottom: 8px;
  background: var(--app-surface);
  border: 1px solid var(--plotpilot-split-border, rgba(0,0,0,0.06));
  transition: box-shadow 0.2s ease, border-color 0.2s ease;
  overflow: hidden;
}

.sl-collapse :deep(.n-collapse-item:hover) {
  border-color: var(--color-brand-border);
  box-shadow: 0 6px 18px var(--color-brand-light);
}

.sl-collapse :deep(.n-collapse-item__header) {
  padding: 12px 14px !important;
  min-height: auto;
}

.sl-collapse :deep(.n-collapse-item__header-main) {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.collapse-header {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.collapse-title {
  font-size: 14px !important;
  margin: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--app-text-primary) !important;
}

.collapse-body {
  padding: 4px 14px 14px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.info-row {
  display: grid;
  grid-template-columns: 88px minmax(0, 1fr);
  align-items: start;
  column-gap: 12px;
  row-gap: 4px;
  padding: 6px 0;
}

@media (max-width: 640px) {
  .info-row {
    grid-template-columns: 1fr;
  }

  .info-value:not(.desc) {
    text-align: left;
  }
}

.info-label {
  font-size: 12px;
  font-weight: 600;
  color: var(--app-text-secondary);
  padding-top: 2px;
}

.info-value {
  font-size: 13px;
  font-weight: 500;
  color: var(--app-text-primary);
  text-align: right;
  line-height: 1.55;
}

.info-value.desc {
  text-align: left;
  font-size: 13px;
  font-weight: 400;
  line-height: 1.65;
  white-space: pre-wrap;
  word-break: break-word;
}

/* 里程碑 */
.collapse-milestones {
  margin-top: 6px;
  padding-top: 8px;
  border-top: 1px solid var(--plotpilot-split-border, rgba(0,0,0,0.06));
}

.ms-title {
  font-size: 12px;
  font-weight: 600;
  color: var(--app-text-secondary);
  margin-bottom: 5px;
}

.ms-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.ms-item {
  display: flex;
  align-items: center;
  gap: 7px;
  font-size: 11.5px;
}

.ms-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--color-brand);
  flex-shrink: 0;
}

.ms-name {
  font-weight: 500;
  font-size: 12px;
  color: var(--app-text-primary);
  flex: 1;
}

.ms-range {
  font-size: 11px;
  color: var(--app-text-muted);
  font-family: var(--font-mono, monospace);
  flex-shrink: 0;
}

.panel-graph {
  flex: 1;
  min-height: 0;
  overflow: hidden;
}
</style>
