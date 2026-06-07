<template>
  <div class="style-preset-selector">
    <div class="preset-grid">
      <div
        v-for="preset in presets"
        :key="preset.value"
        class="preset-card"
        :class="{ 'preset-card--selected': selectedValue === preset.value }"
        @click="selectPreset(preset.value)"
      >
        <div class="preset-card-header">
          <div class="preset-icon">{{ preset.icon }}</div>
          <div class="preset-check" v-if="selectedValue === preset.value">
            <n-icon size="16"><CheckmarkCircle /></n-icon>
          </div>
        </div>
        <div class="preset-card-body">
          <div class="preset-label">{{ preset.label }}</div>
          <div class="preset-preview">{{ getPresetPreview(preset.body) }}</div>
        </div>
      </div>
    </div>

    <div v-if="selectedPreset" class="preset-detail">
      <div class="preset-detail-header">
        <span class="preset-detail-label">完整文风公约</span>
        <n-tag size="small" :bordered="false" type="info">{{ selectedPreset.label }}</n-tag>
      </div>
      <div class="preset-detail-body">
        {{ selectedPreset.body }}
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { CheckmarkCircle } from '@vicons/ionicons5'
import { MARKET_STYLE_PRESETS } from '@/constants/marketStylePresets'

const props = defineProps<{
  modelValue: string
}>()

const emit = defineEmits<{
  'update:modelValue': [value: string]
}>()

const presets = MARKET_STYLE_PRESETS

const selectedValue = computed(() => props.modelValue)

const selectedPreset = computed(() => {
  return presets.find(p => p.value === selectedValue.value)
})

const selectPreset = (value: string) => {
  emit('update:modelValue', value)
}

const getPresetPreview = (body: string): string => {
  // Extract first sentence or first 40 characters
  const match = body.match(/【文风公约·[^】]+】(.+?)([。；]|$)/)
  if (match && match[1]) {
    return match[1].trim().slice(0, 50) + (match[1].length > 50 ? '…' : '')
  }
  return body.slice(0, 50) + '…'
}
</script>

<style scoped>
.style-preset-selector {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.preset-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
  gap: 10px;
}

.preset-card {
  position: relative;
  padding: 12px;
  border-radius: var(--app-radius-md, 10px);
  border: 2px solid var(--app-border);
  background: var(--app-surface);
  cursor: pointer;
  transition: all 0.2s ease;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.preset-card:hover {
  border-color: var(--color-brand, #2563eb);
  background: var(--color-brand-light, rgba(37, 99, 235, 0.04));
  transform: translateY(-1px);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
}

.preset-card--selected {
  border-color: var(--color-brand, #2563eb);
  background: var(--color-brand-light, rgba(37, 99, 235, 0.08));
  box-shadow: 0 0 0 1px var(--color-brand, #2563eb);
}

.preset-card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.preset-icon {
  font-size: 24px;
  line-height: 1;
}

.preset-check {
  color: var(--color-brand, #2563eb);
  line-height: 1;
}

.preset-card-body {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.preset-label {
  font-size: 13px;
  font-weight: 700;
  color: var(--app-text-primary);
  line-height: 1.3;
}

.preset-preview {
  font-size: 11px;
  color: var(--app-text-muted);
  line-height: 1.5;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.preset-detail {
  padding: 12px;
  border-radius: var(--app-radius-md, 10px);
  background: var(--app-surface);
  border: 1px solid var(--app-border);
}

.preset-detail-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 8px;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--app-border);
}

.preset-detail-label {
  font-size: 11px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.07em;
  color: var(--app-text-muted);
}

.preset-detail-body {
  font-size: 12px;
  line-height: 1.7;
  color: var(--app-text-secondary);
  white-space: pre-wrap;
  word-break: break-all;
}
</style>
