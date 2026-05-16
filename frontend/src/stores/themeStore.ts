import { defineStore } from 'pinia'
import { ref, computed, watch } from 'vue'

export type ThemeMode = 'light' | 'dark' | 'anchor' | 'auto'

const STORAGE_KEY = 'plotpilot-theme-mode'

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

  // 独立追踪 OS 偏好，使 auto 模式下 isDark 能响应系统变化
  const systemDark = ref(getSystemDark())

  const isDark = computed(() => {
    if (mode.value === 'auto') return systemDark.value
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

  // 监听系统主题变化，更新响应式 systemDark 使 auto 模式即时生效
  if (typeof window !== 'undefined' && window.matchMedia) {
    window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', (e) => {
      systemDark.value = e.matches
    })
  }

  function applyThemeToDOM() {
    const root = document.documentElement
    if (isDark.value) {
      root.classList.add('dark')
      root.setAttribute('data-theme', isAnchor.value ? 'anchor' : 'dark')
    } else {
      root.classList.remove('dark')
      root.setAttribute('data-theme', 'light')
    }
  }

  // 监听 isDark + mode，覆盖所有变化路径：
  // - 手动切换 mode（light/dark/anchor/auto）
  // - auto 模式下 OS 偏好变化（systemDark 改变 → isDark 改变）
  watch([isDark, mode], applyThemeToDOM, { immediate: true })

  return { mode, isDark, isAnchor, effectiveTheme, setTheme }
})
