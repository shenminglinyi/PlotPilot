<template>
  <teleport to="body">
    <div
      v-if="show"
      ref="maskRef"
      class="builder-mask"
      role="dialog"
      aria-modal="true"
      aria-label="打包制作叙事模组"
      :aria-busy="submitting"
      @click.self="requestClose"
    >
      <div ref="dialogRef" class="builder-dialog" tabindex="-1">
        <header class="builder-head">
          <div>
            <h3 class="builder-title">打包制作叙事模组</h3>
            <p class="builder-sub">
              将你调优过的提示词节点封装为标准 <code>plotpilot-mod/v1.1</code> 清单（兼容 <code>plotpilot-mod/v1</code>），一键分享至 GitHub 社区。
            </p>
          </div>
          <button ref="closeBtnRef" type="button" class="builder-close" aria-label="关闭" :disabled="submitting" @click="requestClose">
            <svg viewBox="0 0 24 24" fill="none" width="18" height="18" aria-hidden="true">
              <path
                d="M18 6 6 18M6 6l12 12"
                stroke="currentColor"
                stroke-width="1.8"
                stroke-linecap="round"
              />
            </svg>
          </button>
        </header>

        <div class="builder-body">
          <fieldset class="builder-fieldset" :disabled="submitting">
            <div class="builder-stack">
          <!-- 基本元数据 -->
          <div class="form-grid">
            <label class="field-item">
              <span class="field-label">模组名称</span>
              <input
                v-model="form.name"
                type="text"
                class="field-input"
                placeholder="例如：硬核刑侦·冷峻程序流"
              />
            </label>
            <label class="field-item is-narrow">
              <span class="field-label">方章单字</span>
              <input
                v-model="form.glyph"
                type="text"
                maxlength="2"
                class="field-input"
                placeholder="刑"
              />
            </label>
            <label class="field-item">
              <span class="field-label">作者署名</span>
              <input
                v-model="form.author"
                type="text"
                class="field-input"
                placeholder="你的笔名或 GitHub ID"
              />
            </label>
            <label class="field-item">
              <span class="field-label">能力分区</span>
              <select v-model="form.roleCategory" class="field-input">
                <option
                  v-for="cat in roleOptions"
                  :key="cat.key"
                  :value="cat.key"
                >
                  {{ cat.label }}
                </option>
              </select>
            </label>
          </div>

          <label class="field-item">
            <span class="field-label">一句话人话价值（展示在卡片正面，让读者 3 秒看懂有什么用）</span>
            <textarea
              v-model="form.summary"
              rows="2"
              class="field-textarea"
              placeholder="例如：消除悬浮推理套话，强制按现场物证链与审讯心理博弈推进章节正文。"
            />
          </label>

          <!-- 选择要打包的引擎节点 -->
          <div class="node-picker-block">
            <div class="picker-head">
              <span class="field-label">
                选择要纳入模组的引擎节点（已选 <strong class="numeric">{{ selectedKeys.length }}</strong> 个）
              </span>
              <input
                v-model="nodeFilter"
                type="text"
                class="picker-search"
                placeholder="筛选节点名称或键…"
              />
            </div>

            <div class="picker-list">
              <label
                v-for="node in sortedNodes"
                :key="node.node_key"
                class="picker-row"
                :class="{ 'is-checked': selectedKeys.includes(node.node_key) }"
              >
                <input
                  type="checkbox"
                  :value="node.node_key"
                  v-model="selectedKeys"
                />
                <span class="picker-node-name">{{ node.name }}</span>
                <code class="picker-node-key">{{ node.node_key }}</code>
                <span v-if="node.has_user_edit" class="edited-pill">已调优</span>
              </label>
            </div>
          </div>

          <section class="extension-editor" aria-label="叙事护栏与开局能力">
            <h4>叙事护栏与开局能力（v1.1 扩展，可选）</h4>
            <div class="tier-options" aria-label="建议模型档位"><button v-for="tier in tierOptions" :key="tier.value" type="button" :aria-pressed="form.recommendedModelTier === tier.value" :class="{ 'is-selected': form.recommendedModelTier === tier.value }" @click="form.recommendedModelTier = tier.value">{{ tier.label }}</button></div>
            <p class="extension-hint">{{ selectedTierHint }}</p>
            <label class="field-item"><span class="field-label">开篇节拍支架</span><textarea v-model="form.openingBeatTemplate" class="beat-input" rows="6" maxlength="4000" /></label>
            <button type="button" class="quiet-btn" @click="loadStarter">载入三幕范例</button>
            <h4>审稿红线清单</h4>
            <div class="rules-ledger"><div v-for="(rule, i) in form.reviewRedlines" :key="rule" class="rule-entry"><span class="numeric">第 {{ i + 1 }} 条</span><p>{{ rule }}</p><button type="button" class="quiet-btn" :aria-label="`移除第 ${i + 1} 条红线`" @click="form.reviewRedlines.splice(i, 1)">移除</button></div></div>
            <div class="entry-controls"><textarea v-model="ruleDraft" aria-label="新增审稿红线，可粘贴多行" maxlength="240" rows="2" class="field-textarea" /><button type="button" class="quiet-btn" @click="addEntries('rules')">添入</button></div>
            <h4>去套话巡检词表</h4>
            <div class="words-pool"><span v-for="(word, i) in form.antiAiWordlist" :key="word" class="word-token">{{ word }}<button type="button" :aria-label="`移除词汇 ${word}`" @click="form.antiAiWordlist.splice(i, 1)">×</button></span><span v-if="!form.antiAiWordlist.length" class="extension-hint">尚未添入巡检词汇</span></div>
            <div class="entry-controls"><input v-model="wordDraft" class="field-input" maxlength="64" aria-label="新增巡检词汇，可用逗号分隔" @keydown.enter.prevent="addEntries('words')" /><button type="button" class="quiet-btn" @click="addEntries('words')">添入</button><button type="button" class="quiet-btn" @click="form.antiAiWordlist = []; wordDraft = ''">清空词表</button></div>
          </section>
          <!-- 可选样章对比 -->
          <details class="showcase-details">
            <summary class="showcase-summary">附带实测样章对比（选填，强烈推荐填写以提升社区安装率）</summary>
            <div class="showcase-fields">
              <input
                v-model="form.scenario"
                type="text"
                class="field-input"
                placeholder="测试场景，例如：雨夜勘查失踪案第一现场"
              />
              <div class="showcase-pair">
                <textarea
                  v-model="form.beforeExcerpt"
                  rows="3"
                  class="field-textarea"
                  placeholder="未装模组时的默认 AI 味片段…"
                />
                <textarea
                  v-model="form.afterExcerpt"
                  rows="3"
                  class="field-textarea"
                  placeholder="启用你的模组后生成的样章片段…"
                />
              </div>
            </div>
          </details>
            </div>
          </fieldset>
        </div>

        <footer class="builder-foot">
          <span class="foot-hint">导出后放入 GitHub 仓库根目录并命名为 <code>plotpilot-mod.json</code>，他人即可通过 <code>github:owner/repo</code> 一键安装。</span>
          <div class="foot-btns">
            <button
              type="button"
              class="builder-btn"
              :disabled="submitting || !canSubmit"
              @click="handleSaveLocal"
            >
              保存到本地已安装
            </button>
            <button
              type="button"
              class="builder-btn is-primary"
              :disabled="submitting || !canSubmit"
              @click="handleExportFile"
            >
              {{ submitting ? '正在打包…' : '导出模组清单' }}
            </button>
          </div>
        </footer>
      </div>
    </div>
  </teleport>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, reactive, ref, watch } from 'vue'
import { useMessage } from 'naive-ui'
import { promptPlazaApi, type PromptNode, type PromptNodeDetail } from '@/api/llmControl'
import {
  MOD_ROLE_CATEGORIES,
  MOD_RECOMMENDED_MODEL_TIER_META,
  type ModRecommendedModelTier,
  type ModNodeOverride,
  type ModRoleCategory,
  type NarrativeModPack,
} from '@/domain/modPack/types'
import {
  stripModDelimiterComments,
  useModHubStore,
} from '@/stores/modHubStore'

import { assertSafeProtocolBody, canonicalizeModPackForExport, validatePackInvariants } from '@/domain/modPack/modProtocol'

const props = defineProps<{
  show: boolean
  nodes: PromptNode[]
}>()

const emit = defineEmits<{
  (e: 'close'): void
  (e: 'created', pack: NarrativeModPack): void
}>()

const message = useMessage()
const modHubStore = useModHubStore()

const roleOptions = MOD_ROLE_CATEGORIES.filter(c => c.key !== 'all') as Array<{
  key: Exclude<ModRoleCategory, 'all'>
  label: string
}>

const form = reactive({
  name: '',
  glyph: '',
  author: '',
  roleCategory: 'style-anti-ai' as Exclude<ModRoleCategory, 'all'>,
  summary: '',
  scenario: '',
  beforeExcerpt: '',
  afterExcerpt: '',
  recommendedModelTier: '' as ModRecommendedModelTier | '',
  openingBeatTemplate: '',
  reviewRedlines: [] as string[],
  antiAiWordlist: [] as string[],
})

const maskRef = ref<HTMLElement | null>(null)
const dialogRef = ref<HTMLElement | null>(null)
const closeBtnRef = ref<HTMLButtonElement | null>(null)
let opener: HTMLElement | null = null
let inertNodes: Array<{ el: HTMLElement; inert: boolean }> = []
let sessionEpoch = 0
let unmounted = false
const nodeFilter = ref('')
const selectedKeys = ref<string[]>([])
const submitting = ref(false)
const ruleDraft = ref('')
const wordDraft = ref('')
const tierOptions: Array<{ value: ModRecommendedModelTier | ''; label: string }> = [
  { value: '', label: '不限档位' }, { value: 'flagship', label: '旗舰主写档' },
  { value: 'balanced', label: '均衡主力档' }, { value: 'economy', label: '轻量省额档' },
]
const selectedTierHint = computed(() => form.recommendedModelTier ? MOD_RECOMMENDED_MODEL_TIER_META[form.recommendedModelTier].hint : '不限定模型档位，按当前创作配置运行')

function isSessionActive(epoch: number): boolean {
  return !unmounted && props.show && sessionEpoch === epoch
}

function requestClose(): void {
  if (submitting.value) return
  emit('close')
}

function loadStarter() {
  if (submitting.value) return
  form.openingBeatTemplate = '【起笔意象】以一处具象时辰、气候或器物细节切入，点出主角眼下的处境：\n【骤然失衡】一桩无法推脱的来客、旧账或异变逼近，迫使主角当场做出应对：\n【首章留钩】表面风波暂歇，却在末句动作或物件上翻出更深一层的悬念：'
}

function addEntries(kind: 'rules' | 'words'): boolean {
  const draft = kind === 'rules' ? ruleDraft : wordDraft
  const entries = draft.value.split(kind === 'rules' ? /[\r\n]+/ : /[\r\n,，、;；]+/).map(v => v.trim()).filter(Boolean)
  if (!entries.length) return true
  const limit = kind === 'rules' ? 24 : 64
  const maxLength = kind === 'rules' ? 240 : 64
  try {
    for (const entry of entries) {
      assertSafeProtocolBody(entry, kind === 'rules' ? '审稿红线' : '巡检词汇')
      if (entry.length > maxLength) throw new Error(`每项最多 ${maxLength} 字，请缩短后添入`)
    }
    const current = kind === 'rules' ? form.reviewRedlines : form.antiAiWordlist
    const merged = [...new Set([...current, ...entries])]
    if (merged.length > limit) throw new Error(`最多可添入 ${limit} 项，请先精简清单`)
    if (kind === 'rules') form.reviewRedlines = merged
    else form.antiAiWordlist = merged
    draft.value = ''
    return true
  } catch (error) {
    message.warning(error instanceof Error ? error.message : '输入内容无效')
    return false
  }
}

function resetBuilderForm(seedDefaultNodes = false): void {
  form.name = ''
  form.glyph = ''
  form.author = ''
  form.roleCategory = 'style-anti-ai'
  form.summary = ''
  form.scenario = ''
  form.beforeExcerpt = ''
  form.afterExcerpt = ''
  form.recommendedModelTier = ''
  form.openingBeatTemplate = ''
  form.reviewRedlines = []
  form.antiAiWordlist = []
  ruleDraft.value = ''
  wordDraft.value = ''
  nodeFilter.value = ''
  selectedKeys.value = seedDefaultNodes
    ? props.nodes.filter(n => n.has_user_edit).map(n => n.node_key).slice(0, 6)
    : []
}

function restoreModalBackground(): void {
  document.removeEventListener('keydown', handleKeys, true)
  for (const node of inertNodes) {
    node.el.inert = node.inert
  }
  inertNodes = []
  if (opener?.isConnected) opener.focus()
  opener = null
}

function handleKeys(event: KeyboardEvent) {
  if (!props.show) return
  if (event.key === 'Escape') {
    event.preventDefault()
    event.stopPropagation()
    requestClose()
    return
  }
  if (event.key !== 'Tab') return
  const selector = submitting.value
    ? 'button:not(:disabled), input:not(:disabled), textarea:not(:disabled), select:not(:disabled)'
    : 'button:not(:disabled), input:not(:disabled), textarea:not(:disabled), select:not(:disabled), summary'
  const items = Array.from(dialogRef.value?.querySelectorAll<HTMLElement>(selector) ?? []).filter(
    el => el.getClientRects().length > 0 && window.getComputedStyle(el).visibility !== 'hidden',
  )
  const first = items[0]
  const last = items[items.length - 1]
  if (!first || !last) {
    event.preventDefault()
    dialogRef.value?.focus()
    return
  }
  const active = document.activeElement
  const outsideOrContainer = active === dialogRef.value || !dialogRef.value?.contains(active)
  if (event.shiftKey && (active === first || outsideOrContainer)) {
    event.preventDefault()
    last.focus()
  } else if (!event.shiftKey && (active === last || outsideOrContainer)) {
    event.preventDefault()
    first.focus()
  }
}

watch(
  () => props.show,
  async (open) => {
    sessionEpoch += 1
    submitting.value = false
    if (!open) {
      resetBuilderForm(false)
      restoreModalBackground()
      return
    }
    const openEpoch = sessionEpoch
    opener = document.activeElement instanceof HTMLElement ? document.activeElement : null
    resetBuilderForm(true)
    document.addEventListener('keydown', handleKeys, true)
    await nextTick()
    if (!isSessionActive(openEpoch)) return
    for (const child of Array.from(document.body.children)) {
      if (child instanceof HTMLElement && child !== maskRef.value && !child.contains(maskRef.value)) {
        inertNodes.push({ el: child, inert: child.inert })
        child.inert = true
      }
    }
    closeBtnRef.value?.focus() ?? dialogRef.value?.focus()
  },
  { immediate: true },
)

onBeforeUnmount(() => {
  unmounted = true
  sessionEpoch += 1
  restoreModalBackground()
})

const sortedNodes = computed(() => {
  const q = nodeFilter.value.trim().toLowerCase()
  const list = q
    ? props.nodes.filter(
        n =>
          n.name.toLowerCase().includes(q) ||
          n.node_key.toLowerCase().includes(q),
      )
    : props.nodes
  return [...list].sort((a, b) => {
    if (a.has_user_edit !== b.has_user_edit) return a.has_user_edit ? -1 : 1
    return a.name.localeCompare(b.name, 'zh-CN')
  })
})

const canSubmit = computed(
  () => form.name.trim().length > 0 && selectedKeys.value.length > 0,
)

interface BuilderSubmissionSnapshot {
  epoch: number
  packId: string
  keys: string[]
  name: string
  glyph: string
  author: string
  roleCategory: Exclude<ModRoleCategory, 'all'>
  summary: string
  scenario: string
  beforeExcerpt: string
  afterExcerpt: string
  recommendedModelTier: ModRecommendedModelTier | ''
  openingBeatTemplate: string
  reviewRedlines: string[]
  antiAiWordlist: string[]
  nodesSnapshot: PromptNode[]
}

function clonePromptNodeSnapshot(node: PromptNode): PromptNode {
  return {
    ...node,
    tags: Array.isArray(node.tags) ? [...node.tags] : [],
    variable_names: Array.isArray(node.variable_names) ? [...node.variable_names] : [],
    variables: Array.isArray(node.variables)
      ? node.variables.map(v => ({
          ...v,
          default:
            v.default !== undefined && typeof v.default === 'object' && v.default !== null
              ? JSON.parse(JSON.stringify(v.default))
              : v.default,
        }))
      : [],
  }
}

function captureSubmissionSnapshot(epoch: number): BuilderSubmissionSnapshot {
  const cleanName = form.name.trim()
  const keys = [...selectedKeys.value]
  if (!cleanName || keys.length === 0) {
    throw new Error('请填写模组名称并至少选择一个引擎节点')
  }
  if (/[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]/.test(form.openingBeatTemplate)) {
    throw new Error('开篇节拍支架包含非法控制字符')
  }
  const normalizedBeat = form.openingBeatTemplate.replace(/\r\n?/g, '\n').trim()
  if (form.openingBeatTemplate.length > 0 && !normalizedBeat) {
    throw new Error('开篇节拍支架不能为空白字符串；不使用时请清空输入框')
  }
  if (normalizedBeat) {
    assertSafeProtocolBody(normalizedBeat, '开篇节拍支架')
    if (normalizedBeat.length > 4000) {
      throw new Error('开篇节拍支架超出 4000 字符上限')
    }
  }
  const packId = `mod-custom-${Date.now().toString(36)}`
  const glyph = (form.glyph.trim() || cleanName.charAt(0) || '模').slice(0, 2)
  const author = form.author.trim() || '本地创作者'
  const reviewRedlines = [...form.reviewRedlines]
  const antiAiWordlist = [...form.antiAiWordlist]
  validatePackInvariants({
    id: packId,
    name: cleanName,
    glyph,
    author,
    repoOrOrigin: '本地打包工坊',
    trustLevel: 'local',
    roleCategory: form.roleCategory,
    roleLabel: '自定义模组',
    summary: cleanName,
    readmeSections: [{ heading: '模组说明', body: cleanName }],
    version: 'v1.0.0',
    license: 'MIT',
    updatedAt: '2026-01-01',
    usageLabel: '本地自制',
    replacesBuiltin: false,
    overrides: keys.map(k => ({
      nodeKey: k,
      nodeLabel: k,
      mode: 'append_protocol' as const,
      systemContent: 'preflight',
    })),
    tags: [],
    ...(form.recommendedModelTier ? { recommendedModelTier: form.recommendedModelTier } : {}),
    ...(normalizedBeat ? { openingBeatTemplate: normalizedBeat } : {}),
    ...(reviewRedlines.length ? { reviewRedlines } : {}),
    ...(antiAiWordlist.length ? { antiAiWordlist } : {}),
  })
  return {
    epoch,
    packId,
    keys,
    name: cleanName,
    glyph,
    author,
    roleCategory: form.roleCategory,
    summary: form.summary.trim(),
    scenario: form.scenario.trim(),
    beforeExcerpt: form.beforeExcerpt.trim(),
    afterExcerpt: form.afterExcerpt.trim(),
    recommendedModelTier: form.recommendedModelTier,
    openingBeatTemplate: normalizedBeat,
    reviewRedlines,
    antiAiWordlist,
    nodesSnapshot: props.nodes.map(clonePromptNodeSnapshot),
  }
}

async function assemblePack(
  snapshot: BuilderSubmissionSnapshot,
  forLocalInstall = false,
): Promise<NarrativeModPack | null> {
  const overrides: ModNodeOverride[] = []
  for (const key of snapshot.keys) {
    const detail = (await promptPlazaApi.getNodeDetail(key)) as unknown as PromptNodeDetail
    if (!isSessionActive(snapshot.epoch)) return null
    const cleanedSystem = stripModDelimiterComments(detail.system || '').trim()
    overrides.push({
      nodeKey:
        !detail.is_builtin && forLocalInstall
          ? `${snapshot.packId}-${detail.node_key}`.slice(0, 120)
          : detail.node_key,
      nodeLabel: detail.name,
      mode: detail.is_builtin ? 'replace_system' : 'standalone_node',
      systemContent: cleanedSystem || `### ${detail.name}\n${detail.description || snapshot.name}`,
      userTemplate: detail.user_template || undefined,
      backendCategory: detail.category,
    })
  }

  const roleMeta = roleOptions.find(r => r.key === snapshot.roleCategory)

  const rawPack: NarrativeModPack = {
    ...(snapshot.recommendedModelTier ? { recommendedModelTier: snapshot.recommendedModelTier } : {}),
    ...(snapshot.openingBeatTemplate ? { openingBeatTemplate: snapshot.openingBeatTemplate } : {}),
    ...(snapshot.reviewRedlines.length ? { reviewRedlines: [...snapshot.reviewRedlines] } : {}),
    ...(snapshot.antiAiWordlist.length ? { antiAiWordlist: [...snapshot.antiAiWordlist] } : {}),
    id: snapshot.packId,
    name: snapshot.name,
    glyph: snapshot.glyph,
    author: snapshot.author,
    repoOrOrigin: '本地打包工坊',
    trustLevel: 'local',
    roleCategory: snapshot.roleCategory,
    roleLabel: roleMeta?.label || '自定义模组',
    summary:
      snapshot.summary ||
      `由 ${snapshot.author} 封装的叙事模组，包含 ${overrides.length} 个引擎节点配置。`,
    readmeSections: [
      {
        heading: '模组说明',
        body:
          snapshot.summary ||
          `包含对 ${overrides.map(o => o.nodeLabel).join('、')} 的定制化提示词调优。`,
      },
    ],
    version: 'v1.0.0',
    license: 'MIT',
    updatedAt: new Date().toISOString().slice(0, 10),
    usageLabel: '本地自制',
    replacesBuiltin: overrides.some(o => o.mode !== 'standalone_node'),
    overrides,
    showcase:
      snapshot.beforeExcerpt && snapshot.afterExcerpt
        ? {
            scenario: snapshot.scenario || '创作实测片段',
            beforeExcerpt: snapshot.beforeExcerpt,
            afterExcerpt: snapshot.afterExcerpt,
          }
        : undefined,
    tags: [roleMeta?.label || '自定义', `${overrides.length} 节点`],
  }
  const canonicalPack = canonicalizeModPackForExport(rawPack)
  validatePackInvariants(canonicalPack)
  return canonicalPack
}

async function handleExportFile(): Promise<void> {
  if (!canSubmit.value || submitting.value) return
  if (!addEntries('rules') || !addEntries('words')) return
  const submitEpoch = sessionEpoch
  let snapshot: BuilderSubmissionSnapshot
  try {
    snapshot = captureSubmissionSnapshot(submitEpoch)
  } catch (e) {
    message.warning(e instanceof Error ? e.message : '打包失败')
    return
  }
  submitting.value = true
  try {
    const pack = await assemblePack(snapshot, false)
    if (!pack || !isSessionActive(submitEpoch)) return
    const manifest = modHubStore.createManifestFromPack(pack)
    const blob = new Blob([JSON.stringify(manifest, null, 2)], {
      type: 'application/json',
    })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'plotpilot-mod.json'
    a.click()
    URL.revokeObjectURL(url)
    message.success('已导出 plotpilot-mod.json 清单文件')
    resetBuilderForm(false)
    emit('created', pack)
    emit('close')
  } catch (e) {
    if (isSessionActive(submitEpoch)) {
      message.warning(e instanceof Error ? e.message : '打包失败')
    }
  } finally {
    if (sessionEpoch === submitEpoch) {
      submitting.value = false
    }
  }
}

async function handleSaveLocal(): Promise<void> {
  if (!canSubmit.value || submitting.value) return
  if (!addEntries('rules') || !addEntries('words')) return
  const submitEpoch = sessionEpoch
  let snapshot: BuilderSubmissionSnapshot
  try {
    snapshot = captureSubmissionSnapshot(submitEpoch)
  } catch (e) {
    message.warning(e instanceof Error ? e.message : '保存失败')
    return
  }
  submitting.value = true
  try {
    const pack = await assemblePack(snapshot, true)
    if (!pack || !isSessionActive(submitEpoch)) return
    await modHubStore.installModPack(pack, snapshot.nodesSnapshot)
    if (!isSessionActive(submitEpoch)) return
    message.success(`已保存并启用「${pack.name}」`)
    resetBuilderForm(false)
    emit('created', pack)
    emit('close')
  } catch (e) {
    if (isSessionActive(submitEpoch)) {
      message.warning(e instanceof Error ? e.message : '保存失败')
    }
  } finally {
    if (sessionEpoch === submitEpoch) {
      submitting.value = false
    }
  }
}
</script>

<style scoped>
.builder-mask { position: fixed; inset: 0; z-index: 3150; background: rgba(22,22,21,0.48); display: flex; align-items: center; justify-content: center; padding: 20px; }
.builder-dialog { width: 100%; max-width: 760px; max-height: 90dvh; background: var(--app-page-bg, #f4f4f2); color: var(--app-text-primary, #161615); border: none; border-radius: 3px; display: flex; flex-direction: column; overflow: hidden; font-family: 'Noto Sans SC', 'PingFang SC', -apple-system, BlinkMacSystemFont, sans-serif; font-size: 14px; }
.builder-dialog :focus-visible { outline: 1.5px solid var(--color-brand, #1f5e5b); outline-offset: 2px; }
.builder-head, .builder-foot { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; padding: 20px 24px; }
.builder-head { border-bottom: 1px solid var(--app-divider, rgba(22,22,21,0.08)); }
.builder-title { margin: 0; font-size: 24px; font-family: 'Noto Serif SC', 'Source Han Serif SC', 'Songti SC', serif; }
.builder-sub, .foot-hint, .extension-hint { margin: 6px 0 0; font-size: 14px; line-height: 1.65; color: var(--app-text-muted, #595953); max-width: 58ch; }
.builder-fieldset { border: none; margin: 0; padding: 0; min-width: 0; }
.builder-body { flex: 1; min-height: 0; overflow-y: auto; padding: 20px 24px; }
.builder-stack { display: flex; flex-direction: column; gap: 24px; }
.form-grid { display: grid; grid-template-columns: 1fr 92px; gap: 16px; }
.field-item, .node-picker-block, .showcase-fields, .extension-editor { display: flex; flex-direction: column; gap: 10px; min-width: 0; }
.field-label { font-size: 14px; font-weight: 500; color: var(--app-text-secondary, #4a4a46); }
.field-input, .field-textarea, .picker-search, .beat-input { box-sizing: border-box; min-width: 0; width: 100%; border: none; border-radius: 3px; background: var(--app-surface-subtle, #ecece8); color: var(--app-text-primary, #161615); font-size: 15px; padding: 12px; font-family: inherit; }
.field-textarea, .beat-input { resize: vertical; }
.beat-input { background: var(--app-page-bg, #f4f4f2); font-size: 16px; font-family: 'Noto Serif SC', 'Source Han Serif SC', 'Songti SC', serif; max-width: 58ch; line-height: 1.75; }
.extension-editor { background: var(--app-surface, #ffffff); padding: 20px; }
.extension-editor h4 { margin: 12px 0 0; font-size: 18px; font-family: 'Noto Serif SC', 'Source Han Serif SC', 'Songti SC', serif; }
.picker-head, .entry-controls, .tier-options, .foot-btns { display: flex; align-items: center; flex-wrap: wrap; gap: 8px; }
.picker-search { max-width: 240px; }
.picker-list { max-height: 220px; overflow-y: auto; background: var(--app-surface, #ffffff); padding: 8px; }
.picker-row { display: flex; align-items: center; flex-wrap: wrap; gap: 8px; padding: 12px; font-size: 14px; cursor: pointer; }
.picker-row.is-checked { background: var(--app-surface-subtle, #ecece8); }
.picker-node-key { color: var(--app-text-muted, #595953); font-size: 14px; overflow-wrap: anywhere; }
.edited-pill { margin-left: auto; color: var(--app-text-secondary, #4a4a46); font-size: 14px; }
.showcase-details { background: var(--app-surface, #ffffff); padding: 16px; }
.showcase-summary { cursor: pointer; font-size: 14px; }
.showcase-pair { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.builder-close, .builder-btn, .quiet-btn, .tier-options button, .word-token button { min-height: 44px; padding: 8px 12px; border: none; border-radius: 3px; background: var(--app-surface-subtle, #ecece8); color: var(--app-text-secondary, #4a4a46); font-family: inherit; font-size: 14px; cursor: pointer; }
.builder-close { min-width: 44px; flex-shrink: 0; background: transparent; }
.builder-btn.is-primary { background: var(--color-brand, #1f5e5b); color: var(--app-text-inverse, #ffffff); max-width: 168px; }
.builder-btn:disabled { opacity: 0.56; cursor: not-allowed; }
.builder-foot { flex-wrap: wrap; background: var(--app-surface-subtle, #ecece8); }
.foot-btns { margin-left: auto; }
.foot-hint { max-width: 58ch; }
.quiet-btn { align-self: flex-start; }
.tier-options button { border-bottom: 2px solid transparent; }
.tier-options button.is-selected { border-bottom-color: var(--color-brand, #1f5e5b); color: var(--app-text-primary, #161615); }
.rule-entry { display: flex; align-items: flex-start; gap: 8px; border-bottom: 1px solid var(--app-divider, rgba(22,22,21,0.08)); padding: 12px 0; }
.rule-entry:last-child { border-bottom: none; }
.rule-entry > span { flex: 0 0 64px; font-size: 14px; color: var(--app-text-muted, #595953); }
.rule-entry p { margin: 0; flex: 1; font-size: 15px; line-height: 1.65; overflow-wrap: anywhere; }
.entry-controls > input, .entry-controls > textarea { flex: 1 1 180px; }
.words-pool { padding: 12px; background: var(--app-page-bg, #f4f4f2); display: flex; flex-wrap: wrap; gap: 8px; }
.word-token { padding-left: 12px; display: inline-flex; align-items: center; background: var(--app-surface, #ffffff); font-size: 14px; overflow-wrap: anywhere; }
.word-token button { min-width: 44px; background: transparent; }
.numeric { font-variant-numeric: tabular-nums; }
@media (max-width: 640px) { .builder-mask { padding: 12px; } .builder-head, .builder-body, .builder-foot { padding: 16px; } .extension-editor { padding: 12px; } .form-grid, .showcase-pair { grid-template-columns: 1fr; } .foot-btns { margin-left: 0; flex-wrap: nowrap; } }
</style>
