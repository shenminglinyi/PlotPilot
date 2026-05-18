<template>
  <div class="engine-matrix">
    <n-alert type="info" :show-icon="false" class="mb-4">
      配置不同场景下使用的模型端点。统一模式下，所有角色共享同一组 API 地址与密钥；
      独立模式下可按标签切换各角色。展开「推理超参」可调整温度、最大输出 token 与请求超时。
    </n-alert>

    <div class="mode-switch mb-4">
      <n-switch v-model:value="isUnifiedMode" size="large">
        <template #checked>统一端点配置</template>
        <template #unchecked>独立端点配置</template>
      </n-switch>
    </div>

    <div class="engine-matrix-body">
      <template v-if="isUnifiedMode">
        <n-card size="small" :bordered="true" class="role-card mb-3">
          <template #header>
            <div class="role-card-header">
              <span class="role-title">✍️ 主力模型</span>
              <n-tag size="small" type="success">写作 / 分析 / 规划</n-tag>
            </div>
          </template>
          <endpoint-grid
            v-model:provider="formData.default_model_provider"
            v-model:api-key="formData.default_model_api_key"
            v-model:base-url="formData.default_model_base_url"
            v-model:model="formData.default_model"
            base-url-placeholder="例如：https://api.openai.com/v1 或兼容网关地址"
            model-placeholder="网关文档中的主模型 ID"
          />
          <inference-collapse
            v-model:temperature="formData.default_temperature"
            v-model:max-tokens="formData.default_max_tokens"
            v-model:timeout-seconds="formData.default_timeout_seconds"
          />
        </n-card>
      </template>

      <n-tabs v-else type="line" animated class="independent-tabs">
        <n-tab-pane name="main" tab="主力模型">
          <n-card size="small" :bordered="true" class="role-card inner-tab-card">
            <template #header>
              <div class="role-card-header">
                <span class="role-title">✍️ 主力模型</span>
                <n-tag size="small" type="success">写作 / 分析 / 规划</n-tag>
              </div>
            </template>
            <endpoint-grid
              v-model:provider="formData.default_model_provider"
              v-model:api-key="formData.default_model_api_key"
              v-model:base-url="formData.default_model_base_url"
              v-model:model="formData.default_model"
              base-url-placeholder="留空则使用协议默认"
              model-placeholder="主模型 ID"
            />
            <inference-collapse
              v-model:temperature="formData.default_temperature"
              v-model:max-tokens="formData.default_max_tokens"
              v-model:timeout-seconds="formData.default_timeout_seconds"
            />
          </n-card>
        </n-tab-pane>
        <n-tab-pane name="cheap" tab="经济模型">
          <n-card size="small" :bordered="true" class="role-card inner-tab-card">
            <template #header>
              <div class="role-card-header">
                <span class="role-title">⚡ 经济模型</span>
                <n-tag size="small" type="warning">批量操作 / 嵌入</n-tag>
              </div>
            </template>
            <endpoint-grid
              v-model:provider="formData.cheap_model_provider"
              v-model:api-key="formData.cheap_model_api_key"
              v-model:base-url="formData.cheap_model_base_url"
              v-model:model="formData.cheap_model"
              base-url-placeholder="留空则跟随主力模型"
              model-placeholder="轻量/低成本模型 ID（按网关文档填写）"
            />
            <inference-collapse
              v-model:temperature="formData.cheap_temperature"
              v-model:max-tokens="formData.cheap_max_tokens"
              v-model:timeout-seconds="formData.cheap_timeout_seconds"
            />
          </n-card>
        </n-tab-pane>
        <n-tab-pane name="kg" tab="知识图谱">
          <n-card size="small" :bordered="true" class="role-card inner-tab-card">
            <template #header>
              <div class="role-card-header">
                <span class="role-title">🕸️ 知识图谱模型</span>
                <n-tag size="small" type="info">三元组抽取</n-tag>
              </div>
            </template>
            <endpoint-grid
              v-model:provider="formData.knowledge_model_provider"
              v-model:api-key="formData.knowledge_model_api_key"
              v-model:base-url="formData.knowledge_model_base_url"
              v-model:model="formData.knowledge_model"
              base-url-placeholder="留空则跟随主力模型"
              model-placeholder="需要较强遵循指令与结构化输出能力"
            />
            <inference-collapse
              v-model:temperature="formData.knowledge_temperature"
              v-model:max-tokens="formData.knowledge_max_tokens"
              v-model:timeout-seconds="formData.knowledge_timeout_seconds"
            />
          </n-card>
        </n-tab-pane>
      </n-tabs>
    </div>

    <div class="engine-footer">
      <n-space justify="end" :size="12">
        <n-button :loading="saving" @click="handleSave">保存配置</n-button>
      </n-space>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useMessage } from 'naive-ui'
import { llmControlApi, type LLMControlPanelData, type LLMProfile, type LLMProtocol } from '@/api/llmControl'
import EndpointGrid from './EngineMatrixEndpointGrid.vue'
import InferenceCollapse from './EngineMatrixInferenceCollapse.vue'

const message = useMessage()
const saving = ref(false)
const isUnifiedMode = ref(true)

const ROLE_MAIN = '主力模型'
const ROLE_CHEAP = '经济模型'
const ROLE_KG = '知识图谱模型'

interface ModelRoleConfig {
  default_model_provider: string
  default_model_api_key: string
  default_model_base_url: string
  default_model: string
  default_temperature: number
  default_max_tokens: number
  default_timeout_seconds: number
  cheap_model_provider: string
  cheap_model_api_key: string
  cheap_model_base_url: string
  cheap_model: string
  cheap_temperature: number
  cheap_max_tokens: number
  cheap_timeout_seconds: number
  knowledge_model_provider: string
  knowledge_model_api_key: string
  knowledge_model_base_url: string
  knowledge_model: string
  knowledge_temperature: number
  knowledge_max_tokens: number
  knowledge_timeout_seconds: number
}

const formData = reactive<ModelRoleConfig>({
  default_model_provider: 'openai',
  default_model_api_key: '',
  default_model_base_url: '',
  default_model: '',
  default_temperature: 0.7,
  default_max_tokens: 8192,
  default_timeout_seconds: 300,
  cheap_model_provider: 'openai',
  cheap_model_api_key: '',
  cheap_model_base_url: '',
  cheap_model: '',
  cheap_temperature: 0.5,
  cheap_max_tokens: 4096,
  cheap_timeout_seconds: 300,
  knowledge_model_provider: 'openai',
  knowledge_model_api_key: '',
  knowledge_model_base_url: '',
  knowledge_model: '',
  knowledge_temperature: 0.3,
  knowledge_max_tokens: 8192,
  knowledge_timeout_seconds: 300,
})

function pickMainProfile(profiles: LLMProfile[], activeId: string | null): LLMProfile | undefined {
  return profiles.find((p) => p.name === ROLE_MAIN)
    || profiles.find((p) => p.id === activeId)
    || profiles[0]
}

function pickCheapProfile(profiles: LLMProfile[]): LLMProfile | undefined {
  return profiles.find((p) => p.name === ROLE_CHEAP)
    || profiles.find((p) => p.name.includes('经济') && (p.name.includes('模型') || p.name.toLowerCase().includes('cheap')))
}

function pickKgProfile(profiles: LLMProfile[]): LLMProfile | undefined {
  return profiles.find((p) => p.name === ROLE_KG)
    || profiles.find((p) => p.name.includes('知识') && p.name.includes('图谱'))
}

function applyProfileToForm(prefix: 'default' | 'cheap' | 'knowledge', p: LLMProfile | undefined) {
  if (!p) return
  if (prefix === 'default') {
    formData.default_model_provider = p.protocol
    formData.default_model_api_key = p.api_key
    formData.default_model_base_url = p.base_url
    formData.default_model = p.model
    formData.default_temperature = p.temperature
    formData.default_max_tokens = p.max_tokens
    formData.default_timeout_seconds = p.timeout_seconds
    return
  }
  if (prefix === 'cheap') {
    formData.cheap_model_provider = p.protocol
    formData.cheap_model_api_key = p.api_key
    formData.cheap_model_base_url = p.base_url
    formData.cheap_model = p.model
    formData.cheap_temperature = p.temperature
    formData.cheap_max_tokens = p.max_tokens
    formData.cheap_timeout_seconds = p.timeout_seconds
    return
  }
  formData.knowledge_model_provider = p.protocol
  formData.knowledge_model_api_key = p.api_key
  formData.knowledge_model_base_url = p.base_url
  formData.knowledge_model = p.model
  formData.knowledge_temperature = p.temperature
  formData.knowledge_max_tokens = p.max_tokens
  formData.knowledge_timeout_seconds = p.timeout_seconds
}

async function loadData() {
  try {
    const data: LLMControlPanelData = await llmControlApi.getPanel()
    const profiles = data.config.profiles
    const main = pickMainProfile(profiles, data.config.active_profile_id)
    applyProfileToForm('default', main)
    applyProfileToForm('cheap', pickCheapProfile(profiles))
    applyProfileToForm('knowledge', pickKgProfile(profiles))
    isUnifiedMode.value = (data.config.endpoint_mode ?? 'unified') !== 'independent'
  } catch {
    /* 使用默认值 */
  }
}

function buildProfilePayload(
  existing: LLMProfile | undefined,
  idFallback: string,
  name: string,
  provider: string,
  key: string,
  url: string,
  model: string,
  temperature: number,
  maxTokens: number,
  timeoutSeconds: number,
): LLMProfile {
  return {
    id: existing?.id || idFallback,
    name,
    protocol: provider as LLMProtocol,
    base_url: url,
    api_key: key,
    model,
    temperature,
    max_tokens: maxTokens,
    timeout_seconds: Math.round(timeoutSeconds),
    extra_headers: existing?.extra_headers ?? {},
    extra_query: existing?.extra_query ?? {},
    extra_body: existing?.extra_body ?? {},
    notes: existing?.notes ?? '',
    preset_key: existing?.preset_key ?? 'custom-openai-compatible',
    use_legacy_chat_completions: existing?.use_legacy_chat_completions ?? false,
  }
}

const roleKeyFlag = computed(() => (isUnifiedMode.value ? 'uni' : 'ind'))

async function handleSave() {
  saving.value = true
  try {
    const data: LLMControlPanelData = await llmControlApi.getPanel()
    const profiles: LLMProfile[] = [...data.config.profiles]

    const mainExisting =
      profiles.find((p) => p.name === ROLE_MAIN)
      || profiles.find((p) => p.id === data.config.active_profile_id)
      || profiles[0]

    const mainProfile = buildProfilePayload(
      mainExisting,
      mainExisting?.id || 'main-default',
      ROLE_MAIN,
      formData.default_model_provider,
      formData.default_model_api_key,
      formData.default_model_base_url,
      formData.default_model,
      formData.default_temperature,
      formData.default_max_tokens,
      formData.default_timeout_seconds,
    )

    const idx0 = profiles.findIndex((p) => p.id === mainProfile.id)
    if (idx0 >= 0) {
      profiles[idx0] = mainProfile
    } else {
      const iNamed = profiles.findIndex((p) => p.name === ROLE_MAIN)
      if (iNamed >= 0) profiles[iNamed] = mainProfile
      else profiles.unshift(mainProfile)
    }

    if (!isUnifiedMode.value) {
      const upsertRole = (
        name: string,
        idSeed: string,
        provider: string,
        key: string,
        url: string,
        model: string,
        temperature: number,
        maxTokens: number,
        timeoutSeconds: number,
      ) => {
        const existingIdx = profiles.findIndex((p) => p.name === name)
        const existing = existingIdx >= 0 ? profiles[existingIdx] : undefined
        const roleProfile = buildProfilePayload(
          existing,
          existing?.id || `${idSeed}-${roleKeyFlag.value}-${Date.now()}`,
          name,
          provider,
          key,
          url,
          model,
          temperature,
          maxTokens,
          timeoutSeconds,
        )
        if (existingIdx >= 0) profiles[existingIdx] = roleProfile
        else profiles.push(roleProfile)
      }

      upsertRole(
        ROLE_CHEAP,
        'cheap',
        formData.cheap_model_provider,
        formData.cheap_model_api_key,
        formData.cheap_model_base_url,
        formData.cheap_model,
        formData.cheap_temperature,
        formData.cheap_max_tokens,
        formData.cheap_timeout_seconds,
      )
      upsertRole(
        ROLE_KG,
        'kg',
        formData.knowledge_model_provider,
        formData.knowledge_model_api_key,
        formData.knowledge_model_base_url,
        formData.knowledge_model,
        formData.knowledge_temperature,
        formData.knowledge_max_tokens,
        formData.knowledge_timeout_seconds,
      )
    } else {
      for (let i = profiles.length - 1; i >= 0; i--) {
        const n = profiles[i].name
        if (n === ROLE_MAIN) continue
        if (
          n === ROLE_CHEAP
          || n === ROLE_KG
          || (n.includes('经济') && n.includes('模型'))
          || (n.includes('知识') && n.includes('图谱'))
        ) {
          profiles.splice(i, 1)
        }
      }
    }

    const newConfig = {
      ...data.config,
      version: 1,
      endpoint_mode: (isUnifiedMode.value ? 'unified' : 'independent') as 'unified' | 'independent',
      active_profile_id: mainProfile.id,
      profiles,
    }

    await llmControlApi.saveConfig(newConfig)
    message.success('配置已保存，系统已切换路由通道')
    await loadData()
  } catch {
    message.error('保存失败')
  } finally {
    saving.value = false
  }
}

onMounted(() => {
  void loadData()
})
</script>

<style scoped>
.engine-matrix {
  padding-bottom: 8px;
}

.mb-4 { margin-bottom: 16px; }
.mb-3 { margin-bottom: 12px; }
.mt-3 { margin-top: 12px; }

.engine-matrix-body {
  max-height: min(72vh, 760px);
  overflow-x: hidden;
  overflow-y: auto;
  padding-right: 6px;
}

.role-card-header {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.role-title {
  font-weight: 600;
  font-size: 14px;
}

.inner-tab-card {
  margin-top: 8px;
}

.independent-tabs :deep(.n-tabs-nav) {
  flex-wrap: wrap;
}

.engine-footer {
  margin-top: 20px;
  padding-top: 16px;
  border-top: 1px solid var(--n-divider-color);
}
</style>
