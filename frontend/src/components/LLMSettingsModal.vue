<template>
  <n-modal
    v-model:show="show"
    preset="card"
    title="配置管理"
    style="width: min(720px, 96vw)"
    :mask-closable="false"
    :segmented="{ content: true, footer: 'soft' }"
  >
    <n-tabs type="line" animated>
      <!-- ═══ Tab 1: LLM 模型 ═══ -->
      <n-tab-pane name="llm" tab="LLM 模型">
        <!-- Config List -->
        <div v-if="!editing" class="config-section">
          <div class="config-toolbar">
            <span class="config-count">{{ configs.length }} 个配置</span>
            <n-button type="primary" size="small" @click="startCreate">
              <template #icon><n-icon><IconAdd /></n-icon></template>
              添加配置
            </n-button>
          </div>

          <div v-if="listLoading" class="config-loading">
            <n-spin size="medium" />
          </div>

          <div v-else-if="configs.length === 0" class="config-empty">
            <p>尚未添加任何 LLM 配置</p>
            <n-button type="primary" @click="startCreate">添加第一个配置</n-button>
          </div>

          <div v-else class="config-list">
            <div
              v-for="cfg in configs"
              :key="cfg.id"
              class="config-card"
              :class="{ active: cfg.id === activeId }"
            >
              <div class="config-info">
                <div class="config-name">
                  {{ cfg.name }}
                  <n-tag
                    size="small"
                    round
                    :type="cfg.provider === 'openai' ? 'success' : 'info'"
                  >
                    {{ cfg.provider === 'openai' ? 'OpenAI' : 'Anthropic' }}
                  </n-tag>
                  <n-tag v-if="cfg.id === activeId" size="small" round type="warning">
                    激活
                  </n-tag>
                </div>
                <div class="config-detail">
                  <span v-if="cfg.model" class="detail-item">{{ cfg.model }}</span>
                  <span v-if="cfg.base_url" class="detail-item">{{ truncateUrl(cfg.base_url) }}</span>
                  <span class="detail-item key-mask">{{ maskKey(cfg.api_key) }}</span>
                </div>
              </div>
              <div class="config-actions">
                <n-button
                  v-if="cfg.id !== activeId"
                  size="small"
                  type="success"
                  secondary
                  @click="handleActivate(cfg.id)"
                  :loading="activatingId === cfg.id"
                >
                  激活
                </n-button>
                <n-button size="small" quaternary @click="startEdit(cfg)">编辑</n-button>
                <n-popconfirm @positive-click="handleDelete(cfg.id)">
                  <template #trigger>
                    <n-button size="small" quaternary type="error" :loading="deletingId === cfg.id">删除</n-button>
                  </template>
                  确定删除「{{ cfg.name }}」？
                </n-popconfirm>
              </div>
            </div>
          </div>
        </div>

        <!-- Add / Edit Form -->
        <div v-else class="form-section">
          <h3 class="form-title">{{ editingId ? '编辑配置' : '新建配置' }}</h3>

          <n-form ref="formRef" :model="form" label-placement="left" label-width="80">
            <n-form-item label="名称" path="name">
              <n-input v-model:value="form.name" placeholder="如：ARK Qwen、Anthropic Claude" />
            </n-form-item>

            <n-form-item label="提供商" path="provider">
              <n-select
                v-model:value="form.provider"
                :options="providerOptions"
                @update:value="onProviderChange"
              />
            </n-form-item>

            <n-form-item label="API Key" path="api_key">
              <n-input
                v-model:value="form.api_key"
                type="password"
                show-password-on="click"
                placeholder="sk-..."
              />
            </n-form-item>

            <n-form-item label="Base URL" path="base_url">
              <n-input
                v-model:value="form.base_url"
                :placeholder="form.provider === 'anthropic' ? 'https://api.anthropic.com' : 'https://api.openai.com/v1'"
              />
            </n-form-item>

            <n-form-item label="默认模型" path="model">
              <div class="model-row">
                <n-select
                  v-model:value="form.model"
                  filterable
                  tag
                  :options="modelOptions"
                  placeholder="选择或输入模型名称"
                  style="flex: 1"
                />
                <n-button
                  size="small"
                  :loading="fetchingModels"
                  :disabled="!form.api_key || !form.base_url"
                  @click="handleFetchModels"
                >
                  获取列表
                </n-button>
              </div>
            </n-form-item>

            <n-form-item label="写作模型" path="writing_model">
              <n-select
                v-model:value="form.writing_model"
                filterable
                tag
                :options="modelOptions"
                placeholder="留空则使用默认模型"
              />
            </n-form-item>

            <n-form-item label="系统模型" path="system_model">
              <n-select
                v-model:value="form.system_model"
                filterable
                tag
                :options="modelOptions"
                placeholder="留空则使用默认模型（审稿/分析等轻量任务）"
              />
            </n-form-item>
          </n-form>

          <n-space justify="end">
            <n-button @click="editing = false">取消</n-button>
            <n-button
              type="primary"
              :loading="saving"
              :disabled="!form.name.trim() || !form.api_key.trim()"
              @click="handleSave"
            >
              保存
            </n-button>
          </n-space>
        </div>
      </n-tab-pane>

      <!-- ═══ Tab 2: 嵌入模型 ═══ -->
      <n-tab-pane name="embedding" tab="嵌入模型">
        <div class="embedding-section">
          <n-alert type="warning" style="margin-bottom: 16px" :bordered="false">
            每本书的向量索引与嵌入模型绑定，一旦开始写作后切换模型将导致已有索引不可用。
            如需更换，请先删除对应书籍的向量数据（data/chromadb/）再重新生成。
          </n-alert>

          <div v-if="embeddingLoading" class="config-loading">
            <n-spin size="medium" />
          </div>

          <template v-else>
            <div class="embedding-mode-switch">
              <span class="mode-label" :class="{ active: embeddingForm.mode === 'local' }">本地模型</span>
              <n-switch
                :value="embeddingForm.mode === 'openai'"
                @update:value="embeddingForm.mode = $event ? 'openai' : 'local'"
              />
              <span class="mode-label" :class="{ active: embeddingForm.mode === 'openai' }">云端模型</span>
            </div>

            <!-- Local mode -->
            <div v-if="embeddingForm.mode === 'local'" class="embedding-local-info">
              <div class="local-model-card">
                <div class="local-model-name">BAAI/bge-small-zh-v1.5</div>
                <div class="local-model-desc">本地中文嵌入模型，无需网络连接</div>
              </div>

              <n-form label-placement="left" label-width="100" style="margin-top: 16px">
                <n-form-item label="模型路径">
                  <n-input v-model:value="embeddingForm.model_path" placeholder="BAAI/bge-small-zh-v1.5" />
                </n-form-item>
                <n-form-item label="GPU 加速">
                  <n-switch v-model:value="embeddingForm.use_gpu" />
                </n-form-item>
              </n-form>
            </div>

            <!-- Cloud mode -->
            <div v-else class="embedding-cloud-form">
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

            <n-space justify="end" style="margin-top: 16px">
              <n-button
                type="primary"
                :loading="embeddingSaving"
                @click="handleSaveEmbedding"
              >
                保存
              </n-button>
            </n-space>
          </template>
        </div>
      </n-tab-pane>
    </n-tabs>
  </n-modal>
</template>

<script setup lang="ts">
import { h, ref, watch } from 'vue'
import { useMessage } from 'naive-ui'
import { settingsApi, type LLMConfigProfile, type EmbeddingConfig } from '@/api/settings'

const show = defineModel<boolean>('show', { default: false })
const message = useMessage()

const IconAdd = () =>
  h('svg', { xmlns: 'http://www.w3.org/2000/svg', viewBox: '0 0 24 24', width: '1em', height: '1em' },
    h('path', { fill: 'currentColor', d: 'M19 13h-6v6h-2v-6H5v-2h6V5h2v6h6v2z' }))

// ── LLM list state ─────────────────────────────────────────
const configs = ref<LLMConfigProfile[]>([])
const activeId = ref<string | null>(null)
const listLoading = ref(false)
const activatingId = ref<string | null>(null)
const deletingId = ref<string | null>(null)

async function loadConfigs() {
  listLoading.value = true
  try {
    const store = await settingsApi.listLLMConfigs()
    configs.value = store.configs
    activeId.value = store.active_id
  } catch {
    message.error('加载配置失败')
  } finally {
    listLoading.value = false
  }
}

// ── LLM form state ─────────────────────────────────────────
const editing = ref(false)
const editingId = ref<string | null>(null)
const saving = ref(false)
const fetchingModels = ref(false)
const modelOptions = ref<Array<{ label: string; value: string }>>([])

const form = ref({
  name: '',
  provider: 'openai' as 'openai' | 'anthropic',
  api_key: '',
  base_url: '',
  model: '',
  system_model: '',
  writing_model: '',
})

const providerOptions = [
  { label: 'OpenAI Compatible', value: 'openai' },
  { label: 'Anthropic', value: 'anthropic' },
]

function startCreate() {
  editingId.value = null
  form.value = { name: '', provider: 'openai', api_key: '', base_url: '', model: '', system_model: '', writing_model: '' }
  modelOptions.value = []
  editing.value = true
}

function startEdit(cfg: LLMConfigProfile) {
  editingId.value = cfg.id
  form.value = {
    name: cfg.name,
    provider: cfg.provider,
    api_key: cfg.api_key,
    base_url: cfg.base_url,
    model: cfg.model,
    system_model: cfg.system_model || '',
    writing_model: cfg.writing_model || '',
  }
  modelOptions.value = cfg.model ? [{ label: cfg.model, value: cfg.model }] : []
  editing.value = true
}

function onProviderChange() {
  modelOptions.value = []
  form.value.model = ''
}

// ── LLM actions ────────────────────────────────────────────

async function handleSave() {
  saving.value = true
  try {
    if (editingId.value) {
      await settingsApi.updateLLMConfig(editingId.value, { ...form.value })
      message.success('配置已更新')
    } else {
      await settingsApi.createLLMConfig({ ...form.value })
      message.success('配置已创建')
    }
    editing.value = false
    await loadConfigs()
  } catch {
    message.error('保存失败')
  } finally {
    saving.value = false
  }
}

async function handleActivate(id: string) {
  activatingId.value = id
  try {
    await settingsApi.activateLLMConfig(id)
    activeId.value = id
    message.success('配置已激活，立即生效')
  } catch {
    message.error('激活失败')
  } finally {
    activatingId.value = null
  }
}

async function handleDelete(id: string) {
  deletingId.value = id
  try {
    await settingsApi.deleteLLMConfig(id)
    message.success('配置已删除')
    await loadConfigs()
  } catch {
    message.error('删除失败')
  } finally {
    deletingId.value = null
  }
}

async function handleFetchModels() {
  fetchingModels.value = true
  try {
    const models = await settingsApi.fetchModels({
      provider: form.value.provider,
      api_key: form.value.api_key,
      base_url: form.value.base_url,
    })
    modelOptions.value = models.map((m: string) => ({ label: m, value: m }))
    if (models.length > 0) {
      message.success(`获取到 ${models.length} 个模型`)
    } else {
      message.warning('未获取到模型列表')
    }
  } catch {
    message.error('获取模型列表失败，请检查 API Key 和 Base URL')
  } finally {
    fetchingModels.value = false
  }
}

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
    message.error('加载嵌入模型配置失败')
  } finally {
    embeddingLoading.value = false
  }
}

async function handleSaveEmbedding() {
  embeddingSaving.value = true
  try {
    const result = await settingsApi.updateEmbeddingConfig({ ...embeddingForm.value })
    embeddingForm.value = result
    message.success('嵌入模型配置已保存，立即生效')
  } catch {
    message.error('保存失败')
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
    if (models.length > 0) {
      message.success(`获取到 ${models.length} 个模型`)
    } else {
      message.warning('未获取到模型列表')
    }
  } catch {
    message.error('获取模型列表失败，请检查 API Key 和 Base URL')
  } finally {
    fetchingEmbeddingModels.value = false
  }
}

// ── modal open ─────────────────────────────────────────────

watch(show, (v) => {
  if (v) {
    editing.value = false
    loadConfigs()
    loadEmbeddingConfig()
  }
})

// ── helpers ────────────────────────────────────────────────

function maskKey(key: string): string {
  if (!key) return ''
  if (key.length <= 8) return '****'
  return key.slice(0, 3) + '...' + key.slice(-4)
}

function truncateUrl(url: string): string {
  if (url.length <= 35) return url
  return url.slice(0, 32) + '...'
}
</script>

<style scoped>
.config-section {
  min-height: 200px;
}

.config-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

.config-count {
  font-size: 13px;
  color: #64748b;
}

.config-loading {
  display: flex;
  justify-content: center;
  padding: 40px;
}

.config-empty {
  text-align: center;
  padding: 40px 20px;
  color: #64748b;
}

.config-empty p {
  margin-bottom: 12px;
}

.config-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.config-card {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 14px 16px;
  background: #f8fafc;
  border-radius: 10px;
  border: 1.5px solid transparent;
  transition: all 0.15s ease;
}

.config-card.active {
  border-color: #4f46e5;
  background: rgba(79, 70, 229, 0.04);
}

.config-card:hover {
  background: #f1f5f9;
}

.config-info {
  flex: 1;
  min-width: 0;
}

.config-name {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 600;
  font-size: 14px;
  color: #1e293b;
  margin-bottom: 4px;
}

.config-detail {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}

.detail-item {
  font-size: 12px;
  color: #94a3b8;
}

.key-mask {
  font-family: 'JetBrains Mono', monospace;
}

.config-actions {
  display: flex;
  gap: 4px;
  flex-shrink: 0;
  margin-left: 12px;
}

.form-section {
  min-height: 200px;
}

.form-title {
  margin: 0 0 20px;
  font-size: 16px;
  font-weight: 600;
  color: #1e293b;
}

.model-row {
  display: flex;
  gap: 8px;
  width: 100%;
}

/* ── Embedding tab ─────────────────────────────────────── */

.embedding-section {
  min-height: 200px;
}

.embedding-mode-switch {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 20px 0;
}

.mode-label {
  font-size: 14px;
  color: #94a3b8;
  transition: color 0.2s;
}

.mode-label.active {
  color: #1e293b;
  font-weight: 600;
}

.embedding-local-info {
  padding: 0 4px;
}

.local-model-card {
  background: #f0fdf4;
  border: 1px solid #bbf7d0;
  border-radius: 10px;
  padding: 16px 20px;
}

.local-model-name {
  font-weight: 600;
  font-size: 15px;
  color: #166534;
  margin-bottom: 4px;
}

.local-model-desc {
  font-size: 13px;
  color: #4ade80;
}

.embedding-cloud-form {
  padding: 0 4px;
}
</style>
