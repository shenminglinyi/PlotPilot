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
            <span class="bible-role-v">本书锁定 · 文风市场预设（可更改）</span>
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
        <div class="bible-stats" aria-live="polite">
          <span class="bible-stat bible-stat-premise" :class="{ 'is-done': stats.premiseOk }">
            梗概锁定 {{ stats.premiseOk ? '已填' : '待补充' }}
          </span>
          <span class="bible-stat-dot" aria-hidden="true" />
          <span class="bible-stat bible-stat-style" :class="{ 'is-done': stats.styleOk }">
            文风公约 {{ stats.styleOk ? '已填' : '待补充' }}
          </span>
        </div>
      </div>
      <n-space class="bible-hero-actions" :size="8" align="center">
        <n-button size="small" secondary :loading="generating" @click="generateBible" title="用 AI 根据小说标题重新生成设定">
          ✦ AI 生成
        </n-button>
        <n-button size="small" type="primary" :loading="saving" @click="save">保存设定</n-button>
      </n-space>
    </header>

    <n-scrollbar class="bible-scroll">
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
                  赛道与世界观仅作展示，不可修改。文风市场预设可通过"更改模板"按钮调整。
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
                  v-if="stylePresetTag.matched"
                  type="info"
                  size="small"
                  round
                  :bordered="false"
                >
                  {{ stylePresetTag.label }}
                </n-tag>
                <n-tag
                  v-else-if="stylePresetTag.hasText"
                  type="warning"
                  size="small"
                  round
                  :bordered="false"
                >
                  {{ stylePresetTag.label }}
                </n-tag>
                <n-tag v-else type="default" size="small" round :bordered="false">—</n-tag>
                <n-dropdown
                  :options="stylePresetMenuOptions"
                  trigger="click"
                  placement="bottom-start"
                  @select="handleStylePresetSelect"
                >
                  <n-button size="tiny" secondary :disabled="saving">
                    <template #icon>
                      <n-icon><component :is="GearIcon" /></n-icon>
                    </template>
                    更改模板
                  </n-button>
                </n-dropdown>
                <n-button size="tiny" secondary @click="openStyleEditor" :disabled="saving">
                  自定义
                </n-button>
                <n-button size="tiny" secondary :loading="regeneratingStyle" @click="handleRegenerateStyle" :disabled="saving">
                  <template #icon>
                    <n-icon>✦</n-icon>
                  </template>
                  AI 重新生成
                </n-button>
              </n-space>
            </n-descriptions-item>
          </n-descriptions>
          <n-collapse
            v-if="(state.style_notes || '').trim()"
            class="bible-style-full-collapse"
          >
            <n-collapse-item title="查看完整文风公约文本" name="style">
              <template #header-extra>
                <n-button size="tiny" text @click.stop="openStyleEditor">编辑</n-button>
              </template>
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

    <!-- 文风自定义编辑弹窗 -->
    <n-modal v-model:show="showStyleEditor" preset="card" title="自定义文风公约" style="width: 700px; max-width: 90vw">
      <n-space vertical :size="12">
        <n-alert type="info" :show-icon="true">
          自定义文风时，可以参考预设模板的结构。如果不使用预设模板，标签会显示"与内置模板不一致"。
        </n-alert>
        <n-input
          v-model:value="customStyleText"
          type="textarea"
          :rows="12"
          placeholder="输入自定义的文风公约，例如：&#10;【文风公约·自定义】第三人称有限视角；节奏明快，对话简洁..."
          show-count
          :maxlength="5000"
        />
        <n-space :size="8" justify="end">
          <n-button @click="showStyleEditor = false">取消</n-button>
          <n-button type="primary" :loading="saving" @click="saveCustomStyle">保存</n-button>
        </n-space>
      </n-space>
    </n-modal>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, onMounted, computed, h } from 'vue'
import { useMessage, NIcon } from 'naive-ui'
import { bibleApi } from '../../api/bible'
import type { CharacterDTO, LocationDTO, TimelineNoteDTO, StyleNoteDTO } from '../../api/bible'
import { knowledgeApi } from '../../api/knowledge'
import { MARKET_STYLE_PRESETS, matchPresetValue } from '@/constants/marketStylePresets'
import { novelApi } from '@/api/novel'
import { parseGenreWorldFromPremise } from '@/utils/premisePresets'

// 齿轮图标
const GearIcon = () =>
  h('svg', {
    xmlns: 'http://www.w3.org/2000/svg',
    viewBox: '0 0 24 24',
    width: '1em',
    height: '1em',
    fill: 'currentColor'
  }, h('path', {
    d: 'M19.14,12.94c0.04-0.3,0.06-0.61,0.06-0.94c0-0.32-0.02-0.64-0.07-0.94l2.03-1.58c0.18-0.14,0.23-0.41,0.12-0.61 l-1.92-3.32c-0.12-0.22-0.37-0.29-0.59-0.22l-2.39,0.96c-0.5-0.38-1.03-0.7-1.62-0.94L14.4,2.81c-0.04-0.24-0.24-0.41-0.48-0.41 h-3.84c-0.24,0-0.43,0.17-0.47,0.41L9.25,5.35C8.66,5.59,8.12,5.92,7.63,6.29L5.24,5.33c-0.22-0.08-0.47,0-0.59,0.22L2.74,8.87 C2.62,9.08,2.66,9.34,2.86,9.48l2.03,1.58C4.84,11.36,4.8,11.69,4.8,12s0.02,0.64,0.07,0.94l-2.03,1.58 c-0.18,0.14-0.23,0.41-0.12,0.61l1.92,3.32c0.12,0.22,0.37,0.29,0.59,0.22l2.39-0.96c0.5,0.38,1.03,0.7,1.62,0.94l0.36,2.54 c0.05,0.24,0.24,0.41,0.48,0.41h3.84c0.24,0,0.44-0.17,0.47-0.41l0.36-2.54c0.59-0.24,1.13-0.56,1.62-0.94l2.39,0.96 c0.22,0.08,0.47,0,0.59-0.22l1.92-3.32c0.12-0.22,0.07-0.47-0.12-0.61L19.14,12.94z M12,15.6c-1.98,0-3.6-1.62-3.6-3.6 s1.62-3.6,3.6-3.6s3.6,1.62,3.6,3.6S13.98,15.6,12,15.6z'
  }))

const props = defineProps<{ slug: string }>()
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
const showStyleEditor = ref(false)
const customStyleText = ref('')
const saving = ref(false)
const generating = ref(false)
const regeneratingStyle = ref(false)
const premiseLock = ref('')
const generatingKnowledge = ref(false)

/** 创建书目时写入 premise 的赛道 / 世界观；文风来自 Bible（只读标签展示） */
const lockedGenre = ref('')
const lockedWorld = ref('')
const hasBookLock = computed(() => {
  const g = lockedGenre.value.trim()
  const w = lockedWorld.value.trim()
  const sty = (state.value.style_notes || '').trim()
  return g !== '' || w !== '' || sty !== ''
})

/** 文风市场预设：匹配内置模板则显示预设名，否则警告文案 */
const stylePresetTag = computed(() => {
  const t = (state.value.style_notes || '').trim()
  if (!t) {
    return { matched: false, hasText: false, label: '—' }
  }
  const m = matchPresetValue(t)
  if (m) {
    const p = MARKET_STYLE_PRESETS.find((x) => x.value === m)
    return { matched: true, hasText: true, label: p?.label ?? m }
  }
  return {
    matched: false,
    hasText: true,
    label: '与内置模板不一致（可能来自旧数据或导入）',
  }
})

function applyStylePresetByValue(value: string) {
  const p = MARKET_STYLE_PRESETS.find((x) => x.value === value)
  if (p) state.value.style_notes = p.body
}

/** 文风预设下拉菜单选项 */
const stylePresetMenuOptions = computed(() =>
  MARKET_STYLE_PRESETS.map(p => ({
    label: p.label,
    key: p.value,
  }))
)

/** 处理文风预设选择 */
async function handleStylePresetSelect(value: string) {
  const preset = MARKET_STYLE_PRESETS.find(p => p.value === value)
  if (!preset) return

  // 应用预设
  state.value.style_notes = preset.body

  // 自动保存
  try {
    saving.value = true
    const apiData = toApiFormat(state.value)
    await bibleApi.updateBible(props.slug, apiData)
    message.success(`已应用文风预设：${preset.label}`)
    syncJsonFromState() // 更新 JSON 缓存
  } catch (error: any) {
    message.error('保存失败：' + (error.response?.data?.detail || error.message))
  } finally {
    saving.value = false
  }
}

/** 保存自定义文风 */
async function saveCustomStyle() {
  if (!customStyleText.value.trim()) {
    message.warning('请输入文风公约内容')
    return
  }

  state.value.style_notes = customStyleText.value.trim()

  try {
    saving.value = true
    const apiData = toApiFormat(state.value)
    await bibleApi.updateBible(props.slug, apiData)
    message.success('文风公约已保存')
    showStyleEditor.value = false
    syncJsonFromState()
  } catch (error: any) {
    message.error('保存失败：' + (error.response?.data?.detail || error.message))
  } finally {
    saving.value = false
  }
}

/** AI 重新生成文风 */
async function handleRegenerateStyle() {
  if (!confirm('确定要 AI 重新生成文风公约吗？当前内容将被覆盖。')) {
    return
  }

  regeneratingStyle.value = true
  try {
    // 调用 Bible 生成 API，只生成文风部分
    await bibleApi.generateBible(props.slug, 'style')

    // 轮询检查状态
    const checkStatus = async () => {
      try {
        const status = await bibleApi.getBibleStatus(props.slug)
        if (status.ready) {
          // 重新加载 Bible
          const bible = await bibleApi.getBible(props.slug)
          const fromApi = fromApiFormat(bible)
          state.value.style_notes = fromApi.style_notes
          syncJsonFromState()
          regeneratingStyle.value = false
          message.success('文风公约已重新生成')
        } else {
          // 继续轮询
          setTimeout(checkStatus, 2000)
        }
      } catch (error) {
        regeneratingStyle.value = false
        message.error('生成失败')
      }
    }

    // 开始轮询
    setTimeout(checkStatus, 1000)
  } catch (error: any) {
    regeneratingStyle.value = false
    message.error('启动生成失败：' + (error.response?.data?.detail || error.message))
  }
}

/** 打开自定义编辑器 */
function openStyleEditor() {
  customStyleText.value = state.value.style_notes || ''
  showStyleEditor.value = true
}

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

const loadPremiseLock = async () => {
  try {
    const k = await knowledgeApi.getKnowledge(props.slug)
    premiseLock.value = k.premise_lock || ''
  } catch {
    premiseLock.value = ''
  }
}

const loadCreationLock = async () => {
  try {
    const n = await novelApi.getNovel(props.slug)
    const parsed = parseGenreWorldFromPremise(n.premise || '')
    lockedGenre.value = (n.locked_genre || '').trim() || parsed.genre
    lockedWorld.value = (n.locked_world_preset || '').trim() || parsed.worldPreset
  } catch {
    lockedGenre.value = ''
    lockedWorld.value = ''
  }
}

const load = async () => {
  await loadCreationLock()
  try {
    const bible = await bibleApi.getBible(props.slug)
    state.value = fromApiFormat(bible)
    const matched = matchPresetValue(state.value.style_notes)
    if (!matched && !(state.value.style_notes || '').trim()) {
      applyStylePresetByValue(MARKET_STYLE_PRESETS[0]?.value ?? 'xianxia_hot')
    }
    syncJsonFromState()
  } catch (err: any) {
    // If Bible doesn't exist, create it
    if (err?.response?.status === 404) {
      try {
        await bibleApi.createBible(props.slug, `bible-${props.slug}`)
        state.value = emptyState()
        applyStylePresetByValue(MARKET_STYLE_PRESETS[0]?.value ?? 'xianxia_hot')
        syncJsonFromState()
      } catch {
        message.error('创建设定失败')
      }
    } else {
      message.error('加载设定失败')
    }
  }
  await loadPremiseLock()
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
    await loadPremiseLock()
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
    await load()
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
    await load()
  } catch (e: any) {
    message.error(e?.response?.data?.detail || 'AI 生成失败，请确认 API Key 已配置')
  } finally {
    generating.value = false
  }
}


watch(
  () => props.slug,
  () => {
    void load()
  }
)

onMounted(() => {
  void load()
})
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
