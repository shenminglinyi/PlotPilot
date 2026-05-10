<template>
  <div class="character-profile">
    <div class="profile-header">
      <n-text strong style="font-size: 14px">角色档案</n-text>
    </div>

    <!-- 未选中状态 -->
    <div v-if="!selectedCharacterId" class="profile-empty">
      <n-empty description="选择角色查看档案" size="small" />
    </div>

    <!-- 选中角色后 -->
    <n-spin v-else :show="loading">
      <div class="profile-content">
        <!-- 角色速写（来自 mask_summary） -->
        <n-card v-if="psycheDetail?.mask_summary" size="small" :bordered="true" class="profile-card sketch-card">
          <template #header>
            <n-space align="center" :size="8">
              <span class="card-icon">🎭</span>
              <n-text strong>角色速写</n-text>
              <n-tag v-if="psycheDetail.role" size="small" :bordered="false" type="info">
                {{ psycheDetail.role }}
              </n-tag>
            </n-space>
          </template>
          <div class="sketch-content">
            <n-text style="font-size: 12px; line-height: 1.8; white-space: pre-line">
              {{ psycheDetail.mask_summary }}
            </n-text>
          </div>
        </n-card>

        <!-- 四维心理画像 -->
        <n-card size="small" :bordered="true" class="profile-card">
          <template #header>
            <n-space align="center" :size="8">
              <span class="card-icon">🧠</span>
              <n-text strong>心理画像</n-text>
            </n-space>
          </template>

          <div class="dimension-grid">
            <!-- 核心信念 -->
            <div class="dimension-item belief">
              <div class="dimension-label">
                <span class="dim-icon">💡</span>
                <n-text depth="3" style="font-size: 11px">核心信念</n-text>
              </div>
              <n-text v-if="psycheDetail?.core_belief" style="font-size: 12px; line-height: 1.6">
                {{ psycheDetail.core_belief }}
              </n-text>
              <n-text v-else depth="3" style="font-size: 11px; font-style: italic">
                未从设定中提取到信念
              </n-text>
              <n-text depth="3" style="font-size: 10px; margin-top: 2px">
                做价值选择时的底层驱动力
              </n-text>
            </div>

            <!-- 绝对禁忌 -->
            <div class="dimension-item taboo">
              <div class="dimension-label">
                <span class="dim-icon">🚫</span>
                <n-text depth="3" style="font-size: 11px">绝对禁忌</n-text>
              </div>
              <n-text v-if="psycheDetail?.taboo" style="font-size: 12px; line-height: 1.6">
                {{ psycheDetail.taboo }}
              </n-text>
              <n-text v-else depth="3" style="font-size: 11px; font-style: italic">
                未从设定中提取到禁忌
              </n-text>
              <n-text depth="3" style="font-size: 10px; margin-top: 2px">
                触碰即崩的行为红线
              </n-text>
            </div>

            <!-- 声线指纹 -->
            <div class="dimension-item voice">
              <div class="dimension-label">
                <span class="dim-icon">🗣️</span>
                <n-text depth="3" style="font-size: 11px">声线指纹</n-text>
              </div>
              <n-text v-if="psycheDetail?.voice_tag" style="font-size: 12px; line-height: 1.6">
                {{ psycheDetail.voice_tag }}
              </n-text>
              <n-text v-else depth="3" style="font-size: 11px; font-style: italic">
                未从设定中提取到声线
              </n-text>
              <n-text depth="3" style="font-size: 10px; margin-top: 2px">
                闭上眼也能认出的说话方式
              </n-text>
            </div>

            <!-- 条件反射 -->
            <div class="dimension-item wound">
              <div class="dimension-label">
                <span class="dim-icon">⚡</span>
                <n-text depth="3" style="font-size: 11px">条件反射</n-text>
              </div>
              <n-text v-if="psycheDetail?.wound" style="font-size: 12px; line-height: 1.6">
                {{ psycheDetail.wound }}
              </n-text>
              <n-text v-else depth="3" style="font-size: 11px; font-style: italic">
                未从设定中提取到创伤
              </n-text>
              <n-text depth="3" style="font-size: 10px; margin-top: 2px">
                压力下的非理性行为触发器
              </n-text>
            </div>
          </div>

          <!-- 创伤演化计数 -->
          <div v-if="psycheDetail && psycheDetail.trauma_count > 0" class="trauma-badge">
            <n-tag size="small" type="warning" :bordered="false">
              {{ psycheDetail.trauma_count }} 次心理转折
            </n-tag>
          </div>
        </n-card>

        <!-- 即时锚点（可编辑） -->
        <n-card size="small" :bordered="true" class="profile-card">
          <template #header>
            <n-space align="center" :size="8">
              <span class="card-icon">⚓</span>
              <n-text strong>即时锚点</n-text>
            </n-space>
          </template>

          <n-space vertical :size="10">
            <n-grid :cols="1" :x-gap="10">
              <n-gi>
                <div class="anchor-field">
                  <n-text depth="3" style="font-size: 11px">心理状态</n-text>
                  <n-input
                    v-model:value="editMental"
                    size="small"
                    placeholder="如：平静、焦虑、压抑"
                    :disabled="!editingAnchor"
                  />
                </div>
              </n-gi>
              <n-gi>
                <div class="anchor-field">
                  <n-text depth="3" style="font-size: 11px">口头禅</n-text>
                  <n-input
                    v-model:value="editVerbal"
                    size="small"
                    placeholder="如：嗯...、岂有此理"
                    :disabled="!editingAnchor"
                  />
                </div>
              </n-gi>
              <n-gi>
                <div class="anchor-field">
                  <n-text depth="3" style="font-size: 11px">小动作</n-text>
                  <n-input
                    v-model:value="editIdle"
                    size="small"
                    placeholder="如：摸剑柄、转笔"
                    :disabled="!editingAnchor"
                  />
                </div>
              </n-gi>
            </n-grid>

            <n-space :size="8">
              <n-button
                v-if="!editingAnchor"
                size="small"
                type="primary"
                @click="startEditAnchor"
              >
                编辑锚点
              </n-button>
              <template v-else>
                <n-button
                  size="small"
                  type="primary"
                  :loading="savingAnchor"
                  @click="saveAnchor"
                >
                  保存
                </n-button>
                <n-button
                  size="small"
                  @click="cancelEditAnchor"
                >
                  取消
                </n-button>
              </template>
            </n-space>
          </n-space>
        </n-card>

        <!-- 工具区：试声线 + 行为验证 -->
        <n-card size="small" :bordered="true" class="profile-card">
          <n-collapse>
            <!-- 试声线 -->
            <n-collapse-item title="🗣️ 试声线" name="voice">
              <n-space vertical :size="8">
                <n-text depth="3" style="font-size: 12px">
                  描述一个场景，测试该角色在此场景下会怎么说。
                </n-text>
                <n-input
                  v-model:value="scenePrompt"
                  type="textarea"
                  size="small"
                  placeholder="例如：被信任的人背叛后的第一反应"
                  :autosize="{ minRows: 2, maxRows: 4 }"
                />
                <n-button
                  type="primary"
                  size="small"
                  :loading="generating"
                  :disabled="!scenePrompt.trim()"
                  @click="generateDialogue"
                >
                  生成对话
                </n-button>
                <n-card
                  v-if="generatedLine"
                  size="small"
                  :bordered="true"
                  class="generated-output"
                >
                  <n-text style="font-size: 13px; line-height: 1.7">
                    {{ generatedLine }}
                  </n-text>
                </n-card>
              </n-space>
            </n-collapse-item>

            <!-- 行为验证 -->
            <n-collapse-item title="🔍 行为验证" name="validate">
              <n-space vertical :size="8">
                <n-text depth="3" style="font-size: 12px">
                  输入一段行为描写，检验是否违背该角色的核心设定。
                </n-text>
                <n-input
                  v-model:value="validateAction"
                  type="textarea"
                  placeholder="例如：他毫不犹豫地相信了那个陌生人"
                  :autosize="{ minRows: 2, maxRows: 4 }"
                  size="small"
                />
                <n-button
                  size="small"
                  type="primary"
                  :loading="validating"
                  :disabled="!validateAction.trim()"
                  @click="runValidate"
                >
                  验证
                </n-button>
                <div v-if="validateResult">
                  <n-alert
                    :type="validateResult.valid ? 'success' : 'warning'"
                    :show-icon="true"
                    size="small"
                    style="margin-bottom: 6px"
                  >
                    {{ validateResult.valid ? '行为符合设定' : '行为可能不符合设定' }}
                  </n-alert>
                  <div v-if="validateResult.warnings.length > 0">
                    <n-text depth="3" style="font-size: 12px; display: block; margin-bottom: 4px">⚠️ 警告：</n-text>
                    <ul class="validate-list">
                      <li v-for="(w, i) in validateResult.warnings" :key="i">{{ w }}</li>
                    </ul>
                  </div>
                  <div v-if="validateResult.suggestions.length > 0">
                    <n-text depth="3" style="font-size: 12px; display: block; margin-bottom: 4px">💡 建议：</n-text>
                    <ul class="validate-list">
                      <li v-for="(s, i) in validateResult.suggestions" :key="i">{{ s }}</li>
                    </ul>
                  </div>
                </div>
              </n-space>
            </n-collapse-item>
          </n-collapse>
        </n-card>
      </div>
    </n-spin>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { useMessage } from 'naive-ui'
import { sandboxApi, type CharacterAnchor } from '@/api/sandbox'
import {
  characterPsycheApi,
  type CharacterPsycheDetailDTO,
  type ValidateBehaviorResponse,
} from '@/api/engineCore'
import { bibleApi } from '@/api/bible'

interface Props {
  slug: string
  selectedCharacterId: string | null
}

const props = defineProps<Props>()
const emit = defineEmits<{
  'refresh': []
}>()

const message = useMessage()

const loading = ref(false)
const characterName = ref('')
const anchor = ref<CharacterAnchor | null>(null)
const psycheDetail = ref<CharacterPsycheDetailDTO | null>(null)

// 锚点编辑
const editingAnchor = ref(false)
const savingAnchor = ref(false)
const editMental = ref('')
const editVerbal = ref('')
const editIdle = ref('')

// 试生成对话
const scenePrompt = ref('')
const generating = ref(false)
const generatedLine = ref('')

// 行为验证
const validateAction = ref('')
const validating = ref(false)
const validateResult = ref<ValidateBehaviorResponse | null>(null)

async function getCharacterName(id: string): Promise<string> {
  try {
    const bible = await bibleApi.getBible(props.slug)
    const char = bible.characters?.find(c => c.id === id)
    return char?.name || ''
  } catch {
    return ''
  }
}

async function loadCharacterData() {
  if (!props.selectedCharacterId) {
    anchor.value = null
    psycheDetail.value = null
    return
  }

  loading.value = true
  try {
    // 获取角色名称
    characterName.value = await getCharacterName(props.selectedCharacterId)

    // 并行加载锚点和心理画像
    const [anchorRes, psycheRes] = await Promise.all([
      sandboxApi.getCharacterAnchor(props.slug, props.selectedCharacterId).catch(() => null),
      characterName.value
        ? characterPsycheApi.get(props.slug, characterName.value).catch(() => null)
        : Promise.resolve(null),
    ])

    anchor.value = anchorRes
    psycheDetail.value = psycheRes

    // 初始化编辑字段
    if (anchorRes) {
      editMental.value = anchorRes.mental_state || ''
      editVerbal.value = anchorRes.verbal_tic || ''
      editIdle.value = anchorRes.idle_behavior || ''
    }
  } catch (err: any) {
    message.error(err.message || '加载角色数据失败')
    anchor.value = null
    psycheDetail.value = null
  } finally {
    loading.value = false
  }
}

function startEditAnchor() {
  editingAnchor.value = true
  if (anchor.value) {
    editMental.value = anchor.value.mental_state || ''
    editVerbal.value = anchor.value.verbal_tic || ''
    editIdle.value = anchor.value.idle_behavior || ''
  }
}

function cancelEditAnchor() {
  editingAnchor.value = false
  if (anchor.value) {
    editMental.value = anchor.value.mental_state || ''
    editVerbal.value = anchor.value.verbal_tic || ''
    editIdle.value = anchor.value.idle_behavior || ''
  }
  scenePrompt.value = ''
  generatedLine.value = ''
}

async function saveAnchor() {
  if (!props.selectedCharacterId) return

  savingAnchor.value = true
  try {
    await sandboxApi.patchCharacterAnchor(props.slug, props.selectedCharacterId, {
      mental_state: editMental.value,
      verbal_tic: editVerbal.value,
      idle_behavior: editIdle.value,
    })
    message.success('锚点已保存')
    editingAnchor.value = false

    // 重新加载
    await loadCharacterData()
  } catch (err: any) {
    message.error(err.message || '保存锚点失败')
  } finally {
    savingAnchor.value = false
  }
}

async function generateDialogue() {
  if (!props.selectedCharacterId || !scenePrompt.value.trim()) return

  generating.value = true
  try {
    const res = await sandboxApi.generateDialogue({
      novel_id: props.slug,
      character_id: props.selectedCharacterId,
      scene_prompt: scenePrompt.value,
      mental_state: editMental.value,
      verbal_tic: editVerbal.value,
      idle_behavior: editIdle.value,
    })
    generatedLine.value = res.dialogue || ''
  } catch (err: any) {
    message.error(err.message || '生成对话失败')
    generatedLine.value = ''
  } finally {
    generating.value = false
  }
}

async function runValidate() {
  if (!characterName.value || !validateAction.value.trim()) return

  validating.value = true
  try {
    const res = await characterPsycheApi.validate(
      props.slug,
      characterName.value,
      { action: validateAction.value }
    )
    validateResult.value = res
  } catch (err: any) {
    message.error(err.message || '行为验证失败')
    validateResult.value = null
  } finally {
    validating.value = false
  }
}

watch(() => props.selectedCharacterId, () => {
  void loadCharacterData()
}, { immediate: true })
</script>

<style scoped>
.character-profile {
  height: 100%;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: var(--app-surface);
}

.profile-header {
  padding: 12px 16px;
  border-bottom: 1px solid var(--aitext-split-border);
  flex-shrink: 0;
}

.profile-empty {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
}

.profile-content {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.profile-card {
  flex-shrink: 0;
}

.card-icon {
  font-size: 16px;
}

/* 角色速写 */
.sketch-card :deep(.n-card__content) {
  padding: 10px 14px;
}

.sketch-content {
  background: var(--app-page-bg, #fafafa);
  border-radius: 6px;
  padding: 10px 12px;
  border-left: 3px solid var(--n-color-target, #e0e0e0);
}

/* 四维心理画像 */
.dimension-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
}

.dimension-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 8px 10px;
  border-radius: 6px;
  background: var(--app-page-bg, #fafafa);
  border-left: 3px solid transparent;
}

.dimension-item.belief {
  border-left-color: #f0a020;
}

.dimension-item.taboo {
  border-left-color: #d03050;
}

.dimension-item.voice {
  border-left-color: #2080d0;
}

.dimension-item.wound {
  border-left-color: #8b5cf6;
}

.dimension-label {
  display: flex;
  align-items: center;
  gap: 4px;
}

.dim-icon {
  font-size: 12px;
}

.trauma-badge {
  margin-top: 8px;
  text-align: right;
}

/* 锚点 */
.anchor-field {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

/* 生成输出 */
.generated-output {
  background: var(--app-page-bg);
}

/* 验证列表 */
.validate-list {
  margin: 4px 0 0 0;
  padding-left: 20px;
  font-size: 12px;
  line-height: 1.6;
}

.validate-list li {
  margin-bottom: 4px;
}
</style>
