<template>
  <n-modal v-model:show="visible" preset="card" title="核心引擎配置 (Model Matrix)" style="width: 600px">
    <n-form :model="formData" label-placement="top">
      <n-form-item label="服务商 (Provider)">
        <n-radio-group v-model:value="formData.provider">
          <n-radio-button value="openai">OpenAI (兼容 API)</n-radio-button>
          <n-radio-button value="anthropic">Anthropic (Claude)</n-radio-button>
        </n-radio-group>
      </n-form-item>

      <div v-if="formData.provider === 'openai'">
        <n-form-item label="API Key">
          <n-input v-model:value="formData.openai_api_key" type="password" show-password-on="click" placeholder="sk-..." />
        </n-form-item>
        <n-form-item label="Base URL (可选，留空则使用官方地址)">
          <n-input v-model:value="formData.openai_base_url" placeholder="https://api.openai.com/v1" />
        </n-form-item>
      </div>

      <div v-if="formData.provider === 'anthropic'">
        <n-form-item label="API Key">
          <n-input v-model:value="formData.anthropic_api_key" type="password" show-password-on="click" placeholder="sk-ant-..." />
        </n-form-item>
        <n-form-item label="Base URL (可选，留空则使用官方地址)">
          <n-input v-model:value="formData.anthropic_base_url" placeholder="https://api.anthropic.com" />
        </n-form-item>
      </div>

      <n-button type="info" dashed block @click="handleVerify" :loading="verifying" class="mb-4">
        🔗 测试连接并获取模型
      </n-button>

      <n-divider />

      <n-form-item label="创作主力模型 (Default Model)">
        <n-select v-model:value="formData.default_model" :options="modelOptions" tag filterable />
        <template #feedback>用于正文生成与大纲推理，建议选择智商最高的模型，如 gpt-4o</template>
      </n-form-item>

      <n-form-item label="分析经济模型 (Cheap Model)">
        <n-select v-model:value="formData.cheap_model" :options="modelOptions" tag filterable />
        <template #feedback>用于后台状态提取与审核，建议选择速度最快、最便宜的模型，如 gpt-4o-mini</template>
      </n-form-item>

      <n-space justify="end" class="mt-4">
        <n-button @click="visible = false">取消</n-button>
        <n-button type="primary" @click="handleSave" :loading="saving">保存配置</n-button>
      </n-space>
    </n-form>
  </n-modal>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useMessage } from 'naive-ui'
import { getLLMConfig, saveLLMConfig, verifyAndFetchModels, type LLMConfig } from '../../api/system'

const visible = ref(false)
const message = useMessage()
const verifying = ref(false)
const saving = ref(false)
const availableModels = ref<string[]>([])

const formData = ref<LLMConfig>({
  provider: 'openai',
  openai_api_key: '',
  openai_base_url: '',
  anthropic_api_key: '',
  anthropic_base_url: '',
  default_model: '',
  cheap_model: ''
})

const modelOptions = ref<{label: string, value: string}[]>([])

const loadData = async () => {
  try {
    const res = await getLLMConfig()
    if (res) {
      formData.value = { ...formData.value, ...res }
      if (formData.value.default_model) {
        modelOptions.value = [
          { label: formData.value.default_model, value: formData.value.default_model },
          { label: formData.value.cheap_model, value: formData.value.cheap_model }
        ]
      }
    }
  } catch (e) {
    console.error('Failed to load LLM config', e)
  }
}

const handleVerify = async () => {
  const p = formData.value.provider
  const key = p === 'openai' ? formData.value.openai_api_key : formData.value.anthropic_api_key
  const base = p === 'openai' ? formData.value.openai_base_url : formData.value.anthropic_base_url
  
  if (!key || key.includes('***')) {
    message.warning('请先输入完整且有效的 API Key')
    return
  }

  verifying.value = true
  try {
    const res = await verifyAndFetchModels(p, key, base)
    if (res && res.models) {
      availableModels.value = res.models
      modelOptions.value = availableModels.value.map(m => ({ label: m, value: m }))
      message.success(`成功获取 ${availableModels.value.length} 个模型`)
    }
  } catch (e: any) {
    message.error(e.response?.data?.detail || '连接失败，请检查端点和秘钥')
  } finally {
    verifying.value = false
  }
}

const handleSave = async () => {
  saving.value = true
  try {
    await saveLLMConfig(formData.value)
    message.success('配置保存成功，系统将使用新配置')
    visible.value = false
  } catch (e) {
    message.error('保存失败')
  } finally {
    saving.value = false
  }
}

const open = () => {
  visible.value = true
  loadData()
}

defineExpose({ open })
</script>

<style scoped>
.mb-4 { margin-bottom: 16px; }
.mt-4 { margin-top: 16px; }
</style>