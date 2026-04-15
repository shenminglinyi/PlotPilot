<template>
  <div class="llm-fab-wrap" :style="fabStyle">
    <n-button
      class="llm-fab"
      circle
      type="primary"
      size="large"
      @pointerdown="handlePointerDown"
      @click="handleFabClick"
    >
      <template #icon>
        <n-icon><SettingsOutline /></n-icon>
      </template>
    </n-button>

    <n-modal
      v-model:show="showModal"
      preset="card"
      title="模型接入配置"
      class="llm-settings-modal"
      style="width: min(840px, 96vw)"
      :bordered="false"
      :segmented="{ content: true, footer: 'soft' }"
      @after-enter="handleOpen"
    >
      <template #header-extra>
        <n-space :size="8" align="center">
          <n-tag size="small" round :bordered="false">{{ vendorLabel }}</n-tag>
          <n-tag size="small" round type="success" :bordered="false">{{ formatLabel }}</n-tag>
          <n-tag v-if="activePresetName" size="small" round type="warning" :bordered="false">
            {{ activePresetName }}
          </n-tag>
        </n-space>
      </template>

      <div class="llm-settings-body">
        <n-alert type="info" :show-icon="true" class="llm-tip">
          支持首页和工作台统一配置。你可以直接填入自定义 API Key，也可以把当前配置保存成预设，后续一键切换。
        </n-alert>

        <n-card size="small" :bordered="false" class="llm-section-card">
          <template #header>
            <n-space justify="space-between" align="center" style="width: 100%">
              <span>预设管理</span>
              <n-space :size="8">
                <n-button size="small" secondary :disabled="!selectedPresetId" @click="handleApplyPreset">
                  应用预设
                </n-button>
                <n-button size="small" secondary :disabled="!selectedPresetId" @click="handleDeletePreset">
                  删除预设
                </n-button>
              </n-space>
            </n-space>
          </template>

          <n-grid :cols="24" :x-gap="12">
            <n-gi :span="10">
              <n-form-item label="已保存预设">
                <n-select
                  v-model:value="selectedPresetId"
                  clearable
                  filterable
                  :options="presetOptions"
                  placeholder="选择一个预设"
                />
              </n-form-item>
            </n-gi>
            <n-gi :span="9">
              <n-form-item label="预设名称">
                <n-input v-model:value="presetName" placeholder="例如 我的 Grok / Claude 正式环境" />
              </n-form-item>
            </n-gi>
            <n-gi :span="5">
              <n-form-item label="保存当前">
                <n-button block type="primary" secondary :loading="presetSaving" @click="handleSavePreset">
                  保存为预设
                </n-button>
              </n-form-item>
            </n-gi>
          </n-grid>
        </n-card>

        <div class="preset-grid">
          <button
            v-for="preset in vendorPresets"
            :key="preset.id"
            type="button"
            class="preset-card"
            :class="{ 'preset-card--active': form.vendor === preset.id }"
            @click="applyVendorPreset(preset.id)"
          >
            <span class="preset-title">{{ preset.label }}</span>
            <span class="preset-sub">{{ preset.description }}</span>
          </button>
        </div>

        <n-grid :cols="24" :x-gap="12">
          <n-form label-placement="top" class="llm-form">
            <n-gi :span="12">
              <n-form-item label="协议格式">
                <n-select v-model:value="form.api_format" :options="formatOptions" />
              </n-form-item>
            </n-gi>
            <n-gi :span="12">
              <n-form-item label="模型名">
                <n-space vertical :size="8" style="width: 100%">
                  <n-text depth="3" style="font-size: 12px">主模型</n-text>
                  <n-auto-complete
                    v-model:value="form.model"
                    :options="modelOptions"
                    placeholder="例如 grok-4.20-0309 / claude-sonnet-4-5 / gpt-5.2-codex"
                  />
                </n-space>
              </n-form-item>
            </n-gi>
          </n-form>
        </n-grid>

        <n-card size="small" :bordered="false" class="llm-section-card endpoint-card">
          <template #header>
            <span>自定义 API 地址</span>
          </template>

          <n-space vertical :size="10">
            <n-text depth="3" style="font-size: 12px">
              {{ resolvedBaseUrlHelpText }}
            </n-text>
            <n-input
              v-model:value="form.base_url"
              :placeholder="resolvedBaseUrlPlaceholder"
            />
            <n-tag size="small" round type="info" :bordered="false">
              当前协议：{{ formatLabel }}
            </n-tag>
          </n-space>
        </n-card>

        <n-card size="small" :bordered="false" class="llm-section-card api-key-card">
          <template #header>
            <n-space justify="space-between" align="center" style="width: 100%">
              <span>自定义 API Key</span>
              <n-text depth="3" style="font-size: 12px">
                当前：{{ form.api_key ? '本次已输入' : (maskedApiKey || '未设置') }}
              </n-text>
            </n-space>
          </template>

          <n-space vertical :size="10">
            <n-text depth="3" style="font-size: 12px">
              可以直接填入新的 key。留空保存时不会覆盖已经保存的密钥。
            </n-text>
            <n-input
              v-model:value="form.api_key"
              type="password"
              show-password-on="click"
              :placeholder="apiKeyPlaceholder"
            />
            <n-space justify="space-between" align="center" style="width: 100%">
              <n-text depth="3" style="font-size: 12px">
                先确认地址和 Key 正确，再拉取可用模型；拉取后主模型和高级模型都可直接下拉选择。
              </n-text>
              <n-button type="primary" secondary :loading="modelsLoading" @click="handleLoadModels">
                拉取模型列表
              </n-button>
            </n-space>
          </n-space>
        </n-card>

        <n-collapse :default-expanded-names="['advanced-models']">
          <n-collapse-item title="高级模型覆盖" name="advanced-models">
            <n-grid :cols="24" :x-gap="12">
              <n-gi :span="12">
                <n-form-item label="快速模型">
                  <n-select
                    v-model:value="form.fast_model"
                    filterable
                    tag
                    :options="modelOptions"
                    placeholder="留空则跟随主模型，也可手动输入"
                  />
                </n-form-item>
              </n-gi>
              <n-gi :span="12">
                <n-form-item label="审阅模型">
                  <n-select
                    v-model:value="form.review_model"
                    filterable
                    tag
                    :options="modelOptions"
                    placeholder="留空则跟随快速模型，也可手动输入"
                  />
                </n-form-item>
              </n-gi>
              <n-gi :span="12">
                <n-form-item label="场景分析模型">
                  <n-select
                    v-model:value="form.scene_director_model"
                    filterable
                    tag
                    :options="modelOptions"
                    placeholder="留空则跟随快速模型，也可手动输入"
                  />
                </n-form-item>
              </n-gi>
              <n-gi :span="12">
                <n-form-item label="状态提取模型">
                  <n-select
                    v-model:value="form.state_extractor_model"
                    filterable
                    tag
                    :options="modelOptions"
                    placeholder="留空则跟随主模型，也可手动输入"
                  />
                </n-form-item>
              </n-gi>
              <n-gi :span="8">
                <n-form-item label="Temperature">
                  <n-input-number v-model:value="form.temperature" :min="0" :max="2" :step="0.1" style="width: 100%" />
                </n-form-item>
              </n-gi>
              <n-gi :span="8">
                <n-form-item label="Max Tokens">
                  <n-input-number v-model:value="form.max_tokens" :min="1" :step="256" style="width: 100%" />
                </n-form-item>
              </n-gi>
              <n-gi :span="8">
                <n-form-item label="超时(ms)">
                  <n-input-number v-model:value="form.timeout_ms" :min="1000" :step="1000" style="width: 100%" />
                </n-form-item>
              </n-gi>
            </n-grid>
          </n-collapse-item>
        </n-collapse>

        <n-alert v-if="testResult" :type="testResult.success ? 'success' : 'warning'" :show-icon="true" class="llm-test-result">
          {{ testResult.message }}
        </n-alert>
      </div>

      <template #footer>
        <n-space justify="space-between" style="width: 100%">
          <n-text depth="3" style="font-size: 12px">
            保存后立即生效；预设用于快速切换不同供应商和模型配置。
          </n-text>
          <n-space :size="10">
            <n-button @click="showModal = false">关闭</n-button>
            <n-button :loading="testing" @click="handleTest">测试连接</n-button>
            <n-button type="primary" :loading="saving" @click="handleSave">保存当前配置</n-button>
          </n-space>
        </n-space>
      </template>
    </n-modal>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { NIcon, useDialog, useMessage } from 'naive-ui'
import { SettingsOutline } from '@vicons/ionicons5'
import {
  llmSettingsApi,
  type LLMSettings,
  type LLMSettingsResponse,
  type ModelOption,
  type LLMPreset,
} from '../../api/llmSettings'

const message = useMessage()
const dialog = useDialog()

const showModal = ref(false)
const loading = ref(false)
const saving = ref(false)
const testing = ref(false)
const modelsLoading = ref(false)
const presetSaving = ref(false)
const maskedApiKey = ref('')
const testResult = ref<{ success: boolean; message: string } | null>(null)
const modelOptions = ref<ModelOption[]>([])
const presets = ref<LLMPreset[]>([])
const selectedPresetId = ref<string | null>(null)
const activePresetId = ref<string | null>(null)
const presetName = ref('')
const FAB_SIZE = 56
const FAB_MARGIN = 22
const FAB_STORAGE_KEY = 'plotpilot.llm-settings-fab-position'
const fabPosition = reactive({ x: 0, y: 0 })
const dragState = reactive({
  active: false,
  pointerId: -1,
  startX: 0,
  startY: 0,
  originX: 0,
  originY: 0,
  moved: false,
})
const suppressNextClick = ref(false)

const vendorPresets = [
  { id: 'claude', label: 'Claude', description: 'Anthropic 原生 Messages 格式' },
  { id: 'openai', label: 'OpenAI', description: 'OpenAI 兼容 Chat Completions' },
  { id: 'codex', label: 'Codex', description: '适合 OpenAI/Codex 兼容接口' },
]

const form = reactive<LLMSettings>({
  vendor: 'openai',
  api_format: 'openai_chat_completions',
  base_url: '',
  api_key: '',
  model: '',
  fast_model: '',
  review_model: '',
  scene_director_model: '',
  state_extractor_model: '',
  temperature: 0.7,
  max_tokens: 4096,
  timeout_ms: 300000,
})

const formatOptions = [
  { label: 'Anthropic Messages', value: 'anthropic_messages' },
  { label: 'OpenAI Chat Completions', value: 'openai_chat_completions' },
  { label: 'OpenAI Responses / Codex', value: 'openai_responses' },
]

const presetOptions = computed(() => (
  presets.value.map(item => ({
    label: activePresetId.value === item.id ? `${item.name} (当前)` : item.name,
    value: item.id,
  }))
))

const activePresetName = computed(() => (
  presets.value.find(item => item.id === activePresetId.value)?.name || ''
))

const vendorLabel = computed(() => {
  const found = vendorPresets.find(item => item.id === form.vendor)
  return found?.label || String(form.vendor)
})

const formatLabel = computed(() => {
  if (form.api_format === 'anthropic_messages') return 'Anthropic'
  if (form.api_format === 'openai_responses') return 'OpenAI Responses / Codex'
  return 'OpenAI Compatible'
})

const baseUrlPlaceholder = computed(() => (
  form.api_format === 'anthropic_messages'
    ? '例如 https://your-anthropic-endpoint'
    : '例如 https://your-openai-compatible-endpoint/v1'
))

const baseUrlHelpText = computed(() => (
  form.api_format === 'anthropic_messages'
    ? '这里可以填写自定义的 Anthropic 兼容地址。通常填写根地址即可，不需要手动补 /v1/messages。'
    : '这里可以填写你自己的 OpenAI 兼容 API 地址。多数第三方网关建议填写到 /v1。'
))

const resolvedBaseUrlPlaceholder = computed(() => {
  if (form.api_format === 'anthropic_messages') return baseUrlPlaceholder.value
  if (form.api_format === 'openai_responses') return '例如 https://your-openai-compatible-endpoint/v1'
  return baseUrlPlaceholder.value
})

const resolvedBaseUrlHelpText = computed(() => {
  if (form.api_format === 'anthropic_messages') return baseUrlHelpText.value
  if (form.api_format === 'openai_responses') {
    return '这里填写支持 OpenAI Responses / Codex Responses 协议的根地址，通常填到 /v1，系统会自动拼接 /responses。'
  }
  return baseUrlHelpText.value
})

const apiKeyPlaceholder = computed(() => (
  maskedApiKey.value ? `当前已保存：${maskedApiKey.value}；留空则不覆盖` : '输入 API Key'
))

const fabStyle = computed(() => ({
  left: `${fabPosition.x}px`,
  top: `${fabPosition.y}px`,
}))

function mergeModelOptions(base: ModelOption[], values: Array<string | undefined>): ModelOption[] {
  const map = new Map<string, ModelOption>()
  for (const item of base) {
    if (!item?.value) continue
    map.set(item.value, item)
  }
  for (const raw of values) {
    const value = String(raw || '').trim()
    if (!value || map.has(value)) continue
    map.set(value, { label: value, value })
  }
  return Array.from(map.values()).sort((a, b) => a.value.localeCompare(b.value))
}

function syncCurrentModelsIntoOptions(base: ModelOption[] = modelOptions.value) {
  modelOptions.value = mergeModelOptions(base, [
    form.model,
    form.fast_model,
    form.review_model,
    form.scene_director_model,
    form.state_extractor_model,
  ])
}

function assignSettings(data: LLMSettings) {
  form.vendor = data.vendor || 'openai'
  form.api_format = data.api_format || 'openai_chat_completions'
  form.base_url = data.base_url || ''
  form.api_key = ''
  form.model = data.model || ''
  form.fast_model = data.fast_model || ''
  form.review_model = data.review_model || ''
  form.scene_director_model = data.scene_director_model || ''
  form.state_extractor_model = data.state_extractor_model || ''
  form.temperature = Number(data.temperature ?? 0.7)
  form.max_tokens = Number(data.max_tokens ?? 4096)
  form.timeout_ms = Number(data.timeout_ms ?? 300000)
  maskedApiKey.value = data.api_key_masked || ''
  syncCurrentModelsIntoOptions([])
}

function assignResponse(data: LLMSettingsResponse) {
  assignSettings(data)
  presets.value = data.presets || []
  activePresetId.value = data.active_preset_id || null
  selectedPresetId.value = data.active_preset_id || null
  if (!presetName.value && activePresetId.value) {
    const active = presets.value.find(item => item.id === activePresetId.value)
    presetName.value = active?.name || ''
  }
  syncCurrentModelsIntoOptions(modelOptions.value)
}

function applyVendorPreset(vendor: string) {
  form.vendor = vendor
  if (vendor === 'claude') {
    form.api_format = 'anthropic_messages'
    return
  }

  form.api_format = vendor === 'codex' ? 'openai_responses' : 'openai_chat_completions'
  if (vendor === 'codex' && !form.model) form.model = 'gpt-5.2-codex'
}

function getViewportBounds() {
  const maxX = Math.max(FAB_MARGIN, window.innerWidth - FAB_SIZE - FAB_MARGIN)
  const maxY = Math.max(FAB_MARGIN, window.innerHeight - FAB_SIZE - FAB_MARGIN)
  return {
    minX: FAB_MARGIN,
    minY: FAB_MARGIN,
    maxX,
    maxY,
  }
}

function clampFabPosition(x: number, y: number) {
  const bounds = getViewportBounds()
  return {
    x: Math.min(bounds.maxX, Math.max(bounds.minX, x)),
    y: Math.min(bounds.maxY, Math.max(bounds.minY, y)),
  }
}

function defaultFabPosition() {
  const bounds = getViewportBounds()
  return {
    x: bounds.maxX,
    y: bounds.maxY,
  }
}

function saveFabPosition() {
  try {
    window.localStorage.setItem(FAB_STORAGE_KEY, JSON.stringify({
      x: fabPosition.x,
      y: fabPosition.y,
    }))
  } catch {
    /* ignore */
  }
}

function applyFabPosition(x: number, y: number, persist = true) {
  const next = clampFabPosition(x, y)
  fabPosition.x = next.x
  fabPosition.y = next.y
  if (persist) saveFabPosition()
}

function loadFabPosition() {
  const fallback = defaultFabPosition()
  try {
    const raw = window.localStorage.getItem(FAB_STORAGE_KEY)
    if (!raw) {
      applyFabPosition(fallback.x, fallback.y, false)
      return
    }
    const parsed = JSON.parse(raw) as { x?: number; y?: number }
    const x = Number(parsed?.x)
    const y = Number(parsed?.y)
    if (Number.isFinite(x) && Number.isFinite(y)) {
      applyFabPosition(x, y, false)
      return
    }
  } catch {
    /* ignore */
  }
  applyFabPosition(fallback.x, fallback.y, false)
}

function handlePointerMove(event: PointerEvent) {
  if (!dragState.active || event.pointerId !== dragState.pointerId) return

  const deltaX = event.clientX - dragState.startX
  const deltaY = event.clientY - dragState.startY
  if (!dragState.moved && Math.hypot(deltaX, deltaY) >= 6) {
    dragState.moved = true
  }
  if (!dragState.moved) return

  applyFabPosition(dragState.originX + deltaX, dragState.originY + deltaY)
}

function stopDragging() {
  dragState.active = false
  dragState.pointerId = -1
  dragState.startX = 0
  dragState.startY = 0
  dragState.originX = 0
  dragState.originY = 0
}

function handlePointerUp(event: PointerEvent) {
  if (!dragState.active || event.pointerId !== dragState.pointerId) return
  suppressNextClick.value = dragState.moved
  stopDragging()
}

function handlePointerDown(event: PointerEvent) {
  if (event.button !== 0) return
  dragState.active = true
  dragState.pointerId = event.pointerId
  dragState.startX = event.clientX
  dragState.startY = event.clientY
  dragState.originX = fabPosition.x
  dragState.originY = fabPosition.y
  dragState.moved = false
}

function handleFabClick() {
  if (suppressNextClick.value) {
    suppressNextClick.value = false
    return
  }
  showModal.value = true
}

function handleWindowResize() {
  applyFabPosition(fabPosition.x, fabPosition.y, false)
}

async function loadSettings() {
  loading.value = true
  try {
    const data = await llmSettingsApi.get()
    assignResponse(data)
  } finally {
    loading.value = false
  }
}

async function handleOpen() {
  testResult.value = null
  await loadSettings()
}

async function handleSave() {
  saving.value = true
  try {
    const saved = await llmSettingsApi.save({ ...form })
    assignResponse(saved)
    message.success('模型接入配置已保存')
  } catch (error) {
    const err = error as { response?: { data?: { detail?: string } }; message?: string }
    message.error(err.response?.data?.detail || err.message || '保存失败')
  } finally {
    saving.value = false
  }
}

async function handleSavePreset() {
  if (!presetName.value.trim()) {
    message.warning('先填写预设名称')
    return
  }

  presetSaving.value = true
  try {
    const result = await llmSettingsApi.savePreset({
      preset_id: selectedPresetId.value,
      name: presetName.value.trim(),
      set_active: true,
      settings: { ...form },
    })
    assignResponse(result)
    const active = presets.value.find(item => item.id === activePresetId.value)
    presetName.value = active?.name || presetName.value
    message.success('预设已保存并设为当前配置')
  } catch (error) {
    const err = error as { response?: { data?: { detail?: string } }; message?: string }
    message.error(err.response?.data?.detail || err.message || '保存预设失败')
  } finally {
    presetSaving.value = false
  }
}

async function handleApplyPreset() {
  if (!selectedPresetId.value) {
    message.warning('先选择一个预设')
    return
  }

  try {
    const result = await llmSettingsApi.activatePreset(selectedPresetId.value)
    assignResponse(result)
    const active = presets.value.find(item => item.id === activePresetId.value)
    presetName.value = active?.name || ''
    message.success('预设已应用')
  } catch (error) {
    const err = error as { response?: { data?: { detail?: string } }; message?: string }
    message.error(err.response?.data?.detail || err.message || '应用预设失败')
  }
}

async function handleDeletePreset() {
  if (!selectedPresetId.value) {
    message.warning('先选择一个预设')
    return
  }

  const preset = presets.value.find(item => item.id === selectedPresetId.value)
  dialog.warning({
    title: '删除预设',
    content: `确认删除预设“${preset?.name || '未命名预设'}”？`,
    positiveText: '删除',
    negativeText: '取消',
    async onPositiveClick() {
      const result = await llmSettingsApi.deletePreset(selectedPresetId.value as string)
      assignResponse(result)
      presetName.value = ''
      message.success('预设已删除')
    },
  })
}

async function handleTest() {
  testing.value = true
  testResult.value = null
  try {
    const result = await llmSettingsApi.test({ ...form })
    testResult.value = { success: true, message: result.message }
    message.success('连接测试成功')
  } catch (error) {
    const err = error as { response?: { data?: { detail?: string } }; message?: string }
    const detail = err.response?.data?.detail || err.message || '连接测试失败'
    testResult.value = { success: false, message: detail }
    message.error(detail)
  } finally {
    testing.value = false
  }
}

async function handleLoadModels() {
  modelsLoading.value = true
  try {
    const result = await llmSettingsApi.listModels({ ...form })
    modelOptions.value = mergeModelOptions(result.items, [
      form.model,
      form.fast_model,
      form.review_model,
      form.scene_director_model,
      form.state_extractor_model,
    ])
    if (!result.items.length) {
      message.warning('没有拉取到可选模型，请检查接口兼容性')
      return
    }
    message.success(`已获取 ${result.count} 个模型`)
  } catch (error) {
    const err = error as { response?: { data?: { detail?: string } }; message?: string }
    message.error(err.response?.data?.detail || err.message || '获取模型列表失败')
  } finally {
    modelsLoading.value = false
  }
}

onMounted(() => {
  loadFabPosition()
  window.addEventListener('pointermove', handlePointerMove)
  window.addEventListener('pointerup', handlePointerUp)
  window.addEventListener('pointercancel', handlePointerUp)
  window.addEventListener('resize', handleWindowResize)
})

onBeforeUnmount(() => {
  window.removeEventListener('pointermove', handlePointerMove)
  window.removeEventListener('pointerup', handlePointerUp)
  window.removeEventListener('pointercancel', handlePointerUp)
  window.removeEventListener('resize', handleWindowResize)
})
</script>

<style scoped>
.llm-fab-wrap {
  position: fixed;
  z-index: 1200;
}

.llm-fab {
  width: 56px;
  height: 56px;
  border: 1px solid rgba(255, 255, 255, 0.18);
  box-shadow: 0 14px 32px rgba(79, 70, 229, 0.28), 0 4px 12px rgba(15, 23, 42, 0.16);
  touch-action: none;
  user-select: none;
  cursor: grab;
}

.llm-fab:active {
  cursor: grabbing;
}

.llm-fab:hover {
  transform: translateY(-1px);
}

.llm-settings-modal :deep(.n-card) {
  border-radius: 18px;
}

.llm-settings-body {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.llm-tip {
  border-radius: 14px;
}

.llm-section-card {
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.96), rgba(246, 248, 255, 0.98));
  border: 1px solid rgba(99, 102, 241, 0.12);
}

.api-key-card {
  background: linear-gradient(180deg, rgba(248, 250, 255, 0.98), rgba(239, 246, 255, 0.98));
}

.preset-grid {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 10px;
}

.preset-card {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 14px 12px;
  border-radius: 14px;
  border: 1px solid rgba(99, 102, 241, 0.14);
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.94), rgba(244, 246, 255, 0.96));
  text-align: left;
  transition: transform 0.18s ease, box-shadow 0.18s ease, border-color 0.18s ease;
  cursor: pointer;
}

.preset-card:hover {
  transform: translateY(-1px);
  box-shadow: 0 8px 18px rgba(15, 23, 42, 0.08);
}

.preset-card--active {
  border-color: rgba(79, 70, 229, 0.55);
  box-shadow: 0 10px 24px rgba(79, 70, 229, 0.14);
  background: linear-gradient(180deg, rgba(238, 242, 255, 0.98), rgba(248, 250, 255, 0.98));
}

.preset-title {
  font-size: 14px;
  font-weight: 700;
  color: #1f2937;
}

.preset-sub {
  font-size: 12px;
  line-height: 1.45;
  color: #6b7280;
}

.llm-form :deep(.n-form-item) {
  margin-bottom: 0;
}

.llm-test-result {
  border-radius: 14px;
}

@media (max-width: 900px) {
  .preset-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
</style>
