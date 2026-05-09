<template>
  <n-drawer
    :show="editorStore.isOpen"
    :width="640"
    placement="right"
    @update:show="handleClose"
  >
    <n-drawer-content :title="drawerTitle">
      <!-- ─── Prompt 模板编辑 ─── -->
      <n-collapse :default-expanded-names="['prompt', 'variables', 'preview']">
        <!-- Prompt 模板 -->
        <n-collapse-item title="📝 Prompt 模板" name="prompt">
          <n-input
            v-model:value="editorStore.promptTemplate"
            type="textarea"
            :rows="12"
            placeholder="输入 Prompt 模板，使用 {{变量名}} 插入变量..."
            font="monospace"
            @update:value="editorStore.renderLocalPreview"
          />
          <div class="template-toolbar">
            <n-text depth="3" style="font-size: 11px">
              使用 &#123;&#123;变量名&#125;&#125; 插入动态内容
            </n-text>
            <n-button size="tiny" quaternary @click="editorStore.resetToDefault">
              🔄 恢复默认
            </n-button>
          </div>
        </n-collapse-item>

        <!-- 变量注入 -->
        <n-collapse-item v-if="variableKeys.length > 0" title="🔌 变量注入" name="variables">
          <div class="variable-list">
            <div v-for="key in variableKeys" :key="key" class="variable-item">
              <n-text class="variable-key">{{ key }}</n-text>
              <n-input
                v-model:value="editorStore.variables[key]"
                size="small"
                :placeholder="`输入 ${key} 的值`"
                @update:value="editorStore.renderLocalPreview"
              />
            </div>
          </div>
        </n-collapse-item>

        <!-- 预览 -->
        <n-collapse-item title="👁️ 预览" name="preview">
          <n-card size="small" embedded>
            <n-scrollbar style="max-height: 200px">
              <pre class="prompt-preview">{{ editorStore.renderedPrompt || '（无预览内容）' }}</pre>
            </n-scrollbar>
          </n-card>
        </n-collapse-item>

        <!-- 阈值配置 -->
        <n-collapse-item title="⚙️ 阈值与参数" name="thresholds">
          <n-form label-placement="left" label-width="100" size="small">
            <!-- 阈值 -->
            <n-form-item v-if="isValidationNode" label="阈值配置">
              <div class="threshold-list">
                <div v-for="(value, key) in localThresholds" :key="key" class="threshold-item">
                  <n-text class="threshold-key">{{ key }}</n-text>
                  <n-slider
                    v-model:value="localThresholds[key]"
                    :min="0"
                    :max="1"
                    :step="0.05"
                    style="flex: 1"
                  />
                  <n-input-number
                    v-model:value="localThresholds[key]"
                    size="tiny"
                    :min="0"
                    :max="1"
                    :step="0.05"
                    style="width: 80px"
                  />
                </div>
                <n-button size="tiny" dashed @click="addThreshold">
                  + 添加阈值
                </n-button>
              </div>
            </n-form-item>

            <!-- 模型参数 -->
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
        </n-collapse-item>
      </n-collapse>

      <!-- 操作按钮 -->
      <template #footer>
        <div class="drawer-footer">
          <n-button @click="editorStore.resetToDefault" :disabled="!editorStore.hasUnsavedChanges">
            🔄 恢复默认
          </n-button>
          <div class="footer-right">
            <n-button @click="handleClose(false)">取消</n-button>
            <n-button
              type="primary"
              :loading="editorStore.isSaving"
              :disabled="!hasAnyChanges"
              @click="handleSave"
            >
              💾 保存并生效
            </n-button>
          </div>
        </div>
      </template>
    </n-drawer-content>
  </n-drawer>
</template>

<script setup lang="ts">
import { computed, watch, reactive } from 'vue'
import { useMessage } from 'naive-ui'
import { useNodeEditorStore } from '@/stores/nodeEditorStore'
import { useDAGStore } from '@/stores/dagStore'

const editorStore = useNodeEditorStore()
const dagStore = useDAGStore()
const message = useMessage()

// ─── 本地配置状态（独立于 prompt 的模型参数）───
const localConfig = reactive({
  temperature: 0.7,
  maxTokens: null as number | null,
  timeoutSeconds: 60,
  maxRetries: 1,
  modelOverride: '',
})

const localThresholds = reactive<Record<string, number>>({})

// ─── 计算属性 ───

const variableKeys = computed(() => Object.keys(editorStore.variables))

const drawerTitle = computed(() => {
  const nodeId = editorStore.nodeId || ''
  const node = dagStore.dagDefinition?.nodes.find(n => n.id === nodeId)
  const meta = node ? dagStore.nodeTypeRegistry[node.type] : null
  return `✏️ ${meta?.display_name || nodeId} — 节点配置`
})

const isValidationNode = computed(() => {
  const nodeId = editorStore.nodeId
  const node = dagStore.dagDefinition?.nodes.find(n => n.id === nodeId)
  return node?.type.startsWith('val_') || node?.type === 'gw_circuit'
})

const hasAnyChanges = computed(() => {
  if (editorStore.hasUnsavedChanges) return true
  // 检查配置是否有变化
  const node = dagStore.dagDefinition?.nodes.find(n => n.id === editorStore.nodeId)
  if (!node) return false
  return (
    localConfig.temperature !== (node.config.temperature ?? 0.7) ||
    localConfig.maxTokens !== (node.config.max_tokens ?? null) ||
    localConfig.timeoutSeconds !== (node.config.timeout_seconds ?? 60) ||
    localConfig.maxRetries !== (node.config.max_retries ?? 1) ||
    localConfig.modelOverride !== (node.config.model_override ?? '') ||
    JSON.stringify(localThresholds) !== JSON.stringify(node.config.thresholds ?? {})
  )
})

// ─── 初始化本地配置 ───

watch(() => editorStore.isOpen, (open) => {
  if (open) {
    editorStore.renderLocalPreview()
    loadLocalConfig()
  }
})

function loadLocalConfig() {
  const node = dagStore.dagDefinition?.nodes.find(n => n.id === editorStore.nodeId)
  if (node) {
    localConfig.temperature = node.config.temperature ?? 0.7
    localConfig.maxTokens = node.config.max_tokens ?? null
    localConfig.timeoutSeconds = node.config.timeout_seconds ?? 60
    localConfig.maxRetries = node.config.max_retries ?? 1
    localConfig.modelOverride = node.config.model_override ?? ''

    // 加载阈值
    Object.keys(localThresholds).forEach(k => delete localThresholds[k])
    if (node.config.thresholds) {
      Object.assign(localThresholds, node.config.thresholds)
    }
  }
}

function addThreshold() {
  const key = prompt('输入阈值名称:')
  if (key && !(key in localThresholds)) {
    localThresholds[key] = 0.5
  }
}

// ─── 保存 ───

async function handleSave() {
  try {
    // 保存 Prompt（通过 editorStore）
    await editorStore.save()

    // 保存其他配置（通过 dagStore）
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
    if (Object.keys(localThresholds).length > 0) {
      config.thresholds = { ...localThresholds }
    }

    if (editorStore.novelId && editorStore.nodeId) {
      await dagStore.updateNodeConfig(editorStore.novelId, editorStore.nodeId, config)
    }

    message.success('节点配置保存成功')
  } catch {
    message.error('节点配置保存失败')
  }
}

function handleClose(show: boolean) {
  if (!show) {
    editorStore.close()
  }
}
</script>

<style scoped>
.variable-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  width: 100%;
}

.variable-item {
  display: flex;
  align-items: center;
  gap: 8px;
}

.variable-key {
  min-width: 120px;
  font-family: monospace;
  font-size: 13px;
  color: #8b5cf6;
}

.prompt-preview {
  font-family: monospace;
  font-size: 12px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-all;
  margin: 0;
  color: #e2e8f0;
}

.template-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 8px;
}

.threshold-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  width: 100%;
}

.threshold-item {
  display: flex;
  align-items: center;
  gap: 8px;
}

.threshold-key {
  min-width: 100px;
  font-family: monospace;
  font-size: 12px;
  color: #f59e0b;
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
