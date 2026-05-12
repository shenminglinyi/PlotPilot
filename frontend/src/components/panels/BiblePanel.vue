<template>
  <div class="bible-panel">
    <header class="bible-hero">
      <div class="bible-hero-main">
        <div class="bible-title-row">
          <h3 class="bible-title">作品设定</h3>
          <n-tag size="small" round :bordered="false" class="bible-badge">Story Bible</n-tag>
        </div>
        <p class="bible-lead">
          <strong>梗概锁定</strong>（主线与不可违背设定）与<strong>写作公约</strong>（人称、时态、叙事距离、基调与禁区）——全书的「写什么」与「怎么写」。
        </p>
        <div class="bible-roles" aria-label="资料分工">
          <div class="bible-role-item bible-role-here">
            <span class="bible-role-k">梗概锁定</span>
            <span class="bible-role-v">此处 · 主线与不可违背设定（全书上下文）</span>
          </div>
          <div class="bible-role-item">
            <span class="bible-role-k">世界观构建</span>
            <span class="bible-role-v">世界观 Tab · 5维度框架</span>
          </div>
          <div class="bible-role-item bible-role-here">
            <span class="bible-role-k">写作风格</span>
            <span class="bible-role-v">本书锁定 · 文风市场预设（只读标签）</span>
          </div>
          <div class="bible-role-item">
            <span class="bible-role-k">角色与地点</span>
            <span class="bible-role-v">知识库 · 三元组关系</span>
          </div>
          <div class="bible-role-item">
            <span class="bible-role-k">叙事线索</span>
            <span class="bible-role-v">故事线/时间线</span>
          </div>
        </div>
        <div class="bible-stats" :aria-busy="!biblePanelDataReady">
          <template v-if="biblePanelDataReady">
            <span class="bible-stat bible-stat-premise" :class="{ 'is-done': stats.premiseOk }">
              梗概锁定 {{ stats.premiseOk ? '已填' : '待补充' }}
            </span>
            <span class="bible-stat-dot" aria-hidden="true" />
            <span class="bible-stat bible-stat-style" :class="{ 'is-done': stats.styleOk }">
              文风公约 {{ stats.styleOk ? '已填' : '待补充' }}
            </span>
          </template>
          <template v-else>
            <!-- 占位与正式行等高，避免先发「待补充」再跳到「已填」造成闪烁 -->
            <span class="bible-stat bible-stat-placeholder">梗概锁定 …</span>
            <span class="bible-stat-dot" aria-hidden="true" />
            <span class="bible-stat bible-stat-placeholder">文风公约 …</span>
          </template>
        </div>
      </div>
      <n-space class="bible-hero-actions" :size="8" align="center">
        <n-button size="small" secondary :loading="generating" @click="generateBible" title="用 AI 根据小说标题重新生成设定">
          ✦ AI 生成
        </n-button>
        <n-button size="small" type="primary" :loading="saving" @click="save">保存设定</n-button>
      </n-space>
    </header>

    <n-scrollbar class="bible-scroll" :class="{ 'bible-scroll--surface-pending': !biblePanelDataReady }">
      <div class="bible-form">
        <n-card
          v-if="hasBookLock"
          size="small"
          class="bible-card bible-card-creation-lock"
          :bordered="false"
          :segmented="{ content: true, footer: false }"
        >
          <template #header>
            <div class="bcard-head">
              <span class="bcard-icon bcard-icon-lock" aria-hidden="true">◎</span>
              <div>
                <div class="bcard-title">本书锁定</div>
                <div class="bcard-desc">
                  赛道、世界观与文风市场预设仅作展示，不提供修改入口（与创建书目 / Bible 初始约定一致）。
                </div>
              </div>
            </div>
          </template>
          <n-descriptions
            :column="1"
            label-placement="left"
            size="small"
            class="bible-creation-lock-desc"
          >
            <n-descriptions-item label="赛道 / 类型">{{ lockedGenre || '—' }}</n-descriptions-item>
            <n-descriptions-item label="世界观基调">{{ lockedWorld || '—' }}</n-descriptions-item>
            <n-descriptions-item label="文风市场预设">
              <n-space size="small" wrap align="center">
                <n-tag
                  :type="stylePresetTag.tagType"
                  size="small"
                  round
                  :bordered="false"
                >
                  {{ stylePresetTag.label }}
                </n-tag>
              </n-space>
            </n-descriptions-item>
          </n-descriptions>
          <n-collapse
            v-show="hasStyleNotesDetail"
            class="bible-style-full-collapse"
          >
            <n-collapse-item title="查看完整文风公约文本" name="style">
              <n-input
                :value="state.style_notes"
                type="textarea"
                readonly
                disabled
                :autosize="{ minRows: 4, maxRows: 14 }"
                class="bible-textarea bible-textarea-readonly"
              />
            </n-collapse-item>
          </n-collapse>
        </n-card>

        <n-card size="small" class="bible-card" :bordered="false" :segmented="{ content: true, footer: false }">
          <template #header>
            <div class="bcard-head bcard-head-row">
              <div class="bcard-head-main">
                <span class="bcard-icon bcard-icon-lock" aria-hidden="true">◆</span>
                <div>
                  <div class="bcard-title">梗概锁定</div>
                  <div class="bcard-desc">
                    主线、不可违背设定、结局走向（与 manifest 互补，防百万字跑篇）。写入全书知识上下文，工具
                    <code class="bible-inline-code">story_set_premise_lock</code> 同源。
                  </div>
                </div>
              </div>
              <n-button
                size="tiny"
                secondary
                :loading="generatingKnowledge"
                @click="generatePremiseKnowledge"
                title="根据 Bible 生成或刷新梗概锁定（覆盖当前框内容）"
              >
                ✦ AI 生成梗概
              </n-button>
            </div>
          </template>
          <n-input
            v-model:value="premiseLock"
            type="textarea"
            :autosize="{ minRows: 5, maxRows: 18 }"
            placeholder="主线、不可违背设定、结局走向（与 manifest 互补，防百万字跑篇）…"
            show-count
            :maxlength="24000"
            class="bible-textarea"
          />
        </n-card>

      </div>
    </n-scrollbar>

    <div class="bible-footer">
      <n-space :size="8">
        <n-button size="small" type="primary" :loading="saving" @click="save">保存</n-button>
        <n-button size="small" @click="openJsonModal">JSON 编辑器</n-button>
      </n-space>
    </div>

    <!-- JSON 编辑器弹窗 -->
    <n-modal v-model:show="showJsonModal" preset="card" title="JSON 编辑器" style="width: 800px; max-width: 90vw">
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
  </div>
</template>

<script setup lang="ts">
import { ref, watch, computed, onMounted, onUnmounted } from 'vue'
import { useMessage } from 'naive-ui'
import { bibleApi } from '../../api/bible'
import type { CharacterDTO, LocationDTO, TimelineNoteDTO, StyleNoteDTO } from '../../api/bible'
import { knowledgeApi } from '../../api/knowledge'
import { MARKET_STYLE_PRESETS, matchPresetValue } from '@/constants/marketStylePresets'
import { novelApi } from '@/api/novel'
import { parseGenreWorldFromPremise } from '@/utils/premisePresets'

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
const saving = ref(false)
const generating = ref(false)
const premiseLock = ref('')
const generatingKnowledge = ref(false)
/** 本作数据是否已从接口合并完成（避免首帧「待补充」→「已填」与下方表单高度连环闪） */
const biblePanelDataReady = ref(false)

/** 并发 load 取消：只应用最后一次 slug 对应的请求结果，避免多块 UI v-if/v-show 交替闪烁 */
let biblePanelLoadSeq = 0

/** 创建书目时写入 premise 的赛道 / 世界观；文风来自 Bible（只读标签展示） */
const lockedGenre = ref('')
const lockedWorld = ref('')
const hasBookLock = computed(() => {
  const g = lockedGenre.value.trim()
  const w = lockedWorld.value.trim()
  const sty = (state.value.style_notes || '').trim()
  return g !== '' || w !== '' || sty !== ''
})

const hasStyleNotesDetail = computed(() => (state.value.style_notes || '').trim().length > 0)

/** 文风市场预设：匹配内置模板则显示预设名，否则警告文案（单组件避免 v-if 整节点销毁重建） */
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
    label: '与内置模板不一致（可能来自旧数据或导入）',
    tagType: 'warning' as const,
  }
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
  } catch (err: any) {
    if (err?.response?.status !== 404) throw err
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
    }

    const pl = typeof (knowledgeRow as any)?.premise_lock === 'string' ? (knowledgeRow as any).premise_lock : ''

    lockedGenre.value = g
    lockedWorld.value = w
    state.value = bibleUi
    premiseLock.value = pl
    syncJsonFromState()
  } catch (err: any) {
    if (seq !== biblePanelLoadSeq || props.slug !== slug) return
    message.error(err?.response?.data?.detail || '加载设定失败')
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
    window.dispatchEvent(new CustomEvent('aitext:knowledge:reload'))

    message.success('设定与梗概锁定已保存')
    syncJsonFromState()
  } catch (e: any) {
    message.error(e?.response?.data?.detail || '保存失败')
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
    window.dispatchEvent(new CustomEvent('aitext:knowledge:reload'))
  } catch (e: any) {
    message.error(e?.response?.data?.detail || 'AI 生成失败，请确认 API Key 已配置')
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
  } catch (e: any) {
    if (e instanceof SyntaxError) {
      message.error('JSON 格式错误')
    } else {
      message.error(e?.response?.data?.detail || '保存失败')
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
  } catch (e: any) {
    message.error(e?.response?.data?.detail || 'AI 生成失败，请确认 API Key 已配置')
  } finally {
    generating.value = false
  }
}


const BIBLE_PANEL_SOFT_RELOAD = 'aitext:bible-panel:soft-reload'

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
.bible-panel {
  height: 100%;
  min-height: 0;
  display: flex;
  flex-direction: column;
  padding: 0 12px 10px;
  background: linear-gradient(165deg, var(--app-surface-subtle) 0%, var(--app-border) 55%, var(--app-page-bg) 100%);
}

.bible-hero {
  flex-shrink: 0;
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 14px;
  padding: 14px 2px 12px;
  border-bottom: 1px solid rgba(15, 23, 42, 0.07);
}

.bible-hero-main {
  min-width: 0;
  flex: 1;
}

.bible-title-row {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  margin-bottom: 8px;
}

.bible-title {
  margin: 0;
  font-size: 17px;
  font-weight: 700;
  letter-spacing: 0.04em;
  color: var(--app-text-primary);
}

.bible-badge {
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.06em;
  text-transform: none;
  background: rgba(79, 70, 229, 0.1) !important;
  color: #4338ca !important;
}

.bible-lead {
  margin: 0 0 12px;
  font-size: 12px;
  line-height: 1.65;
  color: #475569;
  max-width: 52em;
}

.bible-lead strong {
  color: var(--app-text-secondary);
  font-weight: 600;
}

.bible-roles {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px 12px;
  margin-bottom: 12px;
}

@media (max-width: 520px) {
  .bible-roles {
    grid-template-columns: 1fr;
  }
}

.bible-role-item {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 8px 10px;
  border-radius: 8px;
  background: var(--app-surface);
  border: 1px solid var(--app-border);
}

.bible-role-item.bible-role-here {
  border-color: rgba(99, 102, 241, 0.35);
  background: rgba(99, 102, 241, 0.06);
}

.bible-role-k {
  font-size: 11px;
  font-weight: 600;
  color: #64748b;
  letter-spacing: 0.02em;
}

.bible-role-v {
  font-size: 11px;
  color: var(--app-text-secondary);
  line-height: 1.4;
}

.bible-stats {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px 4px;
  font-size: 12px;
  color: #64748b;
  min-height: 1.5em;
}

.bible-stat-placeholder {
  color: rgba(100, 116, 139, 0.55);
  letter-spacing: 0.02em;
  user-select: none;
}

.bible-stat em {
  font-style: normal;
  font-weight: 700;
  color: var(--app-text-primary);
  margin-right: 2px;
}

.bible-stat-dot {
  width: 3px;
  height: 3px;
  border-radius: 50%;
  background: var(--app-text-secondary, #cbd5e1);
  margin: 0 2px;
}

.bible-stat-premise.is-done,
.bible-stat-style.is-done {
  color: #15803d;
}

.bible-hero-actions {
  flex-shrink: 0;
  padding-top: 2px;
}

.bible-scroll {
  flex: 1;
  min-height: 0;
}

.bible-scroll--surface-pending {
  min-height: min(320px, 52vh);
}

/* 不再在加载时隐藏表单：opacity:0 曾与 load 竞态结合导致整页「空白」不可恢复 */
.bible-scroll:not(.bible-scroll--surface-pending) .bible-form {
  transition: opacity 0.12s ease-out;
}

.bible-card-creation-lock {
  border: 1px solid var(--app-border, rgba(15, 23, 42, 0.1));
}

.bible-creation-lock-desc :deep(.n-descriptions-item__label) {
  color: var(--app-text-secondary, #475569);
}

.bible-creation-lock-desc :deep(.n-descriptions-item__content) {
  color: var(--app-text-primary, #111827);
}

.bible-style-full-collapse {
  margin-top: 12px;
}

.bible-style-full-collapse :deep(.n-collapse-item__header) {
  font-size: 12px;
  color: var(--app-text-secondary, #475569);
}

.bible-form {
  padding: 14px 2px 24px;
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.bible-scroll {
  flex: 1;
  min-height: 0;
}

.bible-footer {
  flex-shrink: 0;
  padding: 12px 16px;
  border-top: 1px solid rgba(15, 23, 42, 0.06);
  background: var(--app-surface-subtle);
}

.bible-form {
  padding: 8px 16px 16px;
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.bible-json-input :deep(textarea) {
  font-family: 'Consolas', 'Monaco', monospace;
  font-size: 12px;
  line-height: 1.6;
}

.bible-card {
  border-radius: 12px !important;
  box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04);
  border: 1px solid rgba(15, 23, 42, 0.06) !important;
  background: var(--app-surface) !important;
}

.bible-card :deep(.n-card-header) {
  padding: 12px 14px 10px;
}

.bible-card :deep(.n-card__content) {
  padding: 12px 14px 14px;
}

.bcard-head {
  display: flex;
  align-items: flex-start;
  gap: 10px;
}

.bcard-head-row {
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  width: 100%;
  flex-wrap: wrap;
}

.bcard-head-main {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  min-width: 0;
  flex: 1;
}

.bcard-icon-lock {
  font-size: 12px;
  font-weight: 700;
  color: #4338ca;
  background: rgba(67, 56, 202, 0.12);
}

.bible-inline-code {
  font-size: 10px;
  padding: 1px 5px;
  border-radius: 4px;
  background: rgba(15, 23, 42, 0.06);
  color: #4338ca;
}

.bcard-icon {
  flex-shrink: 0;
  width: 22px;
  height: 22px;
  margin-top: 2px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 13px;
  color: #6366f1;
  background: rgba(99, 102, 241, 0.12);
  border-radius: 6px;
}

.bcard-icon-text {
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.08em;
}

.bible-icon-timeline {
  flex-shrink: 0;
  width: 22px;
  height: 22px;
  margin-top: 2px;
  border-radius: 6px;
  background: linear-gradient(135deg, rgba(99, 102, 241, 0.2), rgba(14, 165, 233, 0.15));
  position: relative;
}

.bible-icon-timeline::after {
  content: '';
  position: absolute;
  left: 50%;
  top: 5px;
  bottom: 5px;
  width: 2px;
  transform: translateX(-50%);
  border-radius: 1px;
  background: #6366f1;
}

.bcard-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--app-text-primary);
  letter-spacing: 0.02em;
  margin-bottom: 4px;
}

.bcard-desc {
  font-size: 11px;
  line-height: 1.5;
  color: #64748b;
}

.bible-textarea :deep(textarea) {
  line-height: 1.55;
}

.bible-textarea-readonly :deep(textarea) {
  cursor: default;
  color: var(--app-text-secondary);
}

.char-block,
.loc-block {
  padding: 12px 0;
  border-bottom: 1px solid rgba(15, 23, 42, 0.06);
}

.char-block:last-child,
.loc-block:last-child {
  border-bottom: none;
  padding-bottom: 0;
}

.char-block-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 10px;
}

.char-label {
  font-size: 12px;
  font-weight: 600;
  color: #475569;
}

.mb-8 {
  margin-bottom: 8px;
}

.w-full {
  width: 100%;
}

.bible-empty {
  padding: 8px 0 4px;
}

.bible-json-wrap {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 14px 2px 20px;
}

.bible-json-alert {
  font-size: 12px;
  line-height: 1.55;
  border-radius: 10px;
  background: rgba(15, 23, 42, 0.04) !important;
}

.bible-json-alert code {
  font-size: 11px;
  padding: 1px 5px;
  border-radius: 4px;
  background: rgba(79, 70, 229, 0.1);
  color: #4338ca;
}

.bible-json {
  min-height: 320px;
  font-family: ui-monospace, 'JetBrains Mono', Consolas, monospace;
  font-size: 12px;
  border-radius: 10px;
}

.bible-card-last {
  margin-bottom: 0;
}
</style>
