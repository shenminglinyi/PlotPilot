<template>
  <n-modal
    v-model:show="visible"
    preset="card"
    title="应用设置"
    :style="{ width: 'min(920px, 96vw)' }"
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
.app-settings-tabs {
  min-height: 420px;
}

.app-settings-tabs :deep(.n-tabs-nav) {
  min-width: 148px;
}

.app-settings-tabs :deep(.n-tabs-pane-wrapper) {
  padding-left: 20px;
  flex: 1;
  min-width: 0;
}

.pane-desc {
  font-size: 13px;
  color: var(--app-text-secondary, #64748b);
  margin-bottom: 16px;
  line-height: 1.5;
}
</style>
