<template>
  <div class="character-dialogue-panel">
    <header class="anchor-desk-banner" role="region" aria-label="角色档案说明">
      <div class="anchor-desk-banner__head">
        <div class="anchor-desk-banner__title">
          <div class="anchor-icon-badge" aria-hidden="true">
            <n-icon size="14"><PeopleOutline /></n-icon>
          </div>
          <n-text strong>角色档案</n-text>
        </div>
        <n-space size="small" align="center" wrap>
          <n-tag v-if="currentChapterNumber" size="small" round :bordered="false" type="info">
            当前第 {{ currentChapterNumber }} 章
          </n-tag>
          <n-button size="tiny" secondary @click="openStoryEvolution">故事演进</n-button>
        </n-space>
      </div>
    </header>

    <n-split direction="horizontal" :default-size="0.20" :min="0.14" :max="0.32">
      <!-- 左栏：角色导航 -->
      <template #1>
        <CharacterNavigator
          :slug="slug"
          :selected-character-id="selectedCharacterId"
          @select-character="onSelectCharacter"
        />
      </template>

      <!-- 右栏：角色档案（4 tab，含对白和记忆） -->
      <template #2>
        <n-split direction="vertical" :default-size="0.36" :min="0.22" :max="0.52">
          <template #1>
            <ChapterCastManager
              :slug="slug"
              :chapter-number="currentChapterNumber"
            />
          </template>
          <template #2>
            <CharacterProfile
              :slug="slug"
              :selected-character-id="selectedCharacterId"
              :current-chapter-number="currentChapterNumber"
              :desk-chapter-number="currentChapterNumber"
            />
          </template>
        </n-split>
      </template>
    </n-split>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { PeopleOutline } from '@vicons/ionicons5'
import CharacterNavigator from './CharacterNavigator.vue'
import CharacterProfile from './CharacterProfile.vue'
import ChapterCastManager from './ChapterCastManager.vue'
import { WORKBENCH_OPEN_SETTINGS_PANEL_EVENT } from '@/workbench/deskEvents'

interface Props {
  slug: string
  currentChapterNumber?: number | null
}

withDefaults(defineProps<Props>(), {
  currentChapterNumber: null,
})

function openStoryEvolution() {
  window.dispatchEvent(
    new CustomEvent(WORKBENCH_OPEN_SETTINGS_PANEL_EVENT, { detail: { panel: 'story-evolution' } }),
  )
}

const selectedCharacterId = ref<string | null>(null)

function onSelectCharacter(characterId: string | null) {
  selectedCharacterId.value = characterId
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
  padding: 8px 12px;
  border-bottom: 1px solid var(--app-border, rgba(0, 0, 0, 0.08));
  background: var(--app-surface-elevated, var(--app-surface));
}

.anchor-desk-banner__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  flex-wrap: wrap;
}

.anchor-desk-banner__title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
  min-width: 0;
}

.anchor-icon-badge {
  width: 28px;
  height: 28px;
  border-radius: 8px;
  background: #3b82f6;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  flex-shrink: 0;
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

.character-dialogue-panel :deep(.n-split-pane-2 > .n-split) {
  height: 100%;
}
</style>
