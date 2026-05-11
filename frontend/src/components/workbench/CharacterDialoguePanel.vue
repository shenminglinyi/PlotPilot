<template>
  <div class="character-dialogue-panel">
    <n-split direction="horizontal" :default-size="0.25" :min="0.20" :max="0.35">
      <!-- 左栏：角色导航 -->
      <template #1>
        <CharacterNavigator
          ref="navigatorRef"
          :slug="slug"
          :selected-character-id="selectedCharacterId"
          @select-character="onSelectCharacter"
        />
      </template>

      <!-- 中栏 + 右栏 -->
      <template #2>
        <n-split direction="horizontal" :default-size="0.70" :min="0.60" :max="0.80">
          <!-- 中栏：对话语料库 -->
          <template #1>
            <DialogueCorpus
              ref="corpusRef"
              :slug="slug"
              :selected-character-id="selectedCharacterId"
            />
          </template>

          <!-- 右栏：角色档案 -->
          <template #2>
            <CharacterProfile
              :slug="slug"
              :selected-character-id="selectedCharacterId"
              @refresh="onCharacterProfileRefresh"
            />
          </template>
        </n-split>
      </template>
    </n-split>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import type { ComponentPublicInstance } from 'vue'
import CharacterNavigator from './CharacterNavigator.vue'
import DialogueCorpus from './DialogueCorpus.vue'
import CharacterProfile from './CharacterProfile.vue'

interface Props {
  slug: string
}

defineProps<Props>()

type CorpusExpose = { load: () => Promise<void>; loadCharacterNames: () => Promise<void> }
type NavigatorExpose = { loadCharacters: () => Promise<void> }

const corpusRef = ref<ComponentPublicInstance & CorpusExpose | null>(null)
const navigatorRef = ref<ComponentPublicInstance & NavigatorExpose | null>(null)

const selectedCharacterId = ref<string | null>(null)

function onSelectCharacter(characterId: string | null) {
  selectedCharacterId.value = characterId
}

/** 锚点保存等：与语料库、左侧角色列表同源刷新 */
function onCharacterProfileRefresh() {
  void corpusRef.value?.load?.()
  void corpusRef.value?.loadCharacterNames?.()
  void navigatorRef.value?.loadCharacters?.()
}
</script>

<style scoped>
.character-dialogue-panel {
  height: 100%;
  min-height: 0;
  display: flex;
  overflow: hidden;
  background: var(--app-surface);
}

.character-dialogue-panel :deep(.n-split) {
  height: 100%;
}

.character-dialogue-panel :deep(.n-split-pane-1),
.character-dialogue-panel :deep(.n-split-pane-2) {
  min-height: 0;
  overflow: hidden;
}
</style>
