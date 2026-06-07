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

      <div class="mtp-classify-strip">
        <div class="mtp-classify-item">
          <span class="mtp-mini-label">市场大类</span>
          <strong>{{ activeMajorLabel }}</strong>
        </div>
        <div class="mtp-classify-item">
          <span class="mtp-mini-label">细分主题</span>
          <strong>{{ activeThemeLabel || '未选择' }}</strong>
        </div>
        <div class="mtp-classify-item mtp-classify-item--wide">
          <span class="mtp-mini-label">赛道属性</span>
          <strong>{{ activeMarketTrack || '未配置' }}</strong>
        </div>
        <div class="mtp-classify-item">
          <span class="mtp-mini-label">引擎大类</span>
          <strong>{{ themeAgentKeyDisplay || 'theme:other' }}</strong>
        </div>
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
        <span class="mtp-k">④ 写作原则</span>
        <span class="mtp-hint">四个大类均按当前主题独立生成，可修改</span>
      </div>
      <div class="mtp-writing-grid">
        <div
          v-for="item in writingPrincipleCards"
          :key="item.key"
          class="mtp-principle-card"
        >
          <div class="mtp-principle-head">
            <span class="mtp-principle-index">{{ item.index }}</span>
            <div class="mtp-principle-title">
              <strong>{{ item.title }}</strong>
              <span>{{ item.scope }}</span>
            </div>
          </div>
          <p class="mtp-principle-note">{{ item.note }}</p>
          <n-input
            type="textarea"
            :autosize="{ minRows: 8, maxRows: 18 }"
            v-model:value="item.model.value"
            :disabled="disabled"
            :placeholder="item.title"
            class="mtp-world-input mtp-principle-input"
          />
        </div>
      </div>
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
  writingProfileForSelection,
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
const storyStructure = defineModel<string>('storyStructure', { default: '' })
const pacingControl = defineModel<string>('pacingControl', { default: '' })
const writingStyle = defineModel<string>('writingStyle', { default: '' })
const specialRequirements = defineModel<string>('specialRequirements', { default: '' })

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

const activeTheme = computed(() => {
  const major = activeMajor.value
  const id = pickedThemeId.value
  if (!major || !id) return undefined
  return major.children?.find((c) => c.id === id)
})

const activeMajorLabel = computed(() => {
  return activeMajor.value ? pickLocaleLabel(activeMajor.value, props.locale) : ''
})

const activeThemeLabel = computed(() => {
  return activeTheme.value ? pickLocaleLabel(activeTheme.value, props.locale) : ''
})

const activeMarketTrack = computed(() => {
  const raw = activeMajor.value?.facets?.market_track
  return typeof raw === 'string' ? raw : ''
})

const writingPrincipleCards = computed(() => [
  {
    key: 'story_structure',
    index: '01',
    title: '剧情结构',
    scope: `${activeMajorLabel.value || '大类'} / ${activeThemeLabel.value || '主题'} 的开篇、发展、高潮、结尾`,
    note: '沿用四段框架，但切入点、推进对象、高潮落点和续作伏笔必须落到主题主句。',
    model: storyStructure,
  },
  {
    key: 'pacing_control',
    index: '02',
    title: '节奏把控',
    scope: `${activeMarketTrack.value || '赛道'} 的小 / 中 / 大爽点排布`,
    note: '不按固定字数阈值切分，按具体压力、选择、可见回报和新增代价安排触发点。',
    model: pacingControl,
  },
  {
    key: 'writing_style',
    index: '03',
    title: '写作风格',
    scope: `${activeThemeLabel.value || '主题'} 的叙事、环境描写、人物对话`,
    note: '分别约束叙事推进、场景质感和角色声口，避免只套用大类通用语气。',
    model: writingStyle,
  },
  {
    key: 'special_requirements',
    index: '04',
    title: '特殊要求',
    scope: `${activeMajorLabel.value || '大类'} / ${activeThemeLabel.value || '主题'} 的专属创作细则`,
    note: '围绕大类、主题主句和赛道约束定制禁忌与要求，避免只复述分类名。',
    model: specialRequirements,
  },
])

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
  worldPreset.value = worldToneForSelection(root, first)
  applyWritingProfile(root, first)
}

function pickTheme(root: TaxonomyNode, leaf: TaxonomyNode) {
  pickedThemeId.value = leaf.id
  genre.value = marketMajorThemeGenre(root, leaf, props.locale)
  worldPreset.value = worldToneForSelection(root, leaf)
  applyWritingProfile(root, leaf)
}

function applyWritingProfile(root: TaxonomyNode, leaf: TaxonomyNode | undefined) {
  const profile = writingProfileForSelection(root, leaf)
  storyStructure.value = profile.story_structure?.trim() || ''
  pacingControl.value = profile.pacing_control?.trim() || ''
  writingStyle.value = profile.writing_style?.trim() || ''
  specialRequirements.value = profile.special_requirements?.trim() || ''
}

const themeAgentKeyDisplay = computed(() => {
  const r = activeMajor.value
  if (!r || !pickedThemeId.value) return ''
  const k = themeAgentKeyForSelection(r)
  return k ? `theme:${k}` : ''
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
.mtp-mini-label {
  display: block;
  margin-bottom: 3px;
  font-size: 11px;
  font-weight: 700;
  color: var(--app-text-muted);
}
.mtp-classify-strip {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 8px;
  margin-top: 10px;
}
.mtp-classify-item {
  min-width: 0;
  padding: 10px 12px;
  border-radius: 8px;
  background: var(--app-surface-subtle);
  border: 1px solid var(--app-border);
}
.mtp-classify-item--wide {
  grid-column: span 2;
}
.mtp-classify-item strong {
  display: block;
  min-width: 0;
  overflow-wrap: anywhere;
  font-size: 12px;
  line-height: 1.45;
  color: var(--app-text-primary);
}
.mtp-world-input :deep(textarea) {
  font-size: 14px;
  line-height: 1.75;
  white-space: pre-wrap;
}
.mtp-writing-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}
.mtp-principle-input :deep(textarea) {
  padding: 14px 16px;
}
.mtp-principle-card {
  min-width: 0;
  padding: 12px;
  border-radius: 8px;
  background: rgba(15, 23, 42, 0.025);
  border: 1px solid var(--app-border);
}
.mtp-principle-head {
  display: flex;
  align-items: flex-start;
  gap: 9px;
  margin-bottom: 7px;
}
.mtp-principle-index {
  flex: 0 0 auto;
  width: 28px;
  height: 22px;
  border-radius: 7px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 11px;
  font-weight: 800;
  color: #2563eb;
  background: rgba(37, 99, 235, 0.09);
  border: 1px solid rgba(37, 99, 235, 0.16);
}
.mtp-principle-title {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.mtp-principle-title strong {
  font-size: 13px;
  color: var(--app-text-primary);
}
.mtp-principle-title span,
.mtp-principle-note {
  font-size: 11px;
  line-height: 1.45;
  color: var(--app-text-muted);
}
.mtp-principle-note {
  margin: 0 0 9px;
}
@media (max-width: 900px) {
  .mtp-classify-strip,
  .mtp-writing-grid {
    grid-template-columns: 1fr;
  }
  .mtp-classify-item--wide {
    grid-column: auto;
  }
}
.mtp-empty-search {
  text-align: center;
  padding: 16px;
  font-size: 13px;
  color: var(--app-text-muted);
}
</style>
