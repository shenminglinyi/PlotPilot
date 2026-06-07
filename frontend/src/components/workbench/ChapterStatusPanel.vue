<template>
  <div class="chapter-status-panel">
    <n-empty v-if="!chapter" description="请从左侧选择一个章节" style="margin-top: 48px" />

    <n-space v-else vertical :size="12" style="width: 100%; padding: 8px 4px">
      <!-- 章节基本信息 -->
      <n-card size="small" :bordered="true" class="status-card">
        <div class="chapter-header">
          <div class="chapter-title-row">
            <n-text class="chapter-number">第 {{ chapter.number }} 章</n-text>
            <n-text class="chapter-title">{{ chapter.title || '未命名' }}</n-text>
          </div>
          <div class="chapter-meta">
            <n-tag :type="chapter.word_count > 0 ? 'success' : 'default'" size="small" round>
              {{ chapter.word_count > 0 ? '已收稿' : '未收稿' }}
            </n-tag>
            <n-text depth="3" class="word-count">{{ chapter.word_count ?? 0 }} 字</n-text>
          </div>
        </div>
      </n-card>

      <n-alert v-if="readOnly" type="warning" :show-icon="true" size="small">
        全托管执行中，辅助撰稿区仅可阅读
      </n-alert>

      <!-- 正文结构 -->
      <n-spin :show="metaLoading">
        <n-card v-if="slug" size="small" :bordered="true" class="status-card">
          <template #header>
            <span class="card-title">📊 正文结构</span>
          </template>
          <n-empty v-if="!chapterStructure && !metaLoading" description="暂无结构分析" size="small" />
          <div v-else-if="chapterStructure" class="structure-grid">
            <div class="structure-item">
              <n-text depth="3">分段</n-text>
              <n-text class="structure-value">{{ chapterStructure.paragraph_count ?? '—' }}</n-text>
            </div>
            <div class="structure-item">
              <n-text depth="3">场景</n-text>
              <n-text class="structure-value">{{ chapterStructure.scene_count ?? '—' }}</n-text>
            </div>
            <div class="structure-item">
              <n-text depth="3">对白</n-text>
              <n-text class="structure-value">
                {{ chapterStructure.dialogue_ratio != null ? `${Math.round(chapterStructure.dialogue_ratio * 100)}%` : '—' }}
              </n-text>
            </div>
            <div class="structure-item">
              <n-text depth="3">节奏</n-text>
              <n-tag size="tiny" round>{{ pacingLabel(chapterStructure.pacing) }}</n-tag>
            </div>
          </div>
        </n-card>
      </n-spin>

      <!-- 自动审阅（AI 章末管线） -->
      <n-card v-if="autopilotChapterReview" size="small" :bordered="true" class="status-card">
        <template #header>
          <span class="card-title">🤖 自动审阅</span>
        </template>
        <n-alert
          v-if="chapter && chapter.number !== autopilotChapterReview.chapter_number"
          type="info"
          size="small"
          style="margin-bottom: 12px"
        >
          为第 {{ autopilotChapterReview.chapter_number }} 章结果
        </n-alert>

        <n-space vertical :size="10">
          <!-- 张力评估 -->
          <div class="review-section">
            <n-text strong class="section-label">张力评估</n-text>
            <div class="tension-bar-wrap">
              <div class="tension-bar">
                <div class="tension-fill" :style="{ width: `${(autopilotChapterReview.tension || 0) * 10}%` }"></div>
              </div>
              <n-text class="tension-value">{{ autopilotChapterReview.tension || 0 }}/10</n-text>
            </div>
          </div>

          <!-- 叙事管线 -->
          <div class="review-section">
            <div class="section-head-row">
              <n-text strong class="section-label">章后管线</n-text>
              <n-tag size="tiny" round :type="aftermathSummary.type">
                {{ aftermathSummary.text }}
              </n-tag>
            </div>
            <div class="aftermath-track" aria-label="章后管线子步骤">
              <div
                v-for="step in aftermathSteps"
                :key="step.id"
                class="aftermath-step"
                :class="`aftermath-step--${step.state}`"
              >
                <div class="aftermath-step__ix">{{ step.index }}</div>
                <div class="aftermath-step__body">
                  <div class="aftermath-step__label-row">
                    <span class="aftermath-step__label">{{ step.label }}</span>
                    <span v-if="step.state === 'done'" class="aftermath-step__ok">✓</span>
                    <span v-else-if="step.state === 'fail'" class="aftermath-step__fail">!</span>
                  </div>
                  <span class="aftermath-step__detail">{{ step.detail }}</span>
                </div>
              </div>
            </div>
          </div>

          <!-- 文风与漂移 -->
          <div class="review-section">
            <n-text strong class="section-label">文风检测</n-text>
            <div class="review-row">
              <n-text depth="3">相似度</n-text>
              <n-text v-if="autopilotChapterReview.similarity_score != null">
                {{ Number(autopilotChapterReview.similarity_score).toFixed(3) }}
              </n-text>
              <n-text v-else depth="3" style="font-size: 12px">
                指纹不足（需 ≥10 样本）
              </n-text>
            </div>
            <div class="review-row">
              <n-text depth="3">漂移告警</n-text>
              <n-tag
                v-if="autopilotChapterReview.similarity_score != null"
                :type="autopilotChapterReview.drift_alert ? 'error' : 'success'"
                size="small"
                round
              >
                {{ autopilotChapterReview.drift_alert ? '⚠ 告警' : '✓ 正常' }}
              </n-tag>
              <n-tag v-else type="default" size="small" round>待采样</n-tag>
            </div>
          </div>

          <!-- 质量评分 -->
          <div v-if="autopilotChapterReview.quality_scores" class="review-section">
            <n-text strong class="section-label">质量评分</n-text>
            <div class="quality-grid">
              <div v-for="(score, key) in autopilotChapterReview.quality_scores" :key="key" class="quality-item">
                <n-text depth="3">{{ qualityLabel(key) }}</n-text>
                <n-progress
                  type="line"
                  :percentage="Math.round(score * 100)"
                  :height="6"
                  :show-indicator="false"
                  :color="score > 0.7 ? '#10b981' : score > 0.4 ? '#f59e0b' : '#ef4444'"
                />
                <n-text>{{ Math.round(score * 100) }}</n-text>
              </div>
            </div>
          </div>

          <!-- 问题摘要 -->
          <div v-if="autopilotChapterReview.issues && autopilotChapterReview.issues.length" class="review-section">
            <n-text strong class="section-label">问题摘要</n-text>
            <n-space vertical :size="4">
              <n-alert
                v-for="(issue, i) in autopilotChapterReview.issues.slice(0, 3)"
                :key="i"
                :type="issue.severity === 'error' ? 'error' : issue.severity === 'warning' ? 'warning' : 'info'"
                size="small"
              >
                {{ issue.message }}
              </n-alert>
              <n-text v-if="autopilotChapterReview.issues.length > 3" depth="3" style="font-size: 11px">
                还有 {{ autopilotChapterReview.issues.length - 3 }} 条问题...
              </n-text>
            </n-space>
          </div>

          <!-- 审阅时间 -->
          <div v-if="autopilotChapterReview.at" class="review-row">
            <n-text depth="3">审阅时间</n-text>
            <n-text depth="3" style="font-size: 12px">{{ formatTime(autopilotChapterReview.at) }}</n-text>
          </div>
        </n-space>
      </n-card>

      <!-- AI 生成质检 -->
      <n-card v-if="lastWorkflowResult && qcChapterNumber != null" size="small" :bordered="true" class="status-card">
        <template #header>
          <span class="card-title">✨ 生成质检</span>
        </template>
        <n-space vertical :size="10">
          <n-alert
            v-if="chapter.number !== qcChapterNumber"
            type="info"
            size="small"
          >
            为第 {{ qcChapterNumber }} 章质检结果
          </n-alert>

          <ConsistencyReportPanel
            :report="lastWorkflowResult.consistency_report"
            :token-count="lastWorkflowResult.token_count"
            @location-click="onLocationClick"
          />

          <n-collapse
            v-if="lastWorkflowResult.style_warnings && lastWorkflowResult.style_warnings.length > 0"
            class="qc-collapse"
          >
            <n-collapse-item :title="`俗套句式 ${lastWorkflowResult.style_warnings.length} 处`" name="cliche">
              <n-space vertical :size="6">
                <n-alert
                  v-for="(w, i) in lastWorkflowResult.style_warnings"
                  :key="i"
                  :type="w.severity === 'warning' ? 'warning' : 'info'"
                  :title="w.pattern"
                  size="small"
                >
                  「{{ w.text }}」
                </n-alert>
              </n-space>
            </n-collapse-item>
          </n-collapse>

          <n-collapse v-if="ghostAnnotationLines.length > 0" class="qc-collapse">
            <n-collapse-item :title="`冲突批注 ${ghostAnnotationLines.length} 条`" name="ghost">
              <n-space vertical :size="6">
                <n-alert
                  v-for="(line, gi) in ghostAnnotationLines"
                  :key="gi"
                  type="warning"
                  size="small"
                >
                  {{ line }}
                </n-alert>
              </n-space>
            </n-collapse-item>
          </n-collapse>

          <n-space :size="8">
            <n-button size="tiny" quaternary @click="$emit('go-editor')">打开编辑</n-button>
            <n-button size="tiny" quaternary @click="$emit('clear-qc')">清除</n-button>
          </n-space>
        </n-space>
      </n-card>
    </n-space>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, computed } from 'vue'
import { useMessage } from 'naive-ui'
import type { GenerateChapterWorkflowResponse } from '../../api/workflow'
import ConsistencyReportPanel from './ConsistencyReportPanel.vue'
import { chapterApi, type ChapterStructureDTO } from '../../api/chapter'
import { getChapterPacingLabel, getChapterQualityLabel } from '@/domain/chapterWriting'

interface Chapter {
  id: number | string
  number: number
  title: string
  word_count: number
}

export interface AutopilotChapterAudit {
  chapter_number: number
  tension: number
  drift_alert: boolean
  similarity_score: number | null
  narrative_sync_ok: boolean
  vector_stored?: boolean
  foreshadow_stored?: boolean
  triples_extracted?: boolean
  causal_edges_stored?: boolean
  character_mutations_stored?: boolean
  debt_updated?: boolean
  evolution_snapshot_ok?: boolean
  character_reconcile_ok?: boolean
  quality_scores?: Record<string, number>
  issues?: Array<{ severity: string; message: string }>
  at: string | null
}

const props = defineProps<{
  slug?: string
  chapter: Chapter | null
  readOnly?: boolean
  lastWorkflowResult?: GenerateChapterWorkflowResponse | null
  qcChapterNumber?: number | null
  autopilotChapterReview?: AutopilotChapterAudit | null
}>()

defineEmits<{
  (e: 'clear-qc'): void
  (e: 'go-editor'): void
}>()

const message = useMessage()

const metaLoading = ref(false)
const chapterStructure = ref<ChapterStructureDTO | null>(null)

const ghostAnnotationLines = computed(() => {
  const raw = props.lastWorkflowResult?.ghost_annotations
  if (!raw || !Array.isArray(raw) || raw.length === 0) return []
  const lines: string[] = []
  for (const item of raw) {
    if (item == null) continue
    if (typeof item === 'string') {
      lines.push(item)
      continue
    }
    if (typeof item === 'object') {
      const o = item as Record<string, unknown>
      const msg =
        (typeof o.message === 'string' && o.message) ||
        (typeof o.summary === 'string' && o.summary) ||
        (typeof o.text === 'string' && o.text) ||
        JSON.stringify(o)
      lines.push(msg)
    }
  }
  return lines
})

type AftermathStepState = 'done' | 'fail' | 'pending'

interface AftermathStep {
  index: number
  id: string
  label: string
  detail: string
  state: AftermathStepState
}

function boolStep(
  index: number,
  id: string,
  label: string,
  detail: string,
  value: boolean | undefined,
  failWhenFalse = false,
): AftermathStep {
  return {
    index,
    id,
    label,
    detail,
    state: value === true ? 'done' : (value === false && failWhenFalse ? 'fail' : 'pending'),
  }
}

const aftermathSteps = computed<AftermathStep[]>(() => {
  const r = props.autopilotChapterReview
  return [
    boolStep(1, 'narrative_summary', '摘要事件', '章节摘要、事件、场景信号写入叙事层', r?.narrative_sync_ok, true),
    boolStep(2, 'beat_sections', '叙事节拍', '大纲段落与 beat_sections 对齐', r?.narrative_sync_ok, true),
    boolStep(3, 'vector_index', '向量索引', '章节语义检索索引可被后续上下文命中', r?.vector_stored),
    boolStep(4, 'foreshadow', '伏笔账本', '埋线、兑现、回收信号进入账本', r?.foreshadow_stored),
    boolStep(5, 'kg_triples', 'KG 三元组', '人物、地点、道具与关系事实抽取', r?.triples_extracted),
    boolStep(6, 'causal_edges', '因果边', '动作后果、承诺兑现链路更新', r?.causal_edges_stored),
    boolStep(7, 'character_state', '角色状态', '角色关系、情绪与立场突变投影', r?.character_mutations_stored ?? r?.character_reconcile_ok),
    boolStep(8, 'narrative_debt', '叙事债务', '未兑现承诺、风险与后续压力更新', r?.debt_updated ?? r?.evolution_snapshot_ok),
  ]
})

const aftermathSummary = computed(() => {
  const steps = aftermathSteps.value
  const failed = steps.filter(s => s.state === 'fail').length
  const done = steps.filter(s => s.state === 'done').length
  if (failed > 0) return { type: 'warning' as const, text: `${failed} 项需复查` }
  if (done === steps.length) return { type: 'success' as const, text: '全部完成' }
  if (done > 0) return { type: 'info' as const, text: `${done}/${steps.length} 已确认` }
  return { type: 'default' as const, text: '等待结果' }
})

function pacingLabel(p: string) {
  return getChapterPacingLabel(p)
}

function qualityLabel(key: string): string {
  return getChapterQualityLabel(key)
}

function formatTime(t: string) {
  try {
    return new Date(t).toLocaleString('zh-CN', {
      month: 'numeric',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    })
  } catch {
    return t
  }
}

async function loadChapterMeta() {
  chapterStructure.value = null
  if (!props.slug || !props.chapter) return
  metaLoading.value = true
  try {
    const struct = await chapterApi.getChapterStructure(props.slug, props.chapter.number)
    chapterStructure.value = struct
  } catch {
    chapterStructure.value = null
  } finally {
    metaLoading.value = false
  }
}

watch(
  () => [props.slug, props.chapter?.number] as const,
  () => {
    void loadChapterMeta()
  },
  { immediate: true }
)

function onLocationClick(location: number) {
  message.info(`问题位置约在第 ${location} 字附近`)
}
</script>

<style scoped>
.chapter-status-panel {
  height: 100%;
  min-height: 0;
  overflow-y: auto;
  padding: 12px 16px 20px;
}

.status-card {
  transition: all 0.2s ease;
}

.status-card:hover {
  border-color: var(--n-primary-color-hover);
}

.card-title {
  font-size: 13px;
  font-weight: 600;
}

/* 章节头部 */
.chapter-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
}

.chapter-title-row {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.chapter-number {
  font-size: 13px;
  font-weight: 600;
  color: var(--n-text-color-2);
}

.chapter-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--n-text-color-1);
}

.chapter-meta {
  display: flex;
  align-items: center;
  gap: 8px;
}

.word-count {
  font-size: 12px;
}

.review-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
}

/* 结构网格 */
.structure-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
}

.structure-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
}

.structure-value {
  font-size: 16px;
  font-weight: 600;
  color: var(--n-text-color-1);
}

/* 审阅区块 */
.review-section {
  padding: 8px 0;
  border-bottom: 1px solid var(--n-border-color);
}

.review-section:last-child {
  border-bottom: none;
  padding-bottom: 0;
}

.section-label {
  display: block;
  margin-bottom: 8px;
  font-size: 12px;
}

.section-head-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 8px;
}

.section-head-row .section-label {
  margin-bottom: 0;
}

/* 张力进度条 */
.tension-bar-wrap {
  display: flex;
  align-items: center;
  gap: 12px;
}

.tension-bar {
  flex: 1;
  height: 8px;
  background: var(--n-color-modal);
  border-radius: 4px;
  overflow: hidden;
  border: 1px solid var(--n-border-color);
}

.tension-fill {
  height: 100%;
  background: linear-gradient(90deg, #10b981, #f59e0b, #ef4444);
  border-radius: 4px;
  transition: width 0.3s ease;
}

.tension-value {
  font-size: 12px;
  font-weight: 600;
  min-width: 40px;
  text-align: right;
}

/* 章后子管线 */
.aftermath-track {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
}

.aftermath-step {
  position: relative;
  display: flex;
  align-items: flex-start;
  gap: 8px;
  min-width: 0;
  padding: 8px;
  border: 1px solid var(--n-border-color);
  border-radius: var(--app-radius-sm, 8px);
  background: var(--app-surface, var(--n-color));
  transition: border-color 0.2s ease, background 0.2s ease;
}

.aftermath-step__ix {
  flex: 0 0 auto;
  width: 20px;
  height: 20px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 999px;
  font-size: 10px;
  font-weight: 800;
  color: var(--n-text-color-3);
  background: var(--n-color-modal);
  border: 1px solid var(--n-border-color);
  font-variant-numeric: tabular-nums;
}

.aftermath-step__body {
  flex: 1;
  min-width: 0;
}

.aftermath-step__label-row {
  display: flex;
  align-items: center;
  gap: 5px;
  min-width: 0;
}

.aftermath-step__label {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 12px;
  font-weight: 700;
  color: var(--n-text-color-1);
}

.aftermath-step__detail {
  display: block;
  margin-top: 3px;
  font-size: 11px;
  line-height: 1.45;
  color: var(--n-text-color-3);
}

.aftermath-step__ok,
.aftermath-step__fail {
  flex: 0 0 auto;
  font-size: 11px;
  font-weight: 900;
}

.aftermath-step__ok {
  color: var(--color-success, #10b981);
}

.aftermath-step__fail {
  color: var(--color-warning, #f59e0b);
}

.aftermath-step--done {
  border-color: color-mix(in srgb, var(--color-success, #10b981) 28%, var(--n-border-color));
  background: color-mix(in srgb, var(--color-success, #10b981) 6%, var(--app-surface, var(--n-color)));
}

.aftermath-step--done .aftermath-step__ix {
  color: var(--color-success, #10b981);
  border-color: color-mix(in srgb, var(--color-success, #10b981) 34%, var(--n-border-color));
  background: var(--color-success-dim, rgba(16, 185, 129, 0.1));
}

.aftermath-step--fail {
  border-color: color-mix(in srgb, var(--color-warning, #f59e0b) 34%, var(--n-border-color));
  background: color-mix(in srgb, var(--color-warning, #f59e0b) 7%, var(--app-surface, var(--n-color)));
}

.aftermath-step--fail .aftermath-step__ix {
  color: var(--color-warning, #f59e0b);
  border-color: color-mix(in srgb, var(--color-warning, #f59e0b) 34%, var(--n-border-color));
  background: var(--color-warning-dim, rgba(245, 158, 11, 0.1));
}

.aftermath-step--pending {
  opacity: 0.72;
}

/* 质量评分网格 */
.quality-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 8px;
}

.quality-item {
  display: flex;
  align-items: center;
  gap: 8px;
}

.quality-item n-text:first-child {
  font-size: 11px;
  min-width: 50px;
}

/* 折叠面板 */
.qc-collapse :deep(.n-collapse-item__header) {
  font-size: 12px;
}
</style>
