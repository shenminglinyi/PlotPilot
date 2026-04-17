<template>
  <div class="detail-panel" v-if="!loading">
    <!-- 节点元信息 -->
    <div class="meta-section">
      <div class="meta-row">
        <n-tag :type="nodeDetail?.is_builtin ? 'info' : 'success'" size="small" :bordered="false">
          {{ nodeDetail?.is_builtin ? '内置' : '自定义' }}
        </n-tag>
        <n-tag v-if="nodeDetail?.output_format === 'json'" type="success" size="small" :bordered="false">JSON</n-tag>
        <span class="version-info">v{{ nodeDetail?.version_count || 0 }}</span>
      </div>
      <p class="desc-text">{{ nodeDetail?.description }}</p>
      <div class="source-line" v-if="nodeDetail?.source">
        <span class="source-icon">S</span>
        <code>{{ nodeDetail.source }}</code>
      </div>
    </div>

    <!-- Tabs: 详情 / 编辑 / 版本历史 -->
    <n-tabs type="line" animated size="small">

      <!-- ===== Tab 1: 详情展示 ===== -->
      <n-tab-pane name="detail" tab="详情">
        <!-- 变量列表 -->
        <div class="section-block" v-if="variables.length">
          <h4 class="section-title">模板变量</h4>
          <div class="var-table">
            <div class="var-row var-header">
              <span class="col-name">变量名</span>
              <span class="col-type">类型</span>
              <span class="col-desc">说明</span>
              <span class="col-req">必填</span>
            </div>
            <div class="var-row" v-for="v in variables" :key="v.name">
              <span class="col-name"><code>{{ '{' }}{{ v.name }}{{ '}' }}</code></span>
              <span class="col-type">{{ v.type }}</span>
              <span class="col-desc">{{ v.desc || '-' }}</span>
              <span class="col-req">
                <n-tag v-if="v.required" size="tiny" type="error" :bordered="false">必填</n-tag>
                <span v-else class="optional-text">可选</span>
              </span>
            </div>
          </div>
        </div>

        <!-- System 提示词 -->
        <div class="section-block">
          <h4 class="section-title section-title-system">System 提示词</h4>
          <pre class="code-block system-code">{{ nodeDetail?.system || '(空)' }}</pre>
        </div>

        <!-- User 模板 -->
        <div class="section-block">
          <h4 class="section-title section-title-user">User 模板</h4>
          <pre class="code-block user-code">{{ nodeDetail?.user_template || '(空)' }}</pre>
        </div>

        <!-- 标签 -->
        <div class="section-block" v-if="nodeDetail?.tags?.length">
          <h4 class="section-title">标签</h4>
          <div class="tags-list">
            <n-tag v-for="tag in nodeDetail.tags" :key="tag" :bordered="false">{{ tag }}</n-tag>
          </div>
        </div>

        <!-- 合约信息 -->
        <div class="section-block" v-if="nodeDetail?.contract_module">
          <h4 class="section-title">Pydantic 合约</h4>
          <code class="contract-code">{{ nodeDetail.contract_module }}:{{ nodeDetail.contract_model }}</code>
        </div>
      </n-tab-pane>

      <!-- ===== Tab 2: 编辑器 ===== -->
      <n-tab-pane name="edit" tab="编辑">
        <div class="tab-content edit-tab">
          <n-alert type="info" title="版本管理提示" :bordered="false" style="margin-bottom: 16px">
            每次保存将自动创建新版本，不会覆盖历史记录。可随时回滚。
          </n-alert>

          <n-form label-placement="top" size="small">
            <n-form-item label="变更摘要（选填）">
              <n-input
                v-model:value="editForm.change_summary"
                placeholder="描述这次修改的内容..."
                maxlength="100"
                show-count
              />
            </n-form-item>
            <n-form-item label="System 提示词">
              <n-input
                v-model:value="editForm.system"
                type="textarea"
                :rows="8"
                placeholder="编辑 System 角色提示词..."
              />
            </n-form-item>
            <n-form-item label="User 模板">
              <n-input
                v-model:value="editForm.user_template"
                type="textarea"
                :rows="5"
                placeholder="编辑 User 模板（支持 {variable}）..."
              />
            </n-form-item>
            <div class="edit-actions">
              <n-button type="primary" @click="handleSave" :loading="saving">保存为新版本</n-button>
              <n-button secondary @click="resetEditForm">重置</n-button>
            </div>
          </n-form>
        </div>
      </n-tab-pane>

      <!-- ===== Tab 3: 版本时间线 ===== -->
      <n-tab-pane name="versions" tab="版本历史 ({{ versions.length }})">
        <div class="tab-content versions-tab">
          <div class="timeline" v-if="versions.length">
            <div
              v-for="(ver, idx) in versions"
              :key="ver.id"
              class="timeline-item"
              :class="{ 'is-current': idx === 0, 'is-user': ver.created_by === 'user' }"
            >
              <div class="timeline-dot"></div>
              <div class="timeline-content">
                <div class="timeline-header">
                  <strong>v{{ ver.version_number }}</strong>
                  <n-tag :type="ver.created_by === 'user' ? 'warning' : 'default'" size="tiny" :bordered="false">
                    {{ ver.created_by === 'user' ? '用户修改' : '系统' }}
                  </n-tag>
                  <span class="timeline-time">{{ formatTime(ver.created_at) }}</span>
                </div>
                <p class="timeline-summary">{{ ver.change_summary || '无摘要' }}</p>
                <div class="timeline-preview">
                  <div class="preview-item">
                    <span class="preview-label">System:</span>
                    <span class="preview-text">{{ ver.system_preview.slice(0, 120) }}{{ ver.system_preview.length > 120 ? '...' : '' }}</span>
                  </div>
                </div>
                <div class="timeline-actions" v-if="idx > 0">
                  <n-button size="tiny" secondary type="warning" @click="handleRollback(ver)">回滚到此版本</n-button>
                  <n-button size="tiny" quaternary @click="showVersionDetail(ver)">查看完整内容</n-button>
                </div>
              </div>
            </div>
          </div>
          <n-empty v-else description="暂无版本历史" />
        </div>
      </n-tab-pane>

    </n-tabs>

    <!-- 版本详情弹窗 -->
    <n-modal
      v-model:show="showVerDetailModal"
      preset="card"
      :title="`v${selectedVersion?.version_number} 完整内容`"
      style="max-width: 640px"
    >
      <div v-if="selectedVersion" class="version-detail-modal">
        <div class="vd-section">
          <h5>System 提示词</h5>
          <pre class="code-block">{{ selectedVersionFull?.system_prompt || '加载中...' }}</pre>
        </div>
        <div class="vd-section">
          <h5>User 模板</h5>
          <pre class="code-block">{{ selectedVersionFull?.user_template || '加载中...' }}</pre>
        </div>
      </div>
    </n-modal>
  </div>

  <!-- 加载状态 -->
  <div v-else class="loading-wrap">
    <n-spin size="medium">加载中...</n-spin>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import {
  NTag, NTabs, NTabPane, NInput, NForm, NFormItem,
  NButton, NAlert, NEmpty, NModal, NSpin, useMessage,
} from 'naive-ui'
import {
  promptPlazaApi,
  type PromptNodeDetail,
  type PromptVersion,
  type PromptVariable,
  type PromptVersionDetail,
} from '../../../api/llmControl'

const props = defineProps<{
  nodeKey: string
}>()

const emit = defineEmits<{
  updated: []
  close: []
}>()

const message = useMessage()
const loading = ref(true)
const saving = ref(false)
const nodeDetail = ref<PromptNodeDetail | null>(null)
const versions = ref<PromptVersion[]>([])

// 编辑表单
const editForm = ref({
  change_summary: '',
  system: '',
  user_template: '',
})

// 版本详情弹窗
const showVerDetailModal = ref(false)
const selectedVersion = ref<PromptVersion | null>(null)
const selectedVersionFull = ref<PromptVersionDetail | null>(null)

// ---- 计算属性 ----

const variables = computed<PromptVariable[]>(() => nodeDetail.value?.variables || [])

// ---- 方法 ----

async function loadDetail() {
  loading.value = true
  try {
    const [detailRes, verRes] = await Promise.all([
      promptPlazaApi.getNodeDetail(props.nodeKey),
      promptPlazaApi.getNodeVersions(props.nodeKey),
    ])
    nodeDetail.value = detailRes as unknown as PromptNodeDetail
    versions.value = verRes as unknown as PromptVersion[]
    resetEditForm()
  } catch (e) {
    console.error('加载节点详情失败:', e)
    message.error('加载失败')
  } finally {
    loading.value = false
  }
}

function resetEditForm() {
  if (!nodeDetail.value) return
  editForm.value = {
    change_summary: '',
    system: nodeDetail.value.system || '',
    user_template: nodeDetail.value.user_template || '',
  }
}

async function handleSave() {
  if (!props.nodeKey) return
  saving.value = true
  try {
    const res = await promptPlazaApi.updateNode(props.nodeKey, {
      system: editForm.value.system,
      user_template: editForm.value.user_template,
      change_summary: editForm.value.change_summary || undefined,
    })
    message.success((res as any).message || '保存成功')
    emit('updated')
    await loadDetail()
  } catch (e: any) {
    message.error(e?.response?.data?.detail || '保存失败')
  } finally {
    saving.value = false
  }
}

async function handleRollback(ver: PromptVersion) {
  if (!props.nodeKey) return
  try {
    const res = await promptPlazaApi.rollbackNode(props.nodeKey, ver.id)
    message.success((res as any).message || `已回滚到 v${ver.version_number}`)
    emit('updated')
    await loadDetail()
  } catch (e: any) {
    message.error(e?.response?.data?.detail || '回滚失败')
  }
}

async function showVersionDetail(ver: PromptVersion) {
  selectedVersion.value = ver
  selectedVersionFull.value = null
  showVerDetailModal.value = true
  try {
    const res = await promptPlazaApi.getVersionDetail(ver.id)
    selectedVersionFull.value = res as unknown as PromptVersionDetail
  } catch (e) {
    console.error('加载版本详情失败:', e)
  }
}

function formatTime(timeStr: string): string {
  if (!timeStr) return ''
  try {
    const d = new Date(timeStr)
    return `${d.getMonth() + 1}/${d.getDate()} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
  } catch {
    return timeStr.slice(0, 16)
  }
}

// 监听 nodeKey 变化重新加载
watch(() => props.nodeKey, () => { loadDetail() })

onMounted(() => { loadDetail() })
</script>

<style scoped>
/* ═══════════════════════════════════════════════════
   详情面板 — 统一主题风格
   ═══════════════════════════════════════════════════ */
.detail-panel {
  display: flex;
  flex-direction: column;
  gap: 18px;
  padding: 6px 2px;
}

/* ---- 元信息 ---- */
.meta-section {
  padding: 14px 16px;
  background: var(--app-surface-subtle);
  border-radius: var(--app-radius-md);
  border: 1px solid var(--app-border);
}
.meta-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}
.version-info {
  font-size: 12px;
  color: var(--app-text-muted);
  margin-left: auto;
  font-weight: 500;
}
.desc-text {
  font-size: 13px;
  color: var(--app-text-secondary);
  line-height: 1.55;
  margin: 0 0 8px;
}
.source-line {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11.5px;
  color: var(--app-text-muted);
}
.source-icon {
  width: 17px;
  height: 17px;
  border-radius: 4px;
  background: var(--color-brand-light);
  color: var(--color-brand);
  font-size: 10px;
  font-weight: 700;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.source-line code {
  background: var(--app-surface-subtle);
  padding: 2px 7px;
  border-radius: 4px;
  font-size: 10.5px;
  font-family: var(--font-mono);
  border: 1px solid var(--app-border);
}

/* ---- 区块 ---- */
.section-block {
  margin-bottom: 20px;
}
.section-title {
  font-size: 13px;
  font-weight: 600;
  margin: 0 0 10px;
  color: var(--app-text-primary);
  letter-spacing: 0.01em;
  display: flex;
  align-items: center;
  gap: 6px;
}
.section-title::before {
  content: '';
  width: 3px;
  height: 14px;
  border-radius: 2px;
  background: var(--color-brand);
  flex-shrink: 0;
}
.section-title-system::before {
  background: #89b4fa;
}
.section-title-user::before {
  background: #a6e3a1;
}

/* ---- 变量表格 ---- */
.var-table {
  border: 1px solid var(--app-border);
  border-radius: var(--app-radius-sm);
  overflow: hidden;
}
.var-row {
  display: grid;
  grid-template-columns: 140px 70px 1fr 50px;
  align-items: center;
  padding: 8px 12px;
  font-size: 12px;
  border-bottom: 1px solid var(--app-border);
  transition: background 0.15s ease;
}
.var-row:hover:not(.var-header) {
  background: var(--color-brand-light);
}
.var-row:last-child {
  border-bottom: none;
}
.var-header {
  background: var(--app-surface-subtle);
  font-weight: 600;
  font-size: 11px;
  color: var(--app-text-muted);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}
.col-name code {
  font-size: 11.5px;
  background: linear-gradient(135deg, rgba(79, 70, 229, 0.08), rgba(139, 92, 246, 0.06));
  padding: 2px 6px;
  border-radius: 4px;
  color: var(--color-brand);
  font-family: var(--font-mono);
  border: 1px solid var(--color-brand-border);
}
.col-type {
  color: var(--app-text-muted);
  font-family: var(--font-mono);
  font-size: 11.5px;
}
.col-desc {
  color: var(--app-text-secondary);
  font-size: 12.5px;
}
.optional-text {
  font-size: 11.5px;
  color: var(--app-text-muted);
  opacity: 0.65;
}

/* ---- 代码块（暗色终端风格）---- */
.code-block {
  background: #1a1b26;
  color: #a9b1d6;
  padding: 16px 18px;
  border-radius: var(--app-radius-md);
  font-size: 12.5px;
  line-height: 1.68;
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 380px;
  overflow-y: auto;
  font-family: var(--font-mono);
  margin: 0;
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.03),
    0 2px 8px rgba(0, 0, 0, 0.15);
}
.code-block::-webkit-scrollbar {
  width: 5px;
}
.code-block::-webkit-scrollbar-thumb {
  background: rgba(122, 130, 160, 0.35);
  border-radius: 3px;
}
.system-code {
  border-left: 3px solid #7aa2f7;
}
.user-code {
  border-left: 3px solid #9ece6a;
}

/* ---- 标签 ---- */
.tags-list {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
}

/* ---- 合约 ---- */
.contract-code {
  background: var(--color-gold-dim);
  color: var(--color-gold);
  padding: 5px 12px;
  border-radius: var(--app-radius-sm);
  font-size: 12px;
  font-family: var(--font-mono);
  display: inline-block;
  border: 1px solid var(--color-gold-border);
}

/* ---- 编辑器 ---- */
.edit-actions {
  display: flex;
  gap: 8px;
  margin-top: 18px;
}

/* ---- 时间线 ---- */
.timeline {
  position: relative;
  padding-left: 26px;
}
.timeline::before {
  content: '';
  position: absolute;
  left: 8px;
  top: 10px;
  bottom: 10px;
  width: 2px;
  background: var(--app-border-strong);
  border-radius: 1px;
}
.timeline-item {
  position: relative;
  padding-bottom: 22px;
}
.timeline-dot {
  position: absolute;
  left: -23px;
  top: 5px;
  width: 12px;
  height: 12px;
  border-radius: 50%;
  background: var(--app-surface);
  border: 2px solid var(--app-border-strong);
  box-shadow: 0 0 0 3px var(--app-surface-subtle);
  z-index: 1;
  transition: all 0.25s ease;
}
.timeline-item.is-current .timeline-dot {
  background: var(--color-brand);
  border-color: var(--color-brand);
  box-shadow: 0 0 0 4px var(--color-brand-light), 0 0 12px var(--color-brand-light);
}
.timeline-item.is-user .timeline-dot {
  background: var(--color-warning);
  border-color: var(--color-warning);
  box-shadow: 0 0 0 4px var(--color-warning-light), 0 0 12px var(--color-warning-light);
}
.timeline-content {
  background: var(--app-surface-subtle);
  border-radius: var(--app-radius-md);
  padding: 14px 16px;
  border: 1px solid var(--app-border);
  transition: all 0.2s ease;
}
.timeline-content:hover {
  border-color: var(--app-border-strong);
  box-shadow: var(--app-shadow-sm);
}
.timeline-item.is-current .timeline-content {
  border-color: var(--color-brand);
  background: linear-gradient(135deg, var(--color-brand-light), transparent 60%);
}
.timeline-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}
.timeline-header strong {
  font-size: 13.5px;
  color: var(--app-text-primary);
}
.timeline-time {
  font-size: 11.5px;
  color: var(--app-text-muted);
  margin-left: auto;
}
.timeline-summary {
  font-size: 12.5px;
  color: var(--app-text-secondary);
  margin: 0 0 10px;
  line-height: 1.45;
}
.timeline-preview {
  background: var(--app-surface);
  border-radius: var(--app-radius-sm);
  padding: 10px 12px;
  margin-bottom: 10px;
  border: 1px solid var(--app-border);
}
.preview-item {
  display: flex;
  gap: 8px;
  font-size: 11.5px;
}
.preview-label {
  color: var(--app-text-muted);
  white-space: nowrap;
  font-weight: 600;
  text-transform: uppercase;
  font-size: 10.5px;
  letter-spacing: 0.05em;
}
.preview-text {
  color: var(--app-text-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.timeline-actions {
  display: flex;
  gap: 6px;
}

/* ---- 版本详情弹窗 ---- */
.version-detail-modal .vd-section {
  margin-bottom: 16px;
}
.version-detail-modal h5 {
  font-size: 13px;
  font-weight: 600;
  margin: 0 0 8px;
  color: var(--app-text-primary);
}

/* ---- 加载 ---- */
.loading-wrap {
  display: flex;
  justify-content: center;
  align-items: center;
  padding: 48px 20px;
}
</style>
