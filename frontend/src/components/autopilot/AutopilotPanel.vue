<template>
  <div class="autopilot-panel">
    <!-- 状态头 -->
    <div class="ap-header">
      <span class="ap-dot" :class="dotClass"></span>
      <span class="ap-title">全托管驾驶</span>
      <span class="ap-stage-tag" :class="stageTagClass">{{ stageLabel }}</span>
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
        <div class="label">当前章 / 幕 / 节拍</div>
        <div class="value">
          <template v-if="status?.current_chapter_number != null && isWriting">
            第 {{ status.current_chapter_number }} 章 ·
          </template>
          第 {{ (status?.current_act || 0) + 1 }} 幕
          <span v-if="isWriting">· {{ beatLabel }}</span>
        </div>
      </div>
      <div class="ap-cell">
        <div class="label">上章张力</div>
        <div class="value" :style="{ color: tensionColor }">{{ tensionLabel }}</div>
      </div>
    </div>

    <!-- 单本挂起 / 失败计数过高：与监控大盘「熔断保护 → 重置」同源接口 -->
    <n-alert v-if="needsRecovery" type="error" :show-icon="true" style="margin: 4px 0; font-size: 12px">
      <div class="recovery-hint">
        <p v-if="status?.autopilot_status === 'error'">
          本书已因<strong>连续失败</strong>被标为<strong>异常挂起</strong>（守护进程会停止处理本书）。
        </p>
        <p v-else>
          已连续失败 <strong>{{ status?.consecutive_error_count || 0 }}</strong> 次（达到 3 次会挂起）。
        </p>
        <p class="recovery-sub">
          全局 LLM 熔断在守护进程内，无法在此直接展示。下方按钮与「监控大盘 → 熔断保护 → 重置」相同：清零计数并解除异常，然后可重新点「启动全托管」。
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

    <!-- 审阅等待：宏观规划完成后、或某一幕「首次」生成章节规划后各需确认一次；确认后同幕不会反复要求审批 -->
    <n-alert v-if="needsReview" type="warning" :show-icon="true" style="margin: 4px 0; font-size: 12px">
      <strong>待审阅确认</strong>：请在侧栏查看刚生成的大纲/结构，确认后点
      <strong>「确认大纲，继续写作」</strong>。
      宏观规划完成后会停一次；之后每一幕<strong>仅在首次生成该幕章节规划</strong>时再停一次，不会无限循环。
    </n-alert>

    <!-- 仅流式正文预览（与监控大盘终端日志分离，避免双 SSE 卡顿） -->
    <AutopilotWritingStream
      v-if="isRunning"
      :writing-content="writingContent"
      :writing-chapter-number="writingChapterNumber"
      :writing-beat-index="writingBeatIndex"
    />

    <!-- 操作按钮 -->
    <n-space justify="end" size="small">
      <n-button v-if="needsReview" type="warning" size="small" :loading="toggling" @click="resume">
        确认大纲，继续写作
      </n-button>
      <n-button v-if="!isRunning && !needsReview" type="primary" size="small" :loading="toggling" @click="openStartModal">
        🚀 启动全托管
      </n-button>
      <n-button v-if="isRunning" type="error" ghost size="small" :loading="toggling" @click="stop">
        ⏹ 停止
      </n-button>
    </n-space>

    <!-- 启动配置弹窗 -->
    <n-modal v-model:show="showStartModal" title="启动全托管" preset="dialog" positive-text="启动" @positive-click="start">
      <n-space vertical :size="12" style="width: 100%">
        <n-alert type="success" :show-icon="true" style="font-size: 12px">
          <strong>自动托管</strong>：守护进程已在后端自动启动，配置好参数后点击"启动"即可开始自动写作。
        </n-alert>
        <n-form>
          <!-- 目标章数（可编辑） -->
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
          <!-- 保护上限 -->
          <n-form-item label="保护上限（章节数，防止意外消耗）">
            <n-input-number 
              v-model:value="startConfig.max_auto_chapters" 
              :min="startConfig.target_chapters"
              :max="9999"
              :step="10"
              style="width: 100%"
            />
          </n-form-item>
          
          <!-- 全自动模式开关 -->
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
              达到 <strong>{{ startConfig.target_chapters }} 章</strong> 目标时自动完成全书；保护上限已自动设置为 <strong>目标 + 20</strong>。
            </template>
          </n-alert>
          <n-text depth="3" style="font-size: 11px; line-height: 1.5; display: block; margin-top: 4px">
            目标章数与每章字数与首页「目标篇幅」同一套落库字段（PUT /novels），可在此微调后再启动；节拍拆分与上方进度说明一致。
          </n-text>
        </n-form>
      </n-space>
    </n-modal>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { useMessage } from 'naive-ui'
import AutopilotWritingStream from './AutopilotWritingStream.vue'
import { subscribeChapterStream } from '../../api/config'

const props = defineProps({ novelId: String })
const emit = defineEmits(['status-change', 'chapter-content-update', 'chapter-start', 'chapter-chunk'])
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

// 目标章数（从 status 获取）
const targetChapters = computed(() => status.value?.target_chapters || 100)

/** 与后端 target_plan_total_words 一致；旧接口无该字段时本地推算 */
const planTotalWordsHint = computed(() => {
  const s = status.value
  if (!s) return 0
  if (s.target_plan_total_words != null && s.target_plan_total_words > 0) {
    return s.target_plan_total_words
  }
  const tc = s.target_chapters ?? 0
  const tw = s.target_words_per_chapter ?? 2500
  return tc * tw
})
/** 驾驶舱仅保留章节内容流；全量日志在监控大盘终端（单 /stream） */
let statusPollTimer = null
/** novel_id 在库中不存在(404)时不再轮询，避免旧标签页/错 slug 刷屏访问日志 */
const statusPollDisabled = ref(false)

// 计算属性
const isRunning  = computed(() => status.value?.autopilot_status === 'running')
const needsReview = computed(() => status.value?.needs_review === true)
const isWriting  = computed(() => status.value?.current_stage === 'writing')
/** 需人工解除：异常挂起，或连续失败已达阈值 */
const needsRecovery = computed(
  () =>
    status.value?.autopilot_status === 'error' ||
    (status.value?.consecutive_error_count || 0) >= 3
)
/** 无完稿时用语稿章节进度条，避免规划落库后仍显示 0% */
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
  'dot-review':  needsReview.value,
  'dot-error':   status.value?.autopilot_status === 'error',
  'dot-stopped': !isRunning.value && !needsReview.value,
}))

const stageLabel = computed(() => {
  const m = {
    macro_planning: '宏观规划', act_planning: '幕级规划',
    writing: '撰写中', auditing: '审计中',
    paused_for_review: '待审阅', completed: '已完成',
  }
  return m[status.value?.current_stage] || '待机'
})

const stageTagClass = computed(() => ({
  'tag-active':  isRunning.value && !needsReview.value,
  'tag-review':  needsReview.value,
  'tag-idle':    !isRunning.value && !needsReview.value,
}))

/** 与守护进程一致：current_beat_index 为 0-based「下一节拍索引」，展示为 1-based 与 /autopilot/stream 日志对齐 */
const beatLabel = computed(() => {
  if (!isWriting.value) return ''
  const b = status.value?.current_beat_index ?? 0
  return `节拍 ${Number(b) + 1}`
})

const tensionLabel = computed(() => {
  const t = status.value?.last_chapter_tension || 0
  if (t >= 8) return `🔥 高潮 (${t}/10)`
  if (t >= 5) return `⚡ 冲突 (${t}/10)`
  return `🌊 平缓 (${t}/10)`
})

const tensionColor = computed(() => {
  const t = status.value?.last_chapter_tension || 0
  return t >= 8 ? '#d03050' : t >= 5 ? '#f0a020' : '#18a058'
})

// 格式化
function formatWords(n) {
  if (!n) return '0'
  return n >= 10000 ? `${(n / 10000).toFixed(1)}万` : String(n)
}

// API 调用
const base = () => `/api/v1/autopilot/${props.novelId}`

async function fetchStatus() {
  const res = await fetch(`${base()}/status`)
  if (res.status === 404) {
    clearStatusPoll()
    status.value = null
    statusPollDisabled.value = true
    return
  }
  if (res.ok) {
    status.value = await res.json()
    emit('status-change', status.value)
  }
}

function clearStatusPoll() {
  if (statusPollTimer) {
    clearInterval(statusPollTimer)
    statusPollTimer = null
  }
}

watch(
  () => [isRunning.value, needsReview.value],
  ([running, review]) => {
    clearStatusPoll()
    if (statusPollDisabled.value) return
    if (running || review) {
      statusPollTimer = setInterval(() => fetchStatus(), 3000)
      void fetchStatus()
    }
  },
  { immediate: true }
)

watch(
  () => props.novelId,
  () => {
    statusPollDisabled.value = false
  }
)

function openStartModal() {
  // 打开弹窗时，从当前状态初始化设置（与 GET /autopilot/.../status 一致）
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
  // 当目标章数改变时，自动调整保护上限
  const target = startConfig.value.target_chapters
  if (startConfig.value.max_auto_chapters < target + 20) {
    startConfig.value.max_auto_chapters = target + 20
  }
}

async function start() {
  toggling.value = true
  try {
    const currentTarget = status.value?.target_chapters
    const newTarget = startConfig.value.target_chapters
    const currentWpc = status.value?.target_words_per_chapter ?? 2500
    const newWpc = startConfig.value.target_words_per_chapter
    const currentAutoApprove = status.value?.auto_approve_mode ?? false
    const newAutoApprove = startConfig.value.auto_approve_mode

    const novelPatch = {}
    if (currentTarget !== newTarget) {
      novelPatch.target_chapters = newTarget
    }
    if (currentWpc !== newWpc) {
      novelPatch.target_words_per_chapter = newWpc
    }

    if (Object.keys(novelPatch).length > 0) {
      const updateRes = await fetch(`/api/v1/novels/${props.novelId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(novelPatch)
      })
      if (!updateRes.ok) {
        message.error('更新书目目标章数或每章字数失败')
        return
      }
    }

    if (currentAutoApprove !== newAutoApprove) {
      const approveRes = await fetch(`/api/v1/novels/${props.novelId}/auto-approve-mode`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          auto_approve_mode: newAutoApprove
        })
      })
      if (!approveRes.ok) {
        message.error('更新全自动模式失败')
        return
      }
    }
    
    // 然后启动自动驾驶
    const res = await fetch(`${base()}/start`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        max_auto_chapters: startConfig.value.max_auto_chapters
      })
    })
    if (res.ok) {
      const modeText = startConfig.value.auto_approve_mode ? '（全自动模式）' : ''
      message.success(`自动驾驶已启动${modeText}`)
    }
    else message.error('启动失败')
    await fetchStatus()
  } finally {
    toggling.value = false
  }
}

async function stop() {
  toggling.value = true
  await fetch(`${base()}/stop`, { method: 'POST' })
  message.info('已停止')
  await fetchStatus()
  toggling.value = false
}

async function resume() {
  toggling.value = true
  const res = await fetch(`${base()}/resume`, { method: 'POST' })
  if (res.ok) message.success('已确认大纲，开始写作')
  else { const e = await res.json(); message.error(e.detail || '恢复失败') }
  await fetchStatus()
  toggling.value = false
}

async function clearCircuitBreaker() {
  toggling.value = true
  try {
    const res = await fetch(`${base()}/circuit-breaker/reset`, { method: 'POST' })
    if (res.ok) {
      message.success('已解除挂起并清零失败计数，可重新启动全托管')
      await fetchStatus()
    } else {
      message.error('操作失败，请确认后端已更新并稍后重试')
    }
  } finally {
    toggling.value = false
  }
}

// 章节内容流订阅（用于推送内容到编辑框）
let chapterStreamCtrl = null

// 写作内容状态（传递给 AutopilotWritingStream）
const writingContent = ref('')
const writingChapterNumber = ref(0)
const writingBeatIndex = ref(0)

function startChapterStream() {
  if (chapterStreamCtrl) {
    chapterStreamCtrl.abort()
  }
  writingContent.value = ''
  writingChapterNumber.value = 0
  writingBeatIndex.value = 0

  chapterStreamCtrl = subscribeChapterStream(props.novelId, {
    onChapterStart: (num) => {
      writingChapterNumber.value = num
      writingContent.value = ''
      writingBeatIndex.value = 0
      emit('chapter-start', num)
    },
    onChapterChunk: (chunk, beatIndex) => {
      // 真正的流式：增量追加文字
      writingContent.value += chunk
      writingBeatIndex.value = beatIndex
      emit('chapter-chunk', { chunk, beatIndex, content: writingContent.value })
    },
    onChapterContent: (data) => {
      // 向后兼容：完整内容
      writingContent.value = data.content
      writingChapterNumber.value = data.chapterNumber
      writingBeatIndex.value = data.beatIndex
      emit('chapter-content-update', data)
    },
    onConnected: () => {
      // SSE连接成功
    },
    onDisconnected: () => {
      // SSE连接断开
    },
    onError: (err) => {
      console.error('Chapter stream error:', err)
    }
  })
}

function stopChapterStream() {
  if (chapterStreamCtrl) {
    chapterStreamCtrl.abort()
    chapterStreamCtrl = null
  }
}

watch(
  () => isRunning.value,
  (running) => {
    if (running) {
      startChapterStream()
    } else {
      stopChapterStream()
    }
  }
)

onMounted(() => { fetchStatus() })
onUnmounted(() => {
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
  transition: all 0.3s ease;
}

.autopilot-panel:hover {
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08);
  border-color: rgba(24, 160, 88, 0.25);
}

.ap-header {
  display: flex;
  align-items: center;
  gap: 10px;
}

.ap-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  flex-shrink: 0;
  box-shadow: 0 0 8px currentColor;
}

.dot-running {
  background: #18a058;
  animation: pulse 1.4s ease-in-out infinite;
}

.dot-review {
  background: #f0a020;
  animation: pulse 0.8s ease-in-out infinite;
}

.dot-error {
  background: #d03050;
}

.dot-stopped {
  background: #999;
}

@keyframes pulse {
  0%, 100% {
    opacity: 1;
    transform: scale(1);
  }
  50% {
    opacity: 0.5;
    transform: scale(0.9);
  }
}

.ap-title {
  font-weight: 600;
  color: var(--n-text-color);
  font-size: 15px;
  letter-spacing: 0.3px;
}

.ap-stage-tag {
  margin-left: auto;
  font-size: 11px;
  padding: 3px 10px;
  border-radius: 12px;
  font-weight: 500;
  letter-spacing: 0.2px;
}

.tag-active {
  background: rgba(24, 160, 88, 0.15);
  color: #18a058;
}

.tag-review {
  background: rgba(240, 160, 32, 0.15);
  color: #f0a020;
}

.tag-idle {
  background: rgba(100, 100, 100, 0.1);
  color: #999;
}

.ap-plan-hint {
  margin: 0 0 8px;
  font-size: 11px;
  line-height: 1.55;
  color: var(--app-text-secondary, #64748b);
}

.ap-plan-hint strong {
  color: var(--app-text-primary, #111827);
  font-weight: 600;
}

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
  transition: background 0.2s ease;
}

.ap-cell:hover {
  background: rgba(255, 255, 255, 0.6);
}

.ap-cell .label {
  font-size: 10px;
  color: var(--n-text-color-3);
  margin-bottom: 2px;
  font-weight: 500;
  line-height: 1.25;
}

.ap-cell .value {
  font-size: 13px;
  font-weight: 600;
  color: var(--n-text-color);
  font-variant-numeric: tabular-nums;
  line-height: 1.3;
  word-break: break-word;
}

@media (max-width: 720px) {
  .ap-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

.recovery-hint p {
  margin: 0 0 6px;
  line-height: 1.5;
}

.recovery-sub {
  font-size: 11px;
  opacity: 0.95;
  margin-bottom: 8px !important;
}
</style>
