<template>
  <n-modal
    v-model:show="show"
    preset="card"
    :class="['macro-modal', phase !== 'idle' && 'macro-modal--stream']"
    :mask-closable="phase === 'idle'"
    :closable="phase === 'idle' || phase === 'error'"
    :segmented="{ content: true, footer: 'soft' }"
    :title="modalTitle"
    @after-leave="resetState"
  >
    <template #header-extra>
      <span v-if="phase === 'idle'" class="mpm-subtitle">一键生成骨架，无需填写部 / 卷 / 幕</span>
      <span v-else-if="isActive" class="mpm-subtitle mpm-subtitle--live">
        <span class="live-dot" />{{ statusMessage }}
      </span>
      <span v-else-if="phase === 'done'" class="mpm-subtitle mpm-subtitle--done">
        {{ doneSummary }}
      </span>
    </template>

    <!-- ── Phase: idle ───────────────────────────────────────────── -->
    <div v-if="phase === 'idle'" class="idle-body">
      <p class="idle-lead">
        将根据本书的<strong>世界观、人物与梗概</strong>，AI 自主规划部 / 卷 / 幕结构并写入左侧结构树。篇幅与节奏以<strong>创建书目时的设定</strong>为准。
      </p>
      <div class="idle-card">
        <div class="idle-card-title">更适合</div>
        <ul class="idle-list">
          <li>想先有一副骨架再动笔</li>
          <li>愿意交给 AI 搭结构、自己跟进度与成稿</li>
          <li>需要一版可编辑的部–卷–幕草稿</li>
        </ul>
      </div>
    </div>

    <!-- ── Phase: generating / streaming / done ─────────────────── -->
    <div v-else-if="phase !== 'error'" class="stream-body">
      <!-- progress bar -->
      <div v-if="isActive" class="prog-track">
        <div class="prog-fill" :style="{ width: `${progressPct}%` }" />
      </div>

      <!-- node list -->
      <div class="node-scroll" ref="nodeScrollRef">
        <!-- arrived nodes -->
        <TransitionGroup name="node-arrive" tag="div" class="node-list">
          <div
            v-for="node in streamedNodes"
            :key="node.key"
            :class="['node-item', `node-item--${node.type}`]"
          >
            <span class="node-icon">{{ nodeIcon(node.type) }}</span>
            <div class="node-content">
              <div class="node-title">{{ node.title }}</div>
              <div v-if="node.description" class="node-desc">{{ node.description }}</div>
              <div v-if="node.narrative_goal && !node.description" class="node-desc">{{ node.narrative_goal }}</div>
            </div>
            <span v-if="node.type === 'act' && node.estimated_chapters" class="node-badge">
              {{ node.estimated_chapters }} 章
            </span>
          </div>
        </TransitionGroup>

        <!-- skeleton placeholders -->
        <template v-if="isActive">
          <div
            v-for="skel in skeletonRows"
            :key="skel.key"
            :class="['skel-row', `skel-row--${skel.type}`]"
          >
            <div class="skel-icon shimmer" />
            <div class="skel-lines">
              <div class="skel-line skel-line--title shimmer" :style="{ width: skel.titleWidth }" />
              <div class="skel-line skel-line--desc shimmer" :style="{ width: skel.descWidth }" />
            </div>
          </div>
        </template>

        <!-- done empty state -->
        <div v-if="phase === 'done' && streamedNodes.length === 0" class="empty-hint">
          AI 未返回有效结构，请重试或检查 AI 配置
        </div>
      </div>
    </div>

    <!-- ── Phase: error ──────────────────────────────────────────── -->
    <div v-else class="error-body">
      <div class="error-icon">⚠️</div>
      <div class="error-msg">{{ errorMessage }}</div>
      <div class="error-hint">请检查 AI 密钥配置或网络连接后重试</div>
    </div>

    <!-- ── Footer ────────────────────────────────────────────────── -->
    <template #footer>
      <n-space justify="space-between" align="center">
        <template v-if="phase === 'idle'">
          <n-button @click="handleClose">取消</n-button>
          <n-button type="primary" @click="startGenerate">
            生成叙事骨架
          </n-button>
        </template>

        <template v-else-if="isActive">
          <n-button @click="abortGenerate" quaternary>取消生成</n-button>
          <span class="gen-counter">{{ streamedNodes.length }} 个节点已生成</span>
        </template>

        <template v-else-if="phase === 'done'">
          <n-button @click="startGenerate" :disabled="false">重新生成</n-button>
          <n-button
            type="primary"
            :loading="isConfirming"
            @click="confirmSave"
          >
            确认写入结构树
          </n-button>
        </template>

        <template v-else-if="phase === 'error'">
          <n-button @click="handleClose">关闭</n-button>
          <n-button type="primary" @click="startGenerate">重试</n-button>
        </template>
      </n-space>
    </template>
  </n-modal>
</template>

<script setup lang="ts">
import { ref, computed, nextTick, watch, onUnmounted } from 'vue'
import { useMessage } from 'naive-ui'
import {
  streamMacroPlan,
  planningApi,
  type MacroStreamNodeEvent,
  type MacroPartNode,
} from '../../api/planning'

const props = defineProps<{ show: boolean; novelId: string }>()
const emit = defineEmits<{
  'update:show': [v: boolean]
  confirmed: []
}>()

const show = computed({
  get: () => props.show,
  set: (v) => emit('update:show', v),
})

const message = useMessage()

// ─── State ────────────────────────────────────────────────────────────────
type Phase = 'idle' | 'generating' | 'streaming' | 'done' | 'error'
const phase = ref<Phase>('idle')
const statusMessage = ref('')
const progressPct = ref(0)
const errorMessage = ref('')
const isConfirming = ref(false)
const generationTime = ref(0)

interface StreamedNode extends MacroStreamNodeEvent {
  key: string
}
const streamedNodes = ref<StreamedNode[]>([])
const doneStructure = ref<MacroPartNode[]>([])
let abortCtrl: AbortController | null = null

const nodeScrollRef = ref<HTMLElement | null>(null)

// ─── Computed ─────────────────────────────────────────────────────────────
const isActive = computed(() => phase.value === 'generating' || phase.value === 'streaming')

const modalTitle = computed(() => {
  if (phase.value === 'idle') return '🎯 启动结构规划'
  if (isActive.value) return '🤖 AI 正在规划叙事骨架…'
  if (phase.value === 'done') return '✅ 叙事骨架已生成'
  if (phase.value === 'error') return '❌ 规划失败'
  return '🎯 启动结构规划'
})

const doneSummary = computed(() => {
  const parts = doneStructure.value
  const partCount = parts.length
  const volCount = parts.reduce((s, p) => s + (p.volumes?.length ?? 0), 0)
  const actCount = parts.reduce(
    (s, p) => s + (p.volumes ?? []).reduce((ss, v) => ss + ((v as Record<string, unknown>).acts as unknown[] ?? []).length, 0),
    0,
  )
  const t = generationTime.value > 0 ? ` · ${generationTime.value.toFixed(1)}s` : ''
  return `${partCount} 部 · ${volCount} 卷 · ${actCount} 幕${t}`
})

// ─── Skeleton rows ────────────────────────────────────────────────────────
const SKELETON_TEMPLATE: Array<{ type: 'part' | 'volume' | 'act'; titleWidth: string; descWidth: string }> = [
  { type: 'part',   titleWidth: '55%', descWidth: '75%' },
  { type: 'volume', titleWidth: '48%', descWidth: '68%' },
  { type: 'act',    titleWidth: '42%', descWidth: '60%' },
  { type: 'act',    titleWidth: '38%', descWidth: '55%' },
  { type: 'volume', titleWidth: '50%', descWidth: '70%' },
  { type: 'act',    titleWidth: '44%', descWidth: '62%' },
  { type: 'part',   titleWidth: '52%', descWidth: '72%' },
  { type: 'volume', titleWidth: '46%', descWidth: '66%' },
]

const skeletonRows = computed(() => {
  if (!isActive.value) return []
  const arrived = streamedNodes.value.length
  const slots = Math.max(SKELETON_TEMPLATE.length - arrived, 2)
  return SKELETON_TEMPLATE.slice(arrived % SKELETON_TEMPLATE.length).slice(0, slots).map((t, i) => ({
    ...t,
    key: `skel-${i}`,
  }))
})

// ─── Helpers ──────────────────────────────────────────────────────────────
function nodeIcon(type: string) {
  if (type === 'part') return '📚'
  if (type === 'volume') return '📖'
  return '🎬'
}

function makeNodeKey(node: MacroStreamNodeEvent): string {
  return `${node.type}-${node.part_index ?? 0}-${node.volume_index ?? 0}-${node.act_index ?? 0}`
}

// ─── Generate ─────────────────────────────────────────────────────────────
function startGenerate() {
  // reset
  abortCtrl?.abort()
  streamedNodes.value = []
  doneStructure.value = []
  statusMessage.value = '正在连接…'
  progressPct.value = 0
  errorMessage.value = ''
  phase.value = 'generating'
  isConfirming.value = false

  abortCtrl = streamMacroPlan(props.novelId, {
    onStatus(e) {
      statusMessage.value = e.message
      progressPct.value = e.percent ?? progressPct.value
      if (e.phase === 'streaming') {
        phase.value = 'streaming'
      }
    },
    onNode(e) {
      if (phase.value !== 'streaming') phase.value = 'streaming'
      streamedNodes.value.push({ ...e, key: makeNodeKey(e) })
      nextTick(() => {
        const el = nodeScrollRef.value
        if (el) el.scrollTop = el.scrollHeight
      })
    },
    onDone(e) {
      doneStructure.value = e.structure
      generationTime.value = e.generation_time ?? 0
      progressPct.value = 100
      phase.value = 'done'
      abortCtrl = null
    },
    onError(msg) {
      errorMessage.value = msg
      phase.value = 'error'
      abortCtrl = null
    },
  })
}

function abortGenerate() {
  abortCtrl?.abort()
  abortCtrl = null
  phase.value = 'idle'
  streamedNodes.value = []
}

// ─── Confirm ──────────────────────────────────────────────────────────────
async function confirmSave() {
  if (doneStructure.value.length === 0) {
    message.warning('结构为空，请重新生成')
    return
  }
  isConfirming.value = true
  try {
    await planningApi.confirmMacro(props.novelId, {
      structure: doneStructure.value as unknown as Record<string, unknown>[],
    })
    message.success('叙事骨架已写入结构树', { duration: 2500 })
    emit('confirmed')
    show.value = false
  } catch (e: unknown) {
    const err = e as { response?: { data?: { detail?: unknown } } }
    const detail = err?.response?.data?.detail
    if (detail && typeof detail === 'object' && (detail as Record<string, unknown>).error === 'MERGE_CONFLICT') {
      message.error('结构存在冲突，请先清空现有结构后重试')
    } else {
      message.error(typeof detail === 'string' ? detail : '写入失败，请重试')
    }
  } finally {
    isConfirming.value = false
  }
}

// ─── Misc ──────────────────────────────────────────────────────────────────
function handleClose() {
  if (isActive.value) return
  show.value = false
}

function resetState() {
  phase.value = 'idle'
  streamedNodes.value = []
  doneStructure.value = []
  statusMessage.value = ''
  progressPct.value = 0
  errorMessage.value = ''
  isConfirming.value = false
}

watch(
  () => props.show,
  (v) => { if (!v) abortCtrl?.abort() },
)

onUnmounted(() => { abortCtrl?.abort() })
</script>

<style scoped>
/* ── Modal size ──────────────────────────────────────────────────────────── */
:global(.macro-modal) {
  width: min(560px, 96vw);
  max-height: min(92vh, 820px);
}
:global(.macro-modal--stream) {
  width: min(680px, 96vw);
  max-height: min(92vh, 840px);
}

/* ── Header extras ───────────────────────────────────────────────────────── */
.mpm-subtitle {
  font-size: 12px;
  color: var(--app-text-secondary, #64748b);
}
.mpm-subtitle--live {
  display: flex;
  align-items: center;
  gap: 6px;
  color: #7c3aed;
  font-weight: 500;
}
.mpm-subtitle--done {
  color: #059669;
  font-weight: 500;
}
.live-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #7c3aed;
  flex-shrink: 0;
  animation: pulse-dot 1.2s ease-in-out infinite;
}
@keyframes pulse-dot {
  0%, 100% { opacity: 1; transform: scale(1); }
  50% { opacity: 0.45; transform: scale(0.75); }
}

/* ── Idle ────────────────────────────────────────────────────────────────── */
.idle-body { padding: 4px 0 10px; }
.idle-lead {
  margin: 0 0 16px;
  font-size: 14px;
  line-height: 1.65;
  color: var(--app-text-primary, #111827);
}
.idle-lead strong { font-weight: 600; }
.idle-card {
  padding: 12px 14px;
  border-radius: 10px;
  border: 1px solid var(--plotpilot-split-border, rgba(15, 23, 42, 0.12));
  background: var(--app-surface-subtle, #f8fafc);
}
.idle-card-title {
  font-size: 13px;
  font-weight: 600;
  margin-bottom: 8px;
  color: var(--app-text-primary, #111827);
}
.idle-list {
  margin: 0;
  padding-left: 1.15rem;
  font-size: 13px;
  line-height: 1.55;
  color: var(--app-text-secondary, #334155);
}
.idle-list li + li { margin-top: 4px; }

/* ── Stream body ─────────────────────────────────────────────────────────── */
.stream-body {
  display: flex;
  flex-direction: column;
  gap: 0;
  min-height: 360px;
}

/* progress bar */
.prog-track {
  height: 3px;
  background: var(--plotpilot-split-border, rgba(15,23,42,.1));
  border-radius: 2px;
  margin-bottom: 14px;
  overflow: hidden;
}
.prog-fill {
  height: 100%;
  background: linear-gradient(90deg, #7c3aed, #2563eb);
  border-radius: 2px;
  transition: width 0.6s ease;
}

/* node scroll area */
.node-scroll {
  flex: 1;
  overflow-y: auto;
  padding-right: 4px;
  max-height: 560px;
  scrollbar-width: thin;
}
.node-list { display: flex; flex-direction: column; }

/* ── Node items ──────────────────────────────────────────────────────────── */
.node-item {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 9px 12px;
  border-radius: 8px;
  margin-bottom: 5px;
  transition: background 0.2s;
}
.node-item--part {
  border-left: 3px solid #7c3aed;
  background: linear-gradient(135deg, rgba(124,58,237,.05), rgba(124,58,237,.01));
}
.node-item--volume {
  margin-left: 18px;
  border-left: 2px solid #2563eb;
  background: rgba(37,99,235,.03);
}
.node-item--act {
  margin-left: 34px;
  border-left: 2px solid #10b981;
  background: rgba(16,185,129,.02);
  padding: 6px 10px;
}
.node-icon {
  font-size: 16px;
  flex-shrink: 0;
  margin-top: 1px;
  line-height: 1;
}
.node-item--act .node-icon { font-size: 14px; }
.node-content { flex: 1; min-width: 0; }
.node-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--app-text-primary, #111827);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  line-height: 1.4;
}
.node-item--volume .node-title { font-size: 13.5px; }
.node-item--act .node-title { font-size: 13px; font-weight: 500; }
.node-desc {
  font-size: 12px;
  color: var(--app-text-secondary, #64748b);
  margin-top: 2px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  line-height: 1.45;
}
.node-badge {
  flex-shrink: 0;
  font-size: 11px;
  font-weight: 500;
  color: #059669;
  background: rgba(16,185,129,.1);
  border-radius: 10px;
  padding: 2px 7px;
  white-space: nowrap;
  margin-top: 2px;
}

/* ── TransitionGroup ────────────────────────────────────────────────────── */
.node-arrive-enter-active {
  transition: opacity 0.3s ease, transform 0.35s cubic-bezier(0.34, 1.3, 0.64, 1);
}
.node-arrive-enter-from {
  opacity: 0;
  transform: translateX(-14px);
}

/* ── Skeleton ────────────────────────────────────────────────────────────── */
.skel-row {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 9px 12px;
  border-radius: 8px;
  margin-bottom: 5px;
  border-left: 3px solid rgba(124,58,237,.15);
}
.skel-row--volume {
  margin-left: 18px;
  border-left: 2px solid rgba(37,99,235,.15);
}
.skel-row--act {
  margin-left: 34px;
  border-left: 2px solid rgba(16,185,129,.15);
  padding: 6px 10px;
}
.skel-icon {
  width: 16px;
  height: 16px;
  border-radius: 4px;
  flex-shrink: 0;
  margin-top: 1px;
}
.skel-lines { flex: 1; display: flex; flex-direction: column; gap: 5px; padding-top: 1px; }
.skel-line {
  height: 12px;
  border-radius: 4px;
}
.skel-line--title { height: 14px; }

/* shimmer */
@keyframes shimmer {
  0% { background-position: -400px 0; }
  100% { background-position: 400px 0; }
}
.shimmer {
  background: linear-gradient(
    90deg,
    rgba(0,0,0,.04) 25%,
    rgba(0,0,0,.09) 37%,
    rgba(0,0,0,.04) 63%
  );
  background-size: 800px 100%;
  animation: shimmer 1.6s ease-in-out infinite;
}

/* ── Error ───────────────────────────────────────────────────────────────── */
.error-body {
  padding: 28px 0;
  text-align: center;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
}
.error-icon { font-size: 40px; }
.error-msg { font-size: 15px; font-weight: 600; color: var(--app-text-primary, #111827); }
.error-hint { font-size: 13px; color: var(--app-text-secondary, #64748b); }

/* ── Footer extras ───────────────────────────────────────────────────────── */
.gen-counter {
  font-size: 12px;
  color: var(--app-text-secondary, #64748b);
}
.empty-hint {
  padding: 40px 0;
  text-align: center;
  font-size: 13px;
  color: var(--app-text-secondary, #64748b);
}
</style>
