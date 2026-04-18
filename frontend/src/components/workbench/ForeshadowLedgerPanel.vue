<template>
  <div class="foreshadow-panel">
    <n-alert type="default" :show-icon="true" class="ledger-sync-hint" style="margin-bottom: 10px">
      <strong>简单版</strong>：把「主角还没兑现的疑问」记在这里；回收时对照爽点。数据与托管监控大盘同源，此处可增删与核销。
    </n-alert>
    <header class="panel-header">
      <div class="header-main">
        <div class="title-row">
          <h3 class="panel-title">伏笔账本</h3>
          <n-tag size="small" round :bordered="false">Foreshadow Ledger</n-tag>
        </div>
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
          <n-badge v-if="pendingCount > 0" :value="pendingCount" :max="99" type="warning" style="margin-left:6px" />
        </n-tab>
        <n-tab name="consumed">已消费</n-tab>
      </n-tabs>
    </div>

    <div class="panel-content">
      <n-spin :show="loading">
        <!-- 场景感官匹配 -->
        <template v-if="activeTab === 'pending'">
          <n-card size="small" :bordered="false" class="match-card">
            <template #header>
              <n-space align="center" justify="space-between" style="width:100%">
                <n-text strong style="font-size:13px">场景感官匹配</n-text>
                <n-button size="tiny" secondary :loading="matchLoading" @click="runMatch">
                  匹配当前场景
                </n-button>
              </n-space>
            </template>
            <n-space vertical :size="8">
              <n-text depth="3" style="font-size:12px">输入当前场景的感官描述词，AI 找出最匹配的待兑现伏笔。</n-text>
              <n-space v-for="(_, idx) in matchAnchors" :key="idx" :size="6" align="center">
                <n-input v-model:value="matchAnchors[idx].key" placeholder="感官（视觉/听觉…）" style="width:100px" size="small" />
                <n-input v-model:value="matchAnchors[idx].value" placeholder="关键词" style="flex:1" size="small" />
                <n-button size="tiny" text @click="matchAnchors.splice(idx, 1)">✕</n-button>
              </n-space>
              <n-button size="tiny" dashed @click="matchAnchors.push({ key: '', value: '' })">+ 添加感官</n-button>

              <template v-if="matchResult !== null">
                <n-divider style="margin:4px 0" />
                <template v-if="matchResult.matched && matchResult.entry">
                  <n-space align="center" :size="6">
                    <n-tag type="success" size="small" round>✓ 找到匹配</n-tag>
                    <n-text strong style="font-size:13px">{{ matchResult.entry.hidden_clue }}</n-text>
                  </n-space>
                  <n-text depth="3" style="font-size:12px">
                    第 {{ matchResult.entry.chapter }} 章埋入 · {{ matchResult.entry.character_id }}
                  </n-text>
                </template>
                <n-alert v-else type="default" :show-icon="false" style="font-size:12px">
                  暂无匹配的待兑现伏笔
                </n-alert>
              </template>
            </n-space>
          </n-card>
        </template>

        <template v-if="activeTab === 'pending'">
          <n-empty v-if="pendingEntries.length === 0" description="暂无待兑现伏笔，点击「添加伏笔」开始布局">
            <template #icon><span style="font-size:42px">🪄</span></template>
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
                  <n-text strong class="entry-clue">{{ entry.hidden_clue }}</n-text>
                </div>
              </template>
              <n-space vertical :size="6">
                <div class="info-row">
                  <n-text depth="3" class="info-label">埋入章节</n-text>
                  <n-text>第 {{ entry.chapter }} 章</n-text>
                </div>
                <div class="info-row">
                  <n-text depth="3" class="info-label">关联角色</n-text>
                  <n-text>{{ entry.character_id }}</n-text>
                </div>
                <div v-if="Object.keys(entry.sensory_anchors).length > 0" class="info-row anchors-row">
                  <n-text depth="3" class="info-label">感官锚点</n-text>
                  <div class="anchors-wrap">
                    <n-tag
                      v-for="(v, k) in entry.sensory_anchors"
                      :key="k"
                      size="tiny"
                      round
                      type="info"
                    >{{ k }}：{{ v }}</n-tag>
                  </div>
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
            <template #icon><span style="font-size:42px">✅</span></template>
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
                  <n-text strong class="entry-clue">{{ entry.hidden_clue }}</n-text>
                </div>
              </template>
              <n-space vertical :size="4">
                <div class="info-row">
                  <n-text depth="3" class="info-label">埋入</n-text>
                  <n-text>第 {{ entry.chapter }} 章</n-text>
                </div>
                <div class="info-row">
                  <n-text depth="3" class="info-label">兑现</n-text>
                  <n-text>第 {{ entry.consumed_at_chapter }} 章</n-text>
                </div>
              </n-space>
            </n-card>
          </n-space>
        </template>
      </n-spin>
    </div>

    <!-- 创建/编辑弹窗 -->
    <n-modal
      v-model:show="showModal"
      preset="card"
      :title="editingEntry ? '编辑伏笔' : '添加伏笔'"
      style="width: min(560px, 96vw)"
    >
      <n-form :model="form" label-placement="left" label-width="90" :show-feedback="false">
        <n-space vertical :size="14">
          <n-form-item label="隐藏线索">
            <n-input
              v-model:value="form.hidden_clue"
              placeholder="例：主角腰间的玉佩微微发热，他没在意"
              type="textarea"
              :autosize="{ minRows: 2, maxRows: 4 }"
            />
          </n-form-item>
          <n-form-item label="关联角色">
            <n-input v-model:value="form.character_id" placeholder="角色名或 ID" />
          </n-form-item>
          <n-form-item label="埋入章节">
            <n-input-number v-model:value="form.chapter" :min="1" style="width:100%" />
          </n-form-item>
          <n-form-item label="感官锚点">
            <n-space vertical :size="6" style="width:100%">
              <n-space v-for="(_, idx) in anchorRows" :key="idx" :size="6" align="center">
                <n-input v-model:value="anchorRows[idx].key" placeholder="感官（视觉/听觉…）" style="width:110px" />
                <n-input v-model:value="anchorRows[idx].value" placeholder="具体描述" style="flex:1" />
                <n-button size="tiny" secondary @click="removeAnchor(idx)">✕</n-button>
              </n-space>
              <n-button size="tiny" dashed @click="addAnchor">+ 添加锚点</n-button>
            </n-space>
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

    <!-- 标记消费弹窗 -->
    <n-modal v-model:show="showConsumeModal" preset="card" title="标记已消费" style="width: 380px">
      <n-form label-placement="left" label-width="90" :show-feedback="false">
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
import { useWorkbenchRefreshStore } from '../../stores/workbenchRefreshStore'
import { useMessage } from 'naive-ui'
import { foreshadowApi } from '../../api/foreshadow'
import type { ForeshadowEntry, MatchForeshadowResponse } from '../../api/foreshadow'

interface Props { slug: string }
const props = defineProps<Props>()
const message = useMessage()

const loading = ref(false)
const saving = ref(false)
const entries = ref<ForeshadowEntry[]>([])
const activeTab = ref<'pending' | 'consumed'>('pending')

const pendingEntries = computed(() => entries.value.filter(e => e.status === 'pending'))
const consumedEntries = computed(() => entries.value.filter(e => e.status === 'consumed'))
const pendingCount = computed(() => pendingEntries.value.length)

// 表单
const showModal = ref(false)
const editingEntry = ref<ForeshadowEntry | null>(null)
const form = ref({ hidden_clue: '', character_id: '', chapter: 1 })
const anchorRows = ref<{ key: string; value: string }[]>([])

// 感官匹配
const matchAnchors = ref<{ key: string; value: string }[]>([{ key: '', value: '' }])
const matchLoading = ref(false)
const matchResult = ref<MatchForeshadowResponse | null>(null)

const runMatch = async () => {
  const anchors: Record<string, string> = {}
  for (const row of matchAnchors.value) {
    if (row.key.trim()) anchors[row.key.trim()] = row.value
  }
  if (Object.keys(anchors).length === 0) { message.warning('请至少填写一个感官锚点'); return }
  matchLoading.value = true
  try {
    matchResult.value = await foreshadowApi.match(props.slug, anchors)
  } catch {
    message.error('匹配失败')
  } finally {
    matchLoading.value = false
  }
}

// 消费弹窗
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
  form.value = { hidden_clue: '', character_id: '', chapter: 1 }
  anchorRows.value = []
  showModal.value = true
}

const openEditModal = (entry: ForeshadowEntry) => {
  editingEntry.value = entry
  form.value = { hidden_clue: entry.hidden_clue, character_id: entry.character_id, chapter: entry.chapter }
  anchorRows.value = Object.entries(entry.sensory_anchors).map(([key, value]) => ({ key, value }))
  showModal.value = true
}

const addAnchor = () => anchorRows.value.push({ key: '', value: '' })
const removeAnchor = (idx: number) => anchorRows.value.splice(idx, 1)

const buildAnchors = () => {
  const result: Record<string, string> = {}
  for (const row of anchorRows.value) {
    if (row.key.trim()) result[row.key.trim()] = row.value
  }
  return result
}

const handleSubmit = async () => {
  if (!form.value.hidden_clue.trim()) { message.warning('请输入隐藏线索'); return }
  if (!form.value.character_id.trim()) { message.warning('请输入关联角色'); return }

  saving.value = true
  try {
    if (editingEntry.value) {
      await foreshadowApi.update(props.slug, editingEntry.value.id, {
        hidden_clue: form.value.hidden_clue,
        character_id: form.value.character_id,
        chapter: form.value.chapter,
        sensory_anchors: buildAnchors(),
      })
      message.success('伏笔已更新')
    } else {
      await foreshadowApi.create(props.slug, {
        entry_id: `fsw-${Date.now()}`,
        hidden_clue: form.value.hidden_clue,
        character_id: form.value.character_id,
        chapter: form.value.chapter,
        sensory_anchors: buildAnchors(),
      })
      message.success('伏笔已添加，生成时 AI 会优先呼应')
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
    message.success('已标记为消费')
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
    entries.value = entries.value.filter(e => e.id !== id)
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
  background: linear-gradient(to bottom, var(--n-color-modal) 0%, rgba(79, 70, 229, 0.02) 100%);
}

.panel-header {
  padding: 16px 20px 14px;
  border-bottom: 1px solid var(--aitext-split-border);
  background: var(--app-surface);
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04);
}

.header-main {
  flex: 1;
  min-width: 0;
}

.title-row {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 8px;
}

.panel-title {
  margin: 0;
  font-size: 18px;
  font-weight: 700;
  background: linear-gradient(135deg, #4f46e5 0%, #6366f1 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}

.panel-lead {
  margin: 0;
  font-size: 12px;
  line-height: 1.6;
  color: var(--text-color-3);
}

.header-actions {
  flex-shrink: 0;
}

.panel-tabs {
  padding: 12px 20px 8px;
  background: var(--app-surface);
  border-bottom: 1px solid var(--aitext-split-border);
}

.panel-content {
  flex: 1;
  overflow-y: auto;
  padding: 18px 20px;
}

.match-card {
  margin-bottom: 16px;
  background: linear-gradient(135deg, rgba(79, 70, 229, 0.05), rgba(99, 102, 241, 0.08));
  border-radius: 10px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04);
}

.entry-card {
  transition: all 0.2s ease;
  border-radius: 10px;
  overflow: hidden;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04);
}

.entry-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.1);
}

.entry-card--consumed {
  opacity: 0.65;
}

.entry-header {
  display: flex;
  align-items: center;
  gap: 10px;
}

.entry-clue {
  flex: 1;
  min-width: 0;
  font-size: 13px;
  font-weight: 500;
}

.info-row {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  font-size: 12px;
}

.info-label {
  flex-shrink: 0;
  width: 60px;
  color: var(--text-color-3);
  font-weight: 600;
}

.anchors-row {
  align-items: flex-start;
}

.anchors-wrap {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.foreshadow-panel :deep(.n-card) {
  border-radius: 10px;
  transition: all 0.2s ease;
}

.foreshadow-panel :deep(.n-tabs) {
  --n-tab-border-radius: 8px;
}

.foreshadow-panel :deep(.n-button) {
  border-radius: 8px;
  font-weight: 500;
  transition: all 0.2s ease;
}

.foreshadow-panel :deep(.n-button:hover) {
  transform: translateY(-1px);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
}

.foreshadow-panel :deep(.n-tag) {
  border-radius: 6px;
  font-weight: 500;
}

.foreshadow-panel :deep(.n-badge) {
  --n-font-weight: 600;
}

.foreshadow-panel :deep(.n-input),
.foreshadow-panel :deep(.n-input-number) {
  border-radius: 8px;
}

.foreshadow-panel :deep(.n-divider) {
  margin: 12px 0;
}

.foreshadow-panel :deep(.n-alert) {
  border-radius: 10px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04);
}
</style>
