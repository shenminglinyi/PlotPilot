<template>
  <div class="cws" :class="{ 'cws--stacked': stacked }">
    <div class="cws-main">
      <div v-if="$slots['manuscript-toolbar']" class="cws-toolbar">
        <slot name="manuscript-toolbar" />
      </div>
      <div class="cws-primary">
        <slot name="primary" />
      </div>
    </div>

    <!-- 宽屏：固定侧栏 -->
    <aside v-if="railEnabled && !stacked && railExpanded" class="cws-rail" aria-label="本章上下文侧栏">
      <div class="cws-rail-inner">
        <slot name="rail" />
      </div>
    </aside>

    <!-- 宽屏：侧栏收起的窄触轨 -->
    <div
      v-if="railEnabled && !stacked && !railExpanded"
      class="cws-rail-collapsed"
      role="toolbar"
      aria-label="展开侧栏与主栏工具"
    >
      <n-tooltip placement="left" trigger="hover">
        <template #trigger>
          <n-button quaternary size="small" class="cws-rail-expand-btn" @click="emitRail(true)">
            <template #icon>
              <ChevronBackOutline />
            </template>
          </n-button>
        </template>
        展开任务与状态侧栏
      </n-tooltip>
      <div class="cws-rail-collapsed-divider" />
      <slot name="rail-collapsed-actions" />
    </div>

    <!-- 窄屏：任务与状态进抽屉 -->
    <n-drawer
      v-if="railEnabled && stacked"
      :show="railExpanded"
      @update:show="emitRail"
      :width="drawerW"
      placement="right"
      display-directive="if"
      :auto-focus="false"
      class="cws-rail-drawer"
    >
      <n-drawer-content :title="props.railDrawerTitle" closable @close="emitRail(false)">
        <div class="cws-rail-inner cws-rail-inner--drawer">
          <slot name="rail" />
        </div>
      </n-drawer-content>
    </n-drawer>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { NButton, NDrawer, NDrawerContent, NTooltip } from 'naive-ui'
import { ChevronBackOutline } from '@vicons/ionicons5'

const props = withDefaults(
  defineProps<{
    stacked: boolean
    railExpanded: boolean
    railEnabled?: boolean
    /** 窄屏侧栏抽屉标题 */
    railDrawerTitle?: string
  }>(),
  {
    railEnabled: true,
    railDrawerTitle: '本章任务与状态',
  }
)

const emit = defineEmits<{
  'update:railExpanded': [v: boolean]
}>()

const drawerW = computed(() => 'var(--plotpilot-chapter-rail-drawer)')

function emitRail(v: boolean) {
  emit('update:railExpanded', v)
}
</script>

<style scoped>
.cws {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: row;
  overflow: hidden;
  background: var(--app-surface);
}

.cws-main {
  flex: 1;
  min-width: 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.cws-toolbar {
  flex-shrink: 0;
  padding: var(--plotpilot-shell-toolbar-pad-top) var(--plotpilot-shell-toolbar-pad-x) 0;
  border-bottom: 1px solid var(--plotpilot-split-border, rgba(0, 0, 0, 0.06));
}

.cws--stacked .cws-toolbar {
  padding-left: var(--plotpilot-space-5);
  padding-right: var(--plotpilot-space-5);
}

.cws-primary {
  flex: 1;
  min-height: 0;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.cws-rail {
  width: var(--plotpilot-chapter-rail-width);
  flex-shrink: 0;
  border-left: 1px solid var(--plotpilot-split-border, rgba(0, 0, 0, 0.08));
  min-height: 0;
  display: flex;
  flex-direction: column;
  background: color-mix(in srgb, var(--app-surface) 92%, var(--app-page-bg, #f0f2f8) 8%);
}

.cws-rail-inner {
  flex: 1;
  min-height: 0;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.cws-rail-inner--drawer {
  max-height: calc(100vh - var(--plotpilot-rail-drawer-body-offset));
}

.cws-rail-collapsed {
  width: var(--plotpilot-chapter-rail-collapsed);
  flex-shrink: 0;
  border-left: 1px solid var(--plotpilot-split-border, rgba(0, 0, 0, 0.08));
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: var(--plotpilot-space-3) 0;
  gap: var(--plotpilot-space-2);
  background: color-mix(in srgb, var(--app-surface) 94%, var(--app-page-bg, #f0f2f8) 6%);
}

.cws-rail-collapsed-divider {
  width: 20px;
  height: 1px;
  background: var(--n-border-color);
  opacity: 0.7;
}

.cws-rail-collapsed :deep(.n-button) {
  padding: 0 4px;
}

.cws-rail-drawer :deep(.n-drawer-body-content-wrapper) {
  padding-top: 0;
}
</style>
