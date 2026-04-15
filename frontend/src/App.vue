<script setup lang="ts">
import { computed } from 'vue'
import { NConfigProvider, NMessageProvider, NDialogProvider, zhCN, dateZhCN, darkTheme } from 'naive-ui'
import type { GlobalThemeOverrides } from 'naive-ui'
import { useThemeStore } from './stores/themeStore'

const themeStore = useThemeStore()

const naiveTheme = computed(() =>
  themeStore.isDark ? darkTheme : undefined
)

const themeOverrides = computed<GlobalThemeOverrides>(() => {
  const isDark = themeStore.isDark
  const isAnchor = themeStore.isAnchor

  // 黑金模式专属色值
  const anchorPrimary = '#c9a227'
  const anchorPrimaryHover = '#ddb930'
  const anchorPrimaryPressed = '#a88a1f'
  const anchorText = '#f0ead6'
  const anchorText2 = '#c4b99a'
  const anchorText3 = '#8a8070'
  const anchorSurface = '#111620'
  const anchorBg = '#0a0c10'
  const anchorInput = '#0d1018'

  return {
    common: {
      primaryColor: isAnchor ? anchorPrimary : (isDark ? '#818cf8' : '#4f46e5'),
      primaryColorHover: isAnchor ? anchorPrimaryHover : (isDark ? '#a5b4fc' : '#6366f1'),
      primaryColorPressed: isAnchor ? anchorPrimaryPressed : (isDark ? '#6366f1' : '#4338ca'),
      primaryColorSuppl: isAnchor ? '#e8c84a' : (isDark ? '#c7d2fe' : '#818cf8'),
      borderRadius: '10px',
      borderRadiusSmall: '8px',
      fontSize: '14px',
      fontSizeMedium: '15px',
      lineHeight: '1.55',
      heightMedium: '38px',

      /* 文字 — 使用变量体系 */
      bodyColor: isAnchor ? anchorText : (isDark ? '#e2e8f0' : '#0f172a'),
      textColor1: isAnchor ? anchorText : (isDark ? '#e2e8f0' : '#0f172a'),
      textColor2: isAnchor ? anchorText2 : (isDark ? '#94a3b8' : '#475569'),
      textColor3: isAnchor ? anchorText3 : (isDark ? '#64748b' : '#64748b'),

      /* 边框 */
      borderColor: isAnchor ? 'rgba(201, 162, 39, 0.14)' : (isDark ? '#334155' : 'rgba(15, 23, 42, 0.09)'),
      dividerColor: isAnchor ? 'rgba(201, 162, 39, 0.06)' : (isDark ? '#1e293b' : 'rgba(15, 23, 42, 0.06)'),

      /* 背景（暗色禁止纯白）*/
      cardColor: isAnchor ? anchorSurface : (isDark ? '#131c31' : '#ffffff'),
      modalColor: isAnchor ? anchorSurface : (isDark ? '#131c31' : '#ffffff'),
      popoverColor: isAnchor ? anchorSurface : (isDark ? '#131c31' : '#ffffff'),
      tableColor: isAnchor ? anchorSurface : (isDark ? '#131c31' : '#ffffff'),
      tableColorStriped: isAnchor ? anchorInput : (isDark ? '#0f172a' : '#f8fafc'),
      tableColorHover: isAnchor ? '#181f2e' : (isDark ? '#1a2436' : '#f8fafc'),
      tableHeaderColor: isAnchor ? anchorSurface : (isDark ? '#131c31' : '#ffffff'),
    },
    Card: {
      borderRadius: '14px',
      paddingMedium: '20px',
    },
    Button: {
      borderRadiusMedium: '10px',
    },
    Input: {
      borderRadius: '10px',
    },
    Select: {
      peers: {
        InternalSelection: {
          color: isAnchor ? anchorInput : (isDark ? '#0f172a' : '#ffffff'),
          borderActive: isAnchor ? anchorPrimary : (isDark ? '#818cf8' : '#4f46e5'),
          borderFocus: isAnchor ? anchorPrimary : (isDark ? '#818cf8' : '#4f46e5'),
        },
      },
    },
    Drawer: {
      color: isAnchor ? anchorBg : (isDark ? '#0b1121' : '#eef1f6'),
      bodyPadding: '0',
    },
    Tabs: {
      tabTextColorActiveLine: isAnchor ? anchorPrimary : (isDark ? '#818cf8' : '#4f46e5'),
      tabTextColorHoverLine: isAnchor ? anchorText2 : (isDark ? '#94a3b8' : '#475569'),
      barColor: isAnchor ? anchorPrimary : (isDark ? '#818cf8' : '#4f46e5'),
    },
    Switch: {
      railColorActive: isAnchor ? anchorPrimary : (isDark ? '#818cf8' : '#4f46e5'),
    },
    Alert: {
      color: isAnchor ? anchorSurface : (isDark ? '#131c31' : '#ffffff'),
      border: 'none',
    },
    Form: {
      labelTextColorTop: isAnchor ? anchorText2 : (isDark ? '#94a3b8' : '#475569'),
    },
    Scrollbar: {
      width: '8px',
      height: '8px',
      borderRadius: '4px',
    },
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
