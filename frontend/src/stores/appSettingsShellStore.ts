import { defineStore } from 'pinia'
import { ref } from 'vue'
import {
  DEFAULT_SETTINGS_SECTION_ID,
  isRegisteredSettingsSectionId,
} from '@/settings/registry'

/**
 * 全局「应用设置」壳层：任意页面可按分区 ID 打开同一弹窗
 */
export const useAppSettingsShellStore = defineStore('appSettingsShell', () => {
  const visible = ref(false)
  const activeSectionId = ref<string>(DEFAULT_SETTINGS_SECTION_ID)

  function open(sectionId: string = DEFAULT_SETTINGS_SECTION_ID) {
    activeSectionId.value = isRegisteredSettingsSectionId(sectionId)
      ? sectionId
      : DEFAULT_SETTINGS_SECTION_ID
    visible.value = true
  }

  function close() {
    visible.value = false
  }

  return {
    visible,
    activeSectionId,
    open,
    close,
  }
})
