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
        <div class="label">当前幕 / 节拍</div>
        <div class="value">
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

    <!-- 实时日志流 -->
    <RealtimeLogStream
      v-if="isRunning"
      :novel-id="novelId"
      :writing-content="writingContent"
      :writing-chapter-number="writingChapterNumber"
      :writing-beat-index="writingBeatIndex"
      @desk-refresh="emit('desk-refresh')"
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
          <strong>自动托管</strong>：守护进程已在后端自动启动，配置好<strong>预计总章数</strong>和<strong>当次计划参数</strong>后点击"启动"即可开始自动写作。
        </n-alert>
        <n-alert type="info" :show-icon="false" style="font-size: 12px">
          目标章节数沿用项目当前配置。这里仅配置本次托管启动参数，避免重复维护同一套目标。
        </n-alert>
        <n-form>
          <n-form-item label="目标章数">
            <n-input :value="targetChapterSummary" readonly />
          </n-form-item>
          <!-- 保护上限 -->
          <n-form-item label="当次计划上限（本次最多先写到第几章）">
            <n-input-number 
              v-model:value="startConfig.max_auto_chapters" 
              :min="targetChapters"
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

          <!-- 专项题材 Agent 开关 -->
          <n-form-item label="专项题材增强">
            <n-space align="center" justify="space-between" style="width: 100%">
              <n-switch
                v-model:value="startConfig.theme_agent_enabled"
                :round="false"
                :disabled="!currentGenre"
              >
                <template #checked>开启</template>
                <template #unchecked>关闭</template>
              </n-switch>
              <n-text depth="3" style="font-size: 12px">
                {{ currentGenre ? `启用「${currentGenreLabel}」题材专项写作能力` : '请先在顶栏选择题材' }}
              </n-text>
            </n-space>
          </n-form-item>

          <!-- 增强技能选择（仅在题材 Agent 开启时显示） -->
          <n-form-item v-if="startConfig.theme_agent_enabled && currentGenre" label="增强技能">
            <n-space vertical :size="8" style="width: 100%">
              <n-spin :show="loadingSkills" size="small">
                <template v-if="availableSkills.length > 0">
                  <n-checkbox-group v-model:value="startConfig.enabled_theme_skills">
                    <n-space vertical :size="4">
                      <div v-for="skill in availableSkills" :key="skill.key" class="skill-item">
                        <n-checkbox :value="skill.key">
                          <n-text>{{ skill.name }}</n-text>
                          <n-tag v-if="skill.source === 'custom'" size="tiny" type="info" style="margin-left: 4px">自定义</n-tag>
                          <n-text v-if="skill.description" depth="3" style="font-size: 11px; margin-left: 4px">
                            — {{ skill.description }}
                          </n-text>
                        </n-checkbox>
                        <n-space v-if="skill.source === 'custom'" :size="4" style="margin-left: 4px">
                          <n-button text size="tiny" type="primary" @click.stop="openEditSkill(skill)">编辑</n-button>
                          <n-button text size="tiny" type="error" @click.stop="deleteCustomSkill(skill)">删除</n-button>
                        </n-space>
                      </div>
                    </n-space>
                  </n-checkbox-group>
                </template>
                <template v-else-if="!loadingSkills">
                  <n-text depth="3" style="font-size: 12px">
                    当前题材暂无可用增强技能，可点击下方按钮创建自定义技能
                  </n-text>
                </template>
              </n-spin>

              <!-- 新增自定义技能按钮 -->
              <n-button size="small" dashed type="primary" style="width: 100%" @click="openCreateSkill">
                + 新增自定义技能
              </n-button>
            </n-space>
          </n-form-item>

          <!-- 自定义技能创建/编辑弹窗 -->
          <n-modal
            v-model:show="showSkillEditor"
            :title="editingSkillId ? '编辑自定义技能' : '新增自定义技能'"
            preset="dialog"
            positive-text="保存"
            negative-text="取消"
            style="width: 560px"
            @positive-click="saveCustomSkill"
          >
            <n-space vertical :size="12" style="width: 100%">
              <n-alert type="info" :show-icon="false" style="font-size: 11px">
                自定义技能让你用自然语言定义写作规则，系统会在生成每章时自动注入这些指令。
              </n-alert>
              <n-form label-placement="top" :show-feedback="false">
                <n-form-item label="技能名称" required>
                  <n-input v-model:value="skillForm.skill_name" placeholder="如：宠物描写增强、职场术语规范" maxlength="50" show-count />
                </n-form-item>
                <n-form-item label="技能说明">
                  <n-input v-model:value="skillForm.skill_description" placeholder="简要说明这个技能做什么" maxlength="200" show-count />
                </n-form-item>
                <n-form-item label="上下文提示词">
                  <n-input
                    v-model:value="skillForm.context_prompt"
                    type="textarea"
                    :rows="3"
                    placeholder="每章生成时注入到写作上下文中的指令。例如：&#10;1. 主角的猫必须在每章出现至少一次&#10;2. 描写猫时要体现猫的傲娇性格"
                  />
                </n-form-item>
                <n-form-item label="节拍提示词">
                  <n-input
                    v-model:value="skillForm.beat_prompt"
                    type="textarea"
                    :rows="2"
                    placeholder="每个节拍（段落）生成时注入的指令。例如：&#10;对话场景中角色说话方式要有区分度"
                  />
                </n-form-item>
                <n-form-item label="节拍触发关键词">
                  <n-input
                    v-model:value="skillForm.beat_triggers"
                    placeholder="逗号分隔，为空则对所有节拍生效。如：战斗,对决,交锋"
                  />
                </n-form-item>
                <n-form-item label="审计检查项">
                  <n-dynamic-input
                    v-model:value="skillForm.audit_checks"
                    placeholder="每章写完后的审计检查点。如：检查主角的猫是否出场"
                  />
                </n-form-item>
              </n-form>
            </n-space>
          </n-modal>
          
          <n-alert type="info" :show-icon="false" style="font-size: 11px; margin-top: -8px">
            <template v-if="startConfig.auto_approve_mode">
              <strong>全自动模式已开启</strong>：系统将跳过所有审阅环节，自动运行直到写完。
            </template>
            <template v-else>
              达到 <strong>{{ targetChapters }} 章</strong> 目标时自动完成全书；保护上限建议至少为 <strong>目标 + 20</strong>。
            </template>
            <template v-if="startConfig.theme_agent_enabled && currentGenre">
              <br/>🎯 <strong>专项题材增强已开启</strong>：将使用「{{ currentGenreLabel }}」题材的专项写作能力（人设、节拍、规则）。
              <template v-if="startConfig.enabled_theme_skills && startConfig.enabled_theme_skills.length > 0">
                <br/>🧩 已选 <strong>{{ startConfig.enabled_theme_skills.length }}</strong> 个增强技能。
              </template>
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
import RealtimeLogStream from './RealtimeLogStream.vue'
import { subscribeChapterStream } from '../../api/config'
import { novelApi } from '../../api/novel'

const props = defineProps({ novelId: String })
const emit = defineEmits(['status-change', 'desk-refresh', 'chapter-content-update', 'chapter-start', 'chapter-chunk'])
const message = useMessage()

const status = ref(null)
const toggling = ref(false)
const showStartModal = ref(false)
const startConfig = ref({
  max_auto_chapters: 120,
  auto_approve_mode: false,
  theme_agent_enabled: false,
  enabled_theme_skills: []
})

// 增强技能状态
const availableSkills = ref([])
const loadingSkills = ref(false)

// 自定义技能编辑器状态
const showSkillEditor = ref(false)
const editingSkillId = ref(null)
const skillForm = ref({
  skill_name: '',
  skill_description: '',
  context_prompt: '',
  beat_prompt: '',
  beat_triggers: '',
  audit_checks: [],
})

// 目标章数（从 status 获取）
const targetChapters = computed(() => status.value?.target_chapters || 100)
const targetChapterSummary = computed(() => `当前项目目标 ${targetChapters.value} 章`)

// 题材信息（用于专项题材 Agent 开关的描述文案）
const genreMap = {
  xuanhuan: '玄幻', dushi: '都市', scifi: '科幻', history: '历史',
  wuxia: '武侠', xianxia: '仙侠', fantasy: '奇幻', game: '游戏',
  suspense: '悬疑', romance: '言情', other: '其他'
}
const currentGenre = computed(() => status.value?.genre || '')
const currentGenreLabel = computed(() => genreMap[currentGenre.value] || currentGenre.value || '')

async function fetchAvailableSkills() {
  if (!props.novelId || !currentGenre.value) {
    availableSkills.value = []
    return
  }
  loadingSkills.value = true
  try {
    const data = await novelApi.getAvailableThemeSkills(props.novelId)
    availableSkills.value = data.available_skills || []
    if (startConfig.value.enabled_theme_skills.length === 0 && availableSkills.value.length > 0) {
      startConfig.value.enabled_theme_skills = availableSkills.value.map(s => s.key)
    }
  } catch (e) {
    console.error('Failed to fetch available skills:', e)
  } finally {
    loadingSkills.value = false
  }
}

watch(
  () => startConfig.value.theme_agent_enabled,
  (enabled) => {
    if (enabled && currentGenre.value) fetchAvailableSkills()
    else availableSkills.value = []
  }
)
/** HTTP/1.1 下同域长连接约 6 路；避免与日志 /stream 双开占满导致其它 API 挂起 */
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

const beatLabel = computed(() => {
  const b = status.value?.current_beat_index || 0
  return b === 0 ? '准备' : `节拍 ${b}`
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
  // 打开弹窗时，从当前状态初始化设置
  const target = status.value?.target_chapters || 100
  const autoApprove = status.value?.auto_approve_mode ?? false
  const themeEnabled = status.value?.theme_agent_enabled ?? false
  const enabledSkills = status.value?.enabled_theme_skills || []
  startConfig.value = {
    max_auto_chapters: target + 20,
    auto_approve_mode: autoApprove,
    theme_agent_enabled: themeEnabled,
    enabled_theme_skills: [...enabledSkills]
  }
  showStartModal.value = true
  // 如果题材增强已开启，立即加载技能列表
  if (themeEnabled && currentGenre.value) {
    fetchAvailableSkills()
  }
}

async function start() {
  toggling.value = true
  try {
    const currentAutoApprove = status.value?.auto_approve_mode ?? false
    const newAutoApprove = startConfig.value.auto_approve_mode

    if (currentAutoApprove !== newAutoApprove) {
      try {
        await novelApi.updateAutoApproveMode(props.novelId, newAutoApprove)
      } catch {
        message.error('更新全自动模式失败')
        return
      }
    }

    // 更新专项题材 Agent 开关
    const currentThemeEnabled = status.value?.theme_agent_enabled ?? false
    const newThemeEnabled = startConfig.value.theme_agent_enabled
    if (currentThemeEnabled !== newThemeEnabled) {
      try {
        await novelApi.updateThemeAgentEnabled(props.novelId, newThemeEnabled)
      } catch {
        message.error('更新专项题材设置失败')
        return
      }
    }

    // 更新增强技能列表
    if (newThemeEnabled) {
      const currentSkills = status.value?.enabled_theme_skills || []
      const newSkills = startConfig.value.enabled_theme_skills || []
      const skillsChanged = JSON.stringify(currentSkills.sort()) !== JSON.stringify([...newSkills].sort())
      if (skillsChanged) {
        try {
          await novelApi.updateEnabledThemeSkills(props.novelId, newSkills)
        } catch {
          message.error('更新增强技能失败')
          return
        }
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
      const themeText = startConfig.value.theme_agent_enabled && currentGenre.value ? `（${currentGenreLabel.value}题材增强）` : ''
      const skillCount = startConfig.value.enabled_theme_skills?.length || 0
      const skillText = startConfig.value.theme_agent_enabled && skillCount > 0 ? `（${skillCount}个增强技能）` : ''
      message.success(`自动驾驶已启动${modeText}${themeText}${skillText}`)
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

// 写作内容状态（传递给 RealtimeLogStream 显示）
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

.skill-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 2px 0;
}

.skill-item:hover {
  background: rgba(24, 160, 88, 0.04);
  border-radius: 4px;
}
</style>
