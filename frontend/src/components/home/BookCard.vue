<script setup lang="ts">
/**
 * BookCard — 书目卡片。首页主区（单行横滑）与「全部书目」弹窗共用，
 * 替代原先复制两份的模板；宽度由父级容器决定。
 */
import { h } from 'vue'
import { NButton, NCheckbox, NIcon, NPopconfirm, NTag } from 'naive-ui'
import { getNovelStageTagType } from '@/domain/novel'

interface BookListItem {
  slug: string
  title: string
  stage: string
  stage_label: string
  genre: string
  chapter_count?: number
  word_count?: number
}

const props = withDefaults(
  defineProps<{
    book: BookListItem
    selected?: boolean
    deleting?: boolean
    /** 主区卡片带多选框；弹窗卡片只有删除 */
    selectable?: boolean
  }>(),
  { selected: false, deleting: false, selectable: true },
)

const emit = defineEmits<{
  (e: 'open'): void
  (e: 'select', value: boolean): void
  (e: 'delete'): void
}>()

const IconTrash = () =>
  h('svg', { xmlns: 'http://www.w3.org/2000/svg', viewBox: '0 0 24 24', width: '1em', height: '1em' },
    h('path', { fill: 'currentColor', d: 'M6 19c0 1.1.9 2 2 2h8c1.1 0 2-.9 2-2V7H6v12zM19 4h-3.5l-1-1h-5l-1 1H5v2h14V4z' }))

const formatWordCount = (count: number): string => {
  if (count >= 10000) {
    return (count / 10000).toFixed(1) + '万字'
  }
  return count + '字'
}
</script>

<template>
  <div
    class="book-card"
    :class="{ 'is-selected': props.selected }"
    @click="emit('open')"
  >
    <div class="card-top">
      <span class="book-dot" :class="`dot-${book.stage}`"></span>
      <span class="book-card-title">{{ book.title }}</span>
    </div>
    <div class="card-meta">
      <n-tag :type="getNovelStageTagType(book.stage)" size="small" round borderable>
        {{ book.stage_label }}
      </n-tag>
      <span class="meta-genre">{{ book.genre || '未分类' }}</span>
    </div>
    <div class="card-stats" v-if="book.chapter_count || book.word_count">
      <template v-if="book.chapter_count">
        <span>{{ book.chapter_count }} 章</span>
      </template>
      <template v-if="book.word_count">
        <span>{{ formatWordCount(book.word_count) }}</span>
      </template>
    </div>
    <div class="card-actions" @click.stop>
      <n-checkbox
        v-if="selectable"
        :checked="selected"
        @update:checked="(val: boolean) => emit('select', val)"
      />
      <n-popconfirm
        positive-text="删除"
        negative-text="取消"
        @positive-click="emit('delete')"
      >
        <template #trigger>
          <n-button
            quaternary
            circle
            size="tiny"
            type="error"
            :loading="deleting"
            aria-label="删除书目"
          >
            <template #icon>
              <n-icon><IconTrash /></n-icon>
            </template>
          </n-button>
        </template>
        将删除「{{ book.title }}」及本地全部章节与设定，且不可恢复。确定删除吗？
      </n-popconfirm>
    </div>
  </div>
</template>

<style scoped>
.book-card {
  position: relative;
  display: flex;
  flex-direction: column;
  width: 100%;
  padding: 18px 18px 14px;
  background: var(--app-surface);
  border: 1px solid var(--app-border);
  border-radius: var(--app-radius-md);
  cursor: pointer;
  transition: border-color var(--app-transition), box-shadow var(--app-transition), transform var(--app-transition);
  animation: book-fade-up 0.35s ease both;
  overflow: hidden;
}

.book-card:hover {
  border-color: var(--color-brand-border);
  box-shadow: var(--app-shadow-md);
  transform: translateY(-1px);
}

.book-card.is-selected {
  border-color: var(--color-brand-border);
  background: var(--color-brand-light);
}

/* 阶段状态小圆点 */
.book-dot {
  width: 9px;
  height: 9px;
  border-radius: 50%;
  flex-shrink: 0;
  display: inline-block;
}

.book-dot.dot-planning { background: var(--color-brand); }
.book-dot.dot-writing { background: #f59e0b; }
.book-dot.dot-reviewing { background: var(--color-seal); }
.book-dot.dot-completed { background: #10b981; }

/* 卡片顶部：标题 + 圆点 */
.card-top {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
}

.book-card-title {
  font-size: 15px;
  font-weight: 650;
  color: var(--app-text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  line-height: 1.3;
}

/* 卡片元信息行：标签 + 类型 */
.card-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
  flex-wrap: wrap;
}

.meta-genre {
  font-size: 12px;
  color: var(--app-text-muted);
}

/* 卡片统计信息 */
.card-stats {
  display: flex;
  gap: 10px;
  font-size: 12px;
  color: var(--app-text-muted);
  font-variant-numeric: tabular-nums;
  margin-bottom: 12px;
  flex: 1;
}

/* 卡片操作按钮 */
.card-actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 6px;
  opacity: 0;
  transition: opacity 0.18s ease;
  padding-top: 4px;
}

.book-card:hover .card-actions,
.book-card:focus-within .card-actions {
  opacity: 1;
}

@keyframes book-fade-up {
  from {
    opacity: 0;
    transform: translateY(10px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

@media (prefers-reduced-motion: reduce) {
  .book-card {
    animation: none;
  }
}

/* 移动端触屏没有 hover，操作区常显 */
@media (max-width: 768px) {
  .card-actions {
    opacity: 1;
  }
}
</style>
