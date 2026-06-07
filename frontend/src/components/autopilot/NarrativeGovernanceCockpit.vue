<template>
  <section class="ng-cockpit" aria-label="总编辑驾驶舱">
    <header class="ng-topbar">
      <div>
        <p class="ng-eyebrow">总编辑驾驶舱</p>
        <h2>叙事治理</h2>
      </div>
      <button class="ng-icon-btn" type="button" title="刷新治理状态" @click="loadState">
        <RefreshOutline class="ng-icon" />
      </button>
    </header>

    <div v-if="state" class="ng-status">
      <div class="ng-metric">
        <span>承诺命中率</span>
        <strong>{{ promiseHitRate }}</strong>
      </div>
      <div class="ng-metric">
        <span>章节预算</span>
        <strong>第 {{ budget.chapter_number }} 章</strong>
        <small>{{ budget.allowed_reveal_level }} · 新线 {{ budget.max_new_storylines }}</small>
      </div>
      <div class="ng-metric">
        <span>治理状态</span>
        <strong :class="severityClass">{{ reportSeverity }}</strong>
        <small>{{ blockReason }}</small>
      </div>
    </div>

    <div v-if="state" class="ng-grid">
      <article class="ng-panel">
        <div class="ng-panel__head">
          <h3>叙事契约</h3>
          <button class="ng-text-btn" type="button" :disabled="saving" @click="saveContract">
            <SaveOutline class="ng-icon" />
            保存
          </button>
        </div>
        <label>
          书名承诺
          <input v-model="contractDraft.title_promise" />
        </label>
        <label>
          核心问题
          <textarea v-model="contractDraft.core_question" rows="3" />
        </label>
        <label>
          主题锚点
          <input v-model="anchorsText" />
        </label>
        <label>
          不可提前兑现
          <textarea v-model="forbiddenText" rows="3" />
        </label>
      </article>

      <article class="ng-panel">
        <div class="ng-panel__head">
          <h3>Canonical Storylines</h3>
          <span>{{ state.canonical_storylines.length }}</span>
        </div>
        <div class="ng-list">
          <div v-for="line in state.canonical_storylines" :key="line.canonical_id" class="ng-line">
            <strong>{{ line.title }}</strong>
            <p>{{ line.goal || line.conflict || '等待章后事件归并' }}</p>
            <div class="ng-tags">
              <span v-for="tag in line.promise_tags" :key="tag">{{ tag }}</span>
              <span v-if="line.aliases.length">aliases {{ line.aliases.length }}</span>
            </div>
          </div>
          <p v-if="state.canonical_storylines.length === 0" class="ng-empty">暂无稳定故事线，章后事件会先进入治理层归并。</p>
        </div>
      </article>

      <article class="ng-panel">
        <div class="ng-panel__head">
          <h3>叙事债务</h3>
          <span>{{ state.open_debts.length }}</span>
        </div>
        <div class="ng-list">
          <div v-for="debt in state.open_debts.slice(0, 6)" :key="debtKey(debt)" class="ng-debt">
            <strong>{{ debtTitle(debt) }}</strong>
            <p>{{ debtDetail(debt) }}</p>
          </div>
          <p v-if="state.open_debts.length === 0" class="ng-empty">没有开放债务。</p>
        </div>
      </article>

      <aside class="ng-panel ng-panel--report">
        <div class="ng-panel__head">
          <h3>治理报告</h3>
          <button
            v-if="state.latest_report"
            class="ng-icon-btn"
            type="button"
            title="接受治理建议"
            @click="acceptReport"
          >
            <CheckmarkOutline class="ng-icon" />
          </button>
        </div>
        <div v-if="state.latest_report" class="ng-list">
          <div v-for="issue in state.latest_report.issues" :key="issue.code + issue.title" class="ng-issue">
            <span :class="['ng-severity', `ng-severity--${issue.severity}`]">{{ issue.severity }}</span>
            <strong>{{ issue.title }}</strong>
            <p>{{ issue.detail }}</p>
            <small>{{ issue.suggestion }}</small>
          </div>
          <p v-if="state.latest_report.issues.length === 0" class="ng-empty">最近一章没有结构性治理问题。</p>
        </div>
        <p v-else class="ng-empty">尚未生成治理报告。</p>
      </aside>
    </div>

    <p v-else class="ng-loading">正在读取叙事治理状态...</p>
  </section>
</template>

<script setup lang="ts">
import { CheckmarkOutline, RefreshOutline, SaveOutline } from '@vicons/ionicons5'
import { computed, onMounted, reactive, ref, watch } from 'vue'
import {
  applyGovernanceReviewAction,
  getGovernanceState,
  updateGovernanceContract,
  type GovernanceStateDTO,
} from '@/api/governance'

const props = defineProps<{
  novelId: string
}>()

const state = ref<GovernanceStateDTO | null>(null)
const saving = ref(false)
const contractDraft = reactive({
  title_promise: '',
  core_question: '',
})
const anchorsText = ref('')
const forbiddenText = ref('')

const budget = computed(() => state.value?.chapter_budget_preview ?? {
  chapter_number: 1,
  allowed_reveal_level: 'hint',
  max_new_storylines: 1,
})

const promiseHitRate = computed(() => {
  const rate = state.value?.latest_report?.promise_hit_rate
  if (typeof rate !== 'number') return '未评估'
  return `${Math.round(rate * 100)}%`
})

const reportSeverity = computed(() => state.value?.latest_report?.severity ?? 'ready')
const severityClass = computed(() => `ng-status-text--${reportSeverity.value}`)
const blockReason = computed(() => {
  if (state.value?.latest_report?.should_pause_autopilot) return '严重结构风险已阻断'
  if (state.value?.latest_report?.issues?.length) return '建议写入下一章预算'
  return '可继续自动驾驶'
})

watch(
  state,
  (next) => {
    if (!next) return
    contractDraft.title_promise = next.contract.title_promise
    contractDraft.core_question = next.contract.core_question
    anchorsText.value = next.contract.theme_anchors.join('、')
    forbiddenText.value = next.contract.forbidden_early_payoffs.join('\n')
  },
  { immediate: true },
)

onMounted(loadState)

async function loadState() {
  state.value = await getGovernanceState(props.novelId)
}

async function saveContract() {
  saving.value = true
  try {
    await updateGovernanceContract(props.novelId, {
      title_promise: contractDraft.title_promise,
      core_question: contractDraft.core_question,
      theme_anchors: splitTokens(anchorsText.value),
      forbidden_early_payoffs: forbiddenText.value.split('\n').map(v => v.trim()).filter(Boolean),
      reveal_budget: state.value?.contract.reveal_budget ?? {},
    })
    await loadState()
  } finally {
    saving.value = false
  }
}

async function acceptReport() {
  const report = state.value?.latest_report
  if (!report) return
  await applyGovernanceReviewAction(props.novelId, { report_id: report.report_id, action: 'accepted' })
  await loadState()
}

function splitTokens(text: string): string[] {
  return text.split(/[、,，\n]/).map(v => v.trim()).filter(Boolean)
}

function debtKey(debt: Record<string, unknown>): string {
  return String(debt.debt_id ?? debt.id ?? debt.title ?? JSON.stringify(debt).slice(0, 40))
}

function debtTitle(debt: Record<string, unknown>): string {
  return String(debt.title ?? debt.debt_type ?? debt.summary ?? '未命名债务')
}

function debtDetail(debt: Record<string, unknown>): string {
  return String(debt.description ?? debt.evidence ?? debt.status ?? '')
}
</script>

<style scoped>
.ng-cockpit {
  margin: 12px 16px 0;
  padding: 16px;
  height: calc(100% - 28px);
  min-height: 0;
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
  border: 1px solid var(--app-border);
  border-radius: 8px;
  background: var(--app-surface);
}

.ng-topbar,
.ng-panel__head,
.ng-status,
.ng-tags {
  display: flex;
  align-items: center;
}

.ng-topbar,
.ng-panel__head {
  justify-content: space-between;
  gap: 12px;
}

.ng-eyebrow {
  margin: 0 0 4px;
  color: var(--app-text-muted);
  font-size: 12px;
}

h2,
h3,
p {
  margin: 0;
}

h2 {
  font-size: 20px;
}

h3 {
  font-size: 14px;
}

.ng-status {
  gap: 10px;
  margin-top: 14px;
}

.ng-metric {
  flex: 1;
  min-width: 0;
  padding: 10px 12px;
  border: 1px solid var(--app-border);
  border-radius: 8px;
  background: var(--app-surface-subtle);
}

.ng-metric span,
.ng-metric small,
.ng-empty,
.ng-line p,
.ng-debt p,
.ng-issue p,
.ng-issue small {
  color: var(--app-text-muted);
}

.ng-metric span,
.ng-metric small {
  display: block;
  font-size: 12px;
}

.ng-metric strong {
  display: block;
  margin: 4px 0 2px;
  font-size: 18px;
}

.ng-grid {
  flex: 1;
  min-height: 0;
  display: grid;
  grid-template-columns: minmax(260px, 1.1fr) minmax(260px, 1fr) minmax(240px, .9fr) minmax(260px, 1fr);
  grid-auto-rows: minmax(0, 1fr);
  gap: 12px;
  margin-top: 14px;
}

.ng-panel {
  min-width: 0;
  min-height: 0;
  padding: 12px;
  display: flex;
  flex-direction: column;
  border: 1px solid var(--app-border);
  border-radius: 8px;
  background: var(--app-surface);
}

label {
  display: block;
  margin-top: 10px;
  color: var(--app-text-muted);
  font-size: 12px;
}

input,
textarea {
  width: 100%;
  box-sizing: border-box;
  margin-top: 5px;
  padding: 8px 9px;
  border: 1px solid var(--app-border);
  border-radius: 6px;
  background: var(--app-input-bg, var(--app-surface));
  color: var(--app-text);
  font: inherit;
  resize: vertical;
}

.ng-icon-btn,
.ng-text-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  height: 30px;
  border: 1px solid var(--app-border);
  border-radius: 6px;
  background: var(--app-surface);
  color: var(--app-text);
  cursor: pointer;
}

.ng-icon-btn {
  width: 30px;
}

.ng-icon {
  width: 15px;
  height: 15px;
}

.ng-text-btn {
  padding: 0 10px;
}

.ng-list {
  display: grid;
  flex: 1;
  min-height: 0;
  align-content: start;
  gap: 9px;
  margin-top: 10px;
  overflow: auto;
}

.ng-line,
.ng-debt,
.ng-issue {
  padding: 9px;
  border: 1px solid var(--app-border);
  border-radius: 7px;
  background: var(--app-surface-subtle);
}

.ng-line strong,
.ng-debt strong,
.ng-issue strong {
  display: block;
  font-size: 13px;
}

.ng-line p,
.ng-debt p,
.ng-issue p,
.ng-issue small {
  display: block;
  margin-top: 4px;
  font-size: 12px;
  line-height: 1.5;
}

.ng-tags {
  flex-wrap: wrap;
  gap: 5px;
  margin-top: 7px;
}

.ng-tags span,
.ng-severity {
  display: inline-flex;
  align-items: center;
  min-height: 20px;
  padding: 0 7px;
  border-radius: 999px;
  background: var(--app-accent-soft);
  color: var(--app-accent);
  font-size: 11px;
}

.ng-severity {
  margin-bottom: 6px;
}

.ng-severity--high,
.ng-severity--critical,
.ng-status-text--high,
.ng-status-text--critical {
  color: var(--app-danger, #b42318);
}

.ng-loading,
.ng-empty {
  padding: 14px 0;
  font-size: 13px;
}

@media (max-width: 1180px) {
  .ng-cockpit {
    height: auto;
    min-height: calc(100% - 28px);
  }

  .ng-grid {
    grid-template-columns: 1fr 1fr;
    grid-auto-rows: minmax(360px, auto);
  }
}

@media (max-width: 720px) {
  .ng-cockpit {
    min-height: auto;
  }

  .ng-status,
  .ng-grid {
    grid-template-columns: 1fr;
    display: grid;
  }
}
</style>
