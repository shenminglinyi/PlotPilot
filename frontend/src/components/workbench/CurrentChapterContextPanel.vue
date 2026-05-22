<template>
  <div class="ctx-panel">
    <!-- 章节标题栏（取代已移除的 chapter-context-bar） -->
    <header class="ctx-header">
      <div class="ctx-header-left">
        <span v-if="chapterLabel" class="ctx-chapter-label">{{ chapterLabel }}</span>
        <n-tag
          v-if="currentChapter"
          :type="currentChapter.word_count > 0 ? 'success' : 'default'"
          size="tiny"
          round
        >
          {{ currentChapter.word_count > 0 ? '已收稿' : '未收稿' }}
        </n-tag>
      </div>
      <n-button size="tiny" secondary :loading="loading" @click="reload">刷新</n-button>
    </header>

    <div class="ctx-body">
      <!-- 世界规则 -->
      <section class="ctx-section">
        <div class="section-label">
          世界规则
          <span class="ctx-jump" @click="$emit('jump-tab', 'worldbuilding')">编辑 →</span>
        </div>
        <n-spin :show="loadingWorld" size="small">
          <n-empty v-if="!loadingWorld && !hasWorldRules" description="未填写世界规则" size="small">
            <template #extra>
              <n-button size="tiny" text @click="$emit('jump-tab', 'worldbuilding')">去填写 →</n-button>
            </template>
          </n-empty>
          <div v-else class="rules-list">
            <div v-if="worldRules.power_system" class="rule-row">
              <span class="rule-key">力量体系</span>
              <span class="rule-val">{{ worldRules.power_system }}</span>
            </div>
            <div v-if="worldRules.physics_rules" class="rule-row">
              <span class="rule-key">物理规律</span>
              <span class="rule-val">{{ worldRules.physics_rules }}</span>
            </div>
            <div v-if="worldRules.magic_tech" class="rule-row">
              <span class="rule-key">魔法/科技</span>
              <span class="rule-val">{{ worldRules.magic_tech }}</span>
            </div>
          </div>
        </n-spin>
      </section>

      <!-- 人物心理 -->
      <section class="ctx-section">
        <div class="section-label">
          人物心理
          <span class="ctx-jump" @click="$emit('jump-tab', 'sandbox')">编辑 →</span>
        </div>
        <n-spin :show="loadingChars" size="small">
          <n-empty v-if="!loadingChars && characters.length === 0" description="暂无角色心理档案" size="small">
            <template #extra>
              <n-button size="tiny" text @click="$emit('jump-tab', 'sandbox')">去填写 →</n-button>
            </template>
          </n-empty>
          <div v-else class="char-list">
            <div v-for="c in characters" :key="c.name" class="char-row">
              <div class="char-name">{{ c.name }}</div>
              <div v-if="c.wound" class="char-wound">
                <span class="wound-label">伤</span>{{ c.wound }}
              </div>
              <div v-if="c.core_belief" class="char-belief">
                <span class="belief-label">信</span>{{ c.core_belief }}
              </div>
            </div>
          </div>
        </n-spin>
      </section>

      <!-- 本章到期伏笔 -->
      <section class="ctx-section">
        <div class="section-label">
          本章到期伏笔
          <span v-if="dueForeshadows.length > 0" class="section-count">{{ dueForeshadows.length }}</span>
          <span class="ctx-jump" @click="$emit('jump-tab', 'foreshadow')">管理 →</span>
        </div>
        <n-spin :show="loadingFs" size="small">
          <n-empty
            v-if="!loadingFs && dueForeshadows.length === 0"
            description="本章无到期伏笔"
            size="small"
          />
          <div v-else class="fs-list">
            <div
              v-for="f in dueForeshadows"
              :key="f.id"
              class="fs-row"
              :class="`fs-row--${f.importance}`"
            >
              <div class="fs-row-main">
                <span class="fs-importance">{{ importanceLabel(f.importance) }}</span>
                <span class="fs-question">{{ f.question }}</span>
                <span class="fs-chapter">第{{ f.chapter }}章</span>
              </div>
              <div class="fs-row-actions">
                <n-button
                  size="tiny"
                  text
                  :type="f.is_priority ? 'warning' : 'default'"
                  :title="f.is_priority ? '取消本章重点' : '标为本章重点（保证进入 AI 上下文）'"
                  :loading="priorityLoadingId === f.id"
                  @click="togglePriority(f)"
                >
                  {{ f.is_priority ? '★' : '☆' }}
                </n-button>
                <n-button
                  size="tiny"
                  text
                  type="success"
                  title="标记此伏笔本章已使用"
                  :loading="consumeLoadingId === f.id"
                  @click="markConsumed(f)"
                >
                  ✓
                </n-button>
              </div>
            </div>
          </div>
        </n-spin>
      </section>

      <!-- 本章生成约束（写作指挥中心核心功能） -->
      <section class="ctx-section ctx-section--hint">
        <div class="section-label">
          本章生成约束
          <n-tooltip>
            <template #trigger>
              <span class="hint-info-icon">?</span>
            </template>
            填写后直接注入 AI 上下文，优先于自动推断。例：男主必须得知线人被杀的消息，场景定在夜市。
          </n-tooltip>
        </div>
        <n-input
          v-model:value="generationHint"
          type="textarea"
          :rows="3"
          :disabled="!currentChapter"
          placeholder="此章必须发生的事、场景限定、禁止内容……直接写给 AI"
          class="hint-input"
          @blur="saveHint"
        />
        <div v-if="hintSaveStatus" class="hint-save-status" :class="`hint-save-status--${hintSaveStatus}`">
          {{ hintSaveStatus === 'saving' ? '保存中…' : hintSaveStatus === 'saved' ? '已保存' : '保存失败' }}
        </div>
      </section>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { worldbuildingApi } from '@/api/worldbuilding'
import { characterPsycheApi, type CharacterPsycheDTO } from '@/api/engineCore'
import { foreshadowApi, type ForeshadowEntry } from '@/api/foreshadow'
import { chapterApi } from '@/api/chapter'
import type { GenerationPrefsDTO } from '@/api/novel'
import { narrativeOrdinalLabel } from '@/utils/narrativeUnitLabel'

interface Chapter {
  id: number
  number: number
  title: string
  word_count: number
}

/** 前端扩展：带优先标记的伏笔（is_priority 在 Task 4/5 后端加入后从 API 取得） */
type ForeshadowEntryWithPriority = ForeshadowEntry & { is_priority?: boolean }

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

// ── world ───────────────────────────────────────────────────────
const loadingWorld = ref(false)
const worldRules = ref({ power_system: '', physics_rules: '', magic_tech: '' })
const hasWorldRules = computed(() =>
  !!(worldRules.value.power_system || worldRules.value.physics_rules || worldRules.value.magic_tech)
)

async function fetchWorld() {
  loadingWorld.value = true
  try {
    const wb = await worldbuildingApi.getWorldbuilding(props.slug)
    const cr = wb?.core_rules
    worldRules.value = {
      power_system: cr?.power_system ?? '',
      physics_rules: cr?.physics_rules ?? '',
      magic_tech: cr?.magic_tech ?? '',
    }
  } catch {
    /* silent */
  } finally {
    loadingWorld.value = false
  }
}

// ── characters ──────────────────────────────────────────────────
const loadingChars = ref(false)
const characters = ref<CharacterPsycheDTO[]>([])

async function fetchChars() {
  loadingChars.value = true
  try {
    const res = await characterPsycheApi.list(props.slug)
    characters.value = (res?.characters ?? []).slice(0, 5)
  } catch {
    /* silent */
  } finally {
    loadingChars.value = false
  }
}

// ── foreshadows ─────────────────────────────────────────────────
const loadingFs = ref(false)
const allPendingFs = ref<ForeshadowEntryWithPriority[]>([])
const consumeLoadingId = ref<string | null>(null)
const priorityLoadingId = ref<string | null>(null)

const dueForeshadows = computed(() => {
  const ch = props.currentChapter?.number ?? null
  if (ch == null) return allPendingFs.value.filter(f => f.suggested_resolve_chapter != null).slice(0, 5)
  const window = ch + 2
  const importanceOrder: Record<string, number> = { critical: 4, high: 3, medium: 2, low: 1 }
  return allPendingFs.value
    .filter(f => f.suggested_resolve_chapter != null && f.suggested_resolve_chapter <= window)
    .sort((a, b) => {
      // 星标优先
      if (a.is_priority && !b.is_priority) return -1
      if (!a.is_priority && b.is_priority) return 1
      return (importanceOrder[b.importance] ?? 2) - (importanceOrder[a.importance] ?? 2)
    })
    .slice(0, 6)
})

async function fetchForeshadows() {
  loadingFs.value = true
  try {
    allPendingFs.value = await foreshadowApi.list(props.slug, 'pending')
  } catch {
    /* silent */
  } finally {
    loadingFs.value = false
  }
}

async function markConsumed(f: ForeshadowEntryWithPriority) {
  const ch = props.currentChapter?.number
  if (ch == null) return
  consumeLoadingId.value = f.id
  try {
    await foreshadowApi.markConsumed(props.slug, f.id, ch)
    allPendingFs.value = allPendingFs.value.filter(e => e.id !== f.id)
  } catch {
    /* silent */
  } finally {
    consumeLoadingId.value = null
  }
}

async function togglePriority(f: ForeshadowEntryWithPriority) {
  priorityLoadingId.value = f.id
  try {
    const newPriority = !f.is_priority
    // Task 5 后端加入 is_priority_for_chapter 字段后，改为真实 API 调用
    // await foreshadowApi.update(props.slug, f.id, { is_priority_for_chapter: newPriority })
    const idx = allPendingFs.value.findIndex(e => e.id === f.id)
    if (idx !== -1) allPendingFs.value[idx] = { ...allPendingFs.value[idx], is_priority: newPriority }
  } catch {
    /* silent */
  } finally {
    priorityLoadingId.value = null
  }
}

// ── generation hint ─────────────────────────────────────────────
const generationHint = ref('')
const hintSaveStatus = ref<'' | 'saving' | 'saved' | 'error'>('')
let hintSaveTimer: ReturnType<typeof setTimeout> | null = null

async function saveHint() {
  const ch = props.currentChapter?.number
  if (ch == null || !props.slug) return
  if (hintSaveTimer) clearTimeout(hintSaveTimer)
  hintSaveStatus.value = 'saving'
  try {
    await chapterApi.updateGenerationHint(props.slug, ch, generationHint.value)
    hintSaveStatus.value = 'saved'
    hintSaveTimer = setTimeout(() => { hintSaveStatus.value = '' }, 2000)
  } catch {
    hintSaveStatus.value = 'error'
  }
}

// ── generation hint load ────────────────────────────────────────
async function fetchHint() {
  const ch = props.currentChapter?.number
  if (ch == null || !props.slug) return
  try {
    const chapter = await chapterApi.getChapter(props.slug, ch)
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

function importanceLabel(imp: string): string {
  const map: Record<string, string> = { critical: '关键', high: '重要', medium: '一般', low: '次要' }
  return map[imp] ?? imp
}
</script>

<style scoped>
.ctx-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
}

/* 章节标题栏（替代已移除的 chapter-context-bar） */
.ctx-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 6px 12px;
  background: var(--app-surface);
  border-bottom: 1px solid var(--plotpilot-split-border);
  flex-shrink: 0;
  gap: 8px;
}

.ctx-header-left {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
}

.ctx-chapter-label {
  font-size: 12px;
  font-weight: 600;
  color: var(--app-text-secondary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* 主体滚动区 */
.ctx-body {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 10px 12px 16px;
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.ctx-section {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.ctx-section--hint {
  border-top: 1px solid var(--plotpilot-split-border);
  padding-top: 12px;
  margin-top: 2px;
}

.section-label {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.05em;
  color: var(--app-text-muted);
  text-transform: uppercase;
}

/* 计数徽标（到期伏笔数） */
.section-count {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 16px;
  height: 14px;
  padding: 0 4px;
  border-radius: 7px;
  background: var(--n-error-color, #d03050);
  color: #fff;
  font-size: 10px;
  font-weight: 700;
}

/* 快速跳转链接 */
.ctx-jump {
  margin-left: auto;
  font-size: 11px;
  font-weight: 400;
  color: var(--n-primary-color, #4f46e5);
  cursor: pointer;
  letter-spacing: 0;
  text-transform: none;
  opacity: 0.8;
  transition: opacity 0.15s;
}

.ctx-jump:hover {
  opacity: 1;
}

/* ── world rules ── */
.rules-list {
  display: flex;
  flex-direction: column;
  gap: 5px;
}

.rule-row {
  display: flex;
  gap: 6px;
  font-size: 12px;
  line-height: 1.5;
}

.rule-key {
  flex-shrink: 0;
  color: var(--app-text-muted);
  width: 56px;
}

.rule-val {
  color: var(--app-text-secondary);
  word-break: break-all;
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

/* ── characters ── */
.char-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.char-row {
  background: var(--app-surface);
  border: 1px solid var(--plotpilot-split-border);
  border-radius: 6px;
  padding: 6px 8px;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.char-name {
  font-size: 12px;
  font-weight: 600;
  color: var(--app-text-primary);
  margin-bottom: 2px;
}

.char-wound,
.char-belief {
  font-size: 11px;
  color: var(--app-text-secondary);
  line-height: 1.4;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.wound-label,
.belief-label {
  display: inline-block;
  width: 14px;
  height: 14px;
  line-height: 14px;
  text-align: center;
  font-size: 10px;
  font-weight: 700;
  border-radius: 2px;
  margin-right: 4px;
  flex-shrink: 0;
}

.wound-label {
  background: rgba(240, 160, 32, 0.15);
  color: var(--n-warning-color, #f0a020);
}

.belief-label {
  background: rgba(32, 128, 240, 0.12);
  color: var(--n-info-color, #2080f0);
}

/* ── foreshadows ── */
.fs-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.fs-row {
  display: flex;
  flex-direction: column;
  gap: 3px;
  padding: 5px 6px;
  border-radius: 4px;
  background: var(--app-surface);
  border-left: 3px solid transparent;
}

.fs-row--critical { border-left-color: var(--n-error-color, #d03050); }
.fs-row--high     { border-left-color: var(--n-warning-color, #f0a020); }
.fs-row--medium   { border-left-color: var(--n-info-color, #2080f0); }
.fs-row--low      { border-left-color: var(--plotpilot-split-border); }

.fs-row-main {
  display: flex;
  align-items: baseline;
  gap: 6px;
  font-size: 12px;
}

.fs-row-actions {
  display: flex;
  gap: 4px;
  justify-content: flex-end;
  margin-top: 1px;
}

.fs-importance {
  flex-shrink: 0;
  font-size: 10px;
  font-weight: 600;
  color: var(--app-text-muted);
  width: 26px;
}

.fs-question {
  flex: 1;
  color: var(--app-text-secondary);
  line-height: 1.4;
  overflow: hidden;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}

.fs-chapter {
  flex-shrink: 0;
  font-size: 10px;
  color: var(--app-text-muted);
}

/* ── generation hint ── */
.hint-info-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 13px;
  height: 13px;
  border-radius: 50%;
  border: 1px solid var(--app-text-muted);
  font-size: 9px;
  color: var(--app-text-muted);
  cursor: default;
  letter-spacing: 0;
  text-transform: none;
  font-weight: 700;
}

.hint-input :deep(textarea) {
  font-size: 12px;
  line-height: 1.55;
}

.hint-save-status {
  font-size: 11px;
  text-align: right;
}

.hint-save-status--saving { color: var(--app-text-muted); }
.hint-save-status--saved  { color: var(--n-success-color, #18a058); }
.hint-save-status--error  { color: var(--n-error-color, #d03050); }
</style>
