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
            {{ drawerTab === 'embedding' ? '嵌入模型 · 向量检索配置' : 'LLM Gateway · OpenAI / Claude / Gemini' }}
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
              <!-- 顶部 Tab 切换 -->
              <div class="drawer-tab-switch">
                <div class="drawer-tab-track" :style="{ transform: `translateX(${drawerTab === 'embedding' ? 0 : '100%'})` }"></div>
                <button
                  type="button"
                  class="drawer-tab-btn"
                  :class="{ active: drawerTab === 'embedding' }"
                  @click="drawerTab = 'embedding'"
                >
                  嵌入模型
                </button>
                <button
                  type="button"
                  class="drawer-tab-btn"
                  :class="{ active: drawerTab === 'llm' }"
                  @click="drawerTab = 'llm'"
                >
                  LLM 设置
                </button>
              </div>

              <!-- 运行时状态栏（仅 LLM 标签页显示） -->
              <div v-if="drawerTab === 'llm'" class="global-llm-runtime-bar" :class="{ 'is-mock': runtimeSummary?.using_mock }">
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

              <!-- 嵌入模型标题（仅嵌入标签页显示） -->
              <div v-else class="embedding-header-info">
                <div class="embedding-header-title">向量检索使用的嵌入模型配置</div>
                <div class="embedding-header-desc">每本书的向量索引与嵌入模型绑定，一旦开始写作后切换模型将导致已有索引不可用。如需更换，请先删除对应书籍的向量数据（data/chromadb/）再重新生成。</div>
              </div>
            </div>
          </template>

          <div class="global-llm-drawer-body">
            <div class="drawer-scroll-content">
              <!-- ══════════════════════════════════
                   LLM 设置面板
                   ══════════════════════════════════ -->
              <div v-show="drawerTab === 'llm'">
                <LLMControlPanel
                  scroll-state-key="global-drawer"
                  @panel-updated="handlePanelUpdated"
                />
              </div>

              <!-- ══════════════════════════════════
                   嵌入模型面板
                   ══════════════════════════════════ -->
              <div v-show="drawerTab === 'embedding'" class="embedding-config-section">
                <div v-if="embeddingLoading" style="display: flex; justify-content: center; padding: 32px 0">
                  <n-spin size="medium" />
                </div>

                <template v-else>
                  <!-- 本地 / 云端 切换 -->
                  <div class="embedding-mode-switch">
                    <span class="emb-mode-label" :class="{ active: embeddingForm.mode === 'local' }">本地模型</span>
                    <n-switch
                      :value="embeddingForm.mode === 'openai'"
                      @update:value="embeddingForm.mode = $event ? 'openai' : 'local'"
                    />
                    <span class="emb-mode-label" :class="{ active: embeddingForm.mode === 'openai' }">云端模型</span>
                  </div>

                  <!-- Local mode -->
                  <div v-if="embeddingForm.mode === 'local'" class="emb-local-info">
                    <div class="emb-local-card">
                      <div class="emb-local-name">BAAI/bge-small-zh-v1.5</div>
                      <div class="emb-local-desc">本地中文嵌入模型，无需网络连接</div>
                    </div>
                    <n-form label-placement="left" label-width="100" style="margin-top: 14px">
                      <n-form-item label="模型路径">
                        <n-input v-model:value="embeddingForm.model_path" placeholder="BAAI/bge-small-zh-v1.5" />
                      </n-form-item>
                      <n-form-item label="GPU 加速">
                        <n-switch v-model:value="embeddingForm.use_gpu" />
                      </n-form-item>
                    </n-form>
                  </div>

                  <!-- Cloud mode -->
                  <div v-else class="emb-cloud-form">
                    <n-form label-placement="left" label-width="100">
                      <n-form-item label="API Key">
                        <n-input
                          v-model:value="embeddingForm.api_key"
                          type="password"
                          show-password-on="click"
                          placeholder="sk-..."
                        />
                      </n-form-item>
                      <n-form-item label="Base URL">
                        <n-input
                          v-model:value="embeddingForm.base_url"
                          placeholder="https://api.openai.com/v1"
                        />
                      </n-form-item>
                      <n-form-item label="模型">
                        <div class="model-row">
                          <n-select
                            v-model:value="embeddingForm.model"
                            filterable
                            tag
                            :options="embeddingModelOptions"
                            placeholder="选择或输入模型名称"
                            style="flex: 1"
                          />
                          <n-button
                            size="small"
                            :loading="fetchingEmbeddingModels"
                            :disabled="!embeddingForm.api_key || !embeddingForm.base_url"
                            @click="handleFetchEmbeddingModels"
                          >
                            获取列表
                          </n-button>
                        </div>
                      </n-form-item>
                    </n-form>
                  </div>

                  <div style="display: flex; justify-content: flex-end; margin-top: 16px">
                    <n-button
                      type="primary"
                      :loading="embeddingSaving"
                      @click="handleSaveEmbedding"
                    >
                      保存嵌入配置
                    </n-button>
                  </div>
                </template>
              </div>
            </div>
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
import { NDrawer, NDrawerContent, NButton, NSwitch, NForm, NFormItem, NInput, NSelect, NSpin } from 'naive-ui'
import {
  llmControlApi,
  type LLMControlPanelData,
  type LLMRuntimeSummary,
} from '../../api/llmControl'
import { settingsApi, type EmbeddingConfig } from '../../api/settings'
import LLMControlPanel from '../workbench/LLMControlPanel.vue'
import ModelSettingsModal from '../settings/ModelSettingsModal.vue'

type Appearance = 'sidebar' | 'topbar'
type DrawerTab = 'embedding' | 'llm'

const props = withDefaults(defineProps<{
  appearance?: Appearance
  ariaLabel?: string
}>(), {
  appearance: 'sidebar',
  ariaLabel: '打开 AI 控制台',
})

const showPanel = ref(false)
const drawerTab = ref<DrawerTab>('llm')
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

// ── Embedding state ────────────────────────────────────────
const embeddingLoading = ref(false)
const embeddingSaving = ref(false)
const fetchingEmbeddingModels = ref(false)
const embeddingModelOptions = ref<Array<{ label: string; value: string }>>([])

const embeddingForm = ref<EmbeddingConfig>({
  mode: 'local',
  api_key: '',
  base_url: '',
  model: 'text-embedding-3-small',
  use_gpu: true,
  model_path: 'BAAI/bge-small-zh-v1.5',
})

async function loadEmbeddingConfig() {
  embeddingLoading.value = true
  try {
    const cfg = await settingsApi.getEmbeddingConfig()
    embeddingForm.value = cfg
    if (cfg.model) {
      embeddingModelOptions.value = [{ label: cfg.model, value: cfg.model }]
    }
  } catch {
    // 静默失败，使用默认值
  } finally {
    embeddingLoading.value = false
  }
}

async function handleSaveEmbedding() {
  embeddingSaving.value = true
  try {
    const result = await settingsApi.updateEmbeddingConfig({ ...embeddingForm.value })
    embeddingForm.value = result
  } catch {
    // 由 naive-ui form 处理错误提示
  } finally {
    embeddingSaving.value = false
  }
}

async function handleFetchEmbeddingModels() {
  fetchingEmbeddingModels.value = true
  try {
    const models = await settingsApi.fetchEmbeddingModels({
      provider: 'openai',
      api_key: embeddingForm.value.api_key,
      base_url: embeddingForm.value.base_url,
    })
    embeddingModelOptions.value = models.map((m: string) => ({ label: m, value: m }))
  } catch {
    // 静默失败
  } finally {
    fetchingEmbeddingModels.value = false
  }
}

function openPanel() {
  void refreshRuntimeSummary()
  void loadEmbeddingConfig()
  showPanel.value = true
}
</script>

<style scoped>
.global-llm-entry {
  display: inline-flex;
  align-items: center;
  width: 100%;
}

/* ── 入口按钮 ──────────────────────────────────────── */
.global-llm-main {
  position: relative;
  display: block;
  overflow: hidden;
  border: 1px solid var(--app-border);
  background:
    radial-gradient(circle at 18% 18%, var(--color-brand-light, rgba(129, 140, 248, 0.32)), transparent 28%),
    linear-gradient(135deg, var(--color-brand), var(--color-brand-hover));
  color: var(--app-text-inverse);
  box-shadow: var(--app-shadow-md), 0 10px 26px var(--color-brand-border, rgba(79, 70, 229, 0.22));
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
  border-radius: var(--app-radius-xl);
}

.global-llm-main.variant-sidebar {
  width: 100%;
  min-height: 0;
  padding: 14px 12px;
  border-radius: 12px;
  box-shadow: var(--app-shadow-sm), 0 1px 3px rgba(0, 0, 0, 0.05);
}

.global-llm-main:hover {
  transform: translateY(-1px);
  border-color: var(--color-brand-border);
  box-shadow: var(--app-shadow-lg), 0 14px 32px var(--color-brand-border, rgba(79, 70, 229, 0.28));
}

.global-llm-main.variant-sidebar:hover {
  box-shadow: var(--app-shadow-sm), 0 2px 8px var(--color-brand-border, rgba(79, 70, 229, 0.18));
}

.global-llm-glow {
  position: absolute;
  inset: 0;
  background:
    radial-gradient(circle at 80% 20%, var(--app-text-inverse, rgba(255, 255, 255, 0.18)), transparent 24%),
    linear-gradient(180deg, var(--app-text-inverse, rgba(255, 255, 255, 0.06)), transparent 45%);
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
  flex-direction: column;
  gap: 6px;
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
  background: linear-gradient(180deg, var(--app-text-inverse, rgba(15, 23, 42, 0.5)), var(--app-text-inverse, rgba(15, 23, 42, 0.16)));
  border: 1px solid var(--app-text-inverse, rgba(255, 255, 255, 0.12));
  box-shadow: inset 0 1px 0 var(--app-text-inverse, rgba(255, 255, 255, 0.08));
}
.global-llm-main.variant-sidebar .global-llm-icon-core { 
  width: 24px; 
  height: 24px; 
  border-radius: 8px; 
}

.global-llm-icon-grid {
  position: absolute;
  inset: 8px;
  border-radius: inherit;
  opacity: 0.35;
  background-image:
    linear-gradient(var(--color-brand-suppl, rgba(191, 219, 254, 0.12)) 1px, transparent 1px),
    linear-gradient(90deg, var(--color-brand-suppl, rgba(191, 219, 254, 0.12)) 1px, transparent 1px);
  background-size: 7px 7px;
}
.global-llm-main.variant-sidebar .global-llm-icon-grid { 
  inset: 4px; 
  background-size: 4px 4px; 
}

.global-llm-icon-chip {
  position: relative;
  z-index: 1;
  font-size: 16px;
  line-height: 1;
}
.global-llm-main.variant-sidebar .global-llm-icon-chip { font-size: 11px; }

.global-llm-icon-spark {
  position: absolute;
  top: 4px;
  right: 4px;
  font-size: 12px;
  color: var(--color-gold);
  filter: drop-shadow(0 0 6px var(--color-gold-glow));
}
.global-llm-main.variant-sidebar .global-llm-icon-spark { 
  top: 1px; 
  right: 1px; 
  font-size: 7px; 
  width: 5px; 
  height: 5px; 
  border-radius: 50%; 
  background: var(--color-gold); 
  box-shadow: 0 0 4px var(--color-gold-glow); 
}

.global-llm-copy {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 5px;
}
.global-llm-main.variant-sidebar .global-llm-copy { 
  gap: 0; 
  align-items: center; 
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
.global-llm-main.variant-sidebar .global-llm-title { 
  font-size: 12px; 
}

.global-llm-status {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: linear-gradient(180deg, var(--color-success-light, #86efac), var(--color-success, #22c55e));
  box-shadow: 0 0 0 4px var(--color-success-light, rgba(34, 197, 94, 0.14));
}
.global-llm-main.variant-sidebar .global-llm-status { 
  width: 6px; 
  height: 6px; 
}

.global-llm-subtitle {
  max-width: 170px;
  color: var(--app-text-secondary, rgba(226, 232, 240, 0.82));
  font-size: 11px;
  line-height: 1.35;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* ── Drawer Header ─────────────────────────────────── */
.global-llm-drawer-header {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

/* ── Tab Switch（切换嵌入/LLM）── */
.drawer-tab-switch {
  position: relative;
  display: flex;
  background: var(--app-surface-subtle);
  border: 1px solid var(--app-border);
  border-radius: var(--app-radius-lg);
  padding: 4px;
  gap: 0;
  width: 100%;
}

.drawer-tab-track {
  position: absolute;
  top: 4px;
  left: 4px;
  width: calc(50% - 4px);
  height: calc(100% - 8px);
  background: var(--tab-track-bg);
  border-radius: calc(var(--app-radius-lg) - 5px);
  transition: transform 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  box-shadow: var(--tab-track-shadow);
  z-index: 0;
  pointer-events: none;
}

.drawer-tab-btn {
  position: relative;
  z-index: 2;
  display: flex;
  align-items: center;
  justify-content: center;
  flex: 1;
  padding: 9px 16px;
  border: none;
  background: transparent;
  color: var(--tab-inactive-color, var(--app-text-secondary));
  font-size: 13.5px;
  font-weight: 700;
  letter-spacing: 0.02em;
  border-radius: calc(var(--app-radius-lg) - 5px);
  cursor: pointer;
  transition: color 0.22s ease, background 0.22s ease;
  white-space: nowrap;
  user-select: none;
}

.drawer-tab-btn.active {
  color: var(--tab-active-color, var(--app-text-inverse, #ffffff));
  text-shadow: 0 1px 4px rgba(0, 0, 0, 0.3);
}

.drawer-tab-btn:not(.active) {
  opacity: 0.8;
}

.drawer-tab-btn:hover:not(.active) {
  color: var(--tab-inactive-hover-color);
  opacity: 1;
}

/* ── 嵌入模型头部信息 ─────────────────────────────── */
.embedding-header-info {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.embedding-header-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--app-text-primary);
}

.embedding-header-desc {
  font-size: 11.5px;
  line-height: 1.45;
  color: var(--app-text-muted);
}

/* ── Runtime Bar ───────────────────────────────────── */
.global-llm-runtime-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 14px;
  border-radius: var(--app-radius-lg);
  background: var(--runtime-bar-bg, linear-gradient(135deg, var(--color-brand-light), var(--app-surface)));
  border: 1px solid var(--runtime-bar-border, var(--color-brand-border));
}

.global-llm-runtime-bar.is-mock {
  background: var(--runtime-mock-bg, linear-gradient(135deg, var(--color-gold-dim), var(--app-surface)));
  border-color: var(--runtime-mock-border, var(--color-gold-border));
}

.global-llm-runtime-bar.is-mock .global-llm-runtime-model {
  color: var(--runtime-mock-model-color, var(--color-gold));
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
  color: var(--app-text-muted);
}

.global-llm-runtime-model {
  font-size: 15px;
  font-weight: 800;
  line-height: 1.25;
  color: var(--runtime-model-color, var(--color-brand));
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
  background: var(--color-brand-light);
  color: var(--color-brand);
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
}

.global-llm-runtime-name {
  max-width: 320px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--app-text-secondary);
  font-size: 12px;
}

/* ── Drawer Body ───────────────────────────────────── */
.global-llm-drawer-body {
  height: 100%;
  min-height: 0;
  overflow: hidden;
}

.drawer-scroll-content {
  height: 100%;
  overflow-y: auto;
  padding-right: 4px;
}

/* ── 嵌入模型区域 ─────────────────────────────────── */
.embedding-config-section {
  margin-top: 8px;
}

.embedding-mode-switch {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 16px 0 8px;
}

.emb-mode-label {
  font-size: 13px;
  color: var(--app-text-muted);
  transition: color 0.2s;
  font-weight: 500;
}

.emb-mode-label.active {
  color: var(--app-text-primary);
  font-weight: 600;
}

.emb-local-info { padding: 0 4px; }

.emb-local-card {
  background: var(--color-success-light);
  border: 1px solid rgba(34, 197, 94, 0.25);
  border-radius: var(--app-radius-md);
  padding: 14px 18px;
}

[data-theme='dark'] .emb-local-card,
[data-theme='anchor'] .emb-local-card {
  background: rgba(34, 197, 94, 0.08);
  border-color: rgba(34, 197, 94, 0.15);
}

.emb-local-name {
  font-weight: 600;
  font-size: 14px;
  color: var(--color-success);
  margin-bottom: 3px;
}

.emb-local-desc {
  font-size: 12.5px;
  color: var(--color-success);
  opacity: 0.75;
}

.emb-cloud-form { padding: 0 4px; }

.model-row {
  display: flex;
  gap: 8px;
  width: 100%;
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
