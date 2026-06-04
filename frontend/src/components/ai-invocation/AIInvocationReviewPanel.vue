<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'

import { useAIInvocationStore } from '../../stores/aiInvocationStore'

const store = useAIInvocationStore()
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
const diagnostics = computed(() => {
  const items = [
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
const hasCommitSteps = computed(() => Boolean(store.commit?.steps?.length))
const showLiveAttempt = computed(() => Boolean(store.attempt?.id))
const showOutputPreview = computed(() => store.hasAttempt && !store.isGenerating && outputPreviewRows.value.length > 0)
const drawerTitle = computed(() => `AI 调试面板：${store.session?.operation || store.session?.node_key || '未加载'}`)
const drawerWidth = '66.666vw'
interface OutputBindingRow {
  label: string
  jsonPath: string
  target: string
}

const outputContractIntro = computed(() => {
  if (!outputBindings.value.length) return ''
  return 'AI 的结果只会按下面这些字段路径解析并写入系统。你调整提示词时，应要求 AI 输出同名 JSON 字段；新增未登记路径只会留在文本里，不会自动入库。'
})
const outputContractRules = computed(() => {
  if (!outputBindings.value.length) return []
  return [
    '字段名必须和契约路径完全一致，包括顶层字段和嵌套层级。',
    '顶层字段不要塞进其他对象里；例如契约写 `style`，就必须输出顶层 `style`，不能写成 `worldbuilding.style`。',
    '数组路径用 `[]` 表示列表项；例如 `characters[]` 代表输出 `characters: [...]`。',
    '如果需要新增可入库字段，需要先扩展后端输出契约/continuation 写入逻辑，再在提示词里要求 AI 输出该字段。',
  ]
})
const outputContractSkeleton = computed(() => {
  const nodeKey = store.session?.node_key || ''
  if (nodeKey === 'bible-worldbuilding') {
    return `{
  "style": "小说整体文风公约",
  "worldbuilding": {
    "core_rules": "核心法则",
    "geography": "地理生态",
    "society": "社会结构",
    "culture": "历史文化",
    "daily_life": "沉浸感细节"
  }
}`
  }
  if (nodeKey === 'bible-characters') {
    return `{
  "characters": [
    {
      "name": "角色名",
      "description": "角色设定",
      "relationships": []
    }
  ]
}`
  }
  if (nodeKey === 'bible-locations') {
    return `{
  "locations": [
    {
      "name": "地点名",
      "description": "地点设定",
      "connections": []
    }
  ]
}`
  }
  return ''
})
const outputBindings = computed<OutputBindingRow[]>(() => {
  const nodeKey = store.session?.node_key || ''
  if (nodeKey === 'bible-worldbuilding') {
    return [
      { label: '文风公约', jsonPath: 'style', target: 'Bible.style_notes[category=文风公约]' },
      { label: '核心法则', jsonPath: 'worldbuilding.core_rules', target: 'Worldbuilding.core_rules' },
      { label: '地理生态', jsonPath: 'worldbuilding.geography', target: 'Worldbuilding.geography' },
      { label: '社会结构', jsonPath: 'worldbuilding.society', target: 'Worldbuilding.society' },
      { label: '历史文化', jsonPath: 'worldbuilding.culture', target: 'Worldbuilding.culture' },
      { label: '沉浸感细节', jsonPath: 'worldbuilding.daily_life', target: 'Worldbuilding.daily_life' },
    ]
  }
  if (nodeKey === 'bible-characters') {
    return [
      { label: '主要角色', jsonPath: 'characters[]', target: 'Bible.characters' },
      { label: '人物关系', jsonPath: 'characters[].relationships', target: 'Bible.characters[].relationships / triples' },
    ]
  }
  if (nodeKey === 'bible-locations') {
    return [
      { label: '地图地点', jsonPath: 'locations[]', target: 'Bible.locations' },
      { label: '地点关系', jsonPath: 'locations[].connections', target: 'Bible.locations[].connections / triples' },
    ]
  }
  return []
})
const currentStepOutputs = computed(() =>
  outputBindings.value.map(item => `${item.label}：${item.jsonPath} → ${item.target}`),
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
    planning: '规划',
    writing: '写作',
    review: '审阅',
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

function pathSegments(path: string): Array<{ key: string; array: boolean }> {
  return path.split('.').filter(Boolean).map((part) => ({
    key: part.replace(/\[\]$/, ''),
    array: part.endsWith('[]'),
  }))
}

function collectPathValues(source: unknown, segments: Array<{ key: string; array: boolean }>): unknown {
  if (!segments.length) return source
  const [head, ...tail] = segments
  if (!source) return undefined
  if (Array.isArray(source)) {
    const mapped = source
      .map(item => collectPathValues(item, segments))
      .filter(item => item !== undefined)
    return head.array ? mapped : mapped.flat()
  }
  if (typeof source !== 'object') return undefined
  const next = (source as Record<string, unknown>)[head.key]
  if (head.array) {
    if (next == null) return undefined
    const arrayValue = Array.isArray(next) ? next : [next]
    if (!tail.length) return arrayValue
    return arrayValue
      .map(item => collectPathValues(item, tail))
      .filter(item => item !== undefined)
  }
  return collectPathValues(next, tail)
}

function pickPath(source: unknown, path: string): unknown {
  if (!source || !path) return undefined
  return collectPathValues(source, pathSegments(path))
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
    value: pickPath(parsedAttemptContent.value, item.jsonPath),
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
          <n-card v-if="currentStepOutputs.length" size="small" title="本步输出契约">
            <n-text depth="3" style="display:block;margin-bottom:8px;">
              {{ outputContractIntro }}
            </n-text>
            <n-list>
              <n-list-item v-for="item in currentStepOutputs" :key="item">
                {{ item }}
              </n-list-item>
            </n-list>
            <n-text v-if="outputContractRules.length" depth="3" style="display:block;margin-top:8px;">
              <div>定义规则：</div>
              <ul style="margin: 6px 0 0 18px; padding: 0;">
                <li v-for="rule in outputContractRules" :key="rule">{{ rule }}</li>
              </ul>
            </n-text>
            <n-text v-if="outputContractSkeleton" depth="3" style="display:block;margin-top:8px;">
              <div>推荐输出骨架：</div>
              <pre class="ai-invocation-value">{{ outputContractSkeleton }}</pre>
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
                        <pre class="ai-invocation-pre">{{ store.draftRuntimeSystem }}</pre>
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
                        <pre class="ai-invocation-pre">{{ store.draftRuntimeUser }}</pre>
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

          <n-card v-if="showOutputPreview" size="small" title="采纳写入预览">
            <n-list>
              <n-list-item v-for="row in outputPreviewRows" :key="row.jsonPath">
                <div class="output-preview-row">
                  <div class="output-preview-row__head">
                    <strong>{{ row.label }}</strong>
                    <n-text depth="3">{{ row.jsonPath }} → {{ row.target }}</n-text>
                  </div>
                  <pre class="ai-invocation-value">{{ safeJsonPreview(row.value) || '未生成 / 解析失败' }}</pre>
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
