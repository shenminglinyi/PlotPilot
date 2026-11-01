<template>
  <!-- 书目管理弹层：书架舞台之外的完整书目录（自 pw fe HomeLibraryModal 移植）。
       舞台看「当下在读什么」，这里管「全部藏书」：搜索、批量管理、删除。 -->
  <n-modal
    :show="show"
    preset="card"
    class="home-library-modal"
    :style="{ width: 'min(1080px, 94vw)' }"
    :bordered="true"
    @update:show="emit('update:show', $event)"
  >
    <template #header>
      <div class="home-library-modal__header">
        <div>
          <span>书目管理</span>
          <strong>全部书目</strong>
        </div>
        <n-tag size="small" :bordered="false">{{ books.length }} 本</n-tag>
      </div>
    </template>

    <div class="home-library-modal__toolbar">
      <n-input v-model:value="query" placeholder="搜索书名或类型" clearable>
        <template #prefix>
          <n-icon><IconSearch /></n-icon>
        </template>
      </n-input>
      <n-button v-if="!selectionMode" secondary @click="selectionMode = true">批量管理</n-button>
      <template v-else>
        <span>已选 {{ selected.length }} 本</span>
        <n-button type="error" secondary :disabled="!selected.length" @click="emit('request-delete', selected)">
          删除
        </n-button>
        <n-button tertiary @click="clearSelection">完成</n-button>
      </template>
    </div>

    <div class="home-library-modal__grid">
      <LibraryBookCard
        v-for="(book, index) in filteredBooks"
        :key="book.slug"
        :book="book"
        :index="index"
        :selected="selected.includes(book.slug)"
        :selection-mode="selectionMode"
        :deleting="deletingSlug === book.slug"
        @open="emit('open', $event)"
        @update:selected="toggleSelected(book.slug, $event)"
        @delete="emit('request-delete', [book.slug])"
      />
      <button v-if="!filteredBooks.length" type="button" class="home-library-modal__empty" @click="emit('new-book')">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true">
          <path d="M5 12h14" />
          <path d="M12 5v14" />
        </svg>
        <strong>{{ query ? '没有匹配的书目' : '建立第一本书' }}</strong>
      </button>
    </div>
  </n-modal>
</template>

<script setup lang="ts">
import { computed, h, ref, watch } from 'vue'
import { NButton, NIcon, NInput, NModal, NTag } from 'naive-ui'
import LibraryBookCard from '@/components/home/LibraryBookCard.vue'
import type { DeckBookItem } from '@/components/home/ProjectDeck.vue'

const props = defineProps<{
  show: boolean
  books: DeckBookItem[]
  deletingSlug?: string | null
}>()
const emit = defineEmits<{
  'update:show': [show: boolean]
  open: [slug: string]
  'request-delete': [slugs: string[]]
  'new-book': []
}>()

const query = ref('')
const selectionMode = ref(false)
const selected = ref<string[]>([])

const filteredBooks = computed(() => {
  const normalized = query.value.trim().toLowerCase()
  if (!normalized) return props.books
  return props.books.filter(
    book =>
      book.title.toLowerCase().includes(normalized) ||
      book.genre.toLowerCase().includes(normalized)
  )
})

// 1. 单本勾选：进入 selected 集合（去重）；取消则剔除
function toggleSelected(slug: string, value: boolean) {
  if (value) selected.value = Array.from(new Set([...selected.value, slug]))
  else selected.value = selected.value.filter(item => item !== slug)
}

// 2. 退出批量模式时清空选择，避免下次进入残留旧勾选
function clearSelection() {
  selected.value = []
  selectionMode.value = false
}

// 3. 书目列表变化（删除/新建）时同步收缩勾选集，防止对已删书发起操作
watch(
  () => props.books.map(book => book.slug),
  slugs => {
    const existing = new Set(slugs)
    selected.value = selected.value.filter(slug => existing.has(slug))
  }
)

// 4. 弹层关闭即复位（搜索词、批量模式、勾选），下次打开是干净状态
watch(
  () => props.show,
  visible => {
    if (!visible) {
      query.value = ''
      clearSelection()
    }
  }
)

const IconSearch = () =>
  h('svg', { xmlns: 'http://www.w3.org/2000/svg', viewBox: '0 0 24 24', width: '1em', height: '1em' },
    h('path', { fill: 'none', stroke: 'currentColor', 'stroke-width': 2, 'stroke-linecap': 'round', 'stroke-linejoin': 'round', d: 'M11 19a8 8 0 1 0 0-16 8 8 0 0 0 0 16zm10 2-4.35-4.35' }))
</script>

<style scoped>
.home-library-modal__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.home-library-modal__header > div {
  display: grid;
  gap: 4px;
}

.home-library-modal__header span {
  color: var(--app-text-muted);
  font-size: 11px;
}

.home-library-modal__header strong {
  color: var(--app-text-primary);
  font-size: 16px;
}

.home-library-modal__toolbar {
  display: flex;
  align-items: center;
  gap: 9px;
  margin-bottom: 14px;
}

.home-library-modal__toolbar .n-input {
  max-width: 330px;
}

.home-library-modal__toolbar > span {
  margin-left: auto;
  color: var(--app-text-muted);
  font-size: 12px;
}

.home-library-modal__grid {
  max-height: min(550px, 64vh);
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(248px, 1fr));
  gap: 12px;
  overflow: auto;
  padding: 2px;
}

.home-library-modal__empty {
  min-height: 180px;
  display: grid;
  place-content: center;
  gap: 9px;
  border: 1px dashed var(--app-border-strong, var(--app-border));
  border-radius: 8px;
  background: transparent;
  color: var(--app-text-muted);
  cursor: pointer;
}

.home-library-modal__empty svg {
  justify-self: center;
  width: 22px;
  height: 22px;
}

@media (max-width: 820px) {
  .home-library-modal__toolbar {
    flex-wrap: wrap;
  }
  .home-library-modal__toolbar .n-input {
    max-width: none;
    flex: 1;
  }
  .home-library-modal__grid {
    grid-template-columns: 1fr;
  }
}
</style>
