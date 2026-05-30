import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import {
  aiInvocationApi,
  type AdoptionCommitDTO,
  type AdoptionDecisionDTO,
  type InvocationAttemptDTO,
  type InvocationResponseDTO,
  type InvocationSessionDTO,
} from '../api/aiInvocation'

function errorText(err: unknown): string {
  if (err instanceof Error && err.message.trim()) return err.message
  if (typeof err === 'string' && err.trim()) return err
  return '操作失败，请稍后重试'
}

export const useAIInvocationStore = defineStore('aiInvocation', () => {
  const visible = ref(false)
  const loading = ref(false)
  const actionLoading = ref(false)
  const error = ref('')
  const session = ref<InvocationSessionDTO | null>(null)
  const attempt = ref<InvocationAttemptDTO | null>(null)
  const decision = ref<AdoptionDecisionDTO | null>(null)
  const commit = ref<AdoptionCommitDTO | null>(null)
  const nextAction = ref('')

  const hasAttempt = computed(() => Boolean(attempt.value?.id))
  const canAccept = computed(() => Boolean(session.value?.id && attempt.value?.id && !decision.value?.id))
  const canCommit = computed(() => Boolean(session.value?.id && decision.value?.id && !commit.value?.id))
  const title = computed(() => {
    if (!session.value) return 'AI 生成审阅'
    return `${session.value.operation} / ${session.value.node_key}`
  })

  function applyResponse(payload: InvocationResponseDTO) {
    session.value = payload.session
    attempt.value = payload.attempt ?? attempt.value ?? null
    decision.value = payload.decision ?? decision.value ?? null
    commit.value = payload.commit ?? commit.value ?? null
    nextAction.value = payload.next_action ?? ''
  }

  function openFromResponse(payload: InvocationResponseDTO) {
    applyResponse(payload)
    visible.value = true
  }

  async function open(sessionId: string) {
    loading.value = true
    error.value = ''
    try {
      const payload = await aiInvocationApi.get(sessionId)
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
    hasAttempt,
    canAccept,
    canCommit,
    title,
    open,
    openFromResponse,
    accept,
    reject,
    runCommit,
    close,
  }
})
