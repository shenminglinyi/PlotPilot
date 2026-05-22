<template>
  <div class="cc-panel">
    <n-empty v-if="!currentChapterNumber" description="请先从左侧选择一个章节" style="margin-top: 40px" />

    <n-scrollbar v-else class="cc-scroll">
      <n-space vertical :size="12" style="padding: 8px 4px 16px">
        <n-alert v-if="readOnly" type="warning" :show-icon="true" size="small">
          托管运行中：仅可查看
        </n-alert>

        <!-- 本章规划 -->
        <n-card v-if="chapterPlan" size="small" :bordered="true" class="cc-card-plan">
          <template #header>
            <span class="card-title">📋 本章规划</span>
          </template>
          <n-descriptions :column="1" label-placement="left" size="small" label-style="white-space: nowrap">
            <n-descriptions-item label="标题">{{ chapterPlan.title || '—' }}</n-descriptions-item>
            <n-descriptions-item v-if="chapterPlan.outline" label="大纲">
              <n-text style="font-size: 12px; white-space: pre-wrap">{{ chapterPlan.outline }}</n-text>
            </n-descriptions-item>
            <n-descriptions-item v-if="chapterPlan.pov_character_id" label="视角">
              {{ getCharacterName(chapterPlan.pov_character_id) }}
            </n-descriptions-item>
            <n-descriptions-item v-if="chapterPlan.timeline_start || chapterPlan.timeline_end" label="时间线">
              {{ chapterPlan.timeline_start || '—' }} → {{ chapterPlan.timeline_end || '—' }}
            </n-descriptions-item>
            <n-descriptions-item v-if="planMoodLine" label="基调">
              {{ planMoodLine }}
            </n-descriptions-item>
          </n-descriptions>
        </n-card>

        <!-- 节拍规划 -->
        <n-card v-if="showBeatsCard" size="small" :bordered="true">
          <template #header>
            <span class="card-title">🎬 节拍规划</span>
          </template>
          <n-tabs v-model:value="activeBeatsTab" type="segment" size="small" animated>
            <n-tab-pane name="macro" tab="宏观">
              <n-text depth="3" style="font-size: 11px; display: block; margin-bottom: 8px">
                章节大纲 — 作者意图总览
              </n-text>
              <div v-if="chapterPlan?.outline?.trim()" class="macro-outline-text">
                {{ chapterPlan.outline }}
              </div>
              <n-empty v-else description="暂无大纲数据" size="small" />
              <template v-if="narrativeBeatSections.length">
                <n-divider style="margin: 12px 0" />
                <n-text depth="3" style="font-size: 11px; display: block; margin-bottom: 8px">
                  知识库<strong>叙事节拍条</strong>（章后同步 · beat_sections）— 按句切分的大纲要点，<strong>不是</strong>写作指挥器微观节拍。
                </n-text>
                <n-space vertical :size="6">
                  <div
                    v-for="(line, i) in narrativeBeatSections"
                    :key="`narr-${i}`"
                    class="narrative-beat-line"
                  >
                    <n-text depth="3" style="font-size: 11px; flex-shrink: 0">{{ i + 1 }}.</n-text>
                    <n-text style="font-size: 12px">{{ line }}</n-text>
                  </div>
                </n-space>
              </template>
            </n-tab-pane>
            
            <n-tab-pane name="micro" tab="微观">
              <n-text depth="3" style="font-size: 11px; display: block; margin-bottom: 8px">
                <template v-if="microHintIsOutlineFallback">
                  章前规划<strong>失败或降级</strong>时的章纲拆条预览（按段落/句读），仅供参考，非指挥器节拍。
                </template>
                <template v-else-if="microHintFromKnowledgeDb">
                  以下为知识库已落库的<strong>指挥器微观节拍</strong>（chapter_summaries.micro_beats）。
                </template>
                <template v-else>
                  仅展示写作指挥器真实 Beat（流式/全托管拆拍）。叙事节拍条见「宏观」页。
                </template>
              </n-text>
              <n-space v-if="microBeats.length" vertical :size="8" style="margin-top: 12px">
                <div v-for="(beat, i) in microBeats" :key="i" class="micro-beat-item">
                  <div class="micro-beat-header">
                    <n-tag :type="getBeatTypeColor(beat.focus)" size="small" round>
                      {{ beatFocusLabel(beat.focus) }}
                    </n-tag>
                    <n-text strong style="margin-left: 8px">节拍 {{ i + 1 }}</n-text>
                    <n-text
                      v-if="beat.target_words > 0"
                      depth="3"
                      style="margin-left: 8px; font-size: 12px"
                    >
                      （约 {{ beat.target_words }} 字）
                    </n-text>
                  </div>
                  <div class="micro-beat-desc">{{ formatBeatDescription(beat.description) }}</div>
                  <div v-if="beat.active_action || beat.emotion_gap || beat.forbidden_drift" class="mbc">
                    <div v-if="beat.active_action" class="mbc-row">
                      <span class="mbc-tag">行为</span><span class="mbc-val">{{ beat.active_action }}</span>
                    </div>
                    <div v-if="beat.emotion_gap" class="mbc-row">
                      <span class="mbc-tag">缺口</span><span class="mbc-val">{{ beat.emotion_gap }}</span>
                    </div>
                    <div v-if="beat.forbidden_drift" class="mbc-row">
                      <span class="mbc-tag mbc-tag--warn">禁止</span><span class="mbc-val mbc-val--muted">{{ beat.forbidden_drift }}</span>
                    </div>
                  </div>
                </div>
              </n-space>
              <n-empty
                v-else
                :description="microEmptyDescription"
                size="small"
              />
            </n-tab-pane>
          </n-tabs>
        </n-card>

        <n-alert v-if="storyNodeNotFound" type="warning" :show-icon="true">
          未在结构树中找到第 {{ currentChapterNumber }} 章的规划节点
        </n-alert>

      </n-space>
    </n-scrollbar>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, onMounted, onUnmounted, computed } from 'vue'
import { storeToRefs } from 'pinia'
import { useWorkbenchRefreshStore } from '../../stores/workbenchRefreshStore'
import { planningApi } from '../../api/planning'
import type { StoryNode } from '../../api/planning'
import { knowledgeApi } from '../../api/knowledge'
import type { ChapterSummary } from '../../api/knowledge'
import { bibleApi, type CharacterDTO } from '../../api/bible'
import type { StreamGeneratedBeat } from '../../api/workflow'
import type { AutopilotChapterAudit } from './ChapterStatusPanel.vue'

const props = withDefaults(
  defineProps<{
    slug: string
    currentChapterNumber?: number | null
    readOnly?: boolean
    autopilotChapterReview?: AutopilotChapterAudit | null
    /** 辅助撰稿 · 最近一次流式生成下发的指挥器节拍（与 SSE beats_generated 一致） */
    assistStreamBeatSession?: { chapterNumber: number; beats: StreamGeneratedBeat[] } | null
    /** 对应章节流式生成失败时，微观区才用章纲拆条兜底 */
    assistStreamFailedChapter?: number | null
    /** 流式完成但章前拆拍失败/降级（≤1 拍） */
    assistStreamPlanFailedChapter?: number | null
    /** 外部 +1 时自动切到节拍规划「微观」tab */
    beatTabBump?: number
    /** 全托管正在写的本章且 total_beats≤1（规划已结束并降级） */
    autopilotOutlinePlanFailed?: boolean
    /** 最近一次流式生成完成的章号（无微观节拍时用于提示） */
    assistStreamCompletedChapter?: number | null
  }>(),
  {
    currentChapterNumber: null,
    readOnly: false,
    autopilotChapterReview: null,
    assistStreamBeatSession: null,
    assistStreamFailedChapter: null,
    assistStreamPlanFailedChapter: null,
    autopilotOutlinePlanFailed: false,
    assistStreamCompletedChapter: null,
  }
)

const storyNodeNotFound = ref(false)
const chapterPlan = ref<StoryNode | null>(null)
const knowledgeChapter = ref<ChapterSummary | null>(null)

const activeBeatsTab = ref<'macro' | 'micro'>('macro')
watch(() => props.beatTabBump, (v) => { if (v && v > 0) activeBeatsTab.value = 'micro' })

// Bible 数据用于 ID -> name 映射
const bibleCharacters = ref<CharacterDTO[]>([])

// 获取人物名称
const getCharacterName = (charId: string): string => {
  const char = bibleCharacters.value.find(c => c.id === charId)
  return char ? char.name : charId
}

const planMoodLine = computed(() => {
  const m = chapterPlan.value?.metadata
  if (!m || typeof m !== 'object') return ''
  const mood = m.mood ?? m.emotion ?? m.tone
  if (typeof mood === 'string' && mood.trim()) return mood
  if (Array.isArray(m.moods) && m.moods.length) return m.moods.join('、')
  return ''
})

const BEAT_LINE_CAP = 48
/** 与后端 chapter_narrative_sync._beats_from_structure_outline 一致：先按换行，再按句读拆，避免一整段只算一条节拍 */
const BEAT_SENTENCE_SPLIT = /[；;。！？!?]+/

/** 过滤按句切分产生的空串、纯标点/引号残片 */
function isMeaningfulBeatLine(s: string): boolean {
  const t = String(s || '').trim()
  if (t.length < 2) return false
  return /[\u4e00-\u9fffA-Za-z0-9]/.test(t)
}

function expandRawBeatLines(raw: string[]): string[] {
  const out: string[] = []
  for (const line of raw) {
    const t = String(line || '').trim()
    if (!isMeaningfulBeatLine(t)) continue
    const byNewline = t.split(/\n+/).map(s => s.trim()).filter(Boolean)
    for (const chunk of byNewline) {
      const subs = chunk
        .split(BEAT_SENTENCE_SPLIT)
        .map(s => s.trim())
        .filter(isMeaningfulBeatLine)
      if (subs.length <= 1) {
        if (isMeaningfulBeatLine(chunk)) out.push(chunk)
      } else {
        out.push(...subs)
      }
      if (out.length >= BEAT_LINE_CAP) {
        return out.slice(0, BEAT_LINE_CAP)
      }
    }
  }
  return out.slice(0, BEAT_LINE_CAP)
}

/** 知识库叙事节拍条（仅用于宏观页展示，不进微观指挥器区） */
const narrativeBeatSections = computed(() => {
  const k = knowledgeChapter.value
  if (!k?.beat_sections?.length) return []
  const raw = k.beat_sections.map(s => String(s || '').trim()).filter(Boolean)
  return expandRawBeatLines(raw)
})

/** 流式失败时从章纲拆条的兜底素材 */
const beatLines = computed(() => {
  const ol = chapterPlan.value?.outline?.trim()
  if (!ol) return []
  const raw = ol.split(/\n+/).map(s => s.trim()).filter(s => s.length > 0)
  return expandRawBeatLines(raw)
})

const showBeatsCard = computed(() => {
  if (!props.currentChapterNumber) return false
  if (chapterPlan.value?.outline?.trim()) return true
  if (knowledgeChapter.value) return true
  if (
    props.assistStreamBeatSession?.chapterNumber === props.currentChapterNumber &&
    props.assistStreamBeatSession.beats.length > 0
  ) {
    return true
  }
  if (props.assistStreamFailedChapter === props.currentChapterNumber) return true
  return false
})

interface MicroBeat {
  description: string
  target_words: number
  focus: string
  active_action?: string
  emotion_gap?: string
  forbidden_drift?: string
}

const BEAT_FOCUS_LABELS: Record<string, string> = {
  sensory: '感官',
  dialogue: '对话',
  action: '动作',
  emotion: '情绪',
  pacing: '节奏',
  outline_ref: '大纲参考',
  narrative_ref: '叙事节拍',
  transition: '过渡',
}

function formatBeatDescription(raw: string): string {
  const s = String(raw || '').trim()
  const prefix = '【章纲节选·须落实】'
  if (!s.startsWith(prefix)) return s
  const nl = s.indexOf('\n')
  if (nl === -1) return s
  return s.slice(nl + 1).trim() || s
}

function beatFocusLabel(focus: string): string {
  const key = (focus || '').trim()
  if (BEAT_FOCUS_LABELS[key]) return BEAT_FOCUS_LABELS[key]
  if (!key) return '节拍'
  return key
}

function normalizeMicroBeatItems(raw: unknown[]): MicroBeat[] {
  const out: MicroBeat[] = []
  for (const item of raw) {
    if (item == null) continue
    if (typeof item === 'string') {
      const d = item.trim()
      if (d) out.push({ description: d, target_words: 0, focus: 'pacing' })
      continue
    }
    if (typeof item === 'object' && !Array.isArray(item)) {
      const o = item as Record<string, unknown>
      const desc = String(o.description ?? o.text ?? o.intent ?? o.scene_goal ?? o.summary ?? '').trim()
      if (!desc) continue
      const tw = o.target_words
      const targetWords =
        typeof tw === 'number' && Number.isFinite(tw)
          ? tw
          : typeof tw === 'string' && tw.trim() !== '' && Number.isFinite(Number(tw))
            ? Number(tw)
            : 0
      const focus = String(o.focus ?? o.type ?? 'pacing').trim() || 'pacing'
      out.push({
        description: desc,
        target_words: targetWords,
        focus,
        active_action:   typeof o.active_action   === 'string' ? o.active_action   : undefined,
        emotion_gap:     typeof o.emotion_gap      === 'string' ? o.emotion_gap     : undefined,
        forbidden_drift: typeof o.forbidden_drift  === 'string' ? o.forbidden_drift : undefined,
      })
    }
  }
  return out
}

function outlineFallbackMicroBeats(): MicroBeat[] {
  if (!beatLines.value.length) return []
  return beatLines.value.map(line => ({
    description: line,
    target_words: 0,
    focus: 'outline_ref',
  }))
}

/** 落库 micro_beats → 流式 SSE；不足时章纲拆条预览（与宏观叙事条分离） */
function conductorMicroBeatsForChapter(ch: number): MicroBeat[] {
  const k = knowledgeChapter.value
  if (k?.micro_beats && Array.isArray(k.micro_beats) && k.micro_beats.length > 0) {
    const parsed = normalizeMicroBeatItems(k.micro_beats as unknown[])
    if (parsed.length > 0) return parsed
  }
  const sess = props.assistStreamBeatSession
  if (sess && sess.chapterNumber === ch && sess.beats.length > 0) {
    const parsed = normalizeMicroBeatItems(sess.beats as unknown[])
    if (parsed.length > 0) return parsed
  }
  return []
}

function isOutlinePlanFailedForChapter(ch: number): boolean {
  if (props.assistStreamFailedChapter != null && props.assistStreamFailedChapter === ch) {
    return true
  }
  if (props.assistStreamPlanFailedChapter != null && props.assistStreamPlanFailedChapter === ch) {
    return true
  }
  if (props.autopilotOutlinePlanFailed && props.currentChapterNumber === ch) {
    return true
  }
  return false
}

const microBeats = computed<MicroBeat[]>(() => {
  const ch = props.currentChapterNumber
  if (!ch) return []

  const conductor = conductorMicroBeatsForChapter(ch)
  const outlinePreview = outlineFallbackMicroBeats()
  const planFailed = isOutlinePlanFailedForChapter(ch)

  if (conductor.length > 1) return conductor

  if (planFailed && outlinePreview.length > 1) return outlinePreview

  if (conductor.length >= 1) return conductor

  if (planFailed && outlinePreview.length) return outlinePreview

  return []
})

const microHintIsOutlineFallback = computed(() => {
  const ch = props.currentChapterNumber
  if (!ch || !microBeats.value.length) return false
  return microBeats.value.every(b => b.focus === 'outline_ref')
})

const microHintFromKnowledgeDb = computed(() => {
  const k = knowledgeChapter.value
  return !!(k?.micro_beats && Array.isArray(k.micro_beats) && k.micro_beats.length > 0)
})

const microEmptyDescription = computed(() => {
  const ch = props.currentChapterNumber
  if (ch && isOutlinePlanFailedForChapter(ch) && beatLines.value.length > 0) {
    return '章前规划失败，但章纲无法拆出有效预览句段'
  }
  if (props.assistStreamCompletedChapter === ch) {
    return '本轮流式未产出指挥器节拍；可重试生成或查看宏观大纲'
  }
  if (narrativeBeatSections.value.length > 0) {
    return '章前规划拆拍将在写作时产出；知识库叙事条见「宏观」页'
  }
  if (
    props.autopilotOutlinePlanFailed === false &&
    beatLines.value.length > 0
  ) {
    return '章前规划进行中或尚未开始；规划完成后将显示指挥器节拍'
  }
  return '暂无指挥器微观节拍：流式生成或全托管写作时将进行章前规划（outline_planning）'
})

const getBeatTypeColor = (focus: string): 'success' | 'warning' | 'error' | 'info' | 'default' => {
  const colorMap: Record<string, 'success' | 'warning' | 'error' | 'info' | 'default'> = {
    sensory: 'info',
    dialogue: 'success',
    action: 'warning',
    emotion: 'error',
    pacing: 'default',
    outline_ref: 'default',
    narrative_ref: 'info',
    transition: 'info',
  }
  return colorMap[focus] || 'default'
}

function formatTime(t: string) {
  try {
    return new Date(t).toLocaleString('zh-CN', {
      month: 'numeric',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    })
  } catch {
    return t
  }
}

function findChapterNode(nodes: StoryNode[], num: number): StoryNode | null {
  for (const node of nodes) {
    if (node.node_type === 'chapter' && node.number === num) return node
    if (node.children?.length) {
      const found = findChapterNode(node.children, num)
      if (found) return found
    }
  }
  return null
}

const resolveStoryNode = async () => {
  storyNodeNotFound.value = false
  if (!props.currentChapterNumber) {
    chapterPlan.value = null
    return
  }
  try {
    const res = await planningApi.getStructure(props.slug)
    const roots = res.data?.nodes ?? []
    const node = findChapterNode(roots, props.currentChapterNumber)
    if (node) {
      chapterPlan.value = node
    } else {
      chapterPlan.value = null
      storyNodeNotFound.value = true
    }
  } catch {
    storyNodeNotFound.value = true
  }
}

async function loadKnowledgeChapter() {
  if (!props.slug || !props.currentChapterNumber) {
    knowledgeChapter.value = null
    return
  }
  try {
    const k = await knowledgeApi.getKnowledge(props.slug)
    const row = k.chapters?.find(c => c.chapter_id === props.currentChapterNumber)
    knowledgeChapter.value = row ?? null
  } catch {
    /* 保留上一份，避免托管轮询触发 deskTick 时整卡清空闪烁 */
  }
}

// 加载 Bible 数据用于名称映射
async function loadBible() {
  try {
    const bible = await bibleApi.getBible(props.slug)
    bibleCharacters.value = bible.characters || []
  } catch {
    bibleCharacters.value = []
  }
}

watch(() => props.slug, async (slug) => {
  if (slug) {
    chapterPlan.value = null
    storyNodeNotFound.value = false
    await Promise.all([
      loadBible(),
      resolveStoryNode(),
      loadKnowledgeChapter()
    ])
  }
})

watch(() => props.currentChapterNumber, async () => {
  await resolveStoryNode()
  await loadKnowledgeChapter()
}, { immediate: false })

const refreshStore = useWorkbenchRefreshStore()
const { deskTick } = storeToRefs(refreshStore)
let deskTickDebounce: ReturnType<typeof setTimeout> | null = null
const DESK_TICK_DEBOUNCE_MS = 450
watch(deskTick, () => {
  if (deskTickDebounce) clearTimeout(deskTickDebounce)
  deskTickDebounce = setTimeout(() => {
    deskTickDebounce = null
    void resolveStoryNode()
    void loadKnowledgeChapter()
  }, DESK_TICK_DEBOUNCE_MS)
})

onMounted(async () => {
  await loadBible()
  await resolveStoryNode()
  await loadKnowledgeChapter()
})

onUnmounted(() => {
  if (deskTickDebounce) {
    clearTimeout(deskTickDebounce)
    deskTickDebounce = null
  }
})
</script>

<style scoped>
.cc-panel {
  padding: 0;
  height: 100%;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.cc-scroll {
  flex: 1;
  min-height: 0;
}

.card-title {
  font-size: 13px;
  font-weight: 600;
}

/* 节拍列表 */
.cc-beat-list {
  margin: 8px 0 0;
  padding-left: 1.2em;
  font-size: 12px;
  line-height: 1.8;
}

/* 宏观大纲 */
.macro-outline-text {
  font-size: 15px;
  line-height: 1.9;
  color: var(--n-text-color-1);
  white-space: pre-wrap;
}

.narrative-beat-line {
  display: flex;
  gap: 8px;
  align-items: flex-start;
  padding: 6px 8px;
  border-radius: 6px;
  background: var(--n-color-modal);
  border: 1px dashed var(--n-border-color);
}

/* 微观节拍 */
.micro-beat-item {
  padding: 12px 14px;
  border-radius: 10px;
  background: linear-gradient(135deg, rgba(99, 102, 241, 0.04) 0%, rgba(139, 92, 246, 0.02) 100%);
  border: 1px solid rgba(99, 102, 241, 0.1);
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

.micro-beat-item:hover {
  border-color: rgba(99, 102, 241, 0.2);
  background: linear-gradient(135deg, rgba(99, 102, 241, 0.06) 0%, rgba(139, 92, 246, 0.04) 100%);
}

.micro-beat-header {
  display: flex;
  align-items: center;
  margin-bottom: 8px;
}

.mbc {
  margin-top: 6px;
  padding: 6px 8px;
  border-radius: 6px;
  background: color-mix(in srgb, var(--color-brand, #6366f1) 5%, var(--card-color, #fff));
  border: 1px solid color-mix(in srgb, var(--color-brand, #6366f1) 18%, transparent);
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.mbc-row {
  display: flex;
  align-items: baseline;
  gap: 6px;
  font-size: 11px;
  line-height: 1.45;
}
.mbc-tag {
  flex-shrink: 0;
  font-size: 10px;
  font-weight: 700;
  padding: 1px 5px;
  border-radius: 4px;
  background: color-mix(in srgb, var(--color-brand, #6366f1) 14%, transparent);
  color: var(--color-brand, #6366f1);
}
.mbc-tag--warn {
  background: rgba(239, 68, 68, 0.12);
  color: #dc2626;
}
.mbc-val { color: var(--app-text-primary, #1e293b); }
.mbc-val--muted { color: var(--app-text-secondary, #64748b); }

.micro-beat-desc {
  margin-top: 6px;
  padding-left: 12px;
  font-size: 13px;
  line-height: 1.6;
  color: var(--n-text-color-2);
  border-left: 2px solid var(--n-border-color);
}

.micro-beat-item:hover .micro-beat-desc {
  border-left-color: var(--n-primary-color);
}

/* 审阅行 */
.review-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
}

/* 张力进度条 */
.tension-bar {
  position: relative;
  width: 100px;
  height: 20px;
  background: var(--n-color-modal);
  border-radius: 10px;
  overflow: hidden;
  border: 1px solid var(--n-border-color);
}

.tension-fill {
  height: 100%;
  background: linear-gradient(90deg, #10b981, #f59e0b, #ef4444);
  border-radius: 10px;
  transition: width 0.3s ease;
}

.tension-value {
  position: absolute;
  right: 8px;
  top: 50%;
  transform: translateY(-50%);
  font-size: 11px;
  font-weight: 600;
  color: var(--n-text-color-1);
}
</style>
