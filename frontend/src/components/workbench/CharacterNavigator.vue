<template>
  <div class="character-navigator">
    <div class="navigator-header">
      <n-text strong style="font-size: 14px">角色导航</n-text>
    </div>

    <n-spin :show="loading">
      <div v-if="characters.length > 0" class="character-list">
        <div
          v-for="char in characters"
          :key="char.id"
          class="character-item"
          :class="{ 'character-item--active': selectedCharacterId === char.id }"
          @click="selectCharacter(char.id)"
        >
          <div class="character-avatar">
            {{ getCharacterEmoji(char.role ?? '') }}
          </div>
          <div class="character-info">
            <div class="character-name">{{ char.name }}</div>
            <n-tag size="tiny" :type="getRoleType(char.role ?? '')" round>
              {{ getRoleLabel(char.role ?? '') }}
            </n-tag>
          </div>
        </div>
      </div>

      <n-empty
        v-else-if="!loading"
        description="暂无角色，请在「世界观」中添加角色"
        size="small"
        style="margin-top: 24px; padding: 0 12px"
      >
        <template #extra>
          <n-button size="small" @click="goToWorldbuilding">
            前往世界观
          </n-button>
        </template>
      </n-empty>
    </n-spin>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'
import { useMessage } from 'naive-ui'
import { bibleApi, type CharacterDTO } from '@/api/bible'
import { useWorkbenchDeskTickReload } from '@/composables/useWorkbenchNarrativeSync'
import { WORKBENCH_OPEN_SETTINGS_PANEL_EVENT } from '@/workbench/deskEvents'

interface Props {
  slug: string
  selectedCharacterId: string | null
}

const props = defineProps<Props>()
const emit = defineEmits<{
  'select-character': [characterId: string | null]
}>()

const message = useMessage()
const loading = ref(false)
const characters = ref<CharacterDTO[]>([])

function getCharacterEmoji(role: string): string {
  const map: Record<string, string> = {
    PROTAGONIST: '🧑',
    SUPPORTING: '👤',
    MINOR: '👥',
  }
  return map[role] || '👤'
}

function getRoleType(role: string): 'success' | 'warning' | 'default' {
  const map: Record<string, 'success' | 'warning' | 'default'> = {
    PROTAGONIST: 'success',
    SUPPORTING: 'warning',
    MINOR: 'default',
  }
  return map[role] || 'default'
}

function getRoleLabel(role: string): string {
  const map: Record<string, string> = {
    PROTAGONIST: '主角',
    SUPPORTING: '配角',
    MINOR: '龙套',
  }
  return map[role] || role
}

function selectCharacter(characterId: string | null) {
  emit('select-character', characterId)
}

function goToWorldbuilding() {
  window.dispatchEvent(
    new CustomEvent(WORKBENCH_OPEN_SETTINGS_PANEL_EVENT, { detail: { panel: 'worldbuilding' } }),
  )
}

async function loadCharacters() {
  if (!props.slug) return

  loading.value = true
  try {
    const bible = await bibleApi.getBible(props.slug)
    characters.value = bible.characters || []
  } catch (err: any) {
    message.error(err.message || '加载角色失败')
    characters.value = []
  } finally {
    loading.value = false
  }
}

watch(() => props.slug, () => void loadCharacters(), { immediate: true })

onMounted(() => {
  void loadCharacters()
})

useWorkbenchDeskTickReload(() => void loadCharacters())

defineExpose({ loadCharacters })
</script>

<style scoped>
.character-navigator {
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: var(--app-surface);
  border-right: 1px solid var(--plotpilot-split-border);
}

.navigator-header {
  padding: 12px 16px;
  border-bottom: 1px solid var(--plotpilot-split-border);
  flex-shrink: 0;
}

.character-list {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 12px;
}

.character-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px;
  border-radius: 6px;
  border: 1px solid var(--n-border-color);
  background: var(--app-surface);
  cursor: pointer;
  transition: all 0.2s;
  margin-bottom: 8px;
}

.character-item:hover {
  border-color: var(--n-primary-color-hover);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
}

.character-item--active {
  border-color: var(--n-primary-color);
  background: rgba(24, 144, 255, 0.04);
}

.character-avatar {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--app-page-bg);
  font-size: 18px;
  flex-shrink: 0;
}

.character-info {
  flex: 1;
  min-width: 0;
}

.character-name {
  font-size: 13px;
  font-weight: 500;
  margin-bottom: 4px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
</style>
