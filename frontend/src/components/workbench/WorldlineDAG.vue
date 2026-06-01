<template>
  <div class="worldline-dag">
    <!-- Header -->
    <div class="wl-header">
      <div class="wl-title-block">
        <n-text strong style="font-size: 14px">世界线版本图</n-text>
        <span>{{ nodes.length }} 个存档 · {{ graphData.branches.length }} 条分支 · {{ confluencePoints.length }} 个汇流点</span>
      </div>
      <n-space :size="8">
        <n-button size="small" :loading="saving" @click="handleManualCheckpoint">
          创建存档
        </n-button>
        <n-button size="small" :loading="loading" @click="load">刷新</n-button>
      </n-space>
    </div>

    <n-spin :show="loading" style="flex:1;min-height:0;display:flex;flex-direction:column;">
      <!-- Empty state -->
      <n-empty
        v-if="!loading && nodes.length === 0"
        description="暂无世界线记录，章节完成后将自动生成"
        size="small"
        style="margin-top: 36px"
      />

      <!-- DAG + Detail 拆分 -->
      <div v-else class="wl-body">
        <!-- SVG graph -->
        <div class="wl-graph-wrap" ref="graphWrap">
          <svg
            v-if="layout.viewBox.h > 0"
            class="wl-svg"
            :viewBox="`0 0 ${layout.viewBox.w} ${layout.viewBox.h}`"
            :style="{ height: layout.viewBox.h + 'px' }"
          >
            <!-- Branch lane labels -->
            <text
              v-for="(col, bi) in layout.branchCols"
              :key="'bl-' + bi"
              :x="col.cx"
              y="18"
              text-anchor="middle"
              class="wl-branch-label"
              :fill="col.color"
            >{{ col.name }}</text>

            <!-- Chapter/time slices are embedded in the same graph, not a separate timeline. -->
            <g
              v-for="marker in layout.timeMarkers"
              :key="'tm-' + marker.key"
              class="wl-time-marker"
            >
              <line
                :x1="marker.x1"
                :y1="marker.y"
                :x2="marker.x2"
                :y2="marker.y"
                class="wl-time-line"
              />
              <text :x="marker.labelX" :y="marker.y + 4" class="wl-time-label">
                {{ marker.label }}
              </text>
            </g>

            <!-- Edges -->
            <line
              v-for="(edge, ei) in layout.edges"
              :key="'e-' + ei"
              :x1="edge.x1" :y1="edge.y1"
              :x2="edge.x2" :y2="edge.y2"
              class="wl-edge"
              :class="{ 'wl-edge--merge': edge.kind === 'merge' }"
            />

            <g
              v-for="cp in layout.confluencePositions"
              :key="'cp-' + cp.id"
              class="wl-confluence"
            >
              <path
                :d="cp.d"
                class="wl-confluence-line"
                :class="{ 'wl-confluence-line--resolved': cp.resolved }"
              />
              <rect
                :x="cp.cx - 9"
                :y="cp.cy - 9"
                width="18"
                height="18"
                rx="5"
                class="wl-confluence-node"
                :class="{ 'wl-confluence-node--resolved': cp.resolved }"
              />
              <text :x="cp.cx + 14" :y="cp.cy + 4" class="wl-confluence-label">{{ cp.label }}</text>
            </g>

            <!-- Nodes -->
            <g
              v-for="n in layout.nodePositions"
              :key="n.id"
              class="wl-node-g"
              :class="{
                'wl-node-g--selected': selectedId === n.id,
                'wl-node-g--head': n.isHead,
              }"
              @click="selectNode(n.id)"
            >
              <rect
                :x="n.x"
                :y="n.y"
                :width="NODE_W"
                :height="NODE_H"
                rx="7"
                class="wl-node-card"
                :class="{ 'wl-node-card--head': n.isHead }"
                :stroke="n.color"
              />
              <rect
                :x="n.x"
                :y="n.y"
                width="4"
                :height="NODE_H"
                rx="2"
                :fill="n.color"
                class="wl-node-accent"
              />
              <text :x="n.x + 12" :y="n.y + 16" class="wl-node-chapter">
                {{ n.chapterLabel }}
              </text>
              <text :x="n.x + NODE_W - 10" :y="n.y + 16" text-anchor="end" class="wl-node-trigger">
                {{ n.triggerShort }}
              </text>
              <text
                :x="n.x + 12"
                :y="n.y + 32"
                class="wl-node-title"
                :class="{ 'wl-node-title--head': n.isHead }"
              >{{ n.name }}</text>
              <text :x="n.x + 12" :y="n.y + 47" class="wl-node-meta">
                {{ n.sliceLabel }}
              </text>
              <text :x="n.x + 12" :y="n.y + 62" class="wl-node-meta">
                {{ n.assetLabel }}
              </text>
              <text
                v-if="n.rollbackLabel"
                :x="n.x + NODE_W - 10"
                :y="n.y + 62"
                text-anchor="end"
                class="wl-node-rollback"
              >{{ n.rollbackLabel }}</text>
            </g>
          </svg>
        </div>

        <!-- Detail panel -->
        <div v-if="selectedNode" class="wl-detail">
          <div class="wl-detail-title">
            <n-tag size="small" :type="triggerTagType(selectedNode.trigger_type)" round>
              {{ triggerLabel(selectedNode.trigger_type) }}
            </n-tag>
            <n-text strong style="font-size: 13px; flex:1; overflow:hidden; text-overflow:ellipsis; white-space:nowrap">
              {{ selectedNode.name }}
            </n-text>
          </div>
          <n-text depth="3" style="font-size: 11px; display:block; margin-bottom: 12px">
            {{ formatTime(selectedNode.created_at) }}
            <template v-if="selectedNode.anchor_chapter != null">
              · 第 {{ selectedNode.anchor_chapter }} 章
            </template>
            <template v-if="selectedNode.branch_name !== 'main'">
              · {{ selectedNode.branch_name }}
            </template>
          </n-text>
          <div v-if="selectedNode.world_slice" class="wl-slice">
            <div class="wl-slice-row">
              <span>时间</span>
              <strong>{{ selectedNode.world_slice.time_anchor || '未标定' }}</strong>
            </div>
            <div class="wl-slice-row">
              <span>地点</span>
              <strong>{{ selectedNode.world_slice.location || '未标定' }}</strong>
            </div>
            <div class="wl-slice-row">
              <span>人物</span>
              <strong>{{ selectedNode.world_slice.characters?.length || 0 }}</strong>
            </div>
            <div class="wl-slice-row">
              <span>道具</span>
              <strong>{{ selectedNode.world_slice.items?.length || 0 }}</strong>
            </div>
            <div class="wl-mini-list" v-if="selectedNode.world_slice.characters?.length">
              <span v-for="char in selectedNode.world_slice.characters.slice(0, 4)" :key="char.id">
                {{ char.name }} · {{ char.status }}
              </span>
            </div>
            <div class="wl-mini-list" v-if="selectedNode.world_slice.items?.length">
              <span v-for="item in selectedNode.world_slice.items.slice(0, 4)" :key="item.id">
                {{ item.name }}
              </span>
            </div>
          </div>

          <n-space vertical :size="8">
            <!-- Checkout -->
            <n-button
              v-if="selectedNode.branch_name !== 'main'"
              size="small"
              type="primary"
              secondary
              block
              :loading="actionLoading === 'merge'"
              @click="handleMergeBranch"
            >
              汇入主线
            </n-button>

            <n-button
              size="small"
              type="primary"
              ghost
              block
              :loading="actionLoading === 'checkout'"
              @click="handleCheckout"
            >
              切换到此切片
            </n-button>

            <!-- Create Branch from here -->
            <n-button
              size="small"
              ghost
              block
              @click="showBranchDialog = true"
            >
              从此分叉
            </n-button>

            <!-- Hard Reset -->
            <n-button
              size="small"
              type="error"
              ghost
              block
              :loading="actionLoading === 'hard-reset'"
              @click="handleHardReset"
            >
              回滚到此切片
            </n-button>

            <!-- Delete -->
            <n-button
              size="small"
              ghost
              block
              :loading="actionLoading === 'delete'"
              @click="handleDelete"
            >
              删除存档
            </n-button>
          </n-space>
        </div>
        <div v-else class="wl-detail wl-detail--empty">
          <n-text depth="3" style="font-size: 12px">点击存档查看操作</n-text>
          <div v-if="confluencePoints.length" class="wl-confluence-list">
            <n-text strong style="font-size: 12px">计划汇流</n-text>
            <div v-for="cp in confluencePoints.slice(0, 5)" :key="cp.id" class="wl-confluence-item">
              <n-tag size="tiny" :type="cp.resolved ? 'success' : 'warning'" :bordered="false">
                {{ confluenceLabel(cp.merge_type) }}
              </n-tag>
              <span>第 {{ cp.target_chapter }} 章 · {{ storylineName(cp.source_storyline_id) }} → {{ storylineName(cp.target_storyline_id) }}</span>
            </div>
          </div>
        </div>
      </div>
    </n-spin>

    <!-- 分支命名 Dialog -->
    <n-modal v-model:show="showBranchDialog" preset="dialog" title="从此节点分叉新支线" positive-text="创建" negative-text="取消" @positive-click="handleCreateBranch">
      <n-form label-placement="left" label-width="72" size="small" style="margin-top: 8px">
        <n-form-item label="支线名称">
          <n-input v-model:value="newBranchName" placeholder="如 alt-ending、bad-route…" />
        </n-form-item>
        <n-form-item label="绑定故事线">
          <n-select
            v-model:value="newBranchStorylineId"
            :options="storylineOptions"
            placeholder="可选，绑定后在故事线旁显示 ⑂"
            clearable
          />
        </n-form-item>
      </n-form>
    </n-modal>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useMessage, useDialog } from 'naive-ui'
import { worldlineApi, type CheckpointNode, type WorldlineGraph, type BranchInfo } from '@/api/worldline'
import { confluenceApi, type ConfluencePointDTO } from '@/api/confluence'
import { workflowApi, type StorylineDTO } from '@/api/workflow'

interface Props {
  slug: string
}
const props = defineProps<Props>()
const emit = defineEmits<{ 'checkpoint-restored': [] }>()

const message = useMessage()
const dialog = useDialog()

const loading = ref(false)
const saving = ref(false)
const actionLoading = ref<string | null>(null)
const selectedId = ref<string | null>(null)
const showBranchDialog = ref(false)
const newBranchName = ref('')
const newBranchStorylineId = ref<string | null>(null)
const storylines = ref<StorylineDTO[]>([])
const confluencePoints = ref<ConfluencePointDTO[]>([])

const storylineOptions = computed(() =>
  storylines.value.map(s => ({
    label: s.name || `故事线 ${s.id.slice(0, 8)}`,
    value: s.id,
  }))
)

async function loadStorylines() {
  try {
    const data = await workflowApi.getStorylines(props.slug)
    storylines.value = data || []
  } catch {
    storylines.value = []
  }
}

async function loadConfluencePoints() {
  try {
    confluencePoints.value = await confluenceApi.list(props.slug)
  } catch {
    confluencePoints.value = []
  }
}
const graphWrap = ref<HTMLElement | null>(null)

const graphData = ref<WorldlineGraph>({ nodes: [], edges: [], branches: [], head_id: null })

const nodes = computed(() => graphData.value.nodes)
const headId = computed(() => graphData.value.head_id)

const selectedNode = computed(() => nodes.value.find(n => n.id === selectedId.value) ?? null)

// ──────────────────────────── Layout ────────────────────────────

const NODE_W = 154
const NODE_H = 68
const COL_W = 170
const ROW_H = 88
const TOP_PAD = 42
const LEFT_PAD = 66

interface ColInfo { cx: number; name: string; color: string }
interface NodePos {
  id: string; x: number; y: number; cx: number; cy: number; name: string
  isHead: boolean; color: string; trigger_type: string
  created_at: string; anchor_chapter: number | null; branch_name: string
  world_slice?: CheckpointNode['world_slice']
  chapterLabel: string
  triggerShort: string
  sliceLabel: string
  assetLabel: string
  rollbackLabel: string
}
interface EdgePos { x1: number; y1: number; x2: number; y2: number; kind?: string }
interface ConfluencePos { id: string; cx: number; cy: number; d: string; label: string; resolved: boolean }
interface TimeMarker { key: string; y: number; x1: number; x2: number; labelX: number; label: string }

const BRANCH_COLORS: Record<number, string> = {
  0: '#1890ff',
  1: '#52c41a',
  2: '#fa8c16',
  3: '#722ed1',
  4: '#eb2f96',
  5: '#13c2c2',
}
function branchColor(idx: number) {
  return BRANCH_COLORS[idx % Object.keys(BRANCH_COLORS).length] ?? '#8c8c8c'
}

const TRIGGER_COLORS: Record<string, string> = {
  CHAPTER: '#1890ff',
  MANUAL: '#fa8c16',
  STASH: '#8c8c8c',
  PRE_RESET: '#f5222d',
  ACT: '#52c41a',
  MILESTONE: '#722ed1',
  AUTO: '#1890ff',
  MERGE: '#16a34a',
}
function nodeColor(triggerType: string, branchIdx: number) {
  if (triggerType === 'STASH' || triggerType === 'PRE_RESET') return TRIGGER_COLORS[triggerType]
  return branchColor(branchIdx)
}

function compact(value: string, max: number) {
  if (!value) return ''
  return value.length > max ? value.slice(0, Math.max(0, max - 1)) + '…' : value
}

const layout = computed(() => {
  const ns = graphData.value.nodes
  const edges = graphData.value.edges
  const branches = graphData.value.branches
  const head = graphData.value.head_id

  if (ns.length === 0) return {
    viewBox: { w: 0, h: 0 },
    branchCols: [] as ColInfo[],
    edges: [] as EdgePos[],
    nodePositions: [] as NodePos[],
    confluencePositions: [] as ConfluencePos[],
    timeMarkers: [] as TimeMarker[],
  }

  // Assign column index per branch name
  const branchOrder: string[] = []
  branches.forEach(b => {
    if (!branchOrder.includes(b.name)) branchOrder.push(b.name)
  })
  ns.forEach(n => {
    if (!branchOrder.includes(n.branch_name)) branchOrder.push(n.branch_name)
  })

  const branchIdx = (name: string) => {
    const i = branchOrder.indexOf(name)
    return i >= 0 ? i : 0
  }

  // Sort nodes by story time first. Created time keeps older records stable when story time is missing.
  const sorted = [...ns].sort((a, b) => {
    const ac = Number(a.anchor_chapter || a.world_slice?.chapter_number || 0)
    const bc = Number(b.anchor_chapter || b.world_slice?.chapter_number || 0)
    if (ac !== bc) return ac - bc
    return a.created_at.localeCompare(b.created_at)
  })

  // y per node
  const nodeY: Record<string, number> = {}
  sorted.forEach((n, i) => {
    nodeY[n.id] = TOP_PAD + i * ROW_H
  })

  const totalCols = Math.max(branchOrder.length, 1)
  const viewW = LEFT_PAD + totalCols * COL_W + 18
  const viewH = TOP_PAD + sorted.length * ROW_H + 28

  const branchCols: ColInfo[] = branchOrder.map((name, i) => ({
    cx: LEFT_PAD + i * COL_W + NODE_W / 2,
    name: name === 'main' ? '主线' : name,
    color: branchColor(i),
  }))

  const nodeMap: Record<string, NodePos> = {}
  const nodePositions: NodePos[] = sorted.map(n => {
    const bi = branchIdx(n.branch_name)
    const x = LEFT_PAD + bi * COL_W
    const y = nodeY[n.id]
    const cx = x + NODE_W / 2
    const cy = y + NODE_H / 2
    const chapter = n.anchor_chapter ?? n.world_slice?.chapter_number ?? null
    const timeAnchor = n.world_slice?.time_anchor || ''
    const location = n.world_slice?.location || ''
    const characters = n.world_slice?.characters?.length || 0
    const items = n.world_slice?.items?.length || 0
    const conflicts = n.world_slice?.conflicts_count || 0
    const pos: NodePos = {
      id: n.id,
      x,
      y,
      cx,
      cy,
      name: compact(n.name, 14),
      isHead: n.id === head,
      color: nodeColor(n.trigger_type, bi),
      trigger_type: n.trigger_type,
      created_at: n.created_at,
      anchor_chapter: n.anchor_chapter,
      branch_name: n.branch_name,
      world_slice: n.world_slice,
      chapterLabel: chapter != null ? `第 ${chapter} 章` : '未锚定',
      triggerShort: triggerLabel(n.trigger_type),
      sliceLabel: compact([timeAnchor, location].filter(Boolean).join(' / ') || '时间切片未标定', 18),
      assetLabel: `人物 ${characters} · 道具 ${items}${conflicts ? ` · 风险 ${conflicts}` : ''}`,
      rollbackLabel: n.rollback_slice?.to_chapter != null ? `回滚→第${n.rollback_slice.to_chapter}章` : '',
    }
    nodeMap[n.id] = pos
    return pos
  })

  const edgePositions: EdgePos[] = edges
    .map((e): EdgePos | null => {
      const from = nodeMap[e.from]
      const to = nodeMap[e.to]
      if (!from || !to) return null
      return {
        x1: from.cx,
        y1: from.y + NODE_H,
        x2: to.cx,
        y2: to.y,
        kind: e.kind,
      }
    })
    .filter((e): e is EdgePos => e !== null)

  const seenMarkers = new Set<string>()
  const timeMarkers: TimeMarker[] = []
  for (const n of sorted) {
    const chapter = n.anchor_chapter ?? n.world_slice?.chapter_number ?? null
    const key = chapter != null ? `chapter-${chapter}` : `node-${n.id}`
    if (seenMarkers.has(key)) continue
    seenMarkers.add(key)
    const y = nodeY[n.id] + NODE_H / 2
    const time = n.world_slice?.time_anchor
    timeMarkers.push({
      key,
      y,
      x1: LEFT_PAD - 10,
      x2: viewW - 12,
      labelX: 8,
      label: chapter != null ? `第${chapter}章${time ? ` · ${compact(time, 8)}` : ''}` : '未锚定',
    })
  }

  const maxChapter = Math.max(
    1,
    ...ns.map(n => Number(n.anchor_chapter || 0)),
    ...confluencePoints.value.map(cp => Number(cp.target_chapter || 0)),
  )
  const chapterToY = (chapter: number) => {
    const ratio = maxChapter <= 1 ? 0 : Math.max(0, Math.min(1, (chapter - 1) / Math.max(1, maxChapter - 1)))
    return TOP_PAD + ratio * Math.max(ROW_H, sorted.length * ROW_H - ROW_H)
  }
  const confluencePositions: ConfluencePos[] = confluencePoints.value.map((cp, index) => {
    const sourceIdx = Math.max(0, Math.min(branchOrder.length - 1, branchIdx(storylineBranchName(cp.source_storyline_id))))
    const targetIdx = Math.max(0, Math.min(branchOrder.length - 1, branchIdx(storylineBranchName(cp.target_storyline_id))))
    const sx = LEFT_PAD + sourceIdx * COL_W + NODE_W / 2
    const tx = LEFT_PAD + targetIdx * COL_W + NODE_W / 2
    const cy = chapterToY(cp.target_chapter) + (index % 3) * 10
    const midX = sx + (tx - sx) * 0.55
    return {
      id: cp.id,
      cx: tx,
      cy,
      d: `M ${sx} ${cy - 18} C ${midX} ${cy - 18}, ${midX} ${cy}, ${tx} ${cy}`,
      label: `Ch.${cp.target_chapter} ${confluenceLabel(cp.merge_type)}`,
      resolved: !!cp.resolved,
    }
  })

  return { viewBox: { w: viewW, h: viewH }, branchCols, edges: edgePositions, nodePositions, confluencePositions, timeMarkers }
})

// ──────────────────────────── Data ────────────────────────────

async function load() {
  loading.value = true
  try {
    graphData.value = await worldlineApi.getGraph(props.slug)
  } catch (err: unknown) {
    const e = err as { message?: string }
    message.error(e?.message || '加载世界线失败')
  } finally {
    loading.value = false
  }
}

watch(() => props.slug, () => {
  selectedId.value = null
  void load()
  void loadStorylines()
  void loadConfluencePoints()
}, { immediate: true })

// ──────────────────────────── Helpers ────────────────────────────

function formatTime(ts: string): string {
  if (!ts) return ''
  const d = new Date(ts)
  const now = new Date()
  const diff = now.getTime() - d.getTime()
  if (diff < 0) return d.toLocaleString('zh-CN')
  const m = Math.floor(diff / 60000)
  const h = Math.floor(diff / 3600000)
  const days = Math.floor(diff / 86400000)
  if (m < 1) return '刚刚'
  if (m < 60) return `${m}分钟前`
  if (h < 24) return `${h}小时前`
  if (days < 7) return `${days}天前`
  return d.toLocaleDateString('zh-CN')
}

function triggerLabel(t: string) {
  const map: Record<string, string> = {
    CHAPTER: '章节', MANUAL: '手动', STASH: '暂存', PRE_RESET: '重置前',
    ACT: '幕', MILESTONE: '里程碑', AUTO: '自动', MERGE: '汇流',
  }
  return map[t] ?? t
}

function confluenceLabel(t: string) {
  const map: Record<string, string> = {
    intersect: '交叉',
    absorb: '并入',
    reveal: '显影',
  }
  return map[t] ?? t
}

function storylineName(id: string) {
  const s = storylines.value.find(item => item.id === id)
  return s?.name || id.slice(0, 6)
}

function storylineBranchName(storylineId: string) {
  const branch = graphData.value.branches.find(b => b.storyline_id === storylineId)
  return branch?.name || 'main'
}

function triggerTagType(t: string): 'info' | 'warning' | 'default' | 'error' | 'success' {
  const map: Record<string, 'info' | 'warning' | 'default' | 'error' | 'success'> = {
    CHAPTER: 'info', MANUAL: 'warning', STASH: 'default',
    PRE_RESET: 'error', ACT: 'success', MILESTONE: 'warning', AUTO: 'info', MERGE: 'success',
  }
  return map[t] ?? 'default'
}

function selectNode(id: string) {
  selectedId.value = selectedId.value === id ? null : id
}

// ──────────────────────────── Actions ────────────────────────────

async function handleManualCheckpoint() {
  saving.value = true
  try {
    await worldlineApi.createCheckpoint(props.slug, {
      trigger_type: 'MANUAL',
      name: `手动存档 ${new Date().toLocaleString('zh-CN')}`,
    })
    message.success('存档已创建')
    await load()
  } catch (err: unknown) {
    const e = err as { message?: string }
    message.error(e?.message || '创建存档失败')
  } finally {
    saving.value = false
  }
}

async function handleCheckout() {
  if (!selectedId.value) return
  actionLoading.value = 'checkout'
  try {
    const res = await worldlineApi.checkout(props.slug, selectedId.value)
    message.success(`切换完成（暂存 ${res.stash_id.slice(0, 8)}…，恢复 ${res.restored_chapters} 章）`)
    await load()
    emit('checkpoint-restored')
  } catch (err: unknown) {
    const e = err as { message?: string }
    message.error(e?.message || 'Checkout 失败')
  } finally {
    actionLoading.value = null
  }
}

async function handleMergeBranch() {
  const node = selectedNode.value
  if (!node || node.branch_name === 'main') return
  const branch = graphData.value.branches.find(b => b.name === node.branch_name)
  if (!branch) {
    message.warning('找不到当前分支')
    return
  }
  actionLoading.value = 'merge'
  try {
    await worldlineApi.mergeBranch(props.slug, branch.id, {
      target_branch_name: 'main',
      name: `${branch.name} 汇入主线`,
    })
    message.success('分支已汇入主线')
    await load()
  } catch (err: unknown) {
    const e = err as { message?: string }
    message.error(e?.message || '分支汇入失败')
  } finally {
    actionLoading.value = null
  }
}

async function handleHardReset() {
  if (!selectedId.value) return
  dialog.warning({
    title: '确认回滚',
    content: '此操作将删除该切片之后的所有章节，且不可恢复（会自动先存档）。确定继续？',
    positiveText: '确定回滚',
    negativeText: '取消',
    onPositiveClick: async () => {
      actionLoading.value = 'hard-reset'
      try {
        const res = await worldlineApi.hardReset(props.slug, selectedId.value!)
        message.warning(`回滚完成（删除 ${res.deleted_chapters} 章）`)
        selectedId.value = null
        await load()
        emit('checkpoint-restored')
      } catch (err: unknown) {
        const e = err as { message?: string }
        message.error(e?.message || 'Hard Reset 失败')
      } finally {
        actionLoading.value = null
      }
    },
  })
}

async function handleDelete() {
  if (!selectedId.value) return
  actionLoading.value = 'delete'
  try {
    await worldlineApi.deleteCheckpoint(props.slug, selectedId.value)
    message.success('存档已删除')
    selectedId.value = null
    await load()
  } catch (err: unknown) {
    const e = err as { message?: string }
    message.error(e?.message || '删除失败')
  } finally {
    actionLoading.value = null
  }
}

async function handleCreateBranch() {
  if (!selectedId.value || !newBranchName.value.trim()) {
    message.warning('请输入支线名称')
    return false
  }
  try {
    await worldlineApi.createBranch(props.slug, {
      name: newBranchName.value.trim(),
      from_checkpoint_id: selectedId.value,
      storyline_id: newBranchStorylineId.value ?? undefined,
    })
    message.success('支线已创建')
    newBranchName.value = ''
    newBranchStorylineId.value = null
    showBranchDialog.value = false
    await load()
  } catch (err: unknown) {
    const e = err as { message?: string }
    message.error(e?.message || '创建支线失败')
    return false
  }
}
</script>

<style scoped>
.worldline-dag {
  height: 100%;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: var(--app-surface);
}

.wl-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  border-bottom: 1px solid var(--plotpilot-split-border);
  flex-shrink: 0;
  background: var(--app-surface-elevated, var(--app-surface));
}

.wl-title-block {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.wl-title-block span {
  color: var(--app-text-muted, rgba(0, 0, 0, 0.58));
  font-size: 11px;
}

.wl-body {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: row;
  overflow: hidden;
}

.wl-graph-wrap {
  flex: 1;
  min-width: 0;
  overflow-y: auto;
  overflow-x: hidden;
  padding: 14px 12px;
  background:
    linear-gradient(90deg, color-mix(in srgb, var(--color-primary, #2563eb) 5%, transparent) 1px, transparent 1px),
    linear-gradient(180deg, color-mix(in srgb, var(--color-primary, #2563eb) 5%, transparent) 1px, transparent 1px);
  background-size: 28px 28px;
}

.wl-svg {
  display: block;
  width: 100%;
  min-width: 0;
  overflow: visible;
}

.wl-time-line {
  stroke: color-mix(in srgb, var(--app-text-muted, #64748b) 18%, transparent);
  stroke-width: 1;
  stroke-dasharray: 3 8;
}

.wl-time-label {
  font-size: 9px;
  fill: var(--app-text-muted, #64748b);
  opacity: 0.86;
  pointer-events: none;
}

.wl-edge {
  stroke: color-mix(in srgb, var(--app-text-muted, #64748b) 42%, transparent);
  stroke-width: 1.7;
  opacity: 0.75;
}

.wl-edge--merge {
  stroke: var(--color-success, #16a34a);
  stroke-width: 2.2;
}

.wl-confluence-line {
  fill: none;
  stroke: var(--color-warning, #d97706);
  stroke-width: 1.8;
  stroke-dasharray: 5 4;
  opacity: 0.82;
}

.wl-confluence-line--resolved {
  stroke: var(--color-success, #16a34a);
  stroke-dasharray: none;
}

.wl-confluence-node {
  fill: color-mix(in srgb, var(--color-warning, #d97706) 18%, var(--app-surface));
  stroke: var(--color-warning, #d97706);
  stroke-width: 1.5;
}

.wl-confluence-node--resolved {
  fill: color-mix(in srgb, var(--color-success, #16a34a) 18%, var(--app-surface));
  stroke: var(--color-success, #16a34a);
}

.wl-confluence-label {
  font-size: 10px;
  fill: var(--app-text-muted, #64748b);
  pointer-events: none;
}

.wl-node-g {
  cursor: pointer;
}

.wl-node-g:hover .wl-node-card {
  filter: brightness(1.02);
  stroke-width: 2;
}

.wl-node-g--selected .wl-node-card {
  stroke: var(--app-text-primary, #111827);
  stroke-width: 2.2;
}

.wl-node-card {
  fill: color-mix(in srgb, var(--app-surface) 94%, var(--color-primary, #2563eb));
  stroke-width: 1.4;
  transition: filter 0.15s, stroke-width 0.15s;
  filter: drop-shadow(0 2px 7px rgba(15, 23, 42, 0.06));
}

.wl-node-card--head {
  fill: color-mix(in srgb, var(--color-primary, #2563eb) 8%, var(--app-surface));
}

.wl-node-accent {
  pointer-events: none;
}

.wl-node-chapter,
.wl-node-trigger,
.wl-node-title,
.wl-node-meta,
.wl-node-rollback {
  pointer-events: none;
}

.wl-node-chapter {
  font-size: 10px;
  fill: var(--app-text-muted, #64748b);
}

.wl-node-trigger {
  font-size: 9px;
  fill: var(--app-text-muted, #64748b);
}

.wl-node-title {
  font-size: 11px;
  fill: var(--app-text-primary, #333);
}

.wl-node-title--head {
  font-weight: 700;
}

.wl-node-meta {
  font-size: 9.5px;
  fill: var(--app-text-muted, #64748b);
}

.wl-node-rollback {
  font-size: 9px;
  fill: var(--color-warning, #d97706);
}

.wl-branch-label {
  font-size: 11px;
  font-weight: 600;
  opacity: 0.8;
}

.wl-detail {
  width: 230px;
  flex-shrink: 0;
  padding: 14px;
  border-left: 1px solid var(--plotpilot-split-border);
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 0;
  background: var(--app-surface);
}

.wl-detail--empty {
  align-items: center;
  justify-content: center;
  gap: 14px;
}

.wl-detail-title {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  margin-bottom: 6px;
  flex-wrap: wrap;
}

.wl-slice {
  display: grid;
  gap: 7px;
  padding: 10px;
  margin: 0 0 12px;
  border: 1px solid var(--app-border, rgba(0, 0, 0, 0.08));
  border-radius: 8px;
  background: var(--app-surface-subtle, rgba(0, 0, 0, 0.03));
}

.wl-slice-row {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  font-size: 11px;
}

.wl-slice-row span {
  color: var(--app-text-muted, rgba(0, 0, 0, 0.58));
}

.wl-slice-row strong {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.wl-mini-list {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.wl-mini-list span {
  padding: 2px 6px;
  border-radius: 999px;
  background: var(--app-surface);
  color: var(--app-text-muted, rgba(0, 0, 0, 0.58));
  font-size: 10px;
}

.wl-confluence-list {
  width: 100%;
  display: grid;
  gap: 8px;
}

.wl-confluence-item {
  display: grid;
  gap: 4px;
  padding: 8px;
  border-radius: 7px;
  background: var(--app-surface-subtle, rgba(0, 0, 0, 0.03));
}

.wl-confluence-item span {
  color: var(--app-text-muted, rgba(0, 0, 0, 0.58));
  font-size: 11px;
  line-height: 1.45;
}
</style>
