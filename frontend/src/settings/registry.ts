import type { Component } from 'vue'

/** 懒加载分区面板（便于 code-splitting） */
export type SettingsSectionLoader = () => Promise<{ default: Component }>

export interface AppSettingsSectionMeta {
  id: string
  label: string
  /** 显示在右侧面板顶部的短说明 */
  description?: string
  /** 越小越靠前 */
  order: number
  component: SettingsSectionLoader
}

const registry: AppSettingsSectionMeta[] = [
  {
    id: 'appearance',
    label: '外观与主题',
    description: '亮暗色、黑金模式与系统联动',
    order: 10,
    component: () => import('@/components/settings/sections/ThemeAppearanceSection.vue'),
  },
  {
    id: 'autopilot-writing',
    label: '写作与全托管',
    description: '指挥相位、字数硬帽、叙事标签（按书目保存）',
    order: 15,
    component: () => import('@/components/settings/sections/AutopilotWritingPrefsSection.vue'),
  },
  {
    id: 'engine',
    label: '核心引擎',
    description: '多角色模型端点；统一或独立 API 配置',
    order: 20,
    component: () => import('@/components/settings/sections/EngineMatrixSection.vue'),
  },
]

/**
 * 注册或覆盖设置分区（插件 / 后续功能包可调用此方法扩充界面）
 */
export function registerAppSettingsSection(meta: AppSettingsSectionMeta): void {
  const i = registry.findIndex((s) => s.id === meta.id)
  if (i >= 0) registry[i] = meta
  else registry.push(meta)
  registry.sort((a, b) => a.order - b.order)
}

export function getAppSettingsSections(): AppSettingsSectionMeta[] {
  return registry.slice().sort((a, b) => a.order - b.order)
}

export function isRegisteredSettingsSectionId(id: string): boolean {
  return registry.some((s) => s.id === id)
}

export const DEFAULT_SETTINGS_SECTION_ID = 'appearance' as const
