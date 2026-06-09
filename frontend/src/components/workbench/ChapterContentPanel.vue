<template>
  <div class="cc-panel">
    <n-empty v-if="!currentChapterNumber" description="请先从左侧选择一个章节" style="margin-top: 40px" />

    <n-scrollbar v-else class="cc-scroll">
      <n-space vertical :size="12" style="padding: 8px 4px 16px">
        <n-alert v-if="readOnly" type="warning" :show-icon="true" size="small">
          托管运行中：仅可查看
        </n-alert>

        <!-- 章前导演计划 -->
        <n-card v-if="chapterPlan" size="small" :bordered="true" class="cc-card-plan">
          <template #header>
            <span class="card-title">📋 章前导演计划</span>
          </template>
          <n-descriptions :column="1" label-placement="left" size="small" label-style="white-space: nowrap">
            <n-descriptions-item label="标题">{{ chapterPlan.title || '—' }}</n-descriptions-item>
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

        <!-- 章节执行剧本 -->
        <n-card v-if="showBeatsCard" size="small" :bordered="true" class="cc-card-script">
          <template #header>
            <div class="script-card-header">
              <span class="card-title">章节执行剧本</span>
              <span class="script-source">{{ scriptSource.label }}</span>
            </div>
          </template>

          <n-alert v-if="showSingleOutlineAtomWarning" type="warning" :show-icon="true" size="small" class="script-alert">
            本章只拿到单段章纲，尚未形成可执行拆拍。
          </n-alert>
          <n-alert
            v-else-if="microHintIsOutlinePreview"
            type="info"
            :show-icon="true"
            size="small"
            class="script-alert"
          >
            当前为章纲拆条预览。
          </n-alert>

          <div v-if="scriptBlocks.length" class="script-blocks">
            <section v-for="block in scriptBlocks" :key="block.title" class="script-block">
              <h4>{{ block.title }}</h4>
              <p v-for="(line, index) in block.lines" :key="`${block.title}-${index}`">{{ line }}</p>
            </section>
          </div>

          <n-empty
            v-else
            :description="microEmptyDescription"
            size="small"
          />
        </n-card>

        <n-alert v-if="storyNodeNotFound" type="warning" :show-icon="true">
          未在结构树中找到第 {{ currentChapterNumber }} 章的规划节点
        </n-alert>

      </n-space>
    </n-scrollbar>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { useMessage } from 'naive-ui'
import { useDebouncedTask } from '../../composables/useDebouncedTask'
import { useWorkbenchRefreshStore } from '../../stores/workbenchRefreshStore'
import { runtimePerformance } from '../../config/performance'
import { planningApi } from '../../api/planning'
import type { StoryNode } from '../../api/planning'
import { knowledgeApi } from '../../api/knowledge'
import type { ChapterSummary } from '../../api/knowledge'
import { bibleApi, type CharacterDTO } from '../../api/bible'
import type { StreamGeneratedBeat } from '../../api/workflow'
import type { AutopilotChapterAudit } from './ChapterStatusPanel.vue'
import { loadAssistBeatSession } from '@/utils/assistBeatSession'
import { getBeatFocusLabel, getBeatFocusTone, getBeatFunctionLabel } from '@/domain/chapterWriting'

const message = useMessage()

const props = withDefaults(
  defineProps<{
    slug: string
    currentChapterNumber?: number | null
    readOnly?: boolean
    autopilotChapterReview?: AutopilotChapterAudit | null
    /** 辅助撰稿旧链路 · 最近一次流式生成下发的指挥器节拍 */
    assistStreamBeatSession?: { chapterNumber: number; beats: StreamGeneratedBeat[] } | null
    /** 对应章节流式生成失败时，规划卡片才用章纲拆条预览 */
    assistStreamFailedChapter?: number | null
    /** 流式完成但章前拆拍失败（≤1 拍） */
    assistStreamPlanFailedChapter?: number | null
    /** 全托管正在写的本章且执行剧本已准备 */
    autopilotOutlinePlanFailed?: boolean
    /** 全托管是否仍在运行（用于空态文案，避免停止后仍显示「规划进行中」） */
    autopilotRunning?: boolean
    /** 最近一次流式生成完成的章号 */
    assistStreamCompletedChapter?: number | null
    /** 全托管 /status 的 outline_plan_mode（如 raw_outline_single） */
    outlinePlanMode?: string
  }>(),
  {
    currentChapterNumber: null,
    readOnly: false,
    autopilotChapterReview: null,
    assistStreamBeatSession: null,
    assistStreamFailedChapter: null,
    assistStreamPlanFailedChapter: null,
    autopilotOutlinePlanFailed: false,
    autopilotRunning: false,
    assistStreamCompletedChapter: null,
    outlinePlanMode: '',
  }
)

const storyNodeNotFound = ref(false)
const chapterPlan = ref<StoryNode | null>(null)
const knowledgeChapter = ref<ChapterSummary | null>(null)

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

/** 流式失败时从章纲拆条的预览素材 */
const beatLines = computed(() => {
  const ol = chapterPlan.value?.outline?.trim()
  if (!ol) return []
  const raw = ol.split(/\n+/).map(s => s.trim()).filter(s => s.length > 0)
  return expandRawBeatLines(raw)
})

const showBeatsCard = computed(() => {
  if (!props.currentChapterNumber) return false
  return true
})

interface MicroBeat {
  description: string
  target_words: number
  focus: string
  function?: string
  pov?: string
  cast_refs?: string[]
  location_refs?: string[]
  prop_refs?: string[]
  knowledge_refs?: string[]
  visible_action?: string
  conflict?: string
  delta?: string
  handoff_to_next?: string
  must_include?: string[]
  must_not_include?: string[]
  active_action?: string
  emotion_gap?: string
  forbidden_drift?: string
}

function formatBeatDescription(raw: string): string {
  let s = String(raw || '').trim()
  const prefix = '【章纲节选·须落实】'
  s = s.replace(/\s*【随后，紧接着写】[\s\S]*$/u, '').trim()
  while (s.includes(prefix)) {
    const start = s.indexOf(prefix)
    const nl = s.indexOf('\n', start)
    if (nl === -1) {
      s = s.slice(0, start).trim()
      break
    }
    s = `${s.slice(0, start)}${s.slice(nl + 1)}`.trim()
  }
  return s
}

function beatFocusLabel(focus: string): string {
  return getBeatFocusLabel(focus)
}

function beatFocusTone(focus: string) {
  return getBeatFocusTone(focus)
}

function normalizeMicroBeatItems(raw: unknown[]): MicroBeat[] {
  const out: MicroBeat[] = []
  const asStringList = (value: unknown): string[] | undefined => {
    if (Array.isArray(value)) {
      const items = value.map(v => String(v).trim()).filter(Boolean)
      return items.length ? items : undefined
    }
    if (typeof value === 'string' && value.trim()) return [value.trim()]
    return undefined
  }
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
        function:        typeof o.function        === 'string' ? o.function        : undefined,
        pov:             typeof o.pov             === 'string' ? o.pov             : undefined,
        cast_refs:       asStringList(o.cast_refs),
        location_refs:   asStringList(o.location_refs),
        prop_refs:       asStringList(o.prop_refs),
        knowledge_refs:  asStringList(o.knowledge_refs),
        visible_action:  typeof o.visible_action  === 'string' ? o.visible_action  : undefined,
        conflict:        typeof o.conflict        === 'string' ? o.conflict        : undefined,
        delta:           typeof o.delta           === 'string' ? o.delta           : undefined,
        handoff_to_next: typeof o.handoff_to_next === 'string' ? o.handoff_to_next : undefined,
        must_include:    asStringList(o.must_include),
        must_not_include: asStringList(o.must_not_include),
        active_action:   typeof o.active_action   === 'string' ? o.active_action   : undefined,
        emotion_gap:     typeof o.emotion_gap      === 'string' ? o.emotion_gap     : undefined,
        forbidden_drift: typeof o.forbidden_drift  === 'string' ? o.forbidden_drift : undefined,
      })
    }
  }
  return out
}

function hasBeatContractDetails(beat: MicroBeat): boolean {
  return Boolean(
    beat.function ||
    beat.pov ||
    beat.cast_refs?.length ||
    beat.location_refs?.length ||
    beat.prop_refs?.length ||
    beat.visible_action ||
    beat.conflict ||
    beat.delta ||
    beat.handoff_to_next ||
    beat.active_action ||
    beat.emotion_gap ||
    beat.forbidden_drift,
  )
}

function beatFunctionLabel(value: string): string {
  return getBeatFunctionLabel(value)
}

function outlinePreviewMicroBeats(): MicroBeat[] {
  if (!beatLines.value.length) return []
  return beatLines.value.map(line => ({
    description: line,
    target_words: 0,
    focus: 'outline_ref',
  }))
}

/** 落库 micro_beats → 流式 SSE；规划失败时才使用章纲拆条预览 */
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
  const stored = loadAssistBeatSession(props.slug, ch)
  if (stored?.length) {
    const parsed = normalizeMicroBeatItems(stored as unknown[])
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
  const outlinePreview = outlinePreviewMicroBeats()
  const planFailed = isOutlinePlanFailedForChapter(ch)

  if (conductor.length > 1) return conductor

  if (planFailed && outlinePreview.length > 1) return outlinePreview

  if (conductor.length >= 1) return conductor

  if (planFailed && outlinePreview.length) return outlinePreview

  return []
})

const microHintIsOutlinePreview = computed(() => {
  const ch = props.currentChapterNumber
  if (!ch || !microBeats.value.length) return false
  return microBeats.value.every(b => b.focus === 'outline_ref')
})

const microHintFromKnowledgeDb = computed(() => {
  const k = knowledgeChapter.value
  return !!(k?.micro_beats && Array.isArray(k.micro_beats) && k.micro_beats.length > 0)
})

const showSingleOutlineAtomWarning = computed(() => {
  if (microHintIsOutlinePreview.value) return false
  if (microBeats.value.length !== 1) return false
  const mode = (props.outlinePlanMode || '').trim()
  if (mode === 'raw_outline_single' || mode === 'error_single_outline') return true
  if (props.autopilotOutlinePlanFailed) return true
  const ch = props.currentChapterNumber
  if (ch && props.assistStreamPlanFailedChapter === ch) return true
  return false
})

const rawOutlineDisplayLines = computed(() => {
  const raw = chapterPlan.value?.outline?.trim()
  if (!raw) return []
  return raw
    .split(/\n+/)
    .map(s => s.trim())
    .filter(isMeaningfulBeatLine)
    .slice(0, 24)
})

interface ScriptBlock {
  title: string
  lines: string[]
}

function compactScriptLine(raw: string): string {
  return String(raw || '')
    .replace(/\[\[[a-z_]+:[^|\]]+\|([^\]]+)\]\]/gi, '$1')
    .replace(/\b(?:novel|char|loc|prop|faction|clue|skill|system)-[A-Za-z0-9_-]+\b/g, '')
    .replace(/\s+/g, ' ')
    .replace(/^[-*•\d.、\s]+/, '')
    .replace(/\s*\|\s*/g, ' | ')
    .trim()
}

function presentScriptLine(raw: string): string {
  const compact = compactScriptLine(raw)
  if (!compact) return ''

  const parts = compact
    .split('|')
    .map(part => part.trim())
    .filter(part => part && part !== '（无）' && part !== '(无)')

  if (parts.length <= 1) return compact

  const [lead, ...rest] = parts
  const useful = rest.filter(part => /[\u4e00-\u9fffA-Za-z0-9]/.test(part))
  if (!useful.length) return lead

  if (/^对话\d+[:：]/.test(lead)) {
    return `${lead}；${useful.join('；')}`
  }
  if (lead.includes('→')) {
    return `${lead}：${useful.join('；')}`
  }
  return `${lead}；${useful.join('；')}`
}

function chunkLines(title: string, lines: string[]): ScriptBlock | null {
  const cleaned = lines.map(presentScriptLine).filter(Boolean)
  if (!cleaned.length) return null
  return { title, lines: cleaned.slice(0, 6) }
}

function outlineBlocks(lines: string[]): ScriptBlock[] {
  const blocks: ScriptBlock[] = []
  let currentTitle = '执行概要'
  let currentLines: string[] = []
  const flush = () => {
    const block = chunkLines(currentTitle, currentLines)
    if (block) blocks.push(block)
  }

  for (const line of lines) {
    const t = compactScriptLine(line)
    if (!t) continue
    const heading = t.match(/^([一二三四五六七八九十]+|[0-9]+)[、.．]\s*(.+)$/)
    if (heading) {
      flush()
      currentTitle = heading[2].replace(/[:：]\s*$/, '') || '执行段落'
      currentLines = []
      continue
    }
    currentLines.push(t)
  }
  flush()

  if (blocks.length > 0) return blocks.slice(0, 4)

  const size = Math.max(1, Math.ceil(lines.length / 3))
  return [
    chunkLines('开场', lines.slice(0, size)),
    chunkLines('推进', lines.slice(size, size * 2)),
    chunkLines('收束', lines.slice(size * 2)),
  ].filter((block): block is ScriptBlock => Boolean(block))
}

const scriptBlocks = computed<ScriptBlock[]>(() => {
  if (microBeats.value.length) {
    const lines = microBeats.value.map((beat, index) => {
      const meta = [
        beat.function ? beatFunctionLabel(beat.function) : '',
        beat.target_words > 0 ? `${beat.target_words}字` : '',
      ].filter(Boolean)
      const prefix = meta.length ? `${meta.join(' / ')}：` : ''
      return `${index + 1}. ${prefix}${formatBeatDescription(beat.description)}`
    })
    return outlineBlocks(lines)
  }
  return outlineBlocks(rawOutlineDisplayLines.value)
})

const scriptSource = computed(() => {
  if (microHintFromKnowledgeDb.value) {
    return { label: '已落库节拍', className: 'script-source--db' }
  }
  if (microHintIsOutlinePreview.value) {
    return { label: '章纲预览', className: 'script-source--outline' }
  }
  const ch = props.currentChapterNumber
  const sess = props.assistStreamBeatSession
  if (ch && sess?.chapterNumber === ch && sess.beats.length > 0) {
    return { label: '流式规划', className: 'script-source--stream' }
  }
  if (microBeats.value.length) {
    return { label: '本地缓存', className: 'script-source--cache' }
  }
  if (chapterPlan.value?.outline?.trim()) {
    return { label: '结构章纲', className: 'script-source--outline' }
  }
  return { label: '待规划', className: 'script-source--empty' }
})

const totalTargetWords = computed(() =>
  microBeats.value.reduce((sum, beat) => sum + Math.max(0, Number(beat.target_words || 0)), 0)
)

function countBeatConstraints(beat: MicroBeat): number {
  return (beat.must_include?.length || 0) + (beat.must_not_include?.length || 0)
}

const constraintTotal = computed(() =>
  microBeats.value.reduce((sum, beat) => sum + countBeatConstraints(beat), 0)
)

const detailTotal = computed(() =>
  microBeats.value.reduce((sum, beat) => sum + (hasBeatContractDetails(beat) ? 1 : 0), 0)
)

const scriptOverview = computed(() => {
  const beatCount = microBeats.value.length
  const outlineCount = rawOutlineDisplayLines.value.length
  return [
    {
      label: '节拍',
      value: beatCount ? `${beatCount} 段` : outlineCount ? `${outlineCount} 条` : '待生成',
      hint: beatCount ? '可执行拆拍' : outlineCount ? '章纲拆条' : '',
    },
    {
      label: '目标字数',
      value: totalTargetWords.value > 0 ? `${totalTargetWords.value} 字` : '未标注',
      hint: totalTargetWords.value > 0 ? '按节拍累计' : '',
    },
    {
      label: '约束',
      value: constraintTotal.value > 0 ? `${constraintTotal.value} 条` : '未标注',
      hint: detailTotal.value > 0 ? `${detailTotal.value} 段含合同` : '',
    },
    {
      label: '来源',
      value: scriptSource.value.label,
      hint: showSingleOutlineAtomWarning.value ? '需重新拆拍' : '',
    },
  ]
})

const microEmptyDescription = computed(() => {
  const ch = props.currentChapterNumber
  if (ch && isOutlinePlanFailedForChapter(ch) && beatLines.value.length > 0) {
    return '章前规划失败，但章纲无法拆出有效预览句段'
  }
  if (props.assistStreamCompletedChapter === ch) {
    return '本轮流式未产出指挥器节拍；可重试生成'
  }
  if (
    props.autopilotRunning &&
    props.autopilotOutlinePlanFailed === false &&
    beatLines.value.length > 0
  ) {
    return '章前规划进行中或尚未开始；规划完成后将显示指挥器节拍'
  }
  if (beatLines.value.length > 0) {
    return '暂无指挥器节拍（托管已停止或未执行章前拆拍）；可重新启动托管或使用流式生成'
  }
  return '暂无章节执行剧本：请先完成幕规划'
})

function formatRefs(items?: string[], mapCharacters = false): string {
  const clean = (items || []).map(v => String(v || '').trim()).filter(Boolean)
  if (!clean.length) return '—'
  const mapped = mapCharacters ? clean.map(getCharacterName) : clean
  const visible = mapped.slice(0, 6)
  const more = mapped.length > visible.length ? ` +${mapped.length - visible.length}` : ''
  return `${visible.join('、')}${more}`
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
const deskTickReload = useDebouncedTask(
  async () => {
    await Promise.all([
      resolveStoryNode(),
      loadKnowledgeChapter(),
    ])
  },
  () => runtimePerformance.workbench.deskTickDebounceMs,
)
watch(deskTick, () => {
  deskTickReload.schedule()
})

onMounted(async () => {
  await loadBible()
  await resolveStoryNode()
  await loadKnowledgeChapter()
})
</script>

<style scoped>
.cc-panel {
  --cc-accent: var(--color-brand);
  --cc-accent-dim: var(--color-brand-light);
  --cc-accent-border: var(--color-brand-border);
  --cc-surface: var(--app-surface-raised, var(--app-surface));
  --cc-surface-subtle: var(--app-surface-subtle);
  --cc-text: var(--app-text-primary);
  --cc-text-secondary: var(--app-text-secondary);
  --cc-text-muted: var(--app-text-muted);

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

.cc-card-script :deep(.n-card-header) {
  padding-bottom: 8px;
}

.script-card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.script-source {
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  height: 20px;
  padding: 0 7px;
  border-radius: 5px;
  border: 1px solid var(--app-border);
  background: var(--cc-surface-subtle);
  color: var(--cc-text-secondary);
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0;
  line-height: 1;
}

.script-alert {
  margin-bottom: 10px;
}

.chapter-script-text {
  margin: 0;
  padding: 10px 12px;
  max-height: 520px;
  overflow: auto;
  white-space: pre-wrap;
  word-break: break-word;
  border-radius: 6px;
  border: 1px solid var(--app-border);
  background: var(--cc-surface-subtle);
  color: var(--cc-text);
  font-family: inherit;
  font-size: 12px;
  line-height: 1.65;
}

.script-blocks {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.script-block {
  padding: 12px;
  border-radius: 8px;
  border: 1px solid var(--app-border);
  background: color-mix(in srgb, var(--cc-surface) 82%, var(--cc-surface-subtle) 18%);
}

.script-block h4 {
  margin: 0 0 8px;
  color: var(--cc-text);
  font-size: 13px;
  font-weight: 700;
  line-height: 1.4;
}

.script-block p {
  margin: 0;
  color: var(--cc-text-secondary);
  font-size: 12px;
  line-height: 1.65;
  overflow-wrap: anywhere;
}

.script-block p + p {
  margin-top: 6px;
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
  background: linear-gradient(
    90deg,
    var(--color-success),
    var(--color-warning),
    var(--color-danger)
  );
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
