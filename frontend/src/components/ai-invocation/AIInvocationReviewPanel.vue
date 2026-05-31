<script setup lang="ts">
import { computed } from 'vue'

import { useAIInvocationStore } from '../../stores/aiInvocationStore'

const store = useAIInvocationStore()

const statusType = computed(() => {
  const status = store.session?.status
  if (status === 'completed') return 'success'
  if (status === 'blocked' || status === 'failed') return 'error'
  if (status === 'awaiting_acceptance' || status === 'awaiting_commit') return 'warning'
  return 'info'
})

const promptSystem = computed(() => store.session?.prompt_snapshot?.prompt?.system ?? '')
const promptUser = computed(() => store.session?.prompt_snapshot?.prompt?.user ?? '')
const aliases = computed(() => Object.entries(store.session?.variable_plan?.aliases ?? {}))
const diagnostics = computed(() => store.session?.variable_plan?.diagnostics ?? [])
const missingVariables = computed(() => store.session?.variable_plan?.required_missing ?? [])
const hasPrompt = computed(() => Boolean(promptSystem.value || promptUser.value))
const hasCommitSteps = computed(() => Boolean(store.commit?.steps?.length))

function formatValue(value: unknown): string {
  if (value == null) return ''
  if (typeof value === 'string') return value
  try {
    return JSON.stringify(value, null, 2)
  } catch {
    return String(value)
  }
}
</script>

<template>
  <n-drawer v-model:show="store.visible" :width="760" :z-index="3600" placement="right">
    <n-drawer-content :title="store.title" closable>
      <n-spin :show="store.loading">
        <n-space vertical :size="16">
          <n-alert v-if="store.error" type="error" :show-icon="true">
            {{ store.error }}
          </n-alert>

          <n-card size="small" title="会话状态">
            <n-space align="center" :size="12">
              <n-tag :type="statusType" size="small">
                {{ store.session?.status || '未加载' }}
              </n-tag>
              <n-text depth="3">策略：{{ store.session?.policy || '-' }}</n-text>
              <n-text depth="3">下一步：{{ store.nextAction || '-' }}</n-text>
            </n-space>
          </n-card>

          <n-alert
            v-if="store.session?.status === 'awaiting_pre_call_review'"
            type="info"
            :show-icon="true"
          >
            当前会话等待生成前审阅。请先核对变量和提示词快照，后续生成动作会继续沿用同一个 AI Invocation 会话。
          </n-alert>
          <n-alert
            v-if="store.session?.status === 'awaiting_acceptance'"
            type="info"
            :show-icon="true"
          >
            当前会话已完成生成，等待你确认是否采纳本次结果。若接受，将进入提交流程。
          </n-alert>

          <n-alert
            v-if="missingVariables.length > 0"
            type="warning"
            :show-icon="true"
          >
            必填变量缺失：{{ missingVariables.join('、') }}
          </n-alert>

          <n-card v-if="diagnostics.length > 0" size="small" title="诊断信息">
            <n-list>
              <n-list-item v-for="item in diagnostics" :key="item">
                {{ item }}
              </n-list-item>
            </n-list>
          </n-card>

          <n-card size="small" title="变量快照">
            <n-empty v-if="aliases.length === 0" description="暂无变量" />
            <n-list v-else>
              <n-list-item v-for="[key, value] in aliases" :key="key">
                <template #prefix>
                  <n-tag size="small">{{ key }}</n-tag>
                </template>
                <pre class="ai-invocation-value">{{ formatValue(value) }}</pre>
              </n-list-item>
            </n-list>
          </n-card>

          <n-card v-if="hasPrompt" size="small" title="提示词快照">
            <n-tabs type="line" animated>
              <n-tab-pane name="system" tab="系统词">
                <n-scrollbar class="ai-invocation-scroll">
                  <pre class="ai-invocation-pre">{{ promptSystem }}</pre>
                </n-scrollbar>
              </n-tab-pane>
              <n-tab-pane name="user" tab="用户词">
                <n-scrollbar class="ai-invocation-scroll">
                  <pre class="ai-invocation-pre">{{ promptUser }}</pre>
                </n-scrollbar>
              </n-tab-pane>
            </n-tabs>
          </n-card>

          <n-card v-if="store.hasAttempt" size="small" title="生成结果">
            <n-alert v-if="store.attempt?.error" type="error" :show-icon="true">
              {{ store.attempt.error }}
            </n-alert>
            <n-scrollbar v-else class="ai-invocation-result">
              <pre class="ai-invocation-pre">{{ store.attempt?.content }}</pre>
            </n-scrollbar>
          </n-card>

          <n-card v-if="store.decision" size="small" title="采纳决策">
            <n-space align="center">
              <n-tag type="success">{{ store.decision.decision }}</n-tag>
              <n-text depth="3">决策 ID：{{ store.decision.id }}</n-text>
            </n-space>
          </n-card>

          <n-card v-if="hasCommitSteps" size="small" title="提交步骤">
            <n-timeline>
              <n-timeline-item
                v-for="step in store.commit?.steps"
                :key="step.name"
                :type="step.status === 'succeeded' ? 'success' : step.status === 'failed' ? 'error' : 'info'"
                :title="step.name"
                :content="step.status"
              />
            </n-timeline>
          </n-card>
        </n-space>
      </n-spin>

      <template #footer>
        <n-space justify="end">
          <n-button @click="store.close">关闭</n-button>
          <n-button
            v-if="store.session?.status === 'awaiting_pre_call_review'"
            type="primary"
            :loading="store.actionLoading"
            @click="store.resume"
          >
            批准生成
          </n-button>
          <n-button
            v-if="store.canAccept"
            tertiary
            type="error"
            :loading="store.actionLoading"
            @click="store.reject"
          >
            放弃
          </n-button>
          <n-button
            v-if="store.canAccept"
            type="primary"
            :loading="store.actionLoading"
            @click="store.accept"
          >
            采纳
          </n-button>
          <n-button
            v-if="store.canCommit"
            type="primary"
            :loading="store.actionLoading"
            @click="store.runCommit"
          >
            提交
          </n-button>
        </n-space>
      </template>
    </n-drawer-content>
  </n-drawer>
</template>

<style scoped>
.ai-invocation-scroll,
.ai-invocation-result {
  max-height: 280px;
}

.ai-invocation-pre,
.ai-invocation-value {
  margin: 0;
  white-space: pre-wrap;
  word-break: break-word;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono', monospace;
  line-height: 1.65;
}

.ai-invocation-value {
  color: var(--text-color-2, #475569);
}
</style>
