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
          <span v-if="appearance !== 'sidebar'" class="plaza-subtitle">
            浏览 · 编辑 · 版本管理
          </span>
        </span>
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
const plazaRef = ref()

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
    const res = await (await fetch('/api/v1/llm-control/prompts/export')).json()
    const blob = new Blob([JSON.stringify(res, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `prompts-backup-${new Date().toISOString().slice(0, 10)}.json`
    a.click()
    URL.revokeObjectURL(url)
    message.success('导出成功')
  } catch (e: any) {
    message.error(e?.message || '导出失败')
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
    const data = JSON.parse(importFileContent.value)
    await fetch('/api/v1/llm-control/prompts/import', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    })
    message.success('导入成功')
    showImportModal.value = false
    loadStats()
    plazaRef.value?.$forceUpdate?.()
    return true
  } catch (e: any) {
    message.error(e?.message || '导入失败，请检查 JSON 格式')
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
}

.plaza-main.variant-sidebar {
  width: 100%;
  min-height: 0;
  padding: 14px 12px;
  border-radius: 12px;
  box-shadow: var(--app-shadow-sm), 0 1px 3px rgba(0, 0, 0, 0.05);
}

.plaza-main:hover {
  transform: translateY(-1px);
  border-color: var(--color-plaza-border);
  box-shadow: var(--app-shadow-lg), 0 14px 32px var(--color-plaza-border, rgba(5, 150, 105, 0.28));
}

.plaza-main.variant-sidebar:hover {
  box-shadow: var(--app-shadow-sm), 0 2px 8px var(--color-plaza-border, rgba(5, 150, 105, 0.18));
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
  flex-direction: column; 
  gap: 6px; 
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
  font-size: 12px; 
}

.plaza-count {
  font-size: 10.5px;
  font-weight: 600;
  background: var(--app-text-inverse, rgba(255, 255, 255, 0.2));
  color: var(--app-text-inverse, #fff);
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
  color: white;
  font-size: 13px;
  font-weight: 800;
  letter-spacing: -0.01em;
}
.modal-header-title {
  font-size: 16px;
  font-weight: 700;
  color: var(--n-text-color-1, #333);
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
  color: var(--n-text-color-3, #999);
}

/* ── 导入区域 ────────────────────────────── */
.import-body {
  margin-top: 8px;
}
.import-hint {
  font-size: 13px;
  color: var(--n-text-color-3, #999);
  margin-bottom: 12px;
}
</style>
