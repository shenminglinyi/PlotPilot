<template>
  <div class="dag-toolbar">
    <div class="toolbar-left">
      <n-text strong class="toolbar-title-text">🧭 DAG 可视化</n-text>

      <!-- 节点统计（精简） -->
      <n-tag v-if="dagStats" size="small" round>
        {{ dagStats.total }} 节点 · {{ dagStats.enabled }} 启用
        <template v-if="dagStats.running > 0">
          · <n-text type="info">{{ dagStats.running }} 运行中</n-text>
        </template>
        <template v-if="dagStats.error > 0">
          · <n-text type="error">{{ dagStats.error }} 错误</n-text>
        </template>
      </n-tag>

      <!-- ★ 托管模式状态指示 -->
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

      <!-- SSE 连接状态 -->
      <n-tooltip trigger="hover">
        <template #trigger>
          <div class="sse-indicator" :class="{ connected: sseConnected }" />
        </template>
        {{ sseConnected ? 'SSE 实时连接正常' : 'SSE 连接断开（托管未运行时不会自动重连）' }}
      </n-tooltip>

      <n-tooltip v-if="registryGapCount > 0" trigger="hover">
        <template #trigger>
          <n-tag size="small" type="error" round>缺注册 {{ registryGapCount }}</n-tag>
        </template>
        画布上有节点类型未在引擎注册表中找到，详见上方提示条。
      </n-tooltip>
      <n-tooltip v-else-if="linkageFailed" trigger="hover">
        <template #trigger>
          <n-tag size="small" type="warning" round>联动</n-tag>
        </template>
        注册表联动接口未加载完成，广场映射可能不完整。
      </n-tooltip>
    </div>

    <div class="toolbar-right">
      <!-- 版本信息 -->
      <n-text depth="3" class="toolbar-version" v-if="dagStats">
        v{{ dagStats.version || 1 }}
      </n-text>

      <!-- ★ 卡片/DAG 切换 Switch（与标题同一排，右侧） -->
      <n-switch
        :value="true"
        @update:value="$emit('switch-to-card')"
        size="small"
      >
        <template #checked>DAG</template>
        <template #unchecked>卡片</template>
      </n-switch>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useDAGStore } from '@/stores/dagStore'

const dagStore = useDAGStore()
const registryGapCount = computed(() => dagStore.registryGaps.length)
const linkageFailed = computed(() => dagStore.registryLinkageFailed)

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
  /** ★ 托管模式状态 */
  autopilotStatus: 'idle' | 'running' | 'paused' | 'completed' | 'error'
  sseConnected: boolean
}>()

defineEmits<{
  'switch-to-card': []
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
</style>
