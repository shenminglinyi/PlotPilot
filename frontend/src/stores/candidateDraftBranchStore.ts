import { defineStore } from 'pinia'
import { ref } from 'vue'

const STORAGE_KEY = 'plotpilot-candidate-draft-branches'

type BranchMap = Record<string, string>

function loadStoredBranches(): BranchMap {
  if (typeof window === 'undefined') return {}
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return {}
    const parsed = JSON.parse(raw)
    if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
      return parsed as BranchMap
    }
  } catch {
    /* ignore */
  }
  return {}
}

function persistBranches(branches: BranchMap) {
  if (typeof window === 'undefined') return
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(branches))
  } catch {
    /* ignore */
  }
}

export const useCandidateDraftBranchStore = defineStore('candidateDraftBranch', () => {
  const branches = ref<BranchMap>(loadStoredBranches())

  function getActiveBranch(novelId: string): string {
    return Object.prototype.hasOwnProperty.call(branches.value, novelId)
      ? branches.value[novelId]
      : 'main'
  }

  function setActiveBranch(novelId: string, branchName: string) {
    branches.value = {
      ...branches.value,
      [novelId]: branchName,
    }
    persistBranches(branches.value)
  }

  return {
    branches,
    getActiveBranch,
    setActiveBranch,
  }
})
