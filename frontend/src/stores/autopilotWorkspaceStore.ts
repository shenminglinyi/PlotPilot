import { defineStore } from 'pinia'
import { ref } from 'vue'

/** 托管撰稿主工作区顶栏分页 */
export type AutopilotWorkspaceTab = 'cockpit' | 'dashboard' | 'operations'

/** 「监控 + DAG」页内子视图 */
export type AutopilotOperationsSubview = 'monitor' | 'dag'

export const AUTOPILOT_WORKSPACE_TABS: ReadonlyArray<{
  id: AutopilotWorkspaceTab
  label: string
  short: string
  description: string
}> = [
  {
    id: 'cockpit',
    label: '全托管驾驶',
    short: '驾驶舱',
    description: '启动、暂停与写作进度',
  },
  {
    id: 'dashboard',
    label: '仪表盘',
    short: '仪表盘',
    description: '张力曲线与质量指标',
  },
  {
    id: 'operations',
    label: '监控 · DAG',
    short: '工作流',
    description: '实时日志与 DAG 画布',
  },
] as const

export const useAutopilotWorkspaceStore = defineStore('autopilotWorkspace', () => {
  const activeTab = ref<AutopilotWorkspaceTab>('cockpit')
  const operationsSubview = ref<AutopilotOperationsSubview>('monitor')

  function setTab(tab: AutopilotWorkspaceTab) {
    activeTab.value = tab
  }

  function setOperationsSubview(view: AutopilotOperationsSubview) {
    operationsSubview.value = view
    if (view === 'dag') {
      activeTab.value = 'operations'
    }
  }

  function openDag() {
    setTab('operations')
    operationsSubview.value = 'dag'
  }

  function openMonitor() {
    setTab('operations')
    operationsSubview.value = 'monitor'
  }

  return {
    activeTab,
    operationsSubview,
    setTab,
    setOperationsSubview,
    openDag,
    openMonitor,
  }
})
