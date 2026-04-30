<template>
  <div class="style-bible-panel">
    <n-space vertical :size="12">
      <n-card size="small" :bordered="false" class="compact-card">
        <template #header>
          <n-space justify="space-between" align="center">
            <span>写作手法库</span>
            <n-button size="tiny" secondary :loading="loading" @click="loadAll">刷新</n-button>
          </n-space>
        </template>

        <n-space vertical :size="10">
          <n-input v-model:value="sampleTitle" size="small" placeholder="样本标题" />
          <n-space :size="8">
            <n-input v-model:value="sceneType" size="small" placeholder="场景类型，如悬疑/情感" />
            <n-checkbox v-model:checked="allowedForGeneration">允许用于生成</n-checkbox>
          </n-space>
          <n-space justify="space-between" align="center" wrap class="sample-source-row">
            <n-text depth="3" style="font-size: 12px">
              可粘贴文本，也可上传 .txt / .md
            </n-text>
            <n-upload
              accept=".txt,.md,.markdown,text/plain,text/markdown"
              :max="1"
              :show-file-list="false"
              @change="handleSampleFileSelect"
            >
              <n-button size="tiny" secondary :loading="readingSampleFile">
                上传文件
              </n-button>
            </n-upload>
          </n-space>
          <n-input
            v-model:value="sampleContent"
            type="textarea"
            placeholder="粘贴完整小说片段或章节。系统只学习节奏、手法和禁用表达，不复刻角色和设定。"
            :autosize="{ minRows: 5, maxRows: 10 }"
          />
          <n-space justify="end">
            <n-button
              size="small"
              secondary
              :loading="importing"
              :disabled="!canImport"
              @click="importOnly"
            >
              仅导入
            </n-button>
            <n-button
              size="small"
              type="primary"
              :loading="importing"
              :disabled="!canImport"
              @click="importAndProfile"
            >
              导入并生成档案
            </n-button>
          </n-space>
        </n-space>
      </n-card>

      <n-card size="small" :bordered="false" class="compact-card">
        <template #header>
          <n-space justify="space-between" align="center">
            <span>风格档案</span>
            <n-button
              size="tiny"
              secondary
              :loading="generatingProfile"
              :disabled="selectedSampleIds.length === 0"
              @click="generateProfileFromSelected"
            >
              用选中样本生成
            </n-button>
          </n-space>
        </template>

        <n-space vertical :size="10">
          <n-input v-model:value="profileName" size="small" placeholder="新档案名称" />
          <n-space :size="8" align="center" wrap class="analysis-config-row">
            <n-checkbox v-model:checked="useLlmAnalysis">AI分析</n-checkbox>
            <n-select
              v-model:value="analysisLlmProfileId"
              size="small"
              :options="llmProfileOptions"
              :loading="loadingLlmProfiles"
              :disabled="!useLlmAnalysis"
              clearable
              placeholder="选择分析模型配置"
              style="min-width: 220px; flex: 1"
            />
            <n-button size="tiny" secondary :loading="loadingLlmProfiles" @click="loadLlmProfiles">
              刷新配置
            </n-button>
          </n-space>
          <n-space v-if="samples.length" :size="6" wrap>
            <n-tag
              v-for="sample in samples"
              :key="sample.id"
              size="small"
              checkable
              :checked="selectedSampleIds.includes(sample.id)"
              @update:checked="(checked: boolean) => toggleSample(sample.id, checked)"
            >
              {{ sample.title }} · {{ sample.char_count }}字
            </n-tag>
          </n-space>
          <n-empty v-else size="small" description="还没有样本" />

          <n-divider style="margin: 6px 0" />

          <n-space v-if="profiles.length" vertical :size="8">
            <button
              v-for="item in profiles"
              :key="item.profile.id"
              class="profile-row"
              :class="{ 'profile-row--active': item.profile.id === selectedProfileId }"
              type="button"
              @click="selectProfile(item.profile.id)"
            >
              <span>
                <strong>{{ item.profile.name }}</strong>
                <small>{{ metricSummary(item.profile.metrics) }}</small>
              </span>
              <n-tag size="tiny" round>{{ item.cards.length }} 卡</n-tag>
            </button>
          </n-space>
          <n-empty v-else size="small" description="还没有风格档案" />
        </n-space>
      </n-card>

      <n-card v-if="selectedProfile" size="small" :bordered="false" class="compact-card">
        <template #header>
          <n-space justify="space-between" align="center">
            <span>{{ selectedProfile.profile.name }}</span>
            <n-button size="tiny" secondary :loading="previewingOverlay" @click="previewOverlay">预览注入</n-button>
          </n-space>
        </template>

        <n-space vertical :size="8">
          <n-space :size="6" wrap>
            <n-tag
              v-for="pattern in selectedProfile.profile.forbidden_patterns.slice(0, 6)"
              :key="pattern"
              size="small"
              type="warning"
              round
            >
              {{ pattern }}
            </n-tag>
          </n-space>

          <n-card
            v-for="card in selectedProfile.cards"
            :key="card.id"
            size="small"
            :bordered="true"
            class="tech-card"
          >
            <n-space vertical :size="6">
              <n-space justify="space-between" align="center">
                <n-space :size="6" align="center">
                  <n-tag size="tiny" round>{{ card.category || 'rule' }}</n-tag>
                  <strong>{{ card.title }}</strong>
                </n-space>
                <n-space :size="6" align="center">
                  <n-button size="tiny" secondary @click="openCardEditor(card)">
                    编辑
                  </n-button>
                  <n-switch
                    size="small"
                    :value="card.enabled"
                    :loading="updatingCardId === card.id"
                    @update:value="(enabled: boolean) => updateCard(card.id, { enabled })"
                  />
                </n-space>
              </n-space>
              <n-text v-if="card.rule_text" depth="3" style="font-size: 12px; line-height: 1.6">
                {{ card.rule_text }}
              </n-text>
              <n-text depth="3" style="font-size: 12px; line-height: 1.6">
                {{ card.prompt_instruction }}
              </n-text>
            </n-space>
          </n-card>

          <n-input
            v-if="overlayText"
            :value="overlayText"
            type="textarea"
            readonly
            :autosize="{ minRows: 5, maxRows: 10 }"
          />
        </n-space>
      </n-card>
    </n-space>

    <n-modal
      v-model:show="showCardEditor"
      preset="card"
      title="编辑技法卡"
      style="width: min(760px, 94vw)"
      :segmented="{ content: true, footer: 'soft' }"
      :mask-closable="!updatingCardId"
    >
      <n-space vertical :size="12">
        <n-space :size="8">
          <n-input v-model:value="cardEditForm.title" size="small" placeholder="标题" />
          <n-input v-model:value="cardEditForm.category" size="small" placeholder="分类，如 pacing/dialogue/anti_ai" />
        </n-space>
        <n-space :size="8">
          <n-input v-model:value="cardEditForm.scene_type" size="small" placeholder="适用场景，可留空" />
          <n-input-number
            v-model:value="cardEditForm.weight"
            size="small"
            :min="0"
            :max="2"
            :step="0.05"
            placeholder="权重"
            style="width: 150px"
          />
        </n-space>
        <n-input
          v-model:value="cardEditForm.rule_text"
          type="textarea"
          placeholder="手法规则：描述这张卡要捕捉的写法"
          :autosize="{ minRows: 3, maxRows: 6 }"
        />
        <n-input
          v-model:value="cardEditForm.example_summary"
          type="textarea"
          placeholder="样本依据：说明它来自哪些样本现象"
          :autosize="{ minRows: 2, maxRows: 5 }"
        />
        <n-input
          v-model:value="cardEditForm.prompt_instruction"
          type="textarea"
          placeholder="生成指令：会注入章节生成提示词，尽量写成可执行约束"
          :autosize="{ minRows: 4, maxRows: 8 }"
        />
        <n-checkbox v-model:checked="cardEditForm.enabled">启用这张技法卡</n-checkbox>
      </n-space>

      <template #footer>
        <n-space justify="end">
          <n-button @click="showCardEditor = false" :disabled="Boolean(updatingCardId)">取消</n-button>
          <n-button
            type="primary"
            :loading="Boolean(updatingCardId)"
            :disabled="!canSaveCardEdit"
            @click="saveCardEditor"
          >
            保存
          </n-button>
        </n-space>
      </template>
    </n-modal>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useMessage } from 'naive-ui'
import {
  styleBibleApi,
  type StyleProfileDetail,
  type StyleSampleDTO,
  type StyleTechniqueCardDTO,
  type UpdateTechniqueCardPayload,
} from '@/api/styleBible'
import { llmControlApi, type LLMProfile } from '@/api/llmControl'

const props = defineProps<{
  slug: string
  currentChapter?: number | null
}>()

const message = useMessage()
const loading = ref(false)
const importing = ref(false)
const readingSampleFile = ref(false)
const generatingProfile = ref(false)
const previewingOverlay = ref(false)
const updatingCardId = ref<string | null>(null)
const sampleTitle = ref('')
const sampleContent = ref('')
const sceneType = ref('')
const allowedForGeneration = ref(true)
const profileName = ref('我的写作手法档案')
const useLlmAnalysis = ref(true)
const analysisLlmProfileId = ref('')
const llmProfiles = ref<LLMProfile[]>([])
const loadingLlmProfiles = ref(false)
const samples = ref<StyleSampleDTO[]>([])
const profiles = ref<StyleProfileDetail[]>([])
const selectedSampleIds = ref<string[]>([])
const selectedProfileId = ref('')
const overlayText = ref('')
const showCardEditor = ref(false)
const editingCardId = ref('')
const cardEditForm = reactive({
  title: '',
  category: '',
  scene_type: '',
  rule_text: '',
  example_summary: '',
  prompt_instruction: '',
  enabled: true,
  weight: 1,
})

const canImport = computed(() => sampleTitle.value.trim() && sampleContent.value.trim())
const selectedProfile = computed(() => profiles.value.find(item => item.profile.id === selectedProfileId.value) || null)
const canSaveCardEdit = computed(() =>
  Boolean(editingCardId.value && cardEditForm.title.trim() && cardEditForm.prompt_instruction.trim())
)
const llmProfileOptions = computed(() =>
  llmProfiles.value.map(profile => ({
    label: `${profile.name}${profile.model ? ` · ${profile.model}` : ''}`,
    value: profile.id,
  }))
)

async function loadAll() {
  loading.value = true
  try {
    const [nextSamples, nextProfiles] = await Promise.all([
      styleBibleApi.listSamples({ novel_id: props.slug }),
      styleBibleApi.listProfiles({ novel_id: props.slug }),
    ])
    samples.value = nextSamples
    profiles.value = nextProfiles
    if (!selectedProfileId.value && nextProfiles.length) {
      selectedProfileId.value = nextProfiles[0].profile.id
    }
  } catch {
    message.error('写作手法库加载失败')
  } finally {
    loading.value = false
  }
}

async function loadLlmProfiles() {
  loadingLlmProfiles.value = true
  try {
    const panel = await llmControlApi.getPanel()
    llmProfiles.value = panel.config.profiles
    if (!analysisLlmProfileId.value && panel.config.active_profile_id) {
      analysisLlmProfileId.value = panel.config.active_profile_id
    }
  } catch {
    message.error('AI配置加载失败')
  } finally {
    loadingLlmProfiles.value = false
  }
}

async function importOnly() {
  await importSample(false)
}

async function importAndProfile() {
  await importSample(true)
}

async function handleSampleFileSelect(data: {
  file: { file?: File | null; name?: string }
  fileList: Array<{ file?: File | null }>
}) {
  const file = data.file?.file
  if (!file) return
  readingSampleFile.value = true
  try {
    const text = await readTextFile(file)
    const content = text.trim()
    if (!content) {
      message.warning('文件内容为空')
      return
    }
    sampleContent.value = content
    if (!sampleTitle.value.trim()) {
      sampleTitle.value = file.name.replace(/\.(txt|md|markdown)$/i, '')
    }
    message.success(`已读取 ${file.name}`)
  } catch {
    message.error('文件读取失败')
  } finally {
    readingSampleFile.value = false
  }
}

async function readTextFile(file: File) {
  const buffer = await file.arrayBuffer()
  const utf8 = new TextDecoder('utf-8').decode(buffer)
  const replacementCount = (utf8.match(/\uFFFD/g) || []).length
  if (replacementCount <= Math.max(3, utf8.length * 0.01)) {
    return utf8
  }
  try {
    return new TextDecoder('gb18030').decode(buffer)
  } catch {
    return utf8
  }
}

async function importSample(createProfile: boolean) {
  importing.value = true
  try {
    const result = await styleBibleApi.importSample({
      title: sampleTitle.value.trim(),
      content: sampleContent.value.trim(),
      novel_id: props.slug,
      scene_type: sceneType.value.trim(),
      allowed_for_generation: allowedForGeneration.value,
      create_profile: false,
      profile_name: profileName.value.trim() || sampleTitle.value.trim(),
    })
    sampleTitle.value = ''
    sampleContent.value = ''
    selectedSampleIds.value = [result.sample.id]
    if (createProfile) {
      const profileResult = await generateProfileForSamples(
        [result.sample.id],
        profileName.value.trim() || result.sample.title
      )
      selectedProfileId.value = profileResult.profile.id
    }
    message.success(createProfile ? '已导入并生成风格档案' : '样本已导入')
    await loadAll()
  } catch {
    message.error('样本导入失败')
  } finally {
    importing.value = false
  }
}

function toggleSample(sampleId: string, checked: boolean) {
  selectedSampleIds.value = checked
    ? Array.from(new Set([...selectedSampleIds.value, sampleId]))
    : selectedSampleIds.value.filter(id => id !== sampleId)
}

async function generateProfileFromSelected() {
  generatingProfile.value = true
  try {
    const result = await generateProfileForSamples(selectedSampleIds.value)
    selectedProfileId.value = result.profile.id
    message.success('风格档案已生成')
    await loadAll()
  } catch {
    message.error('风格档案生成失败')
  } finally {
    generatingProfile.value = false
  }
}

async function generateProfileForSamples(sampleIds: string[], name?: string) {
  return styleBibleApi.generateProfile({
    novel_id: props.slug,
    name: name || profileName.value.trim() || '我的写作手法档案',
    sample_ids: sampleIds,
    use_llm: useLlmAnalysis.value,
    llm_profile_id: useLlmAnalysis.value ? (analysisLlmProfileId.value || '') : '',
  })
}

function selectProfile(profileId: string) {
  selectedProfileId.value = profileId
  overlayText.value = ''
}

async function updateCard(cardId: string, payload: UpdateTechniqueCardPayload) {
  updatingCardId.value = cardId
  try {
    await styleBibleApi.updateCard(cardId, payload)
    overlayText.value = ''
    await loadAll()
    return true
  } catch {
    message.error('技法卡更新失败')
    return false
  } finally {
    updatingCardId.value = null
  }
}

function openCardEditor(card: StyleTechniqueCardDTO) {
  editingCardId.value = card.id
  cardEditForm.title = card.title
  cardEditForm.category = card.category
  cardEditForm.scene_type = card.scene_type
  cardEditForm.rule_text = card.rule_text
  cardEditForm.example_summary = card.example_summary
  cardEditForm.prompt_instruction = card.prompt_instruction
  cardEditForm.enabled = card.enabled
  cardEditForm.weight = Number(card.weight || 1)
  showCardEditor.value = true
}

async function saveCardEditor() {
  if (!editingCardId.value || !canSaveCardEdit.value) return
  const saved = await updateCard(editingCardId.value, {
    title: cardEditForm.title.trim(),
    category: cardEditForm.category.trim(),
    scene_type: cardEditForm.scene_type.trim(),
    rule_text: cardEditForm.rule_text.trim(),
    example_summary: cardEditForm.example_summary.trim(),
    prompt_instruction: cardEditForm.prompt_instruction.trim(),
    enabled: cardEditForm.enabled,
    weight: Number(cardEditForm.weight || 1),
  })
  if (saved) {
    showCardEditor.value = false
  }
}

async function previewOverlay() {
  if (!selectedProfileId.value) return
  previewingOverlay.value = true
  try {
    const result = await styleBibleApi.previewOverlay({
      novel_id: props.slug,
      style_profile_id: selectedProfileId.value,
      scene_type: sceneType.value.trim(),
      max_cards: 6,
    })
    overlayText.value = result.prompt
  } catch {
    message.error('预览失败')
  } finally {
    previewingOverlay.value = false
  }
}

function metricSummary(metrics: Record<string, any>) {
  const sentence = Number(metrics?.avg_sentence_length || 0)
  const dialogue = Number(metrics?.dialogue_ratio || 0)
  return `${sentence ? `${sentence.toFixed(1)}字/句` : '待分析'} · 对白${Math.round(dialogue * 100)}%`
}

watch(() => props.slug, () => {
  selectedProfileId.value = ''
  overlayText.value = ''
  void loadAll()
})

onMounted(() => {
  void loadAll()
  void loadLlmProfiles()
})
</script>

<style scoped>
.style-bible-panel {
  height: 100%;
  min-height: 0;
  overflow-x: hidden;
  overflow-y: auto;
  padding: 10px 12px 16px;
}

.compact-card {
  background: rgba(255, 255, 255, 0.78);
}

.analysis-config-row {
  min-width: 0;
}

.sample-source-row {
  min-width: 0;
}

.profile-row {
  width: 100%;
  min-height: 54px;
  padding: 8px 10px;
  border: 1px solid rgba(148, 163, 184, 0.24);
  border-radius: 8px;
  background: #fff;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  text-align: left;
  cursor: pointer;
}

.profile-row--active {
  border-color: #6366f1;
  background: #eef2ff;
}

.profile-row strong,
.profile-row small {
  display: block;
}

.profile-row strong {
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.profile-row small {
  margin-top: 4px;
  color: #64748b;
  font-size: 11px;
}

.tech-card {
  background: #fff;
}
</style>
