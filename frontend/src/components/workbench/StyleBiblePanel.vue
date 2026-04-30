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
                <n-switch
                  size="small"
                  :value="card.enabled"
                  :loading="updatingCardId === card.id"
                  @update:value="(enabled: boolean) => updateCard(card.id, { enabled })"
                />
              </n-space>
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
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useMessage } from 'naive-ui'
import {
  styleBibleApi,
  type StyleProfileDetail,
  type StyleSampleDTO,
  type UpdateTechniqueCardPayload,
} from '@/api/styleBible'

const props = defineProps<{
  slug: string
  currentChapter?: number | null
}>()

const message = useMessage()
const loading = ref(false)
const importing = ref(false)
const generatingProfile = ref(false)
const previewingOverlay = ref(false)
const updatingCardId = ref<string | null>(null)
const sampleTitle = ref('')
const sampleContent = ref('')
const sceneType = ref('')
const allowedForGeneration = ref(true)
const profileName = ref('我的写作手法档案')
const samples = ref<StyleSampleDTO[]>([])
const profiles = ref<StyleProfileDetail[]>([])
const selectedSampleIds = ref<string[]>([])
const selectedProfileId = ref('')
const overlayText = ref('')

const canImport = computed(() => sampleTitle.value.trim() && sampleContent.value.trim())
const selectedProfile = computed(() => profiles.value.find(item => item.profile.id === selectedProfileId.value) || null)

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

async function importOnly() {
  await importSample(false)
}

async function importAndProfile() {
  await importSample(true)
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
      create_profile: createProfile,
      profile_name: profileName.value.trim() || sampleTitle.value.trim(),
    })
    sampleTitle.value = ''
    sampleContent.value = ''
    selectedSampleIds.value = [result.sample.id]
    if (result.profile) {
      selectedProfileId.value = result.profile.id
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
    const result = await styleBibleApi.generateProfile({
      novel_id: props.slug,
      name: profileName.value.trim() || '我的写作手法档案',
      sample_ids: selectedSampleIds.value,
    })
    selectedProfileId.value = result.profile.id
    message.success('风格档案已生成')
    await loadAll()
  } catch {
    message.error('风格档案生成失败')
  } finally {
    generatingProfile.value = false
  }
}

function selectProfile(profileId: string) {
  selectedProfileId.value = profileId
  overlayText.value = ''
}

async function updateCard(cardId: string, payload: UpdateTechniqueCardPayload) {
  updatingCardId.value = cardId
  try {
    await styleBibleApi.updateCard(cardId, payload)
    await loadAll()
  } catch {
    message.error('技法卡更新失败')
  } finally {
    updatingCardId.value = null
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
})
</script>

<style scoped>
.style-bible-panel {
  padding: 10px 12px 16px;
}

.compact-card {
  background: rgba(255, 255, 255, 0.78);
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

.profile-row small {
  margin-top: 4px;
  color: #64748b;
  font-size: 11px;
}

.tech-card {
  background: #fff;
}
</style>
