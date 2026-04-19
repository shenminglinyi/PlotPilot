<template>
  <div class="llm-panel">
    <header class="llm-header">
      <div class="llm-header-main">
        <div class="llm-title-row">
          <h3 class="llm-title">LLM 控制台</h3>
          <n-tag size="small" round :bordered="false">Provider Control</n-tag>
        </div>
        <p class="llm-lead">
          一个面板统一管理 <strong>OpenAI / Claude / Gemini</strong> 与所有
          <strong>OpenAI / Claude / Gemini 兼容网关</strong>。
          国产模型优先走 <strong>OpenAI 兼容</strong> 模式接入。
        </p>
        <n-space :size="8" wrap>
          <n-tag size="small" type="info" round>
            运行中：{{ runtimeLabel }}
          </n-tag>
          <n-tag v-if="panelData?.runtime?.model" size="small" round>
            模型 {{ panelData?.runtime?.model }}
          </n-tag>
          <n-tag v-if="panelData?.runtime?.protocol" size="small" round>
            协议 {{ panelData?.runtime?.protocol }}
          </n-tag>
        </n-space>
      </div>
      <n-space :size="8" align="center">
        <n-button size="small" secondary :loading="loading" @click="loadPanel">刷新</n-button>
        <n-button size="small" type="primary" :loading="saving" @click="saveAll">保存配置</n-button>
      </n-space>
    </header>

    <n-alert v-if="panelData?.runtime?.using_mock" type="warning" :show-icon="true" class="llm-alert">
      {{ panelData?.runtime?.reason || '当前未配置可用模型，运行时会退回 MockProvider。' }}
    </n-alert>

    <section v-if="panelData && quickImportPresets.length" class="llm-preset-strip">
      <div class="llm-preset-strip-head">
        <div>
          <div class="llm-preset-strip-title">导入厂商预设</div>
          <div class="llm-preset-strip-desc">一键生成常用厂商配置草稿，再填 Key 即可测试。</div>
        </div>
      </div>
      <div class="llm-preset-grid">
        <button
          v-for="preset in quickImportPresets"
          :key="preset.key"
          type="button"
          class="llm-preset-card"
          @click="importPresetShortcut(preset.key)"
        >
          <span class="llm-preset-card-head">
            <span class="llm-preset-card-title">{{ preset.label }}</span>
            <span class="llm-preset-card-protocol">{{ preset.protocol }}</span>
          </span>
          <span class="llm-preset-card-model">{{ preset.default_model || '自定义模型' }}</span>
          <span class="llm-preset-card-url">{{ preset.default_base_url || '兼容网关 / 自定义 Base URL' }}</span>
        </button>
      </div>
    </section>

    <div v-if="panelData && panelData.config" class="llm-layout">
      <aside class="llm-sidebar">
        <div class="llm-sidebar-head">
          <div>
            <div class="llm-sidebar-title">配置档案</div>
            <div class="llm-sidebar-desc">可保存多组 endpoint，随时切换。</div>
          </div>
          <n-button size="tiny" secondary @click="addProfile">新增</n-button>
        </div>

        <div ref="sidebarListRef" class="llm-profile-list" @scroll="saveUiState">
          <button
            v-for="profile in panelData.config?.profiles || []"
            :key="profile.id"
            type="button"
            class="llm-profile-item"
            :class="{
              'is-active': profile.id === panelData.config?.active_profile_id,
              'is-selected': profile.id === selectedProfileId,
            }"
            @click="selectProfile(profile.id)"
          >
            <div class="llm-profile-name-row">
              <span class="llm-profile-name">{{ profile.name }}</span>
              <n-tag v-if="profile.id === panelData.config?.active_profile_id" size="tiny" type="success" round>
                启用中
              </n-tag>
            </div>
            <div class="llm-profile-meta">
              <span>{{ profile.protocol }}</span>
              <span v-if="profile.model">· {{ profile.model }}</span>
            </div>
          </button>
        </div>
      </aside>

      <section v-if="selectedProfile" ref="editorRef" class="llm-editor" @scroll="saveUiState">
        <n-card size="small" :bordered="false" class="llm-card">
          <template #header>
            <div class="llm-card-head">
              <div>
                <div class="llm-card-title">{{ selectedProfile.name }}</div>
                <div class="llm-card-desc">协议、网关、模型、默认参数与高级透传参数。</div>
              </div>
              <n-space :size="8">
                <n-button size="small" secondary @click="duplicateSelected">复制</n-button>
                <n-button
                  size="small"
                  secondary
                  type="error"
                  :disabled="(panelData.config?.profiles || []).length <= 1"
                  @click="removeSelected"
                >
                  删除
                </n-button>
                <n-button size="small" secondary :loading="testing" @click="testSelected">测试连接</n-button>
                <n-button size="small" type="primary" ghost :loading="saving" @click="activateSelected">设为启用</n-button>
              </n-space>
            </div>
          </template>

          <div class="llm-form-grid">
            <div class="llm-field span-2">
              <label class="llm-label">预设</label>
              <div class="llm-field-row">
                <n-select
                  v-model:value="selectedProfile.preset_key"
                  :options="presetOptions"
                  placeholder="选择预设"
                  filterable
                />
                <n-button secondary @click="applyPresetToSelected">应用预设</n-button>
              </div>
              <n-text depth="3" style="font-size: 12px">{{ selectedPreset?.description || '可先套预设，再微调 endpoint。' }}</n-text>
            </div>

            <div class="llm-field">
              <label class="llm-label">配置名称</label>
              <n-input v-model:value="selectedProfile.name" placeholder="例如：DeepSeek 生产网关" />
            </div>

            <div class="llm-field">
              <label class="llm-label">协议</label>
              <n-select v-model:value="selectedProfile.protocol" :options="protocolOptions" />
            </div>

            <div class="llm-field span-2">
              <label class="llm-label">Base URL</label>
              <n-input v-model:value="selectedProfile.base_url" placeholder="可填官方地址，也可填兼容网关地址" />
            </div>

            <div class="llm-field span-2">
              <label class="llm-label">API Key</label>
              <n-input
                v-model:value="selectedProfile.api_key"
                type="password"
                show-password-on="click"
                placeholder="本地保存；仅用于当前项目"
              />
            </div>

            <div class="llm-field span-2">
              <label class="llm-label">模型名</label>
              <div class="llm-model-row">
                <n-auto-complete
                  v-model:value="selectedProfile.model"
                  :options="fetchedModelOptions"
                  placeholder="填写所用网关文档中的模型 ID（本处不预设具体名称）"
                  clearable
                  style="flex: 1"
                />
                <n-button
                  secondary
                  size="small"
                  :loading="fetchingModels"
                  :disabled="!selectedProfile.api_key"
                  @click="handleFetchModels"
                >
                  拉取模型
                </n-button>
              </div>
              <n-text v-if="fetchedModels.length > 0" depth="3" style="font-size: 11px">
                已拉取 {{ fetchedModels.length }} 个模型，可输入过滤或直接选择
              </n-text>
            </div>

            <div class="llm-field">
              <label class="llm-label">默认 temperature</label>
              <n-input-number v-model:value="selectedProfile.temperature" :min="0" :max="2" :step="0.1" style="width: 100%" />
            </div>

            <div class="llm-field">
              <label class="llm-label">默认 max_tokens</label>
              <n-input-number v-model:value="selectedProfile.max_tokens" :min="1" :step="256" style="width: 100%" />
            </div>

            <div class="llm-field">
              <label class="llm-label">超时（秒）</label>
              <n-input-number v-model:value="selectedProfile.timeout_seconds" :min="1" :step="10" style="width: 100%" />
            </div>

            <div v-if="selectedProfile.protocol === 'openai'" class="llm-field span-2">
              <label class="llm-label">使用旧协议（Chat Completions）</label>
              <n-switch v-model:value="selectedProfile.use_legacy_chat_completions" />
              <n-text depth="3" style="font-size: 12px">
                关闭时走 Responses API（默认）；部分国产网关不支持新协议时请开启。
              </n-text>
            </div>

            <div class="llm-field span-2">
              <label class="llm-label">备注</label>
              <n-input v-model:value="selectedProfile.notes" type="textarea" :autosize="{ minRows: 2, maxRows: 4 }" placeholder="例如：公司网关、测试环境、带 reasoning 参数" />
            </div>
          </div>

          <n-collapse class="llm-advanced">
            <n-collapse-item name="advanced" title="高级透传参数（兼容国产模型关键入口）">
              <div class="llm-form-grid">
                <div class="llm-field span-2">
                  <label class="llm-label">extra_headers（JSON）</label>
                  <n-input v-model:value="extraHeadersText" type="textarea" :autosize="{ minRows: 4, maxRows: 10 }" placeholder='{"x-foo": "bar"}' />
                </div>
                <div class="llm-field span-2">
                  <label class="llm-label">extra_query（JSON）</label>
                  <n-input v-model:value="extraQueryText" type="textarea" :autosize="{ minRows: 4, maxRows: 10 }" placeholder='{"api-version": "2024-10-21"}' />
                </div>
                <div class="llm-field span-2">
                  <label class="llm-label">extra_body（JSON）</label>
                  <n-input v-model:value="extraBodyText" type="textarea" :autosize="{ minRows: 5, maxRows: 12 }" placeholder='{"reasoning_effort": "medium"}' />
                </div>
              </div>
              <n-alert type="info" :show-icon="false" class="llm-tip">
                这里用于兼容特殊网关：如 <code>reasoning_effort</code>、<code>top_p</code>、厂商专属开关、额外 header / query。
                若使用带「思考链」的模型，请确认网关会把推理与正文分离；否则正文里可能出现推理片段，可换用标准聊天模型或更新到最新版本（服务端会自动剥离常见
                <code>think</code>、<code>redacted_reasoning</code> 等标签）。
              </n-alert>
            </n-collapse-item>
          </n-collapse>
        </n-card>
      </section>
    </div>

    <n-empty v-else description="加载 LLM 配置中…" class="llm-empty" />
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useMessage } from 'naive-ui'
import {
  llmControlApi,
  type LLMControlConfig,
  type LLMControlPanelData,
  type LLMPreset,
  type LLMProfile,
  type LLMProtocol,
  type LLMRuntimeSummary,
  type ModelItem,
} from '../../api/llmControl'

interface Props {
  scrollStateKey?: string
}

interface PanelUiState {
  selectedProfileId?: string
  editorTop?: number
  sidebarTop?: number
}

const props = withDefaults(defineProps<Props>(), {
  scrollStateKey: '',
})

const emit = defineEmits<{
  'panel-updated': [data: LLMControlPanelData]
}>()

const message = useMessage()

const panelData = ref<LLMControlPanelData | null>(null)
const loading = ref(false)
const saving = ref(false)
const testing = ref(false)
const fetchingModels = ref(false)
const fetchedModels = ref<ModelItem[]>([])
const selectedProfileId = ref('')
const extraHeadersText = ref('{}')
const extraQueryText = ref('{}')
const extraBodyText = ref('{}')
const editorRef = ref<HTMLElement | null>(null)
const sidebarListRef = ref<HTMLElement | null>(null)

const protocolOptions = [
  { label: 'OpenAI 兼容', value: 'openai' },
  { label: 'Anthropic / Claude 兼容', value: 'anthropic' },
  { label: 'Gemini', value: 'gemini' },
]

const presetOptions = computed(() =>
  (panelData.value?.presets || []).map((preset) => ({
    label: preset.label,
    value: preset.key,
  }))
)

const quickImportPresets = computed(() =>
  (panelData.value?.presets || []).filter((preset) => preset.key !== 'custom-openai-compatible')
)

const selectedProfile = computed(() =>
  panelData.value?.config?.profiles.find((profile) => profile.id === selectedProfileId.value) || null
)

const selectedPreset = computed<LLMPreset | null>(() => {
  if (!selectedProfile.value || !panelData.value) return null
  return panelData.value.presets.find((preset) => preset.key === selectedProfile.value?.preset_key) || null
})

const runtimeLabel = computed(() => {
  const runtime = panelData.value?.runtime
  if (!runtime) return '未加载'
  if (runtime.using_mock) return 'MockProvider'
  return runtime.active_profile_name || '已配置'
})

const fetchedModelOptions = computed(() =>
  fetchedModels.value.map((m) => ({
    label: m.id,
    value: m.id,
  }))
)

async function handleFetchModels() {
  if (!selectedProfile.value) return
  fetchingModels.value = true
  fetchedModels.value = []
  try {
    const result = await llmControlApi.fetchModels({
      protocol: selectedProfile.value.protocol,
      base_url: selectedProfile.value.base_url,
      api_key: selectedProfile.value.api_key,
    })
    if (result.success && result.items.length > 0) {
      fetchedModels.value = result.items
      message.success(`成功拉取 ${result.count} 个模型`)
    } else {
      message.warning('未获取到可用模型列表')
    }
  } catch (error) {
    const ax = error as { response?: { data?: { detail?: unknown } }; message?: string }
    let detail = ''
    const d = ax?.response?.data?.detail
    if (typeof d === 'string' && d.trim()) {
      detail = d.trim()
    } else if (Array.isArray(d)) {
      detail = d.map((x: { msg?: string }) => (typeof x?.msg === 'string' ? x.msg : JSON.stringify(x))).join('; ')
    }
    if (!detail && ax?.message) detail = ax.message
    if (!detail) detail = '拉取失败'
    message.error(`模型列表拉取失败：${detail}`)
  } finally {
    fetchingModels.value = false
  }
}

function getUiStateStorageKey(): string {
  return props.scrollStateKey ? `plotpilot.llm-panel.ui.${props.scrollStateKey}` : ''
}

function readUiState(): PanelUiState {
  const key = getUiStateStorageKey()
  if (!key) return {}
  try {
    const raw = sessionStorage.getItem(key)
    return raw ? (JSON.parse(raw) as PanelUiState) : {}
  } catch {
    return {}
  }
}

function saveUiState() {
  const key = getUiStateStorageKey()
  if (!key) return
  const payload: PanelUiState = {
    selectedProfileId: selectedProfileId.value || undefined,
    editorTop: editorRef.value?.scrollTop || 0,
    sidebarTop: sidebarListRef.value?.scrollTop || 0,
  }
  sessionStorage.setItem(key, JSON.stringify(payload))
}

function restoreUiState() {
  const state = readUiState()
  if (editorRef.value && typeof state.editorTop === 'number') {
    editorRef.value.scrollTop = state.editorTop
  }
  if (sidebarListRef.value && typeof state.sidebarTop === 'number') {
    sidebarListRef.value.scrollTop = state.sidebarTop
  }
}

function deepClone<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T
}

function prettyJson(value: Record<string, unknown>): string {
  return JSON.stringify(value || {}, null, 2)
}

function newProfileId(): string {
  return globalThis.crypto?.randomUUID?.() || `profile-${Date.now()}`
}

function buildProfileFromPreset(preset?: LLMPreset): LLMProfile {
  return {
    id: newProfileId(),
    name: preset?.label || '新配置',
    preset_key: preset?.key || 'custom-openai-compatible',
    protocol: (preset?.protocol || 'openai') as LLMProtocol,
    base_url: preset?.default_base_url || '',
    api_key: '',
    model: preset?.default_model || '',
    temperature: 0.7,
    max_tokens: 4096,
    timeout_seconds: 300,
    extra_headers: {},
    extra_query: {},
    extra_body: {},
    notes: '',
    use_legacy_chat_completions: false,
  }
}

function defaultRuntimeSummary(): LLMRuntimeSummary {
  return {
    source: 'mock',
    active_profile_id: null,
    active_profile_name: null,
    protocol: null,
    model: null,
    base_url: null,
    using_mock: true,
    reason: '尚未加载或未返回运行时摘要',
  }
}

/**
 * 兼容代理/网关返回的 `{ data: { config, ... } }`，并补全缺失字段，避免访问 `config.active_profile_id` 时报错。
 */
function normalizePanelData(raw: unknown): LLMControlPanelData {
  let root: Record<string, unknown> =
    raw && typeof raw === 'object' ? { ...(raw as Record<string, unknown>) } : {}

  const wrapped = root.data
  if (
    wrapped &&
    typeof wrapped === 'object' &&
    'config' in (wrapped as object) &&
    !('config' in root)
  ) {
    root = { ...(wrapped as Record<string, unknown>) }
  }

  const cfgIn = root.config
  const cfgObj =
    cfgIn && typeof cfgIn === 'object'
      ? (cfgIn as Record<string, unknown>)
      : { version: 1, active_profile_id: null, profiles: [] }

  let profiles: LLMProfile[] = Array.isArray(cfgObj.profiles)
    ? (cfgObj.profiles as LLMProfile[]).filter(
        (p) => p && typeof p === 'object' && typeof p.id === 'string',
      )
    : []

  if (!profiles.length) {
    profiles = [buildProfileFromPreset(undefined)]
  }

  let activeId =
    typeof cfgObj.active_profile_id === 'string' ? cfgObj.active_profile_id : null
  if (!activeId || !profiles.some((p) => p.id === activeId)) {
    activeId = profiles[0]?.id ?? null
  }

  const config: LLMControlConfig = {
    version: typeof cfgObj.version === 'number' ? cfgObj.version : 1,
    active_profile_id: activeId,
    profiles,
  }

  const presets: LLMPreset[] = Array.isArray(root.presets)
    ? (root.presets as LLMPreset[])
    : []

  const rtIn = root.runtime
  const runtime: LLMRuntimeSummary =
    rtIn && typeof rtIn === 'object'
      ? { ...defaultRuntimeSummary(), ...(rtIn as Partial<LLMRuntimeSummary>) }
      : defaultRuntimeSummary()

  return { config, presets, runtime }
}

function uniqueProfileName(baseName: string): string {
  const normalized = baseName.trim() || '新配置'
  const names = new Set((panelData.value?.config?.profiles || []).map((profile) => profile.name))
  if (!names.has(normalized)) return normalized
  let index = 2
  while (names.has(`${normalized} ${index}`)) {
    index += 1
  }
  return `${normalized} ${index}`
}

function syncJsonEditors() {
  extraHeadersText.value = prettyJson((selectedProfile.value?.extra_headers || {}) as Record<string, unknown>)
  extraQueryText.value = prettyJson((selectedProfile.value?.extra_query || {}) as Record<string, unknown>)
  extraBodyText.value = prettyJson((selectedProfile.value?.extra_body || {}) as Record<string, unknown>)
}

function parseJsonObject(label: string, text: string): Record<string, unknown> {
  if (!text.trim()) return {}
  try {
    const parsed = JSON.parse(text)
    if (!parsed || Array.isArray(parsed) || typeof parsed !== 'object') {
      throw new Error(`${label} 必须是 JSON 对象`)
    }
    return parsed as Record<string, unknown>
  } catch (error) {
    const reason = error instanceof Error ? error.message : 'JSON 解析失败'
    throw new Error(`${label} 格式错误：${reason}`)
  }
}

function commitAdvancedEditors() {
  if (!selectedProfile.value) return
  selectedProfile.value.extra_headers = parseJsonObject('extra_headers', extraHeadersText.value) as Record<string, string>
  selectedProfile.value.extra_query = parseJsonObject('extra_query', extraQueryText.value)
  selectedProfile.value.extra_body = parseJsonObject('extra_body', extraBodyText.value)
}

async function loadPanel() {
  loading.value = true
  try {
    const raw = await llmControlApi.getPanel()
    const data = normalizePanelData(raw)
    panelData.value = deepClone(data)
    const persistedState = readUiState()
    const preferredId = persistedState.selectedProfileId || selectedProfileId.value
    const candidateId = preferredId && data.config.profiles.some((profile) => profile.id === preferredId)
      ? preferredId
      : data.config.active_profile_id || data.config.profiles[0]?.id || ''
    selectedProfileId.value = candidateId
    syncJsonEditors()
    emit('panel-updated', deepClone(data))
    await nextTick()
    restoreUiState()
  } catch (error) {
    const detail = error instanceof Error ? error.message : '加载失败'
    message.error(`LLM 面板加载失败：${detail}`)
  } finally {
    loading.value = false
  }
}

function selectProfile(profileId: string) {
  selectedProfileId.value = profileId
  saveUiState()
}

function addProfile() {
  if (!panelData.value) return
  const preset = panelData.value.presets.find((item) => item.key === 'custom-openai-compatible')
  const profile = buildProfileFromPreset(preset)
  profile.name = uniqueProfileName(profile.name)
  panelData.value.config.profiles.push(profile)
  selectedProfileId.value = profile.id
  syncJsonEditors()
  saveUiState()
}

function importPresetShortcut(presetKey: string) {
  if (!panelData.value) return
  const preset = panelData.value.presets.find((item) => item.key === presetKey)
  if (!preset) return
  const profile = buildProfileFromPreset(preset)
  profile.name = uniqueProfileName(preset.label)
  panelData.value.config.profiles.unshift(profile)
  selectedProfileId.value = profile.id
  syncJsonEditors()
  saveUiState()
  message.success(`已导入预设：${preset.label}`)
}

function duplicateSelected() {
  if (!panelData.value || !selectedProfile.value) return
  try {
    commitAdvancedEditors()
  } catch (error) {
    message.error(error instanceof Error ? error.message : '高级参数格式错误')
    return
  }
  const duplicated = deepClone(selectedProfile.value)
  duplicated.id = newProfileId()
  duplicated.name = `${duplicated.name}（副本）`
  panelData.value.config.profiles.push(duplicated)
  selectedProfileId.value = duplicated.id
  syncJsonEditors()
  saveUiState()
}

function removeSelected() {
  if (!panelData.value || !selectedProfile.value) return
  if (panelData.value.config.profiles.length <= 1) {
    message.warning('至少保留一个配置档案')
    return
  }
  const targetId = selectedProfile.value.id
  panelData.value.config.profiles = panelData.value.config.profiles.filter((profile) => profile.id !== targetId)
  if (panelData.value.config.active_profile_id === targetId) {
    panelData.value.config.active_profile_id = panelData.value.config.profiles[0]?.id || null
  }
  selectedProfileId.value = panelData.value.config.active_profile_id || panelData.value.config.profiles[0]?.id || ''
  syncJsonEditors()
  saveUiState()
}

function applyPresetToSelected() {
  if (!selectedProfile.value || !panelData.value) return
  const preset = panelData.value.presets.find((item) => item.key === selectedProfile.value?.preset_key)
  if (!preset) return
  selectedProfile.value.protocol = preset.protocol
  if (preset.default_base_url) selectedProfile.value.base_url = preset.default_base_url
  if (preset.default_model) selectedProfile.value.model = preset.default_model
  if (!selectedProfile.value.name || selectedProfile.value.name === '新配置') {
    selectedProfile.value.name = preset.label
  }
  syncJsonEditors()
}

async function saveAll() {
  if (!panelData.value) return
  if (!selectedProfile.value) return
  try {
    commitAdvancedEditors()
  } catch (error) {
    message.error(error instanceof Error ? error.message : '高级参数格式错误')
    return
  }

  saving.value = true
  try {
    const response = await llmControlApi.saveConfig(panelData.value.config)
    const normalized = normalizePanelData(response)
    panelData.value = deepClone(normalized)
    selectedProfileId.value = normalized.config.profiles.some((profile) => profile.id === selectedProfileId.value)
      ? selectedProfileId.value
      : normalized.config.active_profile_id || normalized.config.profiles[0]?.id || ''
    syncJsonEditors()
    emit('panel-updated', deepClone(normalized))
    await nextTick()
    restoreUiState()
    saveUiState()
    message.success('LLM 配置已保存')
  } catch (error) {
    const detail = error instanceof Error ? error.message : '保存失败'
    message.error(`保存失败：${detail}`)
  } finally {
    saving.value = false
  }
}

async function activateSelected() {
  if (!panelData.value || !selectedProfile.value) return
  panelData.value.config.active_profile_id = selectedProfile.value.id
  await saveAll()
}

async function testSelected() {
  if (!selectedProfile.value) return
  try {
    commitAdvancedEditors()
  } catch (error) {
    message.error(error instanceof Error ? error.message : '高级参数格式错误')
    return
  }

  testing.value = true
  try {
    const result = await llmControlApi.testProfile(selectedProfile.value)
    if (result.ok) {
      const preview = result.preview ? ` · ${result.preview}` : ''
      message.success(`连接成功（${result.latency_ms}ms）${preview}`)
    } else {
      message.error(result.error || '连接失败')
    }
  } catch (error) {
    const detail = error instanceof Error ? error.message : '连接失败'
    message.error(`测试失败：${detail}`)
  } finally {
    testing.value = false
  }
}

watch(selectedProfileId, () => {
  syncJsonEditors()
  saveUiState()
})

onMounted(() => {
  void loadPanel()
})

onBeforeUnmount(() => {
  saveUiState()
})
</script>

<style scoped>
.llm-panel {
  height: 100%;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: var(--app-surface);
}

.llm-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
  padding: 16px 18px 12px;
  border-bottom: 1px solid var(--aitext-split-border);
  flex-shrink: 0;
}

.llm-header-main {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.llm-title-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.llm-title {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
}

.llm-lead {
  margin: 0;
  font-size: 13px;
  line-height: 1.7;
  color: var(--n-text-color-3);
}

.llm-alert {
  margin: 0 18px 12px;
  flex-shrink: 0;
}

.llm-preset-strip {
  margin: 0 18px 12px;
  padding: 14px;
  border: 1px solid var(--aitext-split-border);
  border-radius: 14px;
  background:
    linear-gradient(180deg, var(--color-brand-light), var(--app-surface)),
    var(--app-surface);
  flex-shrink: 0;
}

.llm-preset-strip-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 12px;
}

.llm-preset-strip-title {
  font-size: 13px;
  font-weight: 700;
  color: var(--n-text-color-1);
}

.llm-preset-strip-desc {
  margin-top: 4px;
  font-size: 12px;
  color: var(--n-text-color-3);
}

.llm-preset-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
  gap: 10px;
}

.llm-preset-card {
  border: 1px solid var(--color-brand-border, rgba(99, 102, 241, 0.12));
  border-radius: 12px;
  background: var(--app-surface-raised, var(--app-surface));
  padding: 12px;
  text-align: left;
  display: flex;
  flex-direction: column;
  gap: 6px;
  cursor: pointer;
  transition: transform 0.16s ease, border-color 0.16s ease, box-shadow 0.16s ease;
}

.llm-preset-card:hover {
  transform: translateY(-1px);
  border-color: var(--color-brand-hover, rgba(79, 70, 229, 0.28));
  box-shadow: var(--app-shadow-md), 0 10px 22px var(--color-brand-border, rgba(79, 70, 229, 0.08));
}

.llm-preset-card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.llm-preset-card-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--n-text-color-1);
}

.llm-preset-card-protocol {
  flex-shrink: 0;
  font-size: 11px;
  color: var(--color-brand, #4f46e5);
  background: var(--color-brand-light, rgba(79, 70, 229, 0.08));
  border-radius: 999px;
  padding: 2px 8px;
}

.llm-preset-card-model {
  font-size: 12px;
  color: var(--n-text-color-2);
}

.llm-preset-card-url {
  font-size: 11px;
  line-height: 1.45;
  color: var(--n-text-color-3);
  word-break: break-all;
}

.llm-layout {
  flex: 1;
  min-height: 0;
  display: grid;
  grid-template-columns: 240px minmax(0, 1fr);
  gap: 14px;
  padding: 0 18px 18px;
  overflow: hidden;
}

.llm-sidebar,
.llm-editor {
  min-height: 0;
}

.llm-sidebar {
  border: 1px solid var(--aitext-split-border);
  border-radius: 12px;
  background: var(--aitext-panel-muted);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.llm-sidebar-head {
  padding: 14px;
  display: flex;
  justify-content: space-between;
  gap: 8px;
  border-bottom: 1px solid var(--aitext-split-border);
}

.llm-sidebar-title {
  font-size: 13px;
  font-weight: 600;
}

.llm-sidebar-desc {
  font-size: 12px;
  color: var(--n-text-color-3);
  margin-top: 4px;
}

.llm-profile-list {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 10px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.llm-profile-item {
  width: 100%;
  border: 1px solid var(--profile-item-border, var(--aitext-split-border));
  border-radius: 10px;
  background: var(--profile-item-bg, var(--app-surface));
  padding: 10px 12px;
  text-align: left;
  cursor: pointer;
  transition: all 0.16s ease;
}

.llm-profile-item:hover,
.llm-profile-item.is-selected {
  border-color: var(--profile-selected-border, var(--color-brand));
  transform: translateY(-1px);
  box-shadow: var(--app-shadow-sm);
}

.llm-profile-item.is-active {
  background: var(--profile-active-bg, var(--color-brand-light));
  border-color: var(--profile-selected-border, var(--color-brand-hover));
}

.llm-profile-name-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
}

.llm-profile-name {
  font-size: 13px;
  font-weight: 700;
  color: var(--profile-name-color, var(--app-text-primary));
}

.llm-profile-meta {
  margin-top: 6px;
  font-size: 12px;
  color: var(--profile-meta-color, var(--app-text-muted));
}

.llm-editor {
  overflow-y: auto;
}

.llm-card {
  min-height: 100%;
}

.llm-card-head {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: flex-start;
}

.llm-card-title {
  font-size: 15px;
  font-weight: 600;
}

.llm-card-desc {
  margin-top: 4px;
  font-size: 12px;
  color: var(--n-text-color-3);
}

.llm-form-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
}

.llm-field {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.llm-field.span-2 {
  grid-column: span 2;
}

.llm-field-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 8px;
}

.llm-label {
  font-size: 12px;
  font-weight: 600;
  color: var(--n-text-color-2);
}

.llm-model-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 8px;
  align-items: start;
}

.llm-advanced {
  margin-top: 18px;
}

.llm-tip {
  margin-top: 10px;
}

.llm-empty {
  margin-top: 80px;
}

@media (max-width: 1180px) {
  .llm-layout {
    grid-template-columns: 1fr;
  }
}
</style>
