<template>
  <div class="global-llm-entry">
    <button
      type="button"
      class="global-llm-main"
      :class="appearance === 'sidebar' ? 'variant-sidebar' : 'variant-topbar'"
      :aria-label="ariaLabel"
      @click="openPanel"
    >
      <span class="global-llm-glow"></span>

      <span class="global-llm-main-content">
        <span class="global-llm-icon-core">
          <span class="global-llm-icon-grid"></span>
          <span class="global-llm-icon-chip">⚙️</span>
          <span class="global-llm-icon-spark">✦</span>
        </span>

        <span class="global-llm-copy">
          <span class="global-llm-title-row">
            <span class="global-llm-title">AI 控制台</span>
            <span class="global-llm-status"></span>
          </span>
          <span v-if="appearance !== 'sidebar'" class="global-llm-subtitle">
            LLM Gateway · OpenAI / Claude / Gemini
          </span>
        </span>
      </span>
    </button>

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
                  <n-button size="tiny" secondary @click="modelSettingsModalRef?.open()">
                    核心引擎
                  </n-button>
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

      <!-- 核心引擎配置模态框 -->
      <ModelSettingsModal ref="modelSettingsModalRef" />
    </teleport>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { NDrawer, NDrawerContent, NButton } from 'naive-ui'
import {
  llmControlApi,
  type LLMControlPanelData,
  type LLMRuntimeSummary,
} from '../../api/llmControl'
import LLMControlPanel from '../workbench/LLMControlPanel.vue'
import ModelSettingsModal from '../settings/ModelSettingsModal.vue'

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
const modelSettingsModalRef = ref<InstanceType<typeof ModelSettingsModal> | null>(null)

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
  width: 100%;
}

/* 顶部入口：复用原悬浮按钮的视觉，但不再 fixed/拖拽 */
.global-llm-main {
  position: relative;
  display: block;
  overflow: hidden;
  border: 1px solid rgba(148, 163, 184, 0.22);
  background:
    radial-gradient(circle at 18% 18%, rgba(129, 140, 248, 0.32), transparent 28%),
    linear-gradient(135deg, rgba(15, 23, 42, 0.98), rgba(49, 46, 129, 0.95) 55%, rgba(37, 99, 235, 0.9));
  color: #fff;
  box-shadow:
    0 12px 30px rgba(30, 41, 59, 0.2),
    0 10px 26px rgba(79, 70, 229, 0.22);
  backdrop-filter: blur(12px);
  cursor: pointer;
  transition:
    transform 0.18s ease,
    box-shadow 0.18s ease,
    opacity 0.18s ease,
    border-color 0.18s ease;
}

.global-llm-main.variant-topbar {
  width: 248px;
  min-height: 68px;
  padding: 12px 14px;
  border-radius: 20px;
}

.global-llm-main.variant-sidebar {
  width: 100%;
  min-height: 0;
  padding: 12px 10px;
  border-radius: 12px;
  box-shadow:
    0 10px 22px rgba(30, 41, 59, 0.14),
    0 8px 18px rgba(79, 70, 229, 0.14);
}

.global-llm-main:hover {
  transform: translateY(-1px);
  border-color: rgba(191, 219, 254, 0.45);
  box-shadow:
    0 14px 34px rgba(30, 41, 59, 0.24),
    0 14px 32px rgba(79, 70, 229, 0.28);
}

.global-llm-glow {
  position: absolute;
  inset: 0;
  background:
    radial-gradient(circle at 80% 20%, rgba(255, 255, 255, 0.18), transparent 24%),
    linear-gradient(180deg, rgba(255, 255, 255, 0.06), transparent 45%);
  pointer-events: none;
}

.global-llm-main-content {
  position: relative;
  z-index: 1;
  display: flex;
  align-items: center;
  gap: 12px;
}

.global-llm-main.variant-sidebar .global-llm-main-content {
  gap: 10px;
}

.global-llm-icon-core {
  position: relative;
  flex: 0 0 auto;
  width: 40px;
  height: 40px;
  border-radius: 14px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(180deg, rgba(15, 23, 42, 0.5), rgba(15, 23, 42, 0.16));
  border: 1px solid rgba(255, 255, 255, 0.12);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.08);
}

.global-llm-icon-grid {
  position: absolute;
  inset: 8px;
  border-radius: inherit;
  opacity: 0.35;
  background-image:
    linear-gradient(rgba(191, 219, 254, 0.12) 1px, transparent 1px),
    linear-gradient(90deg, rgba(191, 219, 254, 0.12) 1px, transparent 1px);
  background-size: 7px 7px;
}

.global-llm-icon-chip {
  position: relative;
  z-index: 1;
  font-size: 16px;
  line-height: 1;
}

.global-llm-icon-spark {
  position: absolute;
  top: 4px;
  right: 4px;
  font-size: 12px;
  color: #fef08a;
  filter: drop-shadow(0 0 6px rgba(253, 224, 71, 0.4));
}

.global-llm-main.variant-sidebar .global-llm-icon-core {
  width: 34px;
  height: 34px;
  border-radius: 12px;
}

.global-llm-main.variant-sidebar .global-llm-icon-grid {
  inset: 7px;
}

.global-llm-main.variant-sidebar .global-llm-icon-spark {
  top: 3px;
  right: 3px;
  font-size: 11px;
}

.global-llm-copy {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 5px;
}

.global-llm-main.variant-sidebar .global-llm-copy {
  gap: 0;
}

.global-llm-title-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.global-llm-title {
  font-size: 14px;
  font-weight: 700;
  letter-spacing: 0.02em;
}

.global-llm-status {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: linear-gradient(180deg, #86efac, #22c55e);
  box-shadow: 0 0 0 4px rgba(34, 197, 94, 0.14);
}

.global-llm-subtitle {
  max-width: 170px;
  color: rgba(226, 232, 240, 0.82);
  font-size: 11px;
  line-height: 1.35;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
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

