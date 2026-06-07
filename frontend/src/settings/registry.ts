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
    label: '外观 & 显示',
    description: '配色主题、界面字号与实时预览',
    order: 10,
    component: () => import('@/components/settings/sections/ThemeAppearanceSection.vue'),
  },
  {
    id: 'writing',
    label: '写作偏好',
    description: '每章目标字数、章节计数标签与落盘排版（按书目保存）',
    order: 20,
    component: () => import('@/components/settings/sections/WritingDisplaySection.vue'),
  },
  {
    id: 'autopilot-writing',
    label: '全托管控制',
    description: '审阅闸门与指挥器相位阈值（按书目保存）',
    order: 30,
    component: () => import('@/components/settings/sections/AutopilotWritingPrefsSection.vue'),
  },
  {
    id: 'engine',
    label: '模型引擎',
    description: '多角色端点配置；统一或独立 API Key',
    order: 40,
    component: () => import('@/components/settings/sections/EngineMatrixSection.vue'),
  },
  {
    id: 'about',
    label: '关于墨枢',
    description: '产品署名、团队信息与直播入口',
    order: 90,
    component: () => import('@/components/settings/sections/AboutBrandSection.vue'),
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
