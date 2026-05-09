<template>
  <div class="dag-toolbar">
    <div class="toolbar-left">
      <!-- 视图切换 -->
      <n-button-group size="small">
        <n-button
          :type="viewMode === 'card' ? 'primary' : 'default'"
          @click="$emit('switchView', 'card')"
        >
          📊 卡片
        </n-button>
        <n-button
          :type="viewMode === 'dag' ? 'primary' : 'default'"
          @click="$emit('switchView', 'dag')"
        >
          🧭 DAG
        </n-button>
      </n-button-group>

      <!-- DAG 统计 -->
      <n-tag v-if="dagStats" size="small" round>
        {{ dagStats.total }} 节点 · {{ dagStats.enabled }} 启用
        <template v-if="dagStats.running > 0">
          · <n-text type="info">{{ dagStats.running }} 运行中</n-text>
        </template>
        <template v-if="dagStats.error > 0">
          · <n-text type="error">{{ dagStats.error }} 错误</n-text>
        </template>
      </n-tag>
    </div>

    <div class="toolbar-center">
      <div class="toolbar-title">
        <n-text strong style="font-size: 14px">🧭 DAG 工作流</n-text>
        <!-- 运行状态指示 -->
        <n-tag
          v-if="runStatus === 'running'"
          size="small"
          type="info"
          round
          :bordered="false"
        >
          <template #icon>
            <n-spin :size="12" />
          </template>
          运行中
        </n-tag>
        <n-tag
          v-else-if="runStatus === 'completed'"
          size="small"
          type="success"
          round
          :bordered="false"
        >
          ✅ 已完成
        </n-tag>
        <n-tag
          v-else-if="runStatus === 'error'"
          size="small"
          type="error"
          round
          :bordered="false"
        >
          ❌ 错误
        </n-tag>
        <!-- SSE 连接状态 -->
        <n-tooltip trigger="hover">
          <template #trigger>
            <div class="sse-indicator" :class="{ connected: sseConnected }" />
          </template>
          {{ sseConnected ? 'SSE 实时连接正常' : 'SSE 连接断开' }}
        </n-tooltip>
      </div>
    </div>

    <div class="toolbar-right">
      <!-- 版本信息 -->
      <n-text depth="3" style="font-size: 11px" v-if="dagStats">
        v{{ dagStats.version || 1 }}
      </n-text>

      <!-- 验证 -->
      <n-button size="small" quaternary @click="$emit('validate')">
        ✅ 校验
      </n-button>
      <!-- 保存 -->
      <n-button size="small" quaternary @click="$emit('save')">
        💾 保存
      </n-button>
      <!-- 运行/停止 -->
      <n-button
        v-if="runStatus !== 'running'"
        size="small"
        type="primary"
        :disabled="runStatus === 'stopping'"
        @click="$emit('run')"
      >
        ▶ 启动
      </n-button>
      <n-button
        v-else
        size="small"
        type="warning"
        :loading="runStatus === 'stopping'"
        @click="$emit('stop')"
      >
        ⏹ 停止
      </n-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { DAGRunStatus } from '@/stores/dagRunStore'

defineProps<{
  novelId: string
  viewMode: 'card' | 'dag'
  dagStats: {
    total: number
    enabled: number
    running: number
    success: number
    error: number
    bypassed: number
    version?: number
  }
  runStatus: DAGRunStatus
  sseConnected: boolean
}>()

defineEmits<{
  switchView: [mode: 'card' | 'dag']
  save: []
  validate: []
  run: []
  stop: []
}>()
</script>

<style scoped>
.dag-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 16px;
  border-bottom: 1px solid var(--n-border-color);
  background: var(--n-color);
  gap: 12px;
}

.toolbar-left,
.toolbar-right {
  display: flex;
  align-items: center;
  gap: 8px;
}

.toolbar-center {
  flex-shrink: 0;
}

.toolbar-title {
  display: flex;
  align-items: center;
  gap: 8px;
}

.sse-indicator {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #ef4444;
  transition: background 0.3s;
}

.sse-indicator.connected {
  background: #22c55e;
  animation: pulse 2s ease-in-out infinite;
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}
</style>
