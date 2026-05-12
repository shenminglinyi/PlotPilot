<template>
  <div class="character-dialogue-panel">
    <header class="anchor-desk-banner" role="region" aria-label="角色锚点说明">
      <div class="anchor-desk-banner__head">
        <div class="anchor-desk-banner__title">
          <span class="anchor-desk-banner__icon" aria-hidden="true">⚓</span>
          <n-text strong>角色锚点</n-text>
        </div>
        <n-space size="small" align="center" wrap>
          <n-tag v-if="currentChapterNumber" size="small" round :bordered="false" type="info">
            当前第 {{ currentChapterNumber }} 章
          </n-tag>
          <n-button size="tiny" secondary @click="openStoryEvolution">故事演进</n-button>
        </n-space>
      </div>
      <n-text depth="3" class="anchor-desk-banner__lead">
        与左侧章节列表同步：有当前章时对白语料默认筛到本章；右栏含「章内生成会带上的字段」预览。选角后联动心理状态、口癖与习惯动作、四维画像；语料来自正文抽取，仅供声线校准参考。
      </n-text>
    </header>
    <n-split direction="horizontal" :default-size="0.24" :min="0.17" :max="0.34">
      <!-- 左栏：角色导航 -->
      <template #1>
        <CharacterNavigator
          :slug="slug"
          :selected-character-id="selectedCharacterId"
          @select-character="onSelectCharacter"
        />
      </template>

      <!-- 中栏 + 右栏 -->
      <template #2>
        <n-split direction="horizontal" :default-size="0.55" :min="0.40" :max="0.68">
          <!-- 中栏：对白语料（正文抽取，锚点声线对照） -->
          <template #1>
            <DialogueCorpus
              :slug="slug"
              :selected-character-id="selectedCharacterId"
              :desk-chapter-number="currentChapterNumber"
            />
          </template>

          <!-- 右栏：锚点与心理画像 -->
          <template #2>
            <CharacterProfile
              :slug="slug"
              :selected-character-id="selectedCharacterId"
              :current-chapter-number="currentChapterNumber"
            />
          </template>
        </n-split>
      </template>
    </n-split>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import CharacterNavigator from './CharacterNavigator.vue'
import DialogueCorpus from './DialogueCorpus.vue'
import CharacterProfile from './CharacterProfile.vue'
import { WORKBENCH_OPEN_SETTINGS_PANEL_EVENT } from '@/workbench/deskEvents'

interface Props {
  slug: string
  /** 工作台当前章节号；用于语料默认筛到本章、顶栏提示 */
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
  padding: 10px 12px 12px;
  border-bottom: 1px solid var(--app-border, rgba(0, 0, 0, 0.08));
  background: var(--app-surface-elevated, var(--app-surface));
}

.anchor-desk-banner__head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px;
  flex-wrap: wrap;
  margin-bottom: 6px;
}

.anchor-desk-banner__title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
  min-width: 0;
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
