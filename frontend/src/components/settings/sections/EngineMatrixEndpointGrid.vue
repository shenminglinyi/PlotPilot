<template>
  <n-grid :cols="24" :x-gap="12" :y-gap="10" class="em-grid">
    <n-gi :span="24" :md="8">
      <label class="em-field">
        <span class="em-label">协议</span>
        <n-select
          :value="provider"
          :options="providerOptions"
          size="small"
          placeholder="选择提供商"
          @update:value="emit('update:provider', $event)"
        />
      </label>
    </n-gi>
    <n-gi :span="24" :md="16">
      <label class="em-field">
        <span class="em-label">API Key</span>
        <n-input
          :value="apiKey"
          type="password"
          show-password-on="click"
          size="small"
          placeholder="留空表示不修改已保存的密钥"
          @update:value="emit('update:apiKey', $event)"
        />
      </label>
    </n-gi>
    <n-gi :span="24">
      <label class="em-field">
        <span class="em-label">Base URL</span>
        <n-input
          :value="baseUrl"
          size="small"
          :placeholder="baseUrlPlaceholder"
          @update:value="emit('update:baseUrl', $event)"
        />
      </label>
    </n-gi>
    <n-gi :span="24" :md="14">
      <label class="em-field">
        <span class="em-label">模型 ID</span>
        <n-input
          :value="model"
          size="small"
          :placeholder="modelPlaceholder"
          @update:value="emit('update:model', $event)"
        />
      </label>
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

<style scoped>
.em-grid {
  width: 100%;
}

.em-field {
  display: grid;
  gap: 4px;
}

.em-label {
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.04em;
  color: var(--app-text-muted);
}
</style>
