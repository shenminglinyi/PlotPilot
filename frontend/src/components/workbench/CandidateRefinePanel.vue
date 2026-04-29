<template>
  <div class="candidate-refine-panel">
    <n-space vertical :size="12">
      <n-card size="small" class="section-card">
        <template #header>
          <div class="card-title">
            <span>候选稿闭环</span>
            <n-tag size="tiny" type="success" round>P1</n-tag>
          </div>
        </template>
        <p class="intro-text">
          候选稿和精修都绑定当前章节，不在右侧另写一份正文。这里负责创建任务，真正的 A/B、采纳、部分采纳和记忆更新仍回到中间写作区完成。
        </p>
        <n-alert v-if="!currentChapter" type="warning" :show-icon="true" class="section-alert">
          先从左侧目录点开具体章节，右侧才会把精修任务送进该章节的候选稿区。
        </n-alert>
        <n-alert v-else type="info" :show-icon="true" class="section-alert">
          当前绑定：第 {{ currentChapter.number }} 章《{{ currentChapter.title || '未命名章节' }}》。
          发送后会自动打开中间写作区的候选稿弹窗。
        </n-alert>
      </n-card>

      <n-card size="small" class="section-card">
        <template #header>
          <div class="card-title">
            <span>精修任务</span>
            <n-tag size="tiny" type="info" round>P3</n-tag>
          </div>
        </template>
        <n-space vertical :size="10">
          <label class="field-label">改稿目标</label>
          <n-select v-model:value="objective" :options="objectiveOptions" :disabled="!currentChapter" />

          <label class="field-label">重点片段</label>
          <n-input
            v-model:value="targetExcerpt"
            type="textarea"
            placeholder="可留空。填写后 PP AI 会优先针对这段做精修。"
            :autosize="{ minRows: 3, maxRows: 7 }"
            :disabled="!currentChapter"
          />

          <label class="field-label">作者要求</label>
          <n-input
            v-model:value="instruction"
            type="textarea"
            placeholder="例如：保留事件，只把对白写得更克制；不要新增设定。"
            :autosize="{ minRows: 3, maxRows: 7 }"
            :disabled="!currentChapter"
          />

          <div class="action-row">
            <n-button
              size="small"
              secondary
              :loading="suggesting"
              :disabled="!currentChapter"
              @click="suggestRewriteTask"
            >
              AI 生成建议
            </n-button>
            <n-button
              size="small"
              type="primary"
              :disabled="!currentChapter"
              @click="sendToCandidateArea"
            >
              发送到候选稿区
            </n-button>
          </div>
        </n-space>
      </n-card>

      <n-card size="small" class="section-card">
        <template #header>在哪里看结果</template>
        <ol class="help-list">
          <li>左侧选择章节后，点“发送到候选稿区”。</li>
          <li>中间写作区会打开“候选稿”弹窗，并创建一条精修任务。</li>
          <li>在候选稿弹窗里继续用 PP AI 生成正文、A/B 对照、部分采纳或最终采纳。</li>
        </ol>
      </n-card>
    </n-space>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useMessage } from 'naive-ui'
import { useWorkbenchContextStore } from '@/stores/workbenchContextStore'
import { novelproSuggestionsApi } from '@/api/novelproSuggestions'
import {
  CHAPTER_PRECISION_REWRITE_OBJECTIVES,
  defaultPrecisionRewriteObjective,
} from '@/utils/chapterPrecisionRewrite'
import {
  PRECISION_REWRITE_SOURCE,
  buildPrecisionRewriteRationale,
} from '@/utils/precisionRewriteTask'

interface Chapter {
  id: number
  number: number
  title: string
  word_count: number
}

const props = defineProps<{
  slug: string
  currentChapter?: Chapter | null
}>()

const message = useMessage()
const contextStore = useWorkbenchContextStore()
const objective = ref(defaultPrecisionRewriteObjective())
const targetExcerpt = ref('')
const instruction = ref('')
const suggesting = ref(false)

const objectiveOptions = computed(() =>
  CHAPTER_PRECISION_REWRITE_OBJECTIVES.map(item => ({
    label: item,
    value: item,
  })),
)

function suggestionText(fields: Record<string, unknown>, key: string) {
  const value = fields[key]
  if (value == null) return ''
  return String(value)
}

async function suggestRewriteTask() {
  if (!props.currentChapter) {
    message.warning('先选择章节再生成精修建议')
    return
  }
  suggesting.value = true
  try {
    const result = await novelproSuggestionsApi.suggestFields(props.slug, {
      suggestion_type: 'precision_rewrite',
      chapter_number: props.currentChapter.number,
      fields: ['objective', 'target_excerpt', 'instruction'],
      target: {
        chapter_title: props.currentChapter.title,
        word_count: props.currentChapter.word_count,
      },
      current_values: {
        objective: objective.value,
        target_excerpt: targetExcerpt.value,
        instruction: instruction.value,
      },
      instruction: '根据当前章节、Obsidian 长期记忆、作品设定和连续性风险，生成一个可执行的精修任务。必须保留主线事实，不要直接改主稿。',
    })
    objective.value = suggestionText(result.fields, 'objective') || objective.value
    targetExcerpt.value = suggestionText(result.fields, 'target_excerpt') || targetExcerpt.value
    instruction.value = suggestionText(result.fields, 'instruction') || instruction.value
    message.success(result.rationale || '已生成精修建议')
  } catch {
    message.error('生成精修建议失败，请检查 PP AI 配置')
  } finally {
    suggesting.value = false
  }
}

function sendToCandidateArea() {
  const chapter = props.currentChapter
  if (!chapter) {
    message.warning('先选择章节再创建候选稿任务')
    return
  }

  contextStore.openCandidateRewriteSeed({
    slug: props.slug,
    chapterNumber: chapter.number,
    source: PRECISION_REWRITE_SOURCE,
    title: `${chapter.title || `第${chapter.number}章`} 精修任务`,
    rationale: buildPrecisionRewriteRationale({
      objective: objective.value,
      instruction: instruction.value,
      targetExcerpt: targetExcerpt.value,
    }),
    metadata: {
      rewrite_focus: 'precision-rewrite',
      precision_objective: objective.value,
      target_excerpt: targetExcerpt.value,
      instruction: instruction.value,
      triggered_by: 'candidate-refine-panel',
    },
  })
  message.success('已发送到中间写作区的候选稿闭环')
}
</script>

<style scoped>
.candidate-refine-panel {
  height: 100%;
  overflow-y: auto;
  padding: 12px;
}

.section-card {
  border-radius: 14px;
}

.card-title,
.action-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.action-row {
  justify-content: flex-end;
  flex-wrap: wrap;
}

.intro-text {
  margin: 0 0 10px;
  color: var(--app-text-secondary);
  font-size: 13px;
  line-height: 1.7;
}

.section-alert {
  margin-top: 8px;
}

.field-label {
  color: var(--app-text-secondary);
  font-size: 12px;
  font-weight: 600;
}

.help-list {
  margin: 0;
  padding-left: 18px;
  color: var(--app-text-secondary);
  font-size: 13px;
  line-height: 1.8;
}
</style>
