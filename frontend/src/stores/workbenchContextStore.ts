import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { ChapterCandidateDraftDTO } from '@/api/chapter'

export type WorkbenchTargetPanel = 'sandbox' | 'voice-lock' | null

export interface VoiceLockDraftContext {
  slug: string
  characterId: string
}

export interface SandboxDraftContext {
  slug: string
  characterId: string
  scenePrompt: string
  mentalState?: string
  verbalTic?: string
  idleBehavior?: string
}

export interface CandidateRewriteSeedContext {
  slug: string
  chapterNumber: number
  source: string
  title?: string
  rationale: string
  content?: string
  metadata?: Record<string, unknown>
}

export interface CandidateRewriteExecutionContext {
  slug: string
  draft: ChapterCandidateDraftDTO
}

export const useWorkbenchContextStore = defineStore('workbenchContext', () => {
  const targetPanel = ref<WorkbenchTargetPanel>(null)
  const voiceLockDraft = ref<VoiceLockDraftContext | null>(null)
  const voiceLockDraftVersion = ref(0)
  const sandboxDraft = ref<SandboxDraftContext | null>(null)
  const sandboxDraftVersion = ref(0)
  const candidateRewriteSeed = ref<CandidateRewriteSeedContext | null>(null)
  const candidateRewriteSeedVersion = ref(0)
  const candidateRewriteExecution = ref<CandidateRewriteExecutionContext | null>(null)
  const candidateRewriteExecutionVersion = ref(0)

  function openVoiceLockForCharacter(payload: VoiceLockDraftContext) {
    targetPanel.value = 'voice-lock'
    voiceLockDraft.value = payload
    voiceLockDraftVersion.value += 1
  }

  function openSandboxWithDraft(payload: SandboxDraftContext) {
    targetPanel.value = 'sandbox'
    sandboxDraft.value = payload
    sandboxDraftVersion.value += 1
  }

  function openCandidateRewriteSeed(payload: CandidateRewriteSeedContext) {
    candidateRewriteSeed.value = payload
    candidateRewriteSeedVersion.value += 1
  }

  function openCandidateRewriteExecution(payload: CandidateRewriteExecutionContext) {
    candidateRewriteExecution.value = payload
    candidateRewriteExecutionVersion.value += 1
  }

  return {
    targetPanel,
    voiceLockDraft,
    voiceLockDraftVersion,
    sandboxDraft,
    sandboxDraftVersion,
    candidateRewriteSeed,
    candidateRewriteSeedVersion,
    candidateRewriteExecution,
    candidateRewriteExecutionVersion,
    openVoiceLockForCharacter,
    openSandboxWithDraft,
    openCandidateRewriteSeed,
    openCandidateRewriteExecution,
  }
})
