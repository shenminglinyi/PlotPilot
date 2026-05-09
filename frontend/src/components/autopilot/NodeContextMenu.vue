<template>
  <Teleport to="body">
    <div
      v-if="visible"
      class="node-context-menu"
      :style="menuStyle"
      @click.stop
    >
      <!-- 节点信息头 -->
      <div class="menu-header">
        <n-text strong style="font-size: 13px">{{ nodeTypeLabel }}</n-text>
      </div>
      <div class="menu-divider" />

      <!-- 操作项 -->
      <div class="menu-item" @click="$emit('edit', nodeId)">
        ✏️ 编辑 Prompt
      </div>
      <div class="menu-item" @click="$emit('rerun', nodeId)">
        🔄 从此节点重跑
      </div>
      <div class="menu-divider" />
      <div class="menu-item" :class="{ 'menu-item-warning': nodeEnabled }" @click="$emit('toggle', nodeId)">
        {{ nodeEnabled ? '⛔ 禁用此节点' : '✅ 启用此节点' }}
      </div>
      <div class="menu-divider" />
      <div class="menu-item" @click="$emit('viewUpstream', nodeId)">
        🔗 查看上游
      </div>
      <div class="menu-item" @click="$emit('viewDownstream', nodeId)">
        🔗 查看下游
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useDAGStore } from '@/stores/dagStore'
import { CATEGORY_LABELS } from '@/types/dag'

const props = defineProps<{
  x: number
  y: number
  nodeId: string
  nodeEnabled: boolean
  nodeType: string
}>()

defineEmits<{
  close: []
  edit: [nodeId: string]
  toggle: [nodeId: string]
  rerun: [nodeId: string]
  viewUpstream: [nodeId: string]
  viewDownstream: [nodeId: string]
}>()

const dagStore = useDAGStore()

const nodeTypeLabel = computed(() => {
  if (!props.nodeType) return props.nodeId
  const meta = dagStore.nodeTypeRegistry[props.nodeType]
  if (meta) {
    const catLabel = CATEGORY_LABELS[meta.category] || meta.category
    return `${meta.icon} ${meta.display_name} (${catLabel})`
  }
  return props.nodeType
})

// 确保菜单不超出视口
const menuStyle = computed(() => {
  const maxX = window.innerWidth - 200
  const maxY = window.innerHeight - 250
  return {
    left: `${Math.min(props.x, maxX)}px`,
    top: `${Math.min(props.y, maxY)}px`,
  }
})
</script>

<style scoped>
.node-context-menu {
  position: fixed;
  z-index: 9999;
  background: var(--n-color-popover, #2d2d3f);
  border: 1px solid var(--n-border-color, #3f3f5f);
  border-radius: 8px;
  padding: 4px 0;
  min-width: 180px;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.3);
}

.menu-header {
  padding: 8px 16px 4px;
}

.menu-item {
  padding: 8px 16px;
  cursor: pointer;
  font-size: 13px;
  transition: background 0.15s;
}

.menu-item:hover {
  background: rgba(59, 130, 246, 0.1);
}

.menu-item-warning:hover {
  background: rgba(245, 158, 11, 0.1);
}

.menu-divider {
  height: 1px;
  background: var(--n-border-color, #3f3f5f);
  margin: 4px 0;
}
</style>
