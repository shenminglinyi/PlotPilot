<template>
  <n-modal v-model:show="visible" preset="card" title="核心引擎配置 (Model Matrix)" style="width: 700px">
    <n-form :model="formData" label-placement="top">
      
      <!-- 创作主力模型配置区 -->
      <n-card size="small" class="mb-4" title="✨ 创作主力模型 (Default Model)">
        <template #header-extra>
          <n-text depth="3" class="text-xs">用于正文连写与复杂逻辑推理</n-text>
        </template>
        
        <n-form-item label="服务商 (Provider)">
          <n-radio-group v-model:value="formData.default_model_provider" @update:value="() => formData.default_model = ''">
            <n-radio-button value="openai">OpenAI 兼容 API</n-radio-button>
            <n-radio-button value="anthropic">Anthropic (Claude)</n-radio-button>
          </n-radio-group>
        </n-form-item>

        <n-form-item label="API Key">
          <n-input v-model:value="formData.default_model_api_key" type="password" show-password-on="click" placeholder="sk-..." />
        </n-form-item>

        <n-form-item label="Base URL (留空则使用官方地址)">
          <n-input v-model:value="formData.default_model_base_url" placeholder="如 https://api.deepseek.com/v1" />
        </n-form-item>

        <n-button type="info" dashed block @click="handleVerify('default')" :loading="verifyingDefault" class="mb-4">
          🔗 测试主力端点并获取模型
        </n-button>

        <n-form-item label="选择主力模型">
          <n-select v-model:value="formData.default_model" :options="defaultModelOptions" tag filterable />
        </n-form-item>
      </n-card>

      <!-- 分析经济模型配置区 -->
      <n-card size="small" class="mb-4" title="⚡ 分析经济模型 (Cheap Model)">
        <template #header-extra>
          <n-text depth="3" class="text-xs">用于后台数据提取、打分与摘要</n-text>
        </template>
        
        <n-form-item label="服务商 (Provider)">
          <n-radio-group v-model:value="formData.cheap_model_provider" @update:value="() => formData.cheap_model = ''">
            <n-radio-button value="openai">OpenAI 兼容 API</n-radio-button>
            <n-radio-button value="anthropic">Anthropic (Claude)</n-radio-button>
          </n-radio-group>
        </n-form-item>

        <n-form-item label="API Key">
          <n-input v-model:value="formData.cheap_model_api_key" type="password" show-password-on="click" placeholder="sk-..." />
        </n-form-item>

        <n-form-item label="Base URL (留空则使用官方地址)">
          <n-input v-model:value="formData.cheap_model_base_url" placeholder="如 https://api.openai.com/v1" />
        </n-form-item>

        <n-button type="info" dashed block @click="handleVerify('cheap')" :loading="verifyingCheap" class="mb-4">
          🔗 测试经济端点并获取模型
        </n-button>

        <n-form-item label="选择经济模型">
          <n-select v-model:value="formData.cheap_model" :options="cheapModelOptions" tag filterable />
        </n-form-item>
      </n-card>

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
const verifyingDefault = ref(false)
const verifyingCheap = ref(false)
const saving = ref(false)

const formData = ref<LLMConfig>({
  provider: 'openai',
  default_model_provider: 'openai',
  default_model_api_key: '',
  default_model_base_url: '',
  default_model: '',
  cheap_model_provider: 'openai',
  cheap_model_api_key: '',
  cheap_model_base_url: '',
  cheap_model: ''
})

const defaultModelOptions = ref<{label: string, value: string}[]>([])
const cheapModelOptions = ref<{label: string, value: string}[]>([])

const loadData = async () => {
  try {
    const res = await getLLMConfig()
    if (res && res.data) {
      formData.value = { ...formData.value, ...res.data }
      
      // 初始化下拉框展示
      if (formData.value.default_model) {
        defaultModelOptions.value = [{ label: formData.value.default_model, value: formData.value.default_model }]
      }
      if (formData.value.cheap_model) {
        cheapModelOptions.value = [{ label: formData.value.cheap_model, value: formData.value.cheap_model }]
      }
    }
  } catch (e) {
    console.error('Failed to load LLM config', e)
  }
}

const handleVerify = async (role: 'default' | 'cheap') => {
  const p = role === 'default' ? formData.value.default_model_provider : formData.value.cheap_model_provider
  const key = role === 'default' ? formData.value.default_model_api_key : formData.value.cheap_model_api_key
  const base = role === 'default' ? formData.value.default_model_base_url : formData.value.cheap_model_base_url
  
  if (!key || key.includes('***')) {
    message.warning('请先输入完整且有效的 API Key')
    return
  }

  if (role === 'default') verifyingDefault.value = true
  else verifyingCheap.value = true

  try {
    const res = await verifyAndFetchModels(p, key, base)
    if (res && res.data && res.data.models) {
      const opts = res.data.models.map((m: string) => ({ label: m, value: m }))
      if (role === 'default') {
        defaultModelOptions.value = opts
      } else {
        cheapModelOptions.value = opts
      }
      message.success(`成功获取 ${res.data.models.length} 个模型`)
    }
  } catch (e: any) {
    message.error(e.response?.data?.detail || '连接失败，请检查端点和秘钥')
  } finally {
    if (role === 'default') verifyingDefault.value = false
    else verifyingCheap.value = false
  }
}

const handleSave = async () => {
  saving.value = true
  try {
    await saveLLMConfig(formData.value)
    message.success('配置保存成功，系统已切换路由通道')
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
.text-xs { font-size: 12px; }
</style>