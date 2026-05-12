<template>
  <div class="props-panel">
    <n-alert type="info" :bordered="false" class="props-hint" title="小说家用法">
      道具与正文、知识库同构：正文可写
      <code>[[prop:道具ID|显示名]]</code>
      ，亦可在此维护；保存章节后系统自动统计本章出现的角色 / 地点 / 势力 / 道具（零 token）。
    </n-alert>

    <n-space vertical :size="14" style="width: 100%">
      <n-card v-if="currentChapterNumber != null" size="small" title="本章实体索引（自动）" :bordered="true">
        <n-space align="center" :size="8" style="margin-bottom: 10px">
          <n-button size="tiny" quaternary :loading="mentionLoading" @click="loadMentions">刷新</n-button>
          <n-button size="tiny" secondary :loading="reindexing" @click="runReindex">从正文重建</n-button>
        </n-space>
        <n-empty v-if="!mentions.length && !mentionLoading" description="尚无索引，保存章节或点「从正文重建」" size="small" />
        <n-scrollbar v-else style="max-height: 180px">
          <n-space vertical :size="4">
            <div v-for="m in mentions" :key="`${m.entity_kind}-${m.entity_id}`" class="mention-row">
              <n-tag size="tiny" :type="kindTagType(m.entity_kind)">{{ kindLabel(m.entity_kind) }}</n-tag>
              <n-text strong>{{ m.display_label }}</n-text>
              <n-text depth="3" style="font-size: 11px">×{{ m.mention_count }}</n-text>
            </div>
          </n-space>
        </n-scrollbar>
      </n-card>

      <n-card size="small" title="道具库（可编辑）" :bordered="true">
        <template #header-extra>
          <n-button size="small" type="primary" @click="openCreate">新建道具</n-button>
        </template>
        <n-spin :show="propsLoading">
          <n-empty v-if="!propsRows.length && !propsLoading" description="暂无道具" size="small" />
          <n-data-table v-else :columns="columns" :data="propsRows" :pagination="false" size="small" />
        </n-spin>
      </n-card>
    </n-space>

    <n-modal v-model:show="showModal" preset="card" :title="editingId ? '编辑道具' : '新建道具'" style="width: 480px">
      <n-form label-placement="top" size="small">
        <n-form-item label="名称">
          <n-input v-model:value="form.name" placeholder="如：青铜罗盘" />
        </n-form-item>
        <n-form-item label="简述">
          <n-input v-model:value="form.description" type="textarea" :autosize="{ minRows: 2, maxRows: 6 }" />
        </n-form-item>
        <n-form-item label="别名（逗号分隔，用于正文自动命中）">
          <n-input v-model:value="form.aliasesText" placeholder="罗盘,司南" />
        </n-form-item>
        <n-form-item label="持有者角色 ID（可选）">
          <n-input v-model:value="form.holder_character_id" placeholder="Bible 人物 id" />
        </n-form-item>
        <n-form-item label="首次出现章（可选）">
          <n-input-number v-model:value="form.first_chapter" :min="1" clearable style="width: 100%" />
        </n-form-item>
      </n-form>
      <template #footer>
        <n-space justify="end">
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
import { NButton, useMessage } from 'naive-ui'
import { manuscriptApi, type BiblePropRow, type ChapterEntityMention } from '@/api/manuscript'
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
const mentions = ref<ChapterEntityMention[]>([])
const mentionLoading = ref(false)
const reindexing = ref(false)

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

const currentChapterNumber = computed(() => props.currentChapter?.number ?? null)

function kindLabel(k: string) {
  const m: Record<string, string> = { char: '角色', loc: '地点', faction: '势力', prop: '道具' }
  return m[k] || k
}

function kindTagType(k: string): 'default' | 'info' | 'success' | 'warning' {
  if (k === 'char') return 'success'
  if (k === 'faction') return 'warning'
  if (k === 'prop') return 'info'
  return 'default'
}

async function loadProps() {
  if (!props.slug) return
  propsLoading.value = true
  try {
    const r = await manuscriptApi.listProps(props.slug)
    propsRows.value = r.props || []
  } catch {
    message.error('加载道具失败')
  } finally {
    propsLoading.value = false
  }
}

async function loadMentions() {
  const n = currentChapterNumber.value
  if (!props.slug || n == null) {
    mentions.value = []
    return
  }
  mentionLoading.value = true
  try {
    const r = await manuscriptApi.listChapterMentions(props.slug, n)
    mentions.value = r.mentions || []
  } catch {
    mentions.value = []
  } finally {
    mentionLoading.value = false
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
  } catch {
    aliases = ''
  }
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
  if (!props.slug || !form.value.name.trim()) {
    message.warning('请填写名称')
    return
  }
  const aliases = form.value.aliasesText
    .split(/[,，]/)
    .map(s => s.trim())
    .filter(Boolean)
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

const columns: DataTableColumns<BiblePropRow> = [
  { title: '名称', key: 'name', ellipsis: { tooltip: true } },
  {
    title: '操作',
    key: 'actions',
    width: 140,
    render(row) {
      return h('div', { style: 'display:flex;gap:6px' }, [
        h(
          NButton,
          { size: 'tiny', onClick: () => openEdit(row) },
          { default: () => '编辑' },
        ),
        h(
          NButton,
          { size: 'tiny', type: 'error', tertiary: true, onClick: () => void removeRow(row) },
          { default: () => '删' },
        ),
      ])
    },
  },
]

onMounted(() => {
  void loadProps()
  void loadMentions()
})

watch(
  () => [props.slug, props.currentChapter?.number, deskTick.value] as const,
  () => {
    void loadProps()
    void loadMentions()
  },
)
</script>

<style scoped>
.props-panel {
  padding: 8px 4px 16px;
  min-height: 0;
}
.props-hint {
  margin-bottom: 12px;
  font-size: 12px;
}
.props-hint code {
  font-size: 11px;
  padding: 0 4px;
  border-radius: 3px;
  background: var(--app-border, rgba(0, 0, 0, 0.06));
}
.mention-row {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
}
</style>
