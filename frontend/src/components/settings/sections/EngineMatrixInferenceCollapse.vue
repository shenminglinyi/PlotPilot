<template>
  <details class="em-infer">
    <summary class="em-infer-summary">推理超参（高级）</summary>
    <div class="em-infer-body">
      <label class="em-infer-field">
        <span>温度</span>
        <n-input-number
          class="em-infer-input"
          :value="temperature"
          :min="0"
          :max="2"
          :step="0.05"
          size="small"
          @update:value="onTemperature"
        />
      </label>
      <label class="em-infer-field">
        <span>最大 token</span>
        <n-input-number
          class="em-infer-input"
          :value="maxTokens"
          :min="1"
          :step="256"
          size="small"
          @update:value="onMaxTokens"
        />
      </label>
      <label class="em-infer-field">
        <span>超时（秒）</span>
        <n-input-number
          class="em-infer-input"
          :value="timeoutSeconds"
          :min="30"
          :max="3600"
          :step="10"
          size="small"
          @update:value="onTimeout"
        />
      </label>
    </div>
  </details>
</template>

<script setup lang="ts">
import { DEFAULT_MAX_OUTPUT_TOKENS } from '@/constants/llm'

const props = defineProps<{
  temperature: number
  maxTokens: number
  timeoutSeconds: number
}>()

const emit = defineEmits<{
  'update:temperature': [number]
  'update:maxTokens': [number]
  'update:timeoutSeconds': [number]
}>()

function onTemperature(v: number | null) {
  emit('update:temperature', v ?? 0.7)
}

function onMaxTokens(v: number | null) {
  emit('update:maxTokens', Math.max(1, Math.floor(v ?? DEFAULT_MAX_OUTPUT_TOKENS)))
}

function onTimeout(v: number | null) {
  emit('update:timeoutSeconds', Math.max(30, Math.floor(v ?? props.timeoutSeconds)))
}
</script>

<style scoped>
.em-infer {
  margin-top: 10px;
  border-radius: 8px;
  border: 1px solid var(--app-border);
  background: var(--app-surface-subtle);
  overflow: hidden;
}

.em-infer-summary {
  padding: 8px 12px;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.04em;
  color: var(--app-text-muted);
  cursor: pointer;
  list-style: none;
  user-select: none;
}

.em-infer-summary::-webkit-details-marker {
  display: none;
}

.em-infer[open] .em-infer-summary {
  border-bottom: 1px solid var(--app-border);
}

.em-infer-body {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
  padding: 10px 12px;
}

.em-infer-field {
  display: grid;
  gap: 4px;
}

.em-infer-field span {
  font-size: 10px;
  color: var(--app-text-muted);
}

.em-infer-input {
  width: 100%;
}

@media (max-width: 640px) {
  .em-infer-body {
    grid-template-columns: 1fr;
  }
}
</style>
