<template>
  <n-modal v-model:show="show" preset="card" title="💬 对话沙盒" style="width: 700px">
    <n-space vertical :size="16">
      <!-- 角色选择 -->
      <n-form-item label="选择角色">
        <n-select
          v-model:value="selectedCharacterId"
          :options="characterOptions"
          placeholder="选择要生成对话的角色"
          @update:value="loadCharacterAnchor"
          :loading="loadingCharacters"
        />
      </n-form-item>

      <!-- 角色锚点展示 -->
      <n-card v-if="characterAnchor" size="small" title="🎭 角色锚点" :bordered="true">
        <n-descriptions :column="1" size="small" bordered>
          <n-descriptions-item label="心理状态">
            <n-tag :type="getMentalStateColor(characterAnchor.mental_state)" size="small">
              {{ characterAnchor.mental_state }}
            </n-tag>
          </n-descriptions-item>
          <n-descriptions-item label="口头禅">
            <n-text code>「{{ characterAnchor.verbal_tic }}」</n-text>
          </n-descriptions-item>
          <n-descriptions-item label="待机动作">
            {{ characterAnchor.idle_behavior }}
          </n-descriptions-item>
        </n-descriptions>
      </n-card>

      <!-- 场景描述 -->
      <n-form-item label="场景描述">
        <n-input
          v-model:value="scenePrompt"
          type="textarea"
          placeholder="描述对话场景（例如：主角在废墟中遇到神秘老人，询问关于古代遗迹的信息）"
          :autosize="{ minRows: 3, maxRows: 6 }"
        />
      </n-form-item>

      <!-- 生成按钮 -->
      <n-button
        type="primary"
        :loading="generating"
        :disabled="!selectedCharacterId || !scenePrompt"
        @click="generateDialogue"
        block
      >
        <template #icon>
          <span>✨</span>
        </template>
        生成对话
      </n-button>

      <!-- 生成结果 -->
      <n-card v-if="generatedDialogue" title="生成结果" size="small" :bordered="true">
        <n-input
          v-model:value="generatedDialogue"
          type="textarea"
          :autosize="{ minRows: 6, maxRows: 12 }"
          placeholder="生成的对话将显示在这里..."
        />
        <template #action>
          <n-space justify="end">
            <n-button @click="regenerate" :loading="generating">
              <template #icon>
                <span>🔄</span>
              </template>
              重新生成
            </n-button>
            <n-button type="success" @click="copyToClipboard">
              <template #icon>
                <span>📋</span>
              </template>
              复制
            </n-button>
          </n-space>
        </template>
      </n-card>
    </n-space>
  </n-modal>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useMessage } from 'naive-ui'
import { sandboxApi, type CharacterAnchor } from '@/api/sandbox'
import { bibleApi, type CharacterDTO } from '@/api/bible'

const props = defineProps<{
  novelId: string
}>()

const show = defineModel<boolean>('show', { default: false })
const message = useMessage()

// 状态
const selectedCharacterId = ref<string | null>(null)
const characterAnchor = ref<CharacterAnchor | null>(null)
const scenePrompt = ref('')
const generating = ref(false)
const generatedDialogue = ref('')
const loadingCharacters = ref(false)
const characters = ref<CharacterDTO[]>([])

// 角色选项
const characterOptions = computed(() => {
  return characters.value.map(char => ({
    label: char.name || char.id,
    value: char.id
  }))
})

// 加载角色列表
async function loadCharacters() {
  if (!props.novelId) return

  loadingCharacters.value = true
  try {
    characters.value = await bibleApi.listCharacters(props.novelId)
  } catch (error) {
    console.error('Failed to load characters:', error)
    message.error('加载角色列表失败')
  } finally {
    loadingCharacters.value = false
  }
}

// 加载角色锚点
async function loadCharacterAnchor(charId: string) {
  if (!charId) {
    characterAnchor.value = null
    return
  }

  try {
    const anchor = await sandboxApi.getCharacterAnchor(props.novelId, charId)
    characterAnchor.value = anchor
  } catch (error) {
    console.error('Failed to load character anchor:', error)
    message.error('加载角色锚点失败')
  }
}

// 生成对话
async function generateDialogue() {
  if (!selectedCharacterId.value || !scenePrompt.value) {
    message.warning('请选择角色并输入场景描述')
    return
  }

  generating.value = true
  try {
    const result = await sandboxApi.generateDialogue({
      novel_id: props.novelId,
      character_id: selectedCharacterId.value,
      scene_prompt: scenePrompt.value,
      mental_state: characterAnchor.value?.mental_state,
      verbal_tic: characterAnchor.value?.verbal_tic,
      idle_behavior: characterAnchor.value?.idle_behavior,
    })

    generatedDialogue.value = result.dialogue
    message.success(`已生成 ${result.character_name} 的对话`)
  } catch (error) {
    console.error('Failed to generate dialogue:', error)
    message.error('生成对话失败')
  } finally {
    generating.value = false
  }
}

// 重新生成
async function regenerate() {
  await generateDialogue()
}

// 复制到剪贴板
async function copyToClipboard() {
  if (!generatedDialogue.value) return

  try {
    await navigator.clipboard.writeText(generatedDialogue.value)
    message.success('已复制到剪贴板')
  } catch (error) {
    console.error('Failed to copy:', error)
    message.error('复制失败')
  }
}

// 获取心理状态颜色
function getMentalStateColor(state: string): 'success' | 'warning' | 'error' | 'info' {
  const lowerState = state.toLowerCase()
  if (lowerState.includes('平静') || lowerState.includes('冷静')) return 'success'
  if (lowerState.includes('焦虑') || lowerState.includes('紧张')) return 'warning'
  if (lowerState.includes('愤怒') || lowerState.includes('恐惧')) return 'error'
  return 'info'
}

// 监听 modal 打开，加载角色列表
watch(show, (newShow) => {
  if (newShow && characters.value.length === 0) {
    loadCharacters()
  }
})
</script>

<style scoped>
:deep(.n-card__action) {
  padding: 12px 16px;
}
</style>
