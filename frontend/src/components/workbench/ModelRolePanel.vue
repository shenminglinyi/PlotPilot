<template>
  <div class="model-role-panel">
    <header class="panel-header">
      <div>
        <h3 class="panel-title">模型分工</h3>
        <p class="panel-lead">
          配置“谁负责写正文、谁负责审稿/记忆/连续性检查”。写作模型不限定 Kimi，可按项目切换。
        </p>
      </div>
    </header>

    <div class="panel-content">
      <n-space vertical :size="14">
        <n-alert type="info" :show-icon="false">
          当前分工：{{ roleSummary }}
        </n-alert>

        <n-card size="small" title="默认角色">
          <n-space vertical :size="12">
            <n-form-item label="写作模型" label-placement="top" :show-feedback="false">
              <n-select
                v-model:value="draftConfig.writingModel"
                :options="writerOptions"
                placeholder="选择负责写正文的模型"
              />
            </n-form-item>
            <n-form-item label="审稿 / 记忆模型" label-placement="top" :show-feedback="false">
              <n-select
                v-model:value="draftConfig.supervisorModel"
                :options="supervisorOptions"
                placeholder="选择负责检查和生成约束的模型"
              />
            </n-form-item>
            <n-button type="primary" secondary @click="saveConfig">
              保存模型分工
            </n-button>
          </n-space>
        </n-card>

        <n-card size="small" title="添加自定义模型">
          <n-space vertical :size="10">
            <n-grid :cols="2" :x-gap="8" :y-gap="8">
              <n-grid-item>
                <n-input v-model:value="customModel.label" placeholder="显示名，如 Gemini 2.5" />
              </n-grid-item>
              <n-grid-item>
                <n-input v-model:value="customModel.value" placeholder="标识，如 gemini-2.5" />
              </n-grid-item>
            </n-grid>
            <n-select v-model:value="customModel.role" :options="roleOptions" />
            <n-input v-model:value="customModel.note" placeholder="备注：适合写作/审稿/长上下文等" />
            <n-button secondary @click="addCustomModel">
              加入模型列表
            </n-button>
          </n-space>
        </n-card>

        <n-card size="small" title="模型列表">
          <n-space vertical :size="8">
            <div v-for="profile in draftConfig.profiles" :key="profile.value" class="model-row">
              <n-space justify="space-between" align="center">
                <div>
                  <n-text strong>{{ profile.label }}</n-text>
                  <n-text depth="3" style="font-size: 12px">
                    {{ profile.value }} · {{ roleLabel(profile.role) }}
                  </n-text>
                  <n-text v-if="profile.note" depth="3" style="font-size: 12px">
                    {{ profile.note }}
                  </n-text>
                </div>
                <n-tag size="small" round :type="profile.role === 'both' ? 'success' : 'info'">
                  {{ roleLabel(profile.role) }}
                </n-tag>
              </n-space>
            </div>
          </n-space>
        </n-card>
      </n-space>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useMessage } from 'naive-ui'
import {
  buildModelRoleSummary,
  getModelOptions,
  loadModelRoleConfig,
  saveModelRoleConfig,
  upsertModelProfile,
  type ModelProfile,
  type ModelRole,
  type ModelRoleConfig,
} from '@/utils/modelRoleConfig'

const message = useMessage()
const draftConfig = ref<ModelRoleConfig>(loadModelRoleConfig())
const customModel = ref<ModelProfile>({
  value: '',
  label: '',
  role: 'both',
  note: '',
})

const roleOptions = [
  { label: '写作模型', value: 'writer' },
  { label: '审稿/记忆模型', value: 'supervisor' },
  { label: '两者都可', value: 'both' },
]

const writerOptions = computed(() => getModelOptions(draftConfig.value, 'writer'))
const supervisorOptions = computed(() => getModelOptions(draftConfig.value, 'supervisor'))
const roleSummary = computed(() => buildModelRoleSummary(draftConfig.value))

function roleLabel(role: ModelRole) {
  if (role === 'writer') return '写作'
  if (role === 'supervisor') return '审稿/记忆'
  return '写作 + 审稿'
}

function saveConfig() {
  draftConfig.value = saveModelRoleConfig(draftConfig.value)
  message.success('模型分工已保存')
}

function addCustomModel() {
  if (!customModel.value.label.trim()) {
    message.warning('请先填写模型显示名')
    return
  }
  draftConfig.value = upsertModelProfile(draftConfig.value, customModel.value)
  draftConfig.value = saveModelRoleConfig(draftConfig.value)
  customModel.value = { value: '', label: '', role: 'both', note: '' }
  message.success('已加入模型列表')
}
</script>

<style scoped>
.model-role-panel {
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: var(--aitext-panel-muted);
}

.panel-header {
  padding: 16px;
  border-bottom: 1px solid var(--aitext-split-border);
  background: var(--app-surface);
}

.panel-title {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
}

.panel-lead {
  margin: 8px 0 0;
  font-size: 13px;
  line-height: 1.5;
  color: var(--text-color-3);
}

.panel-content {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
}

.model-row {
  padding: 10px;
  border: 1px solid var(--aitext-split-border);
  border-radius: 10px;
  background: var(--app-surface);
}
</style>
