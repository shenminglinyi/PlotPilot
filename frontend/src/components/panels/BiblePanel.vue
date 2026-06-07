<template>
  <div class="bible-panel pp-panel">

    <!-- ── Header ──────────────────────────────── -->
    <header class="pp-panel-header">
      <div class="pp-panel-header-main">
        <div class="bible-title-row">
          <div class="wb-icon-badge" style="background:#4f46e5">
            <n-icon size="14"><DocumentTextOutline /></n-icon>
          </div>
          <span class="pp-panel-title">作品设定</span>
          <n-tag size="small" round :bordered="false" class="bible-badge">Story Bible</n-tag>
        </div>
        <div v-if="biblePanelDataReady" class="bible-header-stats">
          <span
            class="pp-chip"
            :class="stats.premiseOk ? 'pp-chip--success' : 'pp-chip--muted'"
            style="font-size:10px"
          >梗概 {{ stats.premiseOk ? '✓ 已填' : '待填' }}</span>
          <span
            class="pp-chip"
            :class="stats.styleOk ? 'pp-chip--success' : 'pp-chip--muted'"
            style="font-size:10px"
          >文风 {{ stats.styleOk ? '✓ 已填' : '待填' }}</span>
        </div>
        <div v-else class="bible-header-stats">
          <span class="pp-chip pp-chip--muted" style="font-size:10px;opacity:.45">梗概 …</span>
          <span class="pp-chip pp-chip--muted" style="font-size:10px;opacity:.45">文风 …</span>
        </div>
      </div>
      <div class="pp-panel-actions">
        <n-button size="small" secondary :loading="generating" @click="generateBible" title="用 AI 根据小说标题重新生成设定">
          ✦ AI 生成
        </n-button>
        <n-button size="small" type="primary" :loading="saving" @click="save">保存</n-button>
      </div>
    </header>

    <!-- ── Scrollable body ──────────────────────── -->
    <div class="pp-panel-content bible-body">

      <!-- 创作契约 -->
      <div v-if="hasBookLock" class="pp-section">
        <div class="pp-section-header">
          <div class="wb-icon-badge" style="background:#6366f1">
            <n-icon size="14"><LockClosedOutline /></n-icon>
          </div>
          <span class="pp-section-label">创作契约</span>
          <n-tag size="tiny" :bordered="false" type="info">引导锁定</n-tag>
          <n-button
            v-if="hasStyleNotesDetail"
            size="tiny"
            secondary
            @click="openStylePresetModal"
            style="margin-left:auto"
          >更换文风</n-button>
        </div>
        <div class="pp-section-body">
          <div class="bible-contract-grid">
            <div v-for="card in lockSummaryCards" :key="card.key" class="bible-contract-card">
              <span class="bible-contract-card__k">{{ card.label }}</span>
              <span class="bible-contract-card__v">{{ card.value }}</span>
            </div>
          </div>

          <div v-if="lockDirectiveItems.length" class="bible-directives">
            <div v-for="item in lockDirectiveItems" :key="item.key" class="bible-directive">
              <span class="bible-directive__k">{{ item.label }}</span>
              <span class="bible-directive__v">{{ item.value }}</span>
            </div>
          </div>

          <!-- 文风公约卡片 -->
          <div v-if="hasStyleNotesDetail" class="bible-style-card">
            <div class="bible-style-card-header">
              <div class="bible-style-icon">{{ stylePresetIcon }}</div>
              <div class="bible-style-info">
                <div class="bible-style-label">
                  <span>{{ stylePresetTag.label }}</span>
                  <span class="bible-style-summary">{{ styleSummary }}</span>
                </div>
                <n-tag
                  :type="stylePresetTag.tagType"
                  size="small"
                  :bordered="false"
                  style="font-size:10px"
                >
                  {{ stylePresetTag.matched ? '内置模板' : '自定义公约' }}
                </n-tag>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- 梗概锁定 -->
      <div class="pp-section">
        <div class="pp-section-header">
          <div class="wb-icon-badge" style="background:#7c3aed">
            <n-icon size="14"><BookmarkOutline /></n-icon>
          </div>
          <span class="pp-section-label">梗概锁定</span>
          <n-button
            size="tiny"
            secondary
            :loading="generatingKnowledge"
            @click="generatePremiseKnowledge"
            style="margin-left:auto"
            title="根据 Bible 生成或刷新梗概锁定"
          >✦ AI 生成</n-button>
        </div>
        <div class="pp-section-body" style="padding-bottom:2px">
          <n-input
            v-model:value="premiseLock"
            type="textarea"
            :autosize="{ minRows: 6, maxRows: 20 }"
            placeholder="主线、不可违背设定、结局走向（防百万字跑篇）…"
            show-count
            :maxlength="24000"
            class="bible-textarea"
          />
        </div>
      </div>

    </div>

    <!-- ── Footer ───────────────────────────────── -->
    <footer class="pp-panel-footer">
      <span class="pp-panel-footer-note">
        <template v-if="biblePanelDataReady">
          {{ stats.premiseOk && stats.styleOk ? '创作契约已就绪' : '梗概或文风公约待完善' }}
        </template>
      </span>
      <n-button size="small" quaternary @click="openJsonModal">JSON 编辑器</n-button>
    </footer>

    <!-- JSON 编辑器弹窗 -->
    <n-modal v-model:show="showJsonModal" preset="card" title="JSON 编辑器" style="width:800px;max-width:90vw">
      <n-space vertical :size="12">
        <n-input
          v-model:value="jsonRaw"
          type="textarea"
          :rows="20"
          placeholder="JSON 格式"
          class="bible-json-input"
        />
        <n-space :size="8">
          <n-button @click="formatJson">格式化</n-button>
          <n-button type="primary" :loading="saving" @click="saveFromJson">保存</n-button>
        </n-space>
      </n-space>
    </n-modal>

    <!-- 文风预设选择弹窗 -->
    <n-modal
      v-model:show="showStylePresetModal"
      preset="card"
      title="选择文风预设"
      style="width:900px;max-width:95vw"
    >
      <StylePresetSelector v-model="selectedStylePresetValue" />
      <template #footer>
        <n-space justify="end" :size="8">
          <n-button @click="showStylePresetModal = false">取消</n-button>
          <n-button type="primary" :loading="saving" @click="applyStylePreset">应用</n-button>
        </n-space>
      </template>
    </n-modal>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, computed, onMounted, onUnmounted } from 'vue'
import { useMessage } from 'naive-ui'
import { DocumentTextOutline, LockClosedOutline, BookmarkOutline } from '@vicons/ionicons5'
import { bibleApi } from '../../api/bible'
import type { CharacterDTO, LocationDTO, TimelineNoteDTO, StyleNoteDTO } from '../../api/bible'
import { knowledgeApi } from '../../api/knowledge'
import { MARKET_STYLE_PRESETS, getMarketStylePresetIcon, matchPresetValue } from '@/constants/marketStylePresets'
import { novelApi } from '@/api/novel'
import { parseGenreWorldFromPremise } from '@/utils/premisePresets'
import { formatApiError, getHttpStatus } from '@/utils/apiError'
import StylePresetSelector from './StylePresetSelector.vue'

const props = withDefaults(
  defineProps<{ slug: string; reloadNonce?: number }>(),
  { reloadNonce: 0 },
)
const message = useMessage()

interface BibleCharacter {
  name: string
  role: string
  traits: string
  arc_note: string
}
interface BibleLocation {
  name: string
  description: string
}

const emptyState = () => ({
  characters: [] as BibleCharacter[],
  locations: [] as BibleLocation[],
  style_notes: '',
})

const state = ref(emptyState())
const jsonRaw = ref('')
const showJsonModal = ref(false)
const showStylePresetModal = ref(false)
const selectedStylePresetValue = ref('')
const saving = ref(false)
const generating = ref(false)
const premiseLock = ref('')
const generatingKnowledge = ref(false)
/** 本作数据是否已从接口合并完成（避免首帧「待补充」→「已填」与下方表单高度连环闪） */
const biblePanelDataReady = ref(false)

/** 并发 load 取消：只应用最后一次 slug 对应的请求结果，避免多块 UI v-if/v-show 交替闪烁 */
let biblePanelLoadSeq = 0

/** 创建书目向导写入的创作契约；文风来自 Bible（只读标签展示） */
const lockedGenre = ref('')
const lockedWorld = ref('')
const lockedStoryStructure = ref('')
const lockedPacingControl = ref('')
const lockedWritingStyle = ref('')
const lockedSpecialRequirements = ref('')
const lockedTargetChapters = ref(0)
const lockedTargetWordsPerChapter = ref(0)
const hasBookLock = computed(() => {
  const g = lockedGenre.value.trim()
  const w = lockedWorld.value.trim()
  const directives = [
    lockedStoryStructure.value,
    lockedPacingControl.value,
    lockedWritingStyle.value,
    lockedSpecialRequirements.value,
  ].some((item) => item.trim() !== '')
  const sty = (state.value.style_notes || '').trim()
  return g !== '' || w !== '' || directives || sty !== '' || lockedTargetChapters.value > 0
})

const hasStyleNotesDetail = computed(() => (state.value.style_notes || '').trim().length > 0)

function compactLine(text: string, max = 96): string {
  const normalized = (text || '').replace(/\s+/g, ' ').trim()
  if (!normalized) return ''
  return normalized.length > max ? `${normalized.slice(0, max)}…` : normalized
}

const lockSummaryCards = computed(() => {
  const cards = [
    { key: 'genre', label: '赛道', value: compactLine(lockedGenre.value, 42) || '未锁定' },
    { key: 'world', label: '世界基调', value: compactLine(lockedWorld.value, 72) || '未锁定' },
  ]
  const chapters = lockedTargetChapters.value
  const words = lockedTargetWordsPerChapter.value
  if (chapters > 0 || words > 0) {
    cards.push({
      key: 'scale',
      label: '体量',
      value: [
        chapters > 0 ? `${chapters} 章` : '',
        words > 0 ? `${words} 字/章` : '',
      ].filter(Boolean).join(' · ') || '未锁定',
    })
  }
  return cards
})

const lockDirectiveItems = computed(() => [
  { key: 'structure', label: '叙事结构', value: compactLine(lockedStoryStructure.value, 110) },
  { key: 'pacing', label: '节奏控制', value: compactLine(lockedPacingControl.value, 110) },
  { key: 'writing', label: '写作规则', value: compactLine(lockedWritingStyle.value, 110) },
  { key: 'requirements', label: '硬性要求', value: compactLine(lockedSpecialRequirements.value, 130) },
].filter((item) => item.value))

const styleSummary = computed(() => compactLine(state.value.style_notes, 88))

/** 文风市场预设：匹配内置模板则显示预设名；未匹配时作为作者自定义公约展示，不暴露内部诊断。 */
const stylePresetTag = computed(() => {
  const t = (state.value.style_notes || '').trim()
  if (!t) {
    return { matched: false, hasText: false, label: '—', tagType: 'default' as const }
  }
  const m = matchPresetValue(t)
  if (m) {
    const p = MARKET_STYLE_PRESETS.find((x) => x.value === m)
    return { matched: true, hasText: true, label: p?.label ?? m, tagType: 'info' as const }
  }
  return {
    matched: false,
    hasText: true,
    label: '文风公约已锁定',
    tagType: 'default' as const,
  }
})

const stylePresetIcon = computed(() => {
  const t = (state.value.style_notes || '').trim()
  if (!t) return '文'
  const m = matchPresetValue(t)
  return getMarketStylePresetIcon(m)
})

const stats = computed(() => {
  const styleOk = (state.value.style_notes || '').trim().length >= 20
  const premiseOk = (premiseLock.value || '').trim().length >= 20
  return { styleOk, premiseOk }
})

const syncJsonFromState = () => {
  jsonRaw.value = JSON.stringify(
    {
      characters: state.value.characters,
      locations: state.value.locations,
      style_notes: state.value.style_notes,
    },
    null,
    2
  )
}

// Convert new API format to old format
const fromApiFormat = (bible: any) => {
  return {
    characters: Array.isArray(bible.characters)
      ? bible.characters.map((c: CharacterDTO) => {
          // Parse description to extract role, traits, arc_note
          const desc = c.description || ''
          const parts = desc.split('\n---\n')
          return {
            name: c.name || '',
            role: parts[0] || '',
            traits: parts[1] || '',
            arc_note: parts[2] || '',
          }
        })
      : [],
    locations: Array.isArray(bible.locations)
      ? bible.locations.map((l: LocationDTO) => ({
          name: l.name || '',
          description: l.description || '',
        }))
      : [],
    style_notes: Array.isArray(bible.style_notes) && bible.style_notes.length > 0
      ? bible.style_notes.map((n: StyleNoteDTO) => n.content).join('\n\n')
      : '',
  }
}

// Convert old format to new API format
const toApiFormat = (data: any) => {
  const characters: CharacterDTO[] = data.characters.map((c: BibleCharacter, i: number) => ({
    id: `char-${i + 1}`,
    name: c.name || '',
    description: [c.role, c.traits, c.arc_note].filter(Boolean).join('\n---\n'),
    relationships: [],
  }))

  const locations: LocationDTO[] = data.locations.map((l: BibleLocation, i: number) => ({
    id: `loc-${i + 1}`,
    name: l.name || '',
    description: l.description || '',
    location_type: 'general',
  }))

  const style_notes: StyleNoteDTO[] = data.style_notes
    ? [
        {
          id: 'style-1',
          category: 'general',
          content: data.style_notes,
        },
      ]
    : []

  return { characters, world_settings: [], locations, timeline_notes: [], style_notes }
}

function styleNotesWithCreationDefault(styleNotes: string): string {
  const t = (styleNotes || '').trim()
  if (t) return styleNotes
  const v = MARKET_STYLE_PRESETS[0]?.value ?? 'xianxia_hot'
  const p = MARKET_STYLE_PRESETS.find((x) => x.value === v)
  return p?.body ?? ''
}

/** 并行阶段内解析 Bible；404 时自动 create 后再拉一次 */
async function fetchBibleStateForPanel(slug: string): Promise<ReturnType<typeof emptyState>> {
  try {
    const bible = await bibleApi.getBible(slug)
    let ui = fromApiFormat(bible)
    if (!matchPresetValue(ui.style_notes) && !(ui.style_notes || '').trim()) {
      ui = { ...ui, style_notes: styleNotesWithCreationDefault('') }
    }
    return ui
  } catch (err: unknown) {
    if (getHttpStatus(err) !== 404) throw err
    try {
      await bibleApi.createBible(slug, `bible-${slug}`)
    } catch {
      message.error('创建设定失败')
      return emptyState()
    }
    const bible = await bibleApi.getBible(slug)
    let ui = fromApiFormat(bible)
    if (!matchPresetValue(ui.style_notes) && !(ui.style_notes || '').trim()) {
      ui = { ...ui, style_notes: styleNotesWithCreationDefault('') }
    }
    return ui
  }
}

const load = async (opts?: { preserveSurface?: boolean }) => {
  const seq = ++biblePanelLoadSeq
  const slug = props.slug
  if (!opts?.preserveSurface) {
    biblePanelDataReady.value = false
  }

  try {
    const [novelRow, knowledgeRow, bibleUi] = await Promise.all([
      novelApi.getNovel(slug).catch(() => null),
      knowledgeApi.getKnowledge(slug).catch(() => ({ premise_lock: '' })),
      fetchBibleStateForPanel(slug),
    ])

    if (seq !== biblePanelLoadSeq || props.slug !== slug) return

    let g = ''
    let w = ''
    if (novelRow) {
      const parsed = parseGenreWorldFromPremise(novelRow.premise || '')
      g = ((novelRow as any).locked_genre || '').trim() || parsed.genre
      w = ((novelRow as any).locked_world_preset || '').trim() || parsed.worldPreset
      lockedStoryStructure.value = ((novelRow as any).locked_story_structure || '').trim()
      lockedPacingControl.value = ((novelRow as any).locked_pacing_control || '').trim()
      lockedWritingStyle.value = ((novelRow as any).locked_writing_style || '').trim()
      lockedSpecialRequirements.value = ((novelRow as any).locked_special_requirements || '').trim()
      lockedTargetChapters.value = Number((novelRow as any).target_chapters || 0)
      lockedTargetWordsPerChapter.value = Number((novelRow as any).target_words_per_chapter || 0)
    } else {
      lockedStoryStructure.value = ''
      lockedPacingControl.value = ''
      lockedWritingStyle.value = ''
      lockedSpecialRequirements.value = ''
      lockedTargetChapters.value = 0
      lockedTargetWordsPerChapter.value = 0
    }

    const pl = typeof (knowledgeRow as any)?.premise_lock === 'string' ? (knowledgeRow as any).premise_lock : ''

    lockedGenre.value = g
    lockedWorld.value = w
    state.value = bibleUi
    premiseLock.value = pl
    syncJsonFromState()
  } catch (err: unknown) {
    if (seq !== biblePanelLoadSeq || props.slug !== slug) return
    message.error(formatApiError(err, '加载设定失败'))
  } finally {
    // 避免竞态 return 或异常路径未解除「表面待定」导致正文区 opacity:0 长期空白
    if (seq === biblePanelLoadSeq && props.slug === slug) {
      biblePanelDataReady.value = true
    }
  }
}

const save = async () => {
  saving.value = true
  try {
    const payload = {
      characters: state.value.characters.filter(c => (c.name || '').trim()),
      locations: state.value.locations.filter(l => (l.name || '').trim()),
      style_notes: state.value.style_notes,
    }
    const apiData = toApiFormat(payload)
    await bibleApi.updateBible(props.slug, apiData)

    const k = await knowledgeApi.getKnowledge(props.slug)
    await knowledgeApi.updateKnowledge(props.slug, {
      ...k,
      premise_lock: premiseLock.value.trim(),
    })
    window.dispatchEvent(new CustomEvent('plotpilot:knowledge:reload'))

    message.success('设定与梗概锁定已保存')
    syncJsonFromState()
  } catch (e: unknown) {
    message.error(formatApiError(e, '保存失败'))
  } finally {
    saving.value = false
  }
}

const generatePremiseKnowledge = async () => {
  generatingKnowledge.value = true
  try {
    const res = await knowledgeApi.generateKnowledge(props.slug)
    message.success(res.message || '梗概已生成')
    await load({ preserveSurface: true })
    window.dispatchEvent(new CustomEvent('plotpilot:knowledge:reload'))
  } catch (e: unknown) {
    message.error(formatApiError(e, 'AI 生成失败，请确认 API Key 已配置'))
  } finally {
    generatingKnowledge.value = false
  }
}

const saveFromJson = async () => {
  saving.value = true
  try {
    const payload = JSON.parse(jsonRaw.value)
    const apiData = toApiFormat(payload)
    await bibleApi.updateBible(props.slug, apiData)
    message.success('设定已保存')
    await load({ preserveSurface: true })
    showJsonModal.value = false
  } catch (e: unknown) {
    if (e instanceof SyntaxError) {
      message.error('JSON 格式错误')
    } else {
      message.error(formatApiError(e, '保存失败'))
    }
  } finally {
    saving.value = false
  }
}

const openJsonModal = () => {
  syncJsonFromState()
  showJsonModal.value = true
}

const formatJson = () => {
  try {
    const parsed = JSON.parse(jsonRaw.value)
    jsonRaw.value = JSON.stringify(parsed, null, 2)
  } catch (e) {
    message.error('JSON 格式错误，无法格式化')
  }
}

const generateBible = async () => {
  generating.value = true
  try {
    const res = await bibleApi.generateBible(props.slug)
    message.success(res.message || 'Bible 生成成功')
    await load({ preserveSurface: true })
  } catch (e: unknown) {
    message.error(formatApiError(e, 'AI 生成失败，请确认 API Key 已配置'))
  } finally {
    generating.value = false
  }
}

const openStylePresetModal = () => {
  const currentValue = matchPresetValue(state.value.style_notes)
  selectedStylePresetValue.value = currentValue || MARKET_STYLE_PRESETS[0]?.value || 'xianxia_hot'
  showStylePresetModal.value = true
}

const applyStylePreset = async () => {
  const preset = MARKET_STYLE_PRESETS.find(p => p.value === selectedStylePresetValue.value)
  if (!preset) {
    message.error('未找到选中的预设')
    return
  }

  state.value.style_notes = preset.body
  showStylePresetModal.value = false

  // Auto-save after applying preset
  await save()
}


const BIBLE_PANEL_SOFT_RELOAD = 'plotpilot:bible-panel:soft-reload'

watch(
  () => [props.slug, props.reloadNonce] as const,
  () => {
    const slug = (props.slug || '').trim()
    if (!slug) return
    void load()
  },
  { immediate: true },
)

onMounted(() => {
  window.addEventListener(BIBLE_PANEL_SOFT_RELOAD, onBiblePanelSoftReload as EventListener)
})

onUnmounted(() => {
  window.removeEventListener(BIBLE_PANEL_SOFT_RELOAD, onBiblePanelSoftReload as EventListener)
})

function onBiblePanelSoftReload() {
  if (props.slug) void load({ preserveSurface: true })
}
</script>

<style scoped>
/* ── Panel root (inherits pp-panel) ─────────────── */
.bible-panel {
  /* pp-panel provides: flex-col, height:100%, overflow:hidden, bg */
}

/* ── Header ──────────────────────────────────────── */
.bible-title-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}

.bible-badge {
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.06em;
  background: rgba(79, 70, 229, 0.1) !important;
  color: #4338ca !important;
}

.bible-header-stats {
  display: flex;
  align-items: center;
  gap: 5px;
  flex-wrap: wrap;
  margin-top: 4px;
}

/* ── Body scroll area ────────────────────────────── */
.bible-body {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

/* ── 创作契约 ────────────────────────────── */
.bible-contract-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(132px, 1fr));
  gap: 8px;
}

.bible-contract-card {
  min-height: 66px;
  padding: 10px;
  border-radius: 8px;
  border: 1px solid var(--app-border);
  background: var(--app-surface);
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.bible-contract-card__k {
  font-size: 11px;
  font-weight: 700;
  color: var(--app-text-muted);
}

.bible-contract-card__v {
  font-size: 12px;
  line-height: 1.45;
  color: var(--app-text-primary);
  word-break: break-word;
}

.bible-directives {
  margin-top: 10px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.bible-directive {
  display: grid;
  grid-template-columns: 64px minmax(0, 1fr);
  gap: 8px;
  align-items: start;
  padding: 7px 9px;
  border-radius: 8px;
  background: var(--plotpilot-panel-muted);
}

.bible-directive__k {
  font-size: 11px;
  font-weight: 700;
  color: var(--app-text-muted);
  line-height: 1.45;
}

.bible-directive__v {
  font-size: 12px;
  line-height: 1.55;
  color: var(--app-text-secondary);
  word-break: break-word;
}

/* ── Textareas ───────────────────────────────────── */
.bible-textarea :deep(textarea) {
  line-height: 1.6;
}

.bible-textarea-readonly :deep(textarea) {
  cursor: default;
  color: var(--app-text-secondary);
}

/* ── Style preset card ───────────────────────────── */
.bible-style-card {
  margin-top: 12px;
  padding: 12px;
  border-radius: var(--app-radius-md, 10px);
  background: var(--plotpilot-panel-muted);
  border: 1px solid var(--app-border);
}

.bible-style-card-header {
  display: flex;
  align-items: center;
  gap: 10px;
}

.bible-style-icon {
  flex-shrink: 0;
  width: 36px;
  height: 36px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 20px;
  border-radius: 8px;
  background: var(--app-surface);
  border: 1px solid var(--app-border);
}

.bible-style-info {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.bible-style-label {
  font-size: 13px;
  font-weight: 700;
  color: var(--app-text-primary);
  line-height: 1.3;
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.bible-style-summary {
  font-size: 11px;
  font-weight: 400;
  line-height: 1.45;
  color: var(--app-text-secondary);
}

.bible-style-content {
  font-size: 12px;
  line-height: 1.7;
  color: var(--app-text-secondary);
  white-space: pre-wrap;
  word-break: break-all;
  padding: 8px;
  border-radius: 6px;
  background: var(--app-surface);
}

/* ── JSON modal ──────────────────────────────────── */
.bible-json-input :deep(textarea) {
  font-family: 'Consolas', 'Monaco', monospace;
  font-size: 12px;
  line-height: 1.6;
}
</style>
