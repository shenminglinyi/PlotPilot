<template>
  <div class="rr-panel">
    <div class="rr-head">
      <span class="rr-title">审稿报告</span>
      <n-space :size="8" align="center">
        <n-button size="tiny" :loading="loading" @click="fetchReport">
          {{ report ? '刷新' : '获取报告' }}
        </n-button>
        <n-text v-if="report" depth="3" class="rr-meta">
          评分 {{ report.overall_score }}/100
        </n-text>
      </n-space>
    </div>

    <template v-if="loading && !report">
      <div class="rr-loading">
        <n-spin size="small" />
        <n-text depth="3" style="margin-left: 8px">分析中…</n-text>
      </div>
    </template>

    <template v-else-if="report">
      <div class="rr-summary">
        <n-space :size="12" align="center">
          <n-tag v-if="report.summary.critical > 0" type="error" size="small" round>
            严重 {{ report.summary.critical }}
          </n-tag>
          <n-tag v-if="report.summary.warning > 0" type="warning" size="small" round>
            警告 {{ report.summary.warning }}
          </n-tag>
          <n-tag v-if="report.summary.suggestion > 0" type="info" size="small" round>
            建议 {{ report.summary.suggestion }}
          </n-tag>
          <n-tag v-if="totalIssues === 0" type="success" size="small" round>
            无问题
          </n-tag>
        </n-space>
        <n-progress
          type="line"
          :percentage="report.overall_score"
          :height="6"
          :border-radius="4"
          :show-indicator="false"
          :color="scoreColor"
          style="margin-top: 8px"
        />
      </div>

      <n-divider style="margin: 10px 0" />

      <template v-if="report.issues.length > 0">
        <n-scrollbar style="max-height: calc(100vh - 380px)">
          <div class="rr-list">
            <div
              v-for="(issue, i) in report.issues"
              :key="i"
              class="rr-item"
              :class="'rr-item--' + issue.severity"
            >
              <n-space align="center" :size="8" wrap>
                <n-tag size="small" :type="severityTagType(issue.severity)" round>
                  {{ severityLabel(issue.severity) }}
                </n-tag>
                <n-tag size="tiny" :bordered="false">{{ issue.category }}</n-tag>
                <n-text depth="3" style="font-size: 12px">{{ issue.location }}</n-text>
              </n-space>
              <p class="rr-desc">{{ issue.description }}</p>
              <p v-if="issue.suggestion" class="rr-suggestion">
                <n-text depth="3" style="font-size: 12px">建议：{{ issue.suggestion }}</n-text>
              </p>
            </div>
          </div>
        </n-scrollbar>
      </template>

      <n-empty v-else description="未发现问题，章节质量良好" size="small" class="rr-empty" />
    </template>

    <n-empty v-else description="点击「获取报告」开始审稿" size="small" class="rr-empty" />

    <n-alert v-if="error" type="error" style="margin-top: 8px; font-size: 12px">
      {{ error }}
    </n-alert>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { chapterApi } from '../../api/chapter'
import type { ReviewReportDTO } from '../../api/chapter'

interface Props {
  slug: string
  chapterNumber: number | null
}

const props = defineProps<Props>()

const report = ref<ReviewReportDTO | null>(null)
const loading = ref(false)
const error = ref('')

const totalIssues = computed(() => {
  if (!report.value) return 0
  return report.value.issues.length
})

const scoreColor = computed(() => {
  if (!report.value) return '#18a058'
  const s = report.value.overall_score
  if (s >= 80) return '#18a058'
  if (s >= 60) return '#f0a020'
  return '#d03050'
})

function severityTagType(severity: string): 'error' | 'warning' | 'info' | 'default' {
  const s = (severity || '').toLowerCase()
  if (s === 'critical') return 'error'
  if (s === 'warning') return 'warning'
  if (s === 'suggestion') return 'info'
  return 'default'
}

function severityLabel(severity: string): string {
  const s = (severity || '').toLowerCase()
  if (s === 'critical') return '严重'
  if (s === 'warning') return '警告'
  if (s === 'suggestion') return '建议'
  return severity || '—'
}

async function fetchReport() {
  if (!props.slug || props.chapterNumber == null) {
    error.value = '请先选择章节'
    return
  }
  loading.value = true
  error.value = ''
  try {
    report.value = await chapterApi.getReviewReport(props.slug, props.chapterNumber)
  } catch (e: unknown) {
    error.value = e instanceof Error ? e.message : '获取审稿报告失败'
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.rr-panel {
  border: 1px solid var(--aitext-split-border, #e0e0e6);
  border-radius: 8px;
  padding: 10px 12px;
  background: var(--aitext-panel-muted, rgba(0, 0, 0, 0.02));
  max-height: min(70vh, 640px);
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.rr-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 8px;
  flex-shrink: 0;
}

.rr-title {
  font-weight: 600;
  font-size: 14px;
}

.rr-meta {
  font-size: 12px;
}

.rr-summary {
  flex-shrink: 0;
}

.rr-loading {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px 0;
}

.rr-list {
  display: flex;
  flex-direction: column;
  gap: 0;
}

.rr-item {
  padding: 10px 0;
}

.rr-item + .rr-item {
  border-top: 1px dashed var(--aitext-split-border, #e0e0e6);
}

.rr-item--critical {
  border-left: 3px solid #d03050;
  padding-left: 8px;
}

.rr-item--warning {
  border-left: 3px solid #f0a020;
  padding-left: 8px;
}

.rr-item--suggestion {
  border-left: 3px solid #2080f0;
  padding-left: 8px;
}

.rr-desc {
  margin: 6px 0 0;
  font-size: 13px;
  line-height: 1.5;
  color: var(--n-text-color);
}

.rr-suggestion {
  margin: 4px 0 0;
  font-size: 12px;
  line-height: 1.5;
}

.rr-empty {
  padding: 24px 0;
}
</style>
