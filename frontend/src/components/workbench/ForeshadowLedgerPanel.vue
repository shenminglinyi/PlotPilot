<template>
  <div class="fsw-panel pp-panel">

    <!-- ── Header ────────────────────────────────────── -->
    <header class="pp-panel-header">
      <div class="pp-panel-header-main">
        <div style="display:flex;align-items:center;gap:8px">
          <span class="pp-panel-title">伏笔账本</span>
          <span v-if="pendingCount > 0" class="pp-chip pp-chip--warning">{{ pendingCount }} 待兑现</span>
          <span v-if="consumedEntries.length > 0" class="pp-chip pp-chip--muted">{{ consumedEntries.length }} 已消费</span>
          <n-tooltip>
            <template #trigger>
              <span class="fsw-help-icon">?</span>
            </template>
            <div style="font-size:12px;line-height:1.6;max-width:200px">
              伏笔 ≈ 主角（或读者）当下的疑问；在本阶段兑现并与爽点挂钩即可，不必写论文。
            </div>
          </n-tooltip>
        </div>
      </div>
      <div class="pp-panel-actions">
        <n-button size="small" type="primary" @click="openCreateModal">+ 添加</n-button>
        <n-tooltip>
          <template #trigger>
            <n-button size="tiny" quaternary :loading="loading" @click="load">
              <template #icon><n-icon size="13"><RefreshOutline /></n-icon></template>
            </n-button>
          </template>
          刷新
        </n-tooltip>
      </div>
    </header>

    <!-- ── Filter strip ──────────────────────────────── -->
    <div class="pp-filter-strip">
      <button
        class="pp-filter-btn"
        :class="{ 'pp-filter-btn--active': activeFilter === 'all' }"
        @click="activeFilter = 'all'; filterCharacter = null"
      >全部</button>
      <button
        v-if="props.currentChapterNumber != null"
        class="pp-filter-btn"
        :class="{ 'pp-filter-btn--active': activeFilter === 'due' }"
        @click="activeFilter = 'due'; filterCharacter = null"
      >本章到期 ↑</button>
      <n-select
        v-if="characterOptions.length > 0"
        v-model:value="filterCharacter"
        :options="characterOptions"
        size="tiny"
        placeholder="按角色"
        clearable
        style="width:90px;flex-shrink:0"
        @update:value="(val: string | null) => { if (val) activeFilter = 'char'; else if (activeFilter === 'char') activeFilter = 'all' }"
      />
    </div>

    <!-- ── Tab toggle ─────────────────────────────────── -->
    <div class="fsw-tabs">
      <n-tabs v-model:value="activeTab" type="segment" size="small">
        <n-tab name="pending">
          待兑现
          <n-badge v-if="pendingCount > 0" :value="pendingCount" :max="99" type="warning" style="margin-left:6px" />
        </n-tab>
        <n-tab name="consumed">已消费</n-tab>
      </n-tabs>
    </div>

    <!-- ── Content ────────────────────────────────────── -->
    <div class="fsw-content pp-panel-content" style="padding:10px 12px">

      <!-- First-load skeleton -->
      <div v-if="!dataLoaded && loading" class="fsw-skeleton">
        <n-skeleton text :rows="3" />
        <n-skeleton text :rows="3" style="margin-top:10px" />
        <n-skeleton text :rows="3" style="margin-top:10px" />
      </div>

      <n-spin v-else :show="loading && dataLoaded">

        <!-- Pending tab -->
        <template v-if="activeTab === 'pending'">
          <div v-if="filteredPending.length === 0" class="pp-empty">
            <span class="pp-empty-icon">🪄</span>
            <span class="pp-empty-text">{{ activeFilter === 'due' ? '本章无到期伏笔' : '暂无待兑现伏笔' }}</span>
            <n-button v-if="activeFilter === 'all'" size="small" secondary @click="openCreateModal">+ 添加伏笔</n-button>
          </div>
          <div v-else class="pp-card-list">
            <div
              v-for="entry in filteredPending"
              :key="entry.id"
              class="pp-accent-bar fsw-card"
              :style="{
                '--pp-accent-color': importanceAccentColor(entry.importance),
                background: entry.is_priority_for_chapter ? 'var(--color-warning-dim)' : 'var(--app-surface)',
              }"
            >
              <!-- Row 1: importance + question + star -->
              <div class="fsw-card-top">
                <span class="pp-chip" :class="importanceChipClass(entry.importance)" style="font-size:10px;flex-shrink:0">
                  {{ importanceLabel(entry.importance) }}
                </span>
                <span class="fsw-question">{{ entry.question }}</span>
                <n-button
                  size="tiny"
                  text
                  :type="entry.is_priority_for_chapter ? 'warning' : 'default'"
                  :title="entry.is_priority_for_chapter ? '取消本章重点' : '标为本章重点（保证进入 AI 上下文）'"
                  :loading="priorityLoadingId === entry.id"
                  @click="togglePriority(entry)"
                >{{ entry.is_priority_for_chapter ? '★' : '☆' }}</n-button>
              </div>
              <!-- Row 2: meta + actions -->
              <div class="fsw-card-meta">
                <span class="pp-chip pp-chip--muted" style="font-size:10px">第{{ entry.chapter }}章</span>
                <span v-if="entry.character_id" class="pp-chip pp-chip--brand" style="font-size:10px">{{ entry.character_id }}</span>
                <span v-if="entry.suggested_resolve_chapter" class="fsw-resolve-hint">
                  → 第{{ entry.suggested_resolve_chapter }}章兑现
                </span>
                <div style="margin-left:auto;display:flex;gap:4px;align-items:center">
                  <n-tooltip>
                    <template #trigger>
                      <n-button size="tiny" text type="success" :loading="consumingId === entry.id" @click="markConsumed(entry)">✓</n-button>
                    </template>
                    标记已消费
                  </n-tooltip>
                  <n-button size="tiny" secondary @click="openEditModal(entry)">编辑</n-button>
                  <n-popconfirm @positive-click="remove(entry.id)">
                    <template #trigger>
                      <n-button size="tiny" type="error" tertiary>删</n-button>
                    </template>
                    确认删除这条伏笔？
                  </n-popconfirm>
                </div>
              </div>
            </div>
          </div>
        </template>

        <!-- Consumed tab -->
        <template v-else>
          <div v-if="consumedEntries.length === 0" class="pp-empty">
            <span class="pp-empty-icon">✅</span>
            <span class="pp-empty-text">暂无已消费伏笔</span>
          </div>
          <div v-else class="pp-card-list">
            <div
              v-for="entry in consumedEntries"
              :key="entry.id"
              class="fsw-card fsw-card--consumed"
            >
              <div class="fsw-card-top">
                <span class="pp-chip pp-chip--success" style="font-size:10px">✓ 已消费</span>
                <span class="fsw-question fsw-question--consumed">{{ entry.question }}</span>
              </div>
              <div class="fsw-card-meta" style="margin-top:4px">
                <span class="pp-chip pp-chip--muted" style="font-size:10px">第{{ entry.chapter }}章埋</span>
                <span style="font-size:11px;color:var(--app-text-muted)">→</span>
                <span class="pp-chip pp-chip--success" style="font-size:10px">第{{ entry.consumed_at_chapter }}章兑现</span>
              </div>
            </div>
          </div>
        </template>
      </n-spin>
    </div>

    <!-- ── Create/Edit modal ──────────────────────────── -->
    <n-modal v-model:show="showModal" preset="card" :title="editingEntry ? '编辑伏笔' : '添加伏笔'" style="width:min(520px,96vw)">
      <n-form :model="form" label-placement="left" label-width="80" :show-feedback="false">
        <n-space vertical :size="12">
          <n-form-item label="当下的疑问">
            <n-input
              v-model:value="form.question"
              placeholder="例：他为何总在雨夜出门？（一句话即可）"
              type="textarea"
              :autosize="{ minRows: 2, maxRows: 5 }"
            />
          </n-form-item>
          <n-form-item label="关联角色">
            <n-input v-model:value="form.character_id" placeholder="角色名或 ID" />
          </n-form-item>
          <n-form-item label="埋入章节">
            <n-input-number v-model:value="form.chapter" :min="1" style="width:100%" />
          </n-form-item>
          <n-form-item label="重要程度">
            <n-select v-model:value="form.importance" :options="importanceOptions" />
          </n-form-item>
          <n-form-item label="预计兑现章">
            <n-input-number v-model:value="form.suggested_resolve_chapter" :min="1" clearable placeholder="可选" style="width:100%" />
          </n-form-item>
        </n-space>
      </n-form>
      <template #action>
        <n-space justify="end" :size="8">
          <n-button @click="showModal = false">取消</n-button>
          <n-button type="primary" :loading="saving" @click="handleSubmit">
            {{ editingEntry ? '保存' : '添加' }}
          </n-button>
        </n-space>
      </template>
    </n-modal>

    <!-- ── Consume chapter modal ──────────────────────── -->
    <n-modal v-model:show="showConsumeModal" preset="card" title="标记已消费" style="width:340px">
      <n-form label-placement="left" label-width="80" :show-feedback="false">
        <n-form-item label="兑现章节">
          <n-input-number v-model:value="consumeChapter" :min="1" style="width:100%" />
        </n-form-item>
      </n-form>
      <template #action>
        <n-space justify="end" :size="8">
          <n-button @click="showConsumeModal = false">取消</n-button>
          <n-button type="success" :loading="saving" @click="confirmConsumed">确认</n-button>
        </n-space>
      </template>
    </n-modal>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { RefreshOutline } from '@vicons/ionicons5'
import { useWorkbenchRefreshStore } from '../../stores/workbenchRefreshStore'
import { useMessage } from 'naive-ui'
import { foreshadowApi } from '../../api/foreshadow'
import type { ForeshadowEntry } from '../../api/foreshadow'

interface Props {
  slug: string
  currentChapterNumber?: number | null
}
const props = withDefaults(defineProps<Props>(), { currentChapterNumber: null })
const emit = defineEmits<{ 'pending-count': [count: number] }>()
const message = useMessage()

// ── state ───────────────────────────────────────────────────────
const loading = ref(false)
const saving = ref(false)
const dataLoaded = ref(false)
const entries = ref<ForeshadowEntry[]>([])
const activeTab = ref<'pending' | 'consumed'>('pending')
const activeFilter = ref<'all' | 'due' | 'char'>('all')
const filterCharacter = ref<string | null>(null)
const consumingId = ref<string | null>(null)
const priorityLoadingId = ref<string | null>(null)

let loadSeq = 0

// ── computed ────────────────────────────────────────────────────
const pendingEntries = computed(() => entries.value.filter(e => e.status === 'pending'))
const consumedEntries = computed(() => entries.value.filter(e => e.status === 'consumed'))
const pendingCount = computed(() => pendingEntries.value.length)

const characterOptions = computed(() => {
  const ids = [...new Set(pendingEntries.value.map(e => e.character_id).filter(Boolean))]
  return ids.map(id => ({ label: id, value: id }))
})

const filteredPending = computed(() => {
  let list = pendingEntries.value
  if (activeFilter.value === 'due' && props.currentChapterNumber != null) {
    const ch = props.currentChapterNumber
    list = list.filter(f => f.suggested_resolve_chapter != null && f.suggested_resolve_chapter <= ch + 2)
  }
  if (activeFilter.value === 'char' && filterCharacter.value) {
    list = list.filter(f => f.character_id === filterCharacter.value)
  }
  return list.slice().sort((a, b) => {
    if (a.is_priority_for_chapter !== b.is_priority_for_chapter)
      return a.is_priority_for_chapter ? -1 : 1
    const order: Record<string, number> = { critical: 4, high: 3, medium: 2, low: 1 }
    return (order[b.importance] ?? 2) - (order[a.importance] ?? 2)
  })
})

// ── helpers ─────────────────────────────────────────────────────
function importanceLabel(imp: string): string {
  return ({ critical: '危急', high: '重要', medium: '一般', low: '次要' } as Record<string, string>)[imp] ?? imp
}
function importanceChipClass(imp: string): string {
  return ({ critical: 'pp-chip--danger', high: 'pp-chip--warning', medium: 'pp-chip--brand', low: 'pp-chip--muted' } as Record<string, string>)[imp] ?? 'pp-chip--muted'
}
function importanceAccentColor(imp: string): string {
  return ({ critical: 'var(--color-danger)', high: 'var(--color-warning)', medium: 'var(--color-brand)', low: 'var(--app-border)' } as Record<string, string>)[imp] ?? 'var(--app-border)'
}

const importanceOptions = [
  { label: '危急', value: 'critical' },
  { label: '重要', value: 'high' },
  { label: '一般', value: 'medium' },
  { label: '次要', value: 'low' },
]

// ── load ─────────────────────────────────────────────────────────
const load = async () => {
  const seq = ++loadSeq
  const slug = props.slug
  loading.value = true
  try {
    const result = await foreshadowApi.list(slug)
    if (seq !== loadSeq || props.slug !== slug) return
    entries.value = result
  } catch {
    if (seq !== loadSeq || props.slug !== slug) return
    message.error('加载伏笔账本失败')
  } finally {
    if (seq === loadSeq) {
      loading.value = false
      dataLoaded.value = true
    }
  }
}

// ── CRUD ─────────────────────────────────────────────────────────
const showModal = ref(false)
const editingEntry = ref<ForeshadowEntry | null>(null)
const form = ref({
  question: '',
  character_id: '',
  chapter: 1,
  importance: 'medium' as ForeshadowEntry['importance'],
  suggested_resolve_chapter: null as number | null,
})

const openCreateModal = () => {
  editingEntry.value = null
  form.value = { question: '', character_id: '', chapter: props.currentChapterNumber ?? 1, importance: 'medium', suggested_resolve_chapter: null }
  showModal.value = true
}

const openEditModal = (entry: ForeshadowEntry) => {
  editingEntry.value = entry
  form.value = {
    question: entry.question,
    character_id: entry.character_id,
    chapter: entry.chapter,
    importance: entry.importance,
    suggested_resolve_chapter: entry.suggested_resolve_chapter,
  }
  showModal.value = true
}

const handleSubmit = async () => {
  if (!form.value.question.trim()) { message.warning('请填写当下的疑问'); return }
  if (!form.value.character_id.trim()) { message.warning('请输入关联角色'); return }
  saving.value = true
  try {
    if (editingEntry.value) {
      await foreshadowApi.update(props.slug, editingEntry.value.id, {
        question: form.value.question,
        character_id: form.value.character_id,
        chapter: form.value.chapter,
        importance: form.value.importance,
        suggested_resolve_chapter: form.value.suggested_resolve_chapter ?? undefined,
      })
      message.success('已保存')
    } else {
      await foreshadowApi.create(props.slug, {
        entry_id: `fsw-${Date.now()}`,
        question: form.value.question,
        character_id: form.value.character_id,
        chapter: form.value.chapter,
        importance: form.value.importance,
        suggested_resolve_chapter: form.value.suggested_resolve_chapter ?? undefined,
      })
      message.success('已添加')
    }
    showModal.value = false
    await load()
  } catch {
    message.error('保存失败')
  } finally {
    saving.value = false
  }
}

// ── Consume ───────────────────────────────────────────────────
const showConsumeModal = ref(false)
const consumingEntry = ref<ForeshadowEntry | null>(null)
const consumeChapter = ref(1)

const markConsumed = (entry: ForeshadowEntry) => {
  consumingEntry.value = entry
  consumeChapter.value = (props.currentChapterNumber ?? entry.chapter) + 1
  showConsumeModal.value = true
}

const confirmConsumed = async () => {
  if (!consumingEntry.value) return
  saving.value = true
  try {
    await foreshadowApi.markConsumed(props.slug, consumingEntry.value.id, consumeChapter.value)
    message.success('已标记为已消费')
    showConsumeModal.value = false
    await load()
  } catch {
    message.error('操作失败')
  } finally {
    saving.value = false
  }
}

// ── Star priority ─────────────────────────────────────────────
const togglePriority = async (entry: ForeshadowEntry) => {
  priorityLoadingId.value = entry.id
  try {
    const newVal = !entry.is_priority_for_chapter
    await foreshadowApi.update(props.slug, entry.id, { is_priority_for_chapter: newVal })
    const idx = entries.value.findIndex(e => e.id === entry.id)
    if (idx !== -1) entries.value[idx] = { ...entries.value[idx], is_priority_for_chapter: newVal }
  } catch {
    message.error('操作失败')
  } finally {
    priorityLoadingId.value = null
  }
}

const remove = async (id: string) => {
  try {
    await foreshadowApi.remove(props.slug, id)
    message.success('已删除')
    entries.value = entries.value.filter(e => e.id !== id)
  } catch {
    message.error('删除失败')
  }
}

// ── lifecycle ─────────────────────────────────────────────────
const { foreshadowTick } = storeToRefs(useWorkbenchRefreshStore())

onMounted(load)
watch(pendingCount, n => emit('pending-count', n), { immediate: true })
watch(foreshadowTick, () => void load())
watch(() => props.slug, () => void load())
</script>

<style scoped>
.fsw-panel { /* pp-panel 基础已有 */ }

.fsw-help-icon {
  width: 15px;
  height: 15px;
  border-radius: 50%;
  background: var(--app-border);
  color: var(--app-text-muted);
  font-size: 10px;
  font-weight: 700;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  cursor: help;
  flex-shrink: 0;
}

/* tabs strip */
.fsw-tabs {
  flex-shrink: 0;
  padding: 8px 12px 5px;
  background: var(--app-surface);
  border-bottom: 1px solid var(--plotpilot-split-border);
}

.fsw-content {
  /* pp-panel-content provides scrolling */
}

.fsw-skeleton { padding: 4px 0; }

/* ── Entry card ────────────────────────────────────── */
.fsw-card {
  border-radius: var(--app-radius-md, 10px);
  background: var(--app-surface);
  border: 1px solid var(--app-border);
  padding: 7px 10px 7px 10px;
  transition: border-color 0.15s, box-shadow 0.15s;
}

.fsw-card:hover {
  border-color: var(--app-border-strong);
  box-shadow: var(--app-shadow-sm);
}

.fsw-card--consumed {
  opacity: 0.82;
  padding: 7px 10px;
}

.fsw-card-top {
  display: flex;
  align-items: center;
  gap: 5px;
}

.fsw-question {
  flex: 1;
  min-width: 0;
  font-size: 12px;
  font-weight: 600;
  color: var(--app-text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.fsw-question--consumed {
  font-weight: 500;
  color: var(--app-text-secondary);
}

.fsw-card-meta {
  display: flex;
  align-items: center;
  gap: 5px;
  margin-top: 5px;
  flex-wrap: wrap;
}

.fsw-resolve-hint {
  font-size: 11px;
  color: var(--app-text-muted);
}
</style>
