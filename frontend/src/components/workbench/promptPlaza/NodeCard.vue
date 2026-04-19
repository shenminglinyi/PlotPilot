<template>
  <div class="node-card" :class="{ 'is-builtin': node.is_builtin, 'has-edit': node.has_user_edit }" @click="$emit('click')">
    <!-- 卡片头部 -->
    <div class="card-header">
      <div class="card-title-row">
        <span class="card-name">{{ node.name }}</span>
        <n-tag
          v-if="node.output_format === 'json'"
          size="tiny"
          type="success"
          :bordered="false"
        >JSON</n-tag>
        <n-tag
          v-if="node.has_user_edit"
          size="tiny"
          type="warning"
          :bordered="false"
        >已修改</n-tag>
      </div>
      <div class="card-key">{{ node.node_key }}</div>
    </div>

    <!-- 描述 -->
    <div class="card-desc">{{ node.description || '暂无描述' }}</div>

    <!-- 变量标签 -->
    <div class="card-vars" v-if="node.variable_names.length">
      <span class="var-label">变量:</span>
      <n-tag
        v-for="vname in displayedVars"
        :key="vname"
        size="tiny"
        :bordered="false"
        type="info"
        round
      >
        {{ '{' + vname + '}' }}
      </n-tag>
      <span v-if="node.variable_names.length > 3" class="more-vars">
        +{{ node.variable_names.length - 3 }}
      </span>
    </div>

    <!-- 标签 -->
    <div class="card-tags" v-if="node.tags.length">
      <n-tag
        v-for="tag in node.tags.slice(0, 4)"
        :key="tag"
        size="tiny"
        :bordered="false"
      >{{ tag }}</n-tag>
    </div>

    <!-- 底部信息 -->
    <div class="card-footer">
      <span class="footer-item version-badge" :title="`${node.version_count} 个版本`">
        v.{{ node.version_count }}
      </span>
      <span class="footer-item source-text" :title="node.source">
        {{ sourceLabel }}
      </span>
      <span v-if="node.is_builtin" class="builtin-badge">内置</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { NTag } from 'naive-ui'
import type { PromptNode } from '../../../api/llmControl'

const props = defineProps<{
  node: PromptNode
}>()

defineEmits<{
  click: []
}>()

const displayedVars = computed(() => props.node.variable_names.slice(0, 3))

const sourceLabel = computed(() => {
  const src = props.node.source
  if (!src) return ''
  // 提取文件名
  const lastPart = src.split(':').pop() || src
  return lastPart.length > 30 ? '...' + lastPart.slice(-30) : lastPart
})
</script>

<style scoped>
.node-card {
  background: var(--app-surface);
  border: 1px solid var(--app-border);
  border-radius: 10px;
  padding: 14px;
  cursor: pointer;
  transition: all 0.2s ease;
  display: flex;
  flex-direction: column;
  gap: 8px;
  position: relative;
}
.node-card:hover {
  border-color: var(--color-brand);
  box-shadow: var(--app-shadow-md);
  transform: translateY(-2px);
}
.node-card.is-builtin {
  border-left: 3px solid var(--color-brand);
}
.node-card.has-edit {
  border-left: 3px solid var(--color-warning);
}

/* 头部 */
.card-header {
  flex-shrink: 0;
}
.card-title-row {
  display: flex;
  align-items: center;
  gap: 6px;
}
.card-name {
  font-size: 14px;
  font-weight: 600;
  color: var(--app-text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.card-key {
  font-size: 11px;
  color: var(--app-text-muted);
  font-family: var(--font-mono, 'SF Mono', 'Fira Code', monospace);
}

/* 描述 */
.card-desc {
  font-size: 12px;
  color: var(--app-text-secondary);
  line-height: 1.5;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  min-height: 36px;
}

/* 变量 */
.card-vars {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 4px;
}
.var-label {
  font-size: 11px;
  color: var(--app-text-muted);
  margin-right: 2px;
}
.more-vars {
  font-size: 11px;
  color: var(--app-text-muted);
}

/* 标签 */
.card-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

/* 底部 */
.card-footer {
  display: flex;
  align-items: center;
  gap: 10px;
  padding-top: 8px;
  border-top: 1px solid var(--app-border);
  margin-top: auto;
}
.footer-item {
  font-size: 11px;
  color: var(--app-text-muted);
}
.version-badge {
  font-weight: 500;
}
.source-text {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 140px;
  flex: 1;
}
.builtin-badge {
  font-size: 10px;
  background: linear-gradient(135deg, var(--color-brand), var(--color-purple));
  color: var(--app-text-inverse);
  padding: 1px 6px;
  border-radius: 4px;
  font-weight: 600;
  letter-spacing: 0.5px;
}
</style>
