<template>
  <div class="detail-panel" v-if="!loading">
    <!-- 节点元信息 -->
    <div class="meta-section">
      <div class="meta-row">
        <n-tag :type="nodeDetail?.is_builtin ? 'info' : 'success'" size="small" :bordered="false">
          {{ nodeDetail?.is_builtin ? '内置内核' : '自定义扩展' }}
        </n-tag>
        <n-tag v-if="nodeDetail?.output_format === 'json'" type="success" size="small" :bordered="false">
          结构化 JSON 输出
        </n-tag>
        <span class="version-info numeric">共 {{ nodeDetail?.version_count || 0 }} 个快照版本</span>
      </div>
      <p class="desc-text">{{ nodeDetail?.description || '（无描述）' }}</p>
      <p class="meta-tip">
        直接修改下方提示词并点「保存为新版本」即可生效；原版自动保存在「版本历史」中，随时可一键回滚。
      </p>
    </div>

    <!-- Tabs: 编辑内容（默认） / 版本历史（修复静态插值 bug） -->
    <n-tabs
      v-model:value="activeTab"
      type="segment"
      animated
      size="medium"
      class="detail-tabs"
    >
      <n-tab-pane name="content" tab="编辑提示词">
        <div class="tab-content edit-tab">
          <n-form label-placement="top" size="small" class="edit-form">
            <n-form-item>
              <template #label>
                <span class="form-label-with-hint">
                  System 角色与规则提示词
                  <span class="label-hint">控制文风、审稿标准或生成协议的核心指令</span>
                </span>
              </template>
              <n-input
                v-model:value="editForm.system"
                type="textarea"
                :autosize="{ minRows: 10, maxRows: 24 }"
                placeholder="在此直接编辑 System 内容…"
                class="mono-input"
              />
            </n-form-item>

            <n-form-item>
              <template #label>
                <span class="form-label-with-hint">
                  User 上下文组装模板
                  <span class="label-hint">使用半角花括号引用上下文槽位（建议保持原有变量名不变）</span>
                </span>
              </template>
              <n-input
                v-model:value="editForm.user_template"
                type="textarea"
                :autosize="{ minRows: 5, maxRows: 16 }"
                placeholder="在此编辑 User 模板…"
                class="mono-input"
              />
            </n-form-item>

            <n-form-item label="本次修改备注（选填，便于在快照历史中识别）">
              <n-input
                v-model:value="editForm.change_summary"
                placeholder="例如：压低环境排比密度、增强人物对话潜台词…"
                maxlength="100"
                show-count
              />
            </n-form-item>
          </n-form>

          <!-- 可折叠的技术参考区：不再霸占首屏 -->
          <details v-if="variables.length || nodeDetail?.contract_module || nodeDetail?.source" class="tech-drawer">
            <summary class="tech-summary">
              查看引擎输入变量参考（{{ variables.length }} 项）与调用链技术信息
            </summary>
            <div class="tech-drawer-body">
              <div class="var-table" v-if="variables.length">
                <div class="var-row var-header">
                  <span class="col-name">槽位名</span>
                  <span class="col-type">类型</span>
                  <span class="col-desc">注入内容说明</span>
                  <span class="col-req">约束</span>
                </div>
                <div class="var-row" v-for="v in variables" :key="v.name">
                  <span class="col-name"><code>{{ '{' + v.name + '}' }}</code></span>
                  <span class="col-type">{{ v.type }}</span>
                  <span class="col-desc">{{ v.desc || '-' }}</span>
                  <span class="col-req">
                    <n-tag v-if="v.required" size="tiny" type="error" :bordered="false">必填</n-tag>
                    <span v-else class="optional-text">可选</span>
                  </span>
                </div>
              </div>

              <div class="tech-meta-list">
                <div v-if="nodeDetail?.source" class="source-line">
                  <span class="tech-meta-key">源码绑定：</span>
                  <code>{{ nodeDetail.source }}</code>
                </div>
                <div v-if="nodeDetail?.contract_module" class="source-line">
                  <span class="tech-meta-key">输出契约：</span>
                  <code>{{ nodeDetail.contract_module }}:{{ nodeDetail.contract_model }}</code>
                </div>
                <div v-if="dagBindingLabels.length" class="dag-linkage">
                  <span class="tech-meta-key">工作流挂载：</span>
                  <n-tag
                    v-for="item in dagBindingLabels"
                    :key="item"
                    size="tiny"
                    type="success"
                    :bordered="false"
                  >
                    {{ item }}
                  </n-tag>
                </div>
              </div>
            </div>
          </details>

          <div class="edit-sticky-bar">
            <div class="edit-sticky-hint">
              保存后立即对后续生成的章节生效。
            </div>
            <div class="edit-sticky-actions">
              <n-button secondary @click="resetEditForm">放弃未存改动</n-button>
              <n-button type="primary" @click="handleSave" :loading="saving">
                保存为新版本
              </n-button>
            </div>
          </div>
        </div>
      </n-tab-pane>

      <n-tab-pane name="versions" :tab="`版本历史 (${versions.length})`">
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
                  <strong class="numeric">v{{ ver.version_number }}</strong>
                  <n-tag :type="ver.created_by === 'user' ? 'warning' : 'default'" size="tiny" :bordered="false">
                    {{ ver.created_by === 'user' ? '自定义快照' : '出厂默认' }}
                  </n-tag>
                  <span v-if="idx === 0" class="current-pill">当前生效</span>
                  <span class="timeline-time numeric">{{ formatTime(ver.created_at) }}</span>
                </div>
                <p class="timeline-summary">{{ ver.change_summary || '初始快照' }}</p>
                <div class="timeline-preview">
                  <div class="preview-item">
                    <span class="preview-label">System 摘要</span>
                    <span class="preview-text">
                      {{ ver.system_preview.slice(0, 120) }}{{ ver.system_preview.length > 120 ? '…' : '' }}
                    </span>
                  </div>
                </div>
                <div class="timeline-actions">
                  <n-button v-if="idx > 0" size="tiny" secondary type="warning" @click="handleRollback(ver)">
                    回滚到此版本
                  </n-button>
                  <n-button size="tiny" quaternary @click="showVersionDetail(ver)">
                    查看完整快照
                  </n-button>
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
      style="max-width: 680px"
    >
      <div v-if="selectedVersion" class="version-detail-modal">
        <div class="vd-section">
          <h5>System 提示词</h5>
          <pre class="code-block">{{ selectedVersionFull?.system_prompt || '加载中…' }}</pre>
        </div>
        <div class="vd-section">
          <h5>User 模板</h5>
          <pre class="code-block">{{ selectedVersionFull?.user_template || '加载中…' }}</pre>
        </div>
      </div>
    </n-modal>
  </div>

  <div v-else class="loading-wrap">
    <n-spin size="medium">加载节点详情…</n-spin>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import {
  NTag, NTabs, NTabPane, NInput, NForm, NFormItem,
  NButton, NEmpty, NModal, NSpin, useMessage,
} from 'naive-ui'
import {
  promptPlazaApi,
  type PromptNodeDetail,
  type PromptVersion,
  type PromptVariable,
  type PromptVersionDetail,
} from '../../../api/llmControl'
import { formatApiError } from '../../../utils/apiError'

const props = defineProps<{
  nodeKey: string
}>()

const emit = defineEmits<{
  updated: []
  close: []
}>()

const message = useMessage()
const activeTab = ref<'content' | 'versions'>('content')
const loading = ref(true)
const saving = ref(false)
const nodeDetail = ref<PromptNodeDetail | null>(null)
const versions = ref<PromptVersion[]>([])

const editForm = ref({
  change_summary: '',
  system: '',
  user_template: '',
})

const showVerDetailModal = ref(false)
const selectedVersion = ref<PromptVersion | null>(null)
const selectedVersionFull = ref<PromptVersionDetail | null>(null)

const variables = computed<PromptVariable[]>(() => nodeDetail.value?.variables || [])
const dagBindingLabels = computed(() => {
  const canvas = nodeDetail.value?.dag_bindings || []
  if (canvas.length) {
    return canvas.map(b => `${b.node_id} · ${b.prompt_mode || 'cpms'}`)
  }
  return (nodeDetail.value?.dag_registry_bindings || []).map(b => `${b.node_type} · ${b.prompt_mode || 'cpms'}`)
})

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
    message.success((res as { message?: string }).message || '保存成功')
    emit('updated')
    await loadDetail()
  } catch (e: unknown) {
    message.error(formatApiError(e, '保存失败'))
  } finally {
    saving.value = false
  }
}

async function handleRollback(ver: PromptVersion) {
  if (!props.nodeKey) return
  try {
    const res = await promptPlazaApi.rollbackNode(props.nodeKey, ver.id)
    message.success((res as { message?: string }).message || `已回滚到 v${ver.version_number}`)
    emit('updated')
    await loadDetail()
  } catch (e: unknown) {
    message.error(formatApiError(e, '回滚失败'))
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

watch(() => props.nodeKey, () => {
  activeTab.value = 'content'
  loadDetail()
})

onMounted(() => { loadDetail() })
</script>

<style scoped>
.detail-panel {
  display: flex;
  flex-direction: column;
  gap: 14px;
  padding: 6px 2px;
}

.numeric {
  font-variant-numeric: tabular-nums;
}

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
  font-size: 12.5px;
  color: var(--app-text-muted);
  margin-left: auto;
  font-weight: 500;
}

.desc-text {
  font-size: 14px;
  color: var(--app-text-primary);
  line-height: 1.6;
  margin: 0 0 8px;
  max-width: 62ch;
}

.meta-tip {
  margin: 0;
  font-size: 12.5px;
  line-height: 1.55;
  color: var(--app-text-muted);
}

.detail-tabs {
  margin-top: 2px;
}

.edit-form {
  padding-bottom: 4px;
}

.form-label-with-hint {
  display: inline-flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 8px;
  font-weight: 600;
}

.label-hint {
  font-size: 12px;
  font-weight: 400;
  color: var(--app-text-muted);
}

.mono-input :deep(textarea) {
  font-family: var(--font-mono);
  font-size: 13px;
  line-height: 1.6;
}

.tech-drawer {
  margin-top: 8px;
  border: 1px solid var(--app-border);
  border-radius: var(--app-radius-md);
  background: var(--app-surface-subtle);
  padding: 10px 14px;
}

.tech-summary {
  font-size: 13px;
  font-weight: 600;
  color: var(--app-text-secondary);
  cursor: pointer;
  user-select: none;
}

.tech-drawer-body {
  margin-top: 12px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.var-table {
  border: 1px solid var(--app-border);
  border-radius: var(--app-radius-sm);
  background: var(--app-surface);
  overflow: hidden;
}

.var-row {
  display: grid;
  grid-template-columns: 150px 70px 1fr 56px;
  align-items: center;
  padding: 8px 12px;
  font-size: 12.5px;
  border-bottom: 1px solid var(--app-border);
}

.var-row:last-child {
  border-bottom: none;
}

.var-header {
  background: var(--app-surface-subtle);
  font-weight: 600;
  font-size: 12px;
  color: var(--app-text-muted);
}

.col-name code {
  font-size: 12px;
  background: var(--app-surface-subtle);
  padding: 2px 6px;
  border-radius: 4px;
  color: var(--color-brand);
  font-family: var(--font-mono);
  border: 1px solid var(--app-border);
}

.col-type {
  color: var(--app-text-muted);
  font-family: var(--font-mono);
  font-size: 12px;
}

.col-desc {
  color: var(--app-text-secondary);
}

.optional-text {
  font-size: 12px;
  color: var(--app-text-muted);
}

.tech-meta-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
  font-size: 12px;
  color: var(--app-text-muted);
}

.source-line,
.dag-linkage {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
}

.tech-meta-key {
  font-weight: 600;
  color: var(--app-text-secondary);
}

.source-line code {
  background: var(--app-surface);
  padding: 2px 7px;
  border-radius: 4px;
  font-size: 11.5px;
  font-family: var(--font-mono);
  border: 1px solid var(--app-border);
}

.edit-sticky-bar {
  position: sticky;
  bottom: 0;
  z-index: 3;
  margin-top: 16px;
  padding: 12px 14px;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  background: var(--app-surface);
  border: 1px solid var(--app-border-strong);
  border-radius: var(--app-radius-md);
}

.edit-sticky-hint {
  font-size: 12.5px;
  color: var(--app-text-muted);
}

.edit-sticky-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-left: auto;
}

.code-block {
  background: var(--app-surface-subtle);
  color: var(--app-text-primary);
  padding: 14px 16px;
  border-radius: var(--app-radius-md);
  font-size: 12.5px;
  line-height: 1.65;
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 360px;
  overflow-y: auto;
  font-family: var(--font-mono);
  margin: 0;
  border: 1px solid var(--app-border);
}

.timeline {
  position: relative;
  padding-left: 24px;
}

.timeline::before {
  content: '';
  position: absolute;
  left: 7px;
  top: 10px;
  bottom: 10px;
  width: 2px;
  background: var(--app-border-strong);
}

.timeline-item {
  position: relative;
  padding-bottom: 18px;
}

.timeline-dot {
  position: absolute;
  left: -22px;
  top: 6px;
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: var(--app-surface);
  border: 2px solid var(--app-border-strong);
  z-index: 1;
}

.timeline-item.is-current .timeline-dot {
  background: var(--color-brand);
  border-color: var(--color-brand);
}

.timeline-item.is-user .timeline-dot {
  background: var(--color-warning);
  border-color: var(--color-warning);
}

.timeline-content {
  background: var(--app-surface-subtle);
  border-radius: var(--app-radius-md);
  padding: 14px 16px;
  border: 1px solid var(--app-border);
}

.timeline-item.is-current .timeline-content {
  border-color: var(--color-brand);
  background: var(--app-surface);
}

.timeline-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}

.current-pill {
  font-size: 11px;
  font-weight: 600;
  padding: 1px 7px;
  border-radius: 999px;
  background: var(--color-brand-light);
  color: var(--color-brand);
}

.timeline-time {
  font-size: 12px;
  color: var(--app-text-muted);
  margin-left: auto;
}

.timeline-summary {
  font-size: 13px;
  color: var(--app-text-secondary);
  margin: 0 0 10px;
  line-height: 1.5;
}

.timeline-preview {
  background: var(--app-surface);
  border-radius: var(--app-radius-sm);
  padding: 9px 12px;
  margin-bottom: 10px;
  border: 1px solid var(--app-border);
}

.preview-item {
  display: flex;
  gap: 8px;
  font-size: 12px;
}

.preview-label {
  color: var(--app-text-muted);
  white-space: nowrap;
  font-weight: 600;
}

.preview-text {
  color: var(--app-text-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.timeline-actions {
  display: flex;
  gap: 8px;
}

.version-detail-modal .vd-section {
  margin-bottom: 16px;
}

.version-detail-modal h5 {
  font-size: 13.5px;
  font-weight: 600;
  margin: 0 0 8px;
  color: var(--app-text-primary);
}

.loading-wrap {
  display: flex;
  justify-content: center;
  align-items: center;
  padding: 48px 20px;
}
</style>
