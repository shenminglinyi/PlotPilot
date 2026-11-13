<script setup lang="ts">
import { computed } from 'vue'
import { NConfigProvider, NMessageProvider, NDialogProvider, zhCN, dateZhCN, darkTheme } from 'naive-ui'
import AppSettingsModal from './components/settings/AppSettingsModal.vue'
import AppUpdateChecker from './components/global/AppUpdateChecker.vue'
import AIInvocationReviewPanel from './components/ai-invocation/AIInvocationReviewPanel.vue'
import { featureFlags } from './config/features'
import type { GlobalThemeOverrides } from 'naive-ui'
import { useThemeStore } from './stores/themeStore'
import { useFontSizeStore, scaledUiPx, type FontSizePreset } from './stores/fontSizeStore'
import { NAIVE_DENSITY_BASE } from './design/layoutDensity'

const themeStore = useThemeStore()
const fontSizeStore = useFontSizeStore()

const naiveTheme = computed(() =>
  themeStore.isDark ? darkTheme : undefined
)

// ─── 静态调色板（东方纸墨编辑室体系：宣纸深黛 / 纯黑夜读 / 古籍泥金）─────────────
const LIGHT_PALETTE = {
  primary:        '#181817',
  primaryHover:   '#2e2e2c',
  primaryPressed: '#0c0c0b',
  primarySuppl:   '#1f5e5b',
  text1:          '#161615',
  text2:          '#454440',
  text3:          '#66645e',
  border:         '#e5e2da',
  divider:        '#ece9e2',
  surface:        '#ffffff',
  tableStriped:   '#faf9f6',
  tableHover:     '#f6f5f1',
  inputBg:        '#ffffff',
  drawerBg:       '#f6f5f1',
  selectBorder:   '#1f5e5b',
} as const

const DARK_PALETTE = {
  primary:        '#f2f0eb',
  primaryHover:   '#ffffff',
  primaryPressed: '#d8d5ce',
  primarySuppl:   '#4fa39e',
  text1:          '#f2f0eb',
  text2:          '#b5b3ad',
  text3:          '#8e8c86',
  border:         '#262626',
  divider:        '#1f1f1f',
  surface:        '#141414',
  tableStriped:   '#191919',
  tableHover:     '#1e1e1e',
  inputBg:        '#141414',
  drawerBg:       '#0b0b0b',
  selectBorder:   '#4fa39e',
} as const

const ANCHOR_PALETTE = {
  primary:        '#c9a227',
  primaryHover:   '#ddb930',
  primaryPressed: '#a88a1f',
  primarySuppl:   '#e8c84a',
  text1:          '#f0ead6',
  text2:          '#c4b99a',
  text3:          '#968c7a',
  border:         'rgba(201, 162, 39, 0.16)',
  divider:        'rgba(201, 162, 39, 0.10)',
  surface:        '#131210',
  tableStriped:   '#171512',
  tableHover:     '#1c1a16',
  inputBg:        '#131210',
  drawerBg:       '#090908',
  selectBorder:   '#c9a227',
} as const

/** Naive UI 形体：随字体档位缩放，基准见 design/layoutDensity */
function naiveShapeOverrides(fz: FontSizePreset): GlobalThemeOverrides {
  const r = scaledUiPx(NAIVE_DENSITY_BASE.borderRadius, fz)
  const rs = scaledUiPx(NAIVE_DENSITY_BASE.borderRadiusSmall, fz)
  const cr = scaledUiPx(NAIVE_DENSITY_BASE.cardBorderRadius, fz)
  const sb = scaledUiPx(NAIVE_DENSITY_BASE.scrollbarWidth, fz)
  return {
    common: {
      fontFamily: 'var(--font-sans)',
      borderRadius: r,
      borderRadiusSmall: rs,
      fontSize: scaledUiPx(NAIVE_DENSITY_BASE.fontSize, fz),
      fontSizeMedium: scaledUiPx(NAIVE_DENSITY_BASE.fontSizeMedium, fz),
      lineHeight: NAIVE_DENSITY_BASE.lineHeight,
      heightMedium: scaledUiPx(NAIVE_DENSITY_BASE.heightMedium, fz),
    },
    Card: {
      borderRadius: cr,
      paddingMedium: scaledUiPx(NAIVE_DENSITY_BASE.cardPaddingMedium, fz),
    },
    Button: { borderRadiusMedium: r },
    Input: { borderRadius: r },
    Scrollbar: { width: sb, height: sb, borderRadius: scaledUiPx(3, fz) },
    DataTable: { borderRadius: r, thFontWeight: '600' },
    Tag: { borderRadius: scaledUiPx(5, fz) },
    Progress: {
      railBorderRadius: scaledUiPx(3, fz),
      fillBorderRadius: scaledUiPx(3, fz),
    },
    Drawer: { bodyPadding: '0' },
    Alert: { border: 'none' },
  }
}

// ─── 颜色 + 字号档位是动态的，量少性能好 ─────────────────────────────────────
const themeOverrides = computed<GlobalThemeOverrides>(() => {
  const p = themeStore.isAnchor ? ANCHOR_PALETTE
          : themeStore.isDark   ? DARK_PALETTE
          :                       LIGHT_PALETTE
  const fz = fontSizeStore.preset

  const shape = naiveShapeOverrides(fz)
  return {
    ...shape,
    common: {
      ...shape.common,
      primaryColor:        p.primary,
      primaryColorHover:   p.primaryHover,
      primaryColorPressed: p.primaryPressed,
      primaryColorSuppl:   p.primarySuppl,
      bodyColor:           p.text1,
      textColor1:          p.text1,
      textColor2:          p.text2,
      textColor3:          p.text3,
      borderColor:         p.border,
      dividerColor:        p.divider,
      cardColor:           p.surface,
      modalColor:          p.surface,
      popoverColor:        p.surface,
      tableColor:          p.surface,
      tableColorStriped:   p.tableStriped,
      tableColorHover:     p.tableHover,
      tableHeaderColor:    p.surface,
    },
    Select: {
      peers: {
        InternalSelection: {
          color:       p.inputBg,
          borderActive: p.selectBorder,
          borderFocus:  p.selectBorder,
        },
      },
    },
    Button: {
      ...shape.Button,
      textColorPrimary:        themeStore.isDark ? '#111111' : '#ffffff',
      textColorHoverPrimary:   themeStore.isDark ? '#111111' : '#ffffff',
      textColorPressedPrimary: themeStore.isDark ? '#111111' : '#ffffff',
      textColorFocusPrimary:   themeStore.isDark ? '#111111' : '#ffffff',
    },
    Drawer: { ...shape.Drawer, color: p.drawerBg },
    Tabs: {
      tabTextColorActiveLine: p.primary,
      tabTextColorHoverLine:  p.text2,
      barColor:               p.primary,
    },
    Switch: { railColorActive: p.primary },
    Alert:  { ...shape.Alert, color: p.surface },
    Form:   { labelTextColorTop: p.text2 },
  }
})
</script>

<template>
  <n-config-provider
    :locale="zhCN"
    :date-locale="dateZhCN"
    :theme="naiveTheme"
    :theme-overrides="themeOverrides"
  >
    <n-message-provider>
      <n-dialog-provider>
        <router-view v-slot="{ Component }">
          <transition name="app-fade" mode="out-in">
            <component :is="Component" />
          </transition>
        </router-view>
        <AIInvocationReviewPanel v-if="featureFlags.aiInvocationDebug" />
        <AppSettingsModal />
        <AppUpdateChecker />
      </n-dialog-provider>
    </n-message-provider>
  </n-config-provider>
</template>

<style>
.app-fade-enter-active,
.app-fade-leave-active {
  transition: opacity 0.2s ease, transform 0.2s ease;
}
.app-fade-enter-from {
  opacity: 0;
  transform: translateY(6px);
}
.app-fade-leave-to {
  opacity: 0;
  transform: translateY(-4px);
}
</style>
