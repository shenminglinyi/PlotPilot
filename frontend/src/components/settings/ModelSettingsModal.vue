<template>
  <n-modal
    v-model:show="visible"
    preset="card"
    title="核心引擎配置"
    style="width: 720px; max-width: 95vw"
    :mask-closable="false"
  >
    <n-alert type="info" :show-icon="false" class="mb-4">
      配置不同场景下使用的模型端点。统一模式下，所有角色共享同一组 API 地址与密钥；
      独立模式下可为每个角色指定不同的 provider。
    </n-alert>

    <div class="mode-switch mb-4">
      <n-switch v-model:value="isUnifiedMode" size="large">
        <template #checked>统一端点配置</template>
        <template #unchecked>独立端点配置</template>
      </n-switch>
    </div>

    <n-form :model="formData" label-placement="top" class="model-matrix-form">
      <!-- 主力模型（写作/分析） -->
      <n-card size="small" :bordered="true" class="role-card mb-3">
        <template #header>
          <div class="role-card-header">
            <span class="role-title">✍️ 主力模型</span>
            <n-tag size="small" type="success">写作 / 分析 / 规划</n-tag>
          </div>
        </template>
        <n-grid :cols="2" :x-gap="16" :y-gap="12">
          <n-gi>
            <n-form-item label="Provider">
              <n-select
                v-model:value="formData.default_model_provider"
                :options="providerOptions"
                placeholder="选择提供商"
              />
            </n-form-item>
          </n-gi>
          <n-gi>
            <n-form-item label="API Key">
              <n-input
                v-model:value="formData.default_model_api_key"
                type="password"
                show-password-on="click"
                placeholder="sk-..."
              />
            </n-form-item>
          </n-gi>
          <n-gi :span="2">
            <n-form-item label="Base URL（留空则使用默认）">
              <n-input
                v-model:value="formData.default_model_base_url"
                placeholder="例如：https://api.openai.com/v1 或兼容网关地址"
              />
            </n-form-item>
          </n-gi>
          <n-gi>
            <n-form-item label="模型名">
              <n-input v-model:value="formData.default_model" placeholder="网关文档中的主模型 ID" />
            </n-form-item>
          </n-gi>
        </n-grid>
      </n-card>

      <!-- 独立模式下的其他角色 -->
      <template v-if="!isUnifiedMode">
        <!-- 经济模型 -->
        <n-card size="small" :bordered="true" class="role-card mb-3">
          <template #header>
            <div class="role-card-header">
              <span class="role-title">⚡ 经济模型</span>
              <n-tag size="small" type="warning">批量操作 / 嵌入</n-tag>
            </div>
          </template>
          <n-grid :cols="2" :x-gap="16" :y-gap="12">
            <n-gi>
              <n-form-item label="Provider">
                <n-select v-model:value="formData.cheap_model_provider" :options="providerOptions" />
              </n-form-item>
            </n-gi>
            <n-gi>
              <n-form-item label="API Key">
                <n-input v-model:value="formData.cheap_model_api_key" type="password" show-password-on="click" />
              </n-form-item>
            </n-gi>
            <n-gi :span="2">
              <n-form-item label="Base URL">
                <n-input v-model:value="formData.cheap_model_base_url" placeholder="留空则跟随主力模型" />
              </n-form-item>
            </n-gi>
            <n-gi>
              <n-form-item label="模型名">
                <n-input v-model:value="formData.cheap_model" placeholder="轻量/低成本模型 ID（按网关文档填写）" />
              </n-form-item>
            </n-gi>
          </n-grid>
        </n-card>

        <!-- 知识图谱模型 -->
        <n-card size="small" :bordered="true" class="role-card mb-3">
          <template #header>
            <div class="role-card-header">
              <span class="role-title">🕸️ 知识图谱模型</span>
              <n-tag size="small" type="info">三元组抽取</n-tag>
            </div>
          </template>
          <n-grid :cols="2" :x-gap="16" :y-gap="12">
            <n-gi>
              <n-form-item label="Provider">
                <n-select v-model:value="formData.knowledge_model_provider" :options="providerOptions" />
              </n-form-item>
            </n-gi>
            <n-gi>
              <n-form-item label="API Key">
                <n-input v-model:value="formData.knowledge_model_api_key" type="password" show-password-on="click" />
              </n-form-item>
            </n-gi>
            <n-gi :span="2">
              <n-form-item label="Base URL">
                <n-input v-model:value="formData.knowledge_model_base_url" placeholder="留空则跟随主力模型" />
              </n-form-item>
            </n-gi>
            <n-gi>
              <n-form-item label="模型名">
                <n-input v-model:value="formData.knowledge_model" placeholder="需要强推理能力" />
              </n-form-item>
            </n-gi>
          </n-grid>
        </n-card>
      </template>
    </n-form>

    <template #action>
      <n-space justify="end" :size="12">
        <n-button @click="visible = false">取消</n-button>
        <n-button type="primary" :loading="saving" @click="handleSave">保存配置</n-button>
      </n-space>
    </template>
  </n-modal>
</template>

<script setup lang="ts">
import { ref, reactive } from 'vue'
import { useMessage } from 'naive-ui'
import { llmControlApi, type LLMControlPanelData, type LLMProfile } from '../../api/llmControl'

const message = useMessage()
const visible = ref(false)
const saving = ref(false)
const isUnifiedMode = ref(true)

const providerOptions = [
  { label: 'OpenAI 兼容', value: 'openai' },
  { label: 'Anthropic / Claude', value: 'anthropic' },
  { label: 'Gemini', value: 'gemini' },
]

interface ModelRoleConfig {
  default_model_provider: string
  default_model_api_key: string
  default_model_base_url: string
  default_model: string
  cheap_model_provider: string
  cheap_model_api_key: string
  cheap_model_base_url: string
  cheap_model: string
  knowledge_model_provider: string
  knowledge_model_api_key: string
  knowledge_model_base_url: string
  knowledge_model: string
}

const formData = reactive<ModelRoleConfig>({
  default_model_provider: 'openai',
  default_model_api_key: '',
  default_model_base_url: '',
  default_model: '',
  cheap_model_provider: 'openai',
  cheap_model_api_key: '',
  cheap_model_base_url: '',
  cheap_model: '',
  knowledge_model_provider: 'openai',
  knowledge_model_api_key: '',
  knowledge_model_base_url: '',
  knowledge_model: '',
})

async function loadData() {
  try {
    const data: LLMControlPanelData = await llmControlApi.getPanel()
    const active = data.config.profiles.find((p) => p.id === data.config.active_profile_id) || data.config.profiles[0]
    if (active) {
      formData.default_model_provider = active.protocol
      formData.default_model_api_key = active.api_key
      formData.default_model_base_url = active.base_url
      formData.default_model = active.model
    }
    // 如果有多个 profile，尝试映射到不同角色
    if (data.config.profiles.length >= 2) {
      const cheap = data.config.profiles.find((p) => p.name.includes('经济') || p.name.includes('Cheap'))
      if (cheap) {
        formData.cheap_model_provider = cheap.protocol
        formData.cheap_model_api_key = cheap.api_key
        formData.cheap_model_base_url = cheap.base_url
        formData.cheap_model = cheap.model
      }
    }
    if (data.config.profiles.length >= 3) {
      const kg = data.config.profiles.find((p) => p.name.includes('知识') || p.name.includes('Knowledge'))
      if (kg) {
        formData.knowledge_model_provider = kg.protocol
        formData.knowledge_model_api_key = kg.api_key
        formData.knowledge_model_base_url = kg.base_url
        formData.knowledge_model = kg.model
      }
    }
    // 检测是否为独立模式
    isUnifiedMode.value = !formData.cheap_model_api_key && !formData.knowledge_model_api_key
  } catch {
    // 使用默认值
  }
}

async function handleSave() {
  saving.value = true
  try {
    const data: LLMControlPanelData = await llmControlApi.getPanel()

    // 构建或更新 profiles
    const profiles: LLMProfile[] = [...data.config.profiles]

    // 更新或创建主力 profile
    const mainProfile: LLMProfile = {
      id: profiles[0]?.id || 'main-default',
      name: '主力模型',
      protocol: formData.default_model_provider as any,
      base_url: formData.default_model_base_url,
      api_key: formData.default_model_api_key,
      model: formData.default_model,
      temperature: 0.7,
      max_tokens: 8192,
      timeout_seconds: 300,
      extra_headers: {},
      extra_query: {},
      extra_body: {},
      notes: '',
      preset_key: 'custom-openai-compatible',
      use_legacy_chat_completions: profiles[0]?.use_legacy_chat_completions ?? false,
    }

    if (profiles.length > 0 && profiles[0].id === mainProfile.id) {
      profiles[0] = mainProfile
    } else {
      profiles.unshift(mainProfile)
    }

    // 独立模式：添加经济和知识图谱 profile
    if (!isUnifiedMode.value) {
      const upsertRole = (name: string, provider: string, key: string, url: string, model: string) => {
        const existing = profiles.findIndex((p) => p.name === name)
        const roleProfile: LLMProfile = {
          id: existing >= 0 ? profiles[existing].id : `${name.toLowerCase()}-${Date.now()}`,
          name,
          protocol: provider as any,
          base_url: url,
          api_key: key,
          model,
          temperature: 0.7,
          max_tokens: 4096,
          timeout_seconds: 300,
          extra_headers: {},
          extra_query: {},
          extra_body: {},
          notes: '',
          preset_key: 'custom-openai-compatible',
          use_legacy_chat_completions: existing >= 0 ? (profiles[existing].use_legacy_chat_completions ?? false) : false,
        }
        if (existing >= 0) {
          profiles[existing] = roleProfile
        } else {
          profiles.push(roleProfile)
        }
      }

      upsertRole('经济模型', formData.cheap_model_provider, formData.cheap_model_api_key, formData.cheap_model_base_url, formData.cheap_model)
      upsertRole('知识图谱模型', formData.knowledge_model_provider, formData.knowledge_model_api_key, formData.knowledge_model_base_url, formData.knowledge_model)
    } else {
      // 统一模式：删除多余的角色 profile，只保留主力
      for (let i = profiles.length - 1; i >= 0; i--) {
        if (profiles[i].name !== '主力模型' && (profiles[i].name.includes('经济') || profiles[i].name.includes('知识'))) {
          profiles.splice(i, 1)
        }
      }
    }

    const newConfig = {
      ...data.config,
      version: 1,
      active_profile_id: mainProfile.id,
      profiles,
    }

    await llmControlApi.saveConfig(newConfig)
    message.success('配置已保存，系统已切换路由通道')
    visible.value = false
  } catch (e) {
    message.error('保存失败')
  } finally {
    saving.value = false
  }
}

function open() {
  visible.value = true
  void loadData()
}

defineExpose({ open })
</script>

<style scoped>
.mb-4 { margin-bottom: 16px; }
.mb-3 { margin-bottom: 12px; }

.role-card-header {
  display: flex;
  align-items: center;
  gap: 8px;
}

.role-title {
  font-weight: 600;
  font-size: 14px;
}

.model-matrix-form :deep(.n-form-item) {
  margin-bottom: 0;
}
</style>
