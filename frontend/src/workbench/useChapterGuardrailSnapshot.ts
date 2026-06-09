import { ref, watch, type Ref } from 'vue'
import { chapterApi } from '@/api/chapter'
import type { GuardrailCheckResponse } from '@/api/engineCore'
import { runtimePerformance } from '@/config/performance'

export interface LoadGuardrailSnapshotOptions {
  force?: boolean
  clear?: boolean
}

export interface UseChapterGuardrailSnapshotOptions {
  slug: Ref<string>
  chapterNumber: Ref<number | null | undefined>
  refreshKey?: Ref<unknown>
}

export function useChapterGuardrailSnapshot(options: UseChapterGuardrailSnapshotOptions) {
  const snapshot = ref<GuardrailCheckResponse | null>(null)
  const backoffUntil = ref(0)
  const backoffKey = ref('')

  function resetBackoff() {
    backoffUntil.value = 0
    backoffKey.value = ''
  }

  function clear() {
    snapshot.value = null
    resetBackoff()
  }

  function currentBackoffKey(): string | null {
    const slug = options.slug.value
    const chapterNumber = options.chapterNumber.value
    if (!slug || !chapterNumber) return null
    return `${slug}:${chapterNumber}`
  }

  async function load(loadOptions: LoadGuardrailSnapshotOptions = {}) {
    const key = currentBackoffKey()
    if (!key) {
      clear()
      return
    }
    if (loadOptions.clear) {
      clear()
    }
    if (
      !loadOptions.force &&
      backoffKey.value === key &&
      Date.now() < backoffUntil.value
    ) {
      return
    }

    try {
      const data = await chapterApi.getGuardrailSnapshot(
        options.slug.value,
        Number(options.chapterNumber.value),
      )
      snapshot.value = data
      if (data == null) {
        backoffKey.value = key
        backoffUntil.value = Date.now() + runtimePerformance.workbench.guardrailEmptyBackoffMs
      } else {
        resetBackoff()
      }
    } catch {
      backoffKey.value = key
      backoffUntil.value = Date.now() + runtimePerformance.workbench.guardrailErrorBackoffMs
    }
  }

  watch(
    () => [options.slug.value, options.chapterNumber.value] as const,
    () => {
      void load({ force: true, clear: true })
    },
    { immediate: true },
  )

  if (options.refreshKey) {
    watch(
      () => options.refreshKey?.value,
      () => {
        void load()
      },
    )
  }

  return {
    snapshot,
    load,
    clear,
    resetBackoff,
  }
}
