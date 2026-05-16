<template>
  <div class="quality-guardrail-panel">
    <n-empty v-if="!chapter" description="请从左侧选择一个章节" style="margin-top: 48px" />

    <div v-else class="guardrail-inner">
      <!-- 顶部操作栏 -->
      <div class="guardrail-header">
        <n-space align="center" :size="8">
          <n-text strong>第 {{ chapter.number }} 章 质量检查</n-text>
          <n-tag v-if="lastReport" :type="lastReport.passed ? 'success' : 'warning'" size="small" round>
            {{ lastReport.passed ? '✓ 通过' : '✗ 未通过' }}
          </n-tag>
        </n-space>
        <n-space :size="8">
          <n-select
            v-model:value="checkMode"
            :options="modeOptions"
            size="small"
            style="width: 100px"
          />
          <n-button
            size="small"
            type="primary"
            :loading="checking"
            :disabled="checking || !chapter.word_count"
            @click="runCheck"
          >
            {{ checking ? '检查中…' : '重新检查' }}
          </n-button>
        </n-space>
      </div>

      <n-alert type="info" :show-icon="true" size="small" style="margin-bottom: 8px">
        保存章节正文后，系统会在后台自动运行建议模式护栏并写入快照；此处可查看快照或手动再次检查。
      </n-alert>

      <!-- 检查结果 -->
      <n-spin :show="checking">
        <template v-if="lastReport">
          <!-- 总分雷达 -->
          <n-card size="small" :bordered="true" class="score-card">
            <div class="overall-score">
              <n-progress
                type="circle"
                :percentage="Math.round(lastReport.overall_score * 100)"
                :stroke-width="8"
                :color="scoreColor(lastReport.overall_score)"
                :rail-color="'var(--n-border-color)'"
                style="width: 80px"
              >
                {{ Math.round(lastReport.overall_score * 100) }}
              </n-progress>
              <div class="overall-meta">
                <n-text depth="3" style="font-size: 12px">综合评分</n-text>
                <n-text style="font-size: 20px; font-weight: 700">{{ (lastReport.overall_score * 100).toFixed(0) }}</n-text>
              </div>
            </div>
          </n-card>

          <!-- 六维度条形图 -->
          <n-card size="small" :bordered="true" class="score-card">
            <template #header>
              <span class="card-title">六维度评分</span>
            </template>
            <div class="dimension-list">
              <div v-for="dim in lastReport.dimensions" :key="dim.key" class="dimension-row">
                <n-text depth="3" style="font-size: 12px; min-width: 72px">{{ dim.name }}</n-text>
                <n-progress
                  type="line"
                  :percentage="Math.round(dim.score * 100)"
                  :height="12"
                  :color="scoreColor(dim.score)"
                  :show-indicator="false"
                  style="flex: 1"
                />
                <n-text style="font-size: 12px; min-width: 36px; text-align: right">
                  {{ Math.round(dim.score * 100) }}
                </n-text>
                <n-text depth="3" style="font-size: 10px; min-width: 32px; text-align: right">
                  ×{{ (dim.weight * 100).toFixed(0) }}%
                </n-text>
              </div>
            </div>
          </n-card>

          <!-- 违规详情 -->
          <n-card v-if="lastReport.violations.length > 0" size="small" :bordered="true" class="score-card">
            <template #header>
              <span class="card-title">违规详情 ({{ lastReport.violations.length }})</span>
            </template>
            <n-collapse :default-expanded-names="['0']" class="violation-collapse">
              <n-collapse-item
                v-for="(v, i) in lastReport.violations"
                :key="i"
                :name="String(i)"
              >
                <template #header>
                  <n-space align="center" :size="6">
                    <n-tag :type="severityType(v.severity)" size="tiny" round>
                      {{ severityLabel(v.severity) }}
                    </n-tag>
                    <n-tag size="tiny" :bordered="false">{{ dimLabel(v.dimension) }}</n-tag>
                    <n-text v-if="v.character" depth="3" style="font-size: 11px">→ {{ v.character }}</n-text>
                  </n-space>
                </template>
                <div class="violation-detail">
                  <p v-if="v.description" class="violation-desc">{{ v.description }}</p>
                  <p v-if="v.original" class="violation-original">
                    <n-text depth="3">原文：</n-text>「{{ v.original }}」
                  </p>
                  <n-alert v-if="v.suggestion" type="info" size="small" :show-icon="false" style="margin-top: 6px">
                    💡 {{ v.suggestion }}
                  </n-alert>
                </div>
              </n-collapse-item>
            </n-collapse>
          </n-card>

          <!-- 无违规 -->
          <n-alert v-else type="success" :show-icon="true" style="margin-top: 8px">
            所有维度检查通过，无违规项。
          </n-alert>
        </template>

        <!-- 无报告且未在检查中 -->
        <n-empty
          v-else-if="!checking"
          description="尚无自动快照：请先保存本章正文；也可点「重新检查」立即运行"
          size="small"
          style="margin-top: 32px"
        />
      </n-spin>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { useMessage } from 'naive-ui'
import { guardrailApi, type GuardrailCheckResponse } from '@/api/engineCore'
import { chapterApi } from '@/api/chapter'
import { useWorkbenchRefreshStore } from '@/stores/workbenchRefreshStore'

interface Chapter {
  id: number | string
  number: number
  title: string
  word_count: number
}

interface Props {
  slug: string
  chapter: Chapter | null
  readOnly?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  readOnly: false,
})

const message = useMessage()

const workbenchRefresh = useWorkbenchRefreshStore()
const { deskTick } = storeToRefs(workbenchRefresh)

const checking = ref(false)
const checkMode = ref<'advise' | 'enforce'>('advise')
const lastReport = ref<GuardrailCheckResponse | null>(null)

const modeOptions = [
  { label: '建议模式', value: 'advise' },
  { label: '强制模式', value: 'enforce' },
]

function scoreColor(score: number): string {
  if (score >= 0.75) return '#10b981'
  if (score >= 0.5) return '#f59e0b'
  return '#ef4444'
}

function severityType(sev: string): 'error' | 'warning' | 'info' | 'default' {
  const s = (sev || '').toLowerCase()
  if (s === 'critical' || s === 'error') return 'error'
  if (s === 'important' || s === 'warning') return 'warning'
  if (s === 'minor' || s === 'info') return 'info'
  return 'default'
}

function severityLabel(sev: string): string {
  const s = (sev || '').toLowerCase()
  if (s === 'critical' || s === 'error') return '严重'
  if (s === 'important' || s === 'warning') return '重要'
  if (s === 'minor' || s === 'info') return '轻微'
  return sev || '—'
}

const DIM_LABELS: Record<string, string> = {
  language_style: '语言风格',
  character_consistency: '角色一致性',
  plot_density: '情节密度',
  naming: '命名',
  viewpoint: '视角',
  rhythm: '节奏',
}

function dimLabel(key: string): string {
  return DIM_LABELS[key] || key
}

async function runCheck() {
  if (!props.chapter || !props.slug) return
  checking.value = true

  try {
    const chapterData = await chapterApi.getChapter(props.slug, props.chapter.number)
    const text = chapterData?.content || ''
    if (!text.trim()) {
      message.warning('该章节暂无正文内容')
      return
    }

    lastReport.value = await guardrailApi.check(props.slug, {
      text,
      mode: checkMode.value,
      chapter_goal: `第${props.chapter.number}章: ${props.chapter.title || ''}`,
      character_names: [],
      era: 'ancient',
      scene_type: 'auto',
    })
  } catch (e: any) {
    message.error(e?.message || '质量检查失败')
  } finally {
    checking.value = false
  }
}

async function hydrateFromSnapshot() {
  lastReport.value = null
  if (!props.slug || !props.chapter) return
  try {
    const snap = await chapterApi.getGuardrailSnapshot(props.slug, props.chapter.number)
    if (snap) {
      lastReport.value = snap
    }
  } catch {
    lastReport.value = null
  }
}

watch(
  () => [props.slug, props.chapter?.number] as const,
  () => {
    void hydrateFromSnapshot()
  },
  { immediate: true }
)

watch(deskTick, () => {
  void hydrateFromSnapshot()
})
</script>

<style scoped>
.quality-guardrail-panel {
  height: 100%;
  min-height: 0;
  overflow-y: auto;
}

.guardrail-inner {
  padding: 12px 16px 20px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.guardrail-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
}

.score-card {
  transition: all 0.2s ease;
}

.score-card:hover {
  border-color: var(--n-primary-color-hover);
}

.card-title {
  font-size: 13px;
  font-weight: 600;
}

.overall-score {
  display: flex;
  align-items: center;
  gap: 16px;
}

.overall-meta {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.dimension-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.dimension-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.violation-collapse :deep(.n-collapse-item__header) {
  font-size: 12px;
}

.violation-detail {
  font-size: 13px;
  line-height: 1.6;
}

.violation-desc {
  margin: 0 0 4px;
}

.violation-original {
  margin: 0;
  color: var(--n-text-color-2);
  font-size: 12px;
}
</style>
