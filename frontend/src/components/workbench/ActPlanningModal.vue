<template>
  <n-modal
    v-model:show="show"
    preset="card"
    :class="['act-plan-modal', uiPhase === 'stream' && 'act-plan-modal--stream']"
    style="width: min(720px, 96vw)"
    :mask-closable="uiPhase !== 'stream'"
    :closable="uiPhase !== 'stream'"
    :segmented="{ content: true, footer: 'soft' }"
    :title="modalHeadline"
  >
    <template #header-extra>
      <n-text v-if="uiPhase === 'form'" depth="3" style="font-size: 12px">
        AI 为本幕生成章节大纲，确认后写入结构树
      </n-text>
      <span v-else-if="uiPhase === 'stream'" class="apm-subtitle apm-subtitle--live">
        <span class="live-dot" />{{ statusMessage }}
      </span>
      <n-text v-else-if="uiPhase === 'edit'" depth="3" style="font-size: 12px">
        已生成 {{ chapters.length }} 章规划，可编辑后确认
      </n-text>
    </template>

    <!-- 配置 -->
    <n-space v-if="uiPhase === 'form'" vertical :size="16">
      <n-alert type="info" :show-icon="true">
        AI 将根据本幕的叙事目标与 Bible 信息，自动为每章生成标题和大纲。生成时可看到流式骨架与占位。
      </n-alert>

      <n-form-item label="本幕章节数" :show-feedback="false">
        <n-input-number
          v-model:value="chapterCount"
          :min="2"
          :max="20"
          style="width: 120px"
        />
        <n-text depth="3" style="margin-left: 8px; font-size: 12px">（不填则由引擎/幕节点推荐）</n-text>
      </n-form-item>

      <n-space justify="end" :size="10">
        <n-button @click="close">取消</n-button>
        <n-button type="primary" @click="startStream">AI 生成章节规划</n-button>
      </n-space>
    </n-space>

    <!-- 流式生成 -->
    <n-space v-else-if="uiPhase === 'stream'" vertical :size="14">
      <div class="prog-track">
        <div class="prog-fill" :style="{ width: `${progressPct}%` }" />
      </div>

      <div
        v-if="llmStreamPreview"
        ref="llmStreamOuterRef"
        class="apm-llm-preview"
      >
        <div class="apm-llm-label">模型输出</div>
        <pre class="apm-llm-pre">{{ llmStreamPreview }}</pre>
      </div>

      <n-scrollbar style="max-height: 52vh">
        <n-space vertical :size="8" style="padding-right: 8px">
          <n-card
            v-for="(ch, idx) in streamPreview"
            :key="'live-' + idx"
            size="small"
            :bordered="true"
            style="background: var(--n-color)"
          >
            <n-space vertical :size="6">
              <n-text strong>{{ ch.title || `第 ${idx + 1} 章` }}</n-text>
              <n-text depth="3" style="font-size: 13px; white-space: pre-wrap">
                {{ ch.outline || '（无大纲）' }}
              </n-text>
              <n-space v-if="ch.bible_elements?.length" :size="6">
                <n-tag v-for="el in ch.bible_elements" :key="el" size="small" round>{{ el }}</n-tag>
              </n-space>
            </n-space>
          </n-card>

          <n-card
            v-for="s in skeletonCount"
            :key="'sk-' + s"
            size="small"
            :bordered="true"
            class="skel-card"
          >
            <n-space vertical :size="10">
              <n-skeleton text :width="`${55 + ((s * 7) % 25)}%`" />
              <n-skeleton text :round="false" :rows="2" />
            </n-space>
          </n-card>
        </n-space>
      </n-scrollbar>

      <n-space justify="end">
        <n-button quaternary @click="abortStream">取消生成</n-button>
      </n-space>
    </n-space>

    <!-- 编辑确认 -->
    <n-space v-else-if="uiPhase === 'edit'" vertical :size="16">
      <n-alert type="success" :show-icon="true">
        已生成 {{ chapters.length }} 章规划，可在下方直接修改标题或大纲后确认。
      </n-alert>

      <n-scrollbar style="max-height: 52vh">
        <n-space vertical :size="8" style="padding-right: 8px">
          <n-card
            v-for="(ch, idx) in chapters"
            :key="idx"
            size="small"
            :bordered="true"
            style="background: var(--n-color)"
          >
            <n-space vertical :size="6">
              <n-input
                v-model:value="ch.title"
                placeholder="章节标题"
                :disabled="confirming"
                size="small"
              />
              <n-input
                v-model:value="ch.outline"
                type="textarea"
                placeholder="本章大纲"
                :autosize="{ minRows: 2, maxRows: 5 }"
                :disabled="confirming"
                size="small"
              />
              <n-space :size="6">
                <n-tag v-for="el in ch.bible_elements" :key="el" size="small" round>{{ el }}</n-tag>
              </n-space>
            </n-space>
          </n-card>
        </n-space>
      </n-scrollbar>

      <n-space justify="end" :size="10">
        <n-button :disabled="confirming" @click="backToForm">重新生成</n-button>
        <n-button :disabled="confirming" @click="close">取消</n-button>
        <n-button type="primary" :loading="confirming" @click="confirm">确认并保存到结构树</n-button>
      </n-space>
    </n-space>

    <!-- 错误 -->
    <n-space v-else vertical :size="16">
      <n-alert type="error" :show-icon="true" :title="streamError || '生成失败'" />
      <n-space justify="end">
        <n-button @click="close">关闭</n-button>
        <n-button type="primary" @click="backToForm">返回</n-button>
      </n-space>
    </n-space>
  </n-modal>
</template>

<script setup lang="ts">
import { ref, computed, watch, onUnmounted, nextTick } from 'vue'
import { useMessage } from 'naive-ui'
import { streamActChapterPlan, planningApi } from '../../api/planning'

interface ChapterDraft {
  title: string
  outline: string
  bible_elements: string[]
  [key: string]: unknown
}

const props = defineProps<{
  show: boolean
  actId: string
  actTitle: string
}>()

const emit = defineEmits<{
  (e: 'update:show', v: boolean): void
  (e: 'confirmed'): void
}>()

const message = useMessage()

const show = computed({
  get: () => props.show,
  set: (v) => emit('update:show', v),
})

type UiPhase = 'form' | 'stream' | 'edit' | 'error'
const uiPhase = ref<UiPhase>('form')

const confirming = ref(false)
const chapterCount = ref<number | null>(null)
const chapters = ref<ChapterDraft[]>([])

const statusMessage = ref('正在连接…')
const progressPct = ref(0)
const expectedChapters = ref(0)
const streamPreview = ref<ChapterDraft[]>([])
const streamError = ref('')
const llmStreamPreview = ref('')
const llmStreamOuterRef = ref<HTMLElement | null>(null)

let abortCtrl: AbortController | null = null

const modalHeadline = computed(() => `规划章节 — ${props.actTitle}`)

const skeletonCount = computed(() => {
  if (uiPhase.value !== 'stream') return 0
  const exp = expectedChapters.value || 0
  const got = streamPreview.value.length
  if (!exp) return Math.min(6, Math.max(2, got + 2))
  return Math.min(20, Math.max(0, exp - got))
})

function mapRawToDraft(c: Record<string, unknown>): ChapterDraft {
  const base = { ...c } as ChapterDraft
  return {
    ...base,
    title: String(c.title ?? base.title ?? ''),
    outline: String(c.outline ?? c.description ?? base.outline ?? ''),
    bible_elements: Array.isArray(c.bible_elements)
      ? (c.bible_elements as string[])
      : (base.bible_elements ?? []),
  }
}

function startStream() {
  abortCtrl?.abort()
  streamPreview.value = []
  llmStreamPreview.value = ''
  statusMessage.value = '正在连接…'
  progressPct.value = 2
  streamError.value = ''
  expectedChapters.value = 0
  uiPhase.value = 'stream'

  abortCtrl = streamActChapterPlan(
    props.actId,
    {
      onStatus(e) {
        statusMessage.value = e.message
        if (typeof e.percent === 'number') progressPct.value = e.percent
        if (typeof e.expected_chapters === 'number' && e.expected_chapters > 0) {
          expectedChapters.value = e.expected_chapters
        }
        if (e.phase === 'streaming') {
          progressPct.value = Math.max(progressPct.value, 90)
          llmStreamPreview.value = ''
        }
      },
      onChunk({ text }) {
        llmStreamPreview.value += text
        nextTick(() => {
          const outer = llmStreamOuterRef.value
          const pre = outer?.querySelector('.apm-llm-pre')
          if (pre) (pre as HTMLElement).scrollTop = pre.scrollHeight
        })
      },
      onChapter(e) {
        streamPreview.value.push(mapRawToDraft(e as Record<string, unknown>))
        nextTick(() => {
          /* 滚动由 n-scrollbar 内部处理；如需可在此 scrollIntoView */
        })
      },
      onDone(e) {
        const raw = e.chapters ?? []
        chapters.value = raw.map((c) => mapRawToDraft(c as Record<string, unknown>))
        if (!chapters.value.length) {
          streamError.value = 'AI 未返回章节数据'
          uiPhase.value = 'error'
          abortCtrl = null
          return
        }
        progressPct.value = 100
        streamPreview.value = []
        uiPhase.value = 'edit'
        abortCtrl = null
      },
      onError(msg) {
        streamError.value = msg
        uiPhase.value = 'error'
        abortCtrl = null
      },
    },
    { chapterCount: chapterCount.value },
  )
}

function abortStream() {
  abortCtrl?.abort()
  abortCtrl = null
  uiPhase.value = 'form'
  streamPreview.value = []
  llmStreamPreview.value = ''
}

function backToForm() {
  abortCtrl?.abort()
  abortCtrl = null
  uiPhase.value = 'form'
  chapters.value = []
  streamPreview.value = []
  llmStreamPreview.value = ''
  streamError.value = ''
}

function close() {
  emit('update:show', false)
}

function reset() {
  abortCtrl?.abort()
  abortCtrl = null
  uiPhase.value = 'form'
  chapters.value = []
  streamPreview.value = []
  llmStreamPreview.value = ''
  confirming.value = false
  chapterCount.value = null
  statusMessage.value = ''
  progressPct.value = 0
  expectedChapters.value = 0
  streamError.value = ''
}

watch(
  () => props.show,
  (v) => {
    if (!v) reset()
  },
)

onUnmounted(() => {
  abortCtrl?.abort()
})

async function confirm() {
  confirming.value = true
  try {
    await planningApi.confirmActChapters(props.actId, { chapters: chapters.value })
    message.success('章节已写入结构树')
    emit('confirmed')
    emit('update:show', false)
  } catch (e: unknown) {
    const err = e as { response?: { data?: { detail?: string } } }
    message.error(err?.response?.data?.detail || '保存失败')
  } finally {
    confirming.value = false
  }
}
</script>

<style scoped>
:global(.act-plan-modal--stream) {
  width: min(760px, 96vw) !important;
}

.apm-subtitle {
  font-size: 12px;
  color: var(--n-text-color-3);
}
.apm-subtitle--live {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: var(--n-primary-color);
}
.live-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--n-primary-color);
  animation: apm-pulse 1.2s ease-in-out infinite;
}
@keyframes apm-pulse {
  0%,
  100% {
    opacity: 1;
  }
  50% {
    opacity: 0.35;
  }
}

.prog-track {
  height: 4px;
  border-radius: 4px;
  background: var(--n-border-color);
  overflow: hidden;
}
.prog-fill {
  height: 100%;
  border-radius: 4px;
  background: linear-gradient(90deg, var(--n-primary-color), var(--n-primary-color-hover));
  transition: width 0.35s ease;
}

.apm-llm-preview {
  margin-bottom: 10px;
  border-radius: 8px;
  border: 1px solid var(--n-border-color);
  background: var(--n-color-modal);
  overflow: hidden;
}
.apm-llm-label {
  padding: 6px 10px;
  font-size: 11px;
  font-weight: 600;
  color: var(--n-text-color-3);
  border-bottom: 1px solid var(--n-border-color);
}
.apm-llm-pre {
  margin: 0;
  padding: 10px 12px;
  max-height: 160px;
  overflow: auto;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-size: 11px;
  line-height: 1.45;
  color: var(--n-text-color);
  white-space: pre-wrap;
  word-break: break-word;
}

.skel-card {
  opacity: 0.85;
}
</style>
