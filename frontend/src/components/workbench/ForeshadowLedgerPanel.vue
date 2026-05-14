<template>
  <div class="foreshadow-panel">
    <header class="panel-header">
      <div class="header-main">
        <h3 class="panel-title">伏笔账本</h3>
        <p class="panel-lead">
          伏笔 ≈ 主角（或读者）当下的疑问；在本阶段兑现并与爽点挂钩即可，不必写论文。
        </p>
      </div>
      <n-space class="header-actions" :size="8" align="center">
        <n-button size="small" secondary @click="openCreateModal">+ 添加伏笔</n-button>
        <n-button size="small" type="primary" :loading="loading" @click="load">刷新</n-button>
      </n-space>
    </header>

    <div class="panel-tabs">
      <n-tabs v-model:value="activeTab" type="segment" size="small">
        <n-tab name="pending">
          待兑现
          <n-badge v-if="pendingCount > 0" :value="pendingCount" :max="99" type="warning" style="margin-left: 6px" />
        </n-tab>
        <n-tab name="consumed">已消费</n-tab>
      </n-tabs>
    </div>

    <div class="panel-content">
      <n-spin :show="loading">
        <template v-if="activeTab === 'pending'">
          <n-empty v-if="pendingEntries.length === 0" description="暂无待兑现伏笔，点击「添加伏笔」开始记录">
            <template #icon><span class="empty-ico" aria-hidden="true">🪄</span></template>
          </n-empty>
          <n-space v-else vertical :size="10">
            <n-card
              v-for="entry in pendingEntries"
              :key="entry.id"
              size="small"
              :bordered="true"
              hoverable
              class="entry-card"
            >
              <template #header>
                <div class="entry-header">
                  <n-tag type="warning" size="small" round>待兑现</n-tag>
                  <n-text strong class="entry-clue">{{ entry.question }}</n-text>
                </div>
              </template>
              <n-space vertical :size="6">
                <div class="info-row">
                  <span class="info-label">埋入章节</span>
                  <span class="info-value">第 {{ entry.chapter }} 章</span>
                </div>
                <div class="info-row">
                  <span class="info-label">关联角色</span>
                  <span class="info-value">{{ entry.character_id || '—' }}</span>
                </div>
              </n-space>
              <template #action>
                <n-space :size="6">
                  <n-button size="tiny" type="success" secondary @click="markConsumed(entry)">标记已消费</n-button>
                  <n-button size="tiny" secondary @click="openEditModal(entry)">编辑</n-button>
                  <n-button size="tiny" type="error" secondary @click="remove(entry.id)">删除</n-button>
                </n-space>
              </template>
            </n-card>
          </n-space>
        </template>

        <template v-else>
          <n-empty v-if="consumedEntries.length === 0" description="暂无已消费伏笔">
            <template #icon><span class="empty-ico" aria-hidden="true">✅</span></template>
          </n-empty>
          <n-space v-else vertical :size="10">
            <n-card
              v-for="entry in consumedEntries"
              :key="entry.id"
              size="small"
              :bordered="true"
              class="entry-card entry-card--consumed"
            >
              <template #header>
                <div class="entry-header">
                  <n-tag type="success" size="small" round>已消费</n-tag>
                  <n-text strong class="entry-clue">{{ entry.question }}</n-text>
                </div>
              </template>
              <n-space vertical :size="4">
                <div class="info-row">
                  <span class="info-label">埋入</span>
                  <span class="info-value">第 {{ entry.chapter }} 章</span>
                </div>
                <div class="info-row">
                  <span class="info-label">兑现</span>
                  <span class="info-value">第 {{ entry.consumed_at_chapter }} 章</span>
                </div>
              </n-space>
            </n-card>
          </n-space>
        </template>
      </n-spin>
    </div>

    <n-modal
      v-model:show="showModal"
      preset="card"
      :title="editingEntry ? '编辑伏笔' : '添加伏笔'"
      style="width: min(520px, 96vw)"
    >
      <n-form :model="form" label-placement="left" label-width="88" :show-feedback="false">
        <n-space vertical :size="14">
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
            <n-input-number v-model:value="form.chapter" :min="1" style="width: 100%" />
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

    <n-modal v-model:show="showConsumeModal" preset="card" title="标记已消费" style="width: 380px">
      <n-form label-placement="left" label-width="88" :show-feedback="false">
        <n-form-item label="兑现章节">
          <n-input-number v-model:value="consumeChapter" :min="1" style="width: 100%" />
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
import { useWorkbenchRefreshStore } from '../../stores/workbenchRefreshStore'
import { useMessage } from 'naive-ui'
import { foreshadowApi } from '../../api/foreshadow'
import type { ForeshadowEntry } from '../../api/foreshadow'

interface Props {
  slug: string
}
const props = defineProps<Props>()
const message = useMessage()

const loading = ref(false)
const saving = ref(false)
const entries = ref<ForeshadowEntry[]>([])
const activeTab = ref<'pending' | 'consumed'>('pending')

const pendingEntries = computed(() => entries.value.filter((e) => e.status === 'pending'))
const consumedEntries = computed(() => entries.value.filter((e) => e.status === 'consumed'))
const pendingCount = computed(() => pendingEntries.value.length)

const showModal = ref(false)
const editingEntry = ref<ForeshadowEntry | null>(null)
const form = ref({ question: '', character_id: '', chapter: 1 })

const showConsumeModal = ref(false)
const consumingEntry = ref<ForeshadowEntry | null>(null)
const consumeChapter = ref(1)

const load = async () => {
  loading.value = true
  try {
    entries.value = await foreshadowApi.list(props.slug)
  } catch {
    message.error('加载伏笔账本失败')
  } finally {
    loading.value = false
  }
}

const openCreateModal = () => {
  editingEntry.value = null
  form.value = { question: '', character_id: '', chapter: 1 }
  showModal.value = true
}

const openEditModal = (entry: ForeshadowEntry) => {
  editingEntry.value = entry
  form.value = {
    question: entry.question,
    character_id: entry.character_id,
    chapter: entry.chapter,
  }
  showModal.value = true
}

const handleSubmit = async () => {
  if (!form.value.question.trim()) {
    message.warning('请填写当下的疑问')
    return
  }
  if (!form.value.character_id.trim()) {
    message.warning('请输入关联角色')
    return
  }

  saving.value = true
  try {
    if (editingEntry.value) {
      await foreshadowApi.update(props.slug, editingEntry.value.id, {
        question: form.value.question,
        character_id: form.value.character_id,
        chapter: form.value.chapter,
      })
      message.success('已保存')
    } else {
      await foreshadowApi.create(props.slug, {
        entry_id: `fsw-${Date.now()}`,
        question: form.value.question,
        character_id: form.value.character_id,
        chapter: form.value.chapter,
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

const markConsumed = (entry: ForeshadowEntry) => {
  consumingEntry.value = entry
  consumeChapter.value = entry.chapter + 1
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

const remove = async (id: string) => {
  try {
    await foreshadowApi.remove(props.slug, id)
    message.success('已删除')
    entries.value = entries.value.filter((e) => e.id !== id)
  } catch {
    message.error('删除失败')
  }
}

const refreshStore = useWorkbenchRefreshStore()
const { foreshadowTick } = storeToRefs(refreshStore)

onMounted(load)

watch(foreshadowTick, () => {
  void load()
})
</script>

<style scoped>
.foreshadow-panel {
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: var(--plotpilot-panel-muted);
}

.panel-header {
  padding: 12px 16px;
  border-bottom: 1px solid var(--plotpilot-split-border);
  background: var(--app-surface);
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
}

.header-main {
  flex: 1;
  min-width: 0;
}

.panel-title {
  margin: 0 0 8px;
  font-size: 16px;
  font-weight: 600;
  color: var(--app-text-primary);
}

.panel-lead {
  margin: 0;
  font-size: 13px;
  line-height: 1.55;
  color: var(--app-text-secondary);
}

.header-actions {
  flex-shrink: 0;
}

.panel-tabs {
  padding: 10px 16px 6px;
  background: var(--app-surface);
  border-bottom: 1px solid var(--plotpilot-split-border);
}

.panel-content {
  flex: 1;
  overflow-y: auto;
  padding: 14px 16px;
}

.empty-ico {
  font-size: 36px;
  line-height: 1;
  opacity: 0.9;
}

.entry-card {
  border-radius: var(--app-radius-md, 10px);
}

.entry-card--consumed {
  opacity: 0.88;
}

.entry-header {
  display: flex;
  align-items: flex-start;
  gap: 8px;
}

.entry-clue {
  flex: 1;
  min-width: 0;
  font-size: 13px;
  font-weight: 500;
  color: var(--app-text-primary);
}

.info-row {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  font-size: 13px;
}

.info-label {
  flex-shrink: 0;
  width: 64px;
  font-weight: 600;
  color: var(--app-text-secondary);
}

.info-value {
  flex: 1;
  min-width: 0;
  color: var(--app-text-primary);
  line-height: 1.5;
}

</style>
