<template>
  <div class="character-dialogue-panel">
    <header class="anchor-desk-banner" role="region" aria-label="角色锚点说明">
      <div class="anchor-desk-banner__title">
        <span class="anchor-desk-banner__icon" aria-hidden="true">⚓</span>
        <n-text strong>角色锚点</n-text>
      </div>
      <n-text depth="3" class="anchor-desk-banner__lead">
        选角后联动：心理状态、口癖与习惯动作、四维画像；中间列为正文自动抽取的对白语料，仅供声线校准参考。
      </n-text>
    </header>
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
          <!-- 中栏：对白语料（正文抽取，锚点声线对照） -->
          <template #1>
            <DialogueCorpus
              ref="corpusRef"
              :slug="slug"
              :selected-character-id="selectedCharacterId"
            />
          </template>

          <!-- 右栏：锚点与心理画像 -->
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
  flex-direction: column;
  overflow: hidden;
  background: var(--app-surface);
}

.anchor-desk-banner {
  flex-shrink: 0;
  padding: 10px 12px 12px;
  border-bottom: 1px solid var(--app-border, rgba(0, 0, 0, 0.08));
  background: var(--app-surface-elevated, var(--app-surface));
}

.anchor-desk-banner__title {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
  font-size: 14px;
}

.anchor-desk-banner__icon {
  font-size: 16px;
  line-height: 1;
}

.anchor-desk-banner__lead {
  display: block;
  font-size: 12px;
  line-height: 1.55;
  max-width: 72ch;
}

.character-dialogue-panel :deep(.n-split) {
  flex: 1;
  min-height: 0;
  height: auto;
}

.character-dialogue-panel :deep(.n-split-pane-1),
.character-dialogue-panel :deep(.n-split-pane-2) {
  min-height: 0;
  overflow: hidden;
}
</style>
