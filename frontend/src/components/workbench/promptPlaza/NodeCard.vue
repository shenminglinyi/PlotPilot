<template>
  <article
    class="node-card"
    :class="{ 'is-builtin': node.is_builtin, 'has-edit': node.has_user_edit }"
    role="button"
    tabindex="0"
    @click="$emit('click')"
    @keydown.enter.prevent="$emit('click')"
  >
    <div class="card-header">
      <div class="card-title-row">
        <span class="card-name" :title="node.name">{{ node.name }}</span>
        <span v-if="node.has_user_edit" class="status-pill is-edited">已调优</span>
        <span v-else-if="!node.is_builtin" class="status-pill is-custom">自定义</span>
      </div>
      <code class="card-key">{{ node.node_key }}</code>
    </div>

    <p class="card-desc">{{ node.description || '引擎底层提示词节点' }}</p>

    <div v-if="cleanTags.length" class="card-tags">
      <span v-for="tag in cleanTags" :key="tag" class="tag-chip">{{ tag }}</span>
    </div>

    <footer class="card-footer">
      <span class="footer-item numeric">v{{ node.version_count }}</span>
      <span v-if="node.variable_names.length" class="footer-item numeric">
        {{ node.variable_names.length }} 项输入槽位
      </span>
      <span v-if="node.output_format === 'json'" class="format-pill">结构化 JSON</span>
      <span class="origin-pill">{{ node.is_builtin ? '内置内核' : '本地扩展' }}</span>
    </footer>
  </article>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { PromptNode } from '../../../api/llmControl'

const props = defineProps<{
  node: PromptNode
}>()

defineEmits<{
  click: []
}>()

const cleanTags = computed(() =>
  props.node.tags.filter(t => !/^v\d+$/i.test(t.trim())).slice(0, 3),
)
</script>

<style scoped>
.node-card {
  background: var(--app-surface);
  border: 1px solid var(--app-border);
  border-radius: 12px;
  padding: 15px 16px;
  cursor: pointer;
  transition: border-color 0.16s ease, background-color 0.16s ease;
  display: flex;
  flex-direction: column;
  gap: 10px;
  outline: none;
}

.node-card:hover,
.node-card:focus-visible {
  border-color: var(--app-border-strong);
}

.node-card.has-edit {
  border-color: color-mix(in srgb, var(--color-warning) 36%, var(--app-border));
}

.card-header {
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.card-title-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.card-name {
  flex: 1;
  font-size: 14.5px;
  font-weight: 600;
  color: var(--app-text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.status-pill {
  flex-shrink: 0;
  font-size: 11.5px;
  font-weight: 600;
  padding: 1px 7px;
  border-radius: 999px;
}

.status-pill.is-edited {
  background: var(--color-warning-light);
  color: var(--color-warning);
}

.status-pill.is-custom {
  background: var(--color-brand-light);
  color: var(--color-brand);
}

.card-key {
  font-size: 12px;
  color: var(--app-text-muted);
  font-family: var(--font-mono);
}

.card-desc {
  margin: 0;
  font-size: 13.5px;
  color: var(--app-text-secondary);
  line-height: 1.56;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  min-height: 42px;
}

.card-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.tag-chip {
  font-size: 11.5px;
  padding: 2px 8px;
  border-radius: 6px;
  background: var(--app-surface-subtle);
  color: var(--app-text-secondary);
}

.card-footer {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  padding-top: 8px;
  border-top: 1px solid var(--app-divider);
  margin-top: auto;
  font-size: 12px;
  color: var(--app-text-muted);
}

.numeric {
  font-variant-numeric: tabular-nums;
}

.format-pill {
  font-size: 11px;
  padding: 1px 6px;
  border-radius: 4px;
  background: var(--color-success-light);
  color: var(--color-success);
  font-weight: 500;
}

.origin-pill {
  margin-left: auto;
  font-size: 11.5px;
  padding: 1px 7px;
  border-radius: 5px;
  background: var(--app-surface-subtle);
  color: var(--app-text-secondary);
}
</style>
