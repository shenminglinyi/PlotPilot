<template>
  <div class="checkpoint-timeline">
    <div class="timeline-header">
      <n-text strong style="font-size: 14px">版本时间线</n-text>
      <n-space :size="8">
        <n-button size="small" type="primary" :loading="creating" @click="handleCreate">
          ＋ 创建节点
        </n-button>
        <n-button size="small" :loading="loading" @click="load">刷新</n-button>
      </n-space>
    </div>

    <n-alert v-if="loadError" type="error" :title="loadError" closable @close="loadError = ''" class="cp-alert" />

    <!-- HEAD 状态 -->
    <n-card v-if="headState" size="small" :bordered="true" class="head-card">
      <template #header>
        <span class="card-title">⭐ 当前 HEAD</span>
      </template>
      <n-space vertical :size="6">
        <div class="info-row">
          <n-text depth="3">触发类型</n-text>
          <n-tag size="small" round>{{ triggerLabel(headState.trigger_type) }}</n-tag>
        </div>
        <div class="info-row">
          <n-text depth="3">原因</n-text>
          <n-text>{{ headState.trigger_reason || '—' }}</n-text>
        </div>
      </n-space>
    </n-card>

    <!-- 时间线列表 -->
    <n-spin :show="loading">
      <div v-if="checkpoints.length > 0" class="timeline-list">
        <div
          v-for="cp in checkpoints"
          :key="cp.id"
          class="timeline-item"
          :class="{ 'timeline-item--head': cp.is_head }"
        >
          <div class="timeline-dot" :class="`timeline-dot--${cp.trigger_type}`" />
          <div class="timeline-content">
            <div class="timeline-meta">
              <n-tag :type="cp.is_head ? 'success' : 'default'" size="tiny" round>
                {{ cp.is_head ? 'HEAD' : triggerLabel(cp.trigger_type) }}
              </n-tag>
              <n-text depth="3" style="font-size: 11px">
                {{ cp.chapter_number ? `第${cp.chapter_number}章` : '' }}
              </n-text>
            </div>
            <n-text style="font-size: 12px">{{ cp.trigger_reason || '—' }}</n-text>
            <div class="timeline-actions">
              <n-text depth="3" style="font-size: 10px">{{ formatTime(cp.created_at) }}</n-text>
              <n-button
                v-if="!cp.is_head"
                size="tiny"
                type="error"
                quaternary
                @click="handleRollback(cp.id)"
                :loading="rollingBack === cp.id"
              >
                回滚
              </n-button>
            </div>
          </div>
        </div>
      </div>

      <n-empty v-else-if="!loading" description="暂无 Checkpoint，章节完成或手动创建后将出现在此" size="small" style="margin-top: 24px" />
    </n-spin>

    <!-- 平行宇宙 -->
    <n-card v-if="branches.length > 0" size="small" :bordered="true" class="branch-card">
      <template #header>
        <span class="card-title">🔀 平行宇宙 ({{ branches.length }})</span>
      </template>
      <n-space vertical :size="8">
        <div v-for="(b, i) in branches" :key="i" class="branch-item">
          <n-text depth="3" style="font-size: 11px">分支点: {{ b.reason || b.branch_point_id.slice(0, 8) }}</n-text>
          <n-text depth="3" style="font-size: 11px">{{ b.children.length }} 条分支</n-text>
        </div>
      </n-space>
    </n-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useMessage } from 'naive-ui'
import {
  checkpointApi,
  type CheckpointDTO,
  type BranchDTO,
  type HeadStateResponse,
} from '@/api/engineCore'

const props = defineProps<{ slug: string }>()
const message = useMessage()

const loading = ref(false)
const loadError = ref('')
const creating = ref(false)
const rollingBack = ref<string | null>(null)

const checkpoints = ref<CheckpointDTO[]>([])
const branches = ref<BranchDTO[]>([])
const headState = ref<HeadStateResponse['state'] | null>(null)

const TRIGGER_LABELS: Record<string, string> = {
  CHAPTER: '章节',
  ACT: '幕切换',
  MILESTONE: '里程碑',
  MANUAL: '手动',
}

function triggerLabel(type: string): string {
  return TRIGGER_LABELS[type] || type
}

function formatTime(t: string): string {
  if (!t) return ''
  try {
    return new Date(t).toLocaleString('zh-CN', {
      month: 'numeric',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    })
  } catch {
    return t
  }
}

async function load() {
  if (!props.slug) return
  loading.value = true
  loadError.value = ''
  try {
    const [listRes, branchRes, headRes] = await Promise.allSettled([
      checkpointApi.list(props.slug),
      checkpointApi.listBranches(props.slug),
      checkpointApi.getHead(props.slug),
    ])
    if (listRes.status === 'fulfilled') {
      checkpoints.value = listRes.value.checkpoints
    }
    if (branchRes.status === 'fulfilled') {
      branches.value = branchRes.value.branches
    }
    if (headRes.status === 'fulfilled') {
      headState.value = headRes.value.state
    }
  } catch {
    loadError.value = '加载 Checkpoint 失败'
  } finally {
    loading.value = false
  }
}

async function handleCreate() {
  creating.value = true
  try {
    const res = await checkpointApi.create(props.slug, { reason: '手动创建' })
    message.success(res.message || 'Checkpoint 已创建')
    await load()
  } catch {
    message.error('创建失败')
  } finally {
    creating.value = false
  }
}

async function handleRollback(cpId: string) {
  rollingBack.value = cpId
  try {
    const res = await checkpointApi.rollback(props.slug, cpId)
    message.success(res.message || '已回滚')
    await load()
  } catch {
    message.error('回滚失败')
  } finally {
    rollingBack.value = null
  }
}

onMounted(load)
</script>

<style scoped>
.checkpoint-timeline {
  height: 100%;
  min-height: 0;
  overflow-y: auto;
  padding: 12px 16px 20px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.timeline-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.cp-alert {
  margin: 0;
}

.head-card,
.branch-card {
  transition: all 0.2s ease;
}

.head-card:hover,
.branch-card:hover {
  border-color: var(--n-primary-color-hover);
}

.card-title {
  font-size: 13px;
  font-weight: 600;
}

.info-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
}

.timeline-list {
  display: flex;
  flex-direction: column;
  gap: 0;
}

.timeline-item {
  display: flex;
  gap: 10px;
  padding: 8px 0;
  border-left: 2px solid var(--n-border-color);
  padding-left: 14px;
  position: relative;
}

.timeline-item--head {
  border-left-color: #18a058;
}

.timeline-dot {
  position: absolute;
  left: -6px;
  top: 12px;
  width: 10px;
  height: 10px;
  border-radius: 50%;
  border: 2px solid var(--n-border-color);
  background: var(--n-color-modal);
}

.timeline-dot--CHAPTER {
  background: #2080f0;
  border-color: #2080f0;
}

.timeline-dot--ACT {
  background: #f59e0b;
  border-color: #f59e0b;
}

.timeline-dot--MILESTONE {
  background: #a855f7;
  border-color: #a855f7;
}

.timeline-dot--MANUAL {
  background: #10b981;
  border-color: #10b981;
}

.timeline-content {
  display: flex;
  flex-direction: column;
  gap: 4px;
  flex: 1;
}

.timeline-meta {
  display: flex;
  align-items: center;
  gap: 6px;
}

.timeline-actions {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 6px;
}

.branch-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
</style>
