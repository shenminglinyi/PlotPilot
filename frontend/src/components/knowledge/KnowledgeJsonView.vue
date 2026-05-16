<template>
  <div class="kjv-root">
    <div class="kjv-toolbar">
      <n-space :size="8">
        <n-button size="small" type="primary" :loading="saving" @click="saveJson">保存 JSON</n-button>
        <n-button size="small" @click="formatJson">格式化</n-button>
      </n-space>
    </div>
    <n-input
      v-model:value="jsonText"
      type="textarea"
      :autosize="{ minRows: 10, maxRows: 20 }"
      placeholder="JSON 数组：与 GET /knowledge 返回的 facts 格式一致"
      class="kjv-editor"
      :status="jsonError ? 'error' : undefined"
    />
    <n-text v-if="jsonError" type="error" depth="3" style="font-size: 12px; margin-top: 8px; display: block; padding: 0 14px;">
      {{ jsonError }}
    </n-text>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { useMessage } from 'naive-ui'
import { knowledgeApi, type ChapterSummary } from '../../api/knowledge'

const props = defineProps<{ slug: string }>()
const emit = defineEmits<{ reload: [] }>()
const message = useMessage()

const saving = ref(false)
const jsonText = ref('')
const jsonError = ref('')
const storyVersion = ref(1)
const premiseLock = ref('')
const chaptersSnapshot = ref<ChapterSummary[]>([])

const reload = async () => {
  try {
    const data = await knowledgeApi.getKnowledge(props.slug)
    storyVersion.value = data.version ?? 1
    premiseLock.value = data.premise_lock ?? ''
    chaptersSnapshot.value = Array.isArray(data.chapters) ? [...data.chapters] : []
    jsonText.value = JSON.stringify(data.facts || [], null, 2)
    jsonError.value = ''
  } catch (e: any) {
    message.error(e?.response?.data?.detail || '加载失败')
  }
}

const formatJson = () => {
  try {
    const parsed = JSON.parse(jsonText.value)
    jsonText.value = JSON.stringify(parsed, null, 2)
    jsonError.value = ''
  } catch (e: any) {
    jsonError.value = `JSON 格式错误: ${e.message}`
  }
}

const saveJson = async () => {
  try {
    const parsed = JSON.parse(jsonText.value)
    if (!Array.isArray(parsed)) {
      jsonError.value = 'JSON 必须是数组格式'
      return
    }
    jsonError.value = ''

    saving.value = true
    await knowledgeApi.putKnowledge(props.slug, {
      version: storyVersion.value,
      premise_lock: premiseLock.value,
      chapters: chaptersSnapshot.value,
      facts: parsed,
    })
    message.success('已保存')
    emit('reload')
    await reload()
  } catch (e: any) {
    if (e.message) {
      jsonError.value = `JSON 格式错误: ${e.message}`
    } else {
      message.error(e?.response?.data?.detail || '保存失败')
    }
  } finally {
    saving.value = false
  }
}

const handleReloadEvent = () => {
  reload()
}

onMounted(() => {
  reload()
  window.addEventListener('plotpilot:knowledge:reload', handleReloadEvent)
})

onUnmounted(() => {
  window.removeEventListener('plotpilot:knowledge:reload', handleReloadEvent)
})
</script>

<style scoped>
.kjv-root {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.kjv-toolbar {
  padding: 10px 14px;
  border-bottom: 1px solid var(--app-divider);
  background: var(--app-surface-subtle);
  flex-shrink: 0;
}

.kjv-editor {
  flex: 1;
  min-height: 0;
  font-family: 'Consolas', 'Monaco', monospace;
  font-size: 13px;
  padding: 14px;
  overflow-y: auto;
}

.kjv-editor :deep(textarea) {
  font-family: 'Consolas', 'Monaco', monospace;
  font-size: 13px;
}
</style>
