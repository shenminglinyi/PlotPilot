<template>
  <n-grid :cols="2" :x-gap="16" :y-gap="12">
    <n-gi>
      <n-form-item label="Provider">
        <n-select
          :value="provider"
          :options="providerOptions"
          placeholder="选择提供商"
          @update:value="emit('update:provider', $event)"
        />
      </n-form-item>
    </n-gi>
    <n-gi>
      <n-form-item label="API Key">
        <n-input
          :value="apiKey"
          type="password"
          show-password-on="click"
          placeholder="密钥"
          @update:value="emit('update:apiKey', $event)"
        />
      </n-form-item>
    </n-gi>
    <n-gi :span="2">
      <n-form-item label="Base URL">
        <n-input
          :value="baseUrl"
          :placeholder="baseUrlPlaceholder"
          @update:value="emit('update:baseUrl', $event)"
        />
      </n-form-item>
    </n-gi>
    <n-gi>
      <n-form-item label="模型名">
        <n-input
          :value="model"
          :placeholder="modelPlaceholder"
          @update:value="emit('update:model', $event)"
        />
      </n-form-item>
    </n-gi>
  </n-grid>
</template>

<script setup lang="ts">
defineProps<{
  provider: string
  apiKey: string
  baseUrl: string
  model: string
  baseUrlPlaceholder?: string
  modelPlaceholder?: string
}>()

const emit = defineEmits<{
  'update:provider': [string]
  'update:apiKey': [string]
  'update:baseUrl': [string]
  'update:model': [string]
}>()

const providerOptions = [
  { label: 'OpenAI 兼容', value: 'openai' },
  { label: 'Anthropic / Claude', value: 'anthropic' },
  { label: 'Gemini', value: 'gemini' },
]
</script>
