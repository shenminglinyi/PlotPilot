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

  return {
    common: {
      primaryColor: isDark ? '#818cf8' : '#4f46e5',
      primaryColorHover: isDark ? '#a5b4fc' : '#6366f1',
      primaryColorPressed: isDark ? '#6366f1' : '#4338ca',
      primaryColorSuppl: isDark ? '#c7d2fe' : '#818cf8',
      borderRadius: '10px',
      borderRadiusSmall: '8px',
      fontSize: '14px',
      fontSizeMedium: '15px',
      lineHeight: '1.55',
      heightMedium: '38px',

      /* 文字 — 使用变量体系 */
      bodyColor: isDark ? '#e2e8f0' : '#0f172a',
      textColor1: isDark ? '#e2e8f0' : '#0f172a',
      textColor2: isDark ? '#94a3b8' : '#475569',
      textColor3: isDark ? '#64748b' : '#64748b',

      /* 边框 */
      borderColor: isDark ? '#334155' : 'rgba(15, 23, 42, 0.09)',
      dividerColor: isDark ? '#1e293b' : 'rgba(15, 23, 42, 0.06)',

      /* 背景（暗色禁止纯白）*/
      cardColor: isDark ? '#131c31' : '#ffffff',
      modalColor: isDark ? '#131c31' : '#ffffff',
      popoverColor: isDark ? '#131c31' : '#ffffff',
      tableColor: isDark ? '#131c31' : '#ffffff',
      tableColorStriped: isDark ? '#0f172a' : '#f8fafc',
      tableColorHover: isDark ? '#1a2436' : '#f8fafc',
      tableHeaderColor: isDark ? '#131c31' : '#ffffff',
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
          color: isDark ? '#0f172a' : '#ffffff',
          borderActive: isDark ? '#818cf8' : '#4f46e5',
          borderFocus: isDark ? '#818cf8' : '#4f46e5',
        },
      },
    },
    Drawer: {
      color: isDark ? '#0b1121' : '#eef1f6',
      bodyPadding: '0',
    },
    Tabs: {
      tabTextColorActiveLine: isDark ? '#818cf8' : '#4f46e5',
      tabTextColorHoverLine: isDark ? '#94a3b8' : '#475569',
      barColor: isDark ? '#818cf8' : '#4f46e5',
    },
    Switch: {
      railColorActive: isDark ? '#818cf8' : '#4f46e5',
    },
    Alert: {
      color: isDark ? '#131c31' : '#ffffff',
      border: 'none',
    },
    Form: {
      labelTextColorTop: isDark ? '#94a3b8' : '#475569',
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
