<template>
  <div class="story-structure" @click="closeMenu">
    <div class="structure-body" v-if="displayTreeData.length > 0">
      <div class="structure-tree-inner">
        <div v-if="isMacroPreviewTree" class="macro-preview-ribbon">
          <div class="macro-preview-ribbon__row">
            <span class="macro-preview-ribbon__pulse" aria-hidden="true" />
            <span class="macro-preview-ribbon__text">
              预览中：部 / 卷 / 幕逐条载入；写入完成后切换为正式结构树
            </span>
          </div>
        </div>
        <n-tree
          :data="displayTreeData"
          :node-props="nodeProps"
          :render-label="renderLabel"
          :render-suffix="renderSuffix"
          :selected-keys="selectedKeys"
          v-model:expanded-keys="expandedKeys"
          block-line
          expand-on-click
          selectable
          @update:selected-keys="handleSelect"
        />
        <div
          v-if="showMacroPreviewTailLoading"
          class="macro-preview-tail-loading"
          aria-busy="true"
          aria-label="下一批节点生成中"
        >
          <n-spin size="small" />
          <div class="macro-preview-tail-loading__track">
            <span class="macro-preview-tail-loading__shimmer" />
          </div>
        </div>
      </div>
    </div>

    <div v-else class="structure-empty-wrap">
      <!-- 宏观规划：流未结束前始终有 loading；无节点时空态骨架，有节点时树下方骨架表示仍可能还有下一条 -->
      <div
        v-if="autopilotEmptyMode === 'planning'"
        class="macro-planning-card"
        role="status"
        aria-live="polite"
      >
        <div class="macro-planning-card__content">
          <div class="macro-planning-card__header">
            <n-spin v-if="macroPlanLoadingMore" size="small" />
            <div class="macro-planning-card__titles">
              <span class="macro-planning-card__headline">{{ macroLiveHeadline }}</span>
            </div>
          </div>
          <p v-if="macroPlanningSubtitle" class="macro-planning-card__hint">{{ macroPlanningSubtitle }}</p>
          <p v-else-if="macroPlanLoadingMore" class="macro-planning-card__hint macro-planning-card__hint--muted">
            生成进行中。结构节点将逐条出现，未完成前下方会显示加载占位。
          </p>
          <p v-if="macroWatchError" class="macro-live-error">{{ macroWatchError }}</p>
          <div
            v-if="showMacroPlanningSkeleton"
            class="macro-planning-placeholder"
            aria-busy="true"
            aria-label="等待结构节点"
          >
            <div class="macro-planning-placeholder__track">
              <span class="macro-planning-placeholder__shimmer" />
            </div>
            <span class="macro-planning-placeholder__spin"><n-spin size="small" /></span>
          </div>
        </div>
      </div>

      <n-empty
        v-else
        :description="structureEmptyDescription"
        class="structure-empty"
      >
        <template #extra>
          <n-space vertical :size="8" align="center">
            <n-spin v-if="loading" size="small" />
            <n-alert v-if="!autopilotEmptyMode" type="info" :show-icon="false" style="font-size: 12px; max-width: 240px; text-align: center;">
              <strong>提示</strong>：可在正文区直接生成正文
            </n-alert>
          </n-space>
        </template>
      </n-empty>
    </div>

    <!-- 右键菜单 -->
    <n-dropdown
      trigger="manual"
      placement="bottom-start"
      :show="menuVisible"
      :options="menuOptions"
      :x="menuX"
      :y="menuY"
      @select="handleMenuSelect"
      @clickoutside="closeMenu"
    />

    <!-- 重命名对话框 -->
    <n-modal
      v-model:show="showRename"
      preset="dialog"
      title="重命名"
      positive-text="确认"
      negative-text="取消"
      @positive-click="doRename"
    >
      <n-input v-model:value="renameValue" placeholder="输入新标题" @keydown.enter="doRename" />
    </n-modal>

    <!-- 添加子节点对话框 -->
    <n-modal
      v-model:show="showAddChild"
      preset="dialog"
      :title="addChildTitle"
      positive-text="确认"
      negative-text="取消"
      @positive-click="doAddChild"
    >
      <n-input v-model:value="addChildValue" :placeholder="addChildPlaceholder" @keydown.enter="doAddChild" />
    </n-modal>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, h, onMounted, onUnmounted, watch } from 'vue'
import { NTree, NEmpty, NSpin, NTag, NSpace, NDropdown, NModal, NInput, useMessage, useDialog } from 'naive-ui'
import { structureApi, type StoryNode } from '@/api/structure'
import { chapterApi } from '@/api/chapter'
import { autopilotApi, isAutopilotHttpError } from '@/api/autopilot'
import type { GenerationPrefsDTO } from '@/api/novel'
import { narrativeTreeChapterLine } from '@/utils/narrativeUnitLabel'
import { formatApiError } from '@/utils/apiError'
import { watchMacroPlanProgress, planningApi, type MacroProgressWatchTerminalEvent, type MacroStreamNodeEvent, type StoryNode as PlanningStoryNode } from '@/api/planning'

const props = defineProps<{
  slug: string
  chapters?: Array<{
    id: number
    number: number
    title: string
    word_count: number
  }>
  currentChapterId?: number | null
  /** 与 NovelDTO.generation_prefs 一致；影响章节节点展示文案 */
  generationPrefs?: GenerationPrefsDTO | null
}>()

const emit = defineEmits<{
  selectChapter: [id: number, title: string]
  planAct: [actId: string, actTitle: string]
  openPlanModal: []
  treeLoaded: [hasData: boolean]
}>()

const message = useMessage()
const dialog = useDialog()

const loading = ref(false)
/** 并发 loadTree 时用深度计数维护 loading，避免先结束的请求把 loading 关掉导致空态与 spin 来回闪 */
let loadTreeDepth = 0
/** 只采纳最近一次 loadTree 的响应，避免慢请求覆盖新数据造成树/空态来回切 */
let loadTreeRequestId = 0

const treeData = ref<any[]>([])
const selectedKeys = ref<string[]>([])
const expandedKeys = ref<string[]>([])

function buildChapterFallbackTree() {
  const chapters = [...(props.chapters ?? [])]
    .filter(ch => Number.isFinite(ch.number) && ch.number >= 1)
    .sort((a, b) => a.number - b.number)

  if (!chapters.length) return []

  return chapters.map((ch) =>
    convertToTreeNode({
      id: `fallback-chapter-${ch.number}`,
      novel_id: props.slug,
      parent_id: null,
      node_type: 'chapter',
      number: ch.number,
      title: ch.title || '',
      order_index: ch.number,
      chapter_count: 0,
      metadata: { syntheticTreeFallback: true },
      created_at: '',
      updated_at: '',
      level: 1,
      icon: '📄',
      display_name: '',
      word_count: ch.word_count || 0,
      status: (ch.word_count || 0) > 0 ? 'completed' : 'draft',
      children: [],
    })
  )
}

/** 全托管时空侧栏提示：引导用户使用全托管 */
const autopilotEmptyMode = ref<null | 'planning' | 'review'>(null)

let macroPlanWatchCtrl: AbortController | null = null
/** SSE 不可用时仍轮询 GET macro/progress，避免界面永远停在「骨架」态 */
const macroProgressPolling = ref(false)
let macroProgressPollTimer: ReturnType<typeof setInterval> | null = null

function clearMacroProgressPoll() {
  if (macroProgressPollTimer != null) {
    clearInterval(macroProgressPollTimer)
    macroProgressPollTimer = null
  }
  macroProgressPolling.value = false
}

const macroWatchError = ref('')
const macroLiveMessage = ref('')
const macroPreviewRoots = ref<PlanningStoryNode[]>([])
/** 流式/SSE 未宣告结束：空态与预览树尾部持续 loading + 骨架 */
const macroPlanLoadingMore = ref(false)

const macroLiveHeadline = computed(() => {
  if (macroWatchError.value) return '规划未完成'
  if (macroPreviewRoots.value.length > 0) return '预览结构加载中'
  return '正在生成叙事结构'
})

/** 尚无节点且流未结束：卡片内骨架 */
const showMacroPlanningSkeleton = computed(
  () =>
    autopilotEmptyMode.value === 'planning' &&
    !macroWatchError.value &&
    macroPlanLoadingMore.value &&
    treeData.value.length === 0 &&
    macroPreviewRoots.value.length === 0,
)

/** 仅展示非重复的进度句（避免标题 + 长说明 + SSE 默认句叠三层） */
const GENERIC_MACRO_MESSAGES = new Set([
  '正在连接宏观规划 SSE…',
  '已连接宏观规划输出流，等待模型生成…',
])

const macroPlanningSubtitle = computed(() => {
  if (macroWatchError.value) return ''
  const m = macroLiveMessage.value?.trim()
  if (!m || GENERIC_MACRO_MESSAGES.has(m)) return ''
  return m
})

function stopMacroPlanWatch() {
  macroPlanWatchCtrl?.abort()
  macroPlanWatchCtrl = null
}

function snapshotMacroPreviewRoots(nodes: PlanningStoryNode[]): PlanningStoryNode[] {
  return JSON.parse(JSON.stringify(nodes)) as PlanningStoryNode[]
}

/** SSE 每条 node 为完整部/卷/幕，在此一次性写入对应树位（非字符流） */
function mergeMacroPreviewNode(ev: MacroStreamNodeEvent) {
  const pi = ev.part_index
  const vi = ev.volume_index
  const ai = ev.act_index
  const roots = macroPreviewRoots.value

  const ensurePart = () => {
    while (roots.length <= pi) {
      const idx = roots.length
      roots.push({
        id: `macro-prev-part-${idx}`,
        node_type: 'part',
        title: '…',
        description: '',
        level: 1,
        children: [],
      })
    }
  }

  if (ev.type === 'part') {
    ensurePart()
    const part = roots[pi]
    part.title = ev.title || part.title
    part.description = typeof ev.description === 'string' ? ev.description : ''
    part.children = part.children || []
    macroPreviewRoots.value = snapshotMacroPreviewRoots(roots)
    return
  }

  ensurePart()
  const part = roots[pi]
  part.children = part.children || []

  if (ev.type === 'volume') {
    const vidx = vi ?? 0
    while (part.children!.length <= vidx) {
      const j = part.children!.length
      part.children!.push({
        id: `macro-prev-vol-${pi}-${j}`,
        node_type: 'volume',
        title: '…',
        description: '',
        level: 2,
        children: [],
      })
    }
    const vol = part.children![vidx]
    vol.title = ev.title || vol.title
    vol.description = typeof ev.description === 'string' ? ev.description : ''
    macroPreviewRoots.value = snapshotMacroPreviewRoots(roots)
    return
  }

  if (ev.type === 'act') {
    const vidx = vi ?? 0
    const aidx = ai ?? 0
    while (part.children!.length <= vidx) {
      const j = part.children!.length
      part.children!.push({
        id: `macro-prev-vol-${pi}-${j}`,
        node_type: 'volume',
        title: '…',
        description: '',
        level: 2,
        children: [],
      })
    }
    const vol = part.children![vidx]
    vol.children = vol.children || []
    while (vol.children.length <= aidx) {
      const k = vol.children.length
      vol.children.push({
        id: `macro-prev-act-${pi}-${vidx}-${k}`,
        node_type: 'act',
        title: '…',
        description: '',
        level: 3,
        children: [],
      })
    }
    const act = vol.children[aidx]
    act.title = ev.title || act.title
    act.description = typeof ev.description === 'string' ? ev.description : ''
  }

  macroPreviewRoots.value = snapshotMacroPreviewRoots(roots)
}

async function loadTreeAfterMacroPersist() {
  for (let i = 0; i < 12; i++) {
    await loadTree()
    if (treeData.value.length > 0) {
      macroPreviewRoots.value = []
      return
    }
    await new Promise((r) => setTimeout(r, 400))
  }
  macroPreviewRoots.value = []
}

function startMacroProgressPoll(slug: string) {
  clearMacroProgressPoll()
  macroProgressPolling.value = true
  macroProgressPollTimer = window.setInterval(async () => {
    if (autopilotEmptyMode.value !== 'planning') {
      clearMacroProgressPoll()
      return
    }
    try {
      const res = await planningApi.getMacroProgress(slug)
      const prog = res.data
      if (!prog) return
      if (prog.message?.trim()) {
        macroLiveMessage.value = prog.message.trim()
      }
      if (prog.status === 'completed') {
        macroPlanLoadingMore.value = false
        await loadTreeAfterMacroPersist()
        clearMacroProgressPoll()
        return
      }
      if (prog.status === 'failed') {
        macroPlanLoadingMore.value = false
        macroWatchError.value = prog.message || '宏观规划失败'
        clearMacroProgressPoll()
      }
    } catch {
      /* 轮询失败不打断 SSE */
    }
  }, 3200)
}

watch(
  () => autopilotEmptyMode.value === 'planning',
  (planning) => {
    stopMacroPlanWatch()
    clearMacroProgressPoll()
    macroWatchError.value = ''
    macroLiveMessage.value = ''
    macroPreviewRoots.value = []
    macroPlanLoadingMore.value = false
    if (!planning || !props.slug) return
    macroPlanLoadingMore.value = true
    startMacroProgressPoll(props.slug)
    macroLiveMessage.value = '正在连接宏观规划 SSE…'
    macroPlanWatchCtrl = watchMacroPlanProgress(props.slug, {
      onStatus: (e) => {
        if (e.message) macroLiveMessage.value = e.message
      },
      onNode: (n) => {
        mergeMacroPreviewNode(n)
      },
      onTerminal: async (t: MacroProgressWatchTerminalEvent) => {
        macroPlanLoadingMore.value = false
        stopMacroPlanWatch()
        clearMacroProgressPoll()
        if (t.status === 'completed') {
          await loadTreeAfterMacroPersist()
        } else if (t.status === 'failed') {
          macroWatchError.value = t.message || '宏观规划失败'
        }
      },
      onError: (m) => {
        stopMacroPlanWatch()
        macroLiveMessage.value = `输出流异常：${m}（已改用接口轮询进度）`
        /* 不塞 macroWatchError，以便轮询在 completed 时仍能拉树 */
      },
      onStreamClosed: () => {
        /* 连接关闭不代表流结束，以 terminal / 轮询 completed 为准 */
      },
    })
  },
  { immediate: true },
)

const structureEmptyDescription = computed(() => {
  if (loading.value && autopilotEmptyMode.value == null) {
    return '正在加载叙事结构…'
  }
  if (autopilotEmptyMode.value === 'planning') {
    return '宏观规划完成后结构树会自动更新'
  }
  if (autopilotEmptyMode.value === 'review') {
    return '待审阅：结构将在确认流程写入后显示；若已开始撰写，正文区刷新后会同步侧栏。'
  }
  return '暂无叙事结构'
})

// 右键菜单状态
const menuVisible = ref(false)
const menuX = ref(0)
const menuY = ref(0)
const menuTargetNode = ref<StoryNode | null>(null)

// 重命名状态
const showRename = ref(false)
const renameValue = ref('')

// 添加子节点状态
const showAddChild = ref(false)
const addChildValue = ref('')
const addChildTitle = computed(() => {
  const t = menuTargetNode.value?.node_type
  if (t === 'part') return '添加卷'
  if (t === 'volume') return '添加幕'
  if (t === 'act') return '添加章节'
  return '添加子节点'
})
const addChildPlaceholder = computed(() => {
  const t = menuTargetNode.value?.node_type
  if (t === 'part') return '卷标题'
  if (t === 'volume') return '幕标题'
  if (t === 'act') return '章节标题'
  return '标题'
})

// 右键菜单选项（根据节点类型动态生成）
const menuOptions = computed(() => {
  const node = menuTargetNode.value
  if (!node) return []
  const items: any[] = [
    { label: '重命名', key: 'rename' },
  ]
  if (node.node_type === 'part') {
    items.push({ label: '添加卷', key: 'add-child' })
  } else if (node.node_type === 'volume') {
    items.push({ label: '添加幕', key: 'add-child' })
  } else if (node.node_type === 'act') {
    items.push({ label: '添加章节（手动）', key: 'add-child' })
    items.push({ type: 'divider', key: 'div' })
    items.push({ label: 'AI 规划章节', key: 'plan-act' })
  }
  items.push({ type: 'divider', key: 'div-del' })
  items.push({ label: '删除', key: 'delete' })
  return items
})

/** 在结构树中按章节号查找节点 id（兼容 chapter-{slug}-{n} 与 chapter-{slug}-chapter-{n} 等后端约定） */
function findChapterNodeId(nodes: StoryNode[], chapterNum: number): string | null {
  for (const node of nodes) {
    if (node.node_type === 'chapter' && node.number === chapterNum) {
      return node.id
    }
    if (node.children?.length) {
      const found = findChapterNodeId(node.children, chapterNum)
      if (found) return found
    }
  }
  return null
}

const convertToTreeNode = (node: StoryNode | PlanningStoryNode): any => {
  const iconMap: Record<string, string> = {
    part: '📚',
    volume: '📖',
    act: '🎬',
    chapter: '📄',
  }
  const n = node.number
  const displayName =
    node.node_type === 'chapter' && typeof n === 'number' && n >= 1
      ? narrativeTreeChapterLine(n, node.title || '', props.generationPrefs ?? undefined)
      : node.title
  return {
    key: node.id,
    label: displayName,
    ...node,
    icon: iconMap[node.node_type] || '📄',
    display_name: displayName,
    children: node.children?.map(convertToTreeNode) || [],
  }
}

const displayTreeData = computed(() => {
  if (treeData.value.length > 0) return treeData.value
  const fallback = buildChapterFallbackTree()
  if (fallback.length > 0) return fallback
  if (macroPreviewRoots.value.length > 0) {
    return macroPreviewRoots.value.map((n) => convertToTreeNode(n))
  }
  return []
})

const isMacroPreviewTree = computed(
  () => treeData.value.length === 0 && macroPreviewRoots.value.length > 0,
)

watch(
  [() => props.currentChapterId, displayTreeData],
  () => {
    const chapterId = props.currentChapterId
    if (chapterId == null || chapterId < 1) {
      selectedKeys.value = []
      return
    }
    const key = findChapterNodeId(displayTreeData.value as StoryNode[], chapterId)
    selectedKeys.value = key ? [key] : []
  },
  { immediate: true, deep: true }
)

/** 预览树已部分展示、流未结束：树下方占位，表示仍可能有下一条节点 */
const showMacroPreviewTailLoading = computed(
  () =>
    autopilotEmptyMode.value === 'planning' &&
    isMacroPreviewTree.value &&
    !macroWatchError.value &&
    macroPlanLoadingMore.value,
)

/** 收集所有非章节节点的 key，用于自动展开 */
const collectNonChapterKeys = (nodes: StoryNode[]): string[] => {
  const keys: string[] = []
  const traverse = (node: StoryNode) => {
    if (node.node_type !== 'chapter') {
      keys.push(node.id)
    }
    node.children?.forEach(traverse)
  }
  nodes.forEach(traverse)
  return keys
}

watch(
  displayTreeData,
  (nodes) => {
    expandedKeys.value = collectNonChapterKeys(nodes as unknown as StoryNode[])
  },
  { deep: true, immediate: true },
)

function isAutopilotMacroPlanningStage(s: Record<string, unknown>): boolean {
  const stage = String(s.current_stage ?? '').toLowerCase()
  const sub = String(s.writing_substep ?? '').toLowerCase()
  return (
    stage === 'macro_planning' ||
    stage === 'planning' ||
    sub === 'macro_planning'
  )
}

async function syncAutopilotEmptyHint(hasTreeData: boolean) {
  if (hasTreeData) {
    autopilotEmptyMode.value = null
    return
  }
  try {
    const s = await autopilotApi.getStatus(props.slug)
    if (s.autopilot_status !== 'running') {
      autopilotEmptyMode.value = null
      return
    }
    if (isAutopilotMacroPlanningStage(s)) {
      autopilotEmptyMode.value = 'planning'
    } else if (s.needs_review === true || String(s.current_stage ?? '').toLowerCase() === 'paused_for_review') {
      autopilotEmptyMode.value = 'review'
    } else {
      autopilotEmptyMode.value = null
    }
  } catch (err) {
    if (isAutopilotHttpError(err)) {
      autopilotEmptyMode.value = null
      return
    }
    /* 网络抖动时不清空已有提示，避免按钮/文案来回闪 */
  }
}

const loadTree = async () => {
  const reqId = ++loadTreeRequestId
  loadTreeDepth++
  loading.value = true
  try {
    const res = await structureApi.getTree(props.slug)
    if (reqId !== loadTreeRequestId) {
      return
    }
    const nodes = Array.isArray(res.tree) ? res.tree : (res.tree?.nodes ?? [])
    treeData.value = nodes.length > 0 ? nodes.map(convertToTreeNode) : buildChapterFallbackTree()

    const hasData = treeData.value.length > 0
    emit('treeLoaded', hasData)
    await syncAutopilotEmptyHint(hasData)
  } catch (e: any) {
    if (reqId !== loadTreeRequestId) {
      return
    }
    message.error(formatApiError(e, '加载结构失败'))
    emit('treeLoaded', false)
    autopilotEmptyMode.value = null
  } finally {
    loadTreeDepth--
    if (loadTreeDepth === 0) {
      loading.value = false
    }
  }
}

function relabelTreeChapterNodes(nodes: unknown[]): unknown[] {
  return nodes.map((raw) => {
    const node = raw as Record<string, unknown>
    const n = node.number
    const next: Record<string, unknown> = { ...node }
    if (node.node_type === 'chapter' && typeof n === 'number' && n >= 1) {
      const line = narrativeTreeChapterLine(
        n,
        String(node.title ?? ''),
        props.generationPrefs ?? undefined
      )
      next.label = line
      next.display_name = line
    }
    const ch = node.children
    if (Array.isArray(ch) && ch.length) {
      next.children = relabelTreeChapterNodes(ch)
    }
    return next
  })
}

watch(
  () => props.generationPrefs,
  () => {
    if (treeData.value.length > 0) {
      treeData.value = relabelTreeChapterNodes(treeData.value) as typeof treeData.value
    }
  },
  { deep: true }
)

/** 从结构树章节节点解析「全书章节号」（与 GET .../chapters/{chapter_number} 一致）
 *
 * node.number 是权威来源：章节删除重排时 story_nodes.number 会被级联更新，
 * 但 story_nodes.id 中编码的数字不会更新，因此必须优先使用 node.number。
 * 仅当 node.number 缺失时才回退到从 ID 中提取编号。
 */
function resolveBookChapterNumber(node: StoryNode): number | null {
  if (node.node_type !== 'chapter') return null
  // 优先使用 node.number（重排后始终保持最新）
  const n = node.number
  if (typeof n === 'number' && n >= 1) return n
  // 降级：从 ID 中提取（仅用于 node.number 缺失的老数据）
  const id = node.id
  const mGlobal = id.match(/-chapter-(\d+)$/)
  if (mGlobal) return parseInt(mGlobal[1], 10)
  const mEnd = id.match(/chapter-(\d+)$/)
  if (mEnd) return parseInt(mEnd[1], 10)
  const mTail = id.match(/-(\d+)$/)
  if (mTail) return parseInt(mTail[1], 10)
  return null
}

const handleSelect = (keys: string[]) => {
  if (!keys.length) return
  const findNode = (nodes: StoryNode[], id: string): StoryNode | null => {
    for (const node of nodes) {
      if (node.id === id) return node
      if (node.children) {
        const found = findNode(node.children, id)
        if (found) return found
      }
    }
    return null
  }
  const node = findNode(displayTreeData.value as StoryNode[], keys[0])
  const num = node ? resolveBookChapterNumber(node) : null
  if (num != null) {
    emit('selectChapter', num, node?.title ?? '')
  }
}

// 右键菜单
const handleContextMenu = (e: MouseEvent, node: StoryNode) => {
  e.preventDefault()
  e.stopPropagation()
  menuTargetNode.value = node
  menuX.value = e.clientX
  menuY.value = e.clientY
  menuVisible.value = true
}

const closeMenu = () => { menuVisible.value = false }

const handleMenuSelect = (key: string) => {
  closeMenu()
  const node = menuTargetNode.value
  if (!node) return
  if (key === 'rename') {
    renameValue.value = node.title
    showRename.value = true
  } else if (key === 'add-child') {
    addChildValue.value = ''
    showAddChild.value = true
  } else if (key === 'plan-act') {
    emit('planAct', node.id, node.title)
  } else if (key === 'delete') {
    dialog.warning({
      title: '确认删除',
      content: `删除「${node.title}」及其所有子节点？此操作不可恢复。`,
      positiveText: '删除',
      negativeText: '取消',
      onPositiveClick: async () => {
        try {
          await structureApi.deleteNode(props.slug, node.id)
          message.success('已删除')
          await loadTree()
        } catch (e: any) {
          message.error(formatApiError(e, '删除失败'))
        }
      },
    })
  }
}

const doRename = async () => {
  const node = menuTargetNode.value
  if (!node || !renameValue.value.trim()) return
  showRename.value = false
  try {
    await structureApi.updateNode(props.slug, node.id, { title: renameValue.value.trim() })
    message.success('已重命名')
    await loadTree()
  } catch (e: any) {
    message.error(formatApiError(e, '重命名失败'))
  }
}

const childTypeMap: Record<string, string> = {
  part: 'volume',
  volume: 'act',
  act: 'chapter',
}

const doAddChild = async () => {
  const node = menuTargetNode.value
  if (!node || !addChildValue.value.trim()) return
  showAddChild.value = false
  const childType = childTypeMap[node.node_type]
  if (!childType) return
  try {
    let number = 1
    if (childType === 'chapter') {
      try {
        const existingChapters = await chapterApi.listChapters(props.slug)
        number = existingChapters.length + 1
      } catch {
        // 若查询失败则退回 number=1，后端 ensure 时会按章节号创建
      }
    }
    await structureApi.createNode(props.slug, {
      node_type: childType as any,
      parent_id: node.id,
      title: addChildValue.value.trim(),
      number,
    })
    message.success('已添加')
    await loadTree()
  } catch (e: any) {
    message.error(formatApiError(e, '添加失败'))
  }
}

const nodeKindLabel: Record<string, string> = {
  part: '部',
  volume: '卷',
  act: '幕',
}

const summarySplitMarkers: Record<string, string[]> = {
  part: ['本部', '本阶段', '阶段目标', '主要阻力', '关键选择', '代价是', '回报是'],
  volume: ['本卷', '卷末', '阶段目标', '主要阻力', '关键选择', '代价是', '回报是'],
  act: ['本幕', '幕末', '阶段目标', '主要阻力', '关键选择', '代价是', '回报是'],
}

function normalizeTreeText(value: unknown): string {
  return String(value ?? '').replace(/\s+/g, ' ').trim()
}

function splitEmbeddedSummary(title: unknown, nodeType: string): { title: string; summary: string } {
  const kind = nodeKindLabel[nodeType]
  const rawText = normalizeTreeText(title)
  const text = kind ? rawText.replace(new RegExp(`^${kind}(?=\\S)`), '') : rawText
  if (!text || nodeType === 'chapter') return { title: text, summary: '' }

  const markers = summarySplitMarkers[nodeType] ?? []
  const splitAt = markers
    .map((marker) => {
      const index = text.indexOf(marker)
      return index >= 2 ? index : -1
    })
    .filter((index) => index > 0)
    .sort((a, b) => a - b)[0]

  if (splitAt == null) {
    const titleLimit = nodeType === 'part' ? 8 : nodeType === 'volume' ? 10 : 12
    if (text.length <= titleLimit) return { title: text, summary: '' }
    const punctuationAt = text.search(/[，。；、:：\s-]/u)
    if (punctuationAt > 1 && punctuationAt <= titleLimit + 4) {
      return {
        title: text.slice(0, punctuationAt).trim(),
        summary: text.slice(punctuationAt + 1).trim(),
      }
    }
    return {
      title: `${text.slice(0, titleLimit)}…`,
      summary: text.slice(titleLimit).trim(),
    }
  }

  const cleanTitle = text
    .slice(0, splitAt)
    .replace(/[，。；、:：\s-]+$/u, '')
    .trim()
  const summary = text.slice(splitAt).trim()

  return {
    title: cleanTitle || text,
    summary: cleanTitle ? summary : '',
  }
}

function buildNodeSummary(node: StoryNode, embeddedSummary: string): string {
  const description = normalizeTreeText(node.description)
  if (!embeddedSummary) return description
  if (!description || description === embeddedSummary) return embeddedSummary
  if (description.includes(embeddedSummary) || embeddedSummary.includes(description)) {
    return embeddedSummary.length >= description.length ? embeddedSummary : description
  }
  return `${embeddedSummary} ${description}`
}

// 渲染节点标签
const renderLabel = ({ option }: { option: any }) => {
  const node = option as StoryNode
  const titleParts = splitEmbeddedSummary(option.display_name, option.node_type)
  const summary = buildNodeSummary(node, titleParts.summary)
  const titleRow: any[] = [
    h('span', { class: 'node-icon', 'aria-hidden': 'true' }, option.icon),
  ]
  const kind = nodeKindLabel[option.node_type]
  if (kind) {
    titleRow.push(h('span', { class: 'node-kind', 'aria-label': kind }, kind))
    titleRow.push(h('span', { class: 'node-separator', 'aria-hidden': 'true' }, '｜'))
  } else if (option.node_type === 'chapter') {
    titleRow.push(h('span', { class: 'node-separator', 'aria-hidden': 'true' }, '｜'))
  }
  titleRow.push(h('span', {
    class: 'node-title',
    title: normalizeTreeText(option.display_name),
    style: {
      display: 'inline-block',
      maxWidth: option.node_type === 'part' ? '150px' : option.node_type === 'volume' ? '170px' : '190px',
      overflow: 'hidden',
      textOverflow: 'ellipsis',
      whiteSpace: 'nowrap',
      verticalAlign: 'bottom',
    },
  }, titleParts.title))

  if (option.node_type === 'chapter') {
    const st = (option as StoryNode & { status?: string }).status
    const hasContent =
      (option.word_count && option.word_count > 0) || st === 'completed'
    titleRow.push(
      h(NTag, {
        size: 'tiny',
        type: hasContent ? 'success' : 'default',
        round: true,
        class: 'node-status-tag',
      }, () => (hasContent ? '已收稿' : '未收稿'))
    )
  }

  const children: any[] = [
    h('span', { class: 'node-title-row' }, titleRow),
  ]
  if (
    summary &&
    ['part', 'volume'].includes(node.node_type)
  ) {
    children.push(h('span', {
      class: 'node-description',
      title: summary,
      style: {
        display: 'block',
        maxWidth: '360px',
        overflow: 'hidden',
        textOverflow: 'ellipsis',
        whiteSpace: 'nowrap',
      },
    }, summary))
  }

  return h('span', { class: ['node-label', `node-label--${option.node_type}`] }, children)
}

// 渲染节点后缀
const renderSuffix = ({ option }: { option: any }) => {
  const elements: any[] = []
  const node = option as StoryNode
  if (node.node_type === 'chapter' && node.word_count) {
    elements.push(h('span', { class: 'node-range' }, `${node.word_count}字`))
  }
  if (node.chapter_start && node.chapter_end) {
    elements.push(
      h('span', { class: 'node-range' }, `${node.chapter_start}-${node.chapter_end}章 (${node.chapter_count})`)
    )
  }
  return elements.length > 0 ? h('span', {}, elements) : null
}

// 节点属性（右键绑定；预览树禁用菜单）
const nodeProps = ({ option }: { option: any }) => {
  const node = option as StoryNode
  const lv = node.level ?? 1
  const base = {
    class: `node-level-${lv}`,
  }
  if (isMacroPreviewTree.value || node.metadata?.syntheticTreeFallback) {
    return base
  }
  return {
    ...base,
    onContextmenu: (e: MouseEvent) => handleContextMenu(e, node),
  }
}

onMounted(() => { loadTree() })

onUnmounted(() => {
  clearMacroProgressPoll()
  stopMacroPlanWatch()
})

defineExpose({ loadTree })
</script>

<style scoped>
.story-structure {
  height: 100%;
  display: flex;
  flex-direction: column;
  padding: 4px 0 8px;
}
.structure-body {
  flex: 1;
  overflow: auto;
}

.structure-tree-inner {
  min-height: 100%;
  padding: 2px 2px 8px;
}

.macro-preview-ribbon {
  display: flex;
  flex-direction: column;
  gap: 6px;
  font-size: 12px;
  line-height: 1.5;
  color: var(--app-text-secondary, var(--n-text-color-2));
  padding: 8px 12px;
  margin: 0 0 10px;
  border-radius: var(--n-border-radius, 8px);
  background: var(--app-surface-subtle, var(--n-color-embedded));
  border: 1px solid var(--plotpilot-split-border, var(--n-border-color));
}

.macro-preview-ribbon__row {
  display: flex;
  align-items: center;
  gap: 10px;
}

.macro-preview-ribbon__text {
  flex: 1;
  min-width: 0;
}

.macro-preview-ribbon__pulse {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
  background: var(--n-primary-color);
  opacity: 0.88;
  animation: macro-ribbon-dot-breathe 1.8s ease-in-out infinite;
  box-shadow: 0 0 0 1px color-mix(in srgb, var(--n-primary-color) 35%, transparent);
}

@keyframes macro-ribbon-dot-breathe {
  0%,
  100% {
    opacity: 0.5;
    transform: scale(0.92);
  }
  50% {
    opacity: 1;
    transform: scale(1);
  }
}

.macro-preview-tail-loading {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: 8px;
  padding: 10px 12px;
  border-radius: var(--n-border-radius, 8px);
  border: 1px dashed var(--app-border-soft, var(--n-border-color));
  background: color-mix(in srgb, var(--n-primary-color) 6%, var(--app-surface, var(--n-color)));
}

.macro-preview-tail-loading__track {
  flex: 1;
  height: 8px;
  border-radius: 999px;
  background: color-mix(in srgb, var(--n-text-color-3) 14%, transparent);
  overflow: hidden;
}

.macro-preview-tail-loading__shimmer {
  display: block;
  height: 100%;
  width: 40%;
  border-radius: 999px;
  background: linear-gradient(
    90deg,
    transparent,
    color-mix(in srgb, var(--n-primary-color) 50%, transparent) 45%,
    color-mix(in srgb, var(--n-primary-color) 70%, transparent) 55%,
    transparent
  );
  animation: macro-shimmer-slide 2.1s ease-in-out infinite;
}

.structure-empty-wrap {
  flex: 1;
  min-height: 0;
}
.structure-empty {
  padding: 40px 0;
}

.macro-planning-card {
  margin: 8px 10px 16px;
  border-radius: var(--n-border-radius, 8px);
  border: 1px solid var(--plotpilot-split-border, var(--n-border-color));
  background: var(--app-surface, var(--n-color));
}

.macro-planning-card__content {
  padding: 14px 12px;
}

.macro-planning-card__header {
  display: flex;
  align-items: flex-start;
  gap: 10px;
}

.macro-planning-card__titles {
  flex: 1;
  min-width: 0;
}

.macro-planning-card__headline {
  font-size: 14px;
  font-weight: 600;
  color: var(--app-text-primary, var(--n-text-color-1));
  line-height: 1.4;
}

.macro-planning-card__hint {
  margin: 10px 0 0;
  padding-left: 34px;
  font-size: 12px;
  line-height: 1.55;
  color: var(--app-text-secondary, var(--n-text-color-3));
}

.macro-planning-card__hint--muted {
  opacity: 0.95;
}

.macro-planning-placeholder {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-top: 12px;
  padding: 12px 12px;
  border-radius: var(--n-border-radius, 8px);
  background: color-mix(in srgb, var(--n-primary-color) 5%, var(--app-surface, var(--n-color)));
  border: 1px dashed var(--app-border-soft, var(--n-border-color));
}

.macro-planning-placeholder__track {
  flex: 1;
  height: 8px;
  border-radius: 999px;
  background: color-mix(in srgb, var(--n-text-color-3) 14%, transparent);
  overflow: hidden;
}

.macro-planning-placeholder__shimmer {
  display: block;
  height: 100%;
  width: 42%;
  border-radius: 999px;
  background: linear-gradient(
    90deg,
    transparent,
    color-mix(in srgb, var(--n-primary-color) 45%, transparent) 40%,
    color-mix(in srgb, var(--n-primary-color) 65%, transparent) 50%,
    color-mix(in srgb, var(--n-primary-color) 45%, transparent) 60%,
    transparent
  );
  animation: macro-shimmer-slide 2.1s ease-in-out infinite;
}

@keyframes macro-shimmer-slide {
  0% {
    transform: translateX(-105%);
  }
  100% {
    transform: translateX(320%);
  }
}

.macro-planning-placeholder__spin {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  opacity: 0.9;
}

.macro-live-error {
  margin: 8px 0 0;
  padding-left: 34px;
  font-size: 12px;
  color: var(--n-error-color, #d03050);
  line-height: 1.45;
}

@media (prefers-reduced-motion: reduce) {
  .macro-preview-ribbon__pulse,
  .macro-preview-tail-loading__shimmer,
  .macro-planning-placeholder__shimmer {
    animation: none !important;
  }
}

.story-structure :deep(.n-tree) {
  --tree-title-1: #eef3f8;
  --tree-title-2: #c7d0dd;
  --tree-title-3: #aeb8c7;
  --tree-title-4: #9aa6b7;
  --tree-muted: #8a94a6;
  --tree-faint: #657084;
  --tree-hover: rgba(148, 163, 184, 0.08);
  --tree-active: rgba(59, 130, 246, 0.12);
  --tree-line: rgba(148, 163, 184, 0.16);
}

.story-structure :deep(.n-tree-node) {
  position: relative;
  padding: 2px 0;
}

.story-structure :deep(.n-tree-node-content) {
  min-height: 30px;
  align-items: flex-start;
  padding: 5px 7px;
  border-radius: 6px;
  transition:
    background-color 0.16s ease,
    box-shadow 0.16s ease;
}

.story-structure :deep(.n-tree-node-content:hover) {
  background: var(--tree-hover);
}

.story-structure :deep(.n-tree-node-content.n-tree-node-content--selected) {
  background: var(--tree-active);
  box-shadow: inset 2px 0 0 var(--n-primary-color);
}

.story-structure :deep(.n-tree-node-content__prefix) {
  margin-top: 3px;
}

.story-structure :deep(.n-tree-node-switcher) {
  width: 20px;
  height: 28px;
  color: var(--tree-faint);
}

.story-structure :deep(.n-tree-node-wrapper) {
  position: relative;
}

.story-structure :deep(.n-tree-node-wrapper::before) {
  content: '';
  position: absolute;
  top: 0;
  bottom: 0;
  left: 10px;
  width: 1px;
  background: var(--tree-line);
  opacity: 0.55;
  pointer-events: none;
}

.story-structure :deep(.n-tree-node-wrapper:first-child::before) {
  top: 16px;
}

.story-structure :deep(.n-tree-node-indent) {
  width: 18px;
}

.node-label {
  display: flex;
  min-width: 0;
  width: 100%;
  flex-direction: column;
  gap: 3px;
  padding: 1px 0;
}

.node-title-row {
  display: inline-flex;
  align-items: center;
  min-width: 0;
  max-width: 100%;
  gap: 6px;
}

.node-icon {
  display: inline-flex;
  width: 18px;
  flex: 0 0 18px;
  align-items: center;
  justify-content: center;
  font-size: 14px;
  line-height: 1;
  opacity: 0.82;
}

.node-title {
  min-width: 0;
  max-width: min(360px, 62vw);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 13px;
  font-weight: 500;
  line-height: 1.45;
  letter-spacing: 0;
}

.node-kind {
  display: inline-flex;
  flex: 0 0 24px;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 18px;
  padding: 0;
  border-radius: 4px;
  border: 1px solid rgba(148, 163, 184, 0.18);
  background: rgba(148, 163, 184, 0.08);
  color: var(--tree-faint, var(--app-text-muted));
  font-size: 11px;
  font-weight: 600;
  line-height: 1;
}

.node-separator {
  flex: 0 0 auto;
  color: rgba(174, 184, 199, 0.74);
  font-size: 12px;
  font-weight: 500;
  line-height: 1;
}

.node-label--part .node-title {
  color: var(--tree-title-1, var(--app-text-primary));
  font-size: 15px;
  font-weight: 700;
}

.node-label--part .node-kind {
  border-color: rgba(96, 165, 250, 0.24);
  background: rgba(59, 130, 246, 0.12);
  color: #9ec5ff;
}

.node-label--volume .node-title {
  color: var(--tree-title-2, var(--app-text-secondary));
  font-size: 13px;
  font-weight: 650;
}

.node-label--volume .node-kind {
  border-color: rgba(212, 168, 83, 0.25);
  background: rgba(212, 168, 83, 0.1);
  color: #d5b26b;
}

.node-label--act .node-title {
  color: var(--tree-title-3, var(--app-text-secondary));
  font-size: 13px;
}

.node-label--act .node-kind {
  border-color: rgba(148, 163, 184, 0.2);
  background: rgba(148, 163, 184, 0.08);
  color: #aeb8c7;
}

.node-label--chapter .node-title {
  color: var(--tree-title-4, var(--app-text-muted));
  font-size: 12px;
  font-weight: 500;
}

.node-description {
  display: block;
  max-width: min(520px, 68vw);
  overflow: hidden;
  color: var(--tree-muted, var(--app-text-muted));
  font-size: 11px;
  font-weight: 400;
  line-height: 1.5;
  letter-spacing: 0;
  opacity: 0.82;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.node-label--part .node-description {
  color: var(--tree-muted, var(--app-text-muted));
  opacity: 0.78;
}

.node-status-tag {
  flex: 0 0 auto;
  margin-left: 2px;
  opacity: 0.9;
}

.node-range {
  display: inline-flex;
  align-items: center;
  min-height: 20px;
  margin-left: 8px;
  color: var(--tree-faint, var(--app-text-muted));
  font-size: 11px;
  font-weight: 400;
  line-height: 1.2;
  white-space: nowrap;
}

.node-level-1 { font-weight: 650; }
.node-level-2 { font-weight: 600; }
.node-level-3 { font-weight: 500; }
.node-level-4 { font-weight: 500; font-size: 13px; }
</style>
