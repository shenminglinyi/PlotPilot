<template>
  <div class="model-role-panel">
    <header class="panel-header">
      <div>
        <h3 class="panel-title">PP AI 配置</h3>
        <p class="panel-lead">
          新增写作、审稿和记忆检查统一使用 LLM 控制台当前激活配置，不再要求复制到外部模型或维护双线 AI。
        </p>
      </div>
    </header>

    <div class="panel-content">
      <n-space vertical :size="14">
        <n-alert type="info" :show-icon="false">
          当前主线：PP 当前 AI。候选稿生成、采纳前检查和章后记忆更新都走同一套 PP LLM 配置。
        </n-alert>

        <n-card size="small" title="旧标签兼容">
          <n-space vertical :size="12">
            <n-text depth="3">
              这里保留 Kimi / Claude / GPT / DeepSeek 等标签，仅用于识别旧候选稿和旧台账。
              当前主流程不会按这里拆成写作模型与审稿模型。
            </n-text>
            <n-button type="primary" secondary @click="saveConfig">
              保存兼容标签
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
              <n-space justify="space-between" align="start">
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
              <n-form-item
                label="绑定 LLM 控制面板配置"
                label-placement="top"
                :show-feedback="false"
                class="profile-binding"
              >
                <n-select
                  v-model:value="profile.llmProfileId"
                  :options="llmProfileOptions"
                  clearable
                  placeholder="不绑定时使用当前激活 LLM"
                />
              </n-form-item>
            </div>
          </n-space>
        </n-card>
      </n-space>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useMessage } from 'naive-ui'
import { llmControlApi, type LLMProfile } from '@/api/llmControl'
import {
  loadModelRoleConfig,
  saveModelRoleConfig,
  upsertModelProfile,
  type ModelProfile,
  type ModelRole,
  type ModelRoleConfig,
} from '@/utils/modelRoleConfig'

const message = useMessage()
const draftConfig = ref<ModelRoleConfig>(loadModelRoleConfig())
const llmProfiles = ref<LLMProfile[]>([])
const customModel = ref<ModelProfile>({
  value: '',
  label: '',
  role: 'both',
  note: '',
})

const roleOptions = [
  { label: '旧写作标签', value: 'writer' },
  { label: '旧检查标签', value: 'supervisor' },
  { label: '旧通用标签', value: 'both' },
]

const llmProfileOptions = computed(() => llmProfiles.value.map(profile => ({
  label: `${profile.name}${profile.model ? ` · ${profile.model}` : ''}`,
  value: profile.id,
})))

function roleLabel(role: ModelRole) {
  if (role === 'writer') return '写作'
  if (role === 'supervisor') return '审稿/记忆'
  return '写作 + 审稿'
}

function saveConfig() {
  draftConfig.value = saveModelRoleConfig(draftConfig.value)
  message.success('PP AI 兼容标签已保存')
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

onMounted(async () => {
  try {
    const panel = await llmControlApi.getPanel()
    llmProfiles.value = panel.config.profiles
  } catch {
    llmProfiles.value = []
  }
})
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

.profile-binding {
  margin-top: 10px;
  margin-bottom: 0;
}
</style>
