<template>
  <div class="mtp" :class="{ 'mtp--busy': disabled }">
    <div class="mtp-toolbar">
      <n-input
        v-model:value="searchQuery"
        clearable
        round
        size="medium"
        placeholder="搜索大类、主题关键词（如「电竞」「废土」「谍战」）…"
        :disabled="disabled"
      >
        <template #prefix>
          <n-icon :component="IconSearch" />
        </template>
      </n-input>
    </div>

    <div class="mtp-section-head">
      <span class="mtp-k">① 大类</span>
      <span v-if="searchQuery.trim()" class="mtp-hint">已过滤 {{ filteredMajors.length }} / {{ rootsCount }}</span>
    </div>
    <div class="mtp-major-row">
      <n-button
        v-for="maj in filteredMajors"
        :key="maj.id"
        size="small"
        round
        strong
        :secondary="pickedMajorId !== maj.id"
        :type="pickedMajorId === maj.id ? 'primary' : 'default'"
        :disabled="disabled"
        class="mtp-major-chip"
        @click="pickMajor(maj)"
      >
        {{ pickLocaleLabel(maj, locale) }}
      </n-button>
    </div>

    <div v-if="activeMajor" class="mtp-detail">
      <div class="mtp-section-head mtp-mt">
        <span class="mtp-k">② 网文主题</span>
      </div>
      <div class="mtp-theme-row">
        <template v-if="activeMajor.children?.length">
          <n-button
            v-for="ch in activeMajor.children"
            :key="ch.id"
            text
            size="tiny"
            :type="pickedThemeId === ch.id ? 'primary' : 'default'"
            class="mtp-theme-chip"
            :disabled="disabled"
            @click="pickTheme(activeMajor!, ch)"
          >
            {{ pickLocaleLabel(ch, locale) }}
          </n-button>
        </template>
        <template v-else>
          <n-text depth="3" style="font-size: 13px">该大类暂无细分节点</n-text>
        </template>
      </div>

      <div class="mtp-track" v-if="activeMajor.facets?.market_track">
        <span class="mtp-mini-label">赛道</span>
        <span class="mtp-track-txt">{{ activeMajor.facets.market_track }}</span>
      </div>

      <div class="mtp-section-head mtp-mt">
        <span class="mtp-k">③ 世界观基调</span>
        <span class="mtp-hint">可修改，重写后仍为「预设 + 自定义」语义</span>
      </div>
      <n-input
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 12 }"
        v-model:value="worldPreset"
        :disabled="disabled"
        placeholder="先选择一大类与一个主题…"
        class="mtp-world-input"
      />

      <div class="mtp-section-head mtp-mt">
        <span class="mtp-k">④ 类型字符串（建档字段）</span>
      </div>
      <n-input :value="genre" readonly :disabled="disabled" placeholder="例：玄幻 / 东方玄幻">
        <template #suffix>
          <n-tooltip v-if="themeAgentTooltip" placement="top-end">
            <template #trigger>
              <span class="mtp-engine-hint">{{ themeAgentKeyDisplay }}</span>
            </template>
            {{ themeAgentTooltip }}
          </n-tooltip>
        </template>
      </n-input>
    </div>
    <div v-else-if="filteredMajors.length === 0" class="mtp-empty-search">
      <span>没有找到匹配的分类，换一个关键词试试</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, h, ref, watch } from 'vue'
import type { TaxonomyNode } from '@/domain/taxonomy/types'
import {
  flattenRootsForSearch,
  marketMajorThemeGenre,
  worldToneForSelection,
  themeAgentKeyForSelection,
  BUILTIN_CN_MARKET_V1,
} from '@/domain/taxonomy/cnMarket'
import { pickLocaleLabel } from '@/domain/taxonomy/types'

const IconSearch = () =>
  h(
    'svg',
    { xmlns: 'http://www.w3.org/2000/svg', viewBox: '0 0 24 24', width: '1em', height: '1em' },
    h('path', {
      fill: 'currentColor',
      d: 'M15.5 14h-.79l-.28-.27A6.471 6.471 0 0 0 16 9.5 6.5 6.5 0 1 0 9.5 16c1.61 0 3.09-.59 4.23-1.57l.27.28v.79l5 4.99L20.49 19l-4.99-5zm-6 0C7.01 14 5 11.99 5 9.5S7.01 5 9.5 5 14 7.01 14 9.5 11.99 14 9.5 14z',
    }),
  )

const props = withDefaults(
  defineProps<{
    locale?: string
    disabled?: boolean
  }>(),
  {
    locale: 'zh-CN',
    disabled: false,
  }
)

const genre = defineModel<string>('genre', { default: '' })
const worldPreset = defineModel<string>('worldPreset', { default: '' })

const roots = BUILTIN_CN_MARKET_V1.roots
const rootsCount = computed(() => roots.length)
const searchTable = flattenRootsForSearch(roots)

const searchQuery = ref('')
const pickedMajorId = ref<string | null>(null)
const pickedThemeId = ref<string | null>(null)

function norm(s: string) {
  return s.trim().toLowerCase()
}

const filteredMajors = computed(() => {
  const q = norm(searchQuery.value)
  if (!q) return roots
  const out: TaxonomyNode[] = []
  for (const hit of searchTable) {
    if (hit.scoreAid.includes(q)) {
      out.push(hit.root)
    }
  }
  return out.length ? out : []
})

const activeMajor = computed(() => {
  const id = pickedMajorId.value
  if (!id) return undefined
  return roots.find((r) => r.id === id)
})

watch(filteredMajors, (list) => {
  if (!pickedMajorId.value) return
  if (!list.some((x) => x.id === pickedMajorId.value)) {
    pickedMajorId.value = list[0]?.id ?? null
    pickedThemeId.value = null
  }
})

function syncFromGenreString() {
  const g = (genre.value || '').trim()
  if (!g.includes('/')) return
  const [a, b] = g.split(/\s*\/\s*/)
  const majorLabel = (a || '').trim()
  const themeLabel = (b || '').trim()
  for (const r of roots) {
    if (pickLocaleLabel(r, props.locale) !== majorLabel) continue
    pickedMajorId.value = r.id
    const leaf = r.children?.find((c) => pickLocaleLabel(c, props.locale) === themeLabel)
    if (leaf) {
      pickedThemeId.value = leaf.id
      return
    }
  }
}

watch(
  () => genre.value,
  () => {
    if (!pickedMajorId.value && (genre.value || '').includes('/')) {
      syncFromGenreString()
    }
  },
  { immediate: false }
)

function pickMajor(root: TaxonomyNode) {
  pickedMajorId.value = root.id
  const first = root.children?.[0]
  pickedThemeId.value = first?.id ?? null

  genre.value = first ? marketMajorThemeGenre(root, first, props.locale) : ''
  worldPreset.value = worldToneForSelection(root)
}

function pickTheme(root: TaxonomyNode, leaf: TaxonomyNode) {
  pickedThemeId.value = leaf.id
  genre.value = marketMajorThemeGenre(root, leaf, props.locale)
  worldPreset.value = worldToneForSelection(root)
}

const themeAgentKeyDisplay = computed(() => {
  const r = activeMajor.value
  if (!r || !pickedThemeId.value) return ''
  const k = themeAgentKeyForSelection(r)
  return k ? `theme:${k}` : ''
})

const themeAgentTooltip = computed(() => {
  const k = themeAgentKeyDisplay.value
  return k ? '供后台 Theme Agent 匹配的体裁路由键（与引擎注册表对应）' : ''
})

</script>

<style scoped>
.mtp {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.mtp--busy {
  opacity: 0.72;
}
.mtp-toolbar {
  margin-bottom: 8px;
}
.mtp-section-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 12px;
  margin-top: 4px;
  margin-bottom: 8px;
}
.mtp-mt {
  margin-top: 10px;
}
.mtp-k {
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.06em;
  color: var(--app-text-secondary);
}
.mtp-hint {
  font-size: 11px;
  color: var(--app-text-muted);
}
.mtp-major-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  padding: 12px;
  border-radius: 12px;
  background: rgba(79, 70, 229, 0.04);
  border: 1px solid rgba(79, 70, 229, 0.12);
}
.mtp-major-chip {
  transition: transform 0.14s ease;
}
.mtp-major-chip:hover {
  transform: translateY(-1px);
}
.mtp-detail {
  margin-top: 6px;
  padding-top: 2px;
}
.mtp-theme-row {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  align-items: center;
  padding-bottom: 4px;
}
.mtp-theme-chip {
  padding: 0 6px !important;
  border-radius: 999px !important;
  font-weight: 600 !important;
}
.mtp-track {
  font-size: 12px;
  line-height: 1.55;
  color: var(--app-text-secondary);
  padding: 10px 12px;
  border-radius: 10px;
  background: var(--app-surface-subtle);
  border-left: 3px solid rgba(139, 92, 246, 0.6);
}
.mtp-mini-label {
  display: inline-block;
  margin-right: 8px;
  font-size: 11px;
  font-weight: 700;
  color: var(--app-text-muted);
}
.mtp-track-txt {
  display: inline;
}
.mtp-world-input :deep(textarea) {
  font-size: 13px;
}
.mtp-engine-hint {
  font-size: 11px;
  color: var(--app-text-muted);
  font-family: ui-monospace, monospace;
}
.mtp-empty-search {
  text-align: center;
  padding: 16px;
  font-size: 13px;
  color: var(--app-text-muted);
}
</style>
