<template>
  <n-modal v-model:show="visible" preset="card" title="核心引擎配置 (Model Matrix)" style="width: 700px">
    <n-form :model="formData" label-placement="top">
      
      <div class="mode-switch mb-4">
        <n-switch v-model:value="isUnifiedMode" size="large">
          <template #checked>统一端点配置</template>
          <template #unchecked>独立端点配置</template>
        </n-switch>
        <n-text depth="3" class="text-xs ml-2">
          {{ isUnifiedMode ? '使用同一个 API Key 驱动两个模型' : '为两个模型分别配置不同的服务商和 Key' }}
        </n-text>
      </div>

      <!-- 统一端点配置区 -->
      <template v-if="isUnifiedMode">
        <n-card size="small" class="mb-4" title="🌐 全局服务端点">
          <n-form-item label="服务商 (Provider)">
            <n-radio-group v-model:value="formData.default_model_provider" @update:value="syncProviders">
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
            🔗 测试端点并获取模型
          </n-button>
        </n-card>

        <!-- 统一模式下的模型分配 -->
        <n-card size="small" class="mb-4" title="🎯 模型任务分配">
          <n-form-item label="✨ 创作主力模型 (Default Model)">
            <n-select v-model:value="formData.default_model" :options="defaultModelOptions" tag filterable />
            <template #feedback>用于正文连写与复杂逻辑推理，建议选择智商最高的模型</template>
          </n-form-item>

          <n-form-item label="⚡ 分析经济模型 (Cheap Model)">
            <n-select v-model:value="formData.cheap_model" :options="cheapModelOptions" tag filterable />
            <template #feedback>用于后台数据提取、打分与摘要，建议选择速度最快、最便宜的模型</template>
          </n-form-item>

          <n-form-item label="🧠 知识图谱模型 (Knowledge Model)">
            <n-select v-model:value="formData.knowledge_model" :options="knowledgeModelOptions" tag filterable />
            <template #feedback>专门用于从设定中提取复杂的知识图谱关系，建议选择逻辑推理能力较强的模型</template>
          </n-form-item>
        </n-card>
      </template>

      <!-- 独立端点配置区 (原逻辑) -->
      <template v-else>
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

        <!-- 知识图谱模型配置区 -->
        <n-card size="small" class="mb-4" title="🧠 知识图谱模型 (Knowledge Model)">
          <template #header-extra>
            <n-text depth="3" class="text-xs">专门用于复杂设定逻辑推理和关系提取</n-text>
          </template>

          <n-form-item label="服务商 (Provider)">
            <n-radio-group v-model:value="formData.knowledge_model_provider" @update:value="() => formData.knowledge_model = ''">
              <n-radio-button value="openai">OpenAI 兼容 API</n-radio-button>
              <n-radio-button value="anthropic">Anthropic (Claude)</n-radio-button>
            </n-radio-group>
          </n-form-item>

          <n-form-item label="API Key">
            <n-input v-model:value="formData.knowledge_model_api_key" type="password" show-password-on="click" placeholder="sk-..." />
          </n-form-item>

          <n-form-item label="Base URL (留空则使用官方地址)">
            <n-input v-model:value="formData.knowledge_model_base_url" placeholder="如 https://api.openai.com/v1" />
          </n-form-item>

          <n-button type="info" dashed block @click="handleVerify('knowledge')" :loading="verifyingKnowledge" class="mb-4">
            🔗 测试知识端点并获取模型
          </n-button>

          <n-form-item label="选择知识图谱模型">
            <n-select v-model:value="formData.knowledge_model" :options="knowledgeModelOptions" tag filterable />
          </n-form-item>
        </n-card>
      </template>

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
const verifyingKnowledge = ref(false)
const saving = ref(false)
const isUnifiedMode = ref(true)

const formData = ref<LLMConfig>({
  provider: 'openai',
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
  knowledge_model: ''
})

const defaultModelOptions = ref<{label: string, value: string}[]>([])
const cheapModelOptions = ref<{label: string, value: string}[]>([])
const knowledgeModelOptions = ref<{label: string, value: string}[]>([])

const syncProviders = () => {
  formData.value.default_model = ''
  formData.value.cheap_model = ''
  formData.value.knowledge_model = ''
}

const loadData = async () => {
  try {
    const res = await getLLMConfig()
    if (res) {
      // res is already the data object returned by axios interceptor
      formData.value = { ...formData.value, ...res }
      
      // 初始化下拉框展示
      if (formData.value.default_model) {
        defaultModelOptions.value = [{ label: formData.value.default_model, value: formData.value.default_model }]
      }
      if (formData.value.cheap_model) {
        cheapModelOptions.value = [{ label: formData.value.cheap_model, value: formData.value.cheap_model }]
      }
      if (formData.value.knowledge_model) {
        knowledgeModelOptions.value = [{ label: formData.value.knowledge_model, value: formData.value.knowledge_model }]
      }

      // 推断是否属于统一模式（三个配置的值完全一样）
      if (
        formData.value.default_model_provider === formData.value.cheap_model_provider &&
        formData.value.default_model_api_key === formData.value.cheap_model_api_key &&
        formData.value.default_model_base_url === formData.value.cheap_model_base_url &&
        formData.value.default_model_provider === formData.value.knowledge_model_provider &&
        formData.value.default_model_api_key === formData.value.knowledge_model_api_key &&
        formData.value.default_model_base_url === formData.value.knowledge_model_base_url
      ) {
        isUnifiedMode.value = true
      } else {
        isUnifiedMode.value = false
      }
    }
  } catch (e) {
    console.error('Failed to load LLM config', e)
  }
}

const handleVerify = async (role: 'default' | 'cheap' | 'knowledge') => {
  const p = formData.value.default_model_provider
  const key = formData.value.default_model_api_key
  const base = formData.value.default_model_base_url

  let p_target = p
  let key_target = key
  let base_target = base

  if (role === 'cheap') {
    p_target = formData.value.cheap_model_provider
    key_target = formData.value.cheap_model_api_key
    base_target = formData.value.cheap_model_base_url
  } else if (role === 'knowledge') {
    p_target = formData.value.knowledge_model_provider
    key_target = formData.value.knowledge_model_api_key
    base_target = formData.value.knowledge_model_base_url
  }

  const targetKey = key_target
  if (!targetKey || targetKey.includes('***')) {
    message.warning('请先输入完整且有效的 API Key')
    return
  }

  if (role === 'default') verifyingDefault.value = true
  else if (role === 'cheap') verifyingCheap.value = true
  else verifyingKnowledge.value = true

  try {
    const targetProvider = p_target
    const targetBase = base_target

    const res = await verifyAndFetchModels(targetProvider, targetKey, targetBase)
    // res is already the data object returned by axios interceptor
    if (res && res.models) {
      const opts = res.models.map((m: string) => ({ label: m, value: m }))

      if (isUnifiedMode.value) {
        // 统一模式下，一次请求更新三个下拉框
        defaultModelOptions.value = opts
        cheapModelOptions.value = opts
        knowledgeModelOptions.value = opts
      } else {
        if (role === 'default') defaultModelOptions.value = opts
        else if (role === 'cheap') cheapModelOptions.value = opts
        else knowledgeModelOptions.value = opts
      }

      message.success(`成功获取 ${res.models.length} 个模型`)
    }
  } catch (e: any) {
    message.error(e.response?.data?.detail || '连接失败，请检查端点和秘钥')
  } finally {
    if (role === 'default') verifyingDefault.value = false
    else if (role === 'cheap') verifyingCheap.value = false
    else verifyingKnowledge.value = false
  }
}

const handleSave = async () => {
  saving.value = true

  // 如果是统一模式，保存前把 default 的配置强行复制给 cheap 和 knowledge
  if (isUnifiedMode.value) {
    formData.value.cheap_model_provider = formData.value.default_model_provider
    formData.value.cheap_model_api_key = formData.value.default_model_api_key
    formData.value.cheap_model_base_url = formData.value.default_model_base_url
    
    formData.value.knowledge_model_provider = formData.value.default_model_provider
    formData.value.knowledge_model_api_key = formData.value.default_model_api_key
    formData.value.knowledge_model_base_url = formData.value.default_model_base_url
  }
  
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