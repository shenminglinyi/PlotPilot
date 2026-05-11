<template>
  <!-- DAG 节点配置抽屉 — 仅用于运行参数调整，提示词编辑走提示词广场 -->
  <n-drawer
    :show="isOpen"
    :width="480"
    placement="right"
    @update:show="handleClose"
  >
    <n-drawer-content :title="drawerTitle">
      <!-- 提示词关联信息 + 跳转广场 -->
      <div v-if="cpmsNodeKey" class="cpms-section">
        <div class="cpms-header">
          <span class="cpms-icon">🏪</span>
          <div class="cpms-info">
            <span class="cpms-label">关联提示词</span>
            <code class="cpms-key">{{ cpmsNodeKey }}</code>
          </div>
          <n-button size="small" type="primary" secondary @click="handleOpenPlaza">
            在广场编辑
          </n-button>
        </div>
        <p class="cpms-hint">
          点击「在广场编辑」打开提示词广场，支持编辑、版本管理、回滚。
        </p>
      </div>

      <!-- 运行参数 -->
      <n-form label-placement="left" label-width="100" size="small" class="config-form">
        <n-form-item label="温度">
          <n-slider
            v-model:value="localConfig.temperature"
            :min="0"
            :max="2"
            :step="0.1"
            style="flex: 1; margin-right: 12px"
          />
          <n-input-number
            v-model:value="localConfig.temperature"
            size="tiny"
            :min="0"
            :max="2"
            :step="0.1"
            style="width: 80px"
          />
        </n-form-item>

        <n-form-item label="最大 Tokens">
          <n-input-number
            v-model:value="localConfig.maxTokens"
            size="small"
            :min="100"
            :max="16000"
            :step="100"
            placeholder="默认"
            clearable
            style="width: 160px"
          />
        </n-form-item>

        <n-form-item label="超时时间">
          <n-input-number
            v-model:value="localConfig.timeoutSeconds"
            size="small"
            :min="10"
            :max="600"
            :step="10"
            style="width: 160px"
          />
          <n-text depth="3" style="margin-left: 8px; font-size: 12px">秒</n-text>
        </n-form-item>

        <n-form-item label="最大重试">
          <n-input-number
            v-model:value="localConfig.maxRetries"
            size="small"
            :min="0"
            :max="5"
            style="width: 160px"
          />
        </n-form-item>

        <n-form-item label="模型覆盖">
          <n-input
            v-model:value="localConfig.modelOverride"
            size="small"
            placeholder="留空使用默认模型"
            clearable
            style="width: 240px"
          />
        </n-form-item>
      </n-form>

      <!-- 操作按钮 -->
      <template #footer>
        <div class="drawer-footer">
          <n-button @click="handleClose(false)">关闭</n-button>
          <div class="footer-right">
            <n-button
              type="primary"
              :disabled="!hasConfigChanges"
              @click="handleSaveConfig"
            >
              保存参数
            </n-button>
          </div>
        </div>
      </template>
    </n-drawer-content>
  </n-drawer>
</template>

<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import { useMessage } from 'naive-ui'
import { useDAGStore } from '@/stores/dagStore'
import { usePromptPlazaBridge } from '@/stores/promptPlazaBridge'

const dagStore = useDAGStore()
const plazaBridge = usePromptPlazaBridge()
const message = useMessage()

// ─── 本地配置状态 ───
const localConfig = reactive({
  temperature: 0.7,
  maxTokens: null as number | null,
  timeoutSeconds: 60,
  maxRetries: 1,
  modelOverride: '',
})

const editingNodeId = ref<string | null>(null)
const isOpen = ref(false)
const cpmsNodeKeyValue = ref<string | null>(null)

// ─── 计算属性 ───

const cpmsNodeKey = computed(() => cpmsNodeKeyValue.value)

const drawerTitle = computed(() => {
  if (cpmsNodeKeyValue.value) {
    return `节点配置 — ${cpmsNodeKeyValue.value}`
  }
  return '节点配置'
})

const hasConfigChanges = computed(() => {
  return (
    localConfig.temperature !== 0.7 ||
    localConfig.maxTokens !== null ||
    localConfig.timeoutSeconds !== 60 ||
    localConfig.maxRetries !== 1 ||
    localConfig.modelOverride !== ''
  )
})

// ─── 打开抽屉（供外部调用） ───

function open(nodeId: string, dagId: string) {
  const dag = dagStore.dagDefinition
  if (!dag) return

  const node = dag.nodes.find(n => n.id === nodeId)
  if (!node) return

  editingNodeId.value = nodeId
  cpmsNodeKeyValue.value = plazaBridge.getCpmsKey(node.type)
  loadLocalConfig(node)
  isOpen.value = true
}

// ─── 初始化本地配置 ───

function loadLocalConfig(node: { config: Record<string, unknown> }) {
  const config = node.config || {}
  localConfig.temperature = (config.temperature as number) ?? 0.7
  localConfig.maxTokens = (config.max_tokens as number | null) ?? null
  localConfig.timeoutSeconds = (config.timeout_seconds as number) ?? 60
  localConfig.maxRetries = (config.max_retries as number) ?? 1
  localConfig.modelOverride = (config.model_override as string) ?? ''
}

// ─── 保存配置 ───

async function handleSaveConfig() {
  if (!editingNodeId.value || !dagStore.dagDefinition) return

  try {
    const config: Record<string, unknown> = {
      temperature: localConfig.temperature,
      timeout_seconds: localConfig.timeoutSeconds,
      max_retries: localConfig.maxRetries,
    }
    if (localConfig.maxTokens !== null) {
      config.max_tokens = localConfig.maxTokens
    }
    if (localConfig.modelOverride) {
      config.model_override = localConfig.modelOverride
    }

    await dagStore.updateNodeConfig(dagStore.dagDefinition.id, editingNodeId.value, config)
    message.success('节点参数保存成功')
  } catch {
    message.error('节点参数保存失败')
  }
}

function handleOpenPlaza() {
  if (cpmsNodeKeyValue.value) {
    plazaBridge.openPromptInPlaza(cpmsNodeKeyValue.value)
  } else {
    plazaBridge.openPromptInPlaza('', false)
  }
}

function handleClose(val: boolean | ((show: boolean) => void)) {
  if (typeof val === 'boolean' && !val) {
    isOpen.value = false
  } else if (typeof val === 'function') {
    isOpen.value = false
  }
}

defineExpose({ open })
</script>

<style scoped>
.cpms-section {
  margin-bottom: 16px;
}

.cpms-header {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 14px;
  background: var(--app-surface-subtle);
  border-radius: var(--app-radius-md);
  border: 1px solid var(--app-border);
}

.cpms-icon {
  font-size: 20px;
  flex-shrink: 0;
}

.cpms-info {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
  flex: 1;
}

.cpms-label {
  font-size: 12px;
  font-weight: 600;
  color: var(--app-text-secondary);
}

.cpms-key {
  font-size: 11px;
  font-family: var(--font-mono);
  color: var(--color-brand);
  background: var(--color-brand-light);
  padding: 2px 6px;
  border-radius: 4px;
  border: 1px solid var(--color-brand-border);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 240px;
}

.cpms-hint {
  font-size: 12px;
  color: var(--app-text-muted);
  margin: 8px 0 0;
  line-height: 1.45;
}

.config-form {
  padding-bottom: 8px;
}

.drawer-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  width: 100%;
}

.footer-right {
  display: flex;
  gap: 8px;
}
</style>
