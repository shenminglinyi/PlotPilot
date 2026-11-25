import { defineStore } from 'pinia'
import { ref, watch } from 'vue'
import { storageKeys } from '@/config/storageKeys'
import { readStorageString, writeStorageString } from '@/utils/storage'

export type FontSizePreset = 'small' | 'medium' | 'large' | 'xlarge'

/** 全局字号档位唯一数据源：设置页、CSS 根字号与 Naive UI 共用。 */
export const FONT_SIZE_SCALES: Readonly<Record<FontSizePreset, number>> = {
  small: 0.875,
  medium: 1,
  large: 1.125,
  xlarge: 1.25,
}

export const FONT_SIZE_PRESETS: ReadonlyArray<{
  value: FontSizePreset
  label: string
  hint: string
  previewRem: string
}> = [
  { value: 'small', label: '较小', hint: '87.5%', previewRem: '1.125rem' },
  { value: 'medium', label: '默认', hint: '100%', previewRem: '1.375rem' },
  { value: 'large', label: '较大', hint: '112.5%', previewRem: '1.625rem' },
  { value: 'xlarge', label: '特大', hint: '125%', previewRem: '1.875rem' },
]

function getStoredPreset(): FontSizePreset {
  const stored = readStorageString(storageKeys.fontSizePreset)
  if (stored === 'small' || stored === 'medium' || stored === 'large' || stored === 'xlarge') {
    return stored
  }
  return 'medium'
}

function round1dp(n: number): number {
  return Math.round(n * 10) / 10
}

/** 将设计稿基准 px 按全局字体档位缩放，供 Naive themeOverrides 使用 */
export function scaledUiPx(basePx: number, preset: FontSizePreset): string {
  return `${round1dp(basePx * FONT_SIZE_SCALES[preset])}px`
}

export const useFontSizeStore = defineStore('fontSize', () => {
  const preset = ref<FontSizePreset>(getStoredPreset())

  function setPreset(next: FontSizePreset) {
    preset.value = next
    writeStorageString(storageKeys.fontSizePreset, next)
  }

  function applyFontScaleToDOM() {
    const scale = FONT_SIZE_SCALES[preset.value]
    document.documentElement.style.setProperty('--app-font-scale', String(scale))
  }

  watch(preset, applyFontScaleToDOM, { immediate: true })

  return {
    preset,
    setPreset,
  }
})
