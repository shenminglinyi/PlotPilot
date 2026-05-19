<template>
  <n-collapse class="adv-collapse mt-3" :default-expanded-names="[]">
    <n-collapse-item title="推理超参（高级）" name="inference">
      <n-grid :cols="2" :x-gap="16" :y-gap="12">
        <n-gi>
          <n-form-item label="温度 temperature" label-width="auto">
            <n-input-number
              class="w-full"
              :value="temperature"
              :min="0"
              :max="2"
              :step="0.05"
              @update:value="onTemperature"
            />
          </n-form-item>
        </n-gi>
        <n-gi>
          <n-form-item label="最大输出 token (max_tokens)" label-width="auto">
            <n-input-number
              class="w-full"
              :value="maxTokens"
              :min="1"
              :max="200000"
              :step="256"
              @update:value="onMaxTokens"
            />
          </n-form-item>
        </n-gi>
        <n-gi>
          <n-form-item label="请求超时 (秒)" label-width="auto">
            <n-input-number
              class="w-full"
              :value="timeoutSeconds"
              :min="30"
              :max="3600"
              :step="10"
              @update:value="onTimeout"
            />
          </n-form-item>
        </n-gi>
      </n-grid>
    </n-collapse-item>
  </n-collapse>
</template>

<script setup lang="ts">
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
  emit('update:maxTokens', Math.max(1, Math.floor(v ?? 4096)))
}

function onTimeout(v: number | null) {
  emit('update:timeoutSeconds', Math.max(30, Math.floor(v ?? props.timeoutSeconds)))
}
</script>

<style scoped>
.adv-collapse :deep(.n-collapse-item__content-inner) {
  padding-top: 4px;
}

.w-full {
  width: 100%;
}

.mt-3 {
  margin-top: 12px;
}
</style>
