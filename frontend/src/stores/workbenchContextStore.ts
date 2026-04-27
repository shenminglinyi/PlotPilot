import { defineStore } from 'pinia'
import { ref } from 'vue'

export type WorkbenchTargetPanel = 'sandbox' | 'voice-lock' | null

export interface SandboxDraftContext {
  slug: string
  characterId: string
  scenePrompt: string
  mentalState?: string
  verbalTic?: string
  idleBehavior?: string
}

export const useWorkbenchContextStore = defineStore('workbenchContext', () => {
  const targetPanel = ref<WorkbenchTargetPanel>(null)
  const sandboxDraft = ref<SandboxDraftContext | null>(null)
  const sandboxDraftVersion = ref(0)

  function openSandboxWithDraft(payload: SandboxDraftContext) {
    targetPanel.value = 'sandbox'
    sandboxDraft.value = payload
    sandboxDraftVersion.value += 1
  }

  return {
    targetPanel,
    sandboxDraft,
    sandboxDraftVersion,
    openSandboxWithDraft,
  }
})
