import { defineStore } from 'pinia'
import { ref, computed, watch } from 'vue'

export type ThemeMode = 'light' | 'dark' | 'anchor' | 'auto'

const STORAGE_KEY = 'aitext-theme-mode'

function getStoredTheme(): ThemeMode {
  try {
    const stored = localStorage.getItem(STORAGE_KEY)
    if (stored === 'light' || stored === 'dark' || stored === 'anchor' || stored === 'auto') return stored
  } catch { /* ignore */ }
  return 'light'
}

function getSystemDark(): boolean {
  return window.matchMedia?.('(prefers-color-scheme: dark)').matches ?? false
}

export const useThemeStore = defineStore('theme', () => {
  const mode = ref<ThemeMode>(getStoredTheme())

  const isDark = computed(() => {
    if (mode.value === 'auto') return getSystemDark()
    return mode.value === 'dark' || mode.value === 'anchor'
  })

  /** 是否为黑金（主播限定色）模式 */
  const isAnchor = computed(() => mode.value === 'anchor')

  /** 实际生效的主题名，供 naive-ui / CSS 使用 */
  const effectiveTheme = computed<'light' | 'dark'>(() =>
    isDark.value ? 'dark' : 'light'
  )

  function setTheme(newMode: ThemeMode) {
    mode.value = newMode
    try {
      localStorage.setItem(STORAGE_KEY, newMode)
    } catch { /* ignore */ }
  }

  // 监听系统主题变化（仅 auto 模式下需要响应）
  if (typeof window !== 'undefined' && window.matchMedia) {
    window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => {
      // 触发 computed 重新计算即可，无需额外操作
    })
  }

  // 同步 <html> class 以支持全局 CSS 变量切换
  watch(isDark, (dark) => {
    const root = document.documentElement
    if (dark) {
      root.classList.add('dark')
      root.setAttribute('data-theme', isAnchor.value ? 'anchor' : 'dark')
    } else {
      root.classList.remove('dark')
      root.setAttribute('data-theme', 'light')
    }
  }, { immediate: true })

  return { mode, isDark, isAnchor, effectiveTheme, setTheme }
})
