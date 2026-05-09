<template>
  <div class="dag-toolbar">
    <div class="toolbar-left">
      <n-text strong class="toolbar-title-text">🧭 DAG 可视化</n-text>
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

      <!-- ★ 托管模式状态指示（替代原来的DAG运行状态） -->
      <n-tag
        v-if="autopilotStatus === 'running'"
        size="small"
        type="info"
        round
        :bordered="false"
      >
        <template #icon>
          <n-spin :size="12" />
        </template>
        托管运行中
      </n-tag>
      <n-tag
        v-else-if="autopilotStatus === 'paused'"
        size="small"
        type="warning"
        round
        :bordered="false"
      >
        ⏸️ 等待审阅
      </n-tag>
      <n-tag
        v-else-if="autopilotStatus === 'completed'"
        size="small"
        type="success"
        round
        :bordered="false"
      >
        ✅ 全书完成
      </n-tag>
      <n-tag
        v-else-if="autopilotStatus === 'error'"
        size="small"
        type="error"
        round
        :bordered="false"
      >
        ❌ 托管异常
      </n-tag>
      <n-tag
        v-else
        size="small"
        type="default"
        round
        :bordered="false"
      >
        ⏹ 空闲
      </n-tag>

      <!-- SSE 连接状态 -->
      <n-tooltip trigger="hover">
        <template #trigger>
          <div class="sse-indicator" :class="{ connected: sseConnected }" />
        </template>
        {{ sseConnected ? 'SSE 实时连接正常' : 'SSE 连接断开' }}
      </n-tooltip>
    </div>

    <div class="toolbar-right">
      <!-- 版本信息 -->
      <n-text depth="3" class="toolbar-version" v-if="dagStats">
        v{{ dagStats.version || 1 }}
      </n-text>

      <!-- ★ 提示词广场入口 -->
      <n-button size="small" quaternary type="primary" @click="$emit('openPlaza')">
        🏪 广场
      </n-button>
      <!-- 验证 -->
      <n-button size="small" quaternary @click="$emit('validate')">
        ✅ 校验
      </n-button>
      <!-- 保存 -->
      <n-button size="small" quaternary @click="$emit('save')">
        <template #icon>
          <span v-if="hasUnsavedChanges" class="unsaved-dot">●</span>
        </template>
        💾 保存
      </n-button>
    </div>
  </div>
</template>

<script setup lang="ts">
const props = defineProps<{
  novelId: string
  dagStats: {
    total: number
    enabled: number
    running: number
    success: number
    error: number
    bypassed: number
    version?: number
  }
  /** ★ 托管模式状态（从 AutopilotDaemon 获取，替代原来的 DAG 运行状态） */
  autopilotStatus: 'idle' | 'running' | 'paused' | 'completed' | 'error'
  sseConnected: boolean
  /** ★ 是否有未保存的更改 */
  hasUnsavedChanges: boolean
}>()

defineEmits<{
  save: []
  validate: []
  /** ★ 打开提示词广场 */
  openPlaza: []
}>()
</script>

<style scoped>
.dag-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 6px 16px;
  border-bottom: 1px solid var(--dag-toolbar-border);
  background: var(--dag-toolbar-bg);
  gap: 12px;
  min-height: 40px;
}

.toolbar-left {
  display: flex;
  align-items: center;
  gap: 10px;
}

.toolbar-right {
  display: flex;
  align-items: center;
  gap: 8px;
}

.toolbar-title-text {
  font-size: 14px;
  color: var(--app-text-primary);
}

.toolbar-version {
  font-size: 11px;
}

/* ── SSE 连接指示灯 ── */
.sse-indicator {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--color-danger);
  transition: background 0.3s;
  flex-shrink: 0;
}

.sse-indicator.connected {
  background: var(--color-success);
  animation: dag-pulse 2s ease-in-out infinite;
}

@keyframes dag-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}

/* ── 未保存指示灯 ── */
.unsaved-dot {
  color: var(--color-danger);
  font-size: 10px;
  animation: pulse 1.5s ease-in-out infinite;
  margin-right: 4px;
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}
</style>
