<template>
  <div class="story-structure" @click="closeMenu">
    <div class="structure-body" v-if="treeData.length > 0">
      <n-tree
        :data="treeData"
        :node-props="nodeProps"
        :render-label="renderLabel"
        :render-suffix="renderSuffix"
        :selected-keys="selectedKeys"
        :default-expanded-keys="expandedKeys"
        block-line
        expand-on-click
        selectable
        @update:selected-keys="handleSelect"
      />
    </div>

    <n-empty
      v-else-if="!loading"
      :description="structureEmptyDescription"
      class="structure-empty"
    >
      <template #extra>
        <n-space vertical :size="8" align="center">
          <n-button v-if="autopilotEmptyMode" type="primary" @click="loadTree">
            刷新结构树
          </n-button>
          <n-button
            v-if="!autopilotEmptyMode"
            type="primary"
            @click="emit('openPlanModal')"
          >
            🎯 启动结构规划
          </n-button>
          <n-button v-else secondary size="small" @click="emit('openPlanModal')">
            手动打开结构规划…
          </n-button>
        </n-space>
      </template>
    </n-empty>

    <n-spin v-if="loading" class="structure-loading" />

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
import { ref, computed, h, onMounted, watch } from 'vue'
import { NTree, NEmpty, NSpin, NTag, NButton, NSpace, NDropdown, NModal, NInput, useMessage, useDialog } from 'naive-ui'
import { structureApi, type StoryNode } from '@/api/structure'
import { chapterApi } from '@/api/chapter'
import { resolveHttpUrl } from '@/api/config'

const props = defineProps<{
  slug: string
  currentChapterId?: number | null
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
/** 全托管时空侧栏提示：避免与「启动结构规划」主按钮混淆 */
const autopilotEmptyMode = ref<null | 'planning' | 'review'>(null)
const structureEmptyDescription = computed(() => {
  if (autopilotEmptyMode.value === 'planning') {
    return '全托管正在生成部-卷-幕结构，请稍候后点击「刷新结构树」'
  }
  if (autopilotEmptyMode.value === 'review') {
    return '待审阅状态下若结构未显示，请点「刷新结构树」并确认守护进程已运行'
  }
  return '暂无叙事结构'
})
const treeData = ref<any[]>([])
const selectedKeys = ref<string[]>([])
const expandedKeys = ref<string[]>([])

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

watch(
  [() => props.currentChapterId, treeData],
  () => {
    const chapterId = props.currentChapterId
    if (chapterId == null || chapterId < 1) {
      selectedKeys.value = []
      return
    }
    const key = findChapterNodeId(treeData.value, chapterId)
    selectedKeys.value = key ? [key] : []
  },
  { immediate: true, deep: true }
)

const convertToTreeNode = (node: StoryNode): any => {
  const iconMap: Record<string, string> = {
    part: '📚',
    volume: '📖',
    act: '🎬',
    chapter: '📄',
  }
  const n = node.number
  const displayName =
    node.node_type === 'chapter' && typeof n === 'number' && n >= 1
      ? `第${n}章 ${node.title || ''}`.trim()
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

async function syncAutopilotEmptyHint(hasTreeData: boolean) {
  if (hasTreeData) {
    autopilotEmptyMode.value = null
    return
  }
  try {
    const r = await fetch(resolveHttpUrl(`/api/v1/autopilot/${props.slug}/status`))
    if (!r.ok) {
      autopilotEmptyMode.value = null
      return
    }
    const s = await r.json()
    if (s.autopilot_status !== 'running') {
      autopilotEmptyMode.value = null
      return
    }
    if (s.current_stage === 'macro_planning') {
      autopilotEmptyMode.value = 'planning'
    } else if (s.needs_review || s.current_stage === 'paused_for_review') {
      autopilotEmptyMode.value = 'review'
    } else {
      autopilotEmptyMode.value = null
    }
  } catch {
    autopilotEmptyMode.value = null
  }
}

const loadTree = async () => {
  loading.value = true
  try {
    const res = await structureApi.getTree(props.slug)
    const nodes = Array.isArray(res.tree) ? res.tree : (res.tree?.nodes ?? [])
    treeData.value = nodes.length > 0 ? nodes.map(convertToTreeNode) : []

    // 自动展开所有非章节节点
    expandedKeys.value = collectNonChapterKeys(treeData.value)

    const hasData = treeData.value.length > 0
    emit('treeLoaded', hasData)
    await syncAutopilotEmptyHint(hasData)
  } catch (e: any) {
    message.error(e?.response?.data?.detail || '加载结构失败')
    emit('treeLoaded', false)
    autopilotEmptyMode.value = null
  } finally {
    loading.value = false
  }
}

/** 从结构树章节节点解析「全书章节号」（与 GET .../chapters/{chapter_number} 一致） */
function resolveBookChapterNumber(node: StoryNode): number | null {
  if (node.node_type !== 'chapter') return null
  const id = node.id
  const mGlobal = id.match(/-chapter-(\d+)$/)
  if (mGlobal) return parseInt(mGlobal[1], 10)
  const mEnd = id.match(/chapter-(\d+)$/)
  if (mEnd) return parseInt(mEnd[1], 10)
  const n = node.number
  if (typeof n === 'number' && n >= 1) return n
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
  const node = findNode(treeData.value, keys[0])
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
          message.error(e?.response?.data?.detail || '删除失败')
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
    message.error(e?.response?.data?.detail || '重命名失败')
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
    message.error(e?.response?.data?.detail || '添加失败')
  }
}

// 渲染节点标签
const renderLabel = ({ option }: { option: any }) => {
  const elements: any[] = [
    h('span', { class: 'node-icon' }, option.icon),
    h('span', { class: 'node-title' }, option.display_name),
  ]
  if (option.node_type === 'chapter') {
    const st = (option as StoryNode & { status?: string }).status
    const hasContent =
      (option.word_count && option.word_count > 0) || st === 'completed'
    elements.push(
      h(NTag, {
        size: 'small',
        type: hasContent ? 'success' : 'default',
        round: true,
        style: { marginLeft: '8px' },
      }, () => (hasContent ? '已收稿' : '未收稿'))
    )
  }
  return h('span', { class: 'node-label' }, elements)
}

// 渲染节点后缀
const renderSuffix = ({ option }: { option: any }) => {
  const elements: any[] = []
  const node = option as StoryNode
  // 「幕」节点仅显示标题（如第 n 幕），不显示后端附带的内容小结，避免树形一行过长
  if (
    node.description &&
    ['part', 'volume'].includes(node.node_type)
  ) {
    elements.push(
      h('span', {
        class: 'node-description',
        style: { color: '#999', fontSize: '12px', marginLeft: '8px' },
      }, node.description)
    )
  }
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

// 节点属性（右键绑定）
const nodeProps = ({ option }: { option: any }) => {
  const node = option as StoryNode
  return {
    class: `node-level-${node.level}`,
    onContextmenu: (e: MouseEvent) => handleContextMenu(e, node),
  }
}

onMounted(() => { loadTree() })

defineExpose({ loadTree })
</script>

<style scoped>
.story-structure {
  height: 100%;
  display: flex;
  flex-direction: column;
  padding: 8px 0;
}
.structure-body {
  flex: 1;
  overflow: auto;
}
.structure-empty {
  padding: 40px 0;
}
.structure-loading {
  display: flex;
  justify-content: center;
  padding: 40px 0;
}
.node-label {
  display: flex;
  align-items: center;
  gap: 8px;
}
.node-icon { font-size: 16px; }
.node-title { font-size: 13px; }
.node-range {
  font-size: 12px;
  color: #999;
  margin-left: 8px;
}
.node-level-1 { font-weight: 600; }
.node-level-2 { font-weight: 500; }
.node-level-3 { font-weight: normal; }
.node-level-4 { font-weight: normal; font-size: 13px; }
</style>
