<template>
  <div class="character-profile">

    <!-- ── Header ─────────────────────────────────────────── -->
    <div class="profile-header">
      <div class="profile-header-row">
        <n-text strong class="profile-header-title">{{ headerTitle }}</n-text>
        <n-space v-if="selectedCharacterId" size="small" wrap align="center">
          <n-tag v-if="psycheDetail?.role" size="small" round :bordered="false" type="info">
            {{ psycheDetail.role }}
          </n-tag>
          <span
            v-if="mentalStateLabel"
            class="cp-state-chip"
            :class="mentalStateLevel"
          >{{ mentalStateLabel }}</span>
        </n-space>
      </div>
      <n-text depth="3" class="profile-header-sub">{{ headerSub }}</n-text>
    </div>

    <!-- ── Empty State ────────────────────────────────────── -->
    <div v-if="!selectedCharacterId" class="profile-empty">
      <n-empty description="左侧点选角色" size="small">
        <template #extra>
          <n-text depth="3" style="font-size: 11px">选择角色后显示其当下状态、底色与成长轨迹。</n-text>
        </template>
      </n-empty>
    </div>

    <!-- ── Content ────────────────────────────────────────── -->
    <n-spin v-else :show="loading">
      <div class="profile-content">

        <!-- ① 当下状态 ──────────────────────────────────── -->
        <div class="cp-section" :class="mentalStateLevel ? `cp-section--accent-${mentalStateLevel}` : ''">
          <div class="cp-section-header">
            <span class="cp-section-label">当下状态</span>
            <span
              v-if="mentalStateLabel"
              class="cp-state-chip"
              :class="mentalStateLevel"
            >{{ mentalStateLabel }}</span>
            <span v-else class="cp-state-chip cp-state-chip--calm">平稳</span>
          </div>
          <div class="cp-section-body">
            <template v-if="bibleChar?.mental_state_reason?.trim()">
              <p class="cp-state-reason">{{ bibleChar.mental_state_reason }}</p>
            </template>
            <template v-if="bibleChar?.verbal_tic?.trim() || bibleChar?.idle_behavior?.trim()">
              <div class="cp-state-hints">
                <div v-if="bibleChar?.verbal_tic?.trim()" class="cp-hint-row">
                  <span class="cp-hint-key">口癖</span>
                  <span class="cp-hint-val">{{ bibleChar.verbal_tic }}</span>
                </div>
                <div v-if="bibleChar?.idle_behavior?.trim()" class="cp-hint-row">
                  <span class="cp-hint-key">习惯</span>
                  <span class="cp-hint-val">{{ bibleChar.idle_behavior }}</span>
                </div>
              </div>
            </template>
            <div v-if="!hasMentalStateContent" class="cp-empty-hint">暂无心理状态记录</div>
          </div>
        </div>

        <!-- ② 底色 ──────────────────────────────────────── -->
        <div class="cp-section">
          <div class="cp-section-header">
            <span class="cp-section-label">灵魂底色</span>
            <span
              v-if="psycheDetail && psycheDetail.trauma_count > 0"
              class="pp-chip pp-chip--warning"
              style="font-size: 10px; padding: 1px 6px"
            >心理转折 ×{{ psycheDetail.trauma_count }}</span>
          </div>
          <div class="cp-section-body cp-t0-body">
            <!-- 速写摘要（面具） -->
            <template v-if="psycheDetail?.mask_summary?.trim()">
              <p class="cp-mask-summary">{{ psycheDetail.mask_summary }}</p>
              <div class="cp-t0-divider" />
            </template>

            <!-- 四维数据 -->
            <dl class="cp-t0-dl">
              <div class="cp-t0-row cp-t0-row--belief">
                <dt>
                  <n-tooltip placement="top-start" trigger="hover">
                    <template #trigger><span class="cp-t0-key">信念</span></template>
                    价值分叉时默认站哪边
                  </n-tooltip>
                </dt>
                <dd>{{ activeBeliefText || '—' }}</dd>
              </div>
              <div class="cp-t0-row cp-t0-row--taboo">
                <dt>
                  <n-tooltip placement="top-start" trigger="hover">
                    <template #trigger><span class="cp-t0-key">禁忌</span></template>
                    碰了就人设崩的那根线
                  </n-tooltip>
                </dt>
                <dd>{{ activeTabooText || '—' }}</dd>
              </div>
              <div class="cp-t0-row cp-t0-row--voice">
                <dt>
                  <n-tooltip placement="top-start" trigger="hover">
                    <template #trigger><span class="cp-t0-key">声线</span></template>
                    句式、口癖、节奏的总和
                  </n-tooltip>
                </dt>
                <dd>{{ activeVoiceText || '—' }}</dd>
              </div>
              <div class="cp-t0-row cp-t0-row--wound">
                <dt>
                  <n-tooltip placement="top-start" trigger="hover">
                    <template #trigger><span class="cp-t0-key">触发</span></template>
                    压力下会犯的蠢 / 过激反应
                  </n-tooltip>
                </dt>
                <dd>{{ activeWoundText || '—' }}</dd>
              </div>
            </dl>
          </div>
        </div>

        <!-- ③ 成长轨迹 ────────────────────────────────────── -->
        <div v-if="narrativeTimeline.length > 0" class="cp-section">
          <div class="cp-section-header">
            <span class="cp-section-label">成长轨迹</span>
            <span class="pp-chip pp-chip--muted" style="font-size:10px;padding:1px 6px">
              {{ narrativeTimeline.length }} 次转变
            </span>
          </div>
          <div class="cp-section-body cp-timeline-body">
            <ol class="cp-timeline-list">
              <li
                v-for="(entry, i) in narrativeTimeline"
                :key="i"
                class="cp-timeline-item"
              >
                <span class="cp-timeline-dot" />
                <div class="cp-timeline-content">
                  <span class="cp-timeline-chapter">第{{ entry.trigger_chapter }}章后</span>
                  <span class="cp-timeline-event">{{ entry.trigger_event?.trim() || '（未命名事件）' }}</span>
                  <span v-if="entry.narrativeDesc" class="cp-timeline-desc">{{ entry.narrativeDesc }}</span>
                </div>
              </li>
            </ol>
          </div>
        </div>

        <!-- ④ 调试预览（折叠） ──────────────────────────── -->
        <div v-if="injectPreviewBody" class="cp-section cp-debug-section">
          <n-collapse :default-expanded-names="[]" class="cp-debug-collapse">
            <n-collapse-item name="inject">
              <template #header>
                <span class="cp-section-label cp-debug-label">调试 · 装配预览</span>
              </template>
              <div class="cp-debug-body">
                <n-text depth="3" class="cp-debug-lead">
                  与写章 context 同构；多角场记时不会只带此人。
                </n-text>
                <pre class="cp-inject-preview">{{ injectPreviewBody }}</pre>
              </div>
            </n-collapse-item>
          </n-collapse>
        </div>

      </div>
    </n-spin>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, computed } from 'vue'
import { useMessage } from 'naive-ui'
import { characterPsycheApi, type CharacterPsycheDetailDTO } from '@/api/engineCore'
import { bibleApi, type CharacterDTO } from '@/api/bible'
import { useWorkbenchDeskTickReload } from '@/composables/useWorkbenchNarrativeSync'

interface Props {
  slug: string
  selectedCharacterId: string | null
  currentChapterNumber?: number | null
}

const props = withDefaults(defineProps<Props>(), {
  currentChapterNumber: null,
})

const message = useMessage()

const loading = ref(false)
const characterName = ref('')
const bibleChar = ref<CharacterDTO | null>(null)
const psycheDetail = ref<CharacterPsycheDetailDTO | null>(null)

// ── Header ────────────────────────────────────────────────────────
const headerTitle = computed(() =>
  props.selectedCharacterId && characterName.value ? characterName.value : '角色当下',
)

const headerSub = computed(() => {
  if (!props.selectedCharacterId) return '选择角色 · 查看当下状态与成长轨迹'
  return '当下状态 · 灵魂底色 · 成长轨迹'
})

// ── Mental State ──────────────────────────────────────────────────
const mentalStateLabel = computed(() => {
  const raw = (bibleChar.value?.mental_state ?? '').trim()
  if (!raw || raw.toUpperCase() === 'NORMAL') return ''
  return raw
})

const mentalStateLevel = computed((): string => {
  if (!mentalStateLabel.value) return ''
  const v = mentalStateLabel.value.toUpperCase()
  if (v.includes('焦虑') || v.includes('恐惧') || v.includes('崩溃') || v.includes('危机')) return 'cp-state-chip--danger'
  if (v.includes('愤怒') || v.includes('悲伤') || v.includes('痛苦') || v.includes('压抑')) return 'cp-state-chip--warning'
  return 'cp-state-chip--warning'
})

const hasMentalStateContent = computed(() =>
  !!(mentalStateLabel.value || bibleChar.value?.mental_state_reason?.trim() ||
     bibleChar.value?.verbal_tic?.trim() || bibleChar.value?.idle_behavior?.trim()),
)

// ── Active T0 data ────────────────────────────────────────────────
const activeBeliefText = computed(() =>
  (bibleChar.value?.core_belief ?? psycheDetail.value?.core_belief ?? '').trim(),
)

const activeTabooText = computed(() => {
  const taboos = bibleChar.value?.moral_taboos ?? []
  if (taboos.length > 0) return taboos.map(String).filter(Boolean).join('；')
  return (psycheDetail.value?.taboo ?? '').trim()
})

const activeVoiceText = computed(() => {
  const vp = bibleChar.value?.voice_profile
  if (vp && typeof vp === 'object') {
    const bits = (['style', 'sentence_pattern', 'speech_tempo'] as const)
      .map(k => String((vp as Record<string, unknown>)[k] ?? '').trim())
      .filter(Boolean)
    if (bits.length > 0) return bits.join(' / ')
  }
  return (psycheDetail.value?.voice_tag ?? '').trim()
})

const activeWoundText = computed(() => {
  const wounds = bibleChar.value?.active_wounds ?? []
  if (wounds.length > 0) {
    const first = wounds[0] as Record<string, string>
    const trig = (first.trigger ?? '').trim()
    const eff = (first.effect ?? '').trim()
    if (trig || eff) return trig && eff ? `${trig} → ${eff}` : trig || eff
  }
  return (psycheDetail.value?.wound ?? '').trim()
})

// ── Narrative Timeline ────────────────────────────────────────────
const PSYCHE_FIELD_NARRATIVE: Record<string, string> = {
  core_belief:   '信念产生转变',
  moral_taboos:  '行为底线调整',
  voice_profile: '表达方式改变',
  active_wounds: '新的创伤记录',
}

interface NarrativeTimelineEntry {
  trigger_chapter: number
  trigger_event: string
  narrativeDesc: string
}

const narrativeTimeline = computed((): NarrativeTimelineEntry[] => {
  const timeline = psycheDetail.value?.evolution_timeline ?? []
  return timeline.map(entry => ({
    trigger_chapter: entry.trigger_chapter,
    trigger_event: entry.trigger_event ?? '',
    narrativeDesc: (entry.changed_fields ?? [])
      .map(f => PSYCHE_FIELD_NARRATIVE[f] ?? f)
      .join('，'),
  }))
})

// ── Inject Preview ────────────────────────────────────────────────
const injectPreviewBody = computed(() => {
  if (!props.selectedCharacterId) return ''
  const c = bibleChar.value
  if (!c) return ''
  const desk = props.currentChapterNumber
  const parts: string[] = [`- ${c.name}:`]

  const pub = (c.public_profile ?? '').trim() || (c.description ?? '').trim().slice(0, 100)
  if (pub) {
    const ell = (c.description ?? '').trim().length > 100 && !(c.public_profile ?? '').trim() ? '…' : ''
    parts.push(pub + ell)
  }

  const hp = (c.hidden_profile ?? '').trim()
  if (hp) {
    const rc = c.reveal_chapter
    if (rc == null || desk == null || desk >= rc) {
      parts.push(`[隐藏面] ${hp}`)
    } else {
      parts.push(`[隐藏面] 第 ${rc} 章后揭示（当前工作台第 ${desk} 章）`)
    }
  }

  const ms = (c.mental_state ?? '').trim()
  if (ms && ms !== 'NORMAL') {
    parts.push(`心理: ${ms}` + ((c.mental_state_reason ?? '').trim() ? `（${c.mental_state_reason}）` : ''))
  }

  if ((c.verbal_tic ?? '').trim()) parts.push(`口头禅: ${c.verbal_tic}`)
  if ((c.idle_behavior ?? '').trim()) parts.push(`习惯动作: ${c.idle_behavior}`)

  const cb = activeBeliefText.value
  if (cb) parts.push(`T0·信念:${cb.slice(0, 260)}`)

  const tabooStr = activeTabooText.value
  if (tabooStr) parts.push(`T0·禁忌:${tabooStr.slice(0, 140)}`)

  const woundStr = activeWoundText.value
  if (woundStr) parts.push(`T0·创伤:${woundStr.slice(0, 140)}`)

  const voiceStr = activeVoiceText.value
  if (voiceStr) parts.push(`T0·声线:${voiceStr.slice(0, 140)}`)

  return parts.join('\n')
})

// ── Data Loading ──────────────────────────────────────────────────
async function loadCharacterData() {
  if (!props.selectedCharacterId) {
    bibleChar.value = null
    psycheDetail.value = null
    characterName.value = ''
    return
  }

  loading.value = true
  bibleChar.value = null
  characterName.value = ''
  try {
    const bible = await bibleApi.getBible(props.slug)
    const char = bible.characters?.find(x => x.id === props.selectedCharacterId) ?? null
    bibleChar.value = char
    characterName.value = char?.name ?? ''

    psycheDetail.value = characterName.value
      ? await characterPsycheApi.get(props.slug, characterName.value).catch(() => null)
      : null
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    message.error(msg || '加载角色数据失败')
    bibleChar.value = null
    psycheDetail.value = null
    characterName.value = ''
  } finally {
    loading.value = false
  }
}

watch(() => props.selectedCharacterId, () => { void loadCharacterData() }, { immediate: true })

useWorkbenchDeskTickReload(() => {
  if (props.selectedCharacterId) void loadCharacterData()
})
</script>

<style scoped>
/* ── Layout ───────────────────────────────────────────────────── */

.character-profile {
  height: 100%;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: var(--app-surface);
}

.profile-header {
  padding: 10px 14px 12px;
  border-bottom: 1px solid var(--plotpilot-split-border);
  flex-shrink: 0;
  background: linear-gradient(
    135deg,
    var(--app-surface) 75%,
    var(--color-purple-dim, rgba(139, 92, 246, 0.04)) 100%
  );
}

.profile-header-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  flex-wrap: wrap;
}

.profile-header-title {
  font-size: 14px;
  min-width: 0;
}

.profile-header-sub {
  display: block;
  margin-top: 4px;
  font-size: 11px;
  line-height: 1.45;
  letter-spacing: 0.02em;
}

.profile-empty {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
}

.profile-content {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 12px 14px 16px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  scrollbar-width: thin;
  scrollbar-color: var(--app-border) transparent;
}

.profile-content::-webkit-scrollbar {
  width: 4px;
}
.profile-content::-webkit-scrollbar-track {
  background: transparent;
}
.profile-content::-webkit-scrollbar-thumb {
  background: var(--app-border);
  border-radius: 2px;
}

/* ── Section Base ─────────────────────────────────────────────── */

.cp-section {
  border-radius: var(--app-radius-md, 10px);
  background: var(--app-surface);
  border: 1px solid var(--app-border);
  overflow: hidden;
}

.cp-section--accent-cp-state-chip--danger {
  border-left: 3px solid var(--color-danger, #ef4444);
}

.cp-section--accent-cp-state-chip--warning {
  border-left: 3px solid var(--color-warning, #f59e0b);
}

.cp-section-header {
  padding: 8px 12px;
  border-bottom: 1px solid var(--app-border);
  display: flex;
  align-items: center;
  gap: 6px;
  min-height: 32px;
}

.cp-section-label {
  font-size: 11px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.07em;
  color: var(--app-text-muted);
  flex: 1;
  min-width: 0;
}

.cp-section-body {
  padding: 10px 12px;
}

/* ── State chip (inline) ─────────────────────────────────────── */

.cp-state-chip {
  display: inline-flex;
  align-items: center;
  padding: 2px 8px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 600;
  white-space: nowrap;
  line-height: 1.4;
}

.cp-state-chip--calm {
  background: var(--color-success-dim, rgba(34, 197, 94, 0.12));
  color: var(--color-success, #22c55e);
}

.cp-state-chip--warning {
  background: var(--color-warning-dim, rgba(245, 158, 11, 0.12));
  color: var(--color-warning, #f59e0b);
}

.cp-state-chip--danger {
  background: var(--color-danger-dim, rgba(239, 68, 68, 0.12));
  color: var(--color-danger, #ef4444);
}

/* ── ① 当下状态 ──────────────────────────────────────────────── */

.cp-state-reason {
  margin: 0 0 8px;
  font-size: 12px;
  line-height: 1.65;
  color: var(--app-text-secondary);
  white-space: pre-wrap;
  word-break: break-word;
}

.cp-state-hints {
  display: flex;
  flex-direction: column;
  gap: 0;
  border: 1px solid var(--plotpilot-split-border, rgba(0, 0, 0, 0.07));
  border-radius: 6px;
  overflow: hidden;
}

.cp-hint-row {
  display: grid;
  grid-template-columns: 44px 1fr;
  font-size: 12px;
  line-height: 1.55;
  border-bottom: 1px solid var(--plotpilot-split-border, rgba(0, 0, 0, 0.06));
}

.cp-hint-row:last-child {
  border-bottom: none;
}

.cp-hint-key {
  padding: 5px 8px;
  color: var(--n-text-color-3);
  font-size: 11px;
  background: var(--app-page-bg, #f5f5f5);
  border-right: 1px solid var(--plotpilot-split-border, rgba(0, 0, 0, 0.06));
  display: flex;
  align-items: center;
}

.cp-hint-val {
  padding: 5px 10px;
  word-break: break-word;
}

.cp-empty-hint {
  font-size: 11px;
  color: var(--app-text-muted);
  text-align: center;
  padding: 4px 0;
}

/* ── ② 灵魂底色 ──────────────────────────────────────────────── */

.cp-mask-summary {
  margin: 0 0 10px;
  font-size: 12px;
  line-height: 1.75;
  white-space: pre-wrap;
  word-break: break-word;
  padding: 8px 10px;
  border-radius: 6px;
  background: var(--app-page-bg, #fafafa);
  border-left: 3px solid var(--n-primary-color-suppl, var(--color-brand, #2563eb));
  color: var(--app-text-secondary);
}

.cp-t0-divider {
  height: 1px;
  background: var(--app-border);
  margin: 2px -12px 10px;
}

.cp-t0-dl {
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: 0;
  border: 1px solid var(--plotpilot-split-border, rgba(0, 0, 0, 0.08));
  border-radius: 6px;
  overflow: hidden;
}

.cp-t0-row {
  display: grid;
  grid-template-columns: 52px 1fr;
  align-items: stretch;
  border-bottom: 1px solid var(--plotpilot-split-border, rgba(0, 0, 0, 0.06));
  font-size: 12px;
  line-height: 1.55;
}

.cp-t0-row:last-child {
  border-bottom: none;
}

.cp-t0-row dt {
  margin: 0;
  padding: 6px 8px;
  background: var(--app-page-bg, #f5f5f5);
  border-right: 1px solid var(--plotpilot-split-border, rgba(0, 0, 0, 0.06));
  display: flex;
  align-items: center;
}

.cp-t0-row dd {
  margin: 0;
  padding: 6px 10px;
  word-break: break-word;
  color: var(--app-text, rgba(0, 0, 0, 0.85));
}

.cp-t0-key {
  font-size: 11px;
  font-weight: 600;
  color: var(--app-text-secondary);
  cursor: default;
  border-bottom: 1px dotted var(--n-border-color);
}

.cp-t0-row--belief .cp-t0-key { color: #d89614; }
.cp-t0-row--taboo  .cp-t0-key { color: #c03030; }
.cp-t0-row--voice  .cp-t0-key { color: #2080d0; }
.cp-t0-row--wound  .cp-t0-key { color: #7c3aed; }

/* ── ③ 成长轨迹 ──────────────────────────────────────────────── */

.cp-timeline-body {
  padding-top: 8px;
  padding-bottom: 8px;
}

.cp-timeline-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 0;
  position: relative;
}

.cp-timeline-list::before {
  content: '';
  position: absolute;
  left: 6px;
  top: 8px;
  bottom: 8px;
  width: 1px;
  background: var(--app-border);
}

.cp-timeline-item {
  display: flex;
  gap: 10px;
  padding: 6px 0;
  position: relative;
}

.cp-timeline-dot {
  flex-shrink: 0;
  width: 13px;
  height: 13px;
  border-radius: 50%;
  background: var(--app-surface);
  border: 2px solid var(--color-purple, #8b5cf6);
  margin-top: 2px;
  position: relative;
  z-index: 1;
}

.cp-timeline-content {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding-bottom: 4px;
}

.cp-timeline-chapter {
  font-size: 11px;
  font-weight: 600;
  color: var(--color-purple, #8b5cf6);
  flex-shrink: 0;
}

.cp-timeline-event {
  font-size: 12px;
  color: var(--app-text-secondary);
  line-height: 1.5;
  word-break: break-word;
}

.cp-timeline-desc {
  font-size: 10px;
  color: var(--app-text-muted);
  line-height: 1.4;
  font-style: italic;
}

/* ── ④ 调试 · 装配预览 ────────────────────────────────────────── */

.cp-debug-section :deep(.n-collapse) {
  background: transparent;
}

.cp-debug-section :deep(.n-collapse-item) {
  background: transparent;
  border-bottom: none;
}

.cp-debug-section :deep(.n-collapse-item__header) {
  padding: 0 10px 0 0;
  min-height: 32px;
  border-bottom: 1px solid var(--app-border);
}

.cp-debug-section :deep(.n-collapse-item:not(.n-collapse-item--active) .n-collapse-item__header) {
  border-bottom: none;
}

.cp-debug-section :deep(.n-collapse-item__header-main) {
  padding: 8px 0 8px 12px;
}

.cp-debug-section :deep(.n-collapse-item__content-inner) {
  padding: 0;
}

.cp-debug-label {
  /* inherits cp-section-label */
  opacity: 0.7;
}

.cp-debug-body {
  padding: 8px 12px 10px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.cp-debug-lead {
  font-size: 10px;
  line-height: 1.45;
}

.cp-inject-preview {
  margin: 0;
  padding: 8px 10px;
  font-size: 11px;
  line-height: 1.5;
  font-family: ui-monospace, 'Cascadia Code', 'SF Mono', Menlo, Consolas, monospace;
  white-space: pre-wrap;
  word-break: break-word;
  background: var(--app-page-bg, #fafafa);
  border-radius: 6px;
  border: 1px solid var(--plotpilot-split-border, rgba(0, 0, 0, 0.08));
  max-height: min(40vh, 320px);
  overflow-y: auto;
}
</style>
