<template>
  <n-modal
    v-model:show="show"
    preset="card"
    style="width: min(760px, 96vw); max-height: min(92vh, 860px)"
    :mask-closable="false"
    :segmented="{ content: true, footer: 'soft' }"
    title="🎯 启动结构规划"
  >
    <template #header-extra>
      <n-text depth="3" style="font-size: 12px">选择规划模式，AI 生成叙事骨架</n-text>
    </template>

    <!-- 模式选择选项卡 -->
    <n-tabs v-if="!generated" v-model:value="planMode" type="segment" animated style="margin-bottom: 16px">
      <n-tab-pane name="quick" tab="⚡ 快速生成">
        <n-space vertical :size="16" style="padding: 16px 0">
          <n-alert type="info" :show-icon="true">
            只需一键，让 AI 基于您的世界观和人物，瞬间生成一套最具商业潜力的宏观叙事骨架。
          </n-alert>
          <n-card size="small" :bordered="false" style="background: var(--n-color-target)">
            <n-space vertical :size="8">
              <n-text strong>✨ 适合场景</n-text>
              <n-ul style="margin: 0; padding-left: 20px">
                <n-li>新手作者，快速起步</n-li>
                <n-li>信任 AI 判断，追求效率</n-li>
                <n-li>不确定具体结构，想要灵感</n-li>
              </n-ul>
            </n-space>
          </n-card>
        </n-space>
      </n-tab-pane>

      <n-tab-pane name="precise" tab="📐 精密定制">
        <n-space vertical :size="16" style="padding: 16px 0">
          <n-alert type="info" :show-icon="true">
            自主设定目标篇幅与卷幕比例，精确掌控小说的节奏与体量。
          </n-alert>

          <n-card title="规划参数" size="small" :bordered="false">
            <n-space vertical :size="14">
              <n-form-item label="目标章节数" label-placement="left" label-width="100" :show-feedback="false">
                <n-input-number
                  v-model:value="form.target_chapters"
                  :min="minChapters"
                  :max="1000"
                  :step="10"
                  style="width: 140px"
                />
                <n-text depth="3" style="margin-left:8px;font-size:12px">章（{{ minChapters }}-1000）</n-text>
              </n-form-item>

              <n-form-item label="结构分布" label-placement="left" label-width="100" :show-feedback="false">
                <n-space :size="12" align="center" wrap>
                  <n-space align="center" :size="4">
                    <n-text style="font-size:13px">部</n-text>
                    <n-input-number v-model:value="form.structure.parts" :min="1" :max="10" style="width:72px" size="small" />
                  </n-space>
                  <n-text depth="3">×</n-text>
                  <n-space align="center" :size="4">
                    <n-text style="font-size:13px">卷/部</n-text>
                    <n-input-number v-model:value="form.structure.volumes_per_part" :min="1" :max="10" style="width:72px" size="small" />
                  </n-space>
                  <n-text depth="3">×</n-text>
                  <n-space align="center" :size="4">
                    <n-text style="font-size:13px">幕/卷</n-text>
                    <n-input-number v-model:value="form.structure.acts_per_volume" :min="1" :max="10" style="width:72px" size="small" />
                  </n-space>
                  <n-tag type="info" size="small" round>
                    共 {{ totalActs }} 幕
                  </n-tag>
                </n-space>
              </n-form-item>

              <!-- 节奏预览 -->
              <n-alert v-if="chaptersPerAct > 0" type="default" :show-icon="false" style="margin-top: 8px">
                <n-space vertical :size="4">
                  <n-text depth="2" style="font-size: 12px">
                    💡 节奏预览：您的故事结构平均每幕将包含约 <n-text strong>{{ chaptersPerAct }}</n-text> 章
                  </n-text>
                  <n-text depth="3" style="font-size: 11px">
                    {{ pacingHint }}
                  </n-text>
                </n-space>
              </n-alert>

              <n-card v-if="loading" size="small" :bordered="false" style="background: var(--n-color-target)">
                <n-space vertical :size="10">
                  <n-text strong>结构生成中</n-text>
                  <n-progress
                    type="line"
                    :percentage="macroProgress.percent"
                    :indicator-placement="'inside'"
                    processing
                  />
                  <n-text depth="3" style="font-size: 12px">
                    {{ macroProgress.message || '正在生成叙事骨架...' }}
                  </n-text>
                </n-space>
              </n-card>
            </n-space>
          </n-card>
        </n-space>
      </n-tab-pane>
    </n-tabs>

    <!-- Step 2：预览 + 编辑 -->
    <n-scrollbar v-if="generated" style="max-height: min(76vh, 720px)">
      <n-space vertical :size="16">
        <n-alert type="success" :show-icon="true">
          已生成 {{ structurePreview.length }} 个顶层节点的叙事骨架，可直接编辑标题和描述后确认写入。
        </n-alert>

        <n-scrollbar style="max-height:52vh">
          <n-space vertical :size="6" style="padding-right:8px">
            <n-card
              v-for="(node, idx) in structurePreview"
              :key="idx"
              size="small"
              :bordered="true"
              style="background: var(--n-color)"
            >
              <template #header>
                <n-space align="center" :size="8">
                  <n-tag :type="node.type === 'part' ? 'error' : node.type === 'volume' ? 'warning' : 'info'" size="small" round>
                    {{ nodeTypeLabel(node.type) }}
                  </n-tag>
                  <n-input
                    v-model:value="node.node.title"
                    size="small"
                    placeholder="标题"
                    style="flex:1"
                  />
                </n-space>
              </template>
              <n-input
                v-if="node.node.description !== undefined"
                v-model:value="node.node.description"
                type="textarea"
                size="small"
                placeholder="叙事目标（可选）"
                :autosize="{ minRows: 1, maxRows: 3 }"
              />
            </n-card>
          </n-space>
        </n-scrollbar>
      </n-space>
    </n-scrollbar>

    <template #footer>
      <n-space justify="space-between">
        <n-button @click="handleClose" :disabled="loading || confirming">取消</n-button>
        <n-space :size="8">
          <n-button v-if="generated" secondary @click="reset">重新生成</n-button>
          <n-button
            v-if="!generated"
            type="primary"
            :loading="loading"
            @click="doGenerate"
          >
            {{ planMode === 'quick' ? '⚡ 一键生成' : '📐 生成框架' }}
          </n-button>
          <n-button
            v-else
            type="primary"
            :loading="confirming"
            @click="doConfirm"
          >
            确认写入结构树
          </n-button>
        </n-space>
      </n-space>
    </template>
  </n-modal>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { useMessage } from 'naive-ui'
import {
  planningApi,
  type MacroPartNode,
  type MacroPlanProgress,
  type MacroPlanResultPayload,
} from '../../api/planning'
import { workflowApi } from '../../api/workflow'

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

const planMode = ref<'quick' | 'precise'>('quick')

const form = ref({
  target_chapters: 100,
  structure: { parts: 3, volumes_per_part: 3, acts_per_volume: 3 },
})

// 计算总幕数
const totalActs = computed(() =>
  form.value.structure.parts * form.value.structure.volumes_per_part * form.value.structure.acts_per_volume
)

// 动态最小章数（必须 >= 总幕数）
const minChapters = computed(() => Math.max(10, totalActs.value))

// 节奏预览：平均每幕章数
const chaptersPerAct = computed(() => {
  if (totalActs.value === 0) return 0
  return Math.floor(form.value.target_chapters / totalActs.value)
})

// 节奏感知提示
const pacingHint = computed(() => {
  const avg = chaptersPerAct.value
  if (avg === 0) return ''
  if (avg <= 5) return '极速节奏：适合短篇或快节奏爽文'
  if (avg <= 15) return '紧凑节奏：适合美剧式快节奏叙事'
  if (avg <= 30) return '标准节奏：适合传统长篇小说'
  if (avg <= 50) return '舒缓节奏：适合慢热修仙/史诗类'
  return '超长节奏：适合超大型史诗巨著'
})

const loading = ref(false)
const confirming = ref(false)
const generated = ref(false)
const rawResult = ref<Record<string, unknown> | null>(null)
const editableStructure = ref<MacroPartNode[]>([])
const structurePreview = ref<{
  type: string
  node: Record<string, unknown>
}[]>([])
const macroProgress = ref<MacroPlanProgress>({
  status: 'idle',
  current: 0,
  total: 0,
  percent: 0,
  message: '',
})
let progressTimer: ReturnType<typeof setInterval> | null = null
let resultWaiter: Promise<MacroPlanResultPayload> | null = null

const nodeTypeLabel = (type: string) => {
  const map: Record<string, string> = { part: '部', volume: '卷', act: '幕', chapter: '章' }
  return map[type] || type
}

const flattenStructure = (parts: MacroPartNode[]) => {
  const result: { type: string; node: Record<string, unknown> }[] = []

  const walkActs = (acts: unknown[]) => {
    for (const act of acts) {
      result.push({ type: 'act', node: act as Record<string, unknown> })
    }
  }

  const walkVolumes = (volumes: unknown[]) => {
    for (const volume of volumes) {
      const volumeNode = volume as Record<string, unknown>
      result.push({ type: 'volume', node: volumeNode })
      if (Array.isArray(volumeNode.acts)) {
        walkActs(volumeNode.acts)
      }
    }
  }

  for (const part of parts) {
    const partNode = part as Record<string, unknown>
    result.push({ type: 'part', node: partNode })
    if (Array.isArray(partNode.volumes)) {
      walkVolumes(partNode.volumes)
    }
  }

  return result
}

const stopProgressPolling = () => {
  if (progressTimer) {
    clearInterval(progressTimer)
    progressTimer = null
  }
}

const pollMacroProgress = async () => {
  if (planMode.value !== 'precise') return
  try {
    const res = await planningApi.getMacroProgress(props.novelId)
    macroProgress.value = res.data
    if (res.data.status === 'failed') {
      stopProgressPolling()
    }
  } catch {
    // 进度轮询失败时不打断主流程
  }
}

const waitForMacroResult = async (): Promise<MacroPlanResultPayload> => {
  while (true) {
    const [progressRes, resultRes] = await Promise.all([
      planningApi.getMacroProgress(props.novelId),
      planningApi.getMacroResult(props.novelId),
    ])
    macroProgress.value = progressRes.data

    if (progressRes.data.status === 'completed' && resultRes.data.ready && resultRes.data.result) {
      stopProgressPolling()
      return resultRes.data.result
    }

    if (progressRes.data.status === 'failed' || resultRes.data.error) {
      stopProgressPolling()
      throw new Error(resultRes.data.error || progressRes.data.message || '生成失败')
    }

    if (progressRes.data.percent >= 100 && progressRes.data.status === 'completed') {
      macroProgress.value = {
        ...progressRes.data,
        message: '正在整理结果...',
      }
    }

    await new Promise(resolve => setTimeout(resolve, 1200))
  }
}

const startProgressPolling = () => {
  stopProgressPolling()
  resultWaiter = null
  macroProgress.value = {
    status: 'running',
    current: 0,
    total: form.value.structure.parts * form.value.structure.volumes_per_part,
    percent: 0,
    message: '正在准备结构规划...',
  }
  pollMacroProgress()
  progressTimer = setInterval(() => {
    void pollMacroProgress()
  }, 1200)
}

const doGenerate = async () => {
  loading.value = true
  try {
    let res: Record<string, unknown>

    if (planMode.value === 'quick') {
      // 快速模式：调用 plan_novel API（AI 自主决定结构）
      res = await workflowApi.planNovel(props.novelId, 'initial', false) as unknown as Record<string, unknown>

      // plan_novel 直接写入了结构，显示成功消息并等待一下让用户看到
      message.success('AI 已自动生成并写入叙事结构，正在刷新...', { duration: 2000 })

      // 等待一小段时间让消息显示，然后触发刷新
      await new Promise(resolve => setTimeout(resolve, 500))

      emit('confirmed')
      closeModal()
      return
    } else {
      // 精密模式：调用 generate_macro API（用户指定结构）
      startProgressPolling()
      await planningApi.generateMacro(props.novelId, form.value)
      resultWaiter = waitForMacroResult()
      res = await resultWaiter as unknown as Record<string, unknown>
    }

    rawResult.value = res
    const structure = Array.isArray(res.structure) ? res.structure as MacroPartNode[] : []
    editableStructure.value = structure
    structurePreview.value = flattenStructure(editableStructure.value)
    if (structurePreview.value.length === 0) {
      structurePreview.value = [{ type: 'part', node: { title: '（AI 返回格式未识别，请查看控制台）' } }]
    }
    generated.value = true
  } catch (e: unknown) {
    const err = e as { response?: { data?: { detail?: string } } }
    message.error(err?.response?.data?.detail || '生成失败，请确认 AI 密钥已配置')
  } finally {
    stopProgressPolling()
    resultWaiter = null
    loading.value = false
  }
}

const doConfirm = async () => {
  confirming.value = true
  try {
    const res = await planningApi.confirmMacro(props.novelId, { structure: editableStructure.value as Record<string, unknown>[] }) as any

    // 解析后端返回的 summary 状态
    const summary = res?.summary || {}
    const status = summary.status || 'GREEN'

    if (status === 'GREEN') {
      // 绿色通路：纯空框架覆盖
      message.success(summary.message || '结构框架已写入结构树')
      emit('confirmed')
      closeModal()
    } else if (status === 'YELLOW') {
      // 黄色通路：安全合并
      message.warning(summary.message || '已安全合并，保留已有正文')
      emit('confirmed')
      closeModal()
    } else {
      // 未知状态，默认成功
      message.success('结构框架已写入结构树')
      emit('confirmed')
      closeModal()
    }
  } catch (e: unknown) {
    const err = e as { response?: { status?: number; data?: { detail?: any } } }

    // 检查是否是 409 Conflict（红色阻断）
    if (err?.response?.status === 409) {
      const detail = err.response.data?.detail
      const conflicts = detail?.conflicts || []

      // 构建冲突详情消息
      let conflictMsg = '⚠️ 致命冲突！新结构删除了包含已有正文的节点：\n\n'
      conflicts.forEach((c: any) => {
        conflictMsg += `• ${c.title || c.node_id} (${c.node_type})\n`
      })
      conflictMsg += '\n请手动清理这些正文，或修改结构比例后再试。'

      message.error(conflictMsg, { duration: 8000 })
    } else {
      // 其他错误
      const errorMsg = typeof err?.response?.data?.detail === 'string'
        ? err.response.data.detail
        : '写入失败'
      message.error(errorMsg)
    }
  } finally {
    confirming.value = false
  }
}

const reset = () => {
  stopProgressPolling()
  generated.value = false
  rawResult.value = null
  editableStructure.value = []
  structurePreview.value = []
  macroProgress.value = {
    status: 'idle',
    current: 0,
    total: 0,
    percent: 0,
    message: '',
  }
}

const closeModal = () => {
  reset()
  show.value = false
}

const handleClose = () => {
  if (loading.value || confirming.value) return
  closeModal()
}
</script>
