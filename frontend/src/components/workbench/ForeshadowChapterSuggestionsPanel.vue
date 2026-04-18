<template>
  <div class="fs-suggestions" :class="{ 'fs-suggestions--embedded': embedded, 'fs-suggestions--compact': compact }">
    <n-empty v-if="!currentChapterNumber" description="请先选择章节" size="small" />

    <template v-else>
      <n-spin :show="loading" size="small">
        <n-text v-if="hintText" depth="3" class="fs-hint">{{ hintText }}</n-text>
        <n-empty v-if="!loading && items.length === 0" description="暂无待兑现疑问" size="small" />
        <n-space v-else-if="items.length" vertical :size="8">
          <n-card
            v-for="row in items.slice(0, compact ? 5 : 12)"
            :key="row.entry.id"
            size="small"
            :bordered="true"
            class="fs-item-card"
          >
            <n-space align="flex-start" :size="8">
              <n-checkbox
                :checked="picked.has(row.entry.id)"
                @update:checked="(v: boolean) => togglePick(row.entry.id, v)"
              />
              <div style="flex: 1; min-width: 0">
                <n-space align="center" :size="6" wrap>
                  <n-tag size="tiny" round>第{{ row.entry.chapter }}章埋入</n-tag>
                  <n-tag v-if="row.distance != null" size="tiny" round type="info">
                    距本章 {{ row.distance === 0 ? '同章' : `${row.distance} 章` }}
                  </n-tag>
                </n-space>
                <p class="clue-text">{{ row.entry.question }}</p>
              </div>
            </n-space>
          </n-card>
        </n-space>
      </n-spin>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, onMounted, computed } from 'vue'
import { foreshadowApi } from '../../api/foreshadow'
import type { ForeshadowEntry } from '../../api/foreshadow'

const props = withDefaults(
  defineProps<{
    slug: string
    currentChapterNumber?: number | null
    embedded?: boolean
    compact?: boolean
    /** 保留兼容，不再请求后端 */
    prefillOutline?: string
    autoRun?: boolean
  }>(),
  { currentChapterNumber: null, embedded: false, compact: false, prefillOutline: '', autoRun: false }
)

const loading = ref(false)
const entries = ref<ForeshadowEntry[]>([])
const picked = ref<Set<string>>(new Set())

const hintText = computed(() =>
  props.autoRun
    ? '与「伏笔账本」同源：列出待兑现疑问，按与当前章的距离排序（近者优先）。'
    : ''
)

type Row = { entry: ForeshadowEntry; distance: number | null }

const items = computed<Row[]>(() => {
  const ch = props.currentChapterNumber
  if (ch == null) return []
  const pending = entries.value.filter((e) => e.status === 'pending')
  const rows: Row[] = pending.map((e) => ({
    entry: e,
    distance: Math.abs(e.chapter - ch),
  }))
  rows.sort((a, b) => {
    if (a.distance !== b.distance) return (a.distance ?? 0) - (b.distance ?? 0)
    return a.entry.chapter - b.entry.chapter
  })
  return rows
})

function togglePick(id: string, on: boolean) {
  const next = new Set(picked.value)
  if (on) next.add(id)
  else next.delete(id)
  picked.value = next
}

async function load() {
  if (!props.slug) return
  loading.value = true
  try {
    entries.value = await foreshadowApi.list(props.slug)
    picked.value = new Set()
  } finally {
    loading.value = false
  }
}

watch(
  () => [props.slug, props.currentChapterNumber] as const,
  () => {
    void load()
  },
  { immediate: true }
)

onMounted(() => {
  void load()
})
</script>

<style scoped>
.fs-suggestions {
  width: 100%;
}
.fs-suggestions--embedded.fs-suggestions--compact .fs-item-card {
  margin-bottom: 0;
}
.fs-hint {
  display: block;
  font-size: 11px;
  margin-bottom: 8px;
  line-height: 1.45;
}
.clue-text {
  margin: 6px 0 0;
  font-size: 13px;
  line-height: 1.5;
  color: var(--app-text-primary);
}
</style>
