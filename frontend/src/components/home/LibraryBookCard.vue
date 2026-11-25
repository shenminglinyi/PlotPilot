<template>
  <!-- 目录卡片：完整书目信息（自 pw fe BookCard 移植，去掉 pw 专属的
       setup_status/content_kind/复制工作台——开源 API 无此数据与能力） -->
  <article
    class="library-book-card"
    :class="{ 'is-selected': selected, 'is-busy': deleting, 'is-selecting': selectionMode }"
    :style="{ animationDelay: `${index * 0.035}s` }"
    role="button"
    tabindex="0"
    :aria-selected="selectionMode ? selected : undefined"
    @click="handleCardActivate"
    @keydown.enter.prevent="handleCardActivate"
    @keydown.space.prevent="handleCardActivate"
  >
    <div class="library-book-card__top">
      <button
        v-if="selectionMode"
        type="button"
        class="library-book-card__select"
        :class="{ 'is-checked': selected }"
        :aria-pressed="selected"
        :aria-label="selected ? `取消选择《${book.title}》` : `选择《${book.title}》`"
        @click.stop="emit('update:selected', !selected)"
      >
        <svg v-if="selected" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" aria-hidden="true">
          <path d="M20 6 9 17l-5-5" />
        </svg>
      </button>
      <span v-else class="library-book-card__dot" :class="`dot-${book.stage}`" />
      <span class="library-book-card__title">{{ book.title }}</span>
      <div class="library-book-card__quick-actions" @click.stop>
        <n-popconfirm positive-text="删除" negative-text="取消" @positive-click="emit('delete', book.slug)">
          <template #trigger>
            <n-button quaternary circle size="tiny" type="error" :loading="deleting" aria-label="删除书目">
              <template #icon>
                <n-icon><IconTrash /></n-icon>
              </template>
            </n-button>
          </template>
          将删除《{{ book.title }}》及本地全部章节与设定，且不可恢复。确定删除吗？
        </n-popconfirm>
      </div>
    </div>

    <div class="library-book-card__meta">
      <n-tag size="small" round :bordered="false" class="library-book-card__stage">
        {{ book.stage_label }}
      </n-tag>
      <span class="library-book-card__genre">{{ book.genre || '未分类' }}</span>
    </div>

    <p v-if="book.premise" class="library-book-card__premise">{{ book.premise }}</p>

    <div v-if="book.chapter_count || book.word_count" class="library-book-card__stats">
      <span v-if="book.chapter_count">{{ book.chapter_count }} 章</span>
      <span v-if="book.target_chapters">目标 {{ book.target_chapters }} 章</span>
      <span v-if="book.word_count">{{ formatWordCount(book.word_count) }}</span>
    </div>
    <div v-else class="library-book-card__stats library-book-card__stats--empty">等待开篇</div>
  </article>
</template>

<script setup lang="ts">
import { h } from 'vue'
import { NButton, NIcon, NPopconfirm, NTag } from 'naive-ui'
import type { DeckBookItem } from '@/components/home/ProjectDeck.vue'

const props = withDefaults(
  defineProps<{
    book: DeckBookItem
    index?: number
    selected?: boolean
    selectionMode?: boolean
    deleting?: boolean
  }>(),
  { index: 0, selected: false, selectionMode: false, deleting: false }
)
const emit = defineEmits<{
  'update:selected': [value: boolean]
  open: [slug: string]
  delete: [slug: string]
}>()

// 1. 激活语义按模式分叉：批量模式勾选/取消勾选；浏览模式直接打开书
function handleCardActivate() {
  if (props.selectionMode) emit('update:selected', !props.selected)
  else emit('open', props.book.slug)
}

function formatWordCount(count: number): string {
  if (count >= 10000) return (count / 10000).toFixed(1) + '万字'
  return count + '字'
}

const IconTrash = () =>
  h('svg', { xmlns: 'http://www.w3.org/2000/svg', viewBox: '0 0 24 24', width: '1em', height: '1em' },
    h('path', { fill: 'currentColor', d: 'M6 19c0 1.1.9 2 2 2h8c1.1 0 2-.9 2-2V7H6v12zM19 4h-3.5l-1-1h-5l-1 1H5v2h14V4z' }))
</script>

<style scoped>
.library-book-card {
  position: relative;
  display: grid;
  gap: 8px;
  padding: 14px 16px;
  border: 1px solid var(--app-border);
  border-radius: 12px;
  background: var(--app-surface);
  cursor: pointer;
  overflow: hidden;
  animation: library-card-enter 0.34s ease both;
  transition: border-color 0.18s ease, box-shadow 0.18s ease, transform 0.18s ease;
}

.library-book-card:hover,
.library-book-card:focus-visible {
  border-color: var(--color-brand);
  box-shadow: var(--app-shadow-md);
  transform: translateY(-1px);
}

.library-book-card.is-selected {
  border-color: var(--color-brand);
  box-shadow: 0 0 0 2px color-mix(in srgb, var(--color-brand) 22%, transparent);
}

.library-book-card.is-busy {
  opacity: 0.6;
  pointer-events: none;
}

@keyframes library-card-enter {
  from { opacity: 0; transform: translateY(8px); }
  to { opacity: 1; transform: translateY(0); }
}

.library-book-card__top {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.library-book-card__dot {
  flex: none;
  width: 8px;
  height: 8px;
  border-radius: 50%;
}

/* 阶段灯：固定语义色，不随主题换肤（与书架/工作台一致） */
.dot-planning { background: #f59e0b; }
.dot-writing { background: #2563eb; }
.dot-review { background: #8b5cf6; }
.dot-completed { background: #10b981; }

.library-book-card__select {
  flex: none;
  display: grid;
  place-items: center;
  width: 18px;
  height: 18px;
  border: 1.5px solid var(--app-border-strong, var(--app-border));
  border-radius: 5px;
  background: var(--app-surface);
  color: #fff;
  cursor: pointer;
  padding: 0;
}

.library-book-card__select.is-checked {
  background: var(--color-brand);
  border-color: var(--color-brand);
}

.library-book-card__select svg {
  width: 12px;
  height: 12px;
}

.library-book-card__title {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-weight: 600;
  font-size: 15px;
  color: var(--app-text-primary);
}

.library-book-card__quick-actions {
  flex: none;
  opacity: 0;
  transition: opacity 0.15s ease;
}

.library-book-card:hover .library-book-card__quick-actions,
.library-book-card.is-busy .library-book-card__quick-actions,
.library-book-card__select.is-checked ~ .library-book-card__quick-actions {
  opacity: 1;
}

.library-book-card__meta {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.library-book-card__stage {
  flex: none;
}

.library-book-card__genre {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 12px;
  color: var(--app-text-muted);
}

.library-book-card__premise {
  margin: 0;
  font-size: 12.5px;
  line-height: 1.55;
  color: var(--app-text-secondary, var(--app-text-muted));
  display: -webkit-box;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
  overflow: hidden;
}

.library-book-card__stats {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 12px;
  color: var(--app-text-muted);
}

.library-book-card__stats--empty {
  color: var(--app-text-muted);
  opacity: 0.7;
}

@media (prefers-reduced-motion: reduce) {
  .library-book-card {
    animation: none;
    transition: none;
  }
}
</style>
