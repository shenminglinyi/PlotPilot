/**
 * 节点编辑器状态管理 — Prompt 编辑 / 变量注入 / 预览
 */
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { dagApi } from '@/api/dag'

export const useNodeEditorStore = defineStore('nodeEditor', () => {
  // ─── 状态 ───
  const isOpen = ref(false)
  const nodeId = ref<string | null>(null)
  const novelId = ref<string | null>(null)

  // Prompt 模板
  const promptTemplate = ref('')
  const originalTemplate = ref('')

  // 变量
  const variables = ref<Record<string, string>>({})

  // 预览
  const renderedPrompt = ref('')
  const isPreviewLoading = ref(false)

  // 保存状态
  const isSaving = ref(false)
  const hasUnsavedChanges = computed(() => promptTemplate.value !== originalTemplate.value)

  // ─── Actions ───

  function open(nId: string, nNodeId: string, template: string, vars: Record<string, string>) {
    novelId.value = nId
    nodeId.value = nNodeId
    promptTemplate.value = template
    originalTemplate.value = template
    variables.value = { ...vars }
    isOpen.value = true
  }

  function close() {
    isOpen.value = false
    nodeId.value = null
    novelId.value = null
    promptTemplate.value = ''
    originalTemplate.value = ''
    variables.value = {}
    renderedPrompt.value = ''
  }

  async function loadPreview() {
    if (!novelId.value || !nodeId.value) return
    isPreviewLoading.value = true
    try {
      const result = await dagApi.getRenderedPrompt(novelId.value, nodeId.value)
      renderedPrompt.value = result.rendered
    } catch {
      renderedPrompt.value = '预览加载失败'
    } finally {
      isPreviewLoading.value = false
    }
  }

  function renderLocalPreview() {
    let rendered = promptTemplate.value
    for (const [key, value] of Object.entries(variables.value)) {
      rendered = rendered.replace(new RegExp(`\\{\\{${key}\\}\\}`, 'g'), value || `[${key}]`)
    }
    renderedPrompt.value = rendered
  }

  async function save() {
    if (!novelId.value || !nodeId.value) return
    isSaving.value = true
    try {
      await dagApi.updateNodeConfig(novelId.value, nodeId.value, {
        prompt_template: promptTemplate.value,
        prompt_variables: variables.value,
      })
      originalTemplate.value = promptTemplate.value
    } catch (e: unknown) {
      throw e
    } finally {
      isSaving.value = false
    }
  }

  function resetToDefault() {
    promptTemplate.value = originalTemplate.value
  }

  return {
    isOpen,
    nodeId,
    novelId,
    promptTemplate,
    originalTemplate,
    variables,
    renderedPrompt,
    isPreviewLoading,
    isSaving,
    hasUnsavedChanges,
    open,
    close,
    loadPreview,
    renderLocalPreview,
    save,
    resetToDefault,
  }
})
