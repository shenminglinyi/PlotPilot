<template>
  <div class="ndp pp-panel">

    <!-- ── Header ─────────────────────────────────────────── -->
    <header class="pp-panel-header ndp-header">
      <div class="pp-panel-header-main">
        <div class="ndp-title-row">
          <h2 class="pp-panel-title">叙事简报</h2>
          <n-tag
            v-if="currentChapter"
            size="small"
            round
            :bordered="false"
            type="info"
            class="ndp-ch-tag"
          >
            第 {{ currentChapter.number }} 章
          </n-tag>
        </div>
        <p class="pp-panel-lead">三系统联合感知 · 实时快照</p>
      </div>
      <n-tooltip trigger="hover">
        <template #trigger>
          <n-button size="tiny" quaternary :loading="loading" @click="load">
            <template #icon><n-icon size="13"><RefreshOutline /></n-icon></template>
          </n-button>
        </template>
        刷新叙事状态
      </n-tooltip>
    </header>

    <!-- ── Body ───────────────────────────────────────────── -->
    <div class="pp-panel-content ndp-body">
      <n-spin :show="loading" size="small" style="min-height: 100px">

        <!-- ① 叙事时刻 ─────────────────────────────────────── -->
        <div class="pp-section ndp-section-moment">
          <div class="pp-section-header">
            <span class="pp-section-label">叙事时刻</span>
            <span class="ndp-phase-badge" :class="`ndp-phase-badge--${phase || 'opening'}`">
              {{ phaseMeta.label }}
            </span>
          </div>
          <div class="pp-section-body ndp-moment-body">
            <!-- Progress stats -->
            <div v-if="maxChapter > 0 || progressPct > 0" class="ndp-moment-stats">
              <span v-if="currentChapter && maxChapter > 0">
                第 {{ currentChapter.number }} / {{ maxChapter }} 章
              </span>
              <span v-if="progressPct > 0" class="ndp-moment-pct">
                <template v-if="currentChapter && maxChapter > 0"> · </template>
                进度 {{ progressPct }}%
              </span>
            </div>
            <!-- Global progress bar -->
            <n-progress
              v-if="progressPct > 0"
              type="line"
              :percentage="progressPct"
              :height="3"
              :border-radius="2"
              :color="phaseMeta.color"
              :rail-color="'var(--app-border)'"
              :show-indicator="false"
              class="ndp-global-progress"
            />
            <!-- Phase axis: dots row -->
            <div class="ndp-phase-track">
              <div class="ndp-phase-dots-row">
                <template v-for="(step, i) in PHASE_STEPS" :key="step.key">
                  <div
                    class="ndp-phase-dot"
                    :class="{
                      'ndp-phase-dot--done': isLineDone(step.key),
                      'ndp-phase-dot--active': phase === step.key,
                    }"
                  />
                  <div
                    v-if="i < PHASE_STEPS.length - 1"
                    class="ndp-phase-line"
                    :class="{ 'ndp-phase-line--done': isLineDone(step.key) }"
                  />
                </template>
              </div>
              <div class="ndp-phase-labels-row">
                <span
                  v-for="step in PHASE_STEPS"
                  :key="step.key"
                  class="ndp-phase-label"
                  :class="{
                    'ndp-phase-label--done': isLineDone(step.key),
                    'ndp-phase-label--active': phase === step.key,
                  }"
                >{{ step.label }}</span>
              </div>
            </div>
            <!-- Phase description hint -->
            <p v-if="currentPhaseHint" class="ndp-phase-hint">{{ currentPhaseHint }}</p>
          </div>
        </div>

        <!-- ② 活跃线体 ──────────────────────────────────────── -->
        <div class="pp-section">
          <div class="pp-section-header">
            <span class="pp-section-label">活跃线体</span>
            <span
              v-if="activeStorylines.length > 0"
              class="pp-chip pp-chip--brand"
            >{{ activeStorylines.length }} 条</span>
          </div>
          <div v-if="activeStorylines.length > 0" class="pp-section-body ndp-threads-body">
            <div v-for="sl in activeStorylines" :key="sl.id" class="ndp-thread-row">
              <n-tag
                :type="storylineTypeNaiveColor(sl)"
                size="tiny"
                round
                class="ndp-thread-type-tag"
              >{{ storylineTypeLabel(sl) }}</n-tag>
              <span class="ndp-thread-name" :title="sl.name || undefined">
                {{ sl.name || '未命名故事线' }}
              </span>
              <div class="ndp-thread-progress-wrap">
                <div
                  class="ndp-thread-bar"
                  :class="`ndp-thread-bar--${storylineTypeKey(sl)}`"
                  :style="{ width: `${storylineMilestoneProgress(sl)}%` }"
                />
              </div>
              <span class="ndp-thread-milestone">{{ storylineMilestoneLabel(sl) }}</span>
            </div>
          </div>
          <div v-else class="ndp-empty-sm">
            <span class="ndp-empty-text-sm">本章暂无活跃故事线</span>
          </div>
        </div>

        <!-- ③ 未兑承诺 ──────────────────────────────────────── -->
        <div class="pp-section">
          <div class="pp-section-header">
            <span class="pp-section-label">未兑承诺</span>
            <span
              v-if="pendingForeshadows.length > 0"
              class="pp-chip"
              :class="hasCriticalPromise ? 'pp-chip--danger' : 'pp-chip--warning'"
            >{{ pendingForeshadows.length }}</span>
            <span v-else class="pp-chip pp-chip--success">已清</span>
          </div>
          <div v-if="urgentForeshadows.length > 0" class="pp-section-body ndp-promises-body">
            <div
              v-for="entry in urgentForeshadows"
              :key="entry.id"
              class="ndp-promise-row"
            >
              <span
                class="ndp-promise-urgency-dot"
                :class="`ndp-promise-urgency-dot--${foreshadowUrgencyClass(entry)}`"
              />
              <span class="ndp-promise-origin">[ch.{{ entry.chapter }}]</span>
              <span class="ndp-promise-question">{{ entry.question }}</span>
              <span
                v-if="entry.suggested_resolve_chapter && currentChapter"
                class="ndp-promise-due"
                :class="`ndp-promise-due--${foreshadowUrgencyClass(entry)}`"
              >
                {{ Math.max(0, entry.suggested_resolve_chapter - currentChapter.number) }}章
              </span>
            </div>
            <div v-if="pendingForeshadows.length > 5" class="ndp-promise-more">
              还有 {{ pendingForeshadows.length - 5 }} 条待兑现
            </div>
          </div>
          <div v-else class="ndp-empty-sm">
            <span class="ndp-empty-text-sm">暂无待兑现的叙事承诺</span>
          </div>
        </div>

        <!-- ④ 角色当下 ──────────────────────────────────────── -->
        <div class="pp-section">
          <div class="pp-section-header">
            <span class="pp-section-label">角色当下</span>
            <span class="pp-jump" role="button" tabindex="0" @click="goToCharacterPanel" @keydown.enter="goToCharacterPanel">
              档案 →
            </span>
          </div>
          <div v-if="mainCharacters.length > 0" class="pp-section-body ndp-cast-body">
            <div
              v-for="ch in mainCharacters"
              :key="ch.name"
              class="ndp-cast-row"
              role="button"
              tabindex="0"
              @click="goToCharacterPanel"
              @keydown.enter="goToCharacterPanel"
            >
              <span class="ndp-cast-avatar" aria-hidden="true">{{ roleEmoji(ch.role) }}</span>
              <div class="ndp-cast-info">
                <div class="ndp-cast-name-row">
                  <span class="ndp-cast-name">{{ ch.name }}</span>
                  <span
                    v-if="characterMentalState(ch.name)"
                    class="pp-chip pp-chip--warning ndp-cast-state-chip"
                  >{{ characterMentalState(ch.name) }}</span>
                </div>
                <p v-if="ch.core_belief" class="ndp-cast-belief">{{ ch.core_belief }}</p>
              </div>
            </div>
          </div>
          <div v-else class="ndp-empty-sm">
            <span class="ndp-empty-text-sm">尚未配置角色心理画像</span>
          </div>
        </div>

        <!-- ⑤ 引擎记忆（折叠） ────────────────────────────── -->
        <div class="pp-section ndp-engine-section">
          <n-collapse :default-expanded-names="[]" class="ndp-engine-collapse">
            <n-collapse-item name="engine">
              <template #header>
                <span class="pp-section-label ndp-engine-label">引擎记忆</span>
              </template>
              <div class="ndp-engine-body">
                <div class="ndp-engine-row">
                  <span class="ndp-engine-key">全书锚点</span>
                  <span class="pp-chip" :class="hasMainStoryline ? 'pp-chip--success' : 'pp-chip--muted'">
                    {{ hasMainStoryline ? '已装载' : '需配置' }}
                  </span>
                </div>
                <div class="ndp-engine-row">
                  <span class="ndp-engine-key">角色声线</span>
                  <span class="pp-chip pp-chip--brand">{{ psyches.length }} 位已配置</span>
                </div>
                <div class="ndp-engine-row">
                  <span class="ndp-engine-key">叙事债务</span>
                  <span class="pp-chip" :class="pendingForeshadows.length > 0 ? 'pp-chip--warning' : 'pp-chip--success'">
                    {{ pendingForeshadows.length }} 条待兑
                  </span>
                </div>
                <div class="ndp-engine-row">
                  <span class="ndp-engine-key">紧急伏笔</span>
                  <span class="pp-chip" :class="urgentCount > 0 ? 'pp-chip--danger' : 'pp-chip--muted'">
                    {{ urgentCount > 0 ? `${urgentCount} 条紧急` : '无紧急' }}
                  </span>
                </div>
              </div>
            </n-collapse-item>
          </n-collapse>
        </div>

      </n-spin>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { RefreshOutline } from '@vicons/ionicons5'
import { narrativeEngineApi, type StoryEvolutionReadModel } from '@/api/narrativeEngine'
import { foreshadowApi, type ForeshadowEntry } from '@/api/foreshadow'
import { characterPsycheApi, type CharacterPsycheDTO } from '@/api/engineCore'
import { bibleApi, type CharacterDTO } from '@/api/bible'
import type { StorylineDTO } from '@/api/workflow'
import { WORKBENCH_OPEN_SETTINGS_PANEL_EVENT } from '@/workbench/deskEvents'

interface Chapter {
  id: number
  number: number
  title: string
  word_count: number
}

interface Props {
  slug: string
  currentChapter?: Chapter | null
}

const props = withDefaults(defineProps<Props>(), {
  currentChapter: null,
})

// ── State ────────────────────────────────────────────────────────
const loading = ref(false)
const storyEvolution = ref<StoryEvolutionReadModel | null>(null)
const pendingForeshadows = ref<ForeshadowEntry[]>([])
const psyches = ref<CharacterPsycheDTO[]>([])
const bibleChars = ref<CharacterDTO[]>([])

// ── Phase Metadata ────────────────────────────────────────────────
const PHASE_STEPS = [
  { key: 'opening',     label: '开局', hint: '铺陈悬念，埋设伏笔，建立世界观' },
  { key: 'development', label: '发展', hint: '激化矛盾，引入支线，角色成长' },
  { key: 'convergence', label: '收敛', hint: '禁止开新坑，强制填坑，收敛线索' },
  { key: 'finale',      label: '终局', hint: '终极对决，切断日常，揭晓谜底' },
] as const

const PHASE_ORDER = ['opening', 'development', 'convergence', 'finale']

const PHASE_LABELS: Record<string, string> = {
  opening:     '开局期',
  development: '发展期',
  convergence: '收敛期',
  finale:      '终局期',
}

const PHASE_COLORS: Record<string, string> = {
  opening:     'var(--color-info)',
  development: 'var(--color-brand)',
  convergence: 'var(--color-warning)',
  finale:      'var(--color-gold)',
}

// ── Computed ──────────────────────────────────────────────────────
const phase = computed(() => storyEvolution.value?.life_cycle?.phase ?? '')

const progressPct = computed(() => {
  const p = storyEvolution.value?.life_cycle?.progress ?? 0
  return Math.round(p)
})

const maxChapter = computed(() => storyEvolution.value?.chronotope?.max_chapter_in_book ?? 0)

const phaseMeta = computed(() => ({
  label: PHASE_LABELS[phase.value] ?? '加载中…',
  color: PHASE_COLORS[phase.value] ?? 'var(--color-brand)',
}))

const currentPhaseHint = computed(() => {
  const step = PHASE_STEPS.find(s => s.key === phase.value)
  return step?.hint ?? ''
})

function isLineDone(key: string): boolean {
  return PHASE_ORDER.indexOf(key) < PHASE_ORDER.indexOf(phase.value)
}

const activeStorylines = computed((): StorylineDTO[] => {
  const ch = props.currentChapter?.number ?? 0
  const all = storyEvolution.value?.plot_spine?.storylines ?? []
  if (ch === 0) return all.slice(0, 5)
  return all
    .filter(sl => {
      const s = sl.estimated_chapter_start ?? 0
      const e = sl.estimated_chapter_end ?? 0
      const inRange = s <= ch && (e === 0 || ch <= e)
      const notDone = sl.status !== 'completed' && sl.status !== 'cancelled'
      return inRange && notDone
    })
    .slice(0, 5)
})

const urgentForeshadows = computed((): ForeshadowEntry[] =>
  pendingForeshadows.value
    .slice()
    .sort((a, b) => {
      const ca = a.suggested_resolve_chapter ?? 9999
      const cb = b.suggested_resolve_chapter ?? 9999
      return ca - cb
    })
    .slice(0, 5),
)

const hasCriticalPromise = computed(() =>
  urgentForeshadows.value.some(e => foreshadowUrgencyClass(e) === 'danger'),
)

const urgentCount = computed(() =>
  pendingForeshadows.value.filter(e => foreshadowUrgencyClass(e) === 'danger').length,
)

const hasMainStoryline = computed(() =>
  (storyEvolution.value?.plot_spine?.storylines ?? []).some(
    sl => sl.role === 'main' || sl.storyline_type === 'main',
  ),
)

const mainCharacters = computed(() =>
  [...psyches.value]
    .sort((a, b) => {
      const order: Record<string, number> = {
        PROTAGONIST: 0, protagonist: 0, main: 0,
        SUPPORTING: 1, supporting: 1,
        MINOR: 2, minor: 2,
      }
      return (order[a.role] ?? 1) - (order[b.role] ?? 1)
    })
    .slice(0, 5),
)

const bibleCharMap = computed(() => {
  const m: Record<string, CharacterDTO> = {}
  for (const c of bibleChars.value) m[c.name] = c
  return m
})

// ── Helper Functions ──────────────────────────────────────────────
function characterMentalState(name: string): string {
  const c = bibleCharMap.value[name]
  if (!c) return ''
  const ms = (c.mental_state ?? '').trim()
  if (!ms || ms.toUpperCase() === 'NORMAL') return ''
  return ms
}

function storylineTypeKey(sl: StorylineDTO): string {
  return sl.role ?? sl.storyline_type ?? 'sub'
}

function storylineTypeNaiveColor(sl: StorylineDTO): 'success' | 'warning' | 'default' {
  const t = storylineTypeKey(sl)
  if (t === 'main') return 'success'
  if (t === 'dark') return 'default'
  return 'warning'
}

function storylineTypeLabel(sl: StorylineDTO): string {
  const t = storylineTypeKey(sl)
  if (t === 'main') return '主'
  if (t === 'dark') return '暗'
  return '支'
}

function storylineMilestoneProgress(sl: StorylineDTO): number {
  const total = sl.milestones?.length ?? 0
  if (total === 0) return 0
  const curr = sl.current_milestone_index ?? 0
  return Math.min(100, Math.round((curr / total) * 100))
}

function storylineMilestoneLabel(sl: StorylineDTO): string {
  const total = sl.milestones?.length ?? 0
  if (total === 0) return ''
  const curr = sl.current_milestone_index ?? 0
  return `${curr}/${total}`
}

function foreshadowUrgencyClass(entry: ForeshadowEntry): 'danger' | 'warning' | 'muted' {
  if (entry.importance === 'critical') return 'danger'
  const due = entry.suggested_resolve_chapter
  const ch = props.currentChapter?.number ?? 0
  if (due && ch > 0) {
    const remaining = due - ch
    if (remaining <= 3) return 'danger'
    if (remaining <= 10) return 'warning'
  }
  if (entry.importance === 'high') return 'warning'
  return 'muted'
}

function roleEmoji(role: string): string {
  const r = (role ?? '').toUpperCase()
  if (r.includes('PROTAGONIST') || r === 'MAIN') return '🧑'
  if (r.includes('SUPPORTING')) return '👤'
  return '👥'
}

function goToCharacterPanel(): void {
  window.dispatchEvent(
    new CustomEvent(WORKBENCH_OPEN_SETTINGS_PANEL_EVENT, { detail: { panel: 'sandbox' } }),
  )
}

// ── Data Loading ──────────────────────────────────────────────────
async function load(): Promise<void> {
  if (!props.slug) return
  loading.value = true
  try {
    const [evo, fs, ps, bible] = await Promise.allSettled([
      narrativeEngineApi.getStoryEvolution(props.slug),
      foreshadowApi.list(props.slug, 'pending'),
      characterPsycheApi.list(props.slug),
      bibleApi.getBible(props.slug),
    ])
    if (evo.status === 'fulfilled') storyEvolution.value = evo.value
    if (fs.status === 'fulfilled') pendingForeshadows.value = fs.value
    if (ps.status === 'fulfilled') psyches.value = ps.value.characters ?? []
    if (bible.status === 'fulfilled') bibleChars.value = bible.value.characters ?? []
  } finally {
    loading.value = false
  }
}

watch(() => [props.slug, props.currentChapter?.id] as const, () => { void load() })

onMounted(() => { void load() })
</script>

<style scoped>
/* ── Layout ──────────────────────────────────────────────────────── */

.ndp {
  /* inherits pp-panel flex layout */
}

.ndp-header {
  /* slight gradient accent on header */
  background: linear-gradient(
    135deg,
    var(--app-surface) 80%,
    var(--color-brand-light, rgba(37, 99, 235, 0.04)) 100%
  );
}

.ndp-title-row {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.ndp-body {
  display: flex;
  flex-direction: column;
  gap: 0;
}

/* ── ① 叙事时刻 ─────────────────────────────────────────────────── */

.ndp-phase-badge {
  display: inline-flex;
  align-items: center;
  padding: 2px 10px;
  border-radius: 6px;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.04em;
  flex-shrink: 0;
}

.ndp-phase-badge--opening {
  background: var(--color-info-dim, rgba(59, 130, 246, 0.12));
  color: var(--color-info, #3b82f6);
}

.ndp-phase-badge--development {
  background: var(--color-brand-light, rgba(37, 99, 235, 0.08));
  color: var(--color-brand, #2563eb);
  border: 1px solid var(--color-brand-border, rgba(37, 99, 235, 0.18));
}

.ndp-phase-badge--convergence {
  background: var(--color-warning-dim, rgba(245, 158, 11, 0.12));
  color: var(--color-warning, #f59e0b);
}

.ndp-phase-badge--finale {
  background: var(--color-gold-dim, rgba(212, 168, 83, 0.15));
  color: var(--color-gold, #d4a853);
}

.ndp-moment-body {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.ndp-moment-stats {
  font-size: 12px;
  color: var(--app-text-secondary);
  line-height: 1.4;
}

.ndp-moment-pct {
  color: var(--app-text-muted);
}

.ndp-global-progress {
  /* override naive-ui progress margin */
}

.ndp-phase-track {
  display: flex;
  flex-direction: column;
  gap: 5px;
  padding: 4px 2px 0;
}

.ndp-phase-dots-row {
  display: flex;
  align-items: center;
}

.ndp-phase-dot {
  flex-shrink: 0;
  width: 9px;
  height: 9px;
  border-radius: 50%;
  background: var(--app-border);
  transition: all 0.25s ease;
}

.ndp-phase-dot--done {
  background: var(--color-success, #22c55e);
}

.ndp-phase-dot--active {
  background: var(--color-brand, #2563eb);
  width: 12px;
  height: 12px;
  box-shadow:
    0 0 0 3px var(--color-brand-light, rgba(37, 99, 235, 0.2)),
    0 0 8px var(--color-brand-light, rgba(37, 99, 235, 0.2));
}

.ndp-phase-line {
  flex: 1;
  height: 2px;
  background: var(--app-border);
  transition: background 0.25s ease;
}

.ndp-phase-line--done {
  background: var(--color-success, #22c55e);
}

.ndp-phase-labels-row {
  display: flex;
  justify-content: space-between;
}

.ndp-phase-label {
  font-size: 10px;
  color: var(--app-text-muted);
  flex: 1;
  text-align: center;
  letter-spacing: 0.02em;
  transition: color 0.2s;
}

.ndp-phase-label:first-child {
  text-align: left;
}

.ndp-phase-label:last-child {
  text-align: right;
}

.ndp-phase-label--done {
  color: var(--color-success, #22c55e);
}

.ndp-phase-label--active {
  color: var(--color-brand, #2563eb);
  font-weight: 700;
}

.ndp-phase-hint {
  margin: 2px 0 0;
  font-size: 11px;
  color: var(--app-text-muted);
  line-height: 1.45;
  font-style: italic;
}

/* ── ② 活跃线体 ─────────────────────────────────────────────────── */

.ndp-threads-body {
  padding-top: 6px;
  padding-bottom: 6px;
}

.ndp-thread-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 5px 0;
  font-size: 12px;
}

.ndp-thread-row + .ndp-thread-row {
  border-top: 1px solid var(--app-border);
}

.ndp-thread-type-tag {
  flex-shrink: 0;
}

.ndp-thread-name {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--app-text-secondary);
}

.ndp-thread-progress-wrap {
  width: 56px;
  height: 4px;
  border-radius: 2px;
  background: var(--app-border);
  flex-shrink: 0;
  overflow: hidden;
}

.ndp-thread-bar {
  height: 100%;
  border-radius: 2px;
  transition: width 0.4s ease;
  min-width: 2px;
}

.ndp-thread-bar--main {
  background: var(--color-success, #22c55e);
}

.ndp-thread-bar--sub,
.ndp-thread-bar--default {
  background: var(--color-warning, #f59e0b);
}

.ndp-thread-bar--dark {
  background: var(--color-purple, #8b5cf6);
}

.ndp-thread-milestone {
  flex-shrink: 0;
  font-size: 10px;
  color: var(--app-text-muted);
  min-width: 28px;
  text-align: right;
  font-family: var(--font-mono, monospace);
}

/* ── ③ 未兑承诺 ─────────────────────────────────────────────────── */

.ndp-promises-body {
  padding-top: 6px;
  padding-bottom: 6px;
}

.ndp-promise-row {
  display: flex;
  align-items: flex-start;
  gap: 7px;
  padding: 5px 0;
  font-size: 12px;
  line-height: 1.4;
}

.ndp-promise-row + .ndp-promise-row {
  border-top: 1px solid var(--app-border);
}

.ndp-promise-urgency-dot {
  flex-shrink: 0;
  width: 7px;
  height: 7px;
  border-radius: 50%;
  margin-top: 4px;
}

.ndp-promise-urgency-dot--danger {
  background: var(--color-danger, #ef4444);
  box-shadow: 0 0 4px var(--color-danger-dim, rgba(239, 68, 68, 0.4));
}

.ndp-promise-urgency-dot--warning {
  background: var(--color-warning, #f59e0b);
}

.ndp-promise-urgency-dot--muted {
  background: var(--app-border);
}

.ndp-promise-origin {
  flex-shrink: 0;
  font-size: 10px;
  color: var(--app-text-muted);
  font-family: var(--font-mono, monospace);
  margin-top: 1px;
  white-space: nowrap;
}

.ndp-promise-question {
  flex: 1;
  min-width: 0;
  color: var(--app-text-secondary);
  overflow: hidden;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}

.ndp-promise-due {
  flex-shrink: 0;
  font-size: 10px;
  color: var(--app-text-muted);
  white-space: nowrap;
  font-weight: 600;
  font-family: var(--font-mono, monospace);
  margin-top: 1px;
}

.ndp-promise-due--danger {
  color: var(--color-danger, #ef4444);
}

.ndp-promise-due--warning {
  color: var(--color-warning, #f59e0b);
}

.ndp-promise-due--muted {
  font-weight: 400;
}

.ndp-promise-more {
  padding: 6px 0 2px;
  font-size: 11px;
  color: var(--app-text-muted);
  text-align: center;
}

/* ── ④ 角色当下 ─────────────────────────────────────────────────── */

.ndp-cast-body {
  padding-top: 4px;
  padding-bottom: 4px;
}

.ndp-cast-row {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 7px 6px;
  border-radius: 6px;
  cursor: pointer;
  transition: background 0.15s;
}

.ndp-cast-row:hover {
  background: var(--color-brand-light, rgba(37, 99, 235, 0.06));
}

.ndp-cast-row + .ndp-cast-row {
  border-top: 1px solid var(--app-border);
}

.ndp-cast-avatar {
  font-size: 20px;
  line-height: 1;
  flex-shrink: 0;
  margin-top: 2px;
}

.ndp-cast-info {
  flex: 1;
  min-width: 0;
}

.ndp-cast-name-row {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}

.ndp-cast-name {
  font-size: 13px;
  font-weight: 600;
  color: var(--app-text-primary);
}

.ndp-cast-state-chip {
  font-size: 10px;
  padding: 1px 6px;
}

.ndp-cast-belief {
  margin: 3px 0 0;
  font-size: 11px;
  color: var(--app-text-muted);
  line-height: 1.45;
  overflow: hidden;
  display: -webkit-box;
  -webkit-line-clamp: 1;
  -webkit-box-orient: vertical;
}

/* ── ⑤ 引擎记忆 ─────────────────────────────────────────────────── */

.ndp-engine-section :deep(.n-collapse) {
  background: transparent;
}

.ndp-engine-section :deep(.n-collapse-item) {
  background: transparent;
  border-bottom: none;
}

.ndp-engine-section :deep(.n-collapse-item__header) {
  padding: 0 10px 0 0;
  min-height: 32px;
  border-bottom: 1px solid var(--app-border);
}

.ndp-engine-section :deep(.n-collapse-item:not(.n-collapse-item--active) .n-collapse-item__header) {
  border-bottom: none;
}

.ndp-engine-section :deep(.n-collapse-item__header-main) {
  padding: 8px 0 8px 12px;
}

.ndp-engine-section :deep(.n-collapse-item__content-inner) {
  padding: 0;
}

.ndp-engine-label {
  /* inherits pp-section-label via class */
}

.ndp-engine-body {
  padding: 6px 12px 8px;
}

.ndp-engine-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 4px 0;
}

.ndp-engine-row + .ndp-engine-row {
  border-top: 1px solid var(--app-border);
}

.ndp-engine-key {
  font-size: 11px;
  color: var(--app-text-muted);
}

/* ── Shared small empty state ────────────────────────────────────── */

.ndp-empty-sm {
  padding: 10px 12px;
  text-align: center;
}

.ndp-empty-text-sm {
  font-size: 11px;
  color: var(--app-text-muted);
}
</style>
