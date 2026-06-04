<script setup lang="ts">
import { useMessage } from 'naive-ui'
import { computed, onBeforeUnmount, ref, watch } from 'vue'

import { useAIInvocationStore } from '../../stores/aiInvocationStore'

const store = useAIInvocationStore()
const message = useMessage()
const promptDraftSystem = ref('')
const promptDraftUser = ref('')
let previewTimer: ReturnType<typeof setTimeout> | null = null

const statusType = computed(() => {
  const status = store.session?.status
  if (status === 'completed') return 'success'
  if (status === 'blocked' || status === 'failed') return 'error'
  if (status === 'awaiting_acceptance' || status === 'awaiting_commit') return 'warning'
  return 'info'
})

const variableSnapshotGroups = computed(() => store.variableSnapshotGroups ?? [])
const hasVariableSnapshot = computed(() => variableSnapshotGroups.value.some(
  (group) => (group.items?.length ?? 0) > 0,
))
const visibleVariableSnapshotGroups = computed(() =>
  variableSnapshotGroups.value.filter(group => (group.items?.length ?? 0) > 0),
)
const expandedVariableGroups = ref<string[]>([])
const expandedPromptGroups = ref<string[]>([])
const promptDraftValidationErrors = computed(() => {
  if (!isDraftEditable.value) return []
  const items: string[] = []
  if (!promptDraftSystem.value.trim()) items.push('系统提示词不能为空')
  if (!promptDraftUser.value.trim()) items.push('用户提示词不能为空')
  return items
})
const diagnostics = computed(() => {
  const items = [
    ...promptDraftValidationErrors.value,
    ...(store.session?.variable_plan?.diagnostics ?? []),
    ...(store.draftDiagnostics ?? []),
  ]
  return Array.from(new Set(items.filter(Boolean)))
})
const missingVariables = computed(() =>
  store.promptDraftPreview?.variable_plan?.required_missing
  ?? store.session?.variable_plan?.required_missing
  ?? [],
)
const missingVariableDrafts = ref<Record<string, string>>({})
const canEditVariables = computed(() => ['blocked', 'awaiting_pre_call_review'].includes(String(store.session?.status || '')))
const hasPrompt = computed(() => Boolean(
  store.draftSystemTemplate
  || store.draftUserTemplate
  || store.draftRuntimeSystem
  || store.draftRuntimeUser,
))
const isPreCallBlocked = computed(() => store.session?.status === 'blocked' && !store.attempt?.id && !store.decision?.id)
const isDraftEditable = computed(() => store.session?.status === 'awaiting_pre_call_review' || isPreCallBlocked.value)
const originalSystemTemplate = computed(() => store.session?.prompt_snapshot?.template_prompt?.system ?? '')
const originalUserTemplate = computed(() => store.session?.prompt_snapshot?.template_prompt?.user ?? '')
const systemPromptDraftChanged = computed(() => promptDraftSystem.value !== originalSystemTemplate.value)
const userPromptDraftChanged = computed(() => promptDraftUser.value !== originalUserTemplate.value)
const runtimePromptSystem = computed(() => (
  promptDraftSystem.value.trim() ? store.draftRuntimeSystem : ''
))
const runtimePromptUser = computed(() => (
  promptDraftUser.value.trim() ? store.draftRuntimeUser : ''
))
const hasCommitSteps = computed(() => Boolean(store.commit?.steps?.length))
const showLiveAttempt = computed(() => Boolean(store.attempt?.id))
const showOutputPreview = computed(() => store.hasAttempt && !store.isGenerating && outputPreviewRows.value.length > 0)
const drawerTitle = computed(() => `AI 调试面板：${store.session?.operation || store.session?.node_key || '未加载'}`)
const drawerWidth = '66.666vw'
interface OutputBindingRow {
  targetDisplayName: string
  jsonPath: string
  target: string
  alias: string
  previewSource: string
}

const outputRuleIntro = computed(() => {
  if (!outputBindings.value.length) return ''
  return '变量中心底层是 key/value；这里展示的是当前节点采纳后允许写入的输出绑定，不是变量中心的完整结构定义。'
})
const outputRuleTips = computed(() => {
  if (!outputBindings.value.length) return []
  return [
    '按本步骤既定结构直接输出结果，不要额外包一层说明文字。',
    '已经约定的字段名保持稳定，不要自行改名，也不要把顶层字段套进别的对象。',
    '列表内容直接输出数组，对象内容保持结构完整。',
    '只有当前节点已绑定的变量会写入变量中心；如需新增独立变量，需要先扩展节点输出绑定。',
  ]
})

const outputBindings = computed<OutputBindingRow[]>(() =>
  (store.session?.output_bindings ?? [])
    .filter(item => Boolean(item.alias))
    .map(item => ({
      targetDisplayName: item.target_display_name || '',
      jsonPath: item.source_path || item.alias,
      target: item.variable_key || item.alias,
      alias: item.alias,
      previewSource: item.preview_source || '',
    })),
)
const promptSystemHint = computed(() => {
  if (isDraftEditable.value) return '当前编辑的是 session 草稿，不直接污染 CPMS 正式版本'
  return '当前为只读预览'
})
const promptUserHint = computed(() => {
  if (isDraftEditable.value) return '左侧可直接修改用户模板变量与结构'
  return '当前为只读预览'
})

watch(
  [() => store.draftSystemEdited, () => store.draftUserEdited],
  ([systemValue, userValue]) => {
    promptDraftSystem.value = systemValue
    promptDraftUser.value = userValue
  },
  { immediate: true },
)

watch(
  () => [store.visible, store.session?.id],
  () => {
    expandedPromptGroups.value = []
    expandedVariableGroups.value = []
    missingVariableDrafts.value = {}
  },
  { immediate: true },
)

watch(missingVariables, (items) => {
  const next = { ...missingVariableDrafts.value }
  for (const alias of items) {
    if (!(alias in next)) next[alias] = ''
  }
  missingVariableDrafts.value = next
}, { immediate: true })

watch([promptDraftSystem, promptDraftUser], ([systemValue, userValue]) => {
  if (!store.session?.id || !isDraftEditable.value) return
  if (previewTimer) window.clearTimeout(previewTimer)
  if (!systemValue.trim() || !userValue.trim()) {
    store.clearPromptDraftPreview()
    return
  }
  previewTimer = window.setTimeout(() => {
    void store.previewPromptDraft(systemValue, userValue).catch(() => {
      // 预览失败时保留旧快照，由页面诊断区提示。
    })
  }, 350)
})

onBeforeUnmount(() => {
  if (previewTimer) window.clearTimeout(previewTimer)
})

function formatValue(value: unknown): string {
  if (value == null) return ''
  if (typeof value === 'string') return value
  try {
    return JSON.stringify(value, null, 2)
  } catch {
    return String(value)
  }
}

function snapshotGroupName(group: { id?: string; scope?: string; stage?: string }): string {
  return group.id || `${group.scope || 'runtime'}:${group.stage || 'runtime'}`
}

function formatScope(scope?: string): string {
  const labels: Record<string, string> = {
    global: '全局变量',
    novel: '小说变量',
    chapter: '章节变量',
    scene: '场景变量',
    beat: '节拍变量',
    runtime: '运行时变量',
  }
  return labels[scope || 'runtime'] || scope || '运行时变量'
}

function formatStage(stage?: string): string {
  const labels: Record<string, string> = {
    setup: '设定',
    worldbuilding: '世界观',
    characters: '人物',
    locations: '地点',
    planning: '规划',
    writing: '写作',
    review: '审阅',
    postprocess: '后处理',
    runtime: '运行时',
  }
  return labels[stage || 'runtime'] || stage || '运行时'
}

function snapshotGroupTitle(group: { title?: string; scope?: string; stage?: string; items?: unknown[] }): string {
  const base = group.title || `${formatScope(group.scope)} · ${formatStage(group.stage)}`
  const count = group.items?.length || 0
  return count > 0 ? `${base}（${count}项）` : base
}

function formatType(type?: string): string {
  return type || '文本'
}

function formatSource(source?: string): string {
  if (!source) return '-'
  if (source.startsWith('materialized:')) return `派生上下文 · ${source.replace('materialized:', '')}`
  if (source === 'variable_hub') return '变量中心'
  if (source === 'explicit') return '显式输入'
  if (source === 'default') return '默认值'
  return source
}

async function handleResume() {
  if (promptDraftValidationErrors.value.length > 0) {
    message.error(promptDraftValidationErrors.value[0])
    return
  }
  if (isDraftEditable.value) {
    await store.savePromptDraft(promptDraftSystem.value, promptDraftUser.value)
  }
  if (missingVariables.value.length > 0) {
    await handleSaveMissingVariables()
  }
  if (store.session?.status === 'blocked') return
  await store.resume()
}

async function handleSaveMissingVariables() {
  const values: Record<string, unknown> = {}
  for (const alias of missingVariables.value) {
    const value = missingVariableDrafts.value[alias]
    if (value != null && String(value).trim() !== '') {
      values[alias] = value
    }
  }
  if (!Object.keys(values).length) return
  await store.updateVariables(values)
}

async function handleRetry() {
  await store.retry()
}

function parseAttemptContent(): Record<string, unknown> | null {
  const raw = store.attempt?.content || ''
  if (!raw.trim()) return null
  const candidates = [
    raw.trim(),
    extractJsonFromMarkdown(raw),
    extractOuterJson(raw),
  ].filter(Boolean) as string[]
  for (const candidate of candidates) {
    try {
      return JSON.parse(candidate) as Record<string, unknown>
    } catch {
      const recovered = recoverTruncatedArrayObject(candidate, 'characters')
        || recoverTruncatedArrayObject(candidate, 'locations')
      if (recovered) return recovered
      // Try the next candidate. LLM output often includes prose or code fences.
    }
  }
  return null
}

function extractJsonFromMarkdown(raw: string): string {
  const fenced = raw.match(/```(?:json)?\s*([\s\S]*?)```/i)
  return fenced?.[1]?.trim() || ''
}

function extractOuterJson(raw: string): string {
  const start = raw.indexOf('{')
  const end = raw.lastIndexOf('}')
  if (start < 0 || end <= start) return ''
  return raw.slice(start, end + 1).trim()
}

function recoverTruncatedArrayObject(raw: string, arrayKey: string): Record<string, unknown> | null {
  const keyIndex = raw.indexOf(`"${arrayKey}"`)
  if (keyIndex < 0) return null
  const openIndex = raw.indexOf('[', keyIndex)
  if (openIndex < 0) return null

  const items: unknown[] = []
  let i = openIndex + 1
  while (i < raw.length) {
    while (i < raw.length && /[\s,]/.test(raw[i])) i += 1
    if (i >= raw.length) break
    if (raw[i] === ']') return items.length ? { [arrayKey]: items } : null
    if (raw[i] !== '{' && raw[i] !== '[') break

    const itemStart = i
    let depth = 0
    let inString = false
    let escapeNext = false
    let consumed = false

    while (i < raw.length) {
      const ch = raw[i]
      if (escapeNext) {
        escapeNext = false
      } else if (ch === '\\' && inString) {
        escapeNext = true
      } else if (ch === '"') {
        inString = !inString
      } else if (!inString) {
        if (ch === '{' || ch === '[') {
          depth += 1
        } else if (ch === '}' || ch === ']') {
          depth -= 1
          if (depth === 0) {
            const itemText = raw.slice(itemStart, i + 1)
            try {
              items.push(JSON.parse(itemText))
            } catch {
              return items.length ? { [arrayKey]: items } : null
            }
            i += 1
            consumed = true
            break
          }
        }
      }
      i += 1
    }

    if (!consumed) break
  }

  return items.length ? { [arrayKey]: items } : null
}

function pickPath(source: unknown, path: string): unknown {
  if (source == null || !path) return undefined
  const normalized = path.trim()
  if (!normalized || normalized === '$') return source
  const input = normalized.startsWith('$.')
    ? normalized.slice(2)
    : normalized.startsWith('$')
      ? normalized.slice(1).replace(/^\./, '')
      : normalized

  let current: unknown = source
  for (const segment of input.split('.').filter(Boolean)) {
    current = pickPathSegment(current, segment)
    if (current == null) return undefined
  }
  return current
}

function pickPathSegment(source: unknown, segment: string): unknown {
  const raw = segment.trim()
  if (!raw || raw === '$') return source
  if (raw === '[]' || raw === '[*]' || raw === '*') return Array.isArray(source) ? source : undefined

  if (Array.isArray(source)) {
    if (raw.startsWith('[') && raw.endsWith(']')) {
      return pickListIndex(source, raw.slice(1, -1))
    }
    const values = source
      .map(item => pickPathSegment(item, raw))
      .filter(item => item !== undefined)
    return values
  }

  let key = raw
  const selectors: string[] = []
  const bracketIndex = raw.indexOf('[')
  if (bracketIndex >= 0) {
    key = raw.slice(0, bracketIndex)
    let rest = raw.slice(bracketIndex)
    while (rest.startsWith('[')) {
      const close = rest.indexOf(']')
      if (close < 0) return undefined
      selectors.push(rest.slice(1, close))
      rest = rest.slice(close + 1)
    }
    if (rest) return undefined
  }

  let value: unknown = source
  if (key) {
    if (!value || typeof value !== 'object') return undefined
    value = (value as Record<string, unknown>)[key]
  }

  for (const selector of selectors) {
    if (selector === '' || selector === '*') {
      if (!Array.isArray(value)) return undefined
      continue
    }
    if (!Array.isArray(value)) return undefined
    value = pickListIndex(value, selector)
  }
  return value
}

function pickListIndex(values: unknown[], selector: string): unknown {
  const index = Number.parseInt(selector, 10)
  if (Number.isNaN(index)) return undefined
  const normalized = index < 0 ? values.length + index : index
  if (normalized < 0 || normalized >= values.length) return undefined
  return values[normalized]
}

function pickExactOrDottedChildren(source: unknown, key: string): unknown {
  if (!source || typeof source !== 'object' || Array.isArray(source) || !key) return undefined
  const record = source as Record<string, unknown>
  if (key in record) return record[key]
  const prefix = `${key}.`
  const nestedEntries = Object.entries(record).filter(([entryKey]) => entryKey.startsWith(prefix))
  if (!nestedEntries.length) return undefined
  const root: Record<string, unknown> = {}
  for (const [entryKey, entryValue] of nestedEntries) {
    const remainder = entryKey.slice(prefix.length)
    if (!remainder) continue
    const parts = remainder.split('.').filter(Boolean)
    if (!parts.length) continue
    let cursor: Record<string, unknown> = root
    for (const part of parts.slice(0, -1)) {
      const next = cursor[part]
      if (!next || typeof next !== 'object' || Array.isArray(next)) {
        cursor[part] = {}
      }
      cursor = cursor[part] as Record<string, unknown>
    }
    cursor[parts[parts.length - 1]] = entryValue
  }
  return Object.keys(root).length ? root : undefined
}

function resolveOutputPreviewValue(source: unknown, row: OutputBindingRow): unknown {
  const candidates = [row.jsonPath, row.alias, row.target]
  for (const candidate of candidates) {
    const normalized = candidate.trim()
    if (!normalized) continue
    const exact = pickExactOrDottedChildren(source, normalized)
    if (exact !== undefined) return exact
    const picked = pickPath(source, normalized)
    if (picked !== undefined) return picked
  }
  return undefined
}

function safeJsonPreview(value: unknown): string {
  if (value == null) return ''
  if (typeof value === 'string') return value
  try {
    return JSON.stringify(value, null, 2)
  } catch {
    return String(value)
  }
}

const parsedAttemptContent = computed(() => parseAttemptContent())
const outputPreviewRows = computed(() =>
  outputBindings.value.map(item => ({
    ...item,
    value: item.previewSource === 'continuation'
      ? undefined
      : resolveOutputPreviewValue(parsedAttemptContent.value, item),
  })),
)
</script>

<template>
  <n-drawer v-model:show="store.visible" :width="drawerWidth" :z-index="3600" placement="right">
    <n-drawer-content :title="drawerTitle" closable>
      <n-spin :show="store.loading">
        <n-space vertical :size="16">
          <n-alert v-if="store.error" type="error" :show-icon="true">
            {{ store.error }}
          </n-alert>

          <n-card size="small" title="会话状态">
            <n-space align="center" :size="12">
              <n-tag :type="statusType" size="small">
                {{ store.session?.status || '未加载' }}
              </n-tag>
              <n-text depth="3">策略：{{ store.session?.policy || '-' }}</n-text>
              <n-text depth="3">下一步：{{ store.nextAction || '-' }}</n-text>
            </n-space>
          </n-card>

          <n-alert
            v-if="store.session?.status === 'awaiting_pre_call_review'"
            type="info"
            :show-icon="true"
          >
            当前会话等待生成前审阅。左侧可修改本次 CPMS 系统词草稿，右侧会实时展示运行时系统词预览；批准生成后本次 session 使用当前草稿。
          </n-alert>
          <n-card v-if="outputBindings.length" size="small" title="本步规则说明">
            <n-text depth="3" style="display:block;margin-bottom:8px;">
              {{ outputRuleIntro }}
            </n-text>
            <n-text v-if="outputRuleTips.length" depth="3" style="display:block;margin-top:8px;">
              <div>规则说明：</div>
              <ul style="margin: 6px 0 0 18px; padding: 0;">
                <li v-for="rule in outputRuleTips" :key="rule">{{ rule }}</li>
              </ul>
            </n-text>
          </n-card>
          <n-alert
            v-if="store.session?.status === 'awaiting_acceptance'"
            type="info"
            :show-icon="true"
          >
            当前会话已完成生成，等待你确认是否采纳本次结果。若接受，将进入提交流程。
          </n-alert>

          <n-alert
            v-if="missingVariables.length > 0"
            type="warning"
            :show-icon="true"
          >
            必填变量缺失：{{ missingVariables.join('、') }}
          </n-alert>

          <n-card v-if="missingVariables.length > 0 && canEditVariables" size="small" title="补齐变量">
            <n-space vertical :size="10">
              <div v-for="alias in missingVariables" :key="alias" class="missing-variable-row">
                <n-text strong>{{ alias }}</n-text>
                <n-input
                  v-model:value="missingVariableDrafts[alias]"
                  type="textarea"
                  :autosize="{ minRows: 2, maxRows: 6 }"
                  placeholder="输入本次变量值"
                />
              </div>
              <n-space justify="end">
                <n-button
                  type="primary"
                  secondary
                  :loading="store.actionLoading"
                  @click="handleSaveMissingVariables"
                >
                  保存变量
                </n-button>
              </n-space>
            </n-space>
          </n-card>

          <n-card v-if="diagnostics.length > 0" size="small" title="诊断信息">
            <n-list>
              <n-list-item v-for="item in diagnostics" :key="item">
                {{ item }}
              </n-list-item>
            </n-list>
          </n-card>

          <n-card v-if="hasPrompt" size="small" title="提示词对照">
            <n-collapse v-model:expanded-names="expandedPromptGroups" accordion>
              <n-collapse-item title="系统提示词对照" name="system">
                <div class="prompt-compare">
                  <section class="prompt-panel">
                    <div class="prompt-panel-head">
                      <div>
                        <strong>CPMS 系统提示词</strong>
                        <n-text depth="3">{{ promptSystemHint }}</n-text>
                      </div>
                      <n-tag v-if="systemPromptDraftChanged" size="small" type="warning">已修改</n-tag>
                    </div>
                    <n-input
                      v-model:value="promptDraftSystem"
                      type="textarea"
                      class="prompt-editor"
                      :readonly="!isDraftEditable"
                      :autosize="false"
                      placeholder="暂无 CPMS 系统提示词"
                    />
                  </section>

                  <section class="prompt-panel">
                    <div class="prompt-panel-head">
                      <div>
                        <strong>运行时系统提示词</strong>
                        <n-text depth="3">按当前变量实时渲染后的调用内容</n-text>
                      </div>
                      <n-tag v-if="store.promptDraftLoading" size="small" type="info">预览中</n-tag>
                    </div>
                    <n-spin :show="store.promptDraftLoading">
                      <n-scrollbar class="ai-invocation-scroll prompt-runtime-scroll">
                        <pre class="ai-invocation-pre">{{ runtimePromptSystem }}</pre>
                      </n-scrollbar>
                    </n-spin>
                  </section>
                </div>
              </n-collapse-item>

              <n-collapse-item title="用户提示词对照" name="user">
                <div class="prompt-compare">
                  <section class="prompt-panel">
                    <div class="prompt-panel-head">
                      <div>
                        <strong>CPMS 用户提示词</strong>
                        <n-text depth="3">{{ promptUserHint }}</n-text>
                      </div>
                      <n-tag v-if="userPromptDraftChanged" size="small" type="warning">已修改</n-tag>
                    </div>
                    <n-input
                      v-model:value="promptDraftUser"
                      type="textarea"
                      class="prompt-editor"
                      :readonly="!isDraftEditable"
                      :autosize="false"
                      placeholder="暂无 CPMS 用户提示词"
                    />
                  </section>

                  <section class="prompt-panel">
                    <div class="prompt-panel-head">
                      <div>
                        <strong>运行时用户提示词</strong>
                        <n-text depth="3">按变量快照实时渲染后的最终内容</n-text>
                      </div>
                      <n-tag v-if="store.promptDraftLoading" size="small" type="info">预览中</n-tag>
                    </div>
                    <n-spin :show="store.promptDraftLoading">
                      <n-scrollbar class="ai-invocation-scroll prompt-runtime-scroll">
                        <pre class="ai-invocation-pre">{{ runtimePromptUser }}</pre>
                      </n-scrollbar>
                    </n-spin>
                  </section>
                </div>
              </n-collapse-item>
            </n-collapse>
          </n-card>

          <n-card size="small" title="变量快照">
            <n-empty v-if="!hasVariableSnapshot" description="暂无变量" />
            <n-collapse v-else v-model:expanded-names="expandedVariableGroups">
              <n-collapse-item
                v-for="group in visibleVariableSnapshotGroups"
                :key="snapshotGroupName(group)"
                :title="snapshotGroupTitle(group)"
                :name="snapshotGroupName(group)"
              >
                <div class="snapshot-group-meta">
                  <n-tag size="small" round>{{ formatScope(group.scope) }}</n-tag>
                  <n-tag size="small" round type="info">{{ formatStage(group.stage) }}</n-tag>
                  <n-tag size="small" round type="default">{{ group.items?.length || 0 }} 项</n-tag>
                </div>
                <n-space vertical :size="10">
                  <n-card
                    v-for="item in group.items || []"
                    :key="item.key"
                    size="small"
                    class="snapshot-item-card"
                  >
                    <div class="snapshot-item-head">
                      <div class="snapshot-item-title">
                        <strong>{{ item.display_name || item.key }}</strong>
                        <n-text depth="3">变量名：{{ item.key }}</n-text>
                      </div>
                      <n-space :size="8">
                        <n-tag size="small" type="default">类型：{{ formatType(item.type) }}</n-tag>
                        <n-tag v-if="item.required" size="small" type="warning">必填</n-tag>
                      </n-space>
                    </div>
                    <n-space :size="8" wrap>
                      <n-tag size="small" type="info">来源：{{ formatSource(item.source || item.variable_key) }}</n-tag>
                      <n-tag v-if="String(item.source || '').startsWith('materialized:')" size="small" type="warning">
                        派生上下文
                      </n-tag>
                      <n-tag v-if="item.source_path" size="small" type="default">
                        路径：{{ item.source_path }}
                      </n-tag>
                      <n-tag v-if="item.projection_key" size="small" type="success">
                        投影：{{ item.projection_key }}
                      </n-tag>
                      <n-tag v-if="item.render_mode && item.render_mode !== 'raw'" size="small" type="default">
                        渲染：{{ item.render_mode }}
                      </n-tag>
                    </n-space>
                    <pre class="ai-invocation-value">{{ formatValue(item.value) }}</pre>
                  </n-card>
                </n-space>
              </n-collapse-item>
            </n-collapse>
          </n-card>

          <n-card v-if="showLiveAttempt" size="small" title="AI 实时输出">
            <n-space align="center" justify="space-between" style="margin-bottom: 10px;">
              <n-text depth="3">
                {{ store.isGenerating ? '生成中，内容会逐步刷新' : '展示当前 attempt 的完整输出' }}
              </n-text>
              <n-tag v-if="store.liveAttemptLoading" size="small" type="info">轮询中</n-tag>
            </n-space>
            <n-alert v-if="store.attempt?.error" type="error" :show-icon="true">
              {{ store.attempt.error }}
            </n-alert>
            <n-spin v-else :show="store.liveAttemptLoading && !store.liveAttemptDisplay">
              <n-scrollbar class="ai-invocation-result">
                <pre class="ai-invocation-pre">{{ store.liveAttemptDisplay || '暂无输出' }}</pre>
              </n-scrollbar>
            </n-spin>
          </n-card>

          <n-card v-if="showOutputPreview" size="small" title="变量中心写入预览">
            <n-list>
              <n-list-item v-for="row in outputPreviewRows" :key="row.jsonPath">
                <div class="output-preview-row">
                  <div class="output-preview-row__head">
                    <strong>{{ row.target }}</strong>
                    <n-text depth="3">提取路径：{{ row.jsonPath }}</n-text>
                    <n-text v-if="row.targetDisplayName" depth="3">变量中心名称：{{ row.targetDisplayName }}</n-text>
                  </div>
                  <pre
                    v-if="row.previewSource !== 'continuation'"
                    class="ai-invocation-value"
                  >{{ safeJsonPreview(row.value) || '未生成 / 解析失败' }}</pre>
                  <pre
                    v-else
                    class="ai-invocation-value"
                  >采纳后由 continuation 派生，不从 AI 原文直接解析</pre>
                </div>
              </n-list-item>
            </n-list>
          </n-card>

          <n-card v-if="store.decision" size="small" title="采纳决策">
            <n-space align="center">
              <n-tag type="success">{{ store.decision.decision }}</n-tag>
              <n-text depth="3">决策 ID：{{ store.decision.id }}</n-text>
            </n-space>
          </n-card>

          <n-card v-if="hasCommitSteps" size="small" title="提交步骤">
            <n-timeline>
              <n-timeline-item
                v-for="step in store.commit?.steps"
                :key="step.name"
                :type="step.status === 'succeeded' ? 'success' : step.status === 'failed' ? 'error' : 'info'"
                :title="step.name"
                :content="step.status"
              />
            </n-timeline>
          </n-card>
        </n-space>
      </n-spin>

      <template #footer>
        <n-space justify="end">
          <n-button @click="store.close">关闭</n-button>
          <n-button
            v-if="store.session?.status === 'awaiting_pre_call_review' || isPreCallBlocked"
            type="primary"
            :loading="store.actionLoading || store.promptDraftLoading"
            @click="handleResume"
          >
            {{ isPreCallBlocked ? '保存并继续' : '批准生成' }}
          </n-button>
          <n-button v-if="store.canRetry" :loading="store.actionLoading" @click="handleRetry">
            重新生成
          </n-button>
          <n-button
            v-if="store.canAccept"
            type="primary"
            :loading="store.actionLoading"
            @click="store.accept"
          >
            采纳
          </n-button>
          <n-button
            v-if="store.canCommit"
            type="primary"
            :loading="store.actionLoading"
            @click="store.runCommit"
          >
            提交
          </n-button>
        </n-space>
      </template>
    </n-drawer-content>
  </n-drawer>
</template>

<style scoped>
.ai-invocation-scroll,
.ai-invocation-result {
  max-height: 280px;
}

.prompt-compare {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
  margin-top: 8px;
}

.prompt-panel {
  display: flex;
  flex-direction: column;
  gap: 10px;
  min-width: 0;
}

.prompt-panel-head {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: flex-start;
}

.prompt-editor {
  min-height: 300px;
}

.prompt-runtime-scroll {
  min-height: 300px;
}

.snapshot-group-meta {
  display: flex;
  gap: 8px;
  margin-bottom: 12px;
  flex-wrap: wrap;
}

.snapshot-item-card {
  border: 1px solid var(--border-color, #e5e7eb);
  background: var(--card-color, #fff);
}

.snapshot-item-head {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: flex-start;
  margin-bottom: 8px;
}

.snapshot-item-title {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.snapshot-item-source {
  display: block;
  margin-bottom: 8px;
  font-size: 12px;
}

.output-preview-row {
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-width: 0;
}

.output-preview-row__head {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: flex-start;
}

.missing-variable-row {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.ai-invocation-scroll,
.ai-invocation-result {
  max-height: 280px;
}

.ai-invocation-pre,
.ai-invocation-value {
  margin: 0;
  white-space: pre-wrap;
  word-break: break-word;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono', monospace;
  line-height: 1.65;
}

.ai-invocation-value {
  color: var(--text-color-2, #475569);
}

@media (max-width: 1200px) {
  .prompt-compare {
    grid-template-columns: 1fr;
  }
}
</style>
