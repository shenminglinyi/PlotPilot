<template>
  <div class="ctx-panel pp-panel">

    <!-- ── 章节仪表盘 Header ──────────────────────────── -->
    <header class="ctx-header">
      <div class="ctx-header-main">
        <div class="ctx-chapter-row">
          <span v-if="chapterLabel" class="ctx-chapter-label">{{ chapterLabel }}</span>
          <span v-if="currentChapter?.word_count" class="ctx-word-count">
            {{ currentChapter.word_count.toLocaleString() }} 字
          </span>
          <span
            v-if="currentChapter"
            class="pp-chip"
            :class="currentChapter.word_count > 0 ? 'pp-chip--success' : 'pp-chip--muted'"
          >{{ currentChapter.word_count > 0 ? '已收稿' : '未收稿' }}</span>
          <span v-if="!currentChapter" class="pp-chip pp-chip--muted">未选择章节</span>
        </div>
        <!-- 字数进度条（有目标字数时显示） -->
        <div v-if="targetWords && currentChapter" class="ctx-progress-row">
          <n-progress
            type="line"
            :percentage="wordCountPct"
            :height="4"
            :border-radius="2"
            :color="wordCountPct >= 100 ? 'var(--color-success)' : 'var(--color-brand)'"
            :rail-color="'var(--app-border)'"
            :show-indicator="false"
            style="flex: 1"
          />
          <span class="ctx-pct-label">{{ wordCountPct }}%</span>
        </div>
      </div>
      <n-tooltip>
        <template #trigger>
          <n-button size="tiny" quaternary :loading="loading" @click="reload">
            <template #icon><n-icon size="13"><RefreshOutline /></n-icon></template>
          </n-button>
        </template>
        刷新全部数据
      </n-tooltip>
    </header>

    <!-- ── 主体内容 ──────────────────────────────────── -->
    <div class="ctx-body pp-panel-content">

      <!-- 世界规则 -->
      <div class="pp-section">
        <div class="pp-section-header">
          <span class="pp-section-label">世界规则</span>
          <n-spin v-if="loadingWorld" :size="10" />
          <span v-if="!loadingWorld && !hasWorldRules" class="pp-chip pp-chip--muted" style="margin-left:auto">未配置</span>
          <span class="pp-jump" @click="$emit('jump-tab', 'worldbuilding')">编辑 →</span>
        </div>
        <div v-if="!loadingWorld && !hasWorldRules" class="pp-section-body" style="padding-top:6px;padding-bottom:8px">
          <span style="font-size:12px;color:var(--app-text-muted)">暂无世界规则，</span>
          <span class="pp-jump" style="margin-left:0;font-size:12px" @click="$emit('jump-tab', 'worldbuilding')">去填写 →</span>
        </div>
        <div v-else-if="hasWorldRules" class="pp-section-body">
          <div v-if="worldRules.power_system" class="pp-kv">
            <span class="pp-kv-key">力量体系</span>
            <span class="pp-kv-val">{{ worldRules.power_system }}</span>
          </div>
          <div v-if="worldRules.physics_rules" class="pp-kv">
            <span class="pp-kv-key">物理规律</span>
            <span class="pp-kv-val">{{ worldRules.physics_rules }}</span>
          </div>
          <div v-if="worldRules.magic_tech" class="pp-kv">
            <span class="pp-kv-key">魔法/科技</span>
            <span class="pp-kv-val">{{ worldRules.magic_tech }}</span>
          </div>
        </div>
      </div>

      <!-- 人物心理 Avatar Rail -->
      <div class="pp-section">
        <div class="pp-section-header">
          <span class="pp-section-label">人物心理</span>
          <n-spin v-if="loadingChars" :size="10" />
          <span class="pp-jump" @click="$emit('jump-tab', 'sandbox')">编辑 →</span>
        </div>
        <div class="pp-section-body" style="padding-top:8px;padding-bottom:8px">
          <div v-if="!loadingChars && characters.length === 0" style="font-size:12px;color:var(--app-text-muted)">
            暂无角色心理档案，
            <span class="pp-jump" style="margin-left:0;font-size:12px" @click="$emit('jump-tab', 'sandbox')">去填写 →</span>
          </div>
          <div v-else class="pp-rail char-rail">
            <n-tooltip
              v-for="c in visibleChars"
              :key="c.name"
              placement="bottom"
              :style="{ maxWidth: '200px' }"
            >
              <template #trigger>
                <div
                  class="pp-avatar char-avatar"
                  :style="{ '--pp-avatar-bg': charAvatarColor(c.name) }"
                >{{ c.name.slice(0, 2) }}</div>
              </template>
              <div style="font-size:12px;line-height:1.6">
                <div style="font-weight:700;margin-bottom:3px">{{ c.name }}</div>
                <div v-if="c.wound"><span style="color:var(--color-danger);font-weight:600">伤</span> {{ c.wound }}</div>
                <div v-if="c.core_belief"><span style="color:var(--color-brand);font-weight:600">信</span> {{ c.core_belief }}</div>
              </div>
            </n-tooltip>
            <div
              v-if="characters.length > 5"
              class="char-overflow"
              @click="$emit('jump-tab', 'sandbox')"
            >+{{ characters.length - 5 }}</div>
          </div>
        </div>
      </div>

      <!-- 本章到期伏笔 -->
      <div class="pp-section">
        <div class="pp-section-header">
          <span class="pp-section-label">本章到期伏笔</span>
          <n-spin v-if="loadingFs" :size="10" />
          <span v-if="dueForeshadows.length > 0" class="pp-chip pp-chip--warning" style="font-size:10px">{{ dueForeshadows.length }}</span>
          <span class="pp-jump" @click="$emit('jump-tab', 'foreshadow')">管理 →</span>
        </div>
        <div class="pp-section-body" style="padding:8px 12px">
          <div v-if="!loadingFs && dueForeshadows.length === 0" style="font-size:12px;color:var(--app-text-muted);padding:4px 0">
            本章无到期伏笔
          </div>
          <div v-else class="pp-card-list fs-list">
            <div
              v-for="f in dueForeshadows"
              :key="f.id"
              class="pp-accent-bar fs-row"
              :style="{
                '--pp-accent-color': importanceAccentColor(f.importance),
                background: f.is_priority_for_chapter ? 'var(--color-warning-dim)' : 'transparent',
              }"
            >
              <div class="fs-row-top">
                <span class="pp-chip" :class="importanceChipClass(f.importance)" style="font-size:10px">
                  {{ importanceLabel(f.importance) }}
                </span>
                <span class="fs-question">{{ f.question }}</span>
                <span class="pp-chip pp-chip--muted" style="font-size:10px">第{{ f.chapter }}章</span>
              </div>
              <div class="fs-row-actions">
                <n-button
                  size="tiny"
                  text
                  :type="f.is_priority_for_chapter ? 'warning' : 'default'"
                  :title="f.is_priority_for_chapter ? '取消本章重点' : '标为本章重点（保证进入 AI 上下文）'"
                  :loading="priorityLoadingId === f.id"
                  @click="togglePriority(f)"
                >{{ f.is_priority_for_chapter ? '★' : '☆' }}</n-button>
                <n-button
                  size="tiny"
                  text
                  type="success"
                  title="标记此伏笔本章已使用"
                  :loading="consumeLoadingId === f.id"
                  @click="markConsumed(f)"
                >✓</n-button>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- 写作指令 -->
      <div class="ctx-hint-zone">
        <div class="ctx-hint-header">
          <n-icon size="13" class="ctx-hint-icon"><CreateOutline /></n-icon>
          <span class="ctx-hint-title">写作指令</span>
          <n-tooltip placement="top-start">
            <template #trigger>
              <span class="ctx-hint-q">?</span>
            </template>
            填写后直接注入 AI 上下文，优先于自动推断。例：男主必须得知线人被杀的消息，场景定在夜市。
          </n-tooltip>
          <span v-if="hintSaveStatus" class="pp-chip" :class="hintStatusChipClass" style="margin-left:auto;font-size:10px">
            {{ hintStatusLabel }}
          </span>
        </div>
        <n-input
          v-model:value="generationHint"
          type="textarea"
          :rows="3"
          :disabled="!currentChapter"
          placeholder="此章必须发生的事、场景限定、禁止内容……直接写给 AI"
          class="ctx-hint-input"
          @blur="saveHint"
        />
      </div>

    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { RefreshOutline, CreateOutline } from '@vicons/ionicons5'
import { worldbuildingApi } from '@/api/worldbuilding'
import { characterPsycheApi, type CharacterPsycheDTO } from '@/api/engineCore'
import { foreshadowApi, type ForeshadowEntry } from '@/api/foreshadow'
import { chapterApi } from '@/api/chapter'
import type { GenerationPrefsDTO } from '@/api/novel'
import { narrativeOrdinalLabel } from '@/utils/narrativeUnitLabel'
import {
  compareForeshadowImportanceDesc,
  getForeshadowImportanceAccentColor,
  getForeshadowImportanceChipClass,
  getForeshadowImportanceLabel,
} from '@/domain/foreshadow'
import { runtimePerformance } from '@/config/performance'

interface Chapter {
  id: number
  number: number
  title: string
  word_count: number
}

type ForeshadowEntryWithPriority = ForeshadowEntry

interface Props {
  slug: string
  currentChapter?: Chapter | null
  generationPrefs?: GenerationPrefsDTO | null
}

const props = withDefaults(defineProps<Props>(), {
  currentChapter: null,
  generationPrefs: null,
})

const emit = defineEmits<{
  'jump-tab': [tab: string]
}>()

// ── chapter label ───────────────────────────────────────────────
const chapterLabel = computed(() => {
  const ch = props.currentChapter
  if (!ch) return ''
  return narrativeOrdinalLabel(ch.number, props.generationPrefs ?? undefined)
})

// ── word count progress ─────────────────────────────────────────
const targetWords = computed(() => props.generationPrefs?.target_chapter_words ?? 0)
const wordCountPct = computed(() => {
  if (!targetWords.value || !props.currentChapter?.word_count) return 0
  return Math.min(100, Math.round((props.currentChapter.word_count / targetWords.value) * 100))
})

// ── world ───────────────────────────────────────────────────────
const loadingWorld = ref(false)
const worldRules = ref({ power_system: '', physics_rules: '', magic_tech: '' })
const hasWorldRules = computed(() =>
  !!(worldRules.value.power_system || worldRules.value.physics_rules || worldRules.value.magic_tech)
)
let worldFetchSeq = 0

async function fetchWorld() {
  const slug = props.slug
  const seq = ++worldFetchSeq
  if (!slug) {
    worldRules.value = { power_system: '', physics_rules: '', magic_tech: '' }
    loadingWorld.value = false
    return
  }
  loadingWorld.value = true
  try {
    const wb = await worldbuildingApi.getWorldbuilding(slug)
    if (seq !== worldFetchSeq || props.slug !== slug) return
    const cr = wb?.core_rules
    worldRules.value = {
      power_system: cr?.power_system ?? '',
      physics_rules: cr?.physics_rules ?? '',
      magic_tech: cr?.magic_tech ?? '',
    }
  } catch {
    /* silent */
  } finally {
    if (seq === worldFetchSeq) loadingWorld.value = false
  }
}

// ── characters ──────────────────────────────────────────────────
const loadingChars = ref(false)
const characters = ref<CharacterPsycheDTO[]>([])
const visibleChars = computed(() => characters.value.slice(0, 5))
let charsFetchSeq = 0

const AVATAR_COLORS = [
  '#2563eb', '#7c3aed', '#db2777', '#dc2626',
  '#d97706', '#059669', '#0891b2', '#65a30d',
]

function charAvatarColor(name: string): string {
  let h = 0
  for (let i = 0; i < name.length; i++) h = (h * 31 + name.charCodeAt(i)) & 0xffffffff
  return AVATAR_COLORS[Math.abs(h) % AVATAR_COLORS.length]
}

async function fetchChars() {
  const slug = props.slug
  const seq = ++charsFetchSeq
  if (!slug) {
    characters.value = []
    loadingChars.value = false
    return
  }
  loadingChars.value = true
  try {
    const res = await characterPsycheApi.list(slug)
    if (seq !== charsFetchSeq || props.slug !== slug) return
    characters.value = (res?.characters ?? []).slice(0, 8)
  } catch {
    /* silent */
  } finally {
    if (seq === charsFetchSeq) loadingChars.value = false
  }
}

// ── foreshadows ─────────────────────────────────────────────────
const loadingFs = ref(false)
const allPendingFs = ref<ForeshadowEntryWithPriority[]>([])
const consumeLoadingId = ref<string | null>(null)
const priorityLoadingId = ref<string | null>(null)
let foreshadowFetchSeq = 0

const dueForeshadows = computed(() => {
  const ch = props.currentChapter?.number ?? null
  if (ch == null) return allPendingFs.value.filter(f => f.suggested_resolve_chapter != null).slice(0, 5)
  const window = ch + 2
  return allPendingFs.value
    .filter(f => f.suggested_resolve_chapter != null && f.suggested_resolve_chapter <= window)
    .sort((a, b) => {
      if (a.is_priority_for_chapter && !b.is_priority_for_chapter) return -1
      if (!a.is_priority_for_chapter && b.is_priority_for_chapter) return 1
      return compareForeshadowImportanceDesc(a.importance, b.importance)
    })
    .slice(0, 6)
})

const importanceLabel = getForeshadowImportanceLabel
const importanceChipClass = getForeshadowImportanceChipClass
const importanceAccentColor = getForeshadowImportanceAccentColor

async function fetchForeshadows() {
  const slug = props.slug
  const seq = ++foreshadowFetchSeq
  if (!slug) {
    allPendingFs.value = []
    loadingFs.value = false
    return
  }
  loadingFs.value = true
  try {
    const entries = await foreshadowApi.list(slug, 'pending')
    if (seq !== foreshadowFetchSeq || props.slug !== slug) return
    allPendingFs.value = entries
  } catch {
    /* silent */
  } finally {
    if (seq === foreshadowFetchSeq) loadingFs.value = false
  }
}

async function markConsumed(f: ForeshadowEntryWithPriority) {
  const ch = props.currentChapter?.number
  const slug = props.slug
  if (ch == null || !slug) return
  consumeLoadingId.value = f.id
  try {
    await foreshadowApi.markConsumed(slug, f.id, ch)
    if (props.slug !== slug || props.currentChapter?.number !== ch) return
    allPendingFs.value = allPendingFs.value.filter(e => e.id !== f.id)
  } catch {
    /* silent */
  } finally {
    if (consumeLoadingId.value === f.id) consumeLoadingId.value = null
  }
}

async function togglePriority(f: ForeshadowEntryWithPriority) {
  const slug = props.slug
  if (!slug) return
  priorityLoadingId.value = f.id
  try {
    const newPriority = !f.is_priority_for_chapter
    await foreshadowApi.update(slug, f.id, { is_priority_for_chapter: newPriority })
    if (props.slug !== slug) return
    const idx = allPendingFs.value.findIndex(e => e.id === f.id)
    if (idx !== -1) allPendingFs.value[idx] = { ...allPendingFs.value[idx], is_priority_for_chapter: newPriority }
  } catch {
    /* silent */
  } finally {
    if (priorityLoadingId.value === f.id) priorityLoadingId.value = null
  }
}

// ── generation hint ─────────────────────────────────────────────
const generationHint = ref('')
const hintSaveStatus = ref<'' | 'saving' | 'saved' | 'error'>('')
let hintSaveTimer: ReturnType<typeof setTimeout> | null = null
let hintFetchSeq = 0
let hintSaveSeq = 0

const hintStatusLabel = computed(() => {
  if (hintSaveStatus.value === 'saving') return '保存中…'
  if (hintSaveStatus.value === 'saved') return '已保存'
  if (hintSaveStatus.value === 'error') return '保存失败'
  return ''
})

const hintStatusChipClass = computed(() => {
  if (hintSaveStatus.value === 'saving') return 'pp-chip--muted'
  if (hintSaveStatus.value === 'saved') return 'pp-chip--success'
  if (hintSaveStatus.value === 'error') return 'pp-chip--danger'
  return ''
})

async function saveHint() {
  const ch = props.currentChapter?.number
  const slug = props.slug
  if (ch == null || !slug) return
  const seq = ++hintSaveSeq
  if (hintSaveTimer) clearTimeout(hintSaveTimer)
  hintSaveStatus.value = 'saving'
  try {
    await chapterApi.updateGenerationHint(slug, ch, generationHint.value)
    if (seq !== hintSaveSeq || props.slug !== slug || props.currentChapter?.number !== ch) {
      if (seq === hintSaveSeq) hintSaveStatus.value = ''
      return
    }
    hintSaveStatus.value = 'saved'
    hintSaveTimer = setTimeout(() => {
      hintSaveStatus.value = ''
      hintSaveTimer = null
    }, runtimePerformance.workbench.chapterHintSavedNoticeMs)
  } catch {
    hintSaveStatus.value = 'error'
  }
}

async function fetchHint() {
  const ch = props.currentChapter?.number
  const slug = props.slug
  const seq = ++hintFetchSeq
  if (ch == null || !slug) {
    generationHint.value = ''
    return
  }
  try {
    const chapter = await chapterApi.getChapter(slug, ch)
    if (seq !== hintFetchSeq || props.slug !== slug || props.currentChapter?.number !== ch) return
    generationHint.value = chapter.generation_hint ?? ''
  } catch {
    /* silent */
  }
}

// ── loading ─────────────────────────────────────────────────────
const loading = computed(() => loadingWorld.value || loadingChars.value || loadingFs.value)

function reload() {
  fetchWorld()
  fetchChars()
  fetchForeshadows()
  fetchHint()
}

onMounted(reload)
watch(() => props.slug, reload)
watch(() => props.currentChapter?.number, () => {
  fetchForeshadows()
  fetchHint()
})

onUnmounted(() => {
  worldFetchSeq++
  charsFetchSeq++
  foreshadowFetchSeq++
  hintFetchSeq++
  hintSaveSeq++
  if (hintSaveTimer) {
    clearTimeout(hintSaveTimer)
    hintSaveTimer = null
  }
})
</script>

<style scoped>
.ctx-panel {
  /* pp-panel 提供 flex-col 骨架 */
}

/* ── Header ─────────────────────────────────────────── */
.ctx-header {
  flex-shrink: 0;
  padding: 8px 12px;
  background: var(--app-surface);
  border-bottom: 1px solid var(--plotpilot-split-border);
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 8px;
}

.ctx-header-main {
  flex: 1;
  min-width: 0;
}

.ctx-chapter-row {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}

.ctx-chapter-label {
  font-size: 13px;
  font-weight: 700;
  color: var(--app-text-primary);
  letter-spacing: 0.01em;
}

.ctx-word-count {
  font-size: 11px;
  color: var(--app-text-muted);
  font-variant-numeric: tabular-nums;
}

.ctx-progress-row {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 5px;
}

.ctx-pct-label {
  font-size: 10px;
  color: var(--app-text-muted);
  flex-shrink: 0;
  font-variant-numeric: tabular-nums;
}

/* ── Body ───────────────────────────────────────────── */
.ctx-body {
  gap: 8px;
  display: flex;
  flex-direction: column;
}

/* ── Character avatar rail ──────────────────────────── */
.char-rail {
  align-items: center;
}

.char-avatar {
  cursor: pointer;
  transition: transform 0.12s, box-shadow 0.12s;
}

.char-avatar:hover {
  transform: translateY(-1px);
  box-shadow: 0 3px 8px rgba(0,0,0,0.15);
}

.char-overflow {
  flex-shrink: 0;
  font-size: 11px;
  color: var(--app-text-muted);
  background: var(--app-border);
  border-radius: 999px;
  padding: 2px 7px;
  cursor: pointer;
  font-weight: 600;
  transition: background 0.15s;
}

.char-overflow:hover {
  background: var(--app-border-strong);
  color: var(--app-text-secondary);
}

/* ── Foreshadow rows ────────────────────────────────── */
.fs-list {
  gap: 5px;
}

.fs-row {
  border-radius: var(--app-radius-sm, 8px);
  padding: 6px 8px 6px 10px;
  display: flex;
  align-items: center;
  gap: 6px;
  transition: background 0.15s;
}

.fs-row:hover {
  background: var(--app-surface-subtle) !important;
}

.fs-row-top {
  display: flex;
  align-items: center;
  gap: 5px;
  flex: 1;
  min-width: 0;
}

.fs-question {
  flex: 1;
  min-width: 0;
  font-size: 12px;
  font-weight: 500;
  color: var(--app-text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.fs-row-actions {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  gap: 2px;
}

/* ── Writing hint zone ──────────────────────────────── */
.ctx-hint-zone {
  border-radius: var(--app-radius-md, 10px);
  background: var(--color-brand-light, rgba(37, 99, 235, 0.08));
  border: 1px solid var(--color-brand-border, rgba(37, 99, 235, 0.18));
  border-left: 3px solid var(--color-brand, #2563eb);
  overflow: hidden;
}

.ctx-hint-header {
  display: flex;
  align-items: center;
  gap: 5px;
  padding: 8px 10px 6px;
}

.ctx-hint-icon {
  color: var(--color-brand);
  opacity: 0.8;
  flex-shrink: 0;
}

.ctx-hint-title {
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.07em;
  text-transform: uppercase;
  color: var(--color-brand);
}

.ctx-hint-q {
  width: 14px;
  height: 14px;
  border-radius: 50%;
  background: var(--color-brand-border);
  color: var(--color-brand);
  font-size: 10px;
  font-weight: 700;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  cursor: help;
  opacity: 0.75;
}

.ctx-hint-input {
  border: none;
  border-radius: 0;
}

.ctx-hint-input :deep(.n-input) {
  background: transparent;
  border: none;
  border-radius: 0;
  box-shadow: none !important;
}

.ctx-hint-input :deep(.n-input__border),
.ctx-hint-input :deep(.n-input__state-border) {
  display: none;
}
</style>
