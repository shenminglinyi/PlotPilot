<template>
  <div class="ccm">
    <div class="ccm-header">
      <div class="ccm-title-block">
        <span class="ccm-title">本章角色锁</span>
        <span v-if="chapterNumber" class="ccm-chapter-tag">第 {{ chapterNumber }} 章</span>
      </div>
      <div class="ccm-actions">
        <n-button size="tiny" quaternary :loading="scheduling" @click="runSchedule">
          刷新内核
        </n-button>
        <n-button
          size="tiny"
          type="primary"
          secondary
          :disabled="suggestions.length === 0"
          :loading="applying"
          @click="applyAll"
        >
          落库对齐
        </n-button>
      </div>
    </div>

    <n-spin :show="scheduling" size="small" class="ccm-spin">
      <div class="ccm-summary">
        <div class="ccm-stat ccm-stat--major">
          <span class="ccm-stat-num">{{ tierCounts.major }}</span>
          <span class="ccm-stat-label">T0 锚定</span>
        </div>
        <div class="ccm-stat ccm-stat--normal">
          <span class="ccm-stat-num">{{ tierCounts.normal }}</span>
          <span class="ccm-stat-label">T1 参与</span>
        </div>
        <div class="ccm-stat ccm-stat--minor">
          <span class="ccm-stat-num">{{ tierCounts.minor }}</span>
          <span class="ccm-stat-label">T2 过场</span>
        </div>
        <div class="ccm-stat ccm-stat--risk">
          <span class="ccm-stat-num">{{ reviewCount }}</span>
          <span class="ccm-stat-label">需校准</span>
        </div>
      </div>

      <div v-if="suggestions.length > 0" class="ccm-section">
        <div class="ccm-section-head">
          <span class="ccm-section-label">选角合同</span>
          <span class="ccm-section-note">后端 Character Narrative Kernel 自动生成</span>
        </div>
        <div class="ccm-list">
          <div
            v-for="item in suggestions"
            :key="item.character_id"
            class="ccm-item"
            :class="`ccm-item--${item.importance}`"
          >
            <div class="ccm-avatar">{{ item.name.slice(0, 1) }}</div>
            <div class="ccm-info">
              <div class="ccm-name-row">
                <span class="ccm-name">{{ item.name }}</span>
                <span class="ccm-imp-tag" :class="`ccm-imp-tag--${item.importance}`">
                  {{ slotTierLabel(item.importance) }}
                </span>
                <span v-if="item.needs_review" class="ccm-risk-tag">校准</span>
              </div>
              <span class="ccm-function">
                {{ sceneFunctionLabel(item.scene_function) }}
              </span>
            </div>
          </div>
        </div>
      </div>

      <div v-if="newCharacterCandidates.length > 0" class="ccm-section ccm-section--candidates">
        <div class="ccm-section-head">
          <span class="ccm-section-label">新角色准入</span>
          <span class="ccm-section-note">默认自动采纳，只有高风险需要看</span>
        </div>
        <div class="ccm-candidates">
          <div
            v-for="candidate in newCharacterCandidates"
            :key="String(candidate.name)"
            class="ccm-candidate"
            :class="candidateClass(candidate)"
          >
            <div class="ccm-candidate-main">
              <span class="ccm-candidate-name">{{ candidate.name }}</span>
              <span class="ccm-candidate-policy">
                {{ recommendationLabel(candidate.recommendation) }}
              </span>
            </div>
            <p class="ccm-candidate-reason">{{ candidate.reason || '内核已完成准入判断' }}</p>
          </div>
        </div>
      </div>

      <div v-if="generatedContext || schedulingLog.length > 0" class="ccm-section ccm-section--context">
        <div class="ccm-section-head">
          <span class="ccm-section-label">上下文锁预览</span>
          <span class="ccm-section-note">随本章角色合同同步生成</span>
        </div>
        <pre v-if="generatedContext" class="ccm-context">{{ generatedContext }}</pre>
        <div v-if="schedulingLog.length > 0" class="ccm-log">
          <span v-for="line in schedulingLog" :key="line">{{ line }}</span>
        </div>
      </div>

      <n-empty
        v-if="!scheduling && suggestions.length === 0 && newCharacterCandidates.length === 0"
        size="small"
        description="暂无本章角色合同"
        class="ccm-empty"
      />
    </n-spin>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useMessage } from 'naive-ui'
import { castApi, type ScheduledCharacterItem } from '@/api/cast'

interface Props {
  slug: string
  chapterNumber?: number | null
  outline?: string
}

type NewCharacterCandidate = {
  name?: unknown
  recommendation?: unknown
  reason?: unknown
  confidence?: unknown
}

const props = withDefaults(defineProps<Props>(), {
  chapterNumber: null,
  outline: '',
})
const message = useMessage()

const scheduling = ref(false)
const applying = ref(false)
const suggestions = ref<ScheduledCharacterItem[]>([])
const newCharacterCandidates = ref<NewCharacterCandidate[]>([])
const generatedContext = ref('')
const schedulingLog = ref<string[]>([])

const tierCounts = computed(() => ({
  major: suggestions.value.filter(s => s.importance === 'major').length,
  normal: suggestions.value.filter(s => s.importance === 'normal').length,
  minor: suggestions.value.filter(s => s.importance === 'minor').length,
}))

const reviewCount = computed(() => suggestions.value.filter(s => s.needs_review).length)

function slotTierLabel(importance: ScheduledCharacterItem['importance']): string {
  if (importance === 'major') return 'T0'
  if (importance === 'normal') return 'T1'
  return 'T2'
}

function sceneFunctionLabel(value?: string): string {
  const map: Record<string, string> = {
    pov: '视角位',
    conflict: '冲突位',
    informant: '信息位',
    mirror: '镜像位',
    foreshadow_carrier: '伏笔位',
    support: '支撑位',
    explicit_scene_cast: '明确出场',
    walk_on: '过场人物',
  }
  return map[String(value || '')] ?? '支撑位'
}

function recommendationLabel(value: unknown): string {
  const raw = String(value || '')
  if (raw === 'create_bible_character') return '建档'
  if (raw === 'ephemeral') return '本章路人'
  if (raw === 'ignore') return '忽略'
  return '无动作'
}

function candidateClass(candidate: NewCharacterCandidate): string {
  const raw = String(candidate.recommendation || '')
  if (raw === 'create_bible_character') return 'ccm-candidate--create'
  if (raw === 'ephemeral') return 'ccm-candidate--ephemeral'
  return 'ccm-candidate--ignore'
}

async function runSchedule() {
  if (!props.slug || !props.chapterNumber) return
  scheduling.value = true
  try {
    const res = await castApi.analyzeOutline(
      props.slug,
      props.chapterNumber,
      props.outline ?? '',
    )
    suggestions.value = res.cast ?? []
    newCharacterCandidates.value = (res.new_character_candidates ?? []) as NewCharacterCandidate[]
    generatedContext.value = res.generated_context ?? ''
    schedulingLog.value = res.scheduling_log ?? []
  } catch (err: unknown) {
    message.error(err instanceof Error ? err.message : '角色内核调度失败')
    suggestions.value = []
    newCharacterCandidates.value = []
    generatedContext.value = ''
    schedulingLog.value = []
  } finally {
    scheduling.value = false
  }
}

async function applyAll() {
  if (!props.slug || !props.chapterNumber) return
  applying.value = true
  try {
    const res = await castApi.scheduleAndPersist(props.slug, {
      chapter_number: props.chapterNumber,
      outline: props.outline ?? '',
      mode: 'apply',
    })
    suggestions.value = res.cast ?? []
    newCharacterCandidates.value = (res.new_character_candidates ?? []) as NewCharacterCandidate[]
    generatedContext.value = res.generated_context ?? ''
    schedulingLog.value = res.scheduling_log ?? []
    message.success('角色合同已由内核写入')
  } catch (err: unknown) {
    message.error(err instanceof Error ? err.message : '角色合同写入失败')
  } finally {
    applying.value = false
  }
}

watch(
  () => [props.slug, props.chapterNumber, props.outline],
  () => { void runSchedule() },
  { immediate: true },
)
</script>

<style scoped>
.ccm {
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background:
    linear-gradient(180deg, var(--app-surface-elevated, var(--app-surface)) 0%, var(--app-surface) 100%);
  border-bottom: 1px solid var(--plotpilot-split-border);
}

.ccm-header {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 10px 12px;
  border-bottom: 1px solid var(--plotpilot-split-border);
}

.ccm-title-block {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.ccm-title {
  font-size: 13px;
  font-weight: 800;
  color: var(--app-text-primary);
}

.ccm-chapter-tag {
  font-size: 11px;
  padding: 2px 7px;
  border-radius: 999px;
  background: var(--color-brand-light, rgba(37, 99, 235, 0.1));
  color: var(--color-brand, #2563eb);
  font-weight: 700;
}

.ccm-actions {
  display: flex;
  gap: 6px;
  flex-shrink: 0;
}

.ccm-spin {
  flex: 1;
  min-height: 0;
  overflow: hidden;
}

.ccm-spin :deep(.n-spin-content) {
  height: 100%;
  min-height: 0;
  overflow-y: auto;
}

.ccm-summary {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 8px;
  padding: 10px 12px;
}

.ccm-stat {
  min-width: 0;
  padding: 8px;
  border-radius: 8px;
  border: 1px solid var(--app-border);
  background: var(--app-surface);
}

.ccm-stat-num {
  display: block;
  font-size: 18px;
  line-height: 1;
  font-weight: 800;
  color: var(--app-text-primary);
}

.ccm-stat-label {
  display: block;
  margin-top: 5px;
  font-size: 10px;
  color: var(--app-text-muted);
  white-space: nowrap;
}

.ccm-stat--major { border-top: 2px solid var(--color-brand, #2563eb); }
.ccm-stat--normal { border-top: 2px solid var(--color-warning, #f59e0b); }
.ccm-stat--minor { border-top: 2px solid var(--app-border); }
.ccm-stat--risk { border-top: 2px solid var(--color-danger, #ef4444); }

.ccm-section {
  padding: 0 12px 10px;
}

.ccm-section-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 6px;
}

.ccm-section-label {
  font-size: 12px;
  font-weight: 800;
  color: var(--app-text-primary);
}

.ccm-section-note {
  font-size: 10px;
  color: var(--app-text-muted);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.ccm-list,
.ccm-candidates {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.ccm-item {
  display: flex;
  align-items: center;
  gap: 9px;
  padding: 8px 10px;
  border-radius: 8px;
  border: 1px solid var(--app-border);
  background: var(--app-surface);
  border-left-width: 3px;
}

.ccm-item--major { border-left-color: var(--color-brand, #2563eb); }
.ccm-item--normal { border-left-color: var(--color-warning, #f59e0b); }
.ccm-item--minor { border-left-color: var(--app-border); }

.ccm-avatar {
  flex-shrink: 0;
  width: 30px;
  height: 30px;
  border-radius: 8px;
  background: var(--app-border);
  color: var(--app-text-primary);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 13px;
  font-weight: 800;
}

.ccm-item--major .ccm-avatar {
  background: var(--color-brand-light, rgba(37, 99, 235, 0.12));
  color: var(--color-brand, #2563eb);
}

.ccm-item--normal .ccm-avatar {
  background: var(--color-warning-dim, rgba(245, 158, 11, 0.12));
  color: var(--color-warning, #f59e0b);
}

.ccm-info {
  flex: 1;
  min-width: 0;
}

.ccm-name-row {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
}

.ccm-name {
  font-size: 13px;
  font-weight: 700;
  color: var(--app-text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.ccm-function {
  display: block;
  margin-top: 3px;
  font-size: 11px;
  color: var(--app-text-muted);
}

.ccm-imp-tag,
.ccm-risk-tag,
.ccm-candidate-policy {
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  height: 18px;
  padding: 0 6px;
  border-radius: 5px;
  font-size: 10px;
  font-weight: 800;
}

.ccm-imp-tag--major {
  background: var(--color-brand-light, rgba(37, 99, 235, 0.1));
  color: var(--color-brand, #2563eb);
}

.ccm-imp-tag--normal {
  background: var(--color-warning-dim, rgba(245, 158, 11, 0.1));
  color: var(--color-warning, #f59e0b);
}

.ccm-imp-tag--minor {
  background: var(--app-border);
  color: var(--app-text-muted);
}

.ccm-risk-tag {
  background: var(--color-danger-dim, rgba(239, 68, 68, 0.1));
  color: var(--color-danger, #ef4444);
}

.ccm-candidate {
  padding: 8px 10px;
  border-radius: 8px;
  border: 1px solid var(--app-border);
  background: var(--app-surface);
}

.ccm-candidate--create {
  border-color: var(--color-brand-light, rgba(37, 99, 235, 0.22));
}

.ccm-candidate--ephemeral {
  border-color: var(--color-warning-dim, rgba(245, 158, 11, 0.22));
}

.ccm-candidate-main {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.ccm-candidate-name {
  font-size: 12px;
  font-weight: 800;
  color: var(--app-text-primary);
}

.ccm-candidate-policy {
  background: var(--app-border);
  color: var(--app-text-muted);
}

.ccm-candidate--create .ccm-candidate-policy {
  background: var(--color-brand-light, rgba(37, 99, 235, 0.1));
  color: var(--color-brand, #2563eb);
}

.ccm-candidate--ephemeral .ccm-candidate-policy {
  background: var(--color-warning-dim, rgba(245, 158, 11, 0.1));
  color: var(--color-warning, #f59e0b);
}

.ccm-candidate-reason {
  margin: 5px 0 0;
  font-size: 11px;
  line-height: 1.5;
  color: var(--app-text-muted);
}

.ccm-section--context {
  padding-bottom: 12px;
}

.ccm-section--context .ccm-context {
  border: 1px solid var(--app-border);
  border-radius: 8px;
  background: var(--app-surface);
}

.ccm-context {
  margin: 0;
  max-height: 180px;
  overflow: auto;
  white-space: pre-wrap;
  word-break: break-word;
  padding: 8px 10px;
  font-size: 11px;
  line-height: 1.55;
  color: var(--app-text-secondary);
}

.ccm-log {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
  padding-top: 8px;
}

.ccm-log span {
  font-size: 10px;
  padding: 2px 6px;
  border-radius: 999px;
  background: var(--app-border);
  color: var(--app-text-muted);
}

.ccm-empty {
  margin-top: 16px;
  padding: 0 16px 18px;
}
</style>
