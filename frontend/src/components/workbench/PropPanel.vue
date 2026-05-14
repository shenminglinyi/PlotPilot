<template>
  <div class="prop-panel">
    <div class="prop-panel__header">
      <n-text strong>道具库</n-text>
      <n-space :size="8">
        <n-select
          v-model:value="filterState"
          :options="stateOptions"
          size="small"
          style="width:110px"
        />
        <n-button size="small" type="primary" @click="openCreate">＋ 新建</n-button>
      </n-space>
    </div>

    <n-spin :show="loading">
      <n-empty v-if="!loading && filtered.length === 0" description="暂无道具" size="small" style="margin-top:24px" />
      <div v-else class="prop-list">
        <div
          v-for="p in filtered"
          :key="p.id"
          class="prop-item"
          :class="{ 'prop-item--damaged': p.lifecycle_state === 'DAMAGED' }"
          @click="openDetail(p)"
        >
          <span class="prop-item__icon">{{ CATEGORY_ICONS[p.prop_category] }}</span>
          <div class="prop-item__body">
            <n-text strong class="prop-item__name">{{ p.name }}</n-text>
            <n-text depth="3" style="font-size:11px">
              {{ holderName(p) }}
              <template v-if="p.introduced_chapter">· 第{{ p.introduced_chapter }}章</template>
            </n-text>
          </div>
          <n-tag :type="LIFECYCLE_TAG_TYPES[p.lifecycle_state]" size="tiny" round>
            {{ LIFECYCLE_LABELS[p.lifecycle_state] }}
          </n-tag>
        </div>
      </div>
    </n-spin>

    <!-- 新建/编辑 Modal -->
    <n-modal v-model:show="showModal" preset="card" :title="editingId ? '编辑道具' : '新建道具'" style="width:480px">
      <n-form label-placement="top" size="small">
        <n-form-item label="名称 *">
          <n-input v-model:value="form.name" placeholder="如：青铜罗盘" />
        </n-form-item>
        <n-form-item label="类型">
          <n-select v-model:value="form.prop_category" :options="categoryOptions" />
        </n-form-item>
        <n-form-item label="简述">
          <n-input v-model:value="form.description" type="textarea" :autosize="{ minRows: 2, maxRows: 5 }" />
        </n-form-item>
        <n-form-item label="别名（逗号分隔）">
          <n-input v-model:value="form.aliasText" placeholder="罗盘,指南针" />
        </n-form-item>
        <n-form-item label="持有者（可选）">
          <n-select v-model:value="form.holder_character_id" :options="charOptions" clearable filterable placeholder="选择角色" />
        </n-form-item>
        <n-form-item label="首次登场章（可选）">
          <n-input-number v-model:value="form.introduced_chapter" :min="1" clearable style="width:100%" />
        </n-form-item>
      </n-form>
      <template #footer>
        <n-space justify="end">
          <n-button @click="showModal = false">取消</n-button>
          <n-button type="primary" :loading="saving" @click="submitForm">保存</n-button>
        </n-space>
      </template>
    </n-modal>

    <!-- 详情抽屉 -->
    <PropDetailDrawer
      v-if="selectedProp"
      :prop="selectedProp"
      :slug="slug"
      :char-options="charOptions"
      @close="selectedProp = null"
      @updated="loadProps"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useMessage } from 'naive-ui'
import {
  propApi, type PropDTO,
  LIFECYCLE_LABELS, LIFECYCLE_TAG_TYPES, CATEGORY_ICONS,
} from '@/api/propApi'
import { bibleApi } from '@/api/bible'
import PropDetailDrawer from './PropDetailDrawer.vue'

const props = defineProps<{ slug: string; currentChapter?: number | null }>()
const message = useMessage()

const loading = ref(false)
const saving = ref(false)
const propsData = ref<PropDTO[]>([])
const selectedProp = ref<PropDTO | null>(null)
const showModal = ref(false)
const editingId = ref<string | null>(null)
const filterState = ref<string | null>(null)
const charOptions = ref<{ label: string; value: string }[]>([])

const form = ref({
  name: '',
  description: '',
  prop_category: 'OTHER' as PropDTO['prop_category'],
  aliasText: '',
  holder_character_id: null as string | null,
  introduced_chapter: null as number | null,
})

const stateOptions = [
  { label: '全部', value: null },
  { label: '使用中', value: 'ACTIVE' },
  { label: '损毁', value: 'DAMAGED' },
  { label: '未登场', value: 'DORMANT' },
  { label: '已结局', value: 'RESOLVED' },
]

const categoryOptions = [
  { label: '武器', value: 'WEAPON' },
  { label: '法器', value: 'ARTIFACT' },
  { label: '工具', value: 'TOOL' },
  { label: '消耗品', value: 'CONSUMABLE' },
  { label: '信物', value: 'TOKEN' },
  { label: '其他', value: 'OTHER' },
]

const filtered = computed(() =>
  filterState.value
    ? propsData.value.filter(p => p.lifecycle_state === filterState.value)
    : propsData.value
)

function holderName(p: PropDTO): string {
  if (!p.holder_character_id) return '无持有者'
  const found = charOptions.value.find(c => c.value === p.holder_character_id)
  return found ? found.label : '未知持有者'
}

async function loadProps() {
  if (!props.slug) return
  loading.value = true
  try {
    propsData.value = await propApi.list(props.slug)
  } catch {
    message.error('加载道具失败')
  } finally {
    loading.value = false
  }
}

async function loadChars() {
  try {
    const chars = await bibleApi.listCharacters(props.slug) as { id: string; name: string }[]
    charOptions.value = (chars ?? []).map(c => ({ label: c.name, value: c.id }))
  } catch {
    charOptions.value = []
  }
}

function openCreate() {
  editingId.value = null
  form.value = {
    name: '', description: '', prop_category: 'OTHER',
    aliasText: '', holder_character_id: null,
    introduced_chapter: props.currentChapter ?? null,
  }
  showModal.value = true
}

function openDetail(p: PropDTO) {
  selectedProp.value = p
}

async function submitForm() {
  if (!form.value.name.trim()) { message.warning('请填写名称'); return }
  saving.value = true
  try {
    const aliases = form.value.aliasText.split(/[,，]/).map(s => s.trim()).filter(Boolean)
    const payload = {
      name: form.value.name.trim(),
      description: form.value.description,
      prop_category: form.value.prop_category,
      aliases,
      holder_character_id: form.value.holder_character_id,
      introduced_chapter: form.value.introduced_chapter,
    }
    if (editingId.value) {
      await propApi.patch(props.slug, editingId.value, payload)
    } else {
      await propApi.create(props.slug, payload)
    }
    message.success(editingId.value ? '已更新' : '道具已创建')
    showModal.value = false
    await loadProps()
  } catch {
    message.error('保存失败')
  } finally {
    saving.value = false
  }
}

onMounted(() => { void loadProps(); void loadChars() })
watch(() => props.slug, () => { void loadProps(); void loadChars() })
</script>

<style scoped>
.prop-panel { height: 100%; display: flex; flex-direction: column; overflow: hidden; background: var(--app-surface); }
.prop-panel__header { display: flex; justify-content: space-between; align-items: center; padding: 12px 16px; border-bottom: 1px solid var(--plotpilot-split-border); flex-shrink: 0; }
.prop-list { flex: 1; overflow-y: auto; padding: 8px 12px; display: flex; flex-direction: column; gap: 6px; }
.prop-item { display: flex; align-items: center; gap: 10px; padding: 10px 12px; border-radius: 6px; border: 1px solid var(--n-border-color); cursor: pointer; transition: all 0.15s; }
.prop-item:hover { border-color: var(--n-primary-color); box-shadow: 0 1px 6px rgba(0,0,0,0.06); }
.prop-item--damaged { border-color: var(--n-error-color); background: rgba(239,68,68,0.03); }
.prop-item__icon { font-size: 18px; flex-shrink: 0; }
.prop-item__body { flex: 1; min-width: 0; }
.prop-item__name { display: block; font-size: 13px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
</style>
