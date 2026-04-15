<template>
  <n-modal
    v-model:show="modalOpen"
    :mask-closable="false"
    :close-on-esc="false"
    :closable="true"
    preset="card"
    title="新书设置向导"
    style="width: 90%; max-width: 600px; max-height: 90vh"
  >
    <n-steps :current="currentStep" :status="stepStatus" size="small">
      <n-step title="世界观" description="5维度框架" />
      <n-step title="人物" description="主要角色" />
      <n-step title="地图" description="地图系统" />
      <n-step title="故事线" description="主线支线" />
      <n-step title="情节弧" description="剧情曲线" />
      <n-step title="开始" description="进入工作台" />
    </n-steps>

    <div class="step-content">
      <!-- Step 1: Generate Worldbuilding + Style -->
      <div v-if="currentStep === 1" class="step-panel">
        <n-alert v-if="bibleError" type="error" :title="bibleError" style="margin-bottom: 16px" />
        <n-spin :show="generatingBible">
          <div v-if="!bibleGenerated" class="step-info">
            <n-icon size="48" color="#18a058">
              <IconBook />
            </n-icon>
            <h3>{{ bibleStatusText }}</h3>
            <p>AI 正在分析您的故事创意，生成世界观（5维度框架）和文风公约...</p>
          </div>

          <!-- 生成完成后显示预览 -->
          <div v-else class="bible-preview">
            <n-alert type="success" title="世界观生成完成" style="margin-bottom: 16px">
              请查看并确认世界观设定和文风公约，下一步将基于此生成人物和地点。
            </n-alert>

            <n-collapse :default-expanded-names="['worldbuilding', 'style']">
              <n-collapse-item title="世界观（5维度框架）" name="worldbuilding">
                <n-space vertical>
                  <n-card size="small" title="核心法则">
                    <n-space vertical size="small">
                      <div><strong>力量体系：</strong>{{ worldbuildingData.core_rules?.power_system || '待生成' }}</div>
                      <div><strong>物理规律：</strong>{{ worldbuildingData.core_rules?.physics_rules || '待生成' }}</div>
                      <div><strong>魔法/科技：</strong>{{ worldbuildingData.core_rules?.magic_tech || '待生成' }}</div>
                    </n-space>
                  </n-card>
                  <n-card size="small" title="地理生态">
                    <n-space vertical size="small">
                      <div><strong>地形：</strong>{{ worldbuildingData.geography?.terrain || '待生成' }}</div>
                      <div><strong>气候：</strong>{{ worldbuildingData.geography?.climate || '待生成' }}</div>
                      <div><strong>资源：</strong>{{ worldbuildingData.geography?.resources || '待生成' }}</div>
                      <div><strong>生态：</strong>{{ worldbuildingData.geography?.ecology || '待生成' }}</div>
                    </n-space>
                  </n-card>
                  <n-card size="small" title="社会结构">
                    <n-space vertical size="small">
                      <div><strong>政治：</strong>{{ worldbuildingData.society?.politics || '待生成' }}</div>
                      <div><strong>经济：</strong>{{ worldbuildingData.society?.economy || '待生成' }}</div>
                      <div><strong>阶级：</strong>{{ worldbuildingData.society?.class_system || '待生成' }}</div>
                    </n-space>
                  </n-card>
                  <n-card size="small" title="历史文化">
                    <n-space vertical size="small">
                      <div><strong>历史：</strong>{{ worldbuildingData.culture?.history || '待生成' }}</div>
                      <div><strong>宗教：</strong>{{ worldbuildingData.culture?.religion || '待生成' }}</div>
                      <div><strong>禁忌：</strong>{{ worldbuildingData.culture?.taboos || '待生成' }}</div>
                    </n-space>
                  </n-card>
                  <n-card size="small" title="沉浸感细节">
                    <n-space vertical size="small">
                      <div><strong>衣食住行：</strong>{{ worldbuildingData.daily_life?.food_clothing || '待生成' }}</div>
                      <div><strong>俚语口音：</strong>{{ worldbuildingData.daily_life?.language_slang || '待生成' }}</div>
                      <div><strong>娱乐方式：</strong>{{ worldbuildingData.daily_life?.entertainment || '待生成' }}</div>
                    </n-space>
                  </n-card>
                </n-space>
              </n-collapse-item>

              <n-collapse-item title="文风公约" name="style">
                <n-card size="small">
                  <div class="style-convention-text">{{ styleConventionDisplay || '待生成' }}</div>
                </n-card>
              </n-collapse-item>
            </n-collapse>
          </div>
        </n-spin>
      </div>

      <!-- Step 2: Generate Characters -->
      <div v-else-if="currentStep === 2" class="step-panel">
        <n-spin :show="generatingCharacters">
          <div v-if="!charactersGenerated" class="step-info">
            <n-icon size="48" color="#2080f0">
              <IconPeople />
            </n-icon>
            <h3>生成人物</h3>
            <p>基于世界观设定，AI 正在生成3-5个主要角色...</p>
          </div>

          <!-- 生成完成后显示预览 -->
          <div v-else class="bible-preview">
            <n-alert type="success" title="人物生成完成" style="margin-bottom: 16px">
              请查看并确认角色设定。
            </n-alert>

            <n-list bordered>
              <n-list-item v-for="char in bibleData.characters" :key="char.name">
                <n-thing :title="char.name" :description="char.description">
                  <template #header-extra>
                    <n-tag size="small">{{ char.role }}</n-tag>
                  </template>
                </n-thing>
              </n-list-item>
            </n-list>
          </div>
        </n-spin>
      </div>

      <!-- Step 3: Generate Locations -->
      <div v-else-if="currentStep === 3" class="step-panel">
        <n-spin :show="generatingLocations">
          <div v-if="!locationsGenerated" class="step-info">
            <n-icon size="48" color="#f0a020">
              <IconMap />
            </n-icon>
            <h3>生成地图</h3>
            <p>基于世界观和人物设定，AI 正在生成完整的地点系统（地图）...</p>
          </div>

          <!-- 生成完成后显示预览 -->
          <div v-else class="bible-preview">
            <n-alert type="success" title="地图生成完成" style="margin-bottom: 16px">
              请查看并确认地点设定。
            </n-alert>

            <BibleLocationsGraphPreview :locations="bibleData.locations || []" />
            <n-list bordered style="margin-top: 16px">
              <n-list-item v-for="loc in bibleData.locations" :key="loc.id || loc.name">
                <n-thing :title="loc.name" :description="loc.description">
                  <template #header-extra>
                    <n-tag size="small" type="info">{{ loc.location_type || '地点' }}</n-tag>
                  </template>
                </n-thing>
              </n-list-item>
            </n-list>
          </div>
        </n-spin>
      </div>

      <!-- Step 4: 主线候选（LLM 推演） -->
      <div v-else-if="currentStep === 4" class="step-panel step-panel--storyline">
        <div class="step-info step-info--wide">
          <n-icon size="48" color="#2080f0">
            <IconTimeline />
          </n-icon>
          <h3>确立故事主轴</h3>
          <p>基于你已确认的世界观、人物与地图，系统推演三条可选<strong>主线方向</strong>。选定一条即可落库为「主线」；支线留到工作台再养。</p>
        </div>

        <n-alert v-if="plotSuggestError" type="error" :title="plotSuggestError" style="margin-bottom: 12px; width: 100%" />
        <n-alert v-if="mainPlotCommitted" type="success" title="已保存主线" style="margin-bottom: 12px; width: 100%">
          已进入本书的主故事线记录，可随时在工作台「设置 → 故事线」中修改。
        </n-alert>

        <n-spin :show="plotSuggesting" style="width: 100%">
          <div v-if="!customMode" class="plot-options-block">
            <n-space vertical :size="12" style="width: 100%">
              <n-card
                v-for="opt in plotOptions"
                :key="opt.id"
                size="small"
                :bordered="true"
                class="plot-option-card"
                :class="{ 'plot-option-card--disabled': mainPlotCommitted }"
              >
                <template #header>
                  <n-space align="center" :size="8">
                    <n-tag size="small" type="info" round>{{ opt.type || '主线方案' }}</n-tag>
                    <span class="plot-option-title">{{ opt.title }}</span>
                  </n-space>
                </template>
                <n-space vertical :size="8">
                  <div class="plot-line"><strong>梗概：</strong>{{ opt.logline }}</div>
                  <div v-if="opt.core_conflict" class="plot-line"><strong>核心冲突：</strong>{{ opt.core_conflict }}</div>
                  <div v-if="opt.starting_hook" class="plot-line"><strong>开篇钩子：</strong>{{ opt.starting_hook }}</div>
                  <n-button
                    type="primary"
                    size="small"
                    :loading="adoptingPlotId === opt.id"
                    :disabled="mainPlotCommitted"
                    @click="adoptPlotOption(opt)"
                  >
                    选这条作为主线
                  </n-button>
                </n-space>
              </n-card>
            </n-space>

            <n-space style="margin-top: 16px; width: 100%" justify="center" :size="12">
              <n-button secondary :disabled="mainPlotCommitted || plotSuggesting" @click="refreshPlotSuggestions">
                换一组方向
              </n-button>
              <n-button secondary :disabled="mainPlotCommitted" @click="customMode = true">
                我有自己的想法
              </n-button>
            </n-space>
          </div>

          <div v-else class="plot-custom-block">
            <n-input
              v-model:value="customLogline"
              type="textarea"
              placeholder="用一句话写下你想写的主线（例如：废柴少年为救妹妹卷入财阀灵根黑市……）"
              :autosize="{ minRows: 2, maxRows: 5 }"
              :disabled="mainPlotCommitted"
            />
            <n-space style="margin-top: 12px" :size="8">
              <n-button :disabled="mainPlotCommitted" @click="cancelCustomMainPlot">返回候选</n-button>
              <n-button
                type="primary"
                :loading="adoptingCustom"
                :disabled="mainPlotCommitted"
                @click="adoptCustomMainPlot"
              >
                用这句话作为主线
              </n-button>
            </n-space>
          </div>
        </n-spin>
      </div>

      <!-- Step 5: Plot Arc -->
      <div v-else-if="currentStep === 5" class="step-panel">
        <div class="step-info">
          <n-icon size="48" color="#f0a020">
            <IconChart />
          </n-icon>
          <h3>设计情节弧线</h3>
          <p>规划故事的起承转合，设置关键剧情点和张力变化。</p>
          <n-space vertical size="small" style="margin-top: 16px; text-align: left">
            <div>• 开端：故事的起点</div>
            <div>• 上升：矛盾逐渐激化</div>
            <div>• 转折：关键转折点</div>
            <div>• 高潮：矛盾最激烈时刻</div>
            <div>• 结局：故事的收尾</div>
          </n-space>
        </div>
      </div>

      <!-- Step 6: Complete -->
      <div v-else-if="currentStep === 6" class="step-panel">
        <div class="step-info">
          <n-icon size="48" color="#18a058">
            <IconCheck />
          </n-icon>
          <h3>准备就绪！</h3>
          <p>所有基础设置已完成，现在可以开始创作了。</p>
          <p style="margin-top: 12px; color: #666">您可以随时在工作台的"设置"面板中调整这些内容。</p>
        </div>
      </div>
    </div>

    <template #footer>
      <n-space justify="space-between">
        <n-button v-if="currentStep > 3 && currentStep < 6" @click="handleSkip">
          跳过向导
        </n-button>
        <div v-else></div>
        <n-space>
          <n-button
            v-if="(currentStep === 1 && bibleGenerated) || (currentStep === 2 && charactersGenerated) || (currentStep === 3 && locationsGenerated)"
            type="primary"
            @click="handleNext"
          >
            确认并继续
          </n-button>
          <n-button v-if="currentStep === 4" :disabled="!mainPlotCommitted" @click="handleNext"> 下一步 </n-button>
          <n-button v-if="currentStep === 5" @click="handleNext">
            完成设置
          </n-button>
          <n-button v-if="currentStep === 6" type="primary" @click="handleComplete">
            进入工作台
          </n-button>
        </n-space>
      </n-space>
    </template>
  </n-modal>
</template>

<script setup lang="ts">
import { h, ref, watch, computed, onUnmounted } from 'vue'
import { useMessage } from 'naive-ui'
import { bibleApi, type BibleDTO, type StyleNoteDTO } from '@/api/bible'
import { worldbuildingApi } from '@/api/worldbuilding'
import { workflowApi, type MainPlotOptionDTO } from '@/api/workflow'
import BibleLocationsGraphPreview from './BibleLocationsGraphPreview.vue'

const WB_DIMS = ['core_rules', 'geography', 'society', 'culture', 'daily_life'] as const

function emptyWorldbuildingShape(): Record<(typeof WB_DIMS)[number], Record<string, string>> {
  return {
    core_rules: {},
    geography: {},
    society: {},
    culture: {},
    daily_life: {},
  }
}

function createEmptyBible(): BibleDTO {
  return {
    id: '',
    novel_id: '',
    characters: [],
    world_settings: [],
    locations: [],
    timeline_notes: [],
    style_notes: [],
  }
}

/** 从 Bible.world_settings 名如 core_rules.power_system 还原为五维对象 */
function worldbuildingFromWorldSettings(
  settings: { name: string; description?: string }[] | undefined
): Record<(typeof WB_DIMS)[number], Record<string, string>> {
  const out = emptyWorldbuildingShape()
  const dimSet = new Set<string>(WB_DIMS)
  for (const s of settings || []) {
    const dot = s.name.indexOf('.')
    if (dot < 0) continue
    const dim = s.name.slice(0, dot)
    const key = s.name.slice(dot + 1)
    if (!dimSet.has(dim) || !key) continue
    out[dim as (typeof WB_DIMS)[number]][key] = (s.description || '').trim()
  }
  return out
}

function normalizeWorldbuildingFromApi(raw: Record<string, unknown> | null | undefined) {
  const out = emptyWorldbuildingShape()
  if (!raw || typeof raw !== 'object') return out
  for (const d of WB_DIMS) {
    const block = raw[d]
    if (block && typeof block === 'object') {
      out[d] = { ...(block as Record<string, string>) }
    }
  }
  return out
}

/** world_settings 打底，API 非空字段覆盖（避免只写入 Bible 时向导全「待生成」） */
function mergeWorldbuildingDisplay(
  fromApi: ReturnType<typeof normalizeWorldbuildingFromApi>,
  fromBibleSettings: ReturnType<typeof worldbuildingFromWorldSettings>
) {
  const out = emptyWorldbuildingShape()
  for (const d of WB_DIMS) {
    const merged = { ...fromBibleSettings[d], ...fromApi[d] }
    out[d] = merged
  }
  return out
}

function styleConventionFromBible(bible: BibleDTO): string {
  const b = bible as BibleDTO & { style?: string }
  if (b.style && String(b.style).trim()) return String(b.style).trim()
  const notes: StyleNoteDTO[] = b.style_notes || []
  const conv = notes.filter(
    (n: StyleNoteDTO) => n.category === '文风公约' || (n.category || '').includes('文风')
  )
  if (conv.length) return conv.map((n: StyleNoteDTO) => (n.content || '').trim()).filter(Boolean).join('\n\n')
  if (notes.length)
    return notes
      .map((n: StyleNoteDTO) => `[${n.category || '风格'}] ${n.content || ''}`.trim())
      .join('\n\n')
  return ''
}

function formatApiError(error: unknown): string {
  const e = error as {
    response?: { data?: { detail?: unknown } }
    message?: string
  }
  const d = e?.response?.data?.detail
  if (typeof d === 'string') return d
  if (Array.isArray(d))
    return d.map((x: { msg?: string }) => x?.msg || JSON.stringify(x)).join('；')
  if (d != null && typeof d === 'object') return JSON.stringify(d)
  if (e?.message) return e.message
  return ''
}

const IconBook = () =>
  h(
    'svg',
    { xmlns: 'http://www.w3.org/2000/svg', viewBox: '0 0 24 24', fill: 'currentColor' },
    h('path', { d: 'M18 2H6c-1.1 0-2 .9-2 2v16c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2zM6 4h5v8l-2.5-1.5L6 12V4z' })
  )

const IconPeople = () =>
  h(
    'svg',
    { xmlns: 'http://www.w3.org/2000/svg', viewBox: '0 0 24 24', fill: 'currentColor' },
    h('path', { d: 'M16 11c1.66 0 2.99-1.34 2.99-3S17.66 5 16 5c-1.66 0-3 1.34-3 3s1.34 3 3 3zm-8 0c1.66 0 2.99-1.34 2.99-3S9.66 5 8 5C6.34 5 5 6.34 5 8s1.34 3 3 3zm0 2c-2.33 0-7 1.17-7 3.5V19h14v-2.5c0-2.33-4.67-3.5-7-3.5zm8 0c-.29 0-.62.02-.97.05 1.16.84 1.97 1.97 1.97 3.45V19h6v-2.5c0-2.33-4.67-3.5-7-3.5z' })
  )

const IconMap = () =>
  h(
    'svg',
    { xmlns: 'http://www.w3.org/2000/svg', viewBox: '0 0 24 24', fill: 'currentColor' },
    h('path', { d: 'M20.5 3l-.16.03L15 5.1 9 3 3.36 4.9c-.21.07-.36.25-.36.48V20.5c0 .28.22.5.5.5l.16-.03L9 18.9l6 2.1 5.64-1.9c.21-.07.36-.25.36-.48V3.5c0-.28-.22-.5-.5-.5zM15 19l-6-2.11V5l6 2.11V19z' })
  )

const IconTimeline = () =>
  h(
    'svg',
    { xmlns: 'http://www.w3.org/2000/svg', viewBox: '0 0 24 24', fill: 'currentColor' },
    h('path', { d: 'M23 8c0 1.1-.9 2-2 2-.18 0-.35-.02-.51-.07l-3.56 3.55c.05.16.07.34.07.52 0 1.1-.9 2-2 2s-2-.9-2-2c0-.18.02-.36.07-.52l-2.55-2.55c-.16.05-.34.07-.52.07s-.36-.02-.52-.07l-4.55 4.56c.05.16.07.33.07.51 0 1.1-.9 2-2 2s-2-.9-2-2 .9-2 2-2c.18 0 .35.02.51.07l4.56-4.55C8.02 9.36 8 9.18 8 9c0-1.1.9-2 2-2s2 .9 2 2c0 .18-.02.36-.07.52l2.55 2.55c.16-.05.34-.07.52-.07s.36.02.52.07l3.55-3.56C19.02 8.35 19 8.18 19 8c0-1.1.9-2 2-2s2 .9 2 2z' })
  )

const IconChart = () =>
  h(
    'svg',
    { xmlns: 'http://www.w3.org/2000/svg', viewBox: '0 0 24 24', fill: 'currentColor' },
    h('path', { d: 'M3.5 18.49l6-6.01 4 4L22 6.92l-1.41-1.41-7.09 7.97-4-4L2 16.99z' })
  )

const IconCheck = () =>
  h(
    'svg',
    { xmlns: 'http://www.w3.org/2000/svg', viewBox: '0 0 24 24', fill: 'currentColor' },
    h('path', { d: 'M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z' })
  )

const props = withDefaults(
  defineProps<{
    novelId: string
    show: boolean
    /** 用于主线默认章节范围 1 ~ targetChapters */
    targetChapters?: number
  }>(),
  { targetChapters: 100 }
)

const message = useMessage()

const emit = defineEmits<{
  (e: 'update:show', value: boolean): void
  (e: 'complete'): void
  (e: 'skip'): void
}>()

/** 与父组件 show 单一数据源，避免本地 visible 与 props 打架导致误 emit(false) 把向导关掉 */
const modalOpen = computed({
  get: () => props.show,
  set: (v: boolean) => {
    if (v) {
      emit('update:show', true)
      return
    }
    requestClose()
  },
})

const currentStep = ref(1)
const stepStatus = ref<'process' | 'finish' | 'error' | 'wait'>('process')

// 第1步：生成世界观和文风
const generatingBible = ref(false)
const bibleGenerated = ref(false)
const bibleStatusText = ref('正在生成世界观...')
const bibleError = ref('')
const bibleData = ref<BibleDTO>(createEmptyBible())
const worldbuildingData = ref<ReturnType<typeof emptyWorldbuildingShape>>(emptyWorldbuildingShape())

const styleConventionDisplay = computed(() => styleConventionFromBible(bibleData.value))

// 第2步：生成人物和地点
const generatingCharacters = ref(false)
const charactersGenerated = ref(false)

// 第3步：生成地点
const generatingLocations = ref(false)
const locationsGenerated = ref(false)

// Step 4：主线推演
const plotOptions = ref<MainPlotOptionDTO[]>([])
const plotSuggesting = ref(false)
const plotSuggestError = ref('')
const mainPlotCommitted = ref(false)
const customMode = ref(false)
const customLogline = ref('')
const adoptingPlotId = ref<string | null>(null)
const adoptingCustom = ref(false)

const chapterEndForStoryline = computed(() => Math.max(1, props.targetChapters ?? 100))

async function loadPlotSuggestions() {
  plotSuggesting.value = true
  plotSuggestError.value = ''
  try {
    const res = await workflowApi.suggestMainPlotOptions(props.novelId)
    plotOptions.value = res.plot_options || []
  } catch (e: unknown) {
    plotSuggestError.value = formatApiError(e) || '推演失败，请重试'
  } finally {
    plotSuggesting.value = false
  }
}

async function refreshPlotSuggestions() {
  await loadPlotSuggestions()
}

async function adoptPlotOption(opt: MainPlotOptionDTO) {
  adoptingPlotId.value = opt.id
  try {
    const parts = [
      opt.logline,
      opt.core_conflict ? `核心冲突：${opt.core_conflict}` : '',
      opt.starting_hook ? `开篇钩子：${opt.starting_hook}` : '',
    ].filter(Boolean)
    await workflowApi.createStoryline(props.novelId, {
      storyline_type: 'main_plot',
      estimated_chapter_start: 1,
      estimated_chapter_end: chapterEndForStoryline.value,
      name: opt.title.slice(0, 200),
      description: parts.join('\n\n').slice(0, 8000),
    })
    mainPlotCommitted.value = true
    message.success('主线已保存')
  } catch (e: unknown) {
    message.error(formatApiError(e) || '保存失败')
  } finally {
    adoptingPlotId.value = null
  }
}

async function adoptCustomMainPlot() {
  const t = customLogline.value.trim()
  if (!t) {
    message.warning('请先写下一句话主线')
    return
  }
  adoptingCustom.value = true
  try {
    await workflowApi.createStoryline(props.novelId, {
      storyline_type: 'main_plot',
      estimated_chapter_start: 1,
      estimated_chapter_end: chapterEndForStoryline.value,
      name: t.length > 80 ? `${t.slice(0, 80)}…` : t,
      description: t.slice(0, 8000),
    })
    mainPlotCommitted.value = true
    customMode.value = false
    message.success('主线已保存')
  } catch (e: unknown) {
    message.error(formatApiError(e) || '保存失败')
  } finally {
    adoptingCustom.value = false
  }
}

function cancelCustomMainPlot() {
  customMode.value = false
}

const pollTimerRef = ref<ReturnType<typeof setTimeout> | null>(null)
const timeoutTimerRef = ref<ReturnType<typeof setTimeout> | null>(null)
/** 递增以作废上一轮流询中的异步回调（避免超时/关闭后仍进入「完成」分支） */
const biblePollEpoch = ref(0)

function clearGenerationTimers() {
  if (pollTimerRef.value != null) {
    clearTimeout(pollTimerRef.value)
    pollTimerRef.value = null
  }
  if (timeoutTimerRef.value != null) {
    clearTimeout(timeoutTimerRef.value)
    timeoutTimerRef.value = null
  }
}

onUnmounted(() => {
  clearGenerationTimers()
})

/** 仅清理轮询定时器，保留总超时 timer（由 clearGenerationTimers 统一清理） */
function clearPollTimer() {
  if (pollTimerRef.value != null) {
    clearTimeout(pollTimerRef.value)
    pollTimerRef.value = null
  }
}

/**
 * 轮询：串行 setTimeout，避免 setInterval+async 叠请求。
 * 必须用 function 声明放在 watch 之前：`watch(..., { immediate: true })` 会同步调用回调，
 * `const startBibleGeneration = ...` 尚在暂存死区会导致运行时报错 / 逻辑异常。
 */
async function startBibleGeneration() {
  clearGenerationTimers()
  biblePollEpoch.value += 1
  const epoch = biblePollEpoch.value
  generatingBible.value = true
  bibleError.value = ''

  try {
    // 第1步：只生成世界观和文风
    await bibleApi.generateBible(props.novelId, 'worldbuilding')
    if (biblePollEpoch.value !== epoch || !generatingBible.value) return
    bibleStatusText.value = '正在生成世界观和文风...'

    const schedulePoll = (delayMs: number) => {
      clearPollTimer()
      pollTimerRef.value = window.setTimeout(() => {
        void runPoll()
      }, delayMs)
    }

    const runPoll = async () => {
      if (biblePollEpoch.value !== epoch || !generatingBible.value) return
      try {
        const status = await bibleApi.getBibleStatus(props.novelId)
        if (biblePollEpoch.value !== epoch || !generatingBible.value) return
        if (status.ready) {
          clearGenerationTimers()
          generatingBible.value = false
          bibleStatusText.value = '世界观生成完成！'

          // 加载 Bible + 世界观：世界观接口失败时从 Bible.world_settings 回退
          try {
            const bible = await bibleApi.getBible(props.novelId)
            bibleData.value = bible
            let fromApi = emptyWorldbuildingShape()
            try {
              const w = await worldbuildingApi.getWorldbuilding(props.novelId)
              fromApi = normalizeWorldbuildingFromApi(w as unknown as Record<string, unknown>)
            } catch {
              /* 404 或未落库：仅用 Bible 五维扁平条目 */
            }
            const fromWs = worldbuildingFromWorldSettings(bible.world_settings)
            worldbuildingData.value = mergeWorldbuildingDisplay(fromApi, fromWs)
            bibleGenerated.value = true
          } catch (error: unknown) {
            console.error('Failed to load generated data:', error)
            bibleGenerated.value = true
          }
          return
        }
      } catch (error: unknown) {
        if (biblePollEpoch.value !== epoch) return
        clearGenerationTimers()
        generatingBible.value = false
        const detail = formatApiError(error)
        bibleError.value =
          detail || '检查状态失败（网络或后端不可用），请确认本机已启动 API 并刷新重试'
        return
      }
      if (biblePollEpoch.value !== epoch || !generatingBible.value) return
      schedulePoll(2000)
    }

    timeoutTimerRef.value = window.setTimeout(() => {
      if (biblePollEpoch.value !== epoch) return
      biblePollEpoch.value += 1
      clearGenerationTimers()
      generatingBible.value = false
      bibleError.value = '生成超时，请稍后在工作台手动重试'
    }, 120000)

    schedulePoll(0)
  } catch (error: unknown) {
    if (biblePollEpoch.value !== epoch) return
    generatingBible.value = false
    const detail = formatApiError(error)
    bibleError.value = detail || '生成失败，请重试'
  }
}

watch(
  () => props.show,
  (val) => {
    if (val) {
      currentStep.value = 1
      stepStatus.value = 'process'
      plotOptions.value = []
      mainPlotCommitted.value = false
      customMode.value = false
      customLogline.value = ''
      plotSuggestError.value = ''
      void startBibleGeneration()
    } else {
      biblePollEpoch.value += 1
      clearGenerationTimers()
      generatingBible.value = false
    }
  },
  { immediate: true }
)

watch(currentStep, (step) => {
  if (step === 4 && props.show && plotOptions.value.length === 0 && !plotSuggesting.value) {
    void loadPlotSuggestions()
  }
})

const handleNext = async () => {
  if (currentStep.value === 1) {
    // 进入第2步：生成人物
    currentStep.value = 2
    generatingCharacters.value = true
    try {
      await bibleApi.generateBible(props.novelId, 'characters')
      // 轮询检查人物生成状态
      const checkCharacters = async () => {
        const bible = await bibleApi.getBible(props.novelId)
        bibleData.value = bible
        if (bible.characters && bible.characters.length > 0) {
          generatingCharacters.value = false
          charactersGenerated.value = true
        } else {
          window.setTimeout(checkCharacters, 2000)
        }
      }
      await checkCharacters()
    } catch (error) {
      console.error('Failed to generate characters:', error)
      generatingCharacters.value = false
    }
  } else if (currentStep.value === 2) {
    // 进入第3步：生成地点
    currentStep.value = 3
    generatingLocations.value = true
    try {
      await bibleApi.generateBible(props.novelId, 'locations')
      // 轮询检查地点生成状态
      const checkLocations = async () => {
        const bible = await bibleApi.getBible(props.novelId)
        bibleData.value = bible
        if (bible.locations && bible.locations.length > 0) {
          generatingLocations.value = false
          locationsGenerated.value = true
        } else {
          window.setTimeout(checkLocations, 2000)
        }
      }
      await checkLocations()
    } catch (error) {
      console.error('Failed to generate locations:', error)
      generatingLocations.value = false
    }
  } else if (currentStep.value < 6) {
    currentStep.value++
  }
}

const handleSkip = () => {
  if (!confirm('确认退出向导？当前修改将不会保存。')) return
  emit('skip')
  emit('update:show', false)
}

const requestClose = () => {
  if (!confirm('确认退出向导？当前修改将不会保存。')) return
  emit('update:show', false)
}

const handleComplete = () => {
  emit('complete')
  emit('update:show', false)
}
</script>

<style scoped>
.step-content {
  margin: 32px 0;
  min-height: 280px;
  max-height: calc(90vh - 280px);
  overflow-y: auto;
}

.step-panel {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 24px;
}

.step-info {
  text-align: center;
  max-width: 480px;
}

.step-info h3 {
  margin: 16px 0 8px;
  font-size: 20px;
  font-weight: 600;
}

.step-info p {
  color: #666;
  line-height: 1.6;
  margin: 8px 0;
}

.step-panel--storyline {
  align-items: stretch;
  max-width: 100%;
}

.step-info--wide {
  max-width: 100%;
  text-align: center;
}

.plot-options-block,
.plot-custom-block {
  width: 100%;
}

.plot-option-title {
  font-weight: 600;
  font-size: 15px;
}

.plot-line {
  font-size: 13px;
  line-height: 1.55;
  color: #555;
  text-align: left;
}

.plot-option-card--disabled {
  opacity: 0.72;
  pointer-events: none;
}

.style-convention-text {
  white-space: pre-wrap;
  line-height: 1.65;
  font-size: 14px;
}
</style>
