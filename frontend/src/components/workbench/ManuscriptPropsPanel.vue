<template>
  <div class="mpp-panel pp-panel">

    <!-- ── Header ──────────────────────────────── -->
    <header class="pp-panel-header">
      <div class="pp-panel-header-main">
        <span class="pp-panel-title">手稿道具</span>
      </div>
      <n-button size="small" type="primary" @click="openCreate">+ 新建</n-button>
    </header>

    <!-- ── Syntax hint (collapsed by default) ───── -->
    <div class="mpp-hint-wrap">
      <n-collapse>
        <n-collapse-item name="hint">
          <template #header>
            <span class="mpp-hint-trigger">
              <n-icon size="12"><InformationCircleOutline /></n-icon>
              用法提示
            </span>
          </template>
          <div class="mpp-hint-body">
            正文可写 <code class="mpp-code">[[prop:道具ID|显示名]]</code> 引用道具；
            保存章节后系统自动统计本章出现的角色 / 地点 / 势力 / 道具（零 token）。
          </div>
        </n-collapse-item>
      </n-collapse>
    </div>

    <!-- ── Scrollable content ─────────────────── -->
    <div class="pp-panel-content mpp-body">

      <!-- 1. 本章实体索引（仅有 currentChapter 时显示） -->
      <div v-if="currentChapterNumber != null" class="pp-section mpp-section">
        <div class="pp-section-header">
          <div class="wb-icon-badge" style="background:#6366f1">
            <n-icon size="14"><BookmarkOutline /></n-icon>
          </div>
          <span class="pp-section-label">本章实体索引</span>
          <span class="pp-chip pp-chip--muted" style="font-size:10px;margin-left:4px">自动</span>
          <div style="margin-left:auto">
            <n-button-group size="tiny">
              <n-button :loading="mentionLoading" @click="loadMentions">刷新</n-button>
              <n-dropdown trigger="click" :options="reindexOptions" @select="handleSyncSelect">
                <n-button style="padding:0 6px">▾</n-button>
              </n-dropdown>
            </n-button-group>
          </div>
        </div>
        <div class="pp-section-body">
          <div v-if="!mentions.length && !mentionLoading" class="mpp-empty-hint">
            尚无索引，保存章节或「从正文重建」
          </div>
          <div v-else class="mpp-tag-cloud">
            <n-tooltip
              v-for="m in mentions"
              :key="`${m.entity_kind}-${m.entity_id}`"
              placement="bottom"
            >
              <template #trigger>
                <n-tag size="small" :type="kindTagType(m.entity_kind)" round style="cursor:default">
                  {{ m.display_label }}
                  <span v-if="m.mention_count > 1" class="mpp-count">×{{ m.mention_count }}</span>
                </n-tag>
              </template>
              {{ kindLabel(m.entity_kind) }} · 出现 {{ m.mention_count }} 次
            </n-tooltip>
          </div>
        </div>
      </div>

      <!-- 2. 道具库 -->
      <div class="pp-section mpp-section">
        <div class="pp-section-header">
          <div class="wb-icon-badge" style="background:#f59e0b">
            <n-icon size="14"><BriefcaseOutline /></n-icon>
          </div>
          <span class="pp-section-label">道具库</span>
          <span v-if="propsRows.length > 0" class="pp-chip pp-chip--muted" style="font-size:10px;margin-left:4px">
            {{ propsRows.length }} 件
          </span>
        </div>
        <div class="pp-section-body" style="padding:0">
          <div v-if="!propsDataLoaded && propsLoading" style="padding:12px">
            <n-skeleton text :rows="3" />
          </div>
          <n-spin v-else :show="propsLoading && propsDataLoaded">
            <div v-if="!propsRows.length && !propsLoading" class="pp-empty" style="padding:20px 16px">
              <span class="pp-empty-icon">📦</span>
              <span class="pp-empty-text">暂无道具</span>
              <n-button size="small" secondary @click="openCreate">+ 新建道具</n-button>
            </div>
            <n-data-table
              v-else
              :columns="columns"
              :data="propsRows"
              :pagination="false"
              size="small"
              :max-height="300"
            />
          </n-spin>
        </div>
      </div>

    </div>

    <!-- ── Create / Edit modal ─────────────────── -->
    <n-modal
      v-model:show="showModal"
      preset="card"
      :title="editingId ? '编辑道具' : '新建道具'"
      style="width:min(480px,96vw)"
    >
      <n-form label-placement="top" size="small">
        <n-form-item label="名称">
          <n-input v-model:value="form.name" placeholder="如：青铜罗盘" />
        </n-form-item>
        <n-form-item label="简述">
          <n-input
            v-model:value="form.description"
            type="textarea"
            :autosize="{ minRows: 2, maxRows: 6 }"
          />
        </n-form-item>
        <n-form-item label="别名（逗号分隔，用于正文自动命中）">
          <n-input v-model:value="form.aliasesText" placeholder="罗盘,司南" />
        </n-form-item>
        <n-form-item label="持有者（可选）">
          <n-select
            v-model:value="form.holder_character_id"
            :options="charOptions"
            placeholder="选择 Bible 中的角色"
            clearable
            filterable
          />
        </n-form-item>
        <n-form-item label="首次出现章（可选）">
          <n-input-number
            v-model:value="form.first_chapter"
            :min="1"
            clearable
            style="width:100%"
          />
        </n-form-item>
      </n-form>
      <template #action>
        <n-space justify="end" :size="8">
          <n-button @click="showModal = false">取消</n-button>
          <n-button type="primary" :loading="saving" @click="submitForm">保存</n-button>
        </n-space>
      </template>
    </n-modal>
  </div>
</template>

<script setup lang="ts">
import { computed, h, onMounted, ref, watch } from 'vue'
import type { DataTableColumns } from 'naive-ui'
import { NButton, NTooltip, useMessage } from 'naive-ui'
import { InformationCircleOutline, BookmarkOutline, BriefcaseOutline } from '@vicons/ionicons5'
import { manuscriptApi, type BiblePropRow, type ChapterEntityMention } from '@/api/manuscript'
import { bibleApi } from '@/api/bible'
import { useWorkbenchRefreshStore } from '@/stores/workbenchRefreshStore'
import { storeToRefs } from 'pinia'

const props = defineProps<{
  slug: string
  currentChapter?: { number: number } | null
}>()

const message = useMessage()
const { deskTick } = storeToRefs(useWorkbenchRefreshStore())

const propsRows = ref<BiblePropRow[]>([])
const propsLoading = ref(false)
const propsDataLoaded = ref(false)
const mentions = ref<ChapterEntityMention[]>([])
const mentionLoading = ref(false)
const reindexing = ref(false)

let propsLoadSeq = 0
let mentionsLoadSeq = 0

interface CharOption { label: string; value: string }
const charOptions = ref<CharOption[]>([])

const currentChapterNumber = computed(() => props.currentChapter?.number ?? null)

// ── Split button options ──────────────────────────────────────────
const reindexOptions = [{ label: '从正文重建', key: 'reindex' }]

function handleSyncSelect(key: string) {
  if (key === 'reindex') void runReindex()
}

// ── Entity kind helpers ───────────────────────────────────────────
function kindLabel(k: string): string {
  return ({ char: '角色', loc: '地点', faction: '势力', prop: '道具' } as Record<string, string>)[k] ?? k
}

function kindTagType(k: string): 'default' | 'info' | 'success' | 'warning' {
  if (k === 'char') return 'success'
  if (k === 'faction') return 'warning'
  if (k === 'prop') return 'info'
  return 'default'
}

// ── Load ──────────────────────────────────────────────────────────
async function loadCharOptions() {
  if (!props.slug) return
  try {
    const chars = await bibleApi.listCharacters(props.slug)
    charOptions.value = (chars ?? []).map(c => ({ label: c.name, value: c.id }))
  } catch {
    charOptions.value = []
  }
}

async function loadProps() {
  if (!props.slug) return
  const seq = ++propsLoadSeq
  const slug = props.slug
  propsLoading.value = true
  try {
    const r = await manuscriptApi.listProps(slug)
    if (seq !== propsLoadSeq || props.slug !== slug) return
    propsRows.value = r.props || []
  } catch {
    if (seq !== propsLoadSeq || props.slug !== slug) return
    message.error('加载道具失败')
  } finally {
    if (seq === propsLoadSeq) {
      propsLoading.value = false
      propsDataLoaded.value = true
    }
  }
}

async function loadMentions() {
  const n = currentChapterNumber.value
  if (!props.slug || n == null) { mentions.value = []; return }
  const seq = ++mentionsLoadSeq
  const slug = props.slug
  mentionLoading.value = true
  try {
    const r = await manuscriptApi.listChapterMentions(slug, n)
    if (seq !== mentionsLoadSeq || props.slug !== slug) return
    mentions.value = r.mentions || []
  } catch {
    if (seq !== mentionsLoadSeq || props.slug !== slug) return
    mentions.value = []
  } finally {
    if (seq === mentionsLoadSeq) mentionLoading.value = false
  }
}

async function runReindex() {
  const n = currentChapterNumber.value
  if (!props.slug || n == null) return
  reindexing.value = true
  try {
    const r = await manuscriptApi.reindexChapterMentions(props.slug, n)
    mentions.value = r.mentions || []
    message.success('已根据正文重建索引')
  } catch {
    message.error('重建失败')
  } finally {
    reindexing.value = false
  }
}

// ── CRUD ──────────────────────────────────────────────────────────
const showModal = ref(false)
const editingId = ref<string | null>(null)
const saving = ref(false)
const form = ref({
  name: '',
  description: '',
  aliasesText: '',
  holder_character_id: '' as string | null,
  first_chapter: null as number | null,
})

function openCreate() {
  editingId.value = null
  form.value = {
    name: '',
    description: '',
    aliasesText: '',
    holder_character_id: '',
    first_chapter: currentChapterNumber.value,
  }
  showModal.value = true
}

function openEdit(row: BiblePropRow) {
  editingId.value = row.id
  let aliases = ''
  try {
    const a = JSON.parse(row.aliases_json || '[]')
    aliases = Array.isArray(a) ? a.join(',') : ''
  } catch { aliases = '' }
  form.value = {
    name: row.name,
    description: row.description || '',
    aliasesText: aliases,
    holder_character_id: row.holder_character_id || '',
    first_chapter: row.first_chapter,
  }
  showModal.value = true
}

async function submitForm() {
  if (!props.slug || !form.value.name.trim()) { message.warning('请填写名称'); return }
  const aliases = form.value.aliasesText.split(/[,，]/).map(s => s.trim()).filter(Boolean)
  saving.value = true
  try {
    if (editingId.value) {
      await manuscriptApi.patchProp(props.slug, editingId.value, {
        name: form.value.name.trim(),
        description: form.value.description,
        aliases,
        holder_character_id: form.value.holder_character_id || null,
        first_chapter: form.value.first_chapter,
      })
      message.success('已更新')
    } else {
      await manuscriptApi.createProp(props.slug, {
        name: form.value.name.trim(),
        description: form.value.description,
        aliases,
        holder_character_id: form.value.holder_character_id || null,
        first_chapter: form.value.first_chapter,
      })
      message.success('已创建')
    }
    showModal.value = false
    await loadProps()
  } catch {
    message.error('保存失败')
  } finally {
    saving.value = false
  }
}

async function removeRow(row: BiblePropRow) {
  if (!props.slug) return
  try {
    await manuscriptApi.deleteProp(props.slug, row.id)
    message.success('已删除')
    await loadProps()
  } catch {
    message.error('删除失败')
  }
}

const starringPropId = ref<string | null>(null)

async function togglePropKey(row: BiblePropRow) {
  if (!props.slug) return
  starringPropId.value = row.id
  try {
    const newKey = !row.is_key
    await manuscriptApi.patchProp(props.slug, row.id, { is_key: newKey })
    const idx = propsRows.value.findIndex(r => r.id === row.id)
    if (idx !== -1) propsRows.value[idx] = { ...propsRows.value[idx], is_key: newKey ? 1 : 0 }
  } catch {
    message.error('操作失败')
  } finally {
    starringPropId.value = null
  }
}

// ── Table columns ─────────────────────────────────────────────────
const columns: DataTableColumns<BiblePropRow> = [
  {
    title: '名称',
    key: 'name',
    width: 90,
    ellipsis: { tooltip: true },
  },
  {
    title: '简述',
    key: 'description',
    ellipsis: { tooltip: true },
    render(row) {
      return row.description || h('span', { style: 'color:var(--app-text-muted);font-size:11px' }, '—')
    },
  },
  {
    title: '持有者',
    key: 'holder_character_id',
    width: 72,
    ellipsis: { tooltip: true },
    render(row) {
      if (!row.holder_character_id) return h('span', { style: 'color:var(--app-text-muted)' }, '—')
      const found = charOptions.value.find(c => c.value === row.holder_character_id)
      return found ? found.label : row.holder_character_id.slice(0, 6) + '…'
    },
  },
  {
    title: '类型',
    key: 'is_key',
    width: 58,
    render(row) {
      const isKey = Boolean(row.is_key)
      return h(
        NTooltip,
        {},
        {
          trigger: () => h(
            'span',
            {
              class: isKey ? 'pp-chip pp-chip--warning' : 'pp-chip pp-chip--muted',
              style: 'font-size:10px;cursor:pointer',
              onClick: () => void togglePropKey(row),
            },
            isKey ? '关键' : '普通',
          ),
          default: () => isKey ? '取消关键（移出 AI 上下文）' : '标为关键（注入 AI 上下文）',
        },
      )
    },
  },
  {
    title: '操作',
    key: 'actions',
    width: 96,
    render(row) {
      return h('div', { style: 'display:flex;gap:4px;align-items:center' }, [
        h(NButton, { size: 'tiny', onClick: () => openEdit(row) }, { default: () => '编辑' }),
        h(
          NButton,
          { size: 'tiny', type: 'error', tertiary: true, onClick: () => void removeRow(row) },
          { default: () => '删' },
        ),
      ])
    },
  },
]

// ── Lifecycle ─────────────────────────────────────────────────────
onMounted(() => {
  void loadProps()
  void loadMentions()
  void loadCharOptions()
})

watch(
  () => [props.slug, props.currentChapter?.number, deskTick.value] as const,
  () => {
    void loadProps()
    void loadMentions()
  },
)

watch(() => props.slug, () => void loadCharOptions())
</script>

<style scoped>
.mpp-panel { /* pp-panel base */ }

/* Hint collapsible strip */
.mpp-hint-wrap {
  flex-shrink: 0;
  border-bottom: 1px solid var(--app-border);
}

.mpp-hint-wrap :deep(.n-collapse) {
  background: var(--app-surface);
  border: none;
}

.mpp-hint-wrap :deep(.n-collapse-item) {
  border: none;
  background: transparent;
  margin: 0;
}

.mpp-hint-wrap :deep(.n-collapse-item__header) {
  padding: 0;
}

.mpp-hint-wrap :deep(.n-collapse-item__content-inner) {
  padding: 0;
}

.mpp-hint-trigger {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 7px 14px;
  font-size: 11px;
  font-weight: 600;
  color: var(--app-text-muted);
}

.mpp-hint-body {
  padding: 0 14px 10px;
  font-size: 11px;
  line-height: 1.7;
  color: var(--app-text-muted);
}

.mpp-code {
  font-size: 10px;
  padding: 1px 5px;
  border-radius: 3px;
  background: var(--app-border);
  color: var(--app-text-primary);
  font-family: ui-monospace, monospace;
}

/* Body scroll area */
.mpp-body {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 10px 12px 14px;
}

/* Sections */
.mpp-section {
  flex-shrink: 0;
}

/* Tag cloud */
.mpp-tag-cloud {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.mpp-count {
  font-size: 10px;
  opacity: 0.75;
  margin-left: 2px;
}

.mpp-empty-hint {
  font-size: 12px;
  color: var(--app-text-muted);
}
</style>
