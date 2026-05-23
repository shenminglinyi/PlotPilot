<template>
  <div class="cp">

    <!-- ── Topbar ─────────────────────────────────────────────────── -->
    <div class="cp-topbar">
      <div class="cp-identity">
        <template v-if="characterName">
          <div class="cp-avatar" :style="{ background: avatarColor }">{{ avatarInitial }}</div>
          <div class="cp-id-text">
            <div class="cp-id-name">{{ characterName }}</div>
            <div class="cp-id-row">
              <span class="cp-role-pip" :class="`cp-role-pip--${roleCssKey}`">{{ roleLabelText }}</span>
              <span v-if="mentalStateLabel" class="cp-state-pip" :class="mentalStateCssKey">
                {{ mentalStateLabel }}
              </span>
            </div>
          </div>
        </template>
        <span v-else class="cp-id-placeholder">角色档案</span>
      </div>
      <div class="cp-topbar-btns">
        <n-tooltip v-if="selectedCharacterId" trigger="hover" :delay="500">
          <template #trigger>
            <n-button size="tiny" quaternary :loading="extracting" @click="doExtract">
              <template #icon><n-icon size="12"><SyncOutline /></n-icon></template>
            </n-button>
          </template>
          从角色描述启发式提取，填充空 Bible 锚点
        </n-tooltip>
        <n-button size="tiny" quaternary :loading="loading" @click="loadCharacterData">
          <template #icon><n-icon size="12"><RefreshOutline /></n-icon></template>
        </n-button>
      </div>
    </div>

    <!-- ── Empty state ────────────────────────────────────────────── -->
    <div v-if="!selectedCharacterId" class="cp-empty">
      <div class="cp-empty-icon">🎭</div>
      <p class="cp-empty-text">从左侧点选角色<br>查看档案</p>
    </div>

    <!-- ── Tabs ───────────────────────────────────────────────────── -->
    <n-spin v-else :show="loading" size="small" class="cp-spin">
      <n-tabs
        v-model:value="activeTab"
        type="line"
        size="small"
        animated
        class="cp-tabs"
        :tab-padding="14"
      >

        <!-- ① 写作参考 ─────────────────────────────────────────── -->
        <n-tab-pane name="write" tab="写作参考" class="cp-pane">

          <!-- 此刻心理 -->
          <div class="cp-card" :class="presentCardClass">
            <div class="cp-card-hd">
              <span class="cp-card-lbl">此刻</span>
              <span v-if="mentalStateLabel" class="cp-state-pip" :class="mentalStateCssKey">
                {{ mentalStateLabel }}
              </span>
              <span v-else class="cp-state-pip cp-state-pip--calm">平稳</span>
            </div>
            <div class="cp-card-bd">
              <p v-if="bibleChar?.mental_state_reason?.trim()" class="cp-reason">
                {{ bibleChar.mental_state_reason }}
              </p>
              <div v-if="hasHabits" class="cp-habit-grid">
                <div v-if="bibleChar?.verbal_tic?.trim()" class="cp-habit-row">
                  <span class="cp-habit-k">口癖</span>
                  <span class="cp-habit-v">{{ bibleChar.verbal_tic }}</span>
                </div>
                <div v-if="bibleChar?.idle_behavior?.trim()" class="cp-habit-row">
                  <span class="cp-habit-k">肢语</span>
                  <span class="cp-habit-v">{{ bibleChar.idle_behavior }}</span>
                </div>
              </div>
              <div v-if="psycheDetail?.mask_summary?.trim()" class="cp-mask-block">
                <span class="cp-mask-ico">◉</span>
                <span class="cp-mask-txt">{{ psycheDetail.mask_summary }}</span>
              </div>
              <p v-if="!hasMentalContent" class="cp-empty-note">暂无心理状态记录</p>
            </div>
          </div>

          <!-- 声线印记 -->
          <div v-if="hasVoice" class="cp-card cp-card--voice">
            <div class="cp-card-hd">
              <span class="cp-card-lbl">声线印记</span>
            </div>
            <div class="cp-card-bd">
              <div v-if="voiceAttrs.length > 0" class="cp-voice-grid">
                <span v-for="a in voiceAttrs" :key="a.k" class="cp-voice-attr">
                  <span class="cp-va-k">{{ a.k }}</span>
                  <span class="cp-va-v">{{ a.v }}</span>
                </span>
              </div>
              <div
                v-if="voiceAttrs.length === 0 && voiceCatchphrases.length === 0 && voiceMetaphors.length === 0 && psycheDetail?.voice_tag?.trim()"
                class="cp-voice-grid"
              >
                <span class="cp-voice-attr">
                  <span class="cp-va-k">综合</span>
                  <span class="cp-va-v">{{ psycheDetail.voice_tag }}</span>
                </span>
              </div>
              <div v-if="voiceCatchphrases.length > 0" class="cp-vp-row">
                <span class="cp-vp-label">口头禅</span>
                <div class="cp-voice-pills">
                  <span v-for="(p, i) in voiceCatchphrases" :key="i" class="cp-vp cp-vp--phrase">「{{ p }}」</span>
                </div>
              </div>
              <div v-if="voiceMetaphors.length > 0" class="cp-vp-row">
                <span class="cp-vp-label">意象</span>
                <div class="cp-voice-pills">
                  <span v-for="(m, i) in voiceMetaphors" :key="i" class="cp-vp cp-vp--meta">{{ m }}</span>
                </div>
              </div>
            </div>
          </div>

          <!-- 声线占位 -->
          <div v-else class="cp-card">
            <div class="cp-card-hd"><span class="cp-card-lbl">声线印记</span></div>
            <div class="cp-card-bd">
              <p class="cp-empty-note">暂无声线数据 · 点击 ↻ 从描述提取</p>
            </div>
          </div>

        </n-tab-pane>

        <!-- ② 记忆 ────────────────────────────────────────────────── -->
        <n-tab-pane name="memory" tab="记忆" class="cp-pane">

          <!-- 活跃创伤 -->
          <div v-if="activeWounds.length > 0" class="cp-card cp-card--wound">
            <div class="cp-card-hd">
              <span class="cp-card-lbl">创伤反射</span>
              <span class="cp-chip cp-chip--purple">{{ activeWounds.length }}</span>
            </div>
            <div class="cp-card-bd">
              <div class="cp-wounds">
                <div v-for="(w, i) in activeWounds" :key="i" class="cp-wound">
                  <div class="cp-wound-line cp-wound-line--t">
                    <span class="cp-wound-badge cp-wound-badge--t">触发</span>
                    <span class="cp-wound-txt">{{ w.trigger || w.description || '—' }}</span>
                  </div>
                  <div class="cp-wound-arrow">↓</div>
                  <div class="cp-wound-line cp-wound-line--r">
                    <span class="cp-wound-badge cp-wound-badge--r">应激</span>
                    <span class="cp-wound-txt">{{ w.effect || '—' }}</span>
                  </div>
                  <p v-if="w.description && w.trigger" class="cp-wound-bg">{{ w.description }}</p>
                </div>
              </div>
            </div>
          </div>

          <!-- 成长地质图 -->
          <div class="cp-card">
            <div class="cp-card-hd">
              <span class="cp-card-lbl">成长记忆</span>
              <span v-if="narrativeTimeline.length" class="cp-chip cp-chip--muted">
                {{ narrativeTimeline.length }}次转折
              </span>
            </div>
            <div class="cp-card-bd">
              <div v-if="narrativeTimeline.length > 0" class="cp-tl">
                <div v-for="(e, i) in narrativeTimeline" :key="i" class="cp-tl-item">
                  <div class="cp-tl-node" />
                  <div class="cp-tl-content">
                    <div class="cp-tl-meta">
                      <span class="cp-tl-ch">第{{ e.trigger_chapter }}章</span>
                      <span v-if="e.narrativeDesc" class="cp-tl-dims">{{ e.narrativeDesc }}</span>
                    </div>
                    <p class="cp-tl-event">{{ e.trigger_event || '（未命名事件）' }}</p>
                  </div>
                </div>
              </div>
              <p v-else class="cp-empty-note">暂无成长记录 · 随章节生成自动积累</p>
            </div>
          </div>

        </n-tab-pane>

        <!-- ③ 待校准 ─────────────────────────────────────────────── -->
        <n-tab-pane name="calibration" tab="待校准" class="cp-pane">
          <div class="cp-card">
            <div class="cp-card-hd">
              <span class="cp-card-lbl">候选记忆</span>
              <span v-if="candidateMemories.length" class="cp-chip cp-chip--purple">{{ candidateMemories.length }}</span>
            </div>
            <div class="cp-card-bd">
              <div v-if="candidateMemories.length" class="cp-candidates">
                <div v-for="m in candidateMemories" :key="m.id" class="cp-candidate">
                  <div class="cp-candidate-meta">
                    <span class="cp-chip cp-chip--muted">{{ memoryTypeLabel(m.memory_type) }}</span>
                    <span v-if="m.chapter_number" class="cp-tl-ch">第{{ m.chapter_number }}章</span>
                    <span class="cp-confidence">{{ Math.round((m.confidence ?? 0) * 100) }}%</span>
                  </div>
                  <p class="cp-candidate-text">{{ memoryAtomText(m) }}</p>
                  <div class="cp-candidate-actions">
                    <n-button size="tiny" type="primary" text :loading="calibratingId === m.id" @click="confirmMemory(m.id)">确认</n-button>
                    <n-button size="tiny" text :loading="calibratingId === m.id" @click="rejectMemory(m.id)">拒绝</n-button>
                  </div>
                </div>
              </div>
              <p v-else class="cp-empty-note">暂无待校准记忆 · 章后抽取会在这里积累候选项</p>
            </div>
          </div>
        </n-tab-pane>

        <!-- ④ 档案 ────────────────────────────────────────────────── -->
        <n-tab-pane name="file" tab="档案" class="cp-pane">

          <!-- 人设两面 -->
          <div v-if="hasProfiles" class="cp-card">
            <div class="cp-card-hd">
              <span class="cp-card-lbl">人设两面</span>
              <span v-if="isHiddenLocked" class="cp-chip cp-chip--muted">🔒 第{{ bibleChar?.reveal_chapter }}章后</span>
            </div>
            <div class="cp-card-bd cp-profiles-bd">
              <div v-if="bibleChar?.public_profile?.trim()" class="cp-profile">
                <div class="cp-profile-hd">
                  <span class="cp-profile-dot" style="background: var(--color-success, #22c55e)" />
                  <span class="cp-profile-lbl">公开人设</span>
                </div>
                <p class="cp-prose">{{ bibleChar.public_profile }}</p>
              </div>
              <div v-if="bibleChar?.hidden_profile?.trim()" class="cp-profile cp-profile--hidden">
                <div class="cp-profile-hd">
                  <span class="cp-profile-dot" style="background: var(--color-purple, #8b5cf6)" />
                  <span class="cp-profile-lbl">
                    隐藏真相
                    <span v-if="isHiddenLocked" class="cp-profile-lock-note">（第{{ bibleChar?.reveal_chapter }}章前保密）</span>
                  </span>
                </div>
                <p class="cp-prose">{{ bibleChar.hidden_profile }}</p>
              </div>
            </div>
          </div>

          <!-- 核心信念 -->
          <div v-if="activeBelief" class="cp-card cp-card--belief">
            <div class="cp-card-hd"><span class="cp-card-lbl">核心信念</span></div>
            <div class="cp-card-bd">
              <blockquote class="cp-belief-quote">{{ activeBelief }}</blockquote>
            </div>
          </div>

          <!-- 行为禁区 -->
          <div v-if="activeTaboos.length > 0" class="cp-card cp-card--taboo">
            <div class="cp-card-hd"><span class="cp-card-lbl">行为禁区</span></div>
            <div class="cp-card-bd">
              <div class="cp-taboos">
                <span v-for="(t, i) in activeTaboos" :key="i" class="cp-taboo-chip">⛔ {{ t }}</span>
              </div>
            </div>
          </div>

          <!-- 无档案占位 -->
          <div v-if="!hasProfiles && !activeBelief && !activeTaboos.length" class="cp-card">
            <div class="cp-card-bd">
              <p class="cp-empty-note">暂无档案数据 · 在世界观中完善 Bible 设定</p>
            </div>
          </div>

          <!-- 调试·装配预览 -->
          <div v-if="injectPreviewBody" class="cp-card cp-card--debug">
            <div class="cp-card-hd cp-card-hd--clickable" @click="debugOpen = !debugOpen">
              <span class="cp-card-lbl cp-card-lbl--dim">调试·装配预览</span>
              <span class="cp-chevron" :class="{ 'cp-chevron--open': debugOpen }">›</span>
            </div>
            <div v-show="debugOpen" class="cp-card-bd">
              <p class="cp-debug-note">Context 层注入预览</p>
              <pre class="cp-debug-pre">{{ injectPreviewBody }}</pre>
            </div>
          </div>

        </n-tab-pane>

        <!-- ⑤ 对白 ────────────────────────────────────────────────── -->
        <n-tab-pane name="dialogue" tab="对白" class="cp-pane cp-pane--fill" display-directive="show">
          <DialogueCorpus
            :slug="slug"
            :selected-character-id="selectedCharacterId"
            :desk-chapter-number="deskChapterNumber"
          />
        </n-tab-pane>

      </n-tabs>
    </n-spin>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, computed } from 'vue'
import { useMessage } from 'naive-ui'
import { RefreshOutline, SyncOutline } from '@vicons/ionicons5'
import {
  characterPsycheApi,
  type CharacterPsycheDetailDTO,
} from '@/api/engineCore'
import { bibleApi, type CharacterDTO } from '@/api/bible'
import { memoryApi, type CharacterProjection, type MemoryAtom } from '@/api/memory'
import { useWorkbenchDeskTickReload } from '@/composables/useWorkbenchNarrativeSync'
import DialogueCorpus from './DialogueCorpus.vue'

interface Props {
  slug: string
  selectedCharacterId: string | null
  currentChapterNumber?: number | null
  deskChapterNumber?: number | null
}

const props = withDefaults(defineProps<Props>(), {
  currentChapterNumber: null,
  deskChapterNumber: null,
})

const message = useMessage()

// ── State ─────────────────────────────────────────────────────────
const loading    = ref(false)
const extracting = ref(false)

const characterName  = ref('')
const bibleChar      = ref<CharacterDTO | null>(null)
const psycheDetail   = ref<CharacterPsycheDetailDTO | null>(null)
const projection     = ref<CharacterProjection | null>(null)

const activeTab  = ref<'write' | 'memory' | 'calibration' | 'file' | 'dialogue'>('write')
const debugOpen  = ref(false)
const calibratingId = ref<string | null>(null)

// ── Avatar & Role ─────────────────────────────────────────────────
const ROLE_COLORS: Record<string, string> = {
  PROTAGONIST: 'var(--color-brand, #2563eb)',
  SUPPORTING:  'var(--color-warning, #f59e0b)',
  MINOR:       'var(--app-text-muted)',
}
const ROLE_LABELS: Record<string, string> = {
  PROTAGONIST: '主角',
  SUPPORTING:  '配角',
  MINOR:       '龙套',
}

const roleKey = computed(() =>
  (bibleChar.value?.role ?? psycheDetail.value?.role ?? '').toUpperCase() || 'MINOR',
)
const avatarColor   = computed(() => ROLE_COLORS[roleKey.value] ?? ROLE_COLORS.MINOR)
const avatarInitial = computed(() => characterName.value.slice(0, 1) || '?')
const roleLabelText = computed(() => ROLE_LABELS[roleKey.value] ?? roleKey.value)
const roleCssKey    = computed(() => roleKey.value.toLowerCase())

// ── Mental State ──────────────────────────────────────────────────
const mentalStateLabel = computed(() => {
  const raw = (bibleChar.value?.mental_state ?? '').trim()
  const projected = String(projection.value?.current_state?.summary ?? '').trim()
  if ((!raw || raw.toUpperCase() === 'NORMAL') && projected) return projected
  return raw && raw.toUpperCase() !== 'NORMAL' ? raw : ''
})

const mentalStateCssKey = computed((): string => {
  const v = mentalStateLabel.value
  if (!v) return ''
  if (/焦虑|恐惧|崩溃|危机|绝望/.test(v)) return 'cp-state-pip--danger'
  if (/愤怒|悲伤|痛苦|压抑/.test(v))      return 'cp-state-pip--warning'
  return 'cp-state-pip--active'
})

const presentCardClass = computed(() => {
  const k = mentalStateCssKey.value
  if (k === 'cp-state-pip--danger')  return 'cp-card--danger-accent'
  if (k === 'cp-state-pip--warning') return 'cp-card--warning-accent'
  return ''
})

const hasMentalContent = computed(() =>
  !!(mentalStateLabel.value ||
     bibleChar.value?.mental_state_reason?.trim() ||
     bibleChar.value?.verbal_tic?.trim() ||
     bibleChar.value?.idle_behavior?.trim() ||
     psycheDetail.value?.mask_summary?.trim()),
)
const hasHabits = computed(() =>
  !!(bibleChar.value?.verbal_tic?.trim() || bibleChar.value?.idle_behavior?.trim()),
)

// ── Profiles ──────────────────────────────────────────────────────
const hasProfiles = computed(() =>
  !!(bibleChar.value?.public_profile?.trim() || bibleChar.value?.hidden_profile?.trim()),
)
const isHiddenLocked = computed(() => {
  const rc = bibleChar.value?.reveal_chapter
  const ch = props.currentChapterNumber
  return typeof rc === 'number' && typeof ch === 'number' && ch < rc
})

// ── 4D Anchors ────────────────────────────────────────────────────
const activeBelief = computed(() =>
  (bibleChar.value?.core_belief ?? psycheDetail.value?.core_belief ?? '').trim(),
)
const activeTaboos = computed((): string[] => {
  const arr = bibleChar.value?.moral_taboos
  if (Array.isArray(arr) && arr.length > 0) return arr.map(String).filter(Boolean)
  const str = (psycheDetail.value?.taboo ?? '').trim()
  if (str) return str.split(/[；;]+/).map(s => s.trim()).filter(Boolean)
  return []
})

interface VoiceShape {
  style?: string
  sentence_pattern?: string
  speech_tempo?: string
  metaphors?: unknown[]
  catchphrases?: unknown[]
}
const voiceObj = computed((): VoiceShape | null => {
  const vp = bibleChar.value?.voice_profile ?? projection.value?.voice_fingerprint
  return (vp && typeof vp === 'object') ? (vp as VoiceShape) : null
})
const TEMPO_MAP: Record<string, string> = { fast: '急促', normal: '平稳', slow: '舒缓' }
const voiceAttrs = computed((): Array<{ k: string; v: string }> => {
  const v = voiceObj.value
  if (!v) return []
  const out: Array<{ k: string; v: string }> = []
  if (v.style)            out.push({ k: '风格', v: String(v.style) })
  if (v.sentence_pattern) out.push({ k: '句式', v: String(v.sentence_pattern) })
  if (v.speech_tempo)     out.push({ k: '节奏', v: TEMPO_MAP[String(v.speech_tempo)] ?? String(v.speech_tempo) })
  return out
})
const voiceCatchphrases = computed((): string[] => {
  const cp = voiceObj.value?.catchphrases
  return Array.isArray(cp) ? cp.map(String).filter(Boolean) : []
})
const voiceMetaphors = computed((): string[] => {
  const m = voiceObj.value?.metaphors
  return Array.isArray(m) ? m.map(String).filter(Boolean) : []
})
const hasVoice = computed(() =>
  voiceAttrs.value.length > 0 ||
  voiceCatchphrases.value.length > 0 ||
  voiceMetaphors.value.length > 0 ||
  !!(psycheDetail.value?.voice_tag?.trim()),
)

// ── Wounds ────────────────────────────────────────────────────────
interface WoundShape { description?: string; trigger?: string; effect?: string }
const activeWounds = computed((): WoundShape[] => {
  const projected = projection.value?.active_scars
  if (Array.isArray(projected) && projected.length > 0) {
    return projected.map(w => ({
      description: String(w.impact ?? w.description ?? ''),
      trigger: String(w.source_event ?? w.trigger ?? ''),
      effect: String(w.impact ?? w.effect ?? ''),
    })).filter(w => w.trigger || w.effect || w.description)
  }
  const arr = bibleChar.value?.active_wounds
  if (Array.isArray(arr) && arr.length > 0)
    return (arr as WoundShape[]).filter(w => w.trigger || w.effect || w.description)
  const str = (psycheDetail.value?.wound ?? '').trim()
  if (str) {
    const p = str.split(/→/).map(s => s.trim())
    return p.length >= 2 ? [{ trigger: p[0], effect: p[1] }] : [{ description: str }]
  }
  return []
})

// ── Evolution Timeline ─────────────────────────────────────────────
const FIELD_NARRATIVE: Record<string, string> = {
  core_belief:   '信念转变',
  moral_taboos:  '底线调整',
  voice_profile: '声线改变',
  active_wounds: '新增创伤',
}
interface TLEntry { trigger_chapter: number; trigger_event: string; narrativeDesc: string }
const narrativeTimeline = computed((): TLEntry[] =>
  projection.value?.emotional_arc?.length
    ? projection.value.emotional_arc.map(e => ({
      trigger_chapter: Number(e.chapter ?? 0),
      trigger_event: String(e.trigger ?? e.emotion ?? ''),
      narrativeDesc: String(e.emotion ?? '情绪弧点'),
    })).filter(e => e.trigger_chapter > 0)
    : (psycheDetail.value?.evolution_timeline ?? []).map(e => ({
    trigger_chapter: e.trigger_chapter,
    trigger_event:   e.trigger_event ?? '',
    narrativeDesc:   (e.changed_fields ?? []).map((f: string) => FIELD_NARRATIVE[f] ?? f).join('，'),
  })),
)

const candidateMemories = computed(() => projection.value?.candidate_memories ?? [])

function memoryTypeLabel(type: string): string {
  const map: Record<string, string> = {
    state: '状态',
    scar: '创伤',
    motivation: '执念',
    emotion: '情绪',
    voice: '对白',
    relationship: '关系',
    debt: '债务',
    fact: '事实',
  }
  return map[type] ?? type
}

function memoryAtomText(atom: MemoryAtom): string {
  const p = atom.payload ?? {}
  return String(
    p.summary ?? p.mental_state ?? p.impact_or_description ?? p.impact ??
    p.description ?? p.content ?? p.source_event ?? atom.text_span ?? '（空候选）',
  )
}

// ── Inject Preview ─────────────────────────────────────────────────
const injectPreviewBody = computed(() => {
  const c = bibleChar.value
  if (!c) return ''
  const desk = props.currentChapterNumber
  const parts: string[] = [`- ${c.name}:`]
  const pub = (c.public_profile ?? '').trim() || (c.description ?? '').trim().slice(0, 100)
  if (pub) parts.push(pub + ((c.description ?? '').trim().length > 100 && !(c.public_profile ?? '').trim() ? '…' : ''))
  const hp = (c.hidden_profile ?? '').trim()
  if (hp) {
    const rc = c.reveal_chapter
    parts.push((rc == null || desk == null || desk >= rc) ? `[隐藏面] ${hp}` : `[隐藏面] 第 ${rc} 章后揭示`)
  }
  const ms = (c.mental_state ?? '').trim()
  if (ms && ms !== 'NORMAL') parts.push(`心理: ${ms}` + ((c.mental_state_reason ?? '').trim() ? `（${c.mental_state_reason}）` : ''))
  if ((c.verbal_tic ?? '').trim())    parts.push(`口头禅: ${c.verbal_tic}`)
  if ((c.idle_behavior ?? '').trim()) parts.push(`习惯动作: ${c.idle_behavior}`)
  if (activeBelief.value)        parts.push(`T0·信念: ${activeBelief.value.slice(0, 260)}`)
  if (activeTaboos.value.length) parts.push(`T0·禁忌: ${activeTaboos.value.join('；').slice(0, 140)}`)
  const wStr = activeWounds.value
    .map(w => (w.trigger && w.effect) ? `${w.trigger} → ${w.effect}` : w.description ?? '')
    .filter(Boolean).join('；')
  if (wStr) parts.push(`T0·创伤: ${wStr.slice(0, 140)}`)
  const vStr = voiceAttrs.value.map(a => `${a.k}·${a.v}`).join('；') || (psycheDetail.value?.voice_tag ?? '').trim()
  if (vStr) parts.push(`T0·声线: ${vStr.slice(0, 140)}`)
  return parts.join('\n')
})

// ── Actions ───────────────────────────────────────────────────────
async function loadCharacterData() {
  if (!props.selectedCharacterId) {
    bibleChar.value = null; psycheDetail.value = null; projection.value = null; characterName.value = ''
    return
  }
  loading.value = true
  try {
    const bible = await bibleApi.getBible(props.slug)
    const char  = bible.characters?.find(x => x.id === props.selectedCharacterId) ?? null
    bibleChar.value     = char
    characterName.value = char?.name ?? ''
    const [psyche, proj] = await Promise.all([
      characterName.value
        ? characterPsycheApi.get(props.slug, characterName.value).catch(() => null)
        : Promise.resolve(null),
      memoryApi.getCharacterProjection(props.slug, props.selectedCharacterId).catch(() => null),
    ])
    psycheDetail.value = psyche
    projection.value = proj
  } catch (err: unknown) {
    message.error(err instanceof Error ? err.message : '加载角色数据失败')
  } finally {
    loading.value = false
  }
}

async function confirmMemory(atomId: string) {
  calibratingId.value = atomId
  try {
    await memoryApi.confirm(props.slug, atomId)
    message.success('已确认候选记忆')
    void loadCharacterData()
  } catch {
    message.error('确认失败')
  } finally {
    calibratingId.value = null
  }
}

async function rejectMemory(atomId: string) {
  calibratingId.value = atomId
  try {
    await memoryApi.reject(props.slug, atomId)
    message.success('已拒绝候选记忆')
    void loadCharacterData()
  } catch {
    message.error('拒绝失败')
  } finally {
    calibratingId.value = null
  }
}

async function doExtract() {
  if (!characterName.value) return
  extracting.value = true
  try {
    const r = await characterPsycheApi.extractToBible(props.slug, characterName.value)
    if (r.ok) {
      message.success(`已同步 ${r.applied_keys.length} 项到 Bible`)
      void loadCharacterData()
    } else {
      message.warning(r.warnings[0] || '无可同步内容')
    }
  } catch {
    message.error('同步失败')
  } finally {
    extracting.value = false
  }
}

watch(() => props.selectedCharacterId, () => {
  activeTab.value = 'write'
  void loadCharacterData()
}, { immediate: true })

useWorkbenchDeskTickReload(() => {
  if (props.selectedCharacterId) void loadCharacterData()
})
</script>

<style scoped>
/* ── Shell ──────────────────────────────────────────────────────── */

.cp {
  height: 100%;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: var(--app-surface);
}

/* ── Topbar ──────────────────────────────────────────────────────── */

.cp-topbar {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 10px 14px;
  border-bottom: 1px solid var(--plotpilot-split-border);
  background: linear-gradient(135deg, var(--app-surface) 75%, var(--color-purple-dim, rgba(139,92,246,0.04)) 100%);
}

.cp-identity {
  display: flex;
  align-items: center;
  gap: 9px;
  min-width: 0;
  flex: 1;
}

.cp-avatar {
  flex-shrink: 0;
  width: 32px;
  height: 32px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 14px;
  font-weight: 700;
  color: #fff;
  line-height: 1;
  user-select: none;
  text-shadow: 0 1px 2px rgba(0,0,0,0.18);
}

.cp-id-text { min-width: 0; flex: 1; }

.cp-id-name {
  font-size: 14px;
  font-weight: 600;
  color: var(--app-text-primary);
  line-height: 1.25;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.cp-id-row {
  display: flex;
  align-items: center;
  gap: 5px;
  margin-top: 3px;
  flex-wrap: wrap;
}

.cp-id-placeholder {
  font-size: 13px;
  font-weight: 600;
  color: var(--app-text-secondary);
}

.cp-topbar-btns { display: flex; gap: 2px; flex-shrink: 0; }

/* Role pip */
.cp-role-pip {
  display: inline-flex;
  align-items: center;
  padding: 1px 7px;
  border-radius: 999px;
  font-size: 10px;
  font-weight: 700;
  white-space: nowrap;
  letter-spacing: 0.04em;
}
.cp-role-pip--protagonist { background: var(--color-brand-light, rgba(37,99,235,0.1)); color: var(--color-brand, #2563eb); }
.cp-role-pip--supporting  { background: var(--color-warning-dim, rgba(245,158,11,0.1)); color: var(--color-warning, #f59e0b); }
.cp-role-pip--minor       { background: var(--app-border); color: var(--app-text-muted); }

/* State pip */
.cp-state-pip {
  display: inline-flex;
  align-items: center;
  padding: 1px 7px;
  border-radius: 999px;
  font-size: 10px;
  font-weight: 600;
  white-space: nowrap;
  line-height: 1.4;
}
.cp-state-pip--calm    { background: var(--color-success-dim, rgba(34,197,94,0.1));  color: var(--color-success, #22c55e); }
.cp-state-pip--active  { background: var(--color-info-dim,    rgba(6,182,212,0.1));  color: var(--color-info,    #06b6d4); }
.cp-state-pip--warning { background: var(--color-warning-dim, rgba(245,158,11,0.1)); color: var(--color-warning, #f59e0b); }
.cp-state-pip--danger  { background: var(--color-danger-dim,  rgba(239,68,68,0.1));  color: var(--color-danger,  #ef4444); }

/* ── Empty ────────────────────────────────────────────────────────── */

.cp-empty {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 10px;
  padding: 24px;
}
.cp-empty-icon { font-size: 32px; opacity: 0.45; line-height: 1; }
.cp-empty-text {
  font-size: 12px;
  color: var(--app-text-muted);
  line-height: 1.65;
  text-align: center;
  margin: 0;
}

/* ── Spin ─────────────────────────────────────────────────────────── */

.cp-spin {
  flex: 1;
  min-height: 0;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}
.cp-spin :deep(.n-spin-content) {
  flex: 1;
  min-height: 0;
  height: 100%;
  display: flex;
  flex-direction: column;
}

/* ── Tabs ─────────────────────────────────────────────────────────── */

.cp-tabs {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

/* NaiveUI tabs layout override */
.cp-tabs :deep(.n-tabs-nav) {
  flex-shrink: 0;
  padding: 0 10px;
  border-bottom: 1px solid var(--plotpilot-split-border);
}

.cp-tabs :deep(.n-tabs-pane-wrapper) {
  flex: 1;
  min-height: 0;
  overflow: hidden;
}

.cp-tabs :deep(.n-tab-pane) {
  height: 100%;
  padding: 0;
}

/* Tab label font */
.cp-tabs :deep(.n-tabs-tab__label) {
  font-size: 12px;
  font-weight: 500;
}

/* ── Pane scroll area ─────────────────────────────────────────────── */

.cp-pane {
  height: 100%;
  overflow-y: auto;
  padding: 10px 12px 16px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  scrollbar-width: thin;
  scrollbar-color: var(--app-border) transparent;
}
.cp-pane::-webkit-scrollbar       { width: 4px; }
.cp-pane::-webkit-scrollbar-track { background: transparent; }
.cp-pane::-webkit-scrollbar-thumb { background: var(--app-border); border-radius: 2px; }

.cp-pane--fill {
  padding: 0;
  overflow: hidden;
}

/* ── Card ─────────────────────────────────────────────────────────── */

.cp-card {
  border-radius: 9px;
  border: 1px solid var(--app-border);
  background: var(--app-surface);
  overflow: hidden;
  flex-shrink: 0;
}

.cp-card--danger-accent  { border-left: 3px solid var(--color-danger,  #ef4444); }
.cp-card--warning-accent { border-left: 3px solid var(--color-warning, #f59e0b); }
.cp-card--voice   { border-left: 3px solid #2080d0; }
.cp-card--wound   { border-left: 3px solid #7c3aed; }
.cp-card--belief  { border-left: 3px solid #d89614; }
.cp-card--taboo   { border-left: 3px solid #c03030; }
.cp-card--debug   { opacity: 0.75; }

.cp-card-hd {
  padding: 7px 10px;
  display: flex;
  align-items: center;
  gap: 6px;
  background: var(--app-page-bg, #fafafa);
  border-bottom: 1px solid var(--app-border);
}

.cp-card-hd--clickable { cursor: pointer; user-select: none; }
.cp-card-hd--clickable:hover { background: var(--app-border); }

.cp-card-lbl {
  font-size: 10px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--app-text-muted);
  flex: 1;
}
.cp-card-lbl--dim { opacity: 0.6; }

.cp-card-bd {
  padding: 9px 11px;
}

/* ── Chevron ──────────────────────────────────────────────────────── */

.cp-chevron {
  flex-shrink: 0;
  font-size: 13px;
  color: var(--app-text-muted);
  transition: transform 0.18s;
  display: inline-block;
  line-height: 1;
}
.cp-chevron--open { transform: rotate(90deg); }

/* ── Chip ─────────────────────────────────────────────────────────── */

.cp-chip {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 18px;
  height: 16px;
  padding: 0 5px;
  border-radius: 8px;
  font-size: 10px;
  font-weight: 700;
  line-height: 1;
}
.cp-chip--muted  { background: var(--app-border); color: var(--app-text-muted); }
.cp-chip--purple { background: rgba(139,92,246,0.1); color: #7c3aed; }

/* ── Empty note ──────────────────────────────────────────────────── */

.cp-empty-note {
  font-size: 11px;
  color: var(--app-text-muted);
  text-align: center;
  padding: 4px 0;
  margin: 0;
}

/* ── 此刻 ─────────────────────────────────────────────────────────── */

.cp-reason {
  margin: 0 0 9px;
  font-size: 12px;
  line-height: 1.7;
  color: var(--app-text-secondary);
  white-space: pre-wrap;
  word-break: break-word;
}

.cp-habit-grid {
  border: 1px solid var(--plotpilot-split-border, rgba(0,0,0,0.07));
  border-radius: 6px;
  overflow: hidden;
  margin-bottom: 8px;
}
.cp-habit-row {
  display: grid;
  grid-template-columns: 40px 1fr;
  font-size: 12px;
  line-height: 1.55;
  border-bottom: 1px solid var(--plotpilot-split-border, rgba(0,0,0,0.06));
}
.cp-habit-row:last-child { border-bottom: none; }
.cp-habit-k {
  padding: 5px 8px;
  font-size: 11px;
  color: var(--app-text-muted);
  background: var(--app-page-bg, #f5f5f5);
  border-right: 1px solid var(--plotpilot-split-border, rgba(0,0,0,0.06));
  display: flex;
  align-items: center;
  flex-shrink: 0;
}
.cp-habit-v { padding: 5px 9px; word-break: break-word; color: var(--app-text-secondary); }

.cp-mask-block {
  display: flex;
  gap: 7px;
  align-items: flex-start;
  padding: 8px 10px;
  border-radius: 7px;
  background: var(--app-page-bg, #fafafa);
  border-left: 3px solid var(--color-brand, #2563eb);
}
.cp-mask-ico { flex-shrink: 0; font-size: 12px; color: var(--color-brand, #2563eb); opacity: 0.6; margin-top: 1px; }
.cp-mask-txt { font-size: 12px; line-height: 1.7; color: var(--app-text-secondary); word-break: break-word; }

/* ── 声线 ─────────────────────────────────────────────────────────── */

.cp-voice-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
  margin-bottom: 6px;
}
.cp-voice-attr {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 3px 8px;
  border-radius: 5px;
  background: rgba(32,128,208,0.07);
  border: 1px solid rgba(32,128,208,0.15);
  font-size: 11px;
}
.cp-va-k { color: var(--app-text-muted); font-weight: 600; }
.cp-va-v { color: var(--app-text-secondary); }

.cp-vp-row {
  display: flex;
  align-items: flex-start;
  gap: 7px;
  margin-top: 5px;
}
.cp-vp-label {
  flex-shrink: 0;
  font-size: 10px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--app-text-muted);
  padding-top: 3px;
  min-width: 36px;
}
.cp-voice-pills { display: flex; flex-wrap: wrap; gap: 4px; }
.cp-vp {
  display: inline-flex;
  align-items: center;
  padding: 2px 7px;
  border-radius: 999px;
  font-size: 11px;
}
.cp-vp--phrase { background: rgba(37,99,235,0.06); color: var(--color-brand, #2563eb); border: 1px solid rgba(37,99,235,0.15); }
.cp-vp--meta   { background: rgba(139,92,246,0.06); color: #7c3aed; border: 1px solid rgba(139,92,246,0.15); }

/* ── 创伤反射 ─────────────────────────────────────────────────────── */

.cp-wounds { display: flex; flex-direction: column; gap: 8px; }

.cp-wound {
  padding: 8px 10px;
  border-radius: 7px;
  background: rgba(124,58,237,0.03);
  border: 1px solid rgba(124,58,237,0.12);
}

.cp-wound-line {
  display: flex;
  align-items: flex-start;
  gap: 7px;
}
.cp-wound-badge {
  flex-shrink: 0;
  font-size: 10px;
  font-weight: 700;
  padding: 1px 5px;
  border-radius: 3px;
  letter-spacing: 0.04em;
}
.cp-wound-badge--t { background: rgba(245,158,11,0.1); color: var(--color-warning, #f59e0b); }
.cp-wound-badge--r { background: rgba(239,68,68,0.1);  color: var(--color-danger,  #ef4444); }

.cp-wound-txt { font-size: 12px; color: var(--app-text-secondary); line-height: 1.5; word-break: break-word; }
.cp-wound-arrow { font-size: 11px; color: var(--app-text-muted); margin: 2px 0 2px 7px; }
.cp-wound-bg { margin: 5px 0 0; font-size: 11px; color: var(--app-text-muted); line-height: 1.6; word-break: break-word; }

/* ── 成长记忆 ─────────────────────────────────────────────────────── */

.cp-tl { display: flex; flex-direction: column; gap: 0; }

.cp-tl-item {
  display: flex;
  gap: 10px;
  position: relative;
  padding-bottom: 12px;
}
.cp-tl-item:last-child { padding-bottom: 0; }

.cp-tl-node {
  flex-shrink: 0;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--color-brand, #2563eb);
  margin-top: 5px;
  position: relative;
  z-index: 1;
}

.cp-tl-item:not(:last-child) .cp-tl-node::after {
  content: '';
  position: absolute;
  left: 50%;
  top: 100%;
  transform: translateX(-50%);
  width: 1px;
  height: calc(100% + 12px);
  background: var(--app-border);
  margin-top: 3px;
}

.cp-tl-content { flex: 1; min-width: 0; }
.cp-tl-meta { display: flex; align-items: center; gap: 6px; margin-bottom: 2px; }
.cp-tl-ch { font-size: 10px; font-weight: 700; color: var(--color-brand, #2563eb); }
.cp-tl-dims { font-size: 10px; color: var(--app-text-muted); }
.cp-tl-event { margin: 0; font-size: 12px; line-height: 1.6; color: var(--app-text-secondary); word-break: break-word; }

/* ── 待校准 ─────────────────────────────────────────────────────── */

.cp-candidates { display: flex; flex-direction: column; gap: 8px; }
.cp-candidate {
  border: 1px solid var(--app-border);
  border-radius: 7px;
  padding: 8px 10px;
  background: var(--app-page-bg, #fafafa);
}
.cp-candidate-meta {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 5px;
}
.cp-confidence {
  margin-left: auto;
  font-size: 10px;
  color: var(--app-text-muted);
  font-variant-numeric: tabular-nums;
}
.cp-candidate-text {
  margin: 0;
  font-size: 12px;
  line-height: 1.65;
  color: var(--app-text-secondary);
  word-break: break-word;
}
.cp-candidate-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 6px;
}

/* ── 档案 ─────────────────────────────────────────────────────────── */

.cp-profiles-bd { display: flex; flex-direction: column; gap: 8px; }

.cp-profile { border-radius: 7px; border: 1px solid var(--app-border); overflow: hidden; }
.cp-profile--hidden { border-color: rgba(139,92,246,0.25); }

.cp-profile-hd {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 5px 10px;
  background: var(--app-page-bg, #fafafa);
  border-bottom: 1px solid var(--app-border);
}
.cp-profile-dot { width: 7px; height: 7px; border-radius: 50%; flex-shrink: 0; }
.cp-profile-lbl { font-size: 11px; font-weight: 600; color: var(--app-text-secondary); }
.cp-profile-lock-note { font-size: 10px; font-weight: 400; color: var(--app-text-muted); margin-left: 4px; }

.cp-prose {
  margin: 0;
  padding: 8px 10px;
  font-size: 12px;
  line-height: 1.75;
  color: var(--app-text-secondary);
  white-space: pre-wrap;
  word-break: break-word;
}

.cp-belief-quote {
  margin: 0;
  padding: 9px 12px;
  font-size: 13px;
  font-weight: 500;
  line-height: 1.7;
  color: var(--app-text-primary);
  font-style: italic;
  word-break: break-word;
  white-space: pre-wrap;
}

.cp-taboos { display: flex; flex-wrap: wrap; gap: 5px; }
.cp-taboo-chip {
  display: inline-flex;
  align-items: center;
  padding: 3px 9px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 600;
  background: var(--color-danger-dim, rgba(239,68,68,0.08));
  color: var(--color-danger, #ef4444);
}

/* ── 调试预览 ─────────────────────────────────────────────────────── */

.cp-debug-note {
  margin: 0 0 6px;
  font-size: 10px;
  color: var(--app-text-muted);
}
.cp-debug-pre {
  margin: 0;
  font-size: 10px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-all;
  color: var(--app-text-secondary);
  background: var(--app-page-bg, #f5f5f5);
  padding: 8px 10px;
  border-radius: 6px;
  max-height: 200px;
  overflow-y: auto;
}
</style>
