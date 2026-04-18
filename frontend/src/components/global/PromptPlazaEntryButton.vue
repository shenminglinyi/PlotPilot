<template>
  <div class="plaza-entry">
    <!-- 入口按钮 —— 仿 AI 控制台样式 -->
    <button
      type="button"
      class="plaza-main"
      :class="appearance === 'sidebar' ? 'variant-sidebar' : 'variant-topbar'"
      aria-label="提示词广场"
      @click="openModal"
    >
      <span class="plaza-glow"></span>

      <span class="plaza-main-content">
        <template v-if="appearance === 'sidebar'">
          <span class="plaza-plain-icon" aria-hidden="true">
            <svg viewBox="0 0 24 24" fill="none">
              <path d="M6 19h12M6 5h12M7 9h10M7 13h10" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>
            </svg>
          </span>
          <span class="plaza-title">提示词广场</span>
        </template>
        <template v-else>
          <span class="plaza-icon-core">
            <span class="plaza-icon-grid"></span>
            <span class="plaza-icon-chip">P</span>
            <span class="plaza-icon-spark"></span>
          </span>

          <span class="plaza-copy">
            <span class="plaza-title-row">
              <span class="plaza-title">提示词广场</span>
              <span v-if="promptCount > 0" class="plaza-count">{{ promptCount }}</span>
            </span>
            <span class="plaza-subtitle">
              浏览 · 编辑 · 版本管理
            </span>
          </span>
        </template>
      </span>
    </button>

    <!-- 弹窗 -->
    <teleport to="body">
      <n-modal
        v-model:show="showModal"
        preset="card"
        title=""
        :style="{ width: '92vw', maxWidth: '1100px', height: '85vh', marginTop: '5vh' }"
        :bordered="true"
        :segmented="{ content: true, footer: 'soft' }"
        :mask-closable="true"
        :close-on-esc="true"
        @after-leave="onModalClose"
      >
        <!-- 弹窗头部 -->
        <template #header>
          <div class="modal-header">
            <div class="modal-header-left">
              <span class="modal-header-icon">P</span>
              <span class="modal-header-title">提示词广场</span>
              <n-tag size="small" type="info" :bordered="false" v-if="stats">
                {{ stats.total_nodes }} 个 · {{ stats.total_versions }} 版本
              </n-tag>
            </div>
            <div class="modal-header-actions">
              <n-button size="small" secondary @click="handleExport">
                导出
              </n-button>
              <n-button size="small" secondary @click="triggerImport">
                导入
              </n-button>
            </div>
          </div>
        </template>

        <!-- 弹窗内容 -->
        <div class="modal-body">
          <PromptPlaza v-if="showModal" @refresh-stats="loadStats" ref="plazaRef" />
        </div>

        <!-- 弹窗底部 -->
        <template #footer>
          <div class="modal-footer-hint">
            内置提示词支持版本管理，自定义修改会自动创建新版本快照
          </div>
        </template>
      </n-modal>
    </teleport>

    <!-- 导入弹窗 -->
    <n-modal
      v-model:show="showImportModal"
      preset="dialog"
      title="导入提示词"
      positive-text="导入"
      negative-text="取消"
      @positive-click="handleImport"
      style="max-width: 520px"
    >
      <div class="import-body">
        <p class="import-hint">选择一个 JSON 文件，将覆盖或新增提示词节点。</p>
        <n-upload
          accept=".json"
          :max="1"
          :show-file-list="true"
          @change="handleFileSelect"
        >
          <n-button>选择文件</n-button>
        </n-upload>
      </div>
    </n-modal>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import {
  NModal, NTag, NButton,
  NUpload, useMessage,
} from 'naive-ui'
import PromptPlaza from '../workbench/PromptPlaza.vue'
import { promptPlazaApi, type PromptStats } from '../../api/llmControl'

type Appearance = 'sidebar' | 'topbar'

const props = withDefaults(defineProps<{
  appearance?: Appearance
}>(), {
  appearance: 'sidebar',
})

const message = useMessage()
const showModal = ref(false)
const promptCount = ref(0)
const stats = ref<PromptStats | null>(null)
const plazaRef = ref<{ loadData: () => Promise<void> } | null>(null)

// 导入相关
const showImportModal = ref(false)
const importFileContent = ref('')

function openModal() {
  showModal.value = true
}

function onModalClose() {
  loadStats()
}

async function loadStats() {
  try {
    const res = await promptPlazaApi.getStats()
    const data = res as unknown as PromptStats
    stats.value = data
    promptCount.value = data?.total_nodes || 0
  } catch {
    // 静默
  }
}

// ---- 导出 ----
async function handleExport() {
  try {
    const res = await promptPlazaApi.exportAll()
    const blob = new Blob([JSON.stringify(res, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `prompts-backup-${new Date().toISOString().slice(0, 10)}.json`
    a.click()
    URL.revokeObjectURL(url)
    message.success('导出成功')
  } catch (e: unknown) {
    const err = e as { message?: string }
    message.error(err?.message || '导出失败')
  }
}

// ---- 导入 ----
function triggerImport() {
  importFileContent.value = ''
  showImportModal.value = true
}

function handleFileSelect(data: { file: { file?: File | null }; fileList: Array<{ file?: File | null }>; event?: Event | ProgressEvent<EventTarget> }) {
  const f = data.file?.file
  if (!f) return
  const reader = new FileReader()
  reader.onload = (e) => {
    importFileContent.value = e.target?.result as string || ''
  }
  reader.readAsText(f)
}

async function handleImport() {
  if (!importFileContent.value) {
    message.warning('请先选择文件')
    return false
  }
  try {
    const data = JSON.parse(importFileContent.value) as Parameters<typeof promptPlazaApi.importData>[0]
    if (!data.prompts || !Array.isArray(data.prompts)) {
      message.error('JSON 中需包含 prompts 数组')
      return false
    }
    const result = await promptPlazaApi.importData(data)
    message.success(result.message || '导入成功')
    if (result.errors?.length) {
      message.warning(`部分条目未导入：${result.errors.slice(0, 3).join('；')}`)
    }
    showImportModal.value = false
    loadStats()
    await plazaRef.value?.loadData?.()
    return true
  } catch (e: unknown) {
    const err = e as { response?: { data?: { detail?: string } }; message?: string }
    message.error(err?.response?.data?.detail || err?.message || '导入失败，请检查 JSON 格式')
    return false
  }
}

onMounted(() => {
  loadStats()
})
</script>

<style scoped>
/* ════════════════════════════════════
   提示词广场入口按钮 —— 完全仿 AI 控制台
   ════════════════════════════════════ */
.plaza-entry {
  display: inline-flex;
  align-items: center;
  width: 100%;
}

/* ── 主按钮 ──────────────────────────────── */
.plaza-main {
  position: relative;
  display: block;
  overflow: hidden;
  border: 1px solid var(--app-border);
  background:
    radial-gradient(circle at 18% 18%, var(--color-plaza-light, rgba(16, 185, 129, 0.28)), transparent 28%),
    linear-gradient(135deg, var(--color-plaza, #059669), var(--color-plaza-hover, #047857));
  color: var(--app-text-inverse);
  box-shadow: var(--app-shadow-md), 0 10px 26px var(--color-plaza-border, rgba(5, 150, 105, 0.22));
  backdrop-filter: blur(12px);
  cursor: pointer;
  transition:
    transform 0.18s ease,
    box-shadow 0.18s ease,
    opacity 0.18s ease,
    border-color 0.18s ease;
}

.plaza-main.variant-topbar {
  width: 248px;
  min-height: 68px;
  padding: 12px 14px;
  border-radius: var(--app-radius-xl);
  color: var(--nav-hero-text);
  border-color: rgba(255, 255, 255, 0.28);
  background: linear-gradient(135deg, rgba(255, 255, 255, 0.14), rgba(255, 255, 255, 0.08));
  box-shadow:
    var(--app-shadow-md),
    0 12px 32px rgba(0, 0, 0, 0.18);
}

.plaza-main.variant-topbar .plaza-title {
  color: var(--nav-hero-text);
}

.plaza-main.variant-topbar .plaza-subtitle {
  color: var(--nav-hero-text-muted, rgba(255, 255, 255, 0.86));
}

.plaza-main.variant-topbar .plaza-icon-core {
  background: linear-gradient(
    180deg,
    var(--nav-hero-pill-bg-top, rgba(255, 255, 255, 0.22)),
    var(--nav-hero-pill-bg-bottom, rgba(255, 255, 255, 0.08))
  );
  border: 1px solid var(--nav-hero-pill-border, rgba(255, 255, 255, 0.28));
  box-shadow: var(--nav-hero-shadow, inset 0 1px 0 rgba(255, 255, 255, 0.12));
}

.plaza-main.variant-topbar .plaza-icon-grid {
  background-image:
    linear-gradient(rgba(255, 255, 255, 0.1) 1px, transparent 1px),
    linear-gradient(90deg, rgba(255, 255, 255, 0.1) 1px, transparent 1px);
}

.plaza-main.variant-topbar .plaza-count {
  background: rgba(255, 255, 255, 0.22);
  color: var(--nav-hero-text, #ffffff);
}

.plaza-main.variant-sidebar {
  width: 100%;
  box-sizing: border-box;
  min-height: 58px;
  padding: 0 14px;
  border-radius: 16px;
  background: linear-gradient(135deg, var(--color-brand-hover) 0%, var(--color-brand) 55%, var(--color-brand-pressed) 100%);
  color: var(--app-text-inverse);
  border: 1px solid color-mix(in srgb, var(--color-brand) 50%, transparent);
  box-shadow: none;
}

.plaza-main:hover {
  transform: translateY(-1px);
  border-color: var(--color-plaza-border);
  box-shadow: var(--app-shadow-lg), 0 14px 32px var(--color-plaza-border, rgba(5, 150, 105, 0.28));
}

.plaza-main.variant-sidebar:hover {
  filter: none;
  transform: none;
  background: linear-gradient(135deg, var(--color-brand, #4f46e5) 0%, var(--color-brand-hover, #6366f1) 55%, var(--color-brand-pressed, #4338ca) 100%);
  box-shadow: none;
}

/* ── 光晕层 ─────────────────────────────── */
.plaza-glow {
  position: absolute;
  inset: 0;
  background:
    radial-gradient(circle at 80% 20%, var(--app-text-inverse, rgba(255, 255, 255, 0.18)), transparent 24%),
    linear-gradient(180deg, var(--app-text-inverse, rgba(255, 255, 255, 0.06)), transparent 45%);
  pointer-events: none;
}

/* ── 内容区 ─────────────────────────────── */
.plaza-main-content {
  position: relative;
  z-index: 1;
  display: flex;
  align-items: center;
  gap: 12px;
}
.plaza-main.variant-sidebar .plaza-main-content { 
  flex-direction: row;
  justify-content: center;
  gap: 8px;
}

.plaza-main.variant-sidebar .plaza-glow {
  display: none;
}

.plaza-plain-icon {
  width: 16px;
  height: 16px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: var(--app-text-inverse, #ffffff);
}

.plaza-plain-icon svg {
  width: 16px;
  height: 16px;
}

[data-theme='anchor'] .plaza-main.variant-sidebar {
  background: linear-gradient(135deg, var(--color-brand-hover, #ddb930) 0%, var(--color-brand, #c9a227) 55%, var(--color-brand-pressed, #a88a1f) 100%);
  border-color: color-mix(in srgb, var(--color-brand, #c9a227) 62%, transparent);
  box-shadow: none;
}

[data-theme='anchor'] .plaza-main.variant-sidebar:hover {
  transform: none;
  filter: none;
  border-color: color-mix(in srgb, var(--color-brand, #c9a227) 74%, transparent);
  box-shadow: none;
}

/* ── 图标核心 ───────────────────────────── */
.plaza-icon-core {
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
.plaza-main.variant-sidebar .plaza-icon-core { 
  width: 24px; 
  height: 24px; 
  border-radius: 8px; 
}

.plaza-icon-grid {
  position: absolute;
  inset: 8px;
  border-radius: inherit;
  opacity: 0.35;
  background-image:
    linear-gradient(var(--color-plaza-suppl, rgba(167, 243, 208, 0.16)) 1px, transparent 1px),
    linear-gradient(90deg, var(--color-plaza-suppl, rgba(167, 243, 208, 0.16)) 1px, transparent 1px);
  background-size: 7px 7px;
}
.plaza-main.variant-sidebar .plaza-icon-grid { 
  inset: 4px; 
  background-size: 4px 4px; 
}

.plaza-icon-chip {
  position: relative;
  z-index: 1;
  font-size: 15px;
  font-weight: 800;
  line-height: 1;
  letter-spacing: -0.02em;
}
.plaza-main.variant-sidebar .plaza-icon-chip { font-size: 10px; }

.plaza-icon-spark {
  position: absolute;
  top: 4px;
  right: 4px;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--color-gold, #f59e0b);
  box-shadow: 0 0 6px var(--color-gold-glow, rgba(245, 158, 11, 0.6));
}
.plaza-main.variant-sidebar .plaza-icon-spark { 
  top: 1px; 
  right: 1px; 
  width: 4px; 
  height: 4px; 
}

/* ── 文字区 ─────────────────────────────── */
.plaza-copy {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 5px;
}
.plaza-main.variant-sidebar .plaza-copy { 
  gap: 0; 
  align-items: center; 
}

.plaza-title-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.plaza-title {
  font-size: 14px;
  font-weight: 700;
  letter-spacing: 0.02em;
}
.plaza-main.variant-sidebar .plaza-title { 
  font-size: 15px;
  font-weight: 600;
  line-height: 1;
  white-space: nowrap;
}

.plaza-count {
  font-size: 10.5px;
  font-weight: 600;
  background: var(--app-text-inverse);
  color: var(--app-text-primary);
  padding: 1px 7px;
  border-radius: 999px;
  letter-spacing: 0.3px;
}
.plaza-main.variant-sidebar .plaza-count { 
  font-size: 9px; 
  padding: 0px 5px; 
}

.plaza-subtitle {
  max-width: 170px;
  color: var(--app-text-secondary, rgba(226, 232, 240, 0.82));
  font-size: 11px;
  line-height: 1.35;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* ── Modal 头部 ──────────────────────────── */
.modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
}
.modal-header-left {
  display: flex;
  align-items: center;
  gap: 8px;
}
.modal-header-icon {
  width: 28px;
  height: 28px;
  border-radius: 9px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, var(--color-plaza, #059669), var(--color-plaza-hover, #047857));
  color: var(--app-text-inverse);
  font-size: 13px;
  font-weight: 800;
  letter-spacing: -0.01em;
}
.modal-header-title {
  font-size: 16px;
  font-weight: 700;
  color: var(--app-text-primary);
}
.modal-header-actions {
  display: flex;
  gap: 6px;
}

/* ── Modal Body ──────────────────────────── */
.modal-body {
  height: calc(85vh - 120px);
  overflow: hidden;
  border-radius: var(--app-radius-md, 8px);
}

/* ── Modal Footer ────────────────────────── */
.modal-footer-hint {
  font-size: 12px;
  color: var(--app-text-muted);
}

/* ── 导入区域 ────────────────────────────── */
.import-body {
  margin-top: 8px;
}
.import-hint {
  font-size: 13px;
  color: var(--app-text-muted);
  margin-bottom: 12px;
}
</style>
