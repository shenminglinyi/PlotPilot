<template>
  <div class="sandbox-panel">
    <!-- 角色锚点卡片 -->
    <n-card title="🎭 角色锚点" size="small" :bordered="true">
      <template #header-extra>
        <n-text v-if="characters.length > 0" depth="3" style="font-size: 12px">
          共 {{ characters.length }} 个角色
        </n-text>
      </template>

      <n-space vertical :size="12">
        <!-- 无角色提示 -->
        <n-alert
          v-if="characters.length === 0 && !charLoading"
          type="warning"
          :show-icon="true"
          style="font-size: 12px"
        >
          当前 Bible 中没有角色，请先在「剧本基建」中添加角色。
        </n-alert>

        <!-- 角色选择 -->
        <n-select
          v-model:value="selectedCharacterId"
          :options="characterOptions"
          placeholder="选择角色编辑锚点"
          filterable
          clearable
          :loading="charLoading"
          @update:value="onCharacterSelect"
        />

        <!-- 锚点编辑区 -->
        <n-spin :show="anchorLoading">
          <template v-if="anchor">
            <n-space vertical :size="10">
              <n-grid :cols="3" :x-gap="10">
                <n-gi>
                  <div class="anchor-field">
                    <n-text class="anchor-label">心理状态</n-text>
                    <n-input v-model:value="editMental" size="small" placeholder="如：平静、焦虑" />
                  </div>
                </n-gi>
                <n-gi>
                  <div class="anchor-field">
                    <n-text class="anchor-label">口头禅</n-text>
                    <n-input v-model:value="editVerbal" size="small" placeholder="如：嗯...、岂有此理" />
                  </div>
                </n-gi>
                <n-gi>
                  <div class="anchor-field">
                    <n-text class="anchor-label">小动作</n-text>
                    <n-input v-model:value="editIdle" size="small" placeholder="如：摸剑柄、转笔" />
                  </div>
                </n-gi>
              </n-grid>

              <!-- 场景测试 -->
              <n-collapse>
                <n-collapse-item title="🧪 试生成对话" name="test">
                  <n-space vertical :size="8">
                    <n-input
                      v-model:value="scenePrompt"
                      type="textarea"
                      size="small"
                      placeholder="描述一个场景，测试角色声线..."
                      :autosize="{ minRows: 2, maxRows: 4 }"
                    />
                    <n-space :size="8">
                      <n-button
                        type="primary"
                        size="small"
                        :loading="genLoading"
                        :disabled="!scenePrompt.trim()"
                        @click="runGenerate"
                      >
                        生成对话
                      </n-button>
                      <n-button
                        size="small"
                        :loading="saveLoading"
                        @click="saveAnchors"
                      >
                        保存锚点
                      </n-button>
                    </n-space>
                    <n-card v-if="generatedLine" size="small" :bordered="true" class="generated-output">
                      <n-text style="font-size: 13px; line-height: 1.7">{{ generatedLine }}</n-text>
                    </n-card>
                  </n-space>
                </n-collapse-item>
              </n-collapse>
            </n-space>
          </template>
          <n-empty v-else-if="selectedCharacterId && !anchorLoading" description="选择角色查看锚点" size="small" />
        </n-spin>
      </n-space>
    </n-card>

    <!-- 对话白名单卡片 -->
    <n-card class="dialogue-section" size="small" :bordered="true">
      <template #header>
        <n-space align="center" justify="space-between" style="width: 100%">
          <n-text strong style="font-size: 14px">💬 对话白名单</n-text>
          <n-space :size="8" align="center">
            <!-- 章节筛选 -->
            <n-select
              v-model:value="filterChapter"
              :options="chapterOptions"
              placeholder="章节"
              clearable
              style="width: 90px"
              size="small"
            />
            <!-- 说话人筛选 -->
            <n-select
              v-model:value="filterSpeaker"
              :options="speakerOptions"
              placeholder="说话人"
              clearable
              filterable
              style="width: 100px"
              size="small"
            />
            <!-- 搜索 -->
            <n-input
              v-model:value="searchText"
              placeholder="搜索..."
              clearable
              size="small"
              style="width: 100px"
            />
          </n-space>
        </n-space>
      </template>

      <!-- 对话列表 -->
      <n-spin :show="loading">
        <n-scrollbar style="max-height: 420px">
          <n-empty v-if="!result" description="加载中..." size="small" />
          <n-empty v-else-if="result.total_count === 0" description="暂无对话数据，生成章节后自动提取" size="small" />
          <n-empty v-else-if="filteredDialogues.length === 0" description="无匹配对话" size="small" />
          <n-space v-else vertical :size="4" style="padding: 4px 4px 4px 0">
            <div
              v-for="d in filteredDialogues"
              :key="d.dialogue_id"
              class="dialogue-item"
            >
              <div class="dialogue-meta">
                <n-tag size="tiny" round>第{{ d.chapter }}章</n-tag>
                <n-tag type="success" size="tiny" round>{{ d.speaker }}</n-tag>
              </div>
              <n-text class="dialogue-content">{{ d.content }}</n-text>
            </div>
          </n-space>
        </n-scrollbar>
        
        <!-- 底部统计 -->
        <div v-if="result && result.total_count > 0" class="dialogue-footer">
          <n-text depth="3" style="font-size: 11px">
            {{ filteredDialogues.length }} / {{ result.total_count }} 条对话
          </n-text>
        </div>
      </n-spin>
    </n-card>

    <!-- 角色灵魂档案 -->
    <n-collapse class="soul-collapse">
      <n-collapse-item title="🔮 角色灵魂档案" name="soul">
        <CharacterPsychePanel :slug="slug" />
      </n-collapse-item>
    </n-collapse>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { storeToRefs } from 'pinia'
import { useWorkbenchRefreshStore } from '../../stores/workbenchRefreshStore'
import { useMessage } from 'naive-ui'
import { sandboxApi } from '../../api/sandbox'
import type { DialogueWhitelistResponse, DialogueEntry, CharacterAnchor } from '../../api/sandbox'
import { bibleApi } from '../../api/bible'
import type { CharacterDTO } from '../../api/bible'
import CharacterPsychePanel from './CharacterPsychePanel.vue'

const props = defineProps<{ slug: string }>()
const message = useMessage()

// 状态
const loading = ref(false)
const charLoading = ref(false)
const result = ref<DialogueWhitelistResponse | null>(null)
const filterChapter = ref<number | null>(null)
const filterSpeaker = ref('')
const searchText = ref('')

const characters = ref<CharacterDTO[]>([])
const selectedCharacterId = ref<string | null>(null)
const anchor = ref<CharacterAnchor | null>(null)
const anchorLoading = ref(false)
const genLoading = ref(false)
const saveLoading = ref(false)
const editMental = ref('')
const editVerbal = ref('')
const editIdle = ref('')
const scenePrompt = ref('')
const generatedLine = ref('')

// 角色选项
const characterOptions = computed(() =>
  characters.value.map(c => ({ label: c.name || c.id, value: c.id }))
)

// 章节选项（从已有对话中提取）
const chapterOptions = computed(() => {
  if (!result.value) return []
  const chapters = new Set<number>()
  result.value.dialogues.forEach(d => chapters.add(d.chapter))
  return Array.from(chapters)
    .sort((a, b) => a - b)
    .map(ch => ({ label: `第${ch}章`, value: ch }))
})

// 说话人选项（从已有对话中提取）
const speakerOptions = computed(() => {
  if (!result.value) return []
  const speakers = new Set<string>()
  result.value.dialogues.forEach(d => speakers.add(d.speaker))
  return Array.from(speakers)
    .sort()
    .map(s => ({ label: s, value: s }))
})

// 过滤后的对话（本地筛选）
const filteredDialogues = computed<DialogueEntry[]>(() => {
  if (!result.value) return []
  let list = result.value.dialogues
  
  // 章节筛选
  if (filterChapter.value !== null) {
    list = list.filter(d => d.chapter === filterChapter.value)
  }
  
  // 说话人筛选
  if (filterSpeaker.value) {
    list = list.filter(d => d.speaker === filterSpeaker.value)
  }
  
  // 关键词搜索
  const kw = searchText.value.trim().toLowerCase()
  if (kw) {
    list = list.filter(d =>
      d.content.toLowerCase().includes(kw) ||
      d.speaker.toLowerCase().includes(kw)
    )
  }
  
  return list
})

// 加载角色列表
async function loadCharacters() {
  charLoading.value = true
  try {
    characters.value = await bibleApi.listCharacters(props.slug)
  } catch {
    characters.value = []
  } finally {
    charLoading.value = false
  }
}

// 选择角色时自动载入锚点
async function onCharacterSelect(charId: string | null) {
  if (!charId) {
    anchor.value = null
    generatedLine.value = ''
    return
  }
  
  anchorLoading.value = true
  generatedLine.value = ''
  try {
    const a = await sandboxApi.getCharacterAnchor(props.slug, charId)
    anchor.value = a
    editMental.value = a.mental_state || ''
    editVerbal.value = a.verbal_tic || ''
    editIdle.value = a.idle_behavior || ''
  } catch {
    message.error('载入锚点失败')
    anchor.value = null
  } finally {
    anchorLoading.value = false
  }
}

// 保存锚点
async function saveAnchors() {
  const id = selectedCharacterId.value
  if (!id) return
  saveLoading.value = true
  try {
    await sandboxApi.patchCharacterAnchor(props.slug, id, {
      mental_state: editMental.value || 'NORMAL',
      verbal_tic: editVerbal.value || '',
      idle_behavior: editIdle.value || '',
    })
    message.success('已保存到 Bible')
    refreshStore.bumpDesk()
  } catch {
    message.error('保存失败')
  } finally {
    saveLoading.value = false
  }
}

// 生成对话
async function runGenerate() {
  const id = selectedCharacterId.value
  if (!id || !scenePrompt.value.trim()) return
  genLoading.value = true
  generatedLine.value = ''
  try {
    const res = await sandboxApi.generateDialogue({
      novel_id: props.slug,
      character_id: id,
      scene_prompt: scenePrompt.value.trim(),
      mental_state: editMental.value || undefined,
      verbal_tic: editVerbal.value || undefined,
      idle_behavior: editIdle.value || undefined,
    })
    generatedLine.value = res.dialogue
  } catch {
    message.error('生成失败')
  } finally {
    genLoading.value = false
  }
}

// 加载对话白名单（加载全部）
async function loadWhitelist() {
  loading.value = true
  try {
    // 不传筛选参数，获取全部对话
    result.value = await sandboxApi.getDialogueWhitelist(props.slug)
  } catch {
    message.error('加载失败')
  } finally {
    loading.value = false
  }
}

// 监听 slug 变化
watch(
  () => props.slug,
  () => {
    loadCharacters()
    loadWhitelist()
    // 重置筛选
    filterChapter.value = null
    filterSpeaker.value = ''
    searchText.value = ''
    anchor.value = null
    generatedLine.value = ''
  }
)

// 初始化：自动加载全部数据
onMounted(() => {
  loadCharacters()
  loadWhitelist()
})

// 刷新监听
const refreshStore = useWorkbenchRefreshStore()
const { deskTick } = storeToRefs(refreshStore)
watch(deskTick, () => {
  loadCharacters()
  loadWhitelist()
})
</script>

<style scoped>
.sandbox-panel {
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow-y: auto;
  padding: 12px 16px;
  gap: 12px;
}

.anchor-field {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.anchor-label {
  font-size: 11px;
  font-weight: 600;
  color: var(--app-text-muted);
}

.generated-output {
  background: var(--color-success-dim, rgba(34, 197, 94, 0.06));
}

.dialogue-section :deep(.n-card__header) {
  padding: 10px 16px !important;
}

.dialogue-item {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 12px 14px;
  background: var(--app-surface-subtle);
  border-radius: 8px;
  border: 1px solid var(--app-border);
  transition: all 0.2s ease;
  box-shadow: var(--app-shadow-sm);
}

.dialogue-item:hover {
  background: var(--color-info-dim, rgba(59, 130, 246, 0.08));
  border-color: var(--color-info-border, rgba(59, 130, 246, 0.2));
  box-shadow: var(--app-shadow-md);
  transform: translateY(-1px);
}

.dialogue-meta {
  display: flex;
  gap: 6px;
  flex-shrink: 0;
}

.dialogue-content {
  font-size: 13px;
  line-height: 1.6;
  color: var(--app-text-primary);
}

.dialogue-footer {
  padding-top: 8px;
  border-top: 1px solid var(--app-divider);
  margin-top: 8px;
  text-align: right;
}

.sandbox-panel :deep(.n-card) {
  border-radius: 10px;
}

.sandbox-panel :deep(.n-card__header) {
  padding: 12px 16px;
  font-weight: 700;
  font-size: 14px;
  background: var(--app-surface-subtle);
  border-bottom: 1px solid var(--app-divider);
}

.sandbox-panel :deep(.n-collapse-item__header-main) {
  font-weight: 600;
}

.sandbox-panel :deep(.n-input),
.sandbox-panel :deep(.n-select),
.sandbox-panel :deep(.n-input-number) {
  border-radius: 6px;
}

.sandbox-panel :deep(.n-button) {
  border-radius: 6px;
}

.sandbox-panel :deep(.n-tag) {
  border-radius: 4px;
}

.sandbox-panel :deep(.n-empty) {
  padding: 20px 0;
}

.soul-collapse {
  margin-top: 12px;
  border: 1px solid var(--app-divider, #e0e0e6);
  border-radius: 8px;
  overflow: hidden;
  background: var(--n-color-modal);
}

.soul-collapse :deep(.n-collapse-item__header) {
  font-weight: 600;
  font-size: 13px;
}

.soul-collapse :deep(.n-collapse-item__content-wrapper) {
  max-height: 400px;
  overflow-y: auto;
}
</style>
