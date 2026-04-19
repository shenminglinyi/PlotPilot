<template>
  <div class="ktte-root">
    <div class="ktte-toolbar">
      <n-space>
        <n-button size="small" quaternary :loading="loading" @click="reload">刷新</n-button>
        <n-button type="primary" size="small" :loading="saving" @click="save">保存到知识库</n-button>
      </n-space>
    </div>

    <section class="ktte-section">
      <div class="ktte-head">
        <span class="ktte-icon">◎</span>
        <span class="ktte-title">知识三元组</span>
        <n-tag size="tiny" round :bordered="false" class="ktte-tag-tool">PUT /knowledge</n-tag>
      </div>
      <p class="ktte-hint">
        保存时提交<strong>全书全部</strong>三元组；下列筛选仅影响展示。
        <strong>人物：</strong>「主—是—主角/配角」作节点；「甲—师徒/敌对—乙」作关系。
        <strong>地点：</strong>实体类型选「地点」；圣经同步的「位于 / 地图地点」亦在此编辑。
      </p>

      <div class="ktte-filter">
        <n-text depth="3" style="font-size: 12px">筛选 · 共 {{ factStats.total }} 条</n-text>
        <n-radio-group v-model:value="editorFilter" size="small">
          <n-radio-button value="all">全部</n-radio-button>
          <n-radio-button value="character">人物 ({{ factStats.character }})</n-radio-button>
          <n-radio-button value="location">地点 ({{ factStats.location }})</n-radio-button>
        </n-radio-group>
        <n-checkbox
          v-if="focusNorm"
          v-model:checked="restrictFocus"
          size="small"
          style="margin-left: 4px"
        >
          仅显示涉及「{{ focusNorm }}」
        </n-checkbox>
      </div>

      <div class="ktte-facts">
        <div v-for="{ f, i: fi } in filteredEditorRows" :key="f.id" class="ktte-fact">
          <div class="ktte-fact-id">{{ f.id }}</div>
          <div class="ktte-fact-grid">
            <n-input v-model:value="f.subject" placeholder="主语" size="small" />
            <n-input v-model:value="f.predicate" placeholder="关系" size="small" />
            <n-input v-model:value="f.object" placeholder="宾语" size="small" />
            <n-input-number
              v-model:value="f.chapter_id"
              placeholder="章号"
              size="small"
              :min="1"
              :show-button="false"
              class="ktte-fact-ch"
            />
            <n-input v-model:value="f.note" placeholder="备注" size="small" class="ktte-fact-note" />
          </div>
          <div class="ktte-fact-meta">
            <n-select
              v-model:value="f.entity_type"
              :options="entityTypeOptions"
              placeholder="实体类型"
              size="small"
              clearable
              class="ktte-fact-select"
            />
            <n-select
              v-model:value="f.importance"
              :options="getImportanceOptions(f.entity_type)"
              placeholder="重要程度"
              size="small"
              clearable
              class="ktte-fact-select"
              :disabled="!f.entity_type"
            />
            <n-select
              v-if="f.entity_type === 'location'"
              v-model:value="f.location_type"
              :options="locationTypeOptions"
              placeholder="地点类型"
              size="small"
              clearable
              class="ktte-fact-select"
            />
          </div>
          <n-button size="tiny" quaternary type="error" @click="removeFact(fi)">删除</n-button>
        </div>
      </div>
      <n-button dashed block class="ktte-add" @click="addFact">+ 添加三元组</n-button>
    </section>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { useMessage } from 'naive-ui'
import { knowledgeApi, type ChapterSummary, type KnowledgeTriple } from '../../api/knowledge'

const props = withDefaults(
  defineProps<{
    slug: string
    /** 打开时的默认实体筛选 */
    defaultEntityFilter?: 'all' | 'character' | 'location'
    /** 与图谱节点联动：仅展示主/宾语等于该名的行（可勾选关闭） */
    focusEntityName?: string
  }>(),
  {
    defaultEntityFilter: 'all',
    focusEntityName: '',
  },
)

const emit = defineEmits<{
  saved: []
}>()

const message = useMessage()

interface Fact {
  id: string
  subject: string
  predicate: string
  object: string
  chapter_id?: number | null
  note?: string
  entity_type?: 'character' | 'location' | null
  importance?: string | null
  location_type?: string | null
  description?: string | null
  first_appearance?: number | null
  related_chapters?: number[]
  tags?: string[]
  attributes?: Record<string, unknown>
  source_type?: string | null
  subject_entity_id?: string | null
  object_entity_id?: string | null
  confidence?: number | null
}

const entityTypeOptions = [
  { label: '人物', value: 'character' },
  { label: '地点', value: 'location' },
]

const characterImportanceOptions = [
  { label: '主角', value: 'primary' },
  { label: '重要配角', value: 'secondary' },
  { label: '次要人物', value: 'minor' },
]

const locationImportanceOptions = [
  { label: '核心地点', value: 'core' },
  { label: '重要地点', value: 'important' },
  { label: '一般地点', value: 'normal' },
]

const locationTypeOptions = [
  { label: '城市', value: 'city' },
  { label: '区域', value: 'region' },
  { label: '建筑', value: 'building' },
  { label: '势力', value: 'faction' },
  { label: '领域', value: 'realm' },
]

const getImportanceOptions = (entityType?: string | null) => {
  if (entityType === 'character') return characterImportanceOptions
  if (entityType === 'location') return locationImportanceOptions
  return []
}

const loading = ref(false)
const saving = ref(false)
const facts = ref<Fact[]>([])
const storyVersion = ref(1)
const premiseLock = ref('')
const chaptersSnapshot = ref<ChapterSummary[]>([])
const editorFilter = ref<'all' | 'character' | 'location'>(props.defaultEntityFilter)
const restrictFocus = ref(false)

const focusNorm = computed(() => (props.focusEntityName || '').trim())

watch(
  () => props.defaultEntityFilter,
  v => {
    editorFilter.value = v
  },
)

watch(
  focusNorm,
  n => {
    restrictFocus.value = Boolean(n)
  },
  { immediate: true },
)

const factStats = computed(() => {
  let character = 0
  let location = 0
  for (const f of facts.value) {
    if (f.entity_type === 'character') character += 1
    else if (f.entity_type === 'location') location += 1
  }
  return { character, location, total: facts.value.length }
})

const filteredEditorRows = computed(() => {
  let rows = facts.value.map((f, i) => ({ f, i }))
  if (editorFilter.value !== 'all') {
    rows = rows.filter(({ f }) => f.entity_type === editorFilter.value)
  }
  if (restrictFocus.value && focusNorm.value) {
    const n = focusNorm.value
    rows = rows.filter(
      ({ f }) => (f.subject || '').trim() === n || (f.object || '').trim() === n,
    )
  }
  return rows
})

const reload = async () => {
  loading.value = true
  try {
    const data = await knowledgeApi.getKnowledge(props.slug)
    storyVersion.value = data.version ?? 1
    premiseLock.value = data.premise_lock ?? ''
    chaptersSnapshot.value = Array.isArray(data.chapters) ? [...data.chapters] : []
    facts.value = (data.facts || []) as Fact[]
  } catch (e: unknown) {
    const err = e as { response?: { data?: { detail?: string } } }
    message.error(err?.response?.data?.detail || '加载失败')
  } finally {
    loading.value = false
  }
}

const addFact = () => {
  const newId = `fact_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`
  const presetType =
    props.defaultEntityFilter === 'character' || props.defaultEntityFilter === 'location'
      ? props.defaultEntityFilter
      : null
  facts.value.push({
    id: newId,
    subject: '',
    predicate: '',
    object: '',
    chapter_id: null,
    note: '',
    entity_type: presetType,
    importance: null,
    location_type: null,
  })
}

const removeFact = (index: number) => {
  facts.value.splice(index, 1)
}

const save = async () => {
  saving.value = true
  try {
    await knowledgeApi.putKnowledge(props.slug, {
      version: storyVersion.value,
      premise_lock: premiseLock.value,
      chapters: chaptersSnapshot.value,
      facts: facts.value as KnowledgeTriple[],
    })
    message.success('已保存')
    await reload()
    emit('saved')
  } catch (e: unknown) {
    const err = e as { response?: { data?: { detail?: string } } }
    message.error(err?.response?.data?.detail || '保存失败')
  } finally {
    saving.value = false
  }
}

watch(
  () => props.slug,
  () => {
    void reload()
  },
)

onMounted(() => {
  void reload()
})
</script>

<style scoped>
.ktte-root {
  padding: 12px 16px 24px;
  max-width: 1100px;
}

.ktte-toolbar {
  margin-bottom: 16px;
}

.ktte-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.ktte-icon {
  font-size: 16px;
  color: var(--color-brand);
}

.ktte-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--app-text-primary);
}

.ktte-tag-tool {
  font-size: 11px;
  background: var(--app-surface-subtle);
  color: var(--app-text-muted);
}

.ktte-hint {
  font-size: 12px;
  color: var(--app-text-muted);
  margin: 0 0 16px;
  line-height: 1.6;
}

.ktte-filter {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px;
  margin-bottom: 14px;
  padding: 8px 10px;
  border-radius: 8px;
  background: var(--color-brand-light);
  border: 1px solid var(--color-brand-border);
}

.ktte-facts {
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin-bottom: 16px;
}

.ktte-fact {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 12px;
  background: var(--app-surface-subtle);
  border-radius: 8px;
  border: 1px solid var(--app-border);
}

.ktte-fact-id {
  font-size: 11px;
  color: var(--app-text-muted);
  font-family: monospace;
}

.ktte-fact-grid {
  display: grid;
  grid-template-columns: 1fr 1fr 1fr 100px 1.5fr;
  gap: 8px;
}

.ktte-fact-meta {
  display: flex;
  gap: 8px;
  align-items: center;
  flex-wrap: wrap;
}

.ktte-fact-select {
  flex: 1;
  min-width: 120px;
}

.ktte-fact-ch {
  width: 100px;
}

.ktte-fact-note {
  grid-column: span 2;
}

.ktte-add {
  margin-top: 8px;
}
</style>
