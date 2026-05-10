<template>
  <div class="dialogue-corpus">
    <div class="corpus-header">
      <n-text strong style="font-size: 14px">对话语料库</n-text>
      <n-button size="small" :loading="loading" @click="load">刷新</n-button>
    </div>

    <!-- 筛选栏 -->
    <div class="corpus-filters">
      <n-select
        v-model:value="filterChapter"
        :options="chapterOptions"
        placeholder="章节"
        clearable
        style="width: 90px"
        size="small"
      />
      <n-select
        v-model:value="filterSpeaker"
        :options="speakerOptions"
        placeholder="说话人"
        clearable
        filterable
        style="width: 100px"
        size="small"
      />
      <n-input
        v-model:value="searchText"
        placeholder="搜索..."
        clearable
        size="small"
        style="flex: 1; min-width: 80px"
      />
    </div>

    <n-spin :show="loading">
      <div class="corpus-content">
        <n-empty
          v-if="!result"
          description="加载中..."
          size="small"
        />
        <n-empty
          v-else-if="result.total_count === 0"
          description="暂无对话数据，生成章节后自动提取"
          size="small"
        />
        <n-empty
          v-else-if="filteredDialogues.length === 0"
          description="无匹配对话"
          size="small"
        />
        <div v-else class="dialogue-list">
          <div
            v-for="d in filteredDialogues"
            :key="d.dialogue_id"
            class="dialogue-item"
            :class="{
              'dialogue-item--highlight': isCharacterDialogue(d.speaker)
            }"
          >
            <div class="dialogue-meta">
              <n-tag size="tiny" round>第{{ d.chapter }}章</n-tag>
              <n-tag type="success" size="tiny" round>{{ d.speaker }}</n-tag>
            </div>
            <n-text class="dialogue-content">{{ d.content }}</n-text>
          </div>
        </div>
      </div>

      <!-- 底部统计 -->
      <div v-if="result && result.total_count > 0" class="corpus-footer">
        <n-text depth="3" style="font-size: 11px">
          {{ filteredDialogues.length }} / {{ result.total_count }} 条对话
        </n-text>
      </div>
    </n-spin>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { useMessage } from 'naive-ui'
import { sandboxApi, type DialogueWhitelistResponse, type DialogueEntry } from '@/api/sandbox'
import { bibleApi } from '@/api/bible'

interface Props {
  slug: string
  selectedCharacterId: string | null
}

const props = defineProps<Props>()
const message = useMessage()

const loading = ref(false)
const result = ref<DialogueWhitelistResponse | null>(null)
const filterChapter = ref<number | null>(null)
const filterSpeaker = ref('')
const searchText = ref('')

const characterNames = ref<Set<string>>(new Set())

// 章节选项（从已有对话中提取）
const chapterOptions = computed(() => {
  if (!result.value) return []
  const chapters = new Set<number>()
  result.value.dialogues.forEach(d => chapters.add(d.chapter))
  return Array.from(chapters)
    .sort((a, b) => a - b)
    .map(ch => ({ label: `第${ch}章`, value: ch }))
})

// 说话人选项（从已有对话中提取）
const speakerOptions = computed(() => {
  if (!result.value) return []
  const speakers = new Set<string>()
  result.value.dialogues.forEach(d => speakers.add(d.speaker))
  return Array.from(speakers)
    .sort()
    .map(s => ({ label: s, value: s }))
})

// 过滤后的对话
const filteredDialogues = computed<DialogueEntry[]>(() => {
  if (!result.value) return []
  let list = result.value.dialogues

  // 章节筛选
  if (filterChapter.value !== null) {
    list = list.filter(d => d.chapter === filterChapter.value)
  }

  // 说话人筛选
  if (filterSpeaker.value) {
    list = list.filter(d => d.speaker === filterSpeaker.value)
  }

  // 关键词搜索
  if (searchText.value) {
    list = list.filter(d => d.content.includes(searchText.value))
  }

  return list
})

// 判断对话是否属于选中角色
function isCharacterDialogue(speaker: string): boolean {
  if (!props.selectedCharacterId) return false
  return characterNames.value.has(speaker)
}

async function loadCharacterNames() {
  if (!props.slug) return

  try {
    const bible = await bibleApi.get(props.slug)
    characterNames.value = new Set(bible.characters?.map(c => c.name) || [])
  } catch {
    characterNames.value = new Set()
  }
}

async function load() {
  if (!props.slug) return

  loading.value = true
  try {
    const res = await sandboxApi.getDialogueWhitelist(props.slug)
    result.value = res
  } catch (err: any) {
    message.error(err.message || '加载对话白名单失败')
    result.value = null
  } finally {
    loading.value = false
  }
}

watch(() => props.slug, () => {
  void loadCharacterNames()
  void load()
}, { immediate: true })

onMounted(() => {
  void loadCharacterNames()
  void load()
})
</script>

<style scoped>
.dialogue-corpus {
  height: 100%;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: var(--app-surface);
  border-right: 1px solid var(--aitext-split-border);
}

.corpus-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  border-bottom: 1px solid var(--aitext-split-border);
  flex-shrink: 0;
}

.corpus-filters {
  display: flex;
  gap: 8px;
  padding: 8px 16px;
  border-bottom: 1px solid var(--aitext-split-border);
  flex-shrink: 0;
}

.corpus-content {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 16px;
}

.dialogue-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.dialogue-item {
  padding: 8px;
  border-radius: 4px;
  background: var(--app-page-bg);
  border: 1px solid transparent;
  transition: all 0.2s;
}

.dialogue-item--highlight {
  border-color: var(--n-primary-color);
  background: rgba(24, 144, 255, 0.04);
}

.dialogue-meta {
  display: flex;
  gap: 6px;
  margin-bottom: 6px;
}

.dialogue-content {
  font-size: 13px;
  line-height: 1.6;
  display: block;
}

.corpus-footer {
  padding: 8px 16px;
  border-top: 1px solid var(--aitext-split-border);
  text-align: center;
  flex-shrink: 0;
}
</style>
