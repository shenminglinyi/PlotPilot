import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import {
  aiInvocationApi,
  type InvocationPromptDraftPreviewDTO,
  type AdoptionCommitDTO,
  type AdoptionDecisionDTO,
  type InvocationAttemptDTO,
  type InvocationResponseDTO,
  type InvocationSessionDTO,
  type InvocationVariableSnapshotGroup,
} from '../api/aiInvocation'

function errorText(err: unknown): string {
  if (err instanceof Error && err.message.trim()) return err.message
  if (typeof err === 'string' && err.trim()) return err
  return '操作失败，请稍后重试'
}

export const useAIInvocationStore = defineStore('aiInvocation', () => {
  const sessionListeners = new Map<string, Array<(payload: InvocationResponseDTO) => void>>()
  const sessionPollTimer = new Map<string, ReturnType<typeof setInterval>>()
  const visible = ref(false)
  const loading = ref(false)
  const actionLoading = ref(false)
  const error = ref('')
  const session = ref<InvocationSessionDTO | null>(null)
  const attempt = ref<InvocationAttemptDTO | null>(null)
  const decision = ref<AdoptionDecisionDTO | null>(null)
  const commit = ref<AdoptionCommitDTO | null>(null)
  const nextAction = ref('')
  const promptDraftSystem = ref('')
  const promptDraftUser = ref('')
  const promptDraftSavedSystem = ref('')
  const promptDraftSavedUser = ref('')
  const promptDraftPreview = ref<InvocationPromptDraftPreviewDTO | null>(null)
  const promptDraftLoading = ref(false)
  const liveAttemptContent = ref('')
  const liveAttemptLoading = ref(false)

  const hasAttempt = computed(() => Boolean(attempt.value?.id))
  const canAccept = computed(() => Boolean(
    session.value?.id
    && session.value.status === 'awaiting_acceptance'
    && attempt.value?.id
    && attempt.value.status === 'succeeded'
    && !decision.value?.id,
  ))
  const canCommit = computed(() => Boolean(session.value?.id && decision.value?.id && !commit.value?.id))
  const canRetry = computed(() => Boolean(
    session.value?.id
    && attempt.value?.id
    && ['awaiting_pre_call_review', 'awaiting_acceptance', 'awaiting_commit', 'cancelled', 'failed'].includes(String(session.value.status || '')),
  ))
  const isGenerating = computed(() => session.value?.status === 'generating')
  const liveAttemptDisplay = computed(() => liveAttemptContent.value || attempt.value?.content || '')
  const title = computed(() => {
    if (!session.value) return 'AI 生成审阅'
    return `${session.value.operation} / ${session.value.node_key}`
  })
  const draftSystemTemplate = computed(
    () => session.value?.prompt_snapshot?.template_prompt?.system || '',
  )
  const draftSystemEdited = computed(
    () => promptDraftSystem.value || promptDraftSavedSystem.value || draftSystemTemplate.value,
  )
  const draftUserTemplate = computed(
    () => session.value?.prompt_snapshot?.template_prompt?.user || '',
  )
  const draftUserEdited = computed(
    () => promptDraftUser.value || promptDraftSavedUser.value || draftUserTemplate.value,
  )
  const draftRuntimeSystem = computed(
    () => promptDraftPreview.value?.prompt_snapshot?.prompt?.system
      || session.value?.prompt_snapshot?.prompt?.system
      || '',
  )
  const draftRuntimeUser = computed(
    () => promptDraftPreview.value?.prompt_snapshot?.prompt?.user
      || session.value?.prompt_snapshot?.prompt?.user
      || '',
  )
  const draftDiagnostics = computed(
    () => promptDraftPreview.value?.prompt_snapshot?.diagnostics
      || session.value?.prompt_snapshot?.diagnostics
      || [],
  )
  const draftMissingVariables = computed(
    () => promptDraftPreview.value?.prompt_snapshot?.missing_variables
      || session.value?.prompt_snapshot?.missing_variables
      || [],
  )
  const variableSnapshotGroups = computed(() => {
    const plan = promptDraftPreview.value?.variable_plan || session.value?.variable_plan
    return plan?.snapshot_groups ?? []
  })

  function applyResponse(payload: InvocationResponseDTO) {
    session.value = payload.session
    attempt.value = payload.attempt ?? attempt.value ?? null
    decision.value = payload.decision ?? decision.value ?? null
    commit.value = payload.commit ?? commit.value ?? null
    nextAction.value = payload.next_action ?? ''
    promptDraftSavedSystem.value = payload.session?.prompt_snapshot?.draft_prompt?.system
      ?? payload.session?.prompt_snapshot?.template_prompt?.system
      ?? ''
    promptDraftSavedUser.value = payload.session?.prompt_snapshot?.draft_prompt?.user
      ?? payload.session?.prompt_snapshot?.template_prompt?.user
      ?? ''
    promptDraftSystem.value = promptDraftSavedSystem.value
    promptDraftUser.value = promptDraftSavedUser.value
    promptDraftPreview.value = null
    if (payload.attempt?.content != null) {
      liveAttemptContent.value = payload.attempt.content
    }
    syncGenerationPolling()
    const listeners = payload.session?.id ? sessionListeners.get(payload.session.id) : undefined
    if (listeners?.length) {
      for (const listener of [...listeners]) {
        listener(payload)
      }
    }
  }

  function openFromResponse(payload: InvocationResponseDTO) {
    applyResponse(payload)
    visible.value = true
  }

  async function open(sessionId: string) {
    visible.value = true
    loading.value = true
    error.value = ''
    session.value = null
    attempt.value = null
    decision.value = null
    commit.value = null
    nextAction.value = ''
    promptDraftSystem.value = ''
    promptDraftUser.value = ''
    promptDraftSavedSystem.value = ''
    promptDraftSavedUser.value = ''
    promptDraftPreview.value = null
    liveAttemptContent.value = ''
    stopGenerationPolling()
    try {
      const payload = await aiInvocationApi.get(sessionId)
      promptDraftSavedSystem.value = payload.session?.prompt_snapshot?.draft_prompt?.system
        ?? payload.session?.prompt_snapshot?.template_prompt?.system
        ?? ''
      promptDraftSavedUser.value = payload.session?.prompt_snapshot?.draft_prompt?.user
        ?? payload.session?.prompt_snapshot?.template_prompt?.user
        ?? ''
      promptDraftSystem.value = promptDraftSavedSystem.value
      promptDraftUser.value = promptDraftSavedUser.value
      openFromResponse(payload)
    } catch (err) {
      error.value = errorText(err)
      throw err
    } finally {
      loading.value = false
    }
  }

  async function accept() {
    if (!session.value?.id || !attempt.value?.id) return
    actionLoading.value = true
    error.value = ''
    try {
      const payload = await aiInvocationApi.accept(session.value.id, {
        attempt_id: attempt.value.id,
        accepted_by: 'user',
      })
      applyResponse(payload)
    } catch (err) {
      error.value = errorText(err)
      throw err
    } finally {
      actionLoading.value = false
    }
  }

  async function reject() {
    if (!session.value?.id || !attempt.value?.id) return
    actionLoading.value = true
    error.value = ''
    try {
      const payload = await aiInvocationApi.reject(session.value.id, {
        attempt_id: attempt.value.id,
        accepted_by: 'user',
      })
      applyResponse(payload)
    } catch (err) {
      error.value = errorText(err)
      throw err
    } finally {
      actionLoading.value = false
    }
  }

  async function retry() {
    if (!session.value?.id) return
    actionLoading.value = true
    error.value = ''
    try {
      const payload = await aiInvocationApi.retry(session.value.id, {
        resumed_by: 'user',
      })
      applyResponse(payload)
      decision.value = null
      commit.value = null
      visible.value = true
      syncGenerationPolling()
    } catch (err) {
      error.value = errorText(err)
      throw err
    } finally {
      actionLoading.value = false
    }
  }

  async function resume() {
    if (!session.value?.id) return
    actionLoading.value = true
    error.value = ''
    try {
      const payload = await aiInvocationApi.resume(session.value.id, {
        resumed_by: 'user',
      })
      applyResponse(payload)
      visible.value = true
      syncGenerationPolling()
    } catch (err) {
      error.value = errorText(err)
      throw err
    } finally {
      actionLoading.value = false
    }
  }

  async function previewPromptDraft(systemTemplate: string, userTemplate?: string | null) {
    if (!session.value?.id) return
    promptDraftLoading.value = true
    try {
      const payload = await aiInvocationApi.previewPromptDraft(session.value.id, {
        system_template: systemTemplate,
        user_template: userTemplate,
      })
      promptDraftPreview.value = payload
    } finally {
      promptDraftLoading.value = false
    }
  }

  async function savePromptDraft(systemTemplate: string, userTemplate?: string | null) {
    if (!session.value?.id) return
    promptDraftLoading.value = true
    try {
      const payload = await aiInvocationApi.savePromptDraft(session.value.id, {
        system_template: systemTemplate,
        user_template: userTemplate,
      })
      promptDraftSavedSystem.value = systemTemplate
      promptDraftSavedUser.value = userTemplate ?? ''
      promptDraftPreview.value = null
      applyResponse(payload)
    } finally {
      promptDraftLoading.value = false
    }
  }

  async function updateVariables(values: Record<string, unknown>) {
    if (!session.value?.id) return
    actionLoading.value = true
    error.value = ''
    try {
      const payload = await aiInvocationApi.updateVariables(session.value.id, {
        values,
        updated_by: 'user',
      })
      applyResponse(payload)
    } catch (err) {
      error.value = errorText(err)
      throw err
    } finally {
      actionLoading.value = false
    }
  }

  async function runCommit() {
    if (!session.value?.id || !decision.value?.id) return
    actionLoading.value = true
    error.value = ''
    try {
      const payload = await aiInvocationApi.commit(session.value.id, decision.value.id)
      applyResponse(payload)
    } catch (err) {
      error.value = errorText(err)
      throw err
    } finally {
      actionLoading.value = false
    }
  }

  function close() {
    visible.value = false
    stopGenerationPolling()
  }

  function stopGenerationPolling(sessionId?: string) {
    if (sessionId) {
      const timer = sessionPollTimer.get(sessionId)
      if (timer) {
        clearInterval(timer)
        sessionPollTimer.delete(sessionId)
      }
    } else {
      for (const timer of sessionPollTimer.values()) {
        clearInterval(timer)
      }
      sessionPollTimer.clear()
    }
    liveAttemptLoading.value = false
  }

  async function refreshSession() {
    if (!session.value?.id) return
    const payload = await aiInvocationApi.get(session.value.id, { silentGlobalFeedback: true })
    applyResponse(payload)
  }

  function syncGenerationPolling() {
    const sessionId = session.value?.id
    if (!sessionId) return
    if (session.value?.status === 'generating') {
      if (sessionPollTimer.has(sessionId)) return
      liveAttemptLoading.value = true
      const timer = window.setInterval(() => {
        void refreshSession().catch(() => {})
      }, 1200)
      sessionPollTimer.set(sessionId, timer)
      return
    }
    stopGenerationPolling()
  }

  function onSessionUpdate(sessionId: string, listener: (payload: InvocationResponseDTO) => void) {
    const listeners = sessionListeners.get(sessionId) ?? []
    listeners.push(listener)
    sessionListeners.set(sessionId, listeners)
    return () => {
      const current = sessionListeners.get(sessionId)
      if (!current) return
      sessionListeners.set(
        sessionId,
        current.filter((item) => item !== listener),
      )
    }
  }

  return {
    visible,
    loading,
    actionLoading,
    error,
    session,
    attempt,
    decision,
    commit,
    nextAction,
    promptDraftSystem,
    promptDraftUser,
    promptDraftSavedSystem,
    promptDraftSavedUser,
    promptDraftPreview,
    promptDraftLoading,
    liveAttemptContent,
    liveAttemptDisplay,
    liveAttemptLoading,
    draftSystemTemplate,
    draftSystemEdited,
    draftUserTemplate,
    draftUserEdited,
    draftRuntimeSystem,
    draftRuntimeUser,
    draftDiagnostics,
    draftMissingVariables,
    variableSnapshotGroups,
    hasAttempt,
    canAccept,
    canCommit,
    canRetry,
    isGenerating,
    title,
    open,
    openFromResponse,
    accept,
    reject,
    retry,
    resume,
    previewPromptDraft,
    savePromptDraft,
    updateVariables,
    runCommit,
    close,
    stopGenerationPolling,
    onSessionUpdate,
  }
})
