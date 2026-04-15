<template>
  <div class="global-llm-entry">
    <button
      v-if="appearance === 'sidebar'"
      type="button"
      class="action-btn"
      @click="openPanel"
      :aria-label="ariaLabel"
    >
      <span class="action-icon">🤖</span>
      <span>AI 控制台</span>
    </button>

    <n-button
      v-else
      type="default"
      secondary
      size="small"
      round
      class="topbar-btn"
      @click="openPanel"
    >
      <template #icon>
        <span style="font-size: 14px">🤖</span>
      </template>
      AI 控制台
    </n-button>

    <teleport to="body">
      <n-drawer
        :show="showPanel"
        placement="right"
        :width="drawerWidth"
        :close-on-esc="true"
        :mask-closable="true"
        @update:show="handleDrawerShowChange"
      >
        <n-drawer-content
          closable
          :header-style="drawerHeaderStyle"
          :native-scrollbar="false"
          :body-content-style="drawerBodyStyle"
        >
          <template #header>
            <div class="global-llm-drawer-header">
              <div class="global-llm-drawer-title-wrap">
                <div class="global-llm-drawer-title">全局 LLM 设置</div>
                <div class="global-llm-drawer-subtitle">统一控制当前项目的模型网关、协议与激活配置</div>
              </div>

              <div class="global-llm-runtime-bar" :class="{ 'is-mock': runtimeSummary?.using_mock }">
                <div class="global-llm-runtime-main">
                  <span class="global-llm-runtime-label">当前激活模型</span>
                  <span class="global-llm-runtime-model">
                    {{ runtimeSummary?.model || (runtimeLoading ? '读取中…' : '未配置') }}
                  </span>
                </div>
                <div class="global-llm-runtime-meta">
                  <span class="global-llm-runtime-chip">
                    {{ runtimeSummary?.protocol || (runtimeLoading ? 'loading' : 'mock') }}
                  </span>
                  <span class="global-llm-runtime-name">
                    {{ runtimeSummary?.active_profile_name || runtimeSummary?.reason || '未激活任何配置' }}
                  </span>
                </div>
              </div>
            </div>
          </template>

          <div class="global-llm-drawer-body">
            <LLMControlPanel
              scroll-state-key="global-drawer"
              @panel-updated="handlePanelUpdated"
            />
          </div>
        </n-drawer-content>
      </n-drawer>
    </teleport>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { NButton, NDrawer, NDrawerContent } from 'naive-ui'
import {
  llmControlApi,
  type LLMControlPanelData,
  type LLMRuntimeSummary,
} from '../../api/llmControl'
import LLMControlPanel from '../workbench/LLMControlPanel.vue'

type Appearance = 'sidebar' | 'topbar'

const props = withDefaults(defineProps<{
  appearance?: Appearance
  ariaLabel?: string
}>(), {
  appearance: 'sidebar',
  ariaLabel: '打开 AI 控制台',
})

const showPanel = ref(false)
const runtimeLoading = ref(false)
const runtimeSummary = ref<LLMRuntimeSummary | null>(null)

const drawerWidth = computed(() => {
  const width = document.documentElement?.clientWidth || window.innerWidth || 1440
  if (width <= 640) return width
  if (width <= 900) return Math.max(360, Math.round(width * 0.96))
  if (width <= 1280) return Math.min(960, Math.round(width * 0.84))
  return 1040
})

const drawerBodyStyle = computed(() => {
  const width = document.documentElement?.clientWidth || window.innerWidth || 1440
  return {
    padding: '0',
    height: width <= 768 ? 'calc(100vh - 56px)' : 'calc(100vh - 68px)',
  }
})

const drawerHeaderStyle = computed(() => {
  const width = document.documentElement?.clientWidth || window.innerWidth || 1440
  return {
    padding: width <= 768 ? '16px 16px 12px' : '18px 20px 14px',
  }
})

function openPanel() {
  void refreshRuntimeSummary()
  showPanel.value = true
}

async function refreshRuntimeSummary() {
  runtimeLoading.value = true
  try {
    const data = await llmControlApi.getPanel()
    runtimeSummary.value = data.runtime
  } catch {
    runtimeSummary.value = null
  } finally {
    runtimeLoading.value = false
  }
}

function handlePanelUpdated(data: LLMControlPanelData) {
  runtimeSummary.value = data.runtime
}

function handleDrawerShowChange(value: boolean) {
  showPanel.value = value
  if (value) void refreshRuntimeSummary()
}

const appearance = computed(() => props.appearance)
</script>

<style scoped>
.global-llm-entry {
  display: inline-flex;
  align-items: center;
}

.topbar-btn {
  border-color: rgba(255, 255, 255, 0.35);
  color: rgba(255, 255, 255, 0.95);
}

.topbar-btn :deep(.n-button__content) {
  font-weight: 600;
}

/* Drawer header/body styles copied for visual consistency */
.global-llm-drawer-header {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.global-llm-drawer-title-wrap {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.global-llm-drawer-title {
  font-size: 18px;
  font-weight: 700;
  color: #0f172a;
}

.global-llm-drawer-subtitle {
  font-size: 12px;
  color: #64748b;
}

.global-llm-runtime-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 14px;
  border-radius: 14px;
  background:
    linear-gradient(135deg, rgba(79, 70, 229, 0.08), rgba(59, 130, 246, 0.08)),
    #f8fafc;
  border: 1px solid rgba(99, 102, 241, 0.1);
}

.global-llm-runtime-bar.is-mock {
  background:
    linear-gradient(135deg, rgba(245, 158, 11, 0.12), rgba(249, 115, 22, 0.1)),
    #fffaf0;
  border-color: rgba(245, 158, 11, 0.18);
}

.global-llm-runtime-main {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.global-llm-runtime-label {
  font-size: 11px;
  line-height: 1;
  color: #64748b;
}

.global-llm-runtime-model {
  font-size: 15px;
  font-weight: 700;
  line-height: 1.25;
  color: #0f172a;
}

.global-llm-runtime-meta {
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 8px;
}

.global-llm-runtime-chip {
  flex-shrink: 0;
  padding: 4px 9px;
  border-radius: 999px;
  background: rgba(79, 70, 229, 0.1);
  color: #4338ca;
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
}

.global-llm-runtime-name {
  max-width: 320px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: #475569;
  font-size: 12px;
}

.global-llm-drawer-body {
  height: 100%;
  min-height: 0;
  overflow: hidden;
}

@media (max-width: 768px) {
  .global-llm-runtime-bar {
    flex-direction: column;
    align-items: flex-start;
  }

  .global-llm-runtime-meta {
    width: 100%;
    flex-wrap: wrap;
  }

  .global-llm-runtime-name {
    max-width: 100%;
    white-space: normal;
  }
}
</style>

