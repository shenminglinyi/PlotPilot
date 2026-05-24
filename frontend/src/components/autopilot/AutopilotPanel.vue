<template>
  <div class="autopilot-panel">
    <section class="ap-hero" aria-label="运行状态">
      <div class="ap-hero__top">
        <div class="ap-hero__status">
          <span class="ap-dot" :class="dotClass" aria-hidden="true" />
          <span class="ap-hero__eyebrow">守护进程</span>
          <span class="ap-stage-tag" :class="stageTagClass">
            <template v-if="stageTransitioning">
              <span class="skeleton-inline skeleton-pulse" />
              <span class="stage-transition-label">
                <span class="stage-text">{{ stagePresentation.text }}</span>
                <span v-if="stagePresentation.live" class="ap-stage-live" aria-label="实时同步" />
              </span>
            </template>
            <template v-else>
              <span class="stage-text">{{ stagePresentation.text }}</span>
              <span v-if="stagePresentation.live" class="ap-stage-live" aria-label="实时同步" />
            </template>
          </span>
          <span
            v-if="isWriting"
            class="ap-sse-pill"
            :class="sseConnected ? 'is-on' : 'is-off'"
          >
            {{ sseConnected ? '流式已连接' : (sseReconnecting ? '重连中' : '流式未连接') }}
          </span>
        </div>
        <div class="ap-hero__pct" :class="{ 'is-active': isRunning }">
          <span class="ap-hero__pct-value">{{ progressPctDisplay }}</span>
          <span class="ap-hero__pct-label">全书进度</span>
        </div>
      </div>
      <n-progress
        class="ap-hero__bar"
        type="line"
        :percentage="progressPct"
        :color="progressColor"
        :show-indicator="false"
        :height="8"
        :border-radius="4"
      />
      <p v-if="status" class="ap-hero__plan-line">
        目标篇幅（与首页一致）
        <strong>{{ formatWords(planTotalWordsHint) }}</strong> 字 ·
        <strong>{{ status.target_chapters ?? '—' }}</strong> 章 ×
        <strong>{{ status.target_words_per_chapter ?? 2500 }}</strong> 字/章
        <n-button
          text
          type="primary"
          size="tiny"
          class="ap-hero__plan-toggle"
          @click="planExpanded = !planExpanded"
        >
          {{ planExpanded ? '收起说明' : '说明' }}
        </n-button>
      </p>
      <p v-if="status && planExpanded" class="ap-plan-detail">
        写满目标章即停；节拍按每章字数拆分。流式字数可能暂时高于章目标，节拍末会收束再落稿。
        进度条、幕/章/节拍与阶段标签可能短暂不同步，以守护进程状态为准。
      </p>
    </section>

    <n-alert
      v-if="statusConnectivityFailures >= 2 && !statusPollDisabled"
      type="warning"
      :show-icon="true"
      class="ap-inline-alert"
    >
      无法连接写作后端（开发约定 <code>127.0.0.1:8005</code>）。已自动拉长轮询间隔，请启动 API 后再试。
    </n-alert>

    <section v-if="status" class="ap-kpi-grid" aria-label="关键指标">
      <article class="ap-kpi">
        <span class="ap-kpi__label">完稿 / 书稿 / 目标</span>
        <span class="ap-kpi__value">
          {{ status.completed_chapters || 0 }}
          <span class="ap-kpi__sep">/</span>
          {{ status.manuscript_chapters ?? status.completed_chapters ?? 0 }}
          <span class="ap-kpi__sep">/</span>
          {{ status.target_chapters || '—' }}
        </span>
      </article>
      <article class="ap-kpi">
        <span class="ap-kpi__label">总字数</span>
        <span class="ap-kpi__value">{{ formatWords(status.total_words) }}</span>
      </article>
      <article class="ap-kpi ap-kpi--location">
        <span class="ap-kpi__label">当前位置</span>
        <span class="ap-location">
          <span class="ap-location__meta">第 {{ (status.current_act || 0) + 1 }} 幕</span>
          <span class="ap-location__title">{{ status.current_act_title || '当前幕' }}</span>
          <!-- 规划阶段：显示阶段标签 -->
          <span class="ap-location__trail">
            <span v-if="!isWriting && status.current_stage === 'act_planning'" class="ap-location__chip">
              幕级规划
            </span>
            <span v-else-if="!isWriting && status.current_stage === 'macro_planning'" class="ap-location__chip">
              宏观规划
            </span>
            <!-- 撰写阶段：只有 writing_substep 激活后才显示章/节拍，避免展示上一章的残留状态 -->
            <span v-if="isWriting && status.current_chapter_number != null && status.writing_substep" class="ap-location__chip ap-location__chip--strong">
              第 {{ status.current_chapter_number }} 章
            </span>
            <span v-if="isWriting && beatLabelActive" class="ap-location__chip">{{ beatLabel }}</span>
          </span>
        </span>
      </article>
      <article class="ap-kpi">
        <span class="ap-kpi__label">上章张力</span>
        <span class="ap-kpi__value" :style="{ color: tensionColor }">{{ tensionLabel }}</span>
      </article>
    </section>

    <section
      v-if="status?.current_act_description || (status?.current_act_title && !status?.current_act_description)"
      class="ap-narrative"
      aria-label="当前幕叙事"
    >
      <span class="ap-narrative__label">当前幕</span>
      <p v-if="status.current_act_description" class="ap-narrative__body">
        <span v-if="status.current_act_title" class="ap-narrative__title">{{ status.current_act_title }}</span>
        {{ status.current_act_description }}
      </p>
      <p v-else class="ap-narrative__body ap-narrative__body--muted">暂无幕描述</p>
    </section>

    <section
      v-if="telemetryVisible"
      class="ap-telemetry"
      aria-label="实时子步骤"
    >
      <header class="ap-telemetry__head">
        <span class="ap-telemetry__title">实时管线</span>
        <span class="substep-badge" :class="substepBadgeClass">{{ writingSubstepDetail.substepLabel }}</span>
      </header>
      <div class="ap-telemetry__grid">
        <div v-if="writingSubstepDetail.totalBeats > 0" class="ap-telemetry__item">
          <span class="ap-telemetry__key">节拍</span>
          <span class="ap-telemetry__val">
            {{ writingSubstepDetail.beatIndex }}/{{ writingSubstepDetail.totalBeats }}
          </span>
          <div class="ap-meter">
            <div
              class="ap-meter__fill ap-meter__fill--beat"
              :style="{ width: writingSubstepDetail.beatPct + '%' }"
            />
          </div>
        </div>
        <div v-if="writingSubstepDetail.accumulatedWords > 0" class="ap-telemetry__item">
          <span class="ap-telemetry__key">本章字数</span>
          <span class="ap-telemetry__val">
            {{ writingSubstepDetail.accumulatedWords }}/{{ writingSubstepDetail.chapterTargetWords }}
            <span class="pct-tag">{{ writingSubstepDetail.wordPct }}%</span>
          </span>
          <div class="ap-meter">
            <div
              class="ap-meter__fill ap-meter__fill--word"
              :style="{ width: Math.min(100, writingSubstepDetail.wordPct) + '%' }"
            />
          </div>
        </div>
        <div v-if="writingSubstepDetail.beatFocus" class="ap-telemetry__item ap-telemetry__item--wide">
          <span class="ap-telemetry__key">焦点</span>
          <span class="ap-telemetry__val ap-telemetry__val--focus">{{ writingSubstepDetail.beatFocus }}</span>
        </div>
        <div v-if="writingSubstepDetail.contextTokens > 0" class="ap-telemetry__item">
          <span class="ap-telemetry__key">上下文</span>
          <span class="ap-telemetry__val">{{ writingSubstepDetail.contextTokens }} tokens</span>
        </div>
      </div>
    </section>

    <StoryPipelineObservability
      v-if="storyPipelineObsVisible"
      :status="status"
      :aftermath-only="storyPipelineAftermathOnly"
    />

    <AuditPipelineObservability
      v-if="auditPipelineObsVisible"
      :status="status"
    />

    <!-- 单本挂起 / 失败计数过高 -->
    <n-alert v-if="needsRecovery" type="error" :show-icon="true" class="ap-inline-alert">
      <div class="recovery-hint">
        <p v-if="status?.autopilot_status === 'error'">
          本书已因<strong>连续失败</strong>被标为<strong>异常挂起</strong>。
        </p>
        <p v-else>
          已连续失败 <strong>{{ status?.consecutive_error_count || 0 }}</strong> 次（达到 3 次会挂起）。
        </p>
        <p class="recovery-sub">
          全局 LLM 熔断在守护进程内，无法在此直接展示。下方按钮与「监控大盘 → 熔断保护 → 重置」相同。
        </p>
        <n-button
          size="small"
          type="primary"
          secondary
          :loading="toggling"
          @click="clearCircuitBreaker"
        >
          解除挂起并清零计数
        </n-button>
      </div>
    </n-alert>

    <!-- 审阅等待 -->
    <n-alert v-if="needsReview" type="warning" :show-icon="true" class="ap-inline-alert">
      <div class="ap-review-alert">
        <span>
          <strong>待审阅确认</strong>：请在侧栏查看刚生成的大纲或结构树，核对无误后点击按钮继续。
        </span>
        <n-button type="warning" size="small" :loading="toggling" @click="resume">
          确认大纲，继续写作
        </n-button>
      </div>
    </n-alert>

    <!-- 仅写作阶段拉章节流；审计/规划时服务端会关流，避免无意义重连 -->
    <AutopilotWritingStream
      v-if="isWriting && props.renderLivePreview !== false"
      :writing-content="writingContent"
      :writing-chapter-number="writingChapterNumber"
      :writing-beat-index="writingBeatIndex"
      :writing-substep="status?.writing_substep"
      :writing-substep-label="status?.writing_substep_label"
      :total-beats="status?.total_beats"
      :accumulated-words="status?.accumulated_words"
      :chapter-target-words="status?.chapter_target_words"
      :beat-focus="status?.beat_focus"
      :context-tokens="status?.context_tokens"
      :runner-stage-label="stageLabel"
      :status-chapter-number="status?.current_chapter_number ?? null"
      :is-writing-phase="isWriting"
    />

    <!-- 操作按钮 -->
    <n-space justify="end" size="small">
      <n-button v-if="needsReview" type="warning" ghost size="small" :loading="toggling" @click="resume">
        再次确认 · 继续
      </n-button>
      <n-button v-if="!isRunning && !needsReview && !needsRecovery" type="primary" size="small" :loading="toggling" @click="openStartModal">
        🚀 启动全托管
      </n-button>
      <n-button v-if="isRunning" type="error" ghost size="small" :loading="toggling" @click="stop">
        ⏹ 停止
      </n-button>
      <!-- 🔥 error 状态下显示强制停止按钮（解除挂起 + 停止） -->
      <n-button v-if="needsRecovery && !isRunning" type="error" size="small" :loading="toggling" @click="forceStopFromError">
        ⏹ 强制停止
      </n-button>
    </n-space>

    <!-- 启动配置弹窗 -->
    <n-modal v-model:show="showStartModal" title="启动全托管" preset="dialog" positive-text="启动" @positive-click="start">
      <n-space vertical :size="12" style="width: 100%">
        <n-alert type="success" :show-icon="true" style="font-size: 12px">
          <strong>自动托管</strong>：守护进程已在后端自动启动，配置好参数后点击"启动"即可开始自动写作。
        </n-alert>
        <n-form>
          <n-form-item label="目标章数">
            <n-input-number
              v-model:value="startConfig.target_chapters"
              :min="1"
              :max="9999"
              :step="10"
              style="width: 100%"
              @update:value="updateProtectionLimit"
            />
          </n-form-item>
          <n-form-item label="每章目标字数">
            <n-input-number
              v-model:value="startConfig.target_words_per_chapter"
              :min="500"
              :max="20000"
              :step="500"
              style="width: 100%"
            />
          </n-form-item>
          <n-form-item label="保护上限（章节数，防止意外消耗）">
            <n-input-number
              v-model:value="startConfig.max_auto_chapters"
              :min="startConfig.target_chapters"
              :max="9999"
              :step="10"
              style="width: 100%"
            />
          </n-form-item>

          <n-form-item label="全自动模式">
            <n-space align="center" justify="space-between" style="width: 100%">
              <n-switch
                v-model:value="startConfig.auto_approve_mode"
                :round="false"
              >
                <template #checked>开启</template>
                <template #unchecked>关闭</template>
              </n-switch>
              <n-text depth="3" style="font-size: 12px">
                跳过所有人工审阅
              </n-text>
            </n-space>
          </n-form-item>

          <n-alert type="info" :show-icon="false" style="font-size: 11px; margin-top: -8px">
            <template v-if="startConfig.auto_approve_mode">
              <strong>全自动模式已开启</strong>：系统将跳过所有审阅环节，自动运行直到写完。
            </template>
            <template v-else>
              达到 <strong>{{ startConfig.target_chapters }} 章</strong> 目标时自动完成全书。
            </template>
          </n-alert>
        </n-form>
      </n-space>
    </n-modal>
  </div>
</template>

<script setup>
import { ref, computed, onUnmounted, watch } from 'vue'
import { useMessage } from 'naive-ui'
import AutopilotWritingStream from './AutopilotWritingStream.vue'
import StoryPipelineObservability from './StoryPipelineObservability.vue'
import AuditPipelineObservability from './AuditPipelineObservability.vue'
import { resolveHttpUrl, subscribeChapterStream } from '../../api/config'
import { buildAutopilotStagePresentation } from '../../constants/autopilotStagePresentation'

const props = defineProps({
  novelId: String,
  renderLivePreview: { type: Boolean, default: true },
})
const emit = defineEmits([
  'status-change',
  'chapter-content-update',
  'chapter-start',
  'chapter-chunk',
  'desk-refresh',
  'beats-planned',
])
const message = useMessage()

const status = ref(null)
const toggling = ref(false)
const planExpanded = ref(false)
const showStartModal = ref(false)
const startConfig = ref({
  target_chapters: 100,
  target_words_per_chapter: 2500,
  max_auto_chapters: 120,
  auto_approve_mode: false
})

// 🔧 新增：SSE 连接状态
const sseConnected = ref(false)
const sseReconnecting = ref(false)
let chapterStreamCtrl = null
let reconnectTimer = null
let reconnectAttempts = 0
/** 递增后忽略旧连接的 onDisconnected / onStreamEnd，避免 stop→abort 与重连竞态 */
let chapterStreamSession = 0
let lastChapterStreamStartMs = 0
const MAX_RECONNECT_ATTEMPTS = 5
const MIN_CHAPTER_STREAM_RESTART_MS = 3000

// 写作内容状态
const writingContent = ref('')
const writingChapterNumber = ref(0)
const writingBeatIndex = ref(0)
let chapterChunkEmitTimer = null
let pendingChapterChunk = null
const CHAPTER_CHUNK_EMIT_INTERVAL_MS = 120

function flushChapterChunkEmit() {
  if (chapterChunkEmitTimer) {
    clearTimeout(chapterChunkEmitTimer)
    chapterChunkEmitTimer = null
  }
  if (!pendingChapterChunk) return
  emit('chapter-chunk', pendingChapterChunk)
  pendingChapterChunk = null
}

function emitChapterChunkThrottled(payload, immediate = false) {
  pendingChapterChunk = payload
  if (immediate) {
    flushChapterChunkEmit()
    return
  }
  if (chapterChunkEmitTimer) return
  chapterChunkEmitTimer = setTimeout(flushChapterChunkEmit, CHAPTER_CHUNK_EMIT_INTERVAL_MS)
}

// 🔥 新增：操作节流保护——防止用户快速连续点击导致请求堆积
// toggling 为 true 时按钮已禁用，但需要额外保护异步操作的竞态
let lastToggleTime = 0
const TOGGLE_THROTTLE_MS = 1000  // 1 秒内不允许重复操作

function isToggleThrottled() {
  const now = Date.now()
  if (now - lastToggleTime < TOGGLE_THROTTLE_MS) {
    return true
  }
  lastToggleTime = now
  return false
}

// 状态轮询
let statusPollTimer = null
const statusPollDisabled = ref(false)
// /status：新请求开始前取消上一轮，减轻后端堆积；序号用于忽略已被替代的 AbortError
let statusFetchSeq = 0
let statusLastAbort = null
/** 连续无法拉取 /status（网络拒绝/超时）时倍增轮询间隔 */
const statusConnectivityFailures = ref(0)
let lastStatusPollIntervalMs = -1

// 计算属性
const isRunning = computed(() => status.value?.autopilot_status === 'running')
// 是否与人工审阅闸门对齐（须点 resume）。
// 「reviewing」为兼容舞台值；主路径 paused_for_review。避免仅展示「待审阅」却无按钮。
function statusNeedsManualReview(s) {
  if (!s) return false
  if (s.needs_review === true) return true
  const stage = String(s.current_stage ?? '').trim().toLowerCase()
  return stage === 'paused_for_review' || stage === 'reviewing'
}

const needsReview = computed(() => statusNeedsManualReview(status.value))
// 🔥 只有运行中且阶段为 writing 时才是真正的"撰写中"
const isWriting = computed(() =>
  status.value?.autopilot_status === 'running' && status.value?.current_stage === 'writing'
)

const storyPipelineWaveIndex = computed(() => {
  const ix = Number(status.value?.story_pipeline_wave_index)
  return Number.isFinite(ix) ? ix : 0
})

const storyPipelineAftermathOnly = computed(() =>
  isWriting.value && storyPipelineWaveIndex.value === 8
)

const telemetryVisible = computed(() =>
  isRunning.value &&
  Boolean(writingSubstepDetail.value) &&
  !storyPipelineAftermathOnly.value &&
  !auditPipelineObsVisible.value
)

/** StoryPipeline（新内核写作）有可观测字段时展示十步管线图 */
const storyPipelineObsVisible = computed(() => {
  if (auditPipelineObsVisible.value) return false
  if (!isWriting.value || !status.value) return false
  const ix = storyPipelineWaveIndex.value
  return Number.isFinite(ix) && ix >= 1 && ix <= 10
})

const auditPipelineObsVisible = computed(() => {
  if (!isRunning.value || !status.value) return false
  const stage = String(status.value.current_stage || '')
  const sub = String(status.value.writing_substep || '')
  const audit = String(status.value.audit_progress || '')
  return (
    stage === 'auditing' ||
    sub === 'pipeline_done' ||
    sub.startsWith('audit_') ||
    audit === 'voice_check' ||
    audit === 'aftermath_pipeline' ||
    audit === 'tension_scoring'
  )
})
const needsRecovery = computed(
  () =>
    status.value?.autopilot_status === 'error' ||
    (status.value?.consecutive_error_count || 0) >= 3
)
// 🔥 守护进程存活状态判断
// 核心原则：如果 /status 接口成功返回了共享内存数据（_from_shared_memory），
// 说明守护进程在运行（否则共享内存不会有数据），不应该仅靠心跳误判。
// 心跳丢失只应在"完全没有共享内存数据"时才触发降级显示。
const daemonAlive = computed(() => {
  // 🔥 如果返回了共享内存实时数据，说明守护进程一定在运行
  // （共享内存是守护进程写入的，有数据 = 守护进程在工作）
  if (status.value?._from_shared_memory) return true

  // 🔥 如果 API 返回了降级状态（DB忙），但有守护进程心跳，说明后端仍在工作
  // 只是 DB 暂时无法读取统计信息，不应显示"后端处理中"
  if (status.value?._degraded && status.value?.daemon_alive) return true

  // 没有共享内存数据时，用心跳判断
  if (status.value?.daemon_alive) return true
  if (status.value?.daemon_heartbeat_at) {
    const age = (Date.now() / 1000) - status.value.daemon_heartbeat_at
    // 🔥 放宽心跳超时：30→60秒，给守护进程更多宽容
    // 场景：LLM调用可能持续30-60秒，期间心跳更新间隔较长
    return age < 60
  }
  // 🔥 如果 autopilot_status=running 但没有心跳也没有共享内存，
  // 可能是首次轮询或守护进程正在启动中，给更长的宽容期
  if (status.value?.autopilot_status === 'running') return true
  return false
})

const targetChapters = computed(() => status.value?.target_chapters || 100)

const planTotalWordsHint = computed(() => {
  const s = status.value
  if (!s) return 0
  if (s.target_plan_total_words != null && s.target_plan_total_words > 0) {
    return s.target_plan_total_words
  }
  return (s.target_chapters ?? 0) * (s.target_words_per_chapter ?? 2500)
})

const progressPct = computed(() => {
  const s = status.value
  if (!s) return 0
  const target = Number(s.target_chapters || 0)
  const completed = Number(s.completed_chapters || 0)
  const manuscript = Number(s.manuscript_chapters ?? completed)
  const currentAuto = Number(s.current_auto_chapters || 0)
  const bestCount = Math.max(completed, manuscript, currentAuto)
  if (target > 0 && bestCount > 0) {
    return Math.min(100, Math.round((bestCount / target) * 1000) / 10)
  }
  const serverPct = Number(s.progress_pct_manuscript ?? s.progress_pct ?? 0)
  return Number.isFinite(serverPct) ? serverPct : 0
})

const progressPctDisplay = computed(() => {
  const n = Number(progressPct.value)
  if (!Number.isFinite(n)) return '0%'
  return `${n < 10 ? n.toFixed(1) : Math.round(n * 10) / 10}%`
})

const progressColor = computed(() => {
  if (needsRecovery.value) return 'var(--color-danger, #ef4444)'
  if (needsReview.value) return 'var(--color-warning, #f59e0b)'
  return 'var(--color-success, #22c55e)'
})

const dotClass = computed(() => ({
  'dot-running': isRunning.value && !needsReview.value,
  'dot-review': needsReview.value,
  'dot-error': status.value?.autopilot_status === 'error',
  'dot-stopped': !isRunning.value && !needsReview.value,
}))

const stagePresentation = computed(() =>
  buildAutopilotStagePresentation({
    current_stage: status.value?.current_stage,
    autopilot_status: status.value?.autopilot_status,
    writing_substep: status.value?.writing_substep,
    writing_substep_label: status.value?.writing_substep_label,
    _from_shared_memory: status.value?._from_shared_memory,
    _degraded: status.value?._degraded,
    audit_progress: status.value?.audit_progress,
    isRunning: isRunning.value,
    daemonAlive: daemonAlive.value,
    current_act: status.value?.current_act ?? null,
  })
)

const stageLabel = computed(() => stagePresentation.value.text)

// 🔥 阶段变更过渡态：检测 current_stage 变化时显示骨架 loading
const prevStage = ref(null)
const stageTransitioning = ref(false)
let stageTransitionTimer = null

watch(
  () => status.value?.current_stage,
  (newStage, oldStage) => {
    if (oldStage && newStage && oldStage !== newStage) {
      // 阶段变了，触发骨架 loading 过渡
      stageTransitioning.value = true
      if (stageTransitionTimer) clearTimeout(stageTransitionTimer)
      stageTransitionTimer = setTimeout(() => {
        stageTransitioning.value = false
      }, 2000) // 2 秒后自动消失
    }
    prevStage.value = newStage
  }
)

const stageTagClass = computed(() => {
  const sem = stagePresentation.value.semantic
  const run = isRunning.value && !needsReview.value
  return {
    'tag-review': needsReview.value,
    'tag-idle': !isRunning.value && !needsReview.value,
    'tag-transitioning': stageTransitioning.value,
    'tag-sem-plan': run && sem === 'plan',
    'tag-sem-write': run && sem === 'write',
    'tag-sem-audit': run && sem === 'audit',
    'tag-sem-sync': run && sem === 'sync',
    'tag-sem-review': run && sem === 'review',
    'tag-sem-idle': run && sem === 'idle',
    'tag-sem-daemon_wait': run && sem === 'daemon_wait',
  }
})

const beatLabel = computed(() => {
  if (!isWriting.value) return ''
  const b = status.value?.current_beat_index ?? 0
  return `节拍 ${Number(b) + 1}`
})

/** 只在管线实际推进节拍时显示节拍号，避免初始启动时展示上一章的残留 beat_index */
const beatLabelActive = computed(() => {
  const substep = status.value?.writing_substep || ''
  return substep === 'llm_calling' || substep === 'beat_magnification'
})

/** ★ V9 细化状态：写作/审计/规划子步骤详情 */
const writingSubstepDetail = computed(() => {
  if (!status.value) return null
  const s = status.value
  const substep = String(s.writing_substep || '')
  const substepLabel = String(s.writing_substep_label || '')
  if (!substep && !substepLabel) return null

  const totalBeats = Number(s.total_beats || 0)
  const beatIndex = Number(s.current_beat_index ?? 0) + 1
  const beatPct = totalBeats > 0 ? Math.min(100, Math.round(beatIndex / totalBeats * 100)) : 0

  const accumulatedWords = Number(s.accumulated_words || 0)
  const chapterTargetWords = Number(s.chapter_target_words || 0)
  const wordPct = chapterTargetWords > 0 && accumulatedWords > 0
    ? Math.min(100, Math.round(accumulatedWords / chapterTargetWords * 100))
    : 0

  return {
    substep,
    substepLabel: substepLabel || substep,
    totalBeats,
    beatIndex,
    beatPct,
    accumulatedWords,
    chapterTargetWords,
    wordPct,
    beatFocus: String(s.beat_focus || ''),
    contextTokens: Number(s.context_tokens || 0),
  }
})

/** 子步骤徽章配色 */
const substepBadgeClass = computed(() => {
  const sub = status.value?.writing_substep || ''
  // 写作阶段
  if (sub === 'llm_calling') return 'substep-active'
  if (sub === 'outline_planning') return 'substep-plan'
  if (sub === 'context_assembly' || sub === 'beat_magnification' || sub === 'chapter_found') return 'substep-prepare'
  if (sub === 'soft_landing' || sub === 'persisting' || sub === 'continuity_check' || sub === 'chapter_persist') return 'substep-finish'
  // 审计阶段
  if (sub === 'audit_voice_check') return 'substep-audit'
  if (sub === 'audit_aftermath') return 'substep-audit'
  if (sub === 'audit_tension') return 'substep-audit'
  // 规划阶段
  if (sub === 'macro_planning') return 'substep-plan'
  if (sub === 'act_planning') return 'substep-plan'
  return ''
})

const tensionLabel = computed(() => {
  // 张力值范围是 0-100，转换为 0-10 显示
  const rawT = status.value?.last_chapter_tension || 0
  if (rawT < 0) return `⏳ 未评估`
  const t = Math.round(rawT / 10) // 0-100 转 0-10
  if (t >= 8) return `🔥 高潮 (${t}/10)`
  if (t >= 6) return `⚡ 冲突 (${t}/10)`
  if (t >= 4) return `🌊 暗流 (${t}/10)`
  return `💤 平缓 (${t}/10)`
})

const tensionColor = computed(() => {
  // 张力值范围是 0-100，转换为 0-10 判断
  const rawT = status.value?.last_chapter_tension || 0
  if (rawT < 0) return '#999'
  const t = Math.round(rawT / 10)
  return t >= 8 ? '#d03050' : t >= 6 ? '#f0a020' : t >= 4 ? '#18a058' : '#36ad6a'
})

// 格式化
function formatWords(n) {
  if (!n) return '0'
  return n >= 10000 ? `${(n / 10000).toFixed(1)}万` : String(n)
}

// API 调用
const autopilotApiRoot = () => `/api/v1/autopilot/${props.novelId}`

// 🔥 优化：缩短超时从 25s → 10s，减少前端等待时间
// 后端 /status 已改为纯共享内存读取（纳秒级响应），10s 已非常宽裕
// 如果 10s 还没返回，说明后端事件循环被阻塞，继续等也没意义
const STATUS_FETCH_TIMEOUT_MS = 10_000

// 🔥 新增：请求去重——如果上一次 fetchStatus 还没返回，不重复发起
let statusFetchInFlight = false

async function fetchStatus() {
  // 请求去重：上一次还在飞就不重复发
  if (statusFetchInFlight) return

  statusFetchSeq += 1
  const seq = statusFetchSeq
  if (statusLastAbort) {
    statusLastAbort.abort()
  }
  const ac = new AbortController()
  statusLastAbort = ac
  const t = window.setTimeout(() => ac.abort(), STATUS_FETCH_TIMEOUT_MS)
  statusFetchInFlight = true
  try {
    const res = await fetch(resolveHttpUrl(`${autopilotApiRoot()}/status`), {
      signal: ac.signal,
    })
    if (res.status === 404) {
      clearStatusPoll()
      status.value = null
      statusPollDisabled.value = true
      statusConnectivityFailures.value = 0
      return
    }
    if (res.ok) {
      statusConnectivityFailures.value = 0
      const body = await res.json()
      status.value = body
      emit('status-change', body)

      // 🔍 调试：审计阶段进度日志
      if (body.current_stage === 'auditing') {
        console.log(
          '[AutopilotPanel] 审计进度:',
          body.audit_progress || '(未知)',
          '| 相似度:', body.last_chapter_audit?.similarity_score ?? 'N/A',
          '| 张力:', body.last_chapter_tension ?? 'N/A'
        )
      }

      // 写作阶段流掉线且已放弃重连：由轮询在冷却后再试（勿在此处清零 reconnectAttempts，否则会死循环）
      if (
        shouldMaintainChapterStream(body) &&
        !chapterStreamCtrl &&
        !sseReconnecting.value &&
        reconnectAttempts >= MAX_RECONNECT_ATTEMPTS &&
        Date.now() - lastChapterStreamStartMs >= MIN_CHAPTER_STREAM_RESTART_MS * 4
      ) {
        reconnectAttempts = MAX_RECONNECT_ATTEMPTS - 1
        scheduleChapterStreamReconnect(0)
      }
    }
  } catch (err) {
    if (seq !== statusFetchSeq) {
      return
    }
    statusConnectivityFailures.value += 1
    if (err instanceof Error && err.name === 'AbortError') {
      console.warn('[AutopilotPanel] fetchStatus 超时，可能后端繁忙或未启动')
    } else {
      console.error('[AutopilotPanel] fetchStatus error:', err)
    }
  } finally {
    window.clearTimeout(t)
    statusFetchInFlight = false
    maybeRestartStatusPollTimer()
  }
}

function clearStatusPoll() {
  if (statusPollTimer) {
    clearInterval(statusPollTimer)
    statusPollTimer = null
  }
  lastStatusPollIntervalMs = -1
}

/** 轮询间隔变化时（如后端断连退避）重置 timer，避免固定 3～5s 刷满 Vite 代理日志 */
function maybeRestartStatusPollTimer() {
  if (statusPollDisabled.value) return
  const ms = getAdaptivePollInterval()
  if (statusPollTimer != null && ms === lastStatusPollIntervalMs) {
    return
  }
  lastStatusPollIntervalMs = ms
  if (statusPollTimer) {
    clearInterval(statusPollTimer)
    statusPollTimer = null
  }
  statusPollTimer = setInterval(() => fetchStatus(), ms)
}

/** 章节正文 SSE 仅在「运行中 + 写作阶段」需要；审计/规划时服务端会关流，不应重连 */
function shouldMaintainChapterStream(body = status.value) {
  if (!body || statusPollDisabled.value) return false
  if (body.autopilot_status !== 'running') return false
  if (statusNeedsManualReview(body)) return false
  return body.current_stage === 'writing'
}

function wantsChapterStream() {
  return shouldMaintainChapterStream()
}

function scheduleChapterStreamReconnect(delayMs) {
  if (reconnectTimer) {
    clearTimeout(reconnectTimer)
    reconnectTimer = null
  }
  if (!shouldMaintainChapterStream()) {
    sseReconnecting.value = false
    return
  }
  if (reconnectAttempts >= MAX_RECONNECT_ATTEMPTS) {
    sseReconnecting.value = false
    return
  }
  const delay = Math.max(delayMs, MIN_CHAPTER_STREAM_RESTART_MS)
  reconnectAttempts++
  sseReconnecting.value = true
  console.log(
    `[AutopilotPanel] SSE 断开，${delay / 1000}s 后重连 (${reconnectAttempts}/${MAX_RECONNECT_ATTEMPTS})`,
  )
  reconnectTimer = setTimeout(() => {
    reconnectTimer = null
    void fetchStatus().then(() => {
      if (!shouldMaintainChapterStream()) {
        sseReconnecting.value = false
        reconnectAttempts = 0
        return
      }
      if (!chapterStreamCtrl && !sseConnected.value) {
        startChapterStream()
      }
    })
  }, delay)
}

function startChapterStream() {
  if (!shouldMaintainChapterStream()) {
    stopChapterStream()
    return
  }

  const now = Date.now()
  if (now - lastChapterStreamStartMs < MIN_CHAPTER_STREAM_RESTART_MS && chapterStreamCtrl) {
    return
  }

  stopChapterStream()
  const session = chapterStreamSession
  lastChapterStreamStartMs = now
  sseReconnecting.value = true

  console.log('[AutopilotPanel] 启动 SSE 连接...')

  chapterStreamCtrl = subscribeChapterStream(props.novelId, {
    onOutlinePlanning: () => {
      void fetchStatus()
    },
    onBeatsPlanned: (chapterNumber, beats) => {
      void fetchStatus()
      emit('desk-refresh')
      emit('beats-planned', { chapterNumber, beats })
    },
    onChapterStart: (num) => {
      const isNewChapter = writingChapterNumber.value !== num
      writingChapterNumber.value = num
      // SSE 重连会对同一章再次发 chapter_start，勿清空已累积正文
      if (isNewChapter) {
        writingContent.value = ''
        writingBeatIndex.value = 0
      }
      reconnectAttempts = 0  // 重置重连计数
      emit('chapter-start', num)
      // 🔥 新章节开始写时刷新侧栏，让结构树/章节列表同步（规划后首次写作尤其需要）
      emit('desk-refresh')
    },
    onChapterChunk: (payload) => {
      const maxLen = 80000
      if (payload.isSnapshot && payload.content != null) {
        if (payload.content.length <= maxLen) {
          writingContent.value = payload.content
        }
      } else if (payload.chunk && writingContent.value.length < maxLen) {
        writingContent.value += payload.chunk
      }
      writingBeatIndex.value = payload.beatIndex
      emitChapterChunkThrottled({
        chunk: payload.chunk ?? '',
        beatIndex: payload.beatIndex,
        content: writingContent.value,
        chapterNumber: writingChapterNumber.value,
        isSnapshot: payload.isSnapshot,
      }, Boolean(payload.isSnapshot))
    },
    onChapterContent: (data) => {
      writingContent.value = data.content
      writingChapterNumber.value = data.chapterNumber
      writingBeatIndex.value = data.beatIndex
      emit('chapter-content-update', data)
    },
    onAutopilotStopped: () => {
      reconnectAttempts = 0
      void fetchStatus()
      // 🔥 全书完成/停止时刷新章节列表，确保侧栏「已收稿」状态同步
      emit('desk-refresh')
    },
    onPausedForReview: () => {
      reconnectAttempts = 0
      void fetchStatus()
      // 🔥 进入待审阅时刷新章节列表和结构树
      emit('desk-refresh')
    },
    onConnected: () => {
      if (session !== chapterStreamSession) return
      sseConnected.value = true
      sseReconnecting.value = false
      console.log('[AutopilotPanel] SSE 已连接')
    },
    onStreamEnd: (reason) => {
      if (session !== chapterStreamSession) return
      sseConnected.value = false
      chapterStreamCtrl = null
      sseReconnecting.value = false
      void fetchStatus().then(() => {
        if (reason === 'stopped' || reason === 'review') {
          reconnectAttempts = 0
          return
        }
        // 服务端在非写作阶段关流（idle）：仅当仍处于 writing 时才重连
        if (!shouldMaintainChapterStream()) {
          reconnectAttempts = 0
          return
        }
        scheduleChapterStreamReconnect(1500)
      })
    },
    onDisconnected: () => {
      if (session !== chapterStreamSession) return
      sseConnected.value = false
      chapterStreamCtrl = null
      void fetchStatus().then(() => {
        if (!shouldMaintainChapterStream()) {
          sseReconnecting.value = false
          reconnectAttempts = 0
          return
        }
        if (reconnectAttempts >= MAX_RECONNECT_ATTEMPTS) {
          console.warn('[AutopilotPanel] SSE 重连次数过多，暂停章节流（仍可通过 /status 轮询看进度）')
          sseReconnecting.value = false
          return
        }
        const delay = Math.min(1000 * 2 ** (reconnectAttempts - 1), 30000)
        scheduleChapterStreamReconnect(delay)
      })
    },
    onError: (err) => {
      if (session !== chapterStreamSession) return
      sseConnected.value = false
      console.error('[AutopilotPanel] SSE 错误:', err)
    },
  })
}

function stopChapterStream() {
  chapterStreamSession++
  if (reconnectTimer) {
    clearTimeout(reconnectTimer)
    reconnectTimer = null
  }
  if (chapterStreamCtrl) {
    chapterStreamCtrl.abort()
    chapterStreamCtrl = null
  }
  sseConnected.value = false
  sseReconnecting.value = false
}

// 🔧 优化：自适应状态轮询 + SSE 协同
// 策略：
// - SSE 已连接时：轮询降到 15s 兜底（SSE 已实时驱动刷新，轮询仅防断连漏检）
// - SSE 未连接但运行中：5s（需要轮询补偿 SSE 的缺失）
// - 非运行中：3s（用户可能刚操作，需要快速看到状态变化）
// - 审阅等待中：10s（用户在看大纲，不需要高频刷新）
function getAdaptivePollInterval() {
  let base
  if (needsReview.value) base = 10000
  else if (!isRunning.value) base = 3000
  else if (sseConnected.value) base = 15000
  else base = 5000
  const mult = Math.min(2 ** Math.min(statusConnectivityFailures.value, 8), 128)
  return Math.min(base * mult, 120_000)
}

watch(
  [
    () => isRunning.value,
    () => needsReview.value,
    () => statusPollDisabled.value,
    () => status.value?.current_stage,
  ],
  () => {
    clearStatusPoll()
    if (statusPollDisabled.value) return

    lastStatusPollIntervalMs = -1
    maybeRestartStatusPollTimer()
    void fetchStatus()

    if (wantsChapterStream()) {
      if (!chapterStreamCtrl && !sseReconnecting.value) {
        startChapterStream()
      }
    } else {
      stopChapterStream()
      reconnectAttempts = 0
    }
  },
  { immediate: true }
)

// 🔥 SSE 连接状态变化时仅调整轮询间隔，不重新管理 SSE 连接（避免与 onDisconnected 双重重连）
watch(
  () => sseConnected.value,
  () => {
    if (!statusPollDisabled.value) {
      lastStatusPollIntervalMs = -1
      maybeRestartStatusPollTimer()
    }
  }
)

watch(
  () => props.novelId,
  () => {
    statusPollDisabled.value = false
    statusConnectivityFailures.value = 0
    reconnectAttempts = 0
    stopChapterStream()
  }
)

function openStartModal() {
  const target = status.value?.target_chapters || 100
  const wpc = status.value?.target_words_per_chapter ?? 2500
  const autoApprove = status.value?.auto_approve_mode ?? false
  startConfig.value = {
    target_chapters: target,
    target_words_per_chapter: wpc,
    max_auto_chapters: target + 20,
    auto_approve_mode: autoApprove
  }
  showStartModal.value = true
}

function updateProtectionLimit() {
  const target = startConfig.value.target_chapters
  if (startConfig.value.max_auto_chapters < target + 20) {
    startConfig.value.max_auto_chapters = target + 20
  }
}

async function start() {
  if (isToggleThrottled()) return
  toggling.value = true
  try {
    const newTarget = startConfig.value.target_chapters
    const newWpc = startConfig.value.target_words_per_chapter
    const currentAutoApprove = status.value?.auto_approve_mode ?? false
    const newAutoApprove = startConfig.value.auto_approve_mode

    // 🔥 乐观更新：立即更新本地状态，用户无需等待后端响应
    const prevStatus = status.value
    status.value = {
      ...status.value,
      autopilot_status: 'running',
      current_stage: prevStatus?.current_stage === 'paused_for_review'
        ? 'writing'  // 审阅恢复时立即显示写作状态
        : (prevStatus?.current_stage || 'macro_planning'),
      target_chapters: newTarget,
      target_words_per_chapter: newWpc,
      auto_approve_mode: newAutoApprove,
      consecutive_error_count: 0,
    }
    emit('status-change', status.value)
    reconnectAttempts = 0
    message.success('自动驾驶已启动')

    // 目标章数 / 每章字数改由 POST .../start 与 RUNNING 原子落库（避免与 PUT /novels 并行竞态导致仍用默认字数）

    // 并行发送所有请求
    const requests = []

    if (currentAutoApprove !== newAutoApprove) {
      requests.push(
        fetch(resolveHttpUrl(`/api/v1/novels/${props.novelId}/auto-approve-mode`), {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ auto_approve_mode: newAutoApprove }),
        }).catch(err => {
          console.warn('[AutopilotPanel] 更新自动审阅模式失败:', err)
        })
      )
    }

    requests.push(
      fetch(resolveHttpUrl(`${autopilotApiRoot()}/start`), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          max_auto_chapters: startConfig.value.max_auto_chapters,
          target_chapters: newTarget,
          target_words_per_chapter: newWpc,
        }),
      }).then(res => {
        if (!res.ok) {
          // 🔥 启动失败时回滚乐观更新
          status.value = prevStatus
          emit('status-change', prevStatus)
          message.error('启动失败')
        }
      }).catch(err => {
        console.warn('[AutopilotPanel] 启动请求失败:', err)
        // 网络错误时回滚
        status.value = prevStatus
        emit('status-change', prevStatus)
        message.error('启动请求失败，请重试')
      })
    )

    // 🔥 不 await 所有请求完成，用户已经看到"已启动"的反馈
    // 后续 fetchStatus 轮询会自动校准状态
    Promise.allSettled(requests).then(() => {
      void fetchStatus()  // 请求全部结束后拉一次真实状态
    })
  } finally {
    toggling.value = false
  }
}

async function stop() {
  if (isToggleThrottled()) return
  // 🔥 乐观更新：立即更新本地状态，用户无需等待后端响应
  const prevStatus = status.value
  status.value = {
    ...status.value,
    autopilot_status: 'stopped',
  }
  emit('status-change', status.value)
  message.info('已停止')
  toggling.value = true

  try {
    // 先关闭 SSE 连接，避免阻塞
    stopChapterStream()
    // 发送停止请求（带超时）
    const controller = new AbortController()
    const timeoutId = setTimeout(() => controller.abort(), 5000)
    try {
      await fetch(resolveHttpUrl(`${autopilotApiRoot()}/stop`), {
        method: 'POST',
        signal: controller.signal
      })
      clearTimeout(timeoutId)
    } catch (e) {
      clearTimeout(timeoutId)
      if (e.name === 'AbortError') {
        message.warning('停止请求超时，但后台可能已处理')
      } else {
        // 🔥 网络错误时回滚乐观更新
        status.value = prevStatus
        emit('status-change', prevStatus)
        throw e
      }
    }
    void fetchStatus()
  } finally {
    toggling.value = false
  }
}

async function resume() {
  if (isToggleThrottled()) return
  // 🔥 乐观更新：立即更新本地状态
  const prevStatus = status.value
  status.value = {
    ...status.value,
    autopilot_status: 'running',
    current_stage: 'writing',
    needs_review: false,
  }
  emit('status-change', status.value)
  reconnectAttempts = 0
  message.success('已确认大纲，开始写作')
  toggling.value = true

  try {
    const res = await fetch(resolveHttpUrl(`${autopilotApiRoot()}/resume`), { method: 'POST' })
    if (!res.ok) {
      // 🔥 恢复失败时回滚乐观更新
      status.value = prevStatus
      emit('status-change', prevStatus)
      const e = await res.json()
      message.error(e.detail || '恢复失败')
    }
    void fetchStatus()
  } catch (err) {
    // 网络错误时回滚
    status.value = prevStatus
    emit('status-change', prevStatus)
    message.error('恢复请求失败，请重试')
  } finally {
    toggling.value = false
  }
}

async function clearCircuitBreaker() {
  // 🔥 乐观更新：立即清零失败计数
  const prevStatus = status.value
  status.value = {
    ...status.value,
    autopilot_status: 'stopped',  // 挂起 → 停止（需用户重新启动）
    consecutive_error_count: 0,
  }
  emit('status-change', status.value)
  message.success('已解除挂起并清零失败计数')
  toggling.value = true

  try {
    const res = await fetch(
      resolveHttpUrl(`${autopilotApiRoot()}/circuit-breaker/reset`),
      { method: 'POST' },
    )
    if (!res.ok) {
      status.value = prevStatus
      emit('status-change', prevStatus)
      message.error('操作失败')
    }
    void fetchStatus()
  } catch (err) {
    status.value = prevStatus
    emit('status-change', prevStatus)
    message.error('操作失败，请重试')
  } finally {
    toggling.value = false
  }
}

async function forceStopFromError() {
  if (isToggleThrottled()) return
  // 🔥 乐观更新：立即设置停止状态
  const prevStatus = status.value
  status.value = {
    ...status.value,
    autopilot_status: 'stopped',
    consecutive_error_count: 0,
  }
  emit('status-change', status.value)
  message.info('正在强制停止...')
  toggling.value = true

  try {
    // 先关闭 SSE 连接
    stopChapterStream()
    // 并行发送：stop 请求 + circuit-breaker/reset 请求
    const stopPromise = fetch(resolveHttpUrl(`${autopilotApiRoot()}/stop`), {
      method: 'POST',
    }).catch(err => {
      console.warn('[AutopilotPanel] 强制停止请求失败:', err)
    })
    const resetPromise = fetch(
      resolveHttpUrl(`${autopilotApiRoot()}/circuit-breaker/reset`),
      { method: 'POST' },
    ).catch(err => {
      console.warn('[AutopilotPanel] 重置熔断器失败:', err)
    })
    await Promise.allSettled([stopPromise, resetPromise])
    void fetchStatus()
  } catch (err) {
    // 即使失败也保持 stopped 状态（强制停止的含义）
    console.warn('[AutopilotPanel] 强制停止异常:', err)
    void fetchStatus()
  } finally {
    toggling.value = false
  }
}

onUnmounted(() => {
  flushChapterChunkEmit()
  statusFetchSeq += 1
  statusFetchInFlight = false  // 🔥 重置请求去重标志
  if (statusLastAbort) {
    statusLastAbort.abort()
    statusLastAbort = null
  }
  clearStatusPoll()
  stopChapterStream()
})
</script>

<style scoped>
.autopilot-panel {
  --ap-accent: var(--color-success, #22c55e);
  --ap-card-bg: var(--app-surface-raised, var(--app-surface));
  --ap-card-border: var(--app-border);
  background: var(--ap-card-bg);
  border: 1px solid var(--ap-card-border);
  border-radius: var(--app-radius-lg, 14px);
  padding: 16px 18px 14px;
  display: flex;
  flex-direction: column;
  gap: 14px;
  box-shadow: var(--app-shadow-md);
}

.ap-hero {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 14px 16px;
  border-radius: var(--app-radius-md, 10px);
  background: linear-gradient(
    145deg,
    color-mix(in srgb, var(--color-primary, #2563eb) 5%, var(--app-surface-subtle)) 0%,
    var(--app-surface-subtle) 55%
  );
  border: 1px solid var(--app-border);
}

.ap-hero__top {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}

.ap-hero__status {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  min-width: 0;
  flex: 1 1 200px;
}

.ap-hero__eyebrow {
  font-size: 10px;
  font-weight: 600;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--app-text-muted);
}

.ap-hero__pct {
  text-align: right;
  flex-shrink: 0;
}

.ap-hero__pct-value {
  display: block;
  font-size: 28px;
  font-weight: 700;
  line-height: 1;
  font-variant-numeric: tabular-nums;
  color: var(--app-text-primary);
  letter-spacing: -0.03em;
}

.ap-hero__pct.is-active .ap-hero__pct-value {
  color: var(--ap-accent);
}

.ap-hero__pct-label {
  font-size: 10px;
  color: var(--app-text-muted);
  margin-top: 2px;
}

.ap-hero__bar :deep(.n-progress-graph) {
  border-radius: 4px;
}

.ap-hero__plan-line {
  margin: 0;
  font-size: 12px;
  line-height: 1.55;
  color: var(--app-text-secondary);
}

.ap-hero__plan-line strong {
  color: var(--app-text-primary);
  font-weight: 600;
}

.ap-hero__plan-toggle {
  margin-left: 4px;
  vertical-align: baseline;
}

.ap-plan-detail {
  margin: 0;
  padding: 10px 12px;
  font-size: 11px;
  line-height: 1.6;
  color: var(--app-text-muted);
  background: color-mix(in srgb, var(--app-text-primary) 3%, transparent);
  border-radius: var(--app-radius-sm, 8px);
  border-left: 3px solid var(--color-primary, #2563eb);
}

.ap-inline-alert {
  font-size: 12px;
}

.ap-inline-alert :deep(.n-alert-body) {
  padding-top: 2px;
  padding-bottom: 2px;
}

.ap-dot {
  width: 9px;
  height: 9px;
  border-radius: 50%;
  flex-shrink: 0;
  box-shadow: 0 0 0 3px color-mix(in srgb, currentColor 18%, transparent);
}

.dot-running {
  background: var(--color-success, #22c55e);
  color: var(--color-success, #22c55e);
  animation: ap-dot-pulse 1.4s ease-in-out infinite;
}

.dot-review {
  background: var(--color-warning, #f59e0b);
  color: var(--color-warning, #f59e0b);
  animation: ap-dot-pulse 0.9s ease-in-out infinite;
}

.dot-error {
  background: var(--color-danger, #ef4444);
  color: var(--color-danger, #ef4444);
}

.dot-stopped {
  background: var(--app-text-muted);
  color: var(--app-text-muted);
}

@keyframes ap-dot-pulse {
  0%, 100% { opacity: 1; transform: scale(1); }
  50% { opacity: 0.55; transform: scale(0.92); }
}

.ap-stage-tag {
  font-size: 12px;
  padding: 4px 11px;
  border-radius: 999px;
  font-weight: 600;
  border: 1px solid transparent;
}

.tag-review {
  background: var(--color-warning-dim);
  color: var(--color-warning);
  border-color: color-mix(in srgb, var(--color-warning) 25%, transparent);
}

.tag-idle {
  background: color-mix(in srgb, var(--app-text-muted) 12%, transparent);
  color: var(--app-text-muted);
}

.tag-sem-plan { background: var(--color-brand-light); color: var(--color-brand); }
.tag-sem-write { background: var(--color-success-dim); color: var(--color-success); }
.tag-sem-audit { background: var(--color-warning-dim); color: var(--color-warning); }
.tag-sem-sync { background: var(--color-info-dim); color: var(--color-info); }
.tag-sem-review { background: var(--color-warning-dim); color: var(--color-warning); }
.tag-sem-idle {
  background: var(--color-purple-light, rgba(139, 92, 246, 0.12));
  color: var(--color-purple, #8b5cf6);
}
.tag-sem-daemon_wait { background: var(--color-info-dim); color: var(--color-info); }

.stage-text { vertical-align: middle; }

.ap-stage-live {
  display: inline-block;
  width: 6px;
  height: 6px;
  margin-left: 6px;
  border-radius: 50%;
  background: currentColor;
  vertical-align: middle;
  animation: ap-live-pulse 1.2s ease-in-out infinite;
}

@keyframes ap-live-pulse {
  0%, 100% { opacity: 0.9; transform: scale(1); }
  50% { opacity: 0.35; transform: scale(0.88); }
}

.tag-transitioning { position: relative; overflow: hidden; }

.skeleton-inline {
  position: absolute;
  inset: 0;
  border-radius: inherit;
  z-index: 1;
}

.skeleton-pulse {
  background: linear-gradient(
    90deg,
    color-mix(in srgb, var(--color-primary) 6%, transparent) 25%,
    color-mix(in srgb, var(--color-primary) 18%, transparent) 50%,
    color-mix(in srgb, var(--color-primary) 6%, transparent) 75%
  );
  background-size: 200% 100%;
  animation: skeleton-shimmer 1.5s ease-in-out infinite;
}

@keyframes skeleton-shimmer {
  0% { background-position: 200% 0; }
  100% { background-position: -200% 0; }
}

.stage-transition-label {
  position: relative;
  z-index: 2;
  animation: fade-in-up 0.35s ease;
}

@keyframes fade-in-up {
  from { opacity: 0; transform: translateY(4px); }
  to { opacity: 1; transform: translateY(0); }
}

.ap-sse-pill {
  font-size: 10px;
  font-weight: 600;
  padding: 3px 8px;
  border-radius: 999px;
  border: 1px solid var(--app-border);
}

.ap-sse-pill.is-on {
  background: var(--color-success-dim);
  color: var(--color-success);
  border-color: color-mix(in srgb, var(--color-success) 30%, transparent);
}

.ap-sse-pill.is-off {
  background: color-mix(in srgb, var(--app-text-muted) 10%, transparent);
  color: var(--app-text-muted);
}

.ap-kpi-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
}

.ap-kpi {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 12px 12px 10px;
  min-width: 0;
  background: var(--app-surface-subtle);
  border: 1px solid var(--app-border);
  border-radius: var(--app-radius-md, 10px);
  transition: border-color var(--app-transition), box-shadow var(--app-transition);
}

.ap-kpi:hover {
  border-color: var(--app-border-strong);
  box-shadow: var(--app-shadow-sm);
}

.ap-kpi__label {
  font-size: 10px;
  font-weight: 600;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: var(--app-text-muted);
}

.ap-kpi__value {
  font-size: 15px;
  font-weight: 650;
  color: var(--app-text-primary);
  font-variant-numeric: tabular-nums;
  line-height: 1.25;
}

.ap-kpi__value--wrap {
  font-size: 13px;
  font-weight: 600;
  line-height: 1.45;
}

.ap-kpi--location {
  gap: 7px;
  padding-bottom: 11px;
}

.ap-kpi__sep {
  margin: 0 2px;
  color: var(--app-text-muted);
  font-weight: 500;
}

.ap-kpi__act {
  display: block;
  margin-top: 2px;
  font-size: 11px;
  font-weight: 500;
  color: var(--app-text-secondary);
}

.ap-kpi__muted {
  color: var(--app-text-muted);
  font-weight: 500;
}

.ap-location {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 5px;
}

.ap-location__meta {
  width: fit-content;
  max-width: 100%;
  padding: 2px 7px;
  border-radius: 999px;
  border: 1px solid color-mix(in srgb, var(--color-primary, #2563eb) 18%, var(--app-border));
  background: color-mix(in srgb, var(--color-primary, #2563eb) 7%, transparent);
  color: var(--app-text-secondary);
  font-size: 10px;
  font-weight: 700;
  line-height: 1.35;
  font-variant-numeric: tabular-nums;
}

.ap-location__title {
  min-width: 0;
  max-width: 100%;
  color: var(--app-text-primary);
  font-size: 13px;
  font-weight: 700;
  line-height: 1.35;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.ap-location__trail {
  min-height: 20px;
  display: flex;
  align-items: center;
  gap: 5px;
  flex-wrap: wrap;
}

.ap-location__chip {
  min-width: 0;
  max-width: 100%;
  padding: 2px 6px;
  border-radius: 6px;
  background: color-mix(in srgb, var(--app-text-muted) 8%, transparent);
  color: var(--app-text-muted);
  font-size: 10.5px;
  font-weight: 650;
  line-height: 1.35;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.ap-location__chip--strong {
  background: var(--color-primary-light, color-mix(in srgb, var(--color-primary, #2563eb) 12%, transparent));
  color: var(--color-primary, #2563eb);
}

.ap-narrative {
  padding: 12px 14px;
  border-radius: var(--app-radius-md, 10px);
  background: var(--app-surface-subtle);
  border: 1px solid var(--app-border);
  border-left: 3px solid var(--color-primary, #2563eb);
}

.ap-narrative__label {
  display: block;
  font-size: 10px;
  font-weight: 600;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--app-text-muted);
  margin-bottom: 6px;
}

.ap-narrative__title {
  display: block;
  font-weight: 600;
  color: var(--app-text-primary);
  margin-bottom: 4px;
}

.ap-narrative__body {
  margin: 0;
  font-size: 12px;
  line-height: 1.65;
  color: var(--app-text-secondary);
}

.ap-narrative__body--muted {
  font-style: italic;
  color: var(--app-text-muted);
}

.ap-telemetry {
  padding: 12px 14px;
  border-radius: var(--app-radius-md, 10px);
  background: color-mix(in srgb, var(--color-primary) 4%, var(--app-surface-subtle));
  border: 1px solid color-mix(in srgb, var(--color-primary) 18%, var(--app-border));
}

.ap-telemetry__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 10px;
}

.ap-telemetry__title {
  font-size: 11px;
  font-weight: 650;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--app-text-muted);
}

.ap-telemetry__grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px 14px;
}

.ap-telemetry__item {
  display: grid;
  grid-template-columns: auto 1fr;
  grid-template-rows: auto auto;
  gap: 4px 10px;
  align-items: center;
}

.ap-telemetry__item--wide {
  grid-column: 1 / -1;
}

.ap-telemetry__key {
  font-size: 11px;
  color: var(--app-text-muted);
  font-weight: 500;
}

.ap-telemetry__val {
  font-size: 12px;
  font-weight: 600;
  color: var(--app-text-primary);
  font-variant-numeric: tabular-nums;
  justify-self: end;
}

.ap-telemetry__val--focus {
  justify-self: start;
  grid-column: 2;
  font-weight: 500;
  color: var(--app-text-secondary);
  word-break: break-word;
}

.ap-meter {
  grid-column: 1 / -1;
  height: 4px;
  border-radius: 999px;
  background: color-mix(in srgb, var(--app-text-primary) 8%, transparent);
  overflow: hidden;
}

.ap-meter__fill {
  height: 100%;
  border-radius: inherit;
  transition: width 0.45s ease;
}

.ap-meter__fill--beat {
  background: linear-gradient(90deg, var(--color-primary), var(--color-brand-hover, #3b82f6));
}

.ap-meter__fill--word {
  background: linear-gradient(90deg, var(--color-success), color-mix(in srgb, var(--color-success) 70%, #fff));
}

.substep-badge {
  display: inline-block;
  padding: 2px 10px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 600;
  background: var(--color-brand-light);
  color: var(--color-brand);
}

.substep-badge.substep-active {
  background: var(--color-success-dim);
  color: var(--color-success);
  animation: pulse-subtle 2s infinite;
}

.substep-badge.substep-prepare,
.substep-badge.substep-plan {
  background: var(--color-info-dim, var(--color-brand-light));
  color: var(--color-info, var(--color-brand));
}

.substep-badge.substep-finish {
  background: var(--color-warning-dim);
  color: var(--color-warning);
}

.substep-badge.substep-audit {
  background: var(--color-warning-dim);
  color: var(--color-warning);
}

@keyframes pulse-subtle {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.72; }
}

.pct-tag {
  font-size: 10px;
  padding: 1px 6px;
  border-radius: 999px;
  background: var(--color-success-dim);
  color: var(--color-success);
  font-weight: 600;
  margin-left: 4px;
}

@media (max-width: 900px) {
  .ap-kpi-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .ap-telemetry__grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 520px) {
  .ap-hero__pct-value {
    font-size: 22px;
  }
}

.ap-review-alert {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 10px;
}

.ap-review-alert span {
  line-height: 1.55;
}

.recovery-hint p { margin: 0 0 6px; line-height: 1.5; }
.recovery-sub { font-size: 11px; opacity: 0.95; margin-bottom: 8px !important; }
</style>

