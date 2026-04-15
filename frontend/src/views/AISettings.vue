<template>
  <div class="settings-page">
    <main class="settings-main">
      <header class="settings-header">
        <n-button quaternary @click="router.push('/')">返回书目</n-button>
        <div>
          <h1>AI 设置</h1>
          <p>填写模型凭证，保存后可立即测试连通。</p>
        </div>
      </header>

      <section class="settings-panel">
        <n-spin :show="loading">
          <n-form label-placement="top">
            <n-form-item label="模型服务">
              <n-select
                v-model:value="form.provider"
                :options="providerOptions"
                @update:value="handleProviderChange"
              />
            </n-form-item>

            <n-form-item label="API Key">
              <n-input
                v-model:value="form.api_key"
                type="password"
                show-password-on="click"
                :placeholder="keyPlaceholder"
                clearable
              />
            </n-form-item>

            <n-form-item label="模型">
              <n-select
                v-model:value="form.model"
                :options="modelOptions"
                tag
                filterable
                placeholder="选择或输入模型 ID"
              />
            </n-form-item>

            <n-form-item label="Base URL">
              <n-input v-model:value="form.base_url" placeholder="默认可留空" />
            </n-form-item>

            <n-alert v-if="savedInfo" type="info" :show-icon="false" class="settings-alert">
              当前已保存：{{ savedInfo }}
            </n-alert>

            <n-alert
              v-if="testResult"
              :type="testResult.ok ? 'success' : 'error'"
              :title="testResult.ok ? '连接成功' : '连接失败'"
              class="settings-alert"
            >
              <div>{{ testResult.message }}</div>
              <div v-if="testResult.latency_ms">耗时：{{ testResult.latency_ms }} ms</div>
              <div v-if="testResult.sample">返回：{{ testResult.sample }}</div>
            </n-alert>

            <n-space justify="end" class="settings-actions">
              <n-button :loading="testing" secondary @click="testConnection">
                测试连接
              </n-button>
              <n-button type="primary" :loading="saving" @click="saveSettings">
                保存设置
              </n-button>
            </n-space>
          </n-form>
        </n-spin>
      </section>
    </main>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useMessage } from 'naive-ui'
import {
  aiSettingsApi,
  type AIConnectionTestResult,
  type AIProvider,
  type AISettings,
  type AISettingsUpdate,
} from '@/api/aiSettings'

const router = useRouter()
const message = useMessage()

const loading = ref(false)
const saving = ref(false)
const testing = ref(false)
const saved = ref<AISettings | null>(null)
const testResult = ref<AIConnectionTestResult | null>(null)

const form = reactive<AISettingsUpdate>({
  provider: 'ark',
  api_key: '',
  model: 'doubao-seed-2-0-mini-260215',
  base_url: 'https://ark.cn-beijing.volces.com/api/v3',
})

const providerOptions = [
  { label: '豆包 / 火山方舟', value: 'ark' },
  { label: 'Claude / Anthropic', value: 'anthropic' },
  { label: 'OpenAI / 兼容服务', value: 'openai' },
]

const providerDefaults: Record<AIProvider, { model: string; base_url: string }> = {
  ark: {
    model: 'doubao-seed-2-0-mini-260215',
    base_url: 'https://ark.cn-beijing.volces.com/api/v3',
  },
  anthropic: {
    model: 'claude-sonnet-4-6',
    base_url: '',
  },
  openai: {
    model: 'gpt-4o',
    base_url: '',
  },
}

const modelMap: Record<AIProvider, Array<{ label: string; value: string }>> = {
  ark: [
    { label: 'doubao-seed-2-0-mini-260215', value: 'doubao-seed-2-0-mini-260215' },
    { label: 'doubao-seed-1-6-250615', value: 'doubao-seed-1-6-250615' },
  ],
  anthropic: [
    { label: 'claude-sonnet-4-6', value: 'claude-sonnet-4-6' },
    { label: 'claude-3-5-sonnet-20241022', value: 'claude-3-5-sonnet-20241022' },
  ],
  openai: [
    { label: 'gpt-4o', value: 'gpt-4o' },
    { label: 'gpt-4o-mini', value: 'gpt-4o-mini' },
  ],
}

const modelOptions = computed(() => modelMap[form.provider as AIProvider])

const keyPlaceholder = computed(() => {
  if (saved.value?.has_api_key && saved.value.provider === form.provider) {
    return `已保存：${saved.value.api_key_hint}，留空表示不修改`
  }
  return '粘贴 API Key'
})

const savedInfo = computed(() => {
  if (!saved.value) return ''
  const keyState = saved.value.has_api_key ? `Key ${saved.value.api_key_hint}` : '未保存 Key'
  return `${providerLabel(saved.value.provider)} / ${saved.value.model} / ${keyState}`
})

function providerLabel(provider: AIProvider) {
  return providerOptions.find(item => item.value === provider)?.label || provider
}

function applySettings(data: AISettings) {
  saved.value = data
  form.provider = data.provider
  form.model = data.model || providerDefaults[data.provider].model
  form.base_url = data.base_url || providerDefaults[data.provider].base_url
  form.api_key = ''
}

async function loadSettings() {
  loading.value = true
  try {
    applySettings(await aiSettingsApi.get())
  } catch {
    message.error('加载 AI 设置失败')
  } finally {
    loading.value = false
  }
}

function handleProviderChange(provider: AIProvider) {
  const defaults = providerDefaults[provider]
  form.model = defaults.model
  form.base_url = defaults.base_url
  form.api_key = ''
  testResult.value = null
}

function payload(): AISettingsUpdate {
  const data: AISettingsUpdate = {
    provider: form.provider,
    model: form.model?.trim(),
    base_url: form.base_url?.trim(),
  }
  if (form.api_key?.trim()) {
    data.api_key = form.api_key.trim()
  }
  return data
}

async function saveSettings() {
  saving.value = true
  testResult.value = null
  try {
    applySettings(await aiSettingsApi.update(payload()))
    message.success('AI 设置已保存')
  } catch (error: any) {
    message.error(error?.response?.data?.detail || '保存失败')
  } finally {
    saving.value = false
  }
}

async function testConnection() {
  testing.value = true
  testResult.value = null
  try {
    testResult.value = await aiSettingsApi.test(payload())
  } catch (error: any) {
    testResult.value = {
      ok: false,
      provider: form.provider,
      model: form.model || '',
      latency_ms: 0,
      message: error?.response?.data?.detail || '测试失败',
      sample: '',
    }
  } finally {
    testing.value = false
  }
}

onMounted(loadSettings)
</script>

<style scoped>
.settings-page {
  min-height: 100vh;
  background: #eef1f7;
  padding: 32px;
}

.settings-main {
  max-width: 860px;
  margin: 0 auto;
}

.settings-header {
  display: flex;
  align-items: flex-start;
  gap: 18px;
  margin-bottom: 24px;
}

.settings-header h1 {
  margin: 0 0 6px;
  font-size: 28px;
  color: #0f172a;
}

.settings-header p {
  margin: 0;
  color: #64748b;
}

.settings-panel {
  background: #fff;
  border: 1px solid #dbe3ef;
  border-radius: 8px;
  padding: 24px;
}

.settings-alert {
  margin-bottom: 16px;
}

.settings-actions {
  margin-top: 8px;
}

@media (max-width: 720px) {
  .settings-page {
    padding: 16px;
  }

  .settings-header {
    flex-direction: column;
  }
}
</style>
