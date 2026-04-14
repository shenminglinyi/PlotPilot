<template>
  <div class="llm-settings-page">
    <StatsSidebar @create-book="$router.push('/')" @refresh-list="$router.push('/')" />
    
    <div class="settings-content">
      <div class="settings-header">
        <h1 class="page-title">
          <span class="title-icon">🤖</span>
          LLM 大模型设置
        </h1>
        <p class="page-subtitle">配置 AI 大模型参数，支持 Anthropic Claude 和阿里 DashScope</p>
      </div>

      <n-card class="settings-card" :bordered="false">
        <!-- Provider Selection -->
        <div class="provider-section">
          <h3 class="section-title">
            <span class="section-icon">🔌</span>
            选择提供商
          </h3>
          <n-radio-group v-model:value="settings.active_provider" class="provider-radio-group">
            <n-radio-button value="anthropic">
              <span class="provider-option">
                <span class="provider-icon">🅰️</span>
                <span class="provider-name">Anthropic Claude</span>
              </span>
            </n-radio-button>
            <n-radio-button value="ark">
              <span class="provider-option">
                <span class="provider-icon">🇨🇳</span>
                <span class="provider-name">阿里 DashScope</span>
              </span>
            </n-radio-button>
            <n-radio-button value="mock">
              <span class="provider-option">
                <span class="provider-icon">🧪</span>
                <span class="provider-name">Mock 模式</span>
              </span>
            </n-radio-button>
          </n-radio-group>
        </div>

        <n-divider />

        <!-- Anthropic Settings -->
        <div v-show="settings.active_provider === 'anthropic'" class="provider-settings">
          <h3 class="section-title">
            <span class="section-icon">🅰️</span>
            Anthropic Claude 配置
          </h3>
          
          <n-grid :cols="2" :x-gap="24" :y-gap="16" responsive="screen">
            <n-gi :span="2">
              <n-form-item label="API Key" :required="true">
                <n-input
                  v-model:value="settings.anthropic.api_key"
                  type="password"
                  placeholder="sk-ant-api03-..."
                  show-password-on="click"
                />
              </n-form-item>
            </n-gi>
            
            <n-gi>
              <n-form-item label="Base URL">
                <n-input
                  v-model:value="settings.anthropic.base_url"
                  placeholder="https://api.anthropic.com"
                />
              </n-form-item>
            </n-gi>
            
            <n-gi>
              <n-form-item label="Model">
                <n-input
                  v-model:value="settings.anthropic.model"
                  placeholder="例如：claude-3-sonnet-20240229"
                />
                <div class="form-hint">请输入模型名称，如 claude-3-sonnet-20240229</div>
              </n-form-item>
            </n-gi>
            
            <n-gi>
              <n-form-item label="Max Tokens">
                <n-slider v-model:value="settings.anthropic.max_tokens" :min="256" :max="8192" :step="256" />
                <div class="slider-value">{{ settings.anthropic.max_tokens }}</div>
              </n-form-item>
            </n-gi>
            
            <n-gi>
              <n-form-item label="Temperature">
                <n-slider v-model:value="settings.anthropic.temperature" :min="0" :max="2" :step="0.1" />
                <div class="slider-value">{{ settings.anthropic.temperature }}</div>
              </n-form-item>
            </n-gi>
            
            <n-gi>
              <n-form-item label="Timeout (秒)">
                <n-input-number v-model:value="settings.anthropic.timeout" :min="10" :max="600" class="w-full" />
              </n-form-item>
            </n-gi>
          </n-grid>
        </div>

        <!-- Ark Settings -->
        <div v-show="settings.active_provider === 'ark'" class="provider-settings">
          <h3 class="section-title">
            <span class="section-icon">🇨🇳</span>
            阿里 DashScope 配置
          </h3>
          
          <n-grid :cols="2" :x-gap="24" :y-gap="16" responsive="screen">
            <n-gi :span="2">
              <n-form-item label="API Key" :required="true">
                <n-input
                  v-model:value="settings.ark.api_key"
                  type="password"
                  placeholder="sk-..."
                  show-password-on="click"
                />
              </n-form-item>
            </n-gi>
            
            <n-gi>
              <n-form-item label="Base URL">
                <n-input
                  v-model:value="settings.ark.base_url"
                  placeholder="https://dashscope.aliyuncs.com/compatible-mode/v1"
                />
              </n-form-item>
            </n-gi>
            
            <n-gi>
              <n-form-item label="Model">
                <n-input
                  v-model:value="settings.ark.model"
                  placeholder="例如：qwen-turbo"
                />
                <div class="form-hint">请输入模型名称，如 qwen-turbo、qwen-max 等</div>
              </n-form-item>
            </n-gi>
            
            <n-gi>
              <n-form-item label="Max Tokens">
                <n-slider v-model:value="settings.ark.max_tokens" :min="256" :max="8192" :step="256" />
                <div class="slider-value">{{ settings.ark.max_tokens }}</div>
              </n-form-item>
            </n-gi>
            
            <n-gi>
              <n-form-item label="Temperature">
                <n-slider v-model:value="settings.ark.temperature" :min="0" :max="2" :step="0.1" />
                <div class="slider-value">{{ settings.ark.temperature }}</div>
              </n-form-item>
            </n-gi>
            
            <n-gi>
              <n-form-item label="Timeout (秒)">
                <n-input-number v-model:value="settings.ark.timeout" :min="10" :max="600" class="w-full" />
              </n-form-item>
            </n-gi>
          </n-grid>
        </div>

        <!-- Mock Mode -->
        <div v-show="settings.active_provider === 'mock'" class="provider-settings">
          <n-alert type="info" title="Mock 模式">
            <p>Mock 模式使用预设的响应，不需要 API Key。</p>
            <p>适用于测试和开发环境。</p>
          </n-alert>
        </div>

        <n-divider />

        <!-- Action Buttons -->
        <div class="action-buttons">
          <n-button
            type="primary"
            size="large"
            :loading="saving"
            :disabled="!canSave"
            @click="handleSave"
          >
            <template #icon>
              <n-icon><IconSave /></n-icon>
            </template>
            保存设置
          </n-button>
          
          <n-button
            size="large"
            :loading="testing"
            :disabled="!canTest"
            @click="handleTest"
          >
            <template #icon>
              <n-icon><IconTest /></n-icon>
            </template>
            测试连接
          </n-button>
        </div>
      </n-card>

      <!-- Test Result -->
      <n-card v-if="testResult" class="result-card" :bordered="false" :class="{ success: testResult.success, error: !testResult.success }">
        <n-space align="center">
          <span class="result-icon">{{ testResult.success ? '✅' : '❌' }}</span>
          <span class="result-message">{{ testResult.message }}</span>
        </n-space>
        <p v-if="testResult.response" class="result-detail">
          响应: {{ testResult.response }}
        </p>
      </n-card>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useMessage } from 'naive-ui'
import { SaveOutline as IconSave, FlashOutline as IconTest } from '@vicons/ionicons5'
import StatsSidebar from '@/components/stats/StatsSidebar.vue'

const message = useMessage()

// Settings state
const settings = ref({
  active_provider: 'ark',
  anthropic: {
    enabled: false,
    api_key: '',
    base_url: 'https://api.anthropic.com',
    model: 'claude-3-sonnet-20240229',
    max_tokens: 4096,
    temperature: 0.7,
    timeout: 300
  },
  ark: {
    enabled: true,
    api_key: '',
    base_url: 'https://dashscope.aliyuncs.com/compatible-mode/v1',
    model: 'qwen-turbo',
    max_tokens: 2048,
    temperature: 0.7,
    timeout: 300
  }
})

const saving = ref(false)
const testing = ref(false)
const testResult = ref<{ success: boolean; message: string; response?: string } | null>(null)

// Computed
const canSave = computed(() => {
  if (settings.value.active_provider === 'mock') return true
  if (settings.value.active_provider === 'anthropic') {
    return settings.value.anthropic.api_key.trim().length > 0
  }
  if (settings.value.active_provider === 'ark') {
    return settings.value.ark.api_key.trim().length > 0
  }
  return false
})

const canTest = computed(() => {
  return canSave.value
})

// Load settings on mount
onMounted(async () => {
  try {
    const response = await fetch('/api/v1/llm-settings')
    if (response.ok) {
      const data = await response.json()
      settings.value = data
    }
  } catch (error) {
    console.error('Failed to load settings:', error)
  }
})

// Save settings
async function handleSave() {
  saving.value = true
  try {
    const response = await fetch('/api/v1/llm-settings', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(settings.value)
    })
    
    if (response.ok) {
      const result = await response.json()
      message.success(result.message || '设置已保存')
    } else {
      const error = await response.json()
      message.error(error.detail || '保存失败')
    }
  } catch (error) {
    message.error('保存失败: ' + (error as Error).message)
  } finally {
    saving.value = false
  }
}

// Test connection
async function handleTest() {
  testing.value = true
  testResult.value = null
  
  try {
    const response = await fetch('/api/v1/llm-settings/test', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(settings.value)
    })
    
    const result = await response.json()
    testResult.value = result
    
    if (result.success) {
      message.success(result.message)
    } else {
      message.error(result.message)
    }
  } catch (error) {
    testResult.value = {
      success: false,
      message: '测试失败: ' + (error as Error).message
    }
    message.error('测试失败')
  } finally {
    testing.value = false
  }
}
</script>

<style scoped>
.llm-settings-page {
  display: flex;
  min-height: 100vh;
  background: linear-gradient(135deg, #f5f7fa 0%, #e4e8ec 100%);
}

.settings-content {
  flex: 1;
  margin-left: 280px;
  padding: 40px;
  max-width: 900px;
}

.settings-header {
  margin-bottom: 32px;
}

.page-title {
  font-size: 28px;
  font-weight: 700;
  color: #1a1a2e;
  margin: 0 0 8px 0;
  display: flex;
  align-items: center;
  gap: 12px;
}

.title-icon {
  font-size: 32px;
}

.page-subtitle {
  font-size: 15px;
  color: #6b7280;
  margin: 0;
}

.settings-card {
  border-radius: 16px;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.08);
}

.provider-section {
  margin-bottom: 24px;
}

.section-title {
  font-size: 18px;
  font-weight: 600;
  color: #1a1a2e;
  margin: 0 0 16px 0;
  display: flex;
  align-items: center;
  gap: 8px;
}

.section-icon {
  font-size: 20px;
}

.provider-radio-group {
  display: flex;
  gap: 12px;
}

.provider-option {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 8px;
}

.provider-icon {
  font-size: 20px;
}

.provider-name {
  font-weight: 500;
}

.provider-settings {
  padding: 8px 0;
}

.slider-value {
  text-align: center;
  color: #6b7280;
  font-size: 13px;
  margin-top: 4px;
}

.action-buttons {
  display: flex;
  gap: 16px;
  justify-content: center;
  padding: 16px 0;
}

.result-card {
  margin-top: 24px;
  border-radius: 12px;
}

.result-card.success {
  background: linear-gradient(135deg, #d1fae5 0%, #a7f3d0 100%);
}

.result-card.error {
  background: linear-gradient(135deg, #fee2e2 0%, #fecaca 100%);
}

.result-icon {
  font-size: 24px;
}

.result-message {
  font-size: 16px;
  font-weight: 500;
}

.result-detail {
  margin: 8px 0 0 0;
  padding-left: 40px;
  color: #6b7280;
  font-size: 14px;
}

.w-full {
  width: 100%;
}

.form-hint {
  font-size: 12px;
  color: #6b7280;
  margin-top: 4px;
}
</style>
