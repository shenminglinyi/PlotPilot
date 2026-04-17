<script setup lang="ts">
import { computed } from 'vue'
import { NConfigProvider, NMessageProvider, NDialogProvider, zhCN, dateZhCN, darkTheme } from 'naive-ui'
import type { GlobalThemeOverrides } from 'naive-ui'
import { useThemeStore } from './stores/themeStore'

const themeStore = useThemeStore()

const naiveTheme = computed(() =>
  themeStore.isDark ? darkTheme : undefined
)

// ─── 静态调色板（不随主题变化，提升出来避免 computed 重建字符串）─────────────
const LIGHT_PALETTE = {
  primary:        '#4f46e5',
  primaryHover:   '#6366f1',
  primaryPressed: '#4338ca',
  primarySuppl:   '#818cf8',
  text1:          '#0f172a',
  text2:          '#475569',
  text3:          '#64748b',
  border:         'rgba(15, 23, 42, 0.09)',
  divider:        'rgba(15, 23, 42, 0.06)',
  surface:        '#ffffff',
  tableStriped:   '#f8fafc',
  tableHover:     '#f8fafc',
  inputBg:        '#ffffff',
  drawerBg:       '#eef1f6',
  selectBorder:   '#4f46e5',
} as const

const DARK_PALETTE = {
  primary:        '#818cf8',
  primaryHover:   '#a5b4fc',
  primaryPressed: '#6366f1',
  primarySuppl:   '#c7d2fe',
  text1:          '#e2e8f0',
  text2:          '#94a3b8',
  text3:          '#64748b',
  border:         'rgba(148, 163, 184, 0.12)',
  divider:        'rgba(148, 163, 184, 0.08)',
  surface:        '#1a2235',
  tableStriped:   '#161d2e',
  tableHover:     '#232d42',
  inputBg:        '#161d2e',
  drawerBg:       '#121826',
  selectBorder:   '#818cf8',
} as const

const ANCHOR_PALETTE = {
  primary:        '#c9a227',
  primaryHover:   '#ddb930',
  primaryPressed: '#a88a1f',
  primarySuppl:   '#e8c84a',
  text1:          '#f0ead6',
  text2:          '#c4b99a',
  text3:          '#8a8070',
  border:         'rgba(201, 162, 39, 0.14)',
  divider:        'rgba(201, 162, 39, 0.06)',
  surface:        '#111620',
  tableStriped:   '#0d1018',
  tableHover:     '#181f2e',
  inputBg:        '#0d1018',
  drawerBg:       '#0a0c10',
  selectBorder:   '#c9a227',
} as const

// 形状与间距等静态覆盖，与主题无关，freeze 后永不重建
const SHAPE_OVERRIDES: GlobalThemeOverrides = Object.freeze({
  common: {
    borderRadius:      '10px',
    borderRadiusSmall: '8px',
    fontSize:          '14px',
    fontSizeMedium:    '15px',
    lineHeight:        '1.55',
    heightMedium:      '38px',
  },
  Card:       { borderRadius: '14px', paddingMedium: '20px' },
  Button:     { borderRadiusMedium: '10px' },
  Input:      { borderRadius: '10px' },
  Scrollbar:  { width: '8px', height: '8px', borderRadius: '4px' },
  DataTable:  { borderRadius: '12px', thFontWeight: '600' },
  Tag:        { borderRadius: '6px' },
  Progress:   { railBorderRadius: '4px', fillBorderRadius: '4px' },
  Drawer:     { bodyPadding: '0' },
  Alert:      { border: 'none' },
})

// ─── 只有颜色部分是动态的，量少性能好 ─────────────────────────────────────
const themeOverrides = computed<GlobalThemeOverrides>(() => {
  const p = themeStore.isAnchor ? ANCHOR_PALETTE
          : themeStore.isDark   ? DARK_PALETTE
          :                       LIGHT_PALETTE

  return {
    ...SHAPE_OVERRIDES,
    common: {
      ...SHAPE_OVERRIDES.common,
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
    Drawer: { ...SHAPE_OVERRIDES.Drawer, color: p.drawerBg },
    Tabs: {
      tabTextColorActiveLine: p.primary,
      tabTextColorHoverLine:  p.text2,
      barColor:               p.primary,
    },
    Switch: { railColorActive: p.primary },
    Alert:  { ...SHAPE_OVERRIDES.Alert, color: p.surface },
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
