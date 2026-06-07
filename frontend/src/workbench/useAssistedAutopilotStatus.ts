import { ref, watch, type Ref } from 'vue'
import { autopilotApi, isAutopilotNotFoundError, type AutopilotStatus } from '@/api/autopilot'
import { useAdaptivePolling } from '@/composables/useAdaptivePolling'
import { assistedAutopilotPollDelayMs } from '@/workbench/autopilotStatus'

export interface UseAssistedAutopilotStatusOptions {
  slug: Ref<string>
  enabled: Ref<boolean>
  onStatus: (status: AutopilotStatus) => void
}

export function useAssistedAutopilotStatus(options: UseAssistedAutopilotStatusOptions) {
  const stoppedForNotFound = ref(false)
  const failureCount = ref(0)

  function resetBackoff() {
    stoppedForNotFound.value = false
    failureCount.value = 0
  }

  async function loadStatus() {
    if (!options.slug.value || stoppedForNotFound.value) return
    try {
      const status = await autopilotApi.getStatus(options.slug.value)
      failureCount.value = 0
      options.onStatus(status)
    } catch (error) {
      if (isAutopilotNotFoundError(error)) {
        stoppedForNotFound.value = true
        failureCount.value = 0
        polling.stop()
        return
      }
      failureCount.value += 1
    }
  }

  const polling = useAdaptivePolling(
    loadStatus,
    () => assistedAutopilotPollDelayMs(failureCount.value),
    {
      pauseWhenHidden: true,
      shouldContinue: () => options.enabled.value && !stoppedForNotFound.value,
    },
  )

  function start() {
    if (!options.enabled.value) {
      polling.stop()
      return
    }
    polling.restart({ immediate: true })
  }

  function stop() {
    polling.stop()
  }

  watch(
    () => options.enabled.value,
    (enabled) => {
      if (!enabled) {
        stop()
        return
      }
      failureCount.value = 0
      start()
    },
    { immediate: true },
  )

  watch(
    () => options.slug.value,
    () => {
      resetBackoff()
      start()
    },
  )

  return {
    failureCount,
    isPolling: polling.isPolling,
    isExecuting: polling.isExecuting,
    stoppedForNotFound,
    resetBackoff,
    start,
    stop,
    refresh: polling.execute,
  }
}
