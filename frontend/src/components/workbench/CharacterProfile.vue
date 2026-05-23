<template>
  <div class="cp">

    <!-- ── 顶栏 ──────────────────────────────────────────────────── -->
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
        <span v-else class="cp-id-placeholder">角色内核档案</span>
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

    <!-- ── 空状态 ──────────────────────────────────────────────── -->
    <div v-if="!selectedCharacterId" class="cp-empty">
      <div class="cp-empty-icon">🎭</div>
      <p class="cp-empty-text">从左侧点选角色<br>查看内核档案</p>
    </div>

    <!-- ── 主体 ───────────────────────────────────────────────── -->
    <n-spin v-else :show="loading" size="small" class="cp-spin">
      <div class="cp-body">

        <!-- ① 此刻 ───────────────────────────────────────────── -->
        <div class="cp-sec" :class="presentSectionClass">
          <div class="cp-sec-hd" @click="toggle('present')">
            <span class="cp-sec-lbl">此刻</span>
            <span v-if="mentalStateLabel" class="cp-state-pip" :class="mentalStateCssKey">
              {{ mentalStateLabel }}
            </span>
            <span v-else class="cp-state-pip cp-state-pip--calm">平稳</span>
            <span class="cp-chevron" :class="{ 'cp-chevron--open': sectionOpen.present }">›</span>
          </div>
          <div v-show="sectionOpen.present" class="cp-sec-bd">
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
            <div v-if="!hasMentalContent" class="cp-empty-note">暂无心理状态记录</div>
          </div>
        </div>

        <!-- ② 人设两面 ───────────────────────────────────────── -->
        <div v-if="hasProfiles" class="cp-sec">
          <div class="cp-sec-hd" @click="toggle('profiles')">
            <span class="cp-sec-lbl">人设两面</span>
            <span v-if="isHiddenLocked" class="pp-chip pp-chip--muted" style="font-size:10px;padding:1px 6px">
              🔒 第{{ bibleChar?.reveal_chapter }}章后
            </span>
            <span class="cp-chevron" :class="{ 'cp-chevron--open': sectionOpen.profiles }">›</span>
          </div>
          <div v-show="sectionOpen.profiles" class="cp-sec-bd cp-profiles-bd">
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
                  <span v-if="isHiddenLocked" class="cp-profile-lock-note">
                    （第{{ bibleChar?.reveal_chapter }}章前对读者保密）
                  </span>
                </span>
              </div>
              <p class="cp-prose">{{ bibleChar.hidden_profile }}</p>
            </div>
          </div>
        </div>

        <!-- ③ 性格锚点 ───────────────────────────────────────── -->
        <div class="cp-sec">
          <div class="cp-sec-hd" @click="toggle('anchors')">
            <span class="cp-sec-lbl">性格锚点</span>
            <span
              v-if="(psycheDetail?.trauma_count ?? 0) > 0"
              class="pp-chip pp-chip--warning"
              style="font-size:10px;padding:1px 6px"
            >
              转折 ×{{ psycheDetail?.trauma_count }}
            </span>
            <span class="cp-chevron" :class="{ 'cp-chevron--open': sectionOpen.anchors }">›</span>
          </div>
          <div v-show="sectionOpen.anchors" class="cp-sec-bd cp-anchors-bd">

            <!-- 核心信念 -->
            <div v-if="activeBelief" class="cp-ab cp-ab--belief">
              <div class="cp-ab-tag" style="color: #d89614">核心信念</div>
              <blockquote class="cp-belief-quote">{{ activeBelief }}</blockquote>
            </div>

            <!-- 行为禁区 -->
            <div v-if="activeTaboos.length > 0" class="cp-ab cp-ab--taboo">
              <div class="cp-ab-tag" style="color: #c03030">行为禁区</div>
              <div class="cp-taboos">
                <span v-for="(t, i) in activeTaboos" :key="i" class="cp-taboo-chip">
                  ⛔ {{ t }}
                </span>
              </div>
            </div>

            <!-- 声线印记 -->
            <div v-if="hasVoice" class="cp-ab cp-ab--voice">
              <div class="cp-ab-tag" style="color: #2080d0">声线印记</div>
              <div v-if="voiceAttrs.length > 0" class="cp-voice-grid">
                <span v-for="a in voiceAttrs" :key="a.k" class="cp-voice-attr">
                  <span class="cp-va-k">{{ a.k }}</span>
                  <span class="cp-va-v">{{ a.v }}</span>
                </span>
              </div>
              <div v-if="voiceAttrs.length === 0 && voiceCatchphrases.length === 0 && voiceMetaphors.length === 0 && psycheDetail?.voice_tag?.trim()" class="cp-voice-grid">
                <span class="cp-voice-attr">
                  <span class="cp-va-k">综合</span>
                  <span class="cp-va-v">{{ psycheDetail.voice_tag }}</span>
                </span>
              </div>
              <div v-if="voiceCatchphrases.length > 0" class="cp-vp-row">
                <span class="cp-vp-label">口头禅</span>
                <div class="cp-voice-pills">
                  <span v-for="(p, i) in voiceCatchphrases" :key="i" class="cp-vp cp-vp--phrase">
                    「{{ p }}」
                  </span>
                </div>
              </div>
              <div v-if="voiceMetaphors.length > 0" class="cp-vp-row">
                <span class="cp-vp-label">意象</span>
                <div class="cp-voice-pills">
                  <span v-for="(m, i) in voiceMetaphors" :key="i" class="cp-vp cp-vp--meta">
                    {{ m }}
                  </span>
                </div>
              </div>
            </div>

            <!-- 创伤反射 -->
            <div v-if="activeWounds.length > 0" class="cp-ab cp-ab--wound">
              <div class="cp-ab-tag" style="color: #7c3aed">创伤反射</div>
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

            <div
              v-if="!activeBelief && activeTaboos.length === 0 && !hasVoice && activeWounds.length === 0"
              class="cp-empty-note"
            >
              暂无锚点数据 · 可点击顶栏 ↻ 从描述自动提取
            </div>

          </div>
        </div>

        <!-- ④ 成长地质图 ──────────────────────────────────────── -->
        <div v-if="narrativeTimeline.length > 0" class="cp-sec">
          <div class="cp-sec-hd" @click="toggle('timeline')">
            <span class="cp-sec-lbl">成长地质图</span>
            <span class="pp-chip pp-chip--muted" style="font-size:10px;padding:1px 6px">
              {{ narrativeTimeline.length }}次转变
            </span>
            <span class="cp-chevron" :class="{ 'cp-chevron--open': sectionOpen.timeline }">›</span>
          </div>
          <div v-show="sectionOpen.timeline" class="cp-sec-bd cp-tl-bd">
            <ol class="cp-tl">
              <li v-for="(e, i) in narrativeTimeline" :key="i" class="cp-tl-item">
                <div class="cp-tl-node" />
                <div class="cp-tl-content">
                  <div class="cp-tl-meta">
                    <span class="cp-tl-ch">第{{ e.trigger_chapter }}章</span>
                    <span v-if="e.narrativeDesc" class="cp-tl-dims">{{ e.narrativeDesc }}</span>
                  </div>
                  <p class="cp-tl-event">{{ e.trigger_event || '（未命名事件）' }}</p>
                </div>
              </li>
            </ol>
          </div>
        </div>

        <!-- ⑤ 一致性校验 ──────────────────────────────────────── -->
        <div class="cp-sec">
          <div class="cp-sec-hd" @click="toggle('validator')">
            <span class="cp-sec-lbl">一致性校验</span>
            <span class="pp-chip pp-chip--brand" style="font-size:10px;padding:1px 6px">工具</span>
            <span class="cp-chevron" :class="{ 'cp-chevron--open': sectionOpen.validator }">›</span>
          </div>
          <div v-show="sectionOpen.validator" class="cp-sec-bd">
            <p class="cp-vtor-hint">描述角色将要做的事，验证是否符合其性格内核。</p>
            <n-input
              v-model:value="validateInput"
              type="textarea"
              :autosize="{ minRows: 2, maxRows: 4 }"
              placeholder="例：李明决定向曾经的死敌低头求和…"
              size="small"
              class="cp-vtor-input"
              @keydown.ctrl.enter.prevent="validateBehavior"
            />
            <n-button
              size="small"
              type="primary"
              ghost
              block
              :loading="validating"
              style="margin-top: 7px"
              @click="validateBehavior"
            >
              校验一致性
            </n-button>
            <div v-if="validateResult" class="cp-vr" :class="validateResult.valid ? 'cp-vr--ok' : 'cp-vr--warn'">
              <div class="cp-vr-verdict">
                <span class="cp-vr-icon">{{ validateResult.valid ? '✓' : '⚠' }}</span>
                <span>{{ validateResult.valid ? '行为符合角色内核' : '存在一致性风险' }}</span>
              </div>
              <ul v-if="validateResult.warnings.length > 0" class="cp-vr-list">
                <li v-for="w in validateResult.warnings" :key="w">{{ w }}</li>
              </ul>
              <template v-if="validateResult.suggestions.length > 0">
                <p class="cp-vr-sugg-hd">建议调整方向：</p>
                <ul class="cp-vr-list cp-vr-list--sugg">
                  <li v-for="s in validateResult.suggestions" :key="s">{{ s }}</li>
                </ul>
              </template>
            </div>
          </div>
        </div>

        <!-- ⑥ 调试·装配预览 ──────────────────────────────────── -->
        <div v-if="injectPreviewBody" class="cp-sec cp-sec--debug">
          <div class="cp-sec-hd" @click="toggle('debug')">
            <span class="cp-sec-lbl cp-sec-lbl--dim">调试·装配预览</span>
            <span class="cp-chevron" :class="{ 'cp-chevron--open': sectionOpen.debug }">›</span>
          </div>
          <div v-show="sectionOpen.debug" class="cp-sec-bd">
            <p class="cp-debug-note">Context 层注入预览，与写章 prompt 同构</p>
            <pre class="cp-debug-pre">{{ injectPreviewBody }}</pre>
          </div>
        </div>

      </div>
    </n-spin>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, computed, reactive } from 'vue'
import { useMessage } from 'naive-ui'
import { RefreshOutline, SyncOutline } from '@vicons/ionicons5'
import {
  characterPsycheApi,
  type CharacterPsycheDetailDTO,
  type ValidateBehaviorResponse,
} from '@/api/engineCore'
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

// ── Core State ────────────────────────────────────────────────────
const loading    = ref(false)
const extracting = ref(false)
const validating = ref(false)

const characterName = ref('')
const bibleChar   = ref<CharacterDTO | null>(null)
const psycheDetail = ref<CharacterPsycheDetailDTO | null>(null)

const validateInput  = ref('')
const validateResult = ref<ValidateBehaviorResponse | null>(null)

// ── Section Toggle ────────────────────────────────────────────────
const sectionOpen = reactive<Record<string, boolean>>({
  present:   true,
  profiles:  true,
  anchors:   true,
  timeline:  false,
  validator: false,
  debug:     false,
})
function toggle(k: string) { sectionOpen[k] = !sectionOpen[k] }

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
const avatarColor  = computed(() => ROLE_COLORS[roleKey.value] ?? ROLE_COLORS.MINOR)
const avatarInitial = computed(() => characterName.value.slice(0, 1) || '?')
const roleLabelText = computed(() => ROLE_LABELS[roleKey.value] ?? roleKey.value)
const roleCssKey    = computed(() => roleKey.value.toLowerCase())

// ── Mental State ──────────────────────────────────────────────────
const mentalStateLabel = computed(() => {
  const raw = (bibleChar.value?.mental_state ?? '').trim()
  return raw && raw.toUpperCase() !== 'NORMAL' ? raw : ''
})

const mentalStateCssKey = computed((): string => {
  const v = mentalStateLabel.value
  if (!v) return ''
  if (/焦虑|恐惧|崩溃|危机|绝望/.test(v)) return 'cp-state-pip--danger'
  if (/愤怒|悲伤|痛苦|压抑/.test(v))      return 'cp-state-pip--warning'
  return 'cp-state-pip--active'
})

const presentSectionClass = computed(() => {
  const k = mentalStateCssKey.value
  if (k === 'cp-state-pip--danger')  return 'cp-sec--danger-accent'
  if (k === 'cp-state-pip--warning') return 'cp-sec--warning-accent'
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

// Voice Profile
interface VoiceShape {
  style?: string
  sentence_pattern?: string
  speech_tempo?: string
  punctuation?: unknown[]
  metaphors?: unknown[]
  catchphrases?: unknown[]
}

const voiceObj = computed((): VoiceShape | null => {
  const vp = bibleChar.value?.voice_profile
  return (vp && typeof vp === 'object') ? (vp as VoiceShape) : null
})

const TEMPO_MAP: Record<string, string> = { fast: '急促', normal: '平稳', slow: '舒缓' }

const voiceAttrs = computed((): Array<{ k: string; v: string }> => {
  const v = voiceObj.value
  if (!v) return []
  const out: Array<{ k: string; v: string }> = []
  if (v.style)            out.push({ k: '风格', v: String(v.style) })
  if (v.sentence_pattern) out.push({ k: '句式', v: String(v.sentence_pattern) })
  if (v.speech_tempo) {
    const raw = String(v.speech_tempo)
    out.push({ k: '节奏', v: TEMPO_MAP[raw] ?? raw })
  }
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

// Wounds
interface WoundShape {
  description?: string
  trigger?: string
  effect?: string
}

const activeWounds = computed((): WoundShape[] => {
  const arr = bibleChar.value?.active_wounds
  if (Array.isArray(arr) && arr.length > 0) {
    return (arr as WoundShape[]).filter(w => w.trigger || w.effect || w.description)
  }
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
  (psycheDetail.value?.evolution_timeline ?? []).map(e => ({
    trigger_chapter: e.trigger_chapter,
    trigger_event:   e.trigger_event ?? '',
    narrativeDesc:   (e.changed_fields ?? []).map(f => FIELD_NARRATIVE[f] ?? f).join('，'),
  })),
)

// ── Inject Preview ─────────────────────────────────────────────────
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
    parts.push((rc == null || desk == null || desk >= rc)
      ? `[隐藏面] ${hp}`
      : `[隐藏面] 第 ${rc} 章后揭示`)
  }

  const ms = (c.mental_state ?? '').trim()
  if (ms && ms !== 'NORMAL') {
    const reason = (c.mental_state_reason ?? '').trim()
    parts.push(`心理: ${ms}` + (reason ? `（${reason}）` : ''))
  }

  if ((c.verbal_tic ?? '').trim())    parts.push(`口头禅: ${c.verbal_tic}`)
  if ((c.idle_behavior ?? '').trim()) parts.push(`习惯动作: ${c.idle_behavior}`)

  if (activeBelief.value)          parts.push(`T0·信念: ${activeBelief.value.slice(0, 260)}`)
  if (activeTaboos.value.length)   parts.push(`T0·禁忌: ${activeTaboos.value.join('；').slice(0, 140)}`)

  const wStr = activeWounds.value
    .map(w => (w.trigger && w.effect) ? `${w.trigger} → ${w.effect}` : w.description ?? '')
    .filter(Boolean).join('；')
  if (wStr) parts.push(`T0·创伤: ${wStr.slice(0, 140)}`)

  const vStr = voiceAttrs.value.map(a => `${a.k}·${a.v}`).join('；') ||
               (psycheDetail.value?.voice_tag ?? '').trim()
  if (vStr) parts.push(`T0·声线: ${vStr.slice(0, 140)}`)

  return parts.join('\n')
})

// ── Actions ───────────────────────────────────────────────────────
async function loadCharacterData() {
  if (!props.selectedCharacterId) {
    bibleChar.value = null
    psycheDetail.value = null
    characterName.value = ''
    return
  }
  loading.value = true
  try {
    const bible = await bibleApi.getBible(props.slug)
    const char  = bible.characters?.find(x => x.id === props.selectedCharacterId) ?? null
    bibleChar.value  = char
    characterName.value = char?.name ?? ''
    psycheDetail.value = characterName.value
      ? await characterPsycheApi.get(props.slug, characterName.value).catch(() => null)
      : null
  } catch (err: unknown) {
    message.error(err instanceof Error ? err.message : '加载角色数据失败')
  } finally {
    loading.value = false
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

async function validateBehavior() {
  if (!characterName.value || !validateInput.value.trim()) return
  validating.value = true
  validateResult.value = null
  try {
    validateResult.value = await characterPsycheApi.validate(
      props.slug,
      characterName.value,
      { action: validateInput.value.trim() },
    )
  } catch {
    message.error('校验服务暂时不可用')
  } finally {
    validating.value = false
  }
}

watch(() => props.selectedCharacterId, () => {
  validateResult.value = null
  validateInput.value = ''
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
  padding: 10px 12px;
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
  letter-spacing: 0;
  line-height: 1;
  user-select: none;
  text-shadow: 0 1px 2px rgba(0,0,0,0.18);
}

.cp-id-text {
  min-width: 0;
  flex: 1;
}

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

.cp-role-pip--protagonist {
  background: var(--color-brand-light, rgba(37,99,235,0.1));
  color: var(--color-brand, #2563eb);
}
.cp-role-pip--supporting {
  background: var(--color-warning-dim, rgba(245,158,11,0.1));
  color: var(--color-warning, #f59e0b);
}
.cp-role-pip--minor {
  background: var(--app-border);
  color: var(--app-text-muted);
}

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

.cp-state-pip--calm {
  background: var(--color-success-dim, rgba(34,197,94,0.1));
  color: var(--color-success, #22c55e);
}
.cp-state-pip--active {
  background: var(--color-info-dim, rgba(6,182,212,0.1));
  color: var(--color-info, #06b6d4);
}
.cp-state-pip--warning {
  background: var(--color-warning-dim, rgba(245,158,11,0.1));
  color: var(--color-warning, #f59e0b);
}
.cp-state-pip--danger {
  background: var(--color-danger-dim, rgba(239,68,68,0.1));
  color: var(--color-danger, #ef4444);
}

.cp-topbar-btns {
  display: flex;
  gap: 2px;
  flex-shrink: 0;
}

/* ── Empty state ─────────────────────────────────────────────────── */

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

/* ── Spin & Body ──────────────────────────────────────────────────── */

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

.cp-body {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 10px 12px 16px;
  display: flex;
  flex-direction: column;
  gap: 7px;
  scrollbar-width: thin;
  scrollbar-color: var(--app-border) transparent;
}

.cp-body::-webkit-scrollbar { width: 4px; }
.cp-body::-webkit-scrollbar-track { background: transparent; }
.cp-body::-webkit-scrollbar-thumb { background: var(--app-border); border-radius: 2px; }

/* ── Section base ─────────────────────────────────────────────────── */

.cp-sec {
  border-radius: var(--app-radius-md, 10px);
  background: var(--app-surface);
  border: 1px solid var(--app-border);
  overflow: hidden;
}

.cp-sec--danger-accent  { border-left: 3px solid var(--color-danger,  #ef4444); }
.cp-sec--warning-accent { border-left: 3px solid var(--color-warning, #f59e0b); }
.cp-sec--debug { opacity: 0.8; }

.cp-sec-hd {
  padding: 8px 10px;
  border-bottom: 1px solid transparent;
  display: flex;
  align-items: center;
  gap: 6px;
  min-height: 32px;
  cursor: pointer;
  user-select: none;
  transition: background 0.12s;
}

.cp-sec-hd:hover { background: var(--app-page-bg, #f5f5f5); }
.cp-sec[class*='--accent'] .cp-sec-hd { border-bottom-color: var(--app-border); }

.cp-sec-lbl {
  font-size: 11px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.07em;
  color: var(--app-text-muted);
  flex: 1;
  min-width: 0;
}

.cp-sec-lbl--dim { opacity: 0.65; }

.cp-chevron {
  flex-shrink: 0;
  font-size: 13px;
  color: var(--app-text-muted);
  transition: transform 0.18s;
  display: inline-block;
  line-height: 1;
}
.cp-chevron--open { transform: rotate(90deg); }

.cp-sec-bd {
  padding: 10px 12px;
  border-top: 1px solid var(--app-border);
}

.cp-empty-note {
  font-size: 11px;
  color: var(--app-text-muted);
  text-align: center;
  padding: 2px 0;
}

/* ── ① 此刻 ──────────────────────────────────────────────────────── */

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

.cp-habit-v {
  padding: 5px 9px;
  word-break: break-word;
  color: var(--app-text-secondary);
}

.cp-mask-block {
  display: flex;
  gap: 7px;
  align-items: flex-start;
  padding: 8px 10px;
  border-radius: 7px;
  background: var(--app-page-bg, #fafafa);
  border-left: 3px solid var(--color-brand, #2563eb);
}

.cp-mask-ico {
  flex-shrink: 0;
  font-size: 12px;
  color: var(--color-brand, #2563eb);
  opacity: 0.6;
  margin-top: 1px;
}

.cp-mask-txt {
  font-size: 12px;
  line-height: 1.7;
  color: var(--app-text-secondary);
  word-break: break-word;
}

/* ── ② 人设两面 ───────────────────────────────────────────────────── */

.cp-profiles-bd {
  display: flex;
  flex-direction: column;
  gap: 9px;
}

.cp-profile {
  border-radius: 7px;
  border: 1px solid var(--app-border);
  overflow: hidden;
}

.cp-profile--hidden {
  border-color: rgba(139, 92, 246, 0.25);
}

.cp-profile-hd {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 10px;
  background: var(--app-page-bg, #fafafa);
  border-bottom: 1px solid var(--app-border);
}

.cp-profile-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  flex-shrink: 0;
}

.cp-profile-lbl {
  font-size: 11px;
  font-weight: 600;
  color: var(--app-text-secondary);
}

.cp-profile-lock-note {
  font-size: 10px;
  font-weight: 400;
  color: var(--app-text-muted);
  margin-left: 4px;
}

.cp-prose {
  margin: 0;
  padding: 8px 10px;
  font-size: 12px;
  line-height: 1.75;
  color: var(--app-text-secondary);
  white-space: pre-wrap;
  word-break: break-word;
}

/* ── ③ 性格锚点 ───────────────────────────────────────────────────── */

.cp-anchors-bd {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.cp-ab {
  border-radius: 7px;
  overflow: hidden;
  border: 1px solid var(--app-border);
}

.cp-ab--belief { border-left: 3px solid #d89614; }
.cp-ab--taboo  { border-left: 3px solid #c03030; }
.cp-ab--voice  { border-left: 3px solid #2080d0; }
.cp-ab--wound  { border-left: 3px solid #7c3aed; }

.cp-ab-tag {
  padding: 5px 10px;
  font-size: 10px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.07em;
  background: var(--app-page-bg, #fafafa);
  border-bottom: 1px solid var(--app-border);
}

/* Core Belief */

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

/* Taboos */

.cp-taboos {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
  padding: 8px 10px;
}

.cp-taboo-chip {
  display: inline-flex;
  align-items: center;
  padding: 3px 9px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 600;
  background: var(--color-danger-dim, rgba(239,68,68,0.08));
  color: var(--color-danger, #ef4444);
  border: 1px solid rgba(239,68,68,0.2);
  white-space: nowrap;
}

/* Voice Fingerprint */

.cp-voice-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
  padding: 8px 10px 0;
}

.cp-voice-attr {
  display: inline-flex;
  align-items: center;
  border-radius: 6px;
  overflow: hidden;
  border: 1px solid var(--app-border);
  font-size: 11px;
}

.cp-va-k {
  padding: 2px 6px;
  background: var(--app-page-bg, #f5f5f5);
  color: var(--app-text-muted);
  font-weight: 600;
  border-right: 1px solid var(--app-border);
}

.cp-va-v {
  padding: 2px 8px;
  color: var(--color-brand, #2563eb);
  font-weight: 500;
  background: var(--color-brand-light, rgba(37,99,235,0.05));
}

.cp-vp-row {
  display: flex;
  align-items: flex-start;
  gap: 7px;
  padding: 7px 10px 0;
}

.cp-vp-label {
  flex-shrink: 0;
  font-size: 10px;
  font-weight: 700;
  color: var(--app-text-muted);
  padding-top: 3px;
  min-width: 32px;
}

.cp-voice-pills {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.cp-vp {
  display: inline-flex;
  align-items: center;
  padding: 2px 8px;
  border-radius: 5px;
  font-size: 11px;
  white-space: nowrap;
}

.cp-vp--phrase {
  background: rgba(32, 128, 208, 0.08);
  color: #2080d0;
  border: 1px solid rgba(32, 128, 208, 0.2);
  font-style: italic;
}

.cp-vp--meta {
  background: var(--app-border);
  color: var(--app-text-secondary);
  border: 1px solid transparent;
}

.cp-ab--voice .cp-vp-row:last-child { padding-bottom: 8px; }
.cp-ab--voice .cp-voice-grid:not(:has(+ .cp-vp-row)) { padding-bottom: 8px; }

/* Wounds */

.cp-wounds {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 8px 10px;
}

.cp-wound {
  background: var(--app-page-bg, #fafafa);
  border-radius: 7px;
  border: 1px solid var(--app-border);
  overflow: hidden;
  padding: 0;
}

.cp-wound-line {
  display: flex;
  align-items: center;
  gap: 7px;
  padding: 6px 10px;
}

.cp-wound-line--t { background: rgba(124, 58, 237, 0.04); }
.cp-wound-line--r { background: rgba(124, 58, 237, 0.07); }

.cp-wound-badge {
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  padding: 1px 6px;
  border-radius: 4px;
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.05em;
}

.cp-wound-badge--t {
  background: rgba(124, 58, 237, 0.12);
  color: #7c3aed;
}

.cp-wound-badge--r {
  background: rgba(124, 58, 237, 0.2);
  color: #7c3aed;
}

.cp-wound-txt {
  font-size: 12px;
  line-height: 1.55;
  color: var(--app-text-secondary);
  word-break: break-word;
  flex: 1;
}

.cp-wound-arrow {
  text-align: center;
  font-size: 14px;
  color: var(--color-purple, #8b5cf6);
  opacity: 0.5;
  padding: 1px 10px;
  border-left: 2px dashed rgba(124, 58, 237, 0.15);
  border-right: 2px dashed rgba(124, 58, 237, 0.15);
  background: rgba(124, 58, 237, 0.03);
}

.cp-wound-bg {
  margin: 0;
  padding: 4px 10px 6px;
  font-size: 10px;
  line-height: 1.5;
  color: var(--app-text-muted);
  font-style: italic;
  border-top: 1px dashed var(--app-border);
  word-break: break-word;
}

/* ── ④ 成长地质图 ─────────────────────────────────────────────────── */

.cp-tl-bd { padding-top: 8px; padding-bottom: 8px; }

.cp-tl {
  list-style: none;
  margin: 0;
  padding: 0;
  position: relative;
  display: flex;
  flex-direction: column;
}

.cp-tl::before {
  content: '';
  position: absolute;
  left: 8px;
  top: 10px;
  bottom: 10px;
  width: 1px;
  background: var(--app-border);
}

.cp-tl-item {
  display: flex;
  gap: 10px;
  padding: 5px 0;
  position: relative;
}

.cp-tl-node {
  flex-shrink: 0;
  width: 17px;
  height: 17px;
  border-radius: 50%;
  background: var(--app-surface);
  border: 2px solid var(--color-purple, #8b5cf6);
  margin-top: 1px;
  position: relative;
  z-index: 1;
}

.cp-tl-content {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 3px;
  padding-bottom: 4px;
}

.cp-tl-meta {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}

.cp-tl-ch {
  font-size: 11px;
  font-weight: 700;
  color: var(--color-purple, #8b5cf6);
}

.cp-tl-dims {
  font-size: 10px;
  color: var(--app-text-muted);
  background: var(--app-border);
  padding: 1px 6px;
  border-radius: 4px;
}

.cp-tl-event {
  margin: 0;
  font-size: 12px;
  line-height: 1.55;
  color: var(--app-text-secondary);
  word-break: break-word;
}

/* ── ⑤ 一致性校验 ─────────────────────────────────────────────────── */

.cp-vtor-hint {
  margin: 0 0 8px;
  font-size: 11px;
  line-height: 1.55;
  color: var(--app-text-muted);
}

.cp-vtor-input { width: 100%; }

.cp-vr {
  margin-top: 10px;
  border-radius: 8px;
  overflow: hidden;
  border: 1px solid var(--app-border);
  font-size: 12px;
}

.cp-vr--ok  { border-color: rgba(34, 197, 94, 0.35); }
.cp-vr--warn { border-color: rgba(245, 158, 11, 0.35); }

.cp-vr-verdict {
  display: flex;
  align-items: center;
  gap: 7px;
  padding: 8px 12px;
  font-weight: 600;
  font-size: 12px;
}

.cp-vr--ok   .cp-vr-verdict { background: var(--color-success-dim, rgba(34,197,94,0.08)); color: var(--color-success, #22c55e); }
.cp-vr--warn .cp-vr-verdict { background: var(--color-warning-dim, rgba(245,158,11,0.08)); color: var(--color-warning, #f59e0b); }

.cp-vr-icon { font-size: 14px; }

.cp-vr-list {
  margin: 0;
  padding: 7px 12px 7px 26px;
  display: flex;
  flex-direction: column;
  gap: 3px;
  border-top: 1px solid var(--app-border);
}

.cp-vr-list li {
  line-height: 1.55;
  color: var(--app-text-secondary);
}

.cp-vr-list--sugg li { color: var(--color-brand, #2563eb); }

.cp-vr-sugg-hd {
  margin: 0;
  padding: 5px 12px 0;
  font-size: 11px;
  font-weight: 600;
  color: var(--app-text-muted);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

/* ── ⑥ 调试预览 ──────────────────────────────────────────────────── */

.cp-debug-note {
  margin: 0 0 7px;
  font-size: 10px;
  line-height: 1.45;
  color: var(--app-text-muted);
}

.cp-debug-pre {
  margin: 0;
  padding: 8px 10px;
  font-size: 11px;
  line-height: 1.5;
  font-family: ui-monospace, 'Cascadia Code', 'SF Mono', Menlo, Consolas, monospace;
  white-space: pre-wrap;
  word-break: break-word;
  background: var(--app-page-bg, #fafafa);
  border-radius: 6px;
  border: 1px solid var(--plotpilot-split-border, rgba(0,0,0,0.08));
  max-height: min(40vh, 280px);
  overflow-y: auto;
}
</style>
