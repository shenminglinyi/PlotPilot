<template>
  <div class="autopilot-panel">
    <!-- 状态头 -->
    <div class="ap-header">
      <span class="ap-dot" :class="dotClass"></span>
      <span class="ap-title">全托管驾驶</span>
      <span class="ap-stage-tag" :class="stageTagClass">{{ stageLabel }}</span>
      <!-- 🔧 新增：SSE 连接状态指示 -->
      <span v-if="isRunning && !needsReview" class="sse-status" :class="sseConnected ? 'connected' : 'disconnected'">
        {{ sseConnected ? '已连接' : (sseReconnecting ? '重连中...' : '未连接') }}
      </span>
    </div>

    <!-- 进度条 -->
    <n-progress
      type="line"
      :percentage="progressPct"
      :color="progressColor"
      indicator-placement="inside"
      :height="14"
      style="margin: 4px 0"
    />

    <p v-if="status" class="ap-plan-hint">
      与首页「目标篇幅」同一套落库参数：计划约
      <strong>{{ formatWords(planTotalWordsHint) }}</strong> 字（
      <strong>{{ status.target_chapters ?? '—' }}</strong> 章 ×
      <strong>{{ status.target_words_per_chapter ?? 2500 }}</strong> 字/章）。全托管写满目标章即停；节拍拆分按「每章字数」执行。
    </p>

    <!-- 数据格 -->
    <div class="ap-grid">
      <div class="ap-cell">
        <div class="label">完稿 / 书稿</div>
        <div class="value">
          {{ status?.completed_chapters || 0 }} / {{ status?.manuscript_chapters ?? status?.completed_chapters ?? 0 }} / {{ status?.target_chapters || '-' }}
        </div>
      </div>
      <div class="ap-cell">
        <div class="label">总字数</div>
        <div class="value">{{ formatWords(status?.total_words) }}</div>
      </div>
      <div class="ap-cell">
        <div class="label">当前幕 / 章 / 节拍</div>
        <div class="value">
          第 {{ (status?.current_act || 0) + 1 }} 幕
          <span v-if="status?.current_act_title" class="act-title">{{ status.current_act_title }}</span>
          <template v-if="status?.current_chapter_number != null && isWriting">
            · 第 {{ status.current_chapter_number }} 章
          </template>
          <span v-if="isWriting"> · {{ beatLabel }}</span>
        </div>
        <div v-if="status?.current_act_description" class="act-desc">{{ status.current_act_description }}</div>
      </div>
      <div class="ap-cell">
        <div class="label">上章张力</div>
        <div class="value" :style="{ color: tensionColor }">{{ tensionLabel }}</div>
      </div>
    </div>

    <!-- ★ V9 细化状态条：运行中时展示子步骤、节拍进度、字数进度 -->
    <div v-if="isRunning && writingSubstepDetail" class="ap-detail-strip">
      <div class="detail-row">
        <span class="detail-label">子步骤</span>
        <span class="detail-value">
          <span class="substep-badge" :class="substepBadgeClass">{{ writingSubstepDetail.substepLabel }}</span>
        </span>
      </div>
      <div class="detail-row" v-if="writingSubstepDetail.totalBeats > 0">
        <span class="detail-label">节拍进度</span>
        <span class="detail-value">
          {{ writingSubstepDetail.beatIndex }}/{{ writingSubstepDetail.totalBeats }}
          <div class="mini-progress">
            <div class="mini-progress-fill" :style="{ width: writingSubstepDetail.beatPct + '%' }"></div>
          </div>
        </span>
      </div>
      <div class="detail-row" v-if="writingSubstepDetail.accumulatedWords > 0">
        <span class="detail-label">字数进度</span>
        <span class="detail-value">
          {{ writingSubstepDetail.accumulatedWords }}/{{ writingSubstepDetail.chapterTargetWords }}字
          <span class="pct-tag">{{ writingSubstepDetail.wordPct }}%</span>
          <div class="mini-progress">
            <div class="mini-progress-fill word-fill" :style="{ width: writingSubstepDetail.wordPct + '%' }"></div>
          </div>
        </span>
      </div>
      <div class="detail-row" v-if="writingSubstepDetail.beatFocus">
        <span class="detail-label">节拍焦点</span>
        <span class="detail-value focus-text">{{ writingSubstepDetail.beatFocus }}</span>
      </div>
      <div class="detail-row" v-if="writingSubstepDetail.contextTokens > 0">
        <span class="detail-label">上下文</span>
        <span class="detail-value">{{ writingSubstepDetail.contextTokens }} tokens</span>
      </div>
    </div>

    <!-- 单本挂起 / 失败计数过高 -->
    <n-alert v-if="needsRecovery" type="error" :show-icon="true" style="margin: 4px 0; font-size: 12px">
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
    <n-alert v-if="needsReview" type="warning" :show-icon="true" style="margin: 4px 0; font-size: 12px">
      <strong>待审阅确认</strong>：请在侧栏查看刚生成的大纲/结构，确认后点
      <strong>「确认大纲，继续写作」</strong>。
    </n-alert>

    <!-- 仅流式正文预览（审阅状态时停止 SSE，避免卡界面） -->
    <AutopilotWritingStream
      v-if="isRunning && !needsReview"
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
    />

    <!-- 操作按钮 -->
    <n-space justify="end" size="small">
      <n-button v-if="needsReview" type="warning" size="small" :loading="toggling" @click="resume">
        确认大纲，继续写作
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
              :max="10000"
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
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { useMessage } from 'naive-ui'
import AutopilotWritingStream from './AutopilotWritingStream.vue'
import { resolveHttpUrl, subscribeChapterStream } from '../../api/config'

const props = defineProps({ novelId: String })
const emit = defineEmits(['status-change', 'chapter-content-update', 'chapter-start', 'chapter-chunk', 'desk-refresh'])
const message = useMessage()

const status = ref(null)
const toggling = ref(false)
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
const MAX_RECONNECT_ATTEMPTS = 5

// 写作内容状态
const writingContent = ref('')
const writingChapterNumber = ref(0)
const writingBeatIndex = ref(0)

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

// 计算属性
const isRunning = computed(() => status.value?.autopilot_status === 'running')
const needsReview = computed(() => status.value?.needs_review === true)
// 🔥 只有运行中且阶段为 writing 时才是真正的"撰写中"
const isWriting = computed(() =>
  status.value?.autopilot_status === 'running' && status.value?.current_stage === 'writing'
)
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
  const done = s.completed_chapters || 0
  const ms = s.manuscript_chapters ?? 0
  if (done > 0) return s.progress_pct ?? 0
  if (ms > 0 && s.progress_pct_manuscript != null) return s.progress_pct_manuscript
  return s.progress_pct ?? 0
})

const progressColor = computed(() => {
  if (needsRecovery.value) return '#d03050'
  if (needsReview.value) return '#f0a020'
  return '#18a058'
})

const dotClass = computed(() => ({
  'dot-running': isRunning.value && !needsReview.value,
  'dot-review': needsReview.value,
  'dot-error': status.value?.autopilot_status === 'error',
  'dot-stopped': !isRunning.value && !needsReview.value,
}))

const stageLabel = computed(() => {
  const stage = status.value?.current_stage
  const apStatus = status.value?.autopilot_status

  // 🔥 如果已停止，不显示"撰写中/审计中"等运行中状态
  if (apStatus === 'stopped' || apStatus === 'error') {
    if (apStatus === 'error') return '异常挂起'
    if (stage === 'completed') return '已完成'
    return '已停止'
  }

  const m = {
    macro_planning: '宏观规划', act_planning: '幕级规划',
    writing: '撰写中', auditing: '审计中',
    paused_for_review: '待审阅', completed: '已完成',
    syncing: '数据同步中',
  }

  // 🔥 守护进程不可达时：优先显示后端状态提示
  if (isRunning.value && !daemonAlive.value) {
    return '后端处理中（等待响应...）'
  }

  // 🔥 三层降级显示策略：
  // 1. 共享内存实时状态（最优）
  // 2. 超时降级（_degraded = true）
  // 3. 正常状态
  if (status.value?._from_shared_memory) {
    // 共享内存实时状态：显示「实时同步中」提示
    if (stage === 'auditing') {
      const progress = status.value?.audit_progress
      if (progress === 'voice_check') return '审计中·文风检查 ⚡'
      if (progress === 'aftermath_pipeline') return '审计中·章后管线 ⚡'
      if (progress === 'tension_scoring') return '审计中·张力打分 ⚡'
      return '审计中 ⚡'
    }
    if (stage === 'syncing') return '数据同步中 ⚡'
    return m[stage] + ' ⚡' || '待机 ⚡'
  }

  // 降级模式：DB 被锁或超时时显示同步状态
  if (status.value?._degraded) {
    if (stage === 'auditing') {
      const progress = status.value?.audit_progress
      if (progress === 'voice_check') return '审计中·文风检查（数据同步中...）'
      if (progress === 'aftermath_pipeline') return '审计中·章后管线（数据同步中...）'
      if (progress === 'tension_scoring') return '审计中·张力打分（数据同步中...）'
      return '审计中（数据同步中...）'
    }
    if (stage === 'syncing') return '数据同步中...'
    return (m[stage] || '待机') + '（数据同步中...）'
  }

  if (stage === 'auditing') {
    const progress = status.value?.audit_progress
    if (progress === 'voice_check') return '审计中（文风检查）'
    if (progress === 'aftermath_pipeline') return '审计中（章后管线）'
    if (progress === 'tension_scoring') return '审计中（张力打分）'
    return '审计中'
  }

  return m[stage] || '待机'
})

const stageTagClass = computed(() => ({
  'tag-active': isRunning.value && !needsReview.value,
  'tag-review': needsReview.value,
  'tag-idle': !isRunning.value && !needsReview.value,
}))

const beatLabel = computed(() => {
if (!isWriting.value) return ''
const b = status.value?.current_beat_index ?? 0
return `节拍 ${Number(b) + 1}`
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
      return
    }
    if (res.ok) {
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

      // 仍在跑且非审阅，但章节流已掉线且自动重连已放弃 → 由轮询周期性再给机会（避免永久无正文流）
      if (
        body.autopilot_status === 'running' &&
        !body.needs_review &&
        !chapterStreamCtrl &&
        !sseReconnecting.value &&
        reconnectAttempts >= MAX_RECONNECT_ATTEMPTS
      ) {
        reconnectAttempts = 0
        startChapterStream()
      }
    }
  } catch (err) {
    if (seq !== statusFetchSeq) {
      return
    }
    if (err instanceof Error && err.name === 'AbortError') {
      console.warn('[AutopilotPanel] fetchStatus 超时，可能后端繁忙')
    } else {
      console.error('[AutopilotPanel] fetchStatus error:', err)
    }
  } finally {
    window.clearTimeout(t)
    statusFetchInFlight = false
  }
}

function clearStatusPoll() {
  if (statusPollTimer) {
    clearInterval(statusPollTimer)
    statusPollTimer = null
  }
}

// 🔧 优化：SSE 连接管理
function startChapterStream() {
  // 先清理旧连接
  stopChapterStream()

  // 审阅状态时不启动 SSE
  if (needsReview.value) {
    console.log('[AutopilotPanel] 审阅状态，不启动 SSE')
    return
  }

  sseReconnecting.value = true
  writingContent.value = ''
  writingChapterNumber.value = 0
  writingBeatIndex.value = 0

  console.log('[AutopilotPanel] 启动 SSE 连接...')

  chapterStreamCtrl = subscribeChapterStream(props.novelId, {
    onChapterStart: (num) => {
      writingChapterNumber.value = num
      writingContent.value = ''
      writingBeatIndex.value = 0
      reconnectAttempts = 0  // 重置重连计数
      emit('chapter-start', num)
      // 🔥 新章节开始写时刷新侧栏，让结构树/章节列表同步（规划后首次写作尤其需要）
      emit('desk-refresh')
    },
    onChapterChunk: (chunk, beatIndex) => {
      // 🔧 优化：限制内容长度，避免 Vue 响应式性能问题
      const maxLen = 80000
      if (writingContent.value.length < maxLen) {
        writingContent.value += chunk
      }
      writingBeatIndex.value = beatIndex
      emit('chapter-chunk', { chunk, beatIndex, content: writingContent.value })
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
      sseConnected.value = true
      sseReconnecting.value = false
      reconnectAttempts = 0
      console.log('[AutopilotPanel] SSE 已连接')
    },
    onDisconnected: () => {
      sseConnected.value = false
      // 先同步一次状态再决定是否重连：审阅暂停时服务端会关流，若仍按旧状态重连会打满次数或假死
      void fetchStatus().then(() => {
        if (reconnectTimer) {
          clearTimeout(reconnectTimer)
          reconnectTimer = null
        }
        if (!isRunning.value || needsReview.value) {
          sseReconnecting.value = false
          reconnectAttempts = 0
          return
        }
        if (reconnectAttempts >= MAX_RECONNECT_ATTEMPTS) {
          console.error('[AutopilotPanel] SSE 重连次数过多，停止尝试')
          sseReconnecting.value = false
          return
        }
        sseReconnecting.value = true
        const delay = Math.min(1000 * 2 ** reconnectAttempts, 30000)
        reconnectAttempts++
        console.log(`[AutopilotPanel] SSE 断开，${delay / 1000}s 后重连 (${reconnectAttempts}/${MAX_RECONNECT_ATTEMPTS})`)
        reconnectTimer = setTimeout(() => {
          void fetchStatus().then(() => {
            if (isRunning.value && !needsReview.value) {
              startChapterStream()
            } else {
              sseReconnecting.value = false
              reconnectAttempts = 0
            }
          })
        }, delay)
      })
    },
    onError: (err) => {
      sseConnected.value = false
      console.error('[AutopilotPanel] SSE 错误:', err)
      // 错误时不立即重连，等待 onDisconnected 处理
    }
  })
}

function stopChapterStream() {
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
  writingContent.value = ''
}

// 🔧 优化：自适应状态轮询 + SSE 协同
// 策略：
// - SSE 已连接时：轮询降到 15s 兜底（SSE 已实时驱动刷新，轮询仅防断连漏检）
// - SSE 未连接但运行中：5s（需要轮询补偿 SSE 的缺失）
// - 非运行中：3s（用户可能刚操作，需要快速看到状态变化）
// - 审阅等待中：10s（用户在看大纲，不需要高频刷新）
function getAdaptivePollInterval() {
  if (needsReview.value) return 10000
  if (!isRunning.value) return 3000
  if (sseConnected.value) return 15000  // SSE 已覆盖实时刷新
  return 5000  // SSE 断连时需要轮询补偿
}

watch(
  () => [isRunning.value, needsReview.value, statusPollDisabled.value],
  () => {
    clearStatusPoll()
    if (statusPollDisabled.value) return

    const pollInterval = getAdaptivePollInterval()
    statusPollTimer = setInterval(() => fetchStatus(), pollInterval)
    void fetchStatus()

    // SSE 连接管理（主动拉流时清零重连计数，避免此前误判耗尽后永久无法再连）
    if (isRunning.value && !needsReview.value) {
      reconnectAttempts = 0
      startChapterStream()
    } else {
      stopChapterStream()
    }
  },
  { immediate: true }
)

// 🔥 SSE 连接状态变化时仅调整轮询间隔，不重新管理 SSE 连接（避免与 onDisconnected 双重重连）
watch(
  () => sseConnected.value,
  () => {
    // 仅在已建立轮询的情况下调整间隔，不重新触发 SSE 连接管理
    if (statusPollTimer && !statusPollDisabled.value) {
      clearStatusPoll()
      const pollInterval = getAdaptivePollInterval()
      statusPollTimer = setInterval(() => fetchStatus(), pollInterval)
    }
  }
)

watch(
  () => props.novelId,
  () => {
    statusPollDisabled.value = false
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
    const currentTarget = status.value?.target_chapters
    const newTarget = startConfig.value.target_chapters
    const currentWpc = status.value?.target_words_per_chapter ?? 2500
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

    // 🔥 非阻塞：配置更新和启动请求并行发送，不等待
    const novelPatch = {}
    if (currentTarget !== newTarget) {
      novelPatch.target_chapters = newTarget
    }
    if (currentWpc !== newWpc) {
      novelPatch.target_words_per_chapter = newWpc
    }

    // 并行发送所有请求
    const requests = []

    if (Object.keys(novelPatch).length > 0) {
      requests.push(
        fetch(resolveHttpUrl(`/api/v1/novels/${props.novelId}`), {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(novelPatch),
        }).catch(err => {
          console.warn('[AutopilotPanel] 更新书目配置失败:', err)
          message.error('更新书目目标章数或每章字数失败')
        })
      )
    }

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
        body: JSON.stringify({ max_auto_chapters: startConfig.value.max_auto_chapters }),
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

onMounted(() => { fetchStatus() })
onUnmounted(() => {
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
  background: linear-gradient(135deg, rgba(24, 160, 88, 0.05) 0%, rgba(24, 160, 88, 0.02) 100%);
  border: 1px solid rgba(24, 160, 88, 0.15);
  border-radius: 12px;
  padding: 16px 18px;
  display: flex;
  flex-direction: column;
  gap: 12px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04);
}

.ap-header {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.ap-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  flex-shrink: 0;
  box-shadow: 0 0 8px currentColor;
}

.dot-running { background: #18a058; animation: pulse 1.4s ease-in-out infinite; }
.dot-review { background: #f0a020; animation: pulse 0.8s ease-in-out infinite; }
.dot-error { background: #d03050; }
.dot-stopped { background: #999; }

@keyframes pulse {
  0%, 100% { opacity: 1; transform: scale(1); }
  50% { opacity: 0.5; transform: scale(0.9); }
}

.ap-title {
  font-weight: 600;
  color: var(--n-text-color);
  font-size: 15px;
}

.ap-stage-tag {
  margin-left: auto;
  font-size: 11px;
  padding: 3px 10px;
  border-radius: 12px;
  font-weight: 500;
}

.tag-active { background: rgba(24, 160, 88, 0.15); color: #18a058; }
.tag-review { background: rgba(240, 160, 32, 0.15); color: #f0a020; }
.tag-idle { background: rgba(100, 100, 100, 0.1); color: #999; }

/* 🔧 新增：SSE 连接状态 */
.sse-status {
  font-size: 10px;
  padding: 2px 6px;
  border-radius: 4px;
  margin-left: 4px;
}
.sse-status.connected { background: rgba(24, 160, 88, 0.15); color: #18a058; }
.sse-status.disconnected { background: rgba(200, 200, 200, 0.15); color: #999; }

.ap-plan-hint {
  margin: 0 0 8px;
  font-size: 11px;
  line-height: 1.55;
  color: var(--app-text-secondary, #64748b);
}

.ap-plan-hint strong { color: var(--app-text-primary, #111827); font-weight: 600; }

.ap-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 8px;
  padding: 4px 0;
}

.ap-cell {
  text-align: center;
  padding: 6px 4px;
  min-width: 0;
  background: rgba(255, 255, 255, 0.4);
  border-radius: 8px;
}

.ap-cell .label {
  font-size: 10px;
  color: var(--n-text-color-3);
  margin-bottom: 2px;
  font-weight: 500;
}

.ap-cell .value {
  font-size: 13px;
  font-weight: 600;
  color: var(--n-text-color);
  font-variant-numeric: tabular-nums;
  word-break: break-word;
}

.act-title {
  font-weight: 500;
  color: var(--n-text-color-2);
  margin-left: 4px;
}

.act-desc {
  font-size: 11px;
  color: var(--n-text-color-3);
  margin-top: 2px;
  line-height: 1.4;
  word-break: break-word;
}

/* ★ V9 细化状态条 */
.ap-detail-strip {
  margin: 2px 0;
  padding: 6px 8px;
  background: rgba(99, 102, 241, 0.06);
  border: 1px solid rgba(99, 102, 241, 0.15);
  border-radius: 6px;
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 12px;
}

.detail-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.detail-label {
  flex-shrink: 0;
  width: 56px;
  color: var(--n-text-color-3);
  font-size: 11px;
  font-weight: 500;
}

.detail-value {
  flex: 1;
  display: flex;
  align-items: center;
  gap: 6px;
  color: var(--n-text-color);
  font-variant-numeric: tabular-nums;
  font-size: 12px;
}

.substep-badge {
  display: inline-block;
  padding: 1px 8px;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 600;
  background: rgba(99, 102, 241, 0.12);
  color: #6366f1;
}

.substep-badge.substep-active {
  background: rgba(34, 197, 94, 0.15);
  color: #16a34a;
  animation: pulse-subtle 2s infinite;
}

.substep-badge.substep-prepare {
  background: rgba(59, 130, 246, 0.12);
  color: #3b82f6;
}

.substep-badge.substep-finish {
  background: rgba(249, 115, 22, 0.12);
  color: #f97316;
}

.substep-badge.substep-audit {
  background: rgba(234, 179, 8, 0.12);
  color: #ca8a04;
}

.substep-badge.substep-plan {
  background: rgba(59, 130, 246, 0.12);
  color: #3b82f6;
}

@keyframes pulse-subtle {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.7; }
}

.pct-tag {
  font-size: 10px;
  padding: 0 4px;
  border-radius: 3px;
  background: rgba(34, 197, 94, 0.12);
  color: #16a34a;
  font-weight: 600;
}

.mini-progress {
  width: 50px;
  height: 3px;
  background: rgba(0, 0, 0, 0.08);
  border-radius: 2px;
  overflow: hidden;
}

.mini-progress-fill {
  height: 100%;
  background: linear-gradient(90deg, #6366f1, #818cf8);
  border-radius: 2px;
  transition: width 0.5s ease;
}

.mini-progress-fill.word-fill {
  background: linear-gradient(90deg, #22c55e, #4ade80);
}

.focus-text {
  font-size: 11px;
  color: var(--n-text-color-2);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 200px;
}

@media (max-width: 720px) {
  .ap-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}

.recovery-hint p { margin: 0 0 6px; line-height: 1.5; }
.recovery-sub { font-size: 11px; opacity: 0.95; margin-bottom: 8px !important; }
</style>
