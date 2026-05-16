import { defineStore } from 'pinia'
import { ref, watch } from 'vue'

export type FontSizePreset = 'small' | 'medium' | 'large' | 'xlarge'

const STORAGE_KEY = 'plotpilot-font-size-preset'

const PRESET_TO_SCALE: Record<FontSizePreset, number> = {
  small: 0.875,
  medium: 1,
  large: 1.125,
  xlarge: 1.25,
}

function getStoredPreset(): FontSizePreset {
  try {
    const stored = localStorage.getItem(STORAGE_KEY)
    if (stored === 'small' || stored === 'medium' || stored === 'large' || stored === 'xlarge') {
      return stored
    }
  } catch {
    /* ignore */
  }
  return 'medium'
}

function round1dp(n: number): number {
  return Math.round(n * 10) / 10
}

/** 将设计稿基准 px 按全局字体档位缩放，供 Naive themeOverrides 使用 */
export function scaledUiPx(basePx: number, preset: FontSizePreset): string {
  return `${round1dp(basePx * PRESET_TO_SCALE[preset])}px`
}

export const useFontSizeStore = defineStore('fontSize', () => {
  const preset = ref<FontSizePreset>(getStoredPreset())

  function setPreset(next: FontSizePreset) {
    preset.value = next
    try {
      localStorage.setItem(STORAGE_KEY, next)
    } catch {
      /* ignore */
    }
  }

  function applyFontScaleToDOM() {
    const scale = PRESET_TO_SCALE[preset.value]
    document.documentElement.style.setProperty('--app-font-scale', String(scale))
  }

  watch(preset, applyFontScaleToDOM, { immediate: true })

  return {
    preset,
    setPreset,
  }
})
