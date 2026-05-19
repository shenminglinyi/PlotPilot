<template>
  <n-modal
    v-model:show="visible"
    preset="card"
    title="应用设置"
    class="settings-modal"
    :style="{ width: 'min(920px, 96vw)', maxHeight: '90vh' }"
    :mask-closable="false"
    :segmented="{ content: 'soft', footer: 'soft' }"
  >
    <n-tabs
      v-model:value="activeSectionId"
      type="line"
      placement="left"
      size="large"
      class="app-settings-tabs"
    >
      <n-tab-pane
        v-for="meta in sections"
        :key="meta.id"
        :name="meta.id"
        :tab="meta.label"
        display-directive="if"
      >
        <div v-if="meta.description" class="pane-desc">
          {{ meta.description }}
        </div>
        <component :is="panels[meta.id]" />
      </n-tab-pane>
    </n-tabs>
  </n-modal>
</template>

<script setup lang="ts">
import { defineAsyncComponent, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { useAppSettingsShellStore } from '@/stores/appSettingsShellStore'
import {
  DEFAULT_SETTINGS_SECTION_ID,
  getAppSettingsSections,
  isRegisteredSettingsSectionId,
} from '@/settings/registry'

const shell = useAppSettingsShellStore()
const { visible, activeSectionId } = storeToRefs(shell)

const sections = getAppSettingsSections()

const panels = Object.fromEntries(
  sections.map((s) => [s.id, defineAsyncComponent(s.component)]),
)

watch(visible, (v) => {
  if (v && !isRegisteredSettingsSectionId(activeSectionId.value)) {
    activeSectionId.value = DEFAULT_SETTINGS_SECTION_ID
  }
})
</script>

<style scoped>
/* 整个 Modal card 最高 90vh，内容区超出时平滑滚动且不显示滚动条 */
:deep(.n-card) {
  display: flex;
  flex-direction: column;
  max-height: 90vh;
  overflow: hidden;
}

:deep(.n-card__content) {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  scrollbar-width: none;        /* Firefox */
  -ms-overflow-style: none;     /* IE/Edge */
  scroll-behavior: smooth;
}

:deep(.n-card__content::-webkit-scrollbar) {
  display: none;                /* Chrome/Safari */
}

.app-settings-tabs {
  /* rem 随 --app-font-scale 联动；min 保底 320px 以防极窄屏 */
  min-height: max(26rem, 320px);
}

.app-settings-tabs :deep(.n-tabs-nav) {
  min-width: 9.5rem;   /* 152px @ scale=1 */
}

.app-settings-tabs :deep(.n-tabs-pane-wrapper) {
  padding-left: 1.375rem;  /* ~22px */
  flex: 1;
  min-width: 0;
  overflow-y: auto;
  scrollbar-width: none;
  -ms-overflow-style: none;
}

.app-settings-tabs :deep(.n-tabs-pane-wrapper::-webkit-scrollbar) {
  display: none;
}

.pane-desc {
  font-size: var(--font-size-sm);
  color: var(--app-text-secondary, #64748b);
  margin-bottom: 1rem;
  line-height: 1.5;
}
</style>
