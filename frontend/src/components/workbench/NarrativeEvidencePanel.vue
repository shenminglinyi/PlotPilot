<template>
  <section class="pp-section">
    <header class="pp-section-header">
      <span class="pp-section-label">剧情验收</span>
      <n-button size="tiny" secondary @click="openReport">查看证据</n-button>
    </header>
    <p class="pp-section-body summary" aria-live="polite">{{ progressText }}</p>
  </section>

  <n-modal v-model:show="open" preset="card" title="剧情验收" :style="{ width: 'min(680px, 94vw)' }">
    <div class="evidence-body">
      <p v-if="error" role="alert">{{ error }} <button @click="loadReport()">重试</button></p>
      <p v-else-if="!report">正在读取验收记录…</p>
      <template v-else>
        <div class="toolbar">
          <label>查看
            <select v-model="groupId" @change="closeSource">
              <option v-for="g in groups" :key="g.id" :value="g.id">{{ g.title }}</option>
            </select>
          </label>
          <n-button size="small" @click="loadReport()">刷新</n-button>
        </div>
        <template v-if="group">
          <p v-for="issue in group.issues" :key="issue" class="issue">{{ issue }}</p>
          <ul v-if="group.items.length" class="verdicts">
            <li v-for="(item, index) in group.items" :key="index">
              <div class="verdict">
                <strong>{{ item.description }}</strong>
                <span class="state">{{ item.status === 'open' ? '待兑现' : item.evidence_current ? '已核验' : '待复核' }}</span>
              </div>
              <div class="citations">
                <template v-for="number in item.evidence_chapters" :key="number">
                  <template v-if="item.evidence_passages?.some(p => p.chapter_number === number)">
                    <button v-for="p in item.evidence_passages.filter(p => p.chapter_number === number)"
                      :key="p.start" type="button" @click="read(number, item.evidence_revisions?.[number], item.evidence_current, p)">
                      第 {{ number }} 章 ·「{{ p.quote }}」
                    </button>
                  </template>
                  <button v-else type="button" @click="read(number, item.evidence_revisions?.[number], item.evidence_current)">阅读第 {{ number }} 章</button>
                </template>
              </div>
            </li>
          </ul>
          <p v-else>暂无验收记录。</p>
          <p v-for="note in group.notes" :key="note">有意留白 · {{ note }}</p>
          <button v-if="group.id === 'ending' && report.ending_review" type="button"
            @click="read(report.ending_review.reviewed_through_chapter, report.ending_review.reviewed_through_revision, report.ending_review.terminal_revision_current)">核读末章</button>
        </template>
        <section v-if="source" aria-live="polite" class="source">
          <div class="verdict">
            <strong>第 {{ source.number }} 章 {{ chapter?.title }}</strong>
            <n-button size="tiny" quaternary @click="closeSource">收起原文</n-button>
          </div>
          <p v-if="sourceError" role="alert">{{ sourceError }}</p>
          <p v-else-if="!chapter">正在读取正文…</p>
          <p v-else-if="excerpt" class="prose">{{ excerpt.before }}<mark>{{ excerpt.quote }}</mark>{{ excerpt.after }}</p>
          <template v-else>
            <p v-if="!currentSource || source.passage" class="issue">此项证据待复核。以下为本章当前正文。</p>
            <p class="prose">{{ chapter.content || '本章当前没有正文。' }}</p>
          </template>
        </section>
      </template>
    </div>
  </n-modal>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { getEvidenceSource, getNarrativeReport, type EvidencePassage, type EvidenceSource, type ReviewedItem } from '@/api/narrativeProgress'
import { useWorkbenchRefreshStore } from '@/stores/workbenchRefreshStore'

const props = defineProps<{ slug: string }>()
const refresh = useWorkbenchRefreshStore()
const open = ref(false)
const report = ref<Awaited<ReturnType<typeof getNarrativeReport>>>()
const error = ref('')
const groupId = ref('')
const source = ref<{ number: number; passage?: EvidencePassage; current: boolean; signedRevision?: string }>()
const chapter = ref<EvidenceSource>()
const sourceError = ref('')
let requestId = 0
let sourceRequestId = 0

const progressText = computed(() => {
  if (error.value) return error.value
  if (!report.value) return '正在读取验收记录…'
  const r = report.value
  const state = r.story_finished ? '故事已验收' : r.generation_finished ? '故事待验收' : '写作中'
  return `已写 ${r.completed_chapters} / ${r.target_chapters} 章 · ${state}`
})
const groups = computed(() => {
  if (!report.value) return []
  const options = report.value.volumes.map(v => ({
    id: 'volume-' + v.id, title: v.title, items: v.milestones, issues: v.issues, notes: [] as string[],
  }))
  const e = report.value.ending_review
  const items: ReviewedItem[] = []
  if (e) {
    for (const [label, item] of [['核心冲突', e.core_conflict], ['人物去向', e.character_outcomes], ['结局', e.ending]] as const) {
      if (item) items.push({ ...item, description: `${label} · ${item.description}` })
    }
    items.push(...(e.required_promises || []))
  }
  options.push({ id: 'ending', title: '全书终局', items, notes: e?.open_ending_notes || [],
    issues: e && !e.terminal_revision_current ? ['末章版本待复核。'] : [] })
  return options
})
const group = computed(() => groups.value.find(g => g.id === groupId.value))
const currentSource = computed(() => source.value?.current && !!source.value.signedRevision
  && chapter.value?.status === 'completed' && chapter.value.manuscript_revision === source.value.signedRevision)
const excerpt = computed(() => {
  const p = source.value?.passage
  if (!chapter.value?.content || !currentSource.value || !p) return
  // The backend signs Unicode code-point offsets. JS UTF-16 offsets diverge after emoji.
  const chars = Array.from(chapter.value.content)
  if (chars.slice(p.start, p.end).join('') !== p.quote) return
  const left = Math.max(0, p.start - 120)
  const right = Math.min(chars.length, p.end + 120)
  return { before: (left ? '…' : '') + chars.slice(left, p.start).join(''), quote: p.quote,
    after: chars.slice(p.end, right).join('') + (right < chars.length ? '…' : '') }
})
function closeSource() {
  sourceRequestId++
  source.value = undefined
  chapter.value = undefined
  sourceError.value = ''
}
async function read(number: number, signedRevision: string | undefined, current: boolean, passage?: EvidencePassage) {
  closeSource()
  const id = sourceRequestId
  source.value = {number, passage, current, signedRevision}
  try {
    const row = await getEvidenceSource(props.slug, number)
    if (id !== sourceRequestId) return
    chapter.value = row
    if (current && !currentSource.value) void loadReport(true)
  } catch {
    if (id === sourceRequestId) sourceError.value = '当前正文无法读取。'
  }
}
async function loadReport(retainSource = false) {
  const id = ++requestId
  error.value = ''
  if (!retainSource) closeSource()
  try {
    const data = await getNarrativeReport(props.slug)
    if (id !== requestId) return
    report.value = data
    if (!groups.value.some(g => g.id === groupId.value)) groupId.value = groups.value[0]?.id || ''
  } catch {
    if (id === requestId) error.value = '验收记录暂时无法读取。'
  }
}
function openReport() {
  open.value = true
  void loadReport()
}
watch(() => props.slug, () => {
  open.value = false
  groupId.value = ''
  report.value = undefined
  void loadReport()
}, { immediate: true })
watch(() => refresh.deskTick, () => void loadReport())
</script>

<style scoped>
.summary { margin: 0; }
.evidence-body { max-height: 72vh; overflow-y: auto; }
.toolbar, .verdict, .citations { display: flex; align-items: center; gap: 8px; }
.toolbar, .verdict { justify-content: space-between; }
.toolbar select { margin-inline-start: 8px; padding: 4px; color: inherit; background: var(--app-bg); }
.verdicts { list-style: none; padding: 0; }
.verdicts li, .source { padding: 12px 0; border-top: 1px solid var(--app-border); }
.state { white-space: nowrap; }
.citations { flex-wrap: wrap; margin-top: 6px; }
.evidence-body button:not(.n-button) { font: inherit; text-align: left; cursor: pointer; color: inherit;
  border: 1px solid var(--app-border); background: transparent; border-radius: 4px; padding: 3px 8px; }
.citations button { max-width: 100%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.prose { white-space: pre-wrap; overflow-wrap: anywhere; line-height: 1.8; }
.issue { color: var(--n-text-color, currentColor); font-weight: 600; }
mark { color: #321f00; background: #ffdc85; }
</style>
