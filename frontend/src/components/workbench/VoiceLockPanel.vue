<template>
  <div class="voice-lock-panel">
    <header class="panel-header">
      <div class="header-main">
        <div class="title-row">
          <h3 class="panel-title">口吻锁定</h3>
          <n-tag size="small" round :bordered="false">P2</n-tag>
        </div>
        <p class="panel-lead">
          用 Bible 锚点和作者样本把角色口吻固定下来。先锁角色，再把代表性改稿沉到文风金库里。
        </p>
      </div>
      <n-button size="small" type="primary" secondary :loading="loading" @click="reloadAll">
        刷新
      </n-button>
    </header>

    <div class="panel-content">
      <n-spin :show="loading">
        <n-alert v-if="loadError" type="error" :show-icon="true" class="section-alert">
          {{ loadError }}
        </n-alert>

        <template v-else>
          <n-space vertical :size="14">
            <n-space :size="8" wrap>
              <n-tag round size="small" :type="characters.length > 0 ? 'info' : 'default'">
                角色 {{ characters.length }}
              </n-tag>
              <n-tag round size="small" :type="fingerprint.sample_count >= 10 ? 'success' : 'warning'">
                文风样本 {{ fingerprint.sample_count }}
              </n-tag>
              <n-tag round size="small" type="default">
                当前章 · 第{{ currentSampleChapter }}章
              </n-tag>
            </n-space>

            <n-alert type="info" :show-icon="true" class="section-alert">
              当前作者样本 {{ fingerprint.sample_count }} 组。样本达到 10 组以后，现有文风漂移检测会更稳定。
            </n-alert>

            <n-grid :cols="2" :x-gap="12">
              <n-grid-item>
                <n-card size="small" :bordered="false" title="角色锁定总览">
                  <n-empty
                    v-if="characters.length === 0"
                    description="当前 Bible 里还没有角色"
                    size="small"
                  />
                  <n-space v-else vertical :size="8">
                    <button
                      v-for="character in characters"
                      :key="character.id"
                      type="button"
                      class="character-row"
                      :class="{ active: selectedCharacterId === character.id }"
                      @click="selectedCharacterId = character.id"
                    >
                      <div class="character-row-main">
                        <n-space :size="8" align="center">
                          <n-text strong>{{ character.name }}</n-text>
                          <n-tag size="small" round :type="anchorStatusType(character)">
                            {{ anchorStatusLabel(character) }}
                          </n-tag>
                        </n-space>
                        <n-text depth="3" style="font-size: 12px">
                          {{ anchorSummary(character) }}
                        </n-text>
                      </div>
                    </button>
                  </n-space>
                </n-card>
              </n-grid-item>

              <n-grid-item>
                <n-card size="small" :bordered="false" title="锚点编辑">
                  <n-empty
                    v-if="!selectedCharacter"
                    description="选择一个角色开始锁定口吻"
                    size="small"
                  />
                  <n-space v-else vertical :size="10">
                    <n-space :size="8" align="center">
                      <n-text strong>{{ selectedCharacter.name }}</n-text>
                      <n-tag size="small" round :type="anchorStatusType(selectedCharacter)">
                        {{ anchorStatusLabel(selectedCharacter) }}
                      </n-tag>
                    </n-space>

                    <div class="field-group">
                      <n-text class="field-label">心理状态</n-text>
                      <n-input
                        v-model:value="editMental"
                        size="small"
                        placeholder="如：克制、焦躁、若无其事"
                      />
                    </div>

                    <div class="field-group">
                      <n-text class="field-label">口头禅 / 固定表达</n-text>
                      <n-input
                        v-model:value="editVerbal"
                        size="small"
                        placeholder="如：先别急、你听我说完"
                      />
                    </div>

                    <div class="field-group">
                      <n-text class="field-label">小动作 / 待机动作</n-text>
                      <n-input
                        v-model:value="editIdle"
                        size="small"
                        placeholder="如：摸剑柄、转笔、避开视线"
                      />
                    </div>

                    <n-space :size="8">
                      <n-button size="small" type="primary" :loading="saveLoading" @click="saveAnchors">
                        保存锚点
                      </n-button>
                      <n-button size="small" tertiary @click="jumpToSandbox">
                        去对话沙盒试写
                      </n-button>
                      <n-button size="small" secondary @click="resetEdits">
                        恢复当前值
                      </n-button>
                    </n-space>

                    <n-alert type="default" :show-icon="false" class="section-alert">
                      更细的对白试写仍然在「对话沙盒」里；这里优先把口吻锚点固定下来。
                    </n-alert>
                  </n-space>
                </n-card>
              </n-grid-item>
            </n-grid>

            <n-card size="small" :bordered="false" title="作者样本沉淀">
              <n-space vertical :size="10">
                <n-text depth="3" style="font-size: 12px">
                  把“AI 原文 → 作者定稿”沉成样本对，后续文风漂移评分会用到它们。
                </n-text>

                <n-grid :cols="3" :x-gap="10">
                  <n-grid-item>
                    <div class="field-group">
                      <n-text class="field-label">章节号</n-text>
                      <n-input-number
                        v-model:value="sampleChapter"
                        size="small"
                        :min="1"
                        style="width: 100%"
                      />
                    </div>
                  </n-grid-item>
                  <n-grid-item>
                    <div class="field-group">
                      <n-text class="field-label">场景类型</n-text>
                      <n-input
                        v-model:value="sceneType"
                        size="small"
                        placeholder="如：对峙、暧昧、日常"
                      />
                    </div>
                  </n-grid-item>
                  <n-grid-item>
                    <div class="field-group">
                      <n-text class="field-label">选中角色</n-text>
                      <n-input
                        :value="selectedCharacter?.name || '未选择'"
                        size="small"
                        disabled
                      />
                    </div>
                  </n-grid-item>
                </n-grid>

                <div class="field-group">
                  <n-text class="field-label">AI 原文</n-text>
                  <n-input
                    v-model:value="aiOriginal"
                    type="textarea"
                    :autosize="{ minRows: 4, maxRows: 8 }"
                    placeholder="粘贴 AI 写出来但你还没满意的原稿。"
                  />
                </div>

                <div class="field-group">
                  <n-text class="field-label">作者定稿</n-text>
                  <n-input
                    v-model:value="authorRefined"
                    type="textarea"
                    :autosize="{ minRows: 4, maxRows: 8 }"
                    placeholder="粘贴你改过之后的版本，尽量保留这个角色最像本人的表达。"
                  />
                </div>

                <n-space :size="8">
                  <n-button
                    size="small"
                    type="primary"
                    :loading="sampleSaving"
                    :disabled="!canSubmitSample"
                    @click="saveVoiceSample"
                  >
                    保存样本对
                  </n-button>
                  <n-button size="small" secondary @click="resetSampleFields">
                    清空
                  </n-button>
                </n-space>
              </n-space>
            </n-card>
          </n-space>
        </template>
      </n-spin>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { useMessage } from 'naive-ui'

import { bibleApi, type CharacterDTO } from '@/api/bible'
import { sandboxApi } from '@/api/sandbox'
import { voiceApi } from '@/api/voice'
import { useWorkbenchContextStore } from '@/stores/workbenchContextStore'
import { useWorkbenchRefreshStore } from '@/stores/workbenchRefreshStore'

const props = defineProps<{
  slug: string
  currentChapter?: number | null
}>()

const message = useMessage()
const refreshStore = useWorkbenchRefreshStore()
const contextStore = useWorkbenchContextStore()
const { deskTick } = storeToRefs(refreshStore)
const { voiceLockDraft, voiceLockDraftVersion } = storeToRefs(contextStore)

const loading = ref(false)
const loadError = ref('')
const saveLoading = ref(false)
const sampleSaving = ref(false)

const characters = ref<CharacterDTO[]>([])
const selectedCharacterId = ref<string | null>(null)
const editMental = ref('NORMAL')
const editVerbal = ref('')
const editIdle = ref('')

const aiOriginal = ref('')
const authorRefined = ref('')
const sceneType = ref('general')
const sampleChapter = ref<number | null>(null)

const fingerprint = ref({
  adjective_density: 0,
  avg_sentence_length: 0,
  sentence_count: 0,
  sample_count: 0,
  last_updated: '',
})

const selectedCharacter = computed(() =>
  characters.value.find(character => character.id === selectedCharacterId.value) ?? null,
)

const currentSampleChapter = computed(() => sampleChapter.value || props.currentChapter || 1)

const canSubmitSample = computed(() =>
  Boolean(aiOriginal.value.trim() && authorRefined.value.trim() && currentSampleChapter.value >= 1),
)

function syncSelectedCharacter(character: CharacterDTO | null) {
  editMental.value = character?.mental_state || 'NORMAL'
  editVerbal.value = character?.verbal_tic || ''
  editIdle.value = character?.idle_behavior || ''
}

function anchorStrength(character: CharacterDTO) {
  let score = 0
  if ((character.mental_state || '').trim().toUpperCase() !== 'NORMAL' && (character.mental_state || '').trim()) {
    score += 1
  }
  if ((character.verbal_tic || '').trim()) score += 1
  if ((character.idle_behavior || '').trim()) score += 1
  return score
}

function anchorStatusLabel(character: CharacterDTO) {
  const score = anchorStrength(character)
  if (score >= 3) return '已锁定'
  if (score >= 1) return '基础锚点'
  return '未锁定'
}

function anchorStatusType(character: CharacterDTO) {
  const score = anchorStrength(character)
  if (score >= 3) return 'success'
  if (score >= 1) return 'warning'
  return 'default'
}

function anchorSummary(character: CharacterDTO) {
  const parts = []
  const mental = (character.mental_state || '').trim()
  const verbal = (character.verbal_tic || '').trim()
  const idle = (character.idle_behavior || '').trim()

  if (mental && mental.toUpperCase() !== 'NORMAL') parts.push(`状态：${mental}`)
  if (verbal) parts.push(`口头禅：${verbal}`)
  if (idle) parts.push(`小动作：${idle}`)

  return parts.length > 0 ? parts.join(' · ') : '还没有稳定的口吻锚点'
}

function resetEdits() {
  syncSelectedCharacter(selectedCharacter.value)
}

function resetSampleFields() {
  aiOriginal.value = ''
  authorRefined.value = ''
  sceneType.value = 'general'
  sampleChapter.value = props.currentChapter || 1
}

function buildSuggestedScenePrompt() {
  const character = selectedCharacter.value
  if (!character) return ''
  const scene = sceneType.value.trim()
  if (scene && scene !== 'general') {
    return `请写一段${character.name}在“${scene}”场景中的对白，保留当前口吻锚点。`
  }
  return `请写一段${character.name}在当前章节语境下的对白，保留当前口吻锚点。`
}

function jumpToSandbox() {
  const character = selectedCharacter.value
  if (!character) {
    message.warning('先选择角色再去对话沙盒')
    return
  }
  contextStore.openSandboxWithDraft({
    slug: props.slug,
    characterId: character.id,
    scenePrompt: buildSuggestedScenePrompt(),
    mentalState: editMental.value || 'NORMAL',
    verbalTic: editVerbal.value || '',
    idleBehavior: editIdle.value || '',
  })
  message.success('已带着当前角色上下文切到对话沙盒')
}

function applyVoiceLockDraft() {
  const draft = voiceLockDraft.value
  if (!draft || draft.slug !== props.slug) return
  if (selectedCharacterId.value === draft.characterId) return
  selectedCharacterId.value = draft.characterId
}

async function loadCharacters() {
  const result = await bibleApi.listCharacters(props.slug)
  characters.value = result

  if (!selectedCharacterId.value || !result.some(character => character.id === selectedCharacterId.value)) {
    selectedCharacterId.value = result[0]?.id ?? null
  }
  syncSelectedCharacter(
    result.find(character => character.id === selectedCharacterId.value) ?? null,
  )
}

async function loadFingerprint() {
  fingerprint.value = await voiceApi.getFingerprint(props.slug)
}

async function reloadAll() {
  if (!props.slug) return
  loading.value = true
  loadError.value = ''
  try {
    await Promise.all([loadCharacters(), loadFingerprint()])
    if (!sampleChapter.value) {
      sampleChapter.value = props.currentChapter || 1
    }
  } catch {
    loadError.value = '加载口吻锁定面板失败，请稍后重试'
  } finally {
    loading.value = false
  }
}

async function saveAnchors() {
  const character = selectedCharacter.value
  if (!character) return

  saveLoading.value = true
  try {
    const updated = await sandboxApi.patchCharacterAnchor(props.slug, character.id, {
      mental_state: editMental.value || 'NORMAL',
      verbal_tic: editVerbal.value || '',
      idle_behavior: editIdle.value || '',
    })

    characters.value = characters.value.map(item =>
      item.id === character.id
        ? {
            ...item,
            mental_state: updated.mental_state,
            verbal_tic: updated.verbal_tic,
            idle_behavior: updated.idle_behavior,
          }
        : item,
    )
    syncSelectedCharacter(
      characters.value.find(item => item.id === character.id) ?? null,
    )
    refreshStore.bumpDesk()
    message.success('角色口吻锚点已保存')
  } catch {
    message.error('保存锚点失败')
  } finally {
    saveLoading.value = false
  }
}

async function saveVoiceSample() {
  if (!canSubmitSample.value) return

  sampleSaving.value = true
  try {
    await voiceApi.createSample(props.slug, {
      ai_original: aiOriginal.value.trim(),
      author_refined: authorRefined.value.trim(),
      chapter_number: currentSampleChapter.value,
      scene_type: sceneType.value.trim() || 'general',
    })
    await loadFingerprint()
    resetSampleFields()
    message.success('文风样本已加入金库')
  } catch {
    message.error('保存文风样本失败')
  } finally {
    sampleSaving.value = false
  }
}

watch(
  () => props.slug,
  () => {
    selectedCharacterId.value = null
    resetSampleFields()
    void reloadAll()
  },
)

watch(
  () => props.currentChapter,
  (value) => {
    if (!sampleChapter.value && value) {
      sampleChapter.value = value
    }
  },
)

watch(selectedCharacter, character => {
  syncSelectedCharacter(character)
})

watch(
  [voiceLockDraftVersion, () => props.slug],
  () => {
    applyVoiceLockDraft()
  },
)

watch(deskTick, () => {
  void reloadAll()
})

onMounted(() => {
  sampleChapter.value = props.currentChapter || 1
  void reloadAll()
  applyVoiceLockDraft()
})
</script>

<style scoped>
.voice-lock-panel {
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: var(--aitext-panel-muted);
}

.panel-header {
  padding: 16px;
  border-bottom: 1px solid var(--aitext-split-border);
  background: var(--app-surface);
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
}

.header-main {
  flex: 1;
  min-width: 0;
}

.title-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.panel-title {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: var(--text-color-1);
}

.panel-lead {
  margin: 0;
  font-size: 13px;
  line-height: 1.5;
  color: var(--text-color-3);
}

.panel-content {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
}

.section-alert {
  margin: 0;
}

.character-row {
  width: 100%;
  border: 1px solid var(--aitext-split-border);
  background: var(--app-surface);
  border-radius: 10px;
  padding: 10px 12px;
  text-align: left;
  transition: border-color 0.18s ease, background 0.18s ease;
}

.character-row:hover {
  border-color: var(--primary-color);
}

.character-row.active {
  border-color: var(--primary-color);
  background: color-mix(in srgb, var(--primary-color) 6%, var(--app-surface));
}

.character-row-main {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.field-group {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.field-label {
  font-size: 12px;
  color: var(--text-color-2);
}
</style>
