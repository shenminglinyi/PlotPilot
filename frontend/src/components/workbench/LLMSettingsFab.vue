<template>
  <div class="llm-fab-wrap">
    <n-button class="llm-fab" circle type="primary" size="large" @click="showModal = true">
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

        <n-card size="small" :bordered="false" class="llm-section-card">
          <template #header>
            <n-space justify="space-between" align="center" style="width: 100%">
              <span>模型列表</span>
              <n-button type="primary" secondary :loading="modelsLoading" @click="handleLoadModels">
                拉取模型列表
              </n-button>
            </n-space>
          </template>

          <n-text depth="3" style="font-size: 12px">
            拉取后，主模型和高级模型都可以直接下拉选择；不在列表里的模型也可以手动填入。
          </n-text>
        </n-card>

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
            <n-gi :span="24">
              <n-form-item label="Base URL">
                <n-input v-model:value="form.base_url" placeholder="例如 https://api.jucode.cn/v1" />
              </n-form-item>
            </n-gi>
          </n-form>
        </n-grid>

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
import { computed, reactive, ref } from 'vue'
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

const formatLabel = computed(() => (
  form.api_format === 'anthropic_messages' ? 'Anthropic' : 'OpenAI Compatible'
))

const apiKeyPlaceholder = computed(() => (
  maskedApiKey.value ? `当前已保存：${maskedApiKey.value}；留空则不覆盖` : '输入 API Key'
))

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
    if (!form.base_url) form.base_url = 'https://api.anthropic.com'
    return
  }

  form.api_format = 'openai_chat_completions'
  if (vendor === 'openai' && !form.base_url) form.base_url = 'https://api.openai.com/v1'
  if (vendor === 'codex' && !form.model) form.model = 'gpt-5.2-codex'
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
</script>

<style scoped>
.llm-fab-wrap {
  position: fixed;
  right: 22px;
  bottom: 22px;
  z-index: 1200;
}

.llm-fab {
  width: 56px;
  height: 56px;
  border: 1px solid rgba(255, 255, 255, 0.18);
  box-shadow: 0 14px 32px rgba(79, 70, 229, 0.28), 0 4px 12px rgba(15, 23, 42, 0.16);
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

  .llm-fab-wrap {
    right: 16px;
    bottom: 16px;
  }
}
</style>
