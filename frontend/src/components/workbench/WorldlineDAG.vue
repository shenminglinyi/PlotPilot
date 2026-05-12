<template>
  <div class="worldline-dag">
    <!-- Header -->
    <div class="wl-header">
      <n-text strong style="font-size: 14px">世界线</n-text>
      <n-space :size="8">
        <n-button size="small" :loading="saving" @click="handleManualCheckpoint">
          ＋ 存档
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

            <!-- Edges -->
            <line
              v-for="(edge, ei) in layout.edges"
              :key="'e-' + ei"
              :x1="edge.x1" :y1="edge.y1"
              :x2="edge.x2" :y2="edge.y2"
              class="wl-edge"
            />

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
              <!-- Outer ring for HEAD -->
              <circle
                v-if="n.isHead"
                :cx="n.cx" :cy="n.cy"
                :r="NODE_R + 4"
                class="wl-node-head-ring"
                :stroke="n.color"
              />
              <circle
                :cx="n.cx" :cy="n.cy"
                :r="NODE_R"
                :fill="n.color"
                class="wl-node-circle"
              />
              <text
                :x="n.cx + NODE_R + 8"
                :y="n.cy + 4"
                class="wl-node-label"
                :class="{ 'wl-node-label--head': n.isHead }"
              >{{ n.name }}</text>
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

          <n-space vertical :size="8">
            <!-- Checkout -->
            <n-button
              size="small"
              type="primary"
              ghost
              block
              :loading="actionLoading === 'checkout'"
              @click="handleCheckout"
            >
              ⎇ Checkout（保留当前）
            </n-button>

            <!-- Create Branch from here -->
            <n-button
              size="small"
              ghost
              block
              @click="showBranchDialog = true"
            >
              ⑂ 从此分叉新支线
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
              ⚠ Hard Reset（破坏性）
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
          <n-text depth="3" style="font-size: 12px">点击节点查看操作</n-text>
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
const graphWrap = ref<HTMLElement | null>(null)

const graphData = ref<WorldlineGraph>({ nodes: [], edges: [], branches: [], head_id: null })

const nodes = computed(() => graphData.value.nodes)
const headId = computed(() => graphData.value.head_id)

const selectedNode = computed(() => nodes.value.find(n => n.id === selectedId.value) ?? null)

// ──────────────────────────── Layout ────────────────────────────

const NODE_R = 8
const COL_W = 180
const ROW_H = 52
const TOP_PAD = 32
const LEFT_PAD = 20

interface ColInfo { cx: number; name: string; color: string }
interface NodePos {
  id: string; cx: number; cy: number; name: string
  isHead: boolean; color: string; trigger_type: string
  created_at: string; anchor_chapter: number | null; branch_name: string
}
interface EdgePos { x1: number; y1: number; x2: number; y2: number }

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
}
function nodeColor(triggerType: string, branchIdx: number) {
  if (triggerType === 'STASH' || triggerType === 'PRE_RESET') return TRIGGER_COLORS[triggerType]
  return branchColor(branchIdx)
}

const layout = computed(() => {
  const ns = graphData.value.nodes
  const edges = graphData.value.edges
  const branches = graphData.value.branches
  const head = graphData.value.head_id

  if (ns.length === 0) return { viewBox: { w: 0, h: 0 }, branchCols: [] as ColInfo[], edges: [] as EdgePos[], nodePositions: [] as NodePos[] }

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

  // Sort nodes by created_at
  const sorted = [...ns].sort((a, b) => a.created_at.localeCompare(b.created_at))

  // y per node
  const nodeY: Record<string, number> = {}
  sorted.forEach((n, i) => {
    nodeY[n.id] = TOP_PAD + i * ROW_H
  })

  const totalCols = Math.max(branchOrder.length, 1)
  const viewW = LEFT_PAD + totalCols * COL_W
  const viewH = TOP_PAD + sorted.length * ROW_H + 20

  const branchCols: ColInfo[] = branchOrder.map((name, i) => ({
    cx: LEFT_PAD + i * COL_W + NODE_R + 4,
    name: name === 'main' ? 'main' : name,
    color: branchColor(i),
  }))

  const nodeMap: Record<string, NodePos> = {}
  const nodePositions: NodePos[] = sorted.map(n => {
    const bi = branchIdx(n.branch_name)
    const cx = LEFT_PAD + bi * COL_W + NODE_R + 4
    const cy = nodeY[n.id]
    const pos: NodePos = {
      id: n.id,
      cx,
      cy,
      name: n.name.length > 18 ? n.name.slice(0, 17) + '…' : n.name,
      isHead: n.id === head,
      color: nodeColor(n.trigger_type, bi),
      trigger_type: n.trigger_type,
      created_at: n.created_at,
      anchor_chapter: n.anchor_chapter,
      branch_name: n.branch_name,
    }
    nodeMap[n.id] = pos
    return pos
  })

  const edgePositions: EdgePos[] = edges
    .map(e => {
      const from = nodeMap[e.from]
      const to = nodeMap[e.to]
      if (!from || !to) return null
      return { x1: from.cx, y1: from.cy, x2: to.cx, y2: to.cy }
    })
    .filter((e): e is EdgePos => e !== null)

  return { viewBox: { w: viewW, h: viewH }, branchCols, edges: edgePositions, nodePositions }
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
    ACT: '幕', MILESTONE: '里程碑', AUTO: '自动',
  }
  return map[t] ?? t
}

function triggerTagType(t: string): 'info' | 'warning' | 'default' | 'error' | 'success' {
  const map: Record<string, 'info' | 'warning' | 'default' | 'error' | 'success'> = {
    CHAPTER: 'info', MANUAL: 'warning', STASH: 'default',
    PRE_RESET: 'error', ACT: 'success', MILESTONE: 'warning', AUTO: 'info',
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
    message.success(`Checkout 完成（暂存 ID: ${res.stash_id.slice(0, 8)}…，恢复 ${res.restored_chapters} 章）`)
    await load()
    emit('checkpoint-restored')
  } catch (err: unknown) {
    const e = err as { message?: string }
    message.error(e?.message || 'Checkout 失败')
  } finally {
    actionLoading.value = null
  }
}

async function handleHardReset() {
  if (!selectedId.value) return
  dialog.warning({
    title: '确认 Hard Reset',
    content: '此操作将删除该 Checkpoint 之后的所有章节，且不可恢复（会自动先存档）。确定继续？',
    positiveText: '确定 Hard Reset',
    negativeText: '取消',
    onPositiveClick: async () => {
      actionLoading.value = 'hard-reset'
      try {
        const res = await worldlineApi.hardReset(props.slug, selectedId.value!)
        message.warning(`Hard Reset 完成（删除 ${res.deleted_chapters} 章）`)
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
  border-right: 1px solid var(--aitext-split-border);
}

.wl-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  border-bottom: 1px solid var(--aitext-split-border);
  flex-shrink: 0;
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
  overflow: auto;
  padding: 8px 4px;
}

.wl-svg {
  display: block;
  width: 100%;
  overflow: visible;
}

.wl-edge {
  stroke: var(--n-border-color, #e0e0e0);
  stroke-width: 2;
  opacity: 0.7;
}

.wl-node-g {
  cursor: pointer;
}

.wl-node-g:hover .wl-node-circle {
  filter: brightness(1.2);
  stroke: rgba(255,255,255,0.5);
  stroke-width: 2;
}

.wl-node-g--selected .wl-node-circle {
  stroke: white;
  stroke-width: 2.5;
}

.wl-node-head-ring {
  fill: none;
  stroke-width: 2;
  opacity: 0.4;
}

.wl-node-circle {
  transition: filter 0.15s;
}

.wl-node-label {
  font-size: 11px;
  fill: var(--n-text-color, #333);
  pointer-events: none;
}

.wl-node-label--head {
  font-weight: 700;
}

.wl-branch-label {
  font-size: 11px;
  font-weight: 600;
  opacity: 0.8;
}

.wl-detail {
  width: 190px;
  flex-shrink: 0;
  padding: 14px 12px;
  border-left: 1px solid var(--aitext-split-border);
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 0;
}

.wl-detail--empty {
  align-items: center;
  justify-content: center;
}

.wl-detail-title {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  margin-bottom: 6px;
  flex-wrap: wrap;
}
</style>
