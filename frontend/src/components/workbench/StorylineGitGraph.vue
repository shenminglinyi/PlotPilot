<template>
  <div class="gg-container" ref="containerRef">
    <!-- ======== 顶部工具栏 ======== -->
    <header class="gg-header">
      <div class="gg-header-left">
        <span class="gg-logo">⌥</span>
        <h3 class="gg-title">Git Graph · 叙事版本控制</h3>
        <n-tag size="tiny" round :bordered="false" type="info">
          {{ tracks.length }} tracks · {{ commits.length }} commits
        </n-tag>
      </div>
      <div class="gg-header-right">
        <n-button size="tiny" secondary :loading="loading" @click="loadData">
          <template #icon>↻</template>
          刷新
        </n-button>
        <n-tooltip trigger="hover">
          <template #trigger>
            <n-button size="tiny" quaternary @click="toggleZoom">
              {{ zoomed ? '⊖ 收起' : '⊕ 放大' }}
            </n-button>
          </template>
          切换视图密度
        </n-tooltip>
      </div>
    </header>

    <!-- ======== 主体画布 ======== -->
    <div
      ref="canvasRef"
      class="gg-canvas"
      :class="{ 'gg--zoomed': zoomed }"
      @scroll="onScroll"
    >
      <!-- 加载态 -->
      <div v-if="loading" class="gg-state gg-state--loading">
        <div class="gg-spinner" />
        <span>正在构建 Git Graph…</span>
      </div>

      <!-- 空状态 -->
      <div v-else-if="!tracks.length" class="gg-state gg-state--empty">
        <span class="gg-empty-icon">🌱</span>
        <p class="gg-empty-title">暂无故事线</p>
        <p class="gg-empty-desc">添加故事线后，Git Graph 将自动生长出分支与合并</p>
      </div>

      <!-- SVG 图谱 -->
      <svg
        v-else
        ref="svgRef"
        class="gg-svg"
        :viewBox="`0 0 ${svgWidth} ${svgHeight}`"
        preserveAspectRatio="xMinYMin meet"
      >
        <defs>
          <!-- 每条轨道的渐变 -->
          <linearGradient v-for="tr in tracks" :id="'gg-grad-' + tr.id" :key="'g-' + tr.id" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" :stop-color="tr.color" stop-opacity="1" />
            <stop offset="100%" :stop-color="adjustColor(tr.color, -40)" stop-opacity="1" />
          </linearGradient>

          <!-- Merge 专用渐变 -->
          <linearGradient id="gg-grad-merge" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stop-color="#a78bfa" />
            <stop offset="100%" stop-color="#6366f1" />
          </linearGradient>

          <!-- 发光滤镜 -->
          <filter id="gg-glow" x="-50%" y="-50%" width="200%" height="200%">
            <feGaussianBlur stdDeviation="3" result="blur" />
            <feMerge>
              <feMergeNode in="blur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>

          <!-- 当前 HEAD 强发光 -->
          <filter id="gg-glow-head" x="-50%" y="-50%" width="200%" height="200%">
            <feGaussianBlur stdDeviation="5" result="blur" />
            <feMerge>
              <feMergeNode in="blur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>

          <!-- 流光渐变（用于路径动画） -->
          <linearGradient id="gg-flow-grad" x1="0%" y1="0%" x2="100%" y2="0%">
            <stop offset="0%" stop-color="#fff" stop-opacity="0" />
            <stop offset="50%" stop-color="#fff" stop-opacity="0.4" />
            <stop offset="100%" stop-color="#fff" stop-opacity="0" />
          </linearGradient>

          <!-- HEAD 箭头 marker -->
          <marker id="gg-arrow" markerWidth="10" markerHeight="7" refX="9" refY="3.5" orient="auto">
            <polygon points="0 0, 10 3.5, 0 7" fill="#f59e0b" />
          </marker>

          <!-- Branch 箭头 marker -->
          <marker id="gg-arrow-branch" markerWidth="8" markerHeight="6" refX="7" refY="3" orient="auto">
            <polygon points="0 0, 8 3, 0 6" fill="#22d3ee" opacity="0.7" />
          </marker>
        </defs>

        <!-- ======== 背景层 ======== -->
        <g class="gg-bg">
          <!-- 轨道横线（虚线） -->
          <line
            v-for="(tr, ti) in tracks"
            :key="'track-bg-' + tr.id"
            :x1="labelWidth"
            :y1="trackY(ti)"
            :x2="svgWidth - paddingR"
            :y2="trackY(ti)"
            stroke="rgba(99,102,241,0.08)"
            stroke-width="1"
            stroke-dasharray="6,4"
          />

          <!-- 章节竖网格线 -->
          <line
            v-for="ch in visibleChapters"
            :key="'grid-' + ch"
            :x1="chapterToX(ch)"
            :y1="paddingT"
            :x2="chapterToX(ch)"
            :y2="svgHeight - paddingB"
            stroke="rgba(99,102,241,0.05)"
            stroke-width="1"
            stroke-dasharray="3,3"
          />
        </g>

        <!-- ======== 连线路径层（核心算法：Branch + Merge 贝塞尔曲线） ======== -->
        <g class="gg-edges">
          <!-- 1) 同轨道直线段：相邻 commit 之间的连线 -->
          <path
            v-for="(seg, si) in straightSegments"
            :key="'seg-' + si"
            :d="seg.d"
            :stroke="getTrackColor(seg.trackId)"
            :stroke-width="seg.isActive ? 2.5 : 1.6"
            :stroke-opacity="seg.isActive ? 0.85 : 0.35"
            fill="none"
            stroke-linecap="round"
            class="gg-edge"
            :class="{ 'gg-edge--active': seg.isActive }"
          />

          <!-- 2) Branch 曲线：从源 commit 分叉到新轨道的首次 commit -->
          <path
            v-for="(br, bi) in branchCurves"
            :key="'branch-' + bi"
            :d="br.d"
            :stroke="getTrackColor(br.targetTrackId || '')"
            stroke-width="2"
            fill="none"
            stroke-linecap="round"
            stroke-dasharray="6,3"
            class="gg-edge gg-edge--branch"
            marker-end="url(#gg-arrow-branch)"
          />

          <!-- 3) Merge 曲线：多条线汇聚到 merge commit -->
          <path
            v-for="(mr, mi) in mergeCurves"
            :key="'merge-' + mi"
            :d="mr.d"
            :stroke="mr.color"
            stroke-width="2"
            fill="none"
            stroke-linecap="round"
            class="gg-edge gg-edge--merge"
            opacity="0.75"
          />
        </g>

        <!-- ======== Commit 节点层 ======== -->
        <g class="gg-nodes">
          <g
            v-for="cm in commits"
            :key="cm.id"
            class="gg-commit-group"
            :class="{
              'gg-commit--head': cm.chapterIndex === currentChapter,
              'gg-commit--hover': hoverId === cm.id,
              'gg-commit--active': activeId === cm.id,
              'gg-commit--merge': !!cm.mergeFrom?.length,
              'gg-commit--branch': !!cm.branchFrom,
            }"
            @mouseenter="onCommitHover($event, cm)"
            @mouseleave="hideTooltip"
            @click="selectCommit(cm)"
          >
            <!-- HEAD 光晕脉冲环 -->
            <circle
              v-if="cm.chapterIndex === currentChapter"
              :cx="commitCx(cm)"
              :cy="commitCy(cm)"
              r="16"
              fill="none"
              stroke="#f59e0b"
              stroke-width="2"
              opacity="0.35"
              class="gg-pulse-ring"
            />

            <!-- Merge 节点：菱形/圆角矩形 -->
            <rect
              v-if="cm.mergeFrom?.length"
              :x="commitCx(cm) - 9"
              :y="commitCy(cm) - 9"
              width="18"
              height="18"
              rx="4"
              fill="url(#gg-grad-merge)"
              stroke="#8b5cf6"
              stroke-width="1.5"
              :filter="cm.chapterIndex === currentChapter ? 'url(#gg-glow-head)' : ''"
              class="gg-node-shape gg-merge-shape"
            />
            <text
              v-if="cm.mergeFrom?.length"
              :x="commitCx(cm)"
              :y="commitCy(cm) + 4"
              text-anchor="middle"
              font-size="9"
              font-weight="800"
              fill="#fff"
              font-family="var(--font-sans, monospace)"
            >⤝</text>

            <!-- 普通 / Branch 节点：圆 -->
            <circle
              v-if="!cm.mergeFrom?.length"
              :cx="commitCx(cm)"
              :cy="commitCy(cm)"
              :r="cm.chapterIndex === currentChapter ? 8 : (isActiveCommit(cm) ? 6.5 : 5)"
              :fill="'url(#gg-grad-' + (getTrackId(cm) || 'default') + ')'"
              :stroke="getTrackColor(getTrackId(cm))"
              :stroke-width="cm.chapterIndex === currentChapter ? 2.5 : 1.5"
              :filter="cm.chapterIndex === currentChapter ? 'url(#gg-glow-head)' : ''"
              class="gg-node-shape gg-circle"
              style="transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1)"
            />

            <!-- 标签文字 -->
            <text
              :x="commitCx(cm)"
              :y="commitCy(cm) - (cm.mergeFrom?.length ? 16 : 14)"
              text-anchor="middle"
              font-size="10"
              :font-weight="cm.chapterIndex === currentChapter ? '700' : '500'"
              :fill="cm.chapterIndex === currentChapter ? '#f59e0b' : '#94a3b8'"
              font-family="var(--font-sans, monospace)"
              class="gg-commit-label"
            >{{ cm.label }}</text>

            <!-- HEAD 文字标记 -->
            <text
              v-if="cm.chapterIndex === currentChapter && isMainTrack(getTrackId(cm))"
              :x="commitCx(cm) + 16"
              :y="commitCy(cm) + 4"
              font-size="9"
              font-weight="800"
              fill="#f59e0b"
              font-family="var(--font-sans, monospace)"
            >HEAD</text>

            <!-- Branch 标记 -->
            <text
              v-if="cm.branchFrom"
              :x="commitCx(cm) - 14"
              :y="commitCy(cm) - 12"
              font-size="8"
              fill="#22d3ee"
              font-family="var(--font-sans, monospace)"
              opacity="0.8"
            >branch</text>

            <!-- Merge 来源数标记 -->
            <text
              v-if="cm.mergeFrom?.length"
              :x="commitCx(cm) + 15"
              :y="commitCy(cm) + 4"
              font-size="8"
              fill="#a78bfa"
              font-family="var(--font-sans, monospace)"
            >×{{ cm.mergeFrom.length }}</text>
          </g>
        </g>

        <!-- ======== X 轴章节标签 ======== -->
        <g class="gg-x-axis">
          <text
            v-for="(ch, ci) in visibleChapters"
            :key="'xl-' + ch"
            :x="chapterToX(ch)"
            :y="svgHeight - 10"
            text-anchor="middle"
            :font-size="ci % chapterLabelStep === 0 ? 11 : 9"
            :font-weight="ci % chapterLabelStep === 0 ? '600' : '400'"
            :fill="ci % chapterLabelStep === 0 ? '#64748b' : '#475569'"
            font-family="var(--font-sans, monospace)"
          >Ch.{{ ch }}</text>
          <text
            :x="svgWidth - 10"
            :y="svgHeight - 22"
            text-anchor="end"
            font-size="10"
            fill="#475569"
            font-family="var(--font-sans, monospace)"
          >→ 章节 (Chapter) →</text>
        </g>
      </svg>

      <!-- ======== 左侧轨道标签（HTML overlay） ======== -->
      <div v-if="tracks.length" class="gg-track-labels">
        <div
          v-for="(tr, ti) in tracks"
          :key="'tl-' + tr.id"
          class="gg-track-label"
          :style="{ top: trackY(ti) + 'px' }"
        >
          <span class="gg-track-dot" :style="{ background: tr.color, boxShadow: `0 0 6px ${tr.color}40` }" />
          <span class="gg-track-name">{{ tr.label }}</span>
          <n-tag size="tiny" round :bordered="false" :type="tr.isMain ? 'success' : 'info'">
            {{ tr.isMain ? 'master' : 'branch' }}
          </n-tag>
        </div>
      </div>

      <!-- ======== 浮动 Tooltip ======== -->
      <Teleport to="body">
        <transition name="gg-fade">
          <div
            v-if="tooltip.visible"
            class="gg-tooltip"
            :style="{ left: tooltip.x + 'px', top: tooltip.y + 'px' }"
          >
            <div class="gg-tip-header">
              <span class="gg-tip-hash">#{{ tooltip.commit?.id?.slice(0, 7) }}</span>
              <span class="gg-tip-label">{{ tooltip.commit?.label }}</span>
            </div>
            <div class="gg-tip-body">
              <div class="gg-tip-row">
                <span class="gg-tip-k">章节</span>
                <span class="gg-tip-v">第 {{ tooltip.commit?.chapterIndex }} 章</span>
              </div>
              <div class="gg-tip-row">
                <span class="gg-tip-k">轨道</span>
                <span class="gg-tip-v">
                  <span class="gg-tip-dot" :style="{ background: tooltip.commit ? getTrackColor(getTrackId(tooltip.commit)) : '#94a3b8' }" />
                  {{ getTrackLabel(tooltip.commit) }}
                </span>
              </div>
              <div v-if="tooltip.commit?.branchFrom" class="gg-tip-row gg-tip-branch-info">
                <span class="gg-tip-k">Branch</span>
                <span class="gg-tip-v cyan">← fork from #{{ tooltip.commit.branchFrom.slice(0, 7) }}</span>
              </div>
              <div v-if="tooltip.commit?.mergeFrom?.length" class="gg-tip-row gg-tip-merge-info">
                <span class="gg-tip-k">Merge</span>
                <span class="gg-tip-v purple">⤝ {{ tooltip.commit.mergeFrom.length }} 条线汇合</span>
              </div>
              <div v-if="tooltip.commit?.chapterIndex === currentChapter" class="gg-tip-current">
                ● HEAD — 当前写作位置
              </div>
            </div>
            <div class="gg-tip-footer">
              <span class="gg-tip-hint">点击回滚到此 Commit</span>
            </div>
          </div>
        </transition>
      </Teleport>
    </div>

    <!-- ======== 底部详情面板（选中 Commit 后展示） ======== -->
    <transition name="gg-slide-up">
      <div v-if="activeCommitData" class="gg-detail-bar">
        <div class="gg-detail-main">
          <div class="gg-detail-left">
            <span class="gg-detail-badge" :class="{ 'gg-detail-badge--merge': activeCommitData.mergeFrom?.length }">
              {{ activeCommitData.mergeFrom?.length ? '⤝ Merge Commit' : '● Commit' }}
            </span>
            <span class="gg-detail-hash">#{{ activeCommitData.id.slice(0, 8) }}</span>
            <span class="gg-detail-label">{{ activeCommitData.label }}</span>
            <span v-if="activeCommitData.chapterIndex === currentChapter" class="gg-detail-head-tag">HEAD</span>
          </div>
          <div class="gg-detail-center">
            <div class="gg-detail-meta">
              <span><b>章节：</b>第 {{ activeCommitData.chapterIndex }} 章</span>
              <span><b>轨道：</b>{{ getTrackLabel(activeCommitData) }}</span>
            </div>
            <div v-if="activeCommitData.branchFrom" class="gg-detail-branch">
              <span class="cyan">↗ Branch from #{{ activeCommitData.branchFrom.slice(0, 8) }}</span>
            </div>
            <div v-if="activeCommitData.mergeFrom?.length" class="gg-detail-merge">
              <span class="purple">⤝ Merge: {{ activeCommitData.mergeFrom.length }} 条故事线在此交汇</span>
            </div>
          </div>
          <div class="gg-detail-actions">
            <n-button size="small" type="warning" secondary :loading="rollbacking" @click="confirmRollback(activeCommitData)">
              ↩ 回滚到此 Commit
            </n-button>
            <n-button size="tiny" quaternary @click="activeCommitData = null; activeId = null">
              ✕ 关闭
            </n-button>
          </div>
        </div>
      </div>
    </transition>

    <!-- ======== 底部状态栏 ======== -->
    <footer v-if="tracks.length" class="gg-footer">
      <span class="gg-stats">
        <b>{{ totalChapters }}</b> 章 ·
        <b>{{ commits.filter(c => c.branchFrom).length }}</b> 次 Branch ·
        <b>{{ commits.filter(c => c.mergeFrom?.length).length }}</b> 次 Merge ·
        <b>{{ tracks.length }}</b> Tracks
      </span>
      <span v-if="currentChapter !== null" class="gg-current-info">
        <span class="gg-current-dot" /> HEAD @ Ch.{{ currentChapter }}
      </span>
    </footer>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { useMessage, useDialog } from 'naive-ui'
import { workflowApi } from '../../api/workflow'
import { chroniclesApi } from '../../api/chronicles'
import { storeToRefs } from 'pinia'
import { useWorkbenchRefreshStore } from '../../stores/workbenchRefreshStore'
import type { StorylineDTO, StorylineGraphDataDTO, StorylineMergePointDTO } from '../../api/workflow'

// ==================== Props & Emits ====================
interface Props {
  slug: string
  currentChapter?: number
}
const props = defineProps<Props>()
const emit = defineEmits(['rollback'])
const message = useMessage()
const dialog = useDialog()
const refreshStore = useWorkbenchRefreshStore()
const { chroniclesTick } = storeToRefs(refreshStore)

// ==================== 类型定义 ====================
interface TrackDef {
  id: string
  color: string
  label: string
  isMain: boolean
  storylineType: string
}

interface CommitDef {
  id: string
  chapterIndex: number
  trackId: string
  label: string
  branchFrom?: string       // 从哪个 commit 的 trackId 分支出来
  mergeFrom?: string[]      // 哪些 commit 的 ID 汇合到这个节点
  description?: string
}

// ==================== 响应式状态 ====================
const loading = ref(false)
const rollbacking = ref(false)
const zoomed = ref(false)
const canvasRef = ref<HTMLElement | null>(null)

// 数据
const rawStorylines = ref<StorylineDTO[]>([])
const rawMergePoints = ref<StorylineMergePointDTO[]>([])

// 交互
const hoverId = ref<string | null>(null)
const activeId = ref<string | null>(null)
const activeCommitData = ref<CommitDef | null>(null)

// Tooltip
const tooltip = ref({
  visible: false,
  x: 0,
  y: 0,
  commit: null as CommitDef | null,
})

// ==================== 布局常量 ====================
const GAP_X = 110             // 章节水平间距
const GAP_Y = 72              // 轨道垂直间距
const labelWidth = 130        // 左侧标签区宽度
const paddingT = 30           // 顶部留白
const paddingB = 45           // 底部留白（X轴标签）
const paddingR = 40           // 右侧留白

// ==================== 颜色系统 ====================
const LINE_COLORS: Record<string, string> = {
  main_plot: '#6366f1',   // indigo - 主线 master
  romance: '#ec4899',     // pink
  revenge: '#ef4444',     // red
  mystery: '#8b5cf6',     // violet
  growth: '#10b981',      // emerald
  political: '#f59e0b',   // amber
  adventure: '#06b6d4',   // cyan
  family: '#f97316',      // orange
  friendship: '#84cc16',  // lime
}

function getLineColor(type: string): string {
  return LINE_COLORS[type] || '#94a3b8'
}

function adjustColor(hex: string, amount: number): string {
  const num = parseInt(hex.replace('#', ''), 16)
  const r = Math.min(255, Math.max(0, (num >> 16) + amount))
  const g = Math.min(255, Math.max(0, ((num >> 8) & 0xff) + amount))
  const b = Math.min(255, Math.max(0, (num & 0xff) + amount))
  return '#' + ((1 << 24) | (r << 16) | (g << 8) | b).toString(16).slice(1)
}

const TYPE_LABELS: Record<string, string> = {
  main_plot: '主线', romance: '爱情线', revenge: '复仇线',
  mystery: '悬疑线', growth: '成长线', political: '政治线',
  adventure: '冒险线', family: '家庭线', friendship: '友情线',
}
function getTypeLabel(t: string): string { return TYPE_LABELS[t] || t }

// ==================== 核心数据转换：原始 Storylines → Tracks + Commits ====================
/** 轨道列表 */
const tracks = computed<TrackDef[]>(() => {
  return rawStorylines.value.map((sl) => ({
    id: sl.id,
    color: getLineColor(sl.storyline_type),
    label: (sl.name || getTypeLabel(sl.storyline_type)).slice(0, 14),
    isMain: sl.storyline_type === 'main_plot',
    storylineType: sl.storyline_type,
  }))
})

/** Commit 列表：每个故事线在每个活跃章节产生一个 commit */
const commits = computed<CommitDef[]>(() => {
  const result: CommitDef[] = []
  const lines = rawStorylines.value

  for (const sl of lines) {
    for (let ch = sl.estimated_chapter_start; ch <= sl.estimated_chapter_end; ch++) {
      const id = `${sl.id}-ch${ch}`
      const commit: CommitDef = {
        id,
        chapterIndex: ch,
        trackId: sl.id,
        label: buildCommitLabel(ch, sl),
        description: sl.description,
      }
      result.push(commit)
    }
  }

  // 标注 Branch 关系：如果一条线的起始章节与另一条线重叠，且不是主线，则视为分支
  detectBranches(result, lines)

  // 标注 Merge 关系：基于 merge_points 数据
  detectMerges(result)

  // 按 chapterIndex 排序
  result.sort((a, b) => a.chapterIndex - b.chapterIndex || a.trackId.localeCompare(b.trackId))

  return result
})

/** 自动生成 commit label */
function buildCommitLabel(ch: number, sl: StorylineDTO): string {
  const typeName = getTypeLabel(sl.storyline_type)
  // 如果有里程碑，优先用里程碑标题
  if (sl.milestones?.length) {
    const ms = sl.milestones.find(m => ch >= m.target_chapter_start && ch <= m.target_chapter_end)
    if (ms?.title) return ms.title.slice(0, 12)
  }
  return `${typeName}·Ch.${ch}`
}

/** 检测 Branch 关系 */
function detectBranches(commits: CommitDef[], lines: StorylineDTO[]) {
  const mainLine = lines.find(l => l.storyline_type === 'main_plot')
  if (!mainLine) return

  for (const commit of commits) {
    const sl = lines.find(l => l.id === commit.trackId)
    if (!sl || sl.storyline_type === 'main_plot') continue

    // 如果这条支线的起始章节正好在主线的活跃范围内，视为从主线 branch 出来
    if (commit.chapterIndex === sl.estimated_chapter_start &&
        commit.chapterIndex >= mainLine.estimated_chapter_start &&
        commit.chapterIndex <= mainLine.estimated_chapter_end) {
      // 找到主线上同一章节的 commit 作为 branch source
      const sourceCommit = commits.find(c =>
        c.trackId === mainLine.id && c.chapterIndex === commit.chapterIndex
      )
      if (sourceCommit) {
        commit.branchFrom = sourceCommit.id
      }
    }

    // 也检测从其他非主线 branch 出的情况
    if (!commit.branchFrom && sl.storyline_type !== 'main_plot') {
      for (const other of lines) {
        if (other.id === sl.id) continue
        if (commit.chapterIndex === sl.estimated_chapter_start &&
            commit.chapterIndex >= other.estimated_chapter_start &&
            commit.chapterIndex <= other.estimated_chapter_end) {
          const src = commits.find(c => c.trackId === other.id && c.chapterIndex === commit.chapterIndex)
          if (src) { commit.branchFrom = src.id; break }
        }
      }
    }
  }
}

/** 基于 merge_points 数据标注 Merge 关系 */
function detectMerges(commits: CommitDef[]) {
  const mps = rawMergePoints.value
  for (const mp of mps) {
    if (mp.merge_type !== 'convergence') continue
    // 找到 merge 章节的所有 commit
    const targetCommits = commits.filter(c => c.chapterIndex === mp.chapter_number)
    // 涉及的故事线 ID
    const involvedIds = new Set(mp.storyline_ids)
    // 在目标章节中，属于涉及线的 commit 标注为 merge
    for (const tc of targetCommits) {
      if (involvedIds.has(tc.trackId)) {
        // 收集其他线的来源 commit
        const sources: string[] = []
        for (const otherId of involvedIds) {
          if (otherId === tc.trackId) continue
          // 找到该线在 merge 章节前一个 commit
          const prevCommit = [...commits]
            .filter(c => c.trackId === otherId && c.chapterIndex < mp.chapter_number)
            .sort((a, b) => b.chapterIndex - a.chapterIndex)[0]
          if (prevCommit) sources.push(prevCommit.id)
        }
        if (sources.length > 0) {
          tc.mergeFrom = sources
        }
      }
    }
  }
}

// ==================== 坐标计算 ====================
function getTrackIndex(trackId: string): number {
  return tracks.value.findIndex(t => t.id === trackId)
}

function trackY(_index: number): number {
  return paddingT + _index * GAP_Y + GAP_Y / 2
}

function chapterToX(ch: number): number {
  return labelWidth + ch * GAP_X + GAP_X / 2
}

function commitCx(cm: CommitDef): number {
  return chapterToX(cm.chapterIndex)
}

function commitCy(cm: CommitDef): number {
  const idx = getTrackIndex(cm.trackId)
  return idx >= 0 ? trackY(idx) : paddingT + GAP_Y / 2
}

function getTrackId(cm: CommitDef): string {
  return cm.trackId
}

function getTrackColor(trackId: string): string {
  return tracks.value.find(t => t.id === trackId)?.color || '#94a3b8'
}

function getTrackLabel(cm: CommitDef | null): string {
  if (!cm) return '—'
  const tr = tracks.value.find(t => t.id === cm.trackId)
  return tr?.label || '—'
}

function isMainTrack(trackId: string): boolean {
  return tracks.value.find(t => t.id === trackId)?.isMain ?? false
}

function isActiveCommit(cm: CommitDef): boolean {
  const cc = props.currentChapter
  if (cc === null || cc === undefined) return false
  // 同一轨道上当前章节附近的 commit 视为活跃
  return cm.trackId === activeCommitData.value?.trackId ||
         cm.chapterIndex === cc
}

// ==================== SVG 尺寸 ====================
const svgWidth = computed(() => {
  if (!commits.value.length) return labelWidth + 400
  const maxCh = Math.max(...commits.value.map(c => c.chapterIndex), 0)
  return labelWidth + (maxCh + 1) * GAP_X + paddingR
})

const svgHeight = computed(() => {
  const tc = Math.max(tracks.value.length, 1)
  return paddingT + tc * GAP_Y + paddingB
})

// ==================== 章节显示采样 ====================
const allChapters = computed(() => {
  const set = new Set<number>()
  for (const c of commits.value) set.add(c.chapterIndex)
  return Array.from(set).sort((a, b) => a - b)
})

const visibleChapters = computed(() => {
  const chs = allChapters.value
  if (chs.length <= 20) return chs
  const step = Math.ceil(chs.length / 20)
  return chs.filter((_, i) => i % step === 0 || i === chs.length - 1)
})

const chapterLabelStep = computed(() => {
  const chs = allChapters.value
  if (chs.length <= 20) return 1
  return Math.ceil(chs.length / 20)
})

const totalChapters = computed(() => allChapters.value.length)

// ==================== 核心：路径生成算法 ====================

/** 直线段：同轨道相邻 commit 之间的连线 */
interface StraightSeg {
  d: string
  trackId: string
  isActive: boolean
}

const straightSegments = computed<StraightSeg[]>(() => {
  const segs: StraightSeg[] = []
  for (const tr of tracks.value) {
    const trackCommits = commits.value
      .filter(c => c.trackId === tr.id)
      .sort((a, b) => a.chapterIndex - b.chapterIndex)

    for (let i = 0; i < trackCommits.length - 1; i++) {
      const c1 = trackCommits[i]
      const c2 = trackCommits[i + 1]
      segs.push({
        d: `M ${commitCx(c1)} ${commitCy(c1)} L ${commitCx(c2)} ${commitCy(c2)}`,
        trackId: tr.id,
        isActive: isActiveCommit(c1) || isActiveCommit(c2),
      })
    }
  }
  return segs
})

/** Branch 曲线：从源 commit 到分叉出的新 commit */
interface CurvePath {
  d: string
  targetTrackId?: string
  color?: string
}

const branchCurves = computed<CurvePath[]>(() => {
  const curves: CurvePath[] = []
  for (const cm of commits.value) {
    if (!cm.branchFrom) continue
    const source = commits.value.find(c => c.id === cm.branchFrom)
    if (!source) continue

    const x1 = commitCx(source)
    const y1 = commitCy(source)
    const x2 = commitCx(cm)
    const y2 = commitCy(cm)
    const dx = x2 - x1
    // 三次贝塞尔曲线：水平先走一段再弯过去
    curves.push({
      d: `M ${x1} ${y1} C ${x1 + dx * 0.4} ${y1}, ${x2 - dx * 0.4} ${y2}, ${x2} ${y2}`,
      targetTrackId: cm.trackId,
    })
  }
  return curves
})

/** Merge 曲线：各线汇聚到 merge 点 */
const mergeCurves = computed<CurvePath[]>(() => {
  const curves: CurvePath[] = []
  const processed = new Set<string>()

  for (const cm of commits.value) {
    if (!cm.mergeFrom?.length) continue
    const mx = commitCx(cm)
    const my = commitCy(cm)

    for (const sourceId of cm.mergeFrom) {
      if (processed.has(sourceId + '-' + cm.id)) continue
      processed.add(sourceId + '-' + cm.id)

      const source = commits.value.find(c => c.id === sourceId)
      if (!source) continue

      const sx = commitCx(source)
      const sy = commitCy(source)
    const _dx = mx - sx

    curves.push({
      d: `M ${sx} ${sy} C ${sx + _dx * 0.45} ${sy}, ${mx - _dx * 0.35} ${my}, ${mx} ${my}`,
      color: getTrackColor(source.trackId),
    })
    }
  }
  return curves
})

// ==================== 交互方法 ====================
function toggleZoom() { zoomed.value = !zoomed.value }

function onCommitHover(event: MouseEvent, cm: CommitDef) {
  hoverId.value = cm.id
  const rect = canvasRef.value?.getBoundingClientRect()
  if (!rect) return
  tooltip.value = {
    visible: true,
    x: event.clientX - rect.left + 16,
    y: event.clientY - rect.top - 10,
    commit: cm,
  }
}

function hideTooltip() {
  tooltip.value.visible = false
  hoverId.value = null
}

function selectCommit(cm: CommitDef) {
  if (activeId.value === cm.id) {
    activeId.value = null
    activeCommitData.value = null
  } else {
    activeId.value = cm.id
    activeCommitData.value = cm
  }
}

// ==================== 回滚逻辑 ====================
async function confirmRollback(cm: CommitDef) {
  dialog.warning({
    title: '⚠️ 全息回滚确认',
    content: `回滚到 Commit [${cm.label}] (第${cm.chapterIndex}章) 将删除之后所有章节内容。此操作不可撤销，确定继续？`,
    positiveText: '确认回滚',
    negativeText: '取消',
    onPositiveClick: async () => {
      rollbacking.value = true
      try {
        const res = await chroniclesApi.get(props.slug)
        const snaps = res.rows
          .filter(r => r.chapter_index >= cm.chapterIndex)
          .flatMap(r => r.snapshots)
          .sort((a, b) => (a.anchor_chapter ?? 0) - (b.anchor_chapter ?? 0))
        if (!snaps.length) {
          message.warning('该章节无可用快照，请先在全息编年史中创建快照')
          return false
        }
        const target = [...snaps].reverse().find(s => (s.anchor_chapter ?? 0) <= cm.chapterIndex) || snaps[0]
        const result = await chroniclesApi.rollbackToSnapshot(props.slug, target.id)
        message.success(`已回滚：删除 ${result.deleted_count} 个章节`)
        emit('rollback', cm)
        refreshStore.bumpAfterChapterDeskChange()
        activeCommitData.value = null
        activeId.value = null
        await loadData()
      } catch (e: any) {
        message.error(e?.response?.data?.detail || '回滚失败')
        return false
      } finally {
        rollbacking.value = false
      }
    },
  })
}

function onScroll() {
  /* 保留滚动状态追踪能力 */
}

// ==================== 数据加载 ====================
async function loadData() {
  loading.value = true
  try {
    const data: StorylineGraphDataDTO = await workflowApi.getStorylineGraphData(props.slug)
    rawStorylines.value = data.storylines || []
    rawMergePoints.value = data.merge_points || []
  } catch (_e) {
    try {
      rawStorylines.value = await workflowApi.getStorylines(props.slug)
      rawMergePoints.value = []
    } catch (e2: any) {
      message.error(e2?.response?.data?.detail || '加载失败')
    }
  } finally {
    loading.value = false
  }
}

// ==================== Lifecycle ====================
watch(() => props.slug, () => void loadData(), { immediate: true })
watch(chroniclesTick, () => void loadData())
onMounted(() => void loadData())
</script>

<style scoped>
/* ==================== 容器 ==================== */
.gg-container {
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: #0f1117;
  border-radius: 12px;
  position: relative;
}

/* ==================== Header ==================== */
.gg-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 16px;
  background: linear-gradient(180deg, #161820 0%, #13141c 100%);
  border-bottom: 1px solid rgba(99, 102, 241, 0.12);
  flex-shrink: 0;
  border-radius: 12px 12px 0 0;
}

.gg-header-left {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.gg-logo {
  font-size: 18px;
  line-height: 1;
  color: #a78bfa;
  font-weight: 700;
}

.gg-title {
  margin: 0;
  font-size: 13px;
  font-weight: 600;
  color: #e2e8f0;
  letter-spacing: 0.03em;
  white-space: nowrap;
}

.gg-header-right {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-shrink: 0;
}

/* ==================== Canvas ==================== */
.gg-canvas {
  flex: 1;
  min-height: 0;
  overflow: auto;
  position: relative;
  cursor: default;
  background:
    radial-gradient(ellipse at 50% 0%, rgba(99, 102, 241, 0.04) 0%, transparent 60%),
    #0f1117;
}

.gg-canvas.gg--zoomed {
  overflow: auto;
}

.gg-svg {
  display: block;
  width: 100%;
  min-width: max-content;
}

/* ==================== 左侧轨道标签 ==================== */
.gg-track-labels {
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  width: labelWidth;
  pointer-events: none;
  z-index: 5;
}

.gg-track-label {
  position: absolute;
  left: 8px;
  transform: translateY(-50%);
  display: flex;
  align-items: center;
  gap: 6px;
  pointer-events: auto;
  padding: 4px 10px;
  background: rgba(22, 24, 32, 0.9);
  backdrop-filter: blur(8px);
  border-radius: 8px;
  border: 1px solid rgba(99, 102, 241, 0.12);
  transition: all 0.2s ease;
  white-space: nowrap;
  font-size: 11px;
}

.gg-track-label:hover {
  background: rgba(30, 34, 46, 0.95);
  border-color: rgba(99, 102, 241, 0.25);
  transform: translateY(-50%) scale(1.03);
}

.gg-track-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

.gg-track-name {
  font-weight: 600;
  color: #cbd5e1;
  font-size: 11px;
  letter-spacing: 0.01em;
}

/* ==================== 边线样式 ==================== */
.gg-edge {
  transition: all 0.25s ease;
}

.gg-edge:hover {
  stroke-width: 3.5;
}

.gg-edge--active {
  opacity: 0.85 !important;
}

.gg-edge--branch {
  stroke-dasharray: 6,4;
  animation: flow-dash 1.5s linear infinite;
}

.gg-edge--merge {
  stroke-dasharray: none;
}

@keyframes flow-dash {
  to { stroke-dashoffset: -18; }
}

/* ==================== Commit 节点 ==================== */
.gg-commit-group {
  cursor: pointer;
  outline: none;
}

.gg-node-shape {
  transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
}

.gg-commit-group:hover .gg-circle {
  filter: url(#gg-glow);
  transform-origin: center;
  transform: scale(1.25);
}

.gg-commit-group:hover .gg-merge-shape {
  transform: scale(1.12);
  transform-origin: center;
}

.gg-commit--head .gg-circle {
  animation: pulse-head 2s ease-in-out infinite;
}

.gg-pulse-ring {
  animation: pulse-ring 2s ease-in-out infinite;
}

@keyframes pulse-head {
  0%, 100% { transform: scale(1); }
  50% { transform: scale(1.18); }
}

@keyframes pulse-ring {
  0%, 100% { opacity: 0.35; r: 16; }
  50% { opacity: 0.08; r: 24; }
}

.gg-commit-label {
  transition: fill 0.2s ease;
}

.gg-commit-group:hover .gg-commit-label {
  fill: #e2e8f0;
}

/* ==================== Tooltip ==================== */
.gg-tooltip {
  position: fixed;
  z-index: 9999;
  padding: 0;
  background: rgba(15, 17, 23, 0.96);
  backdrop-filter: blur(16px);
  border-radius: 10px;
  color: #e2e8f0;
  font-size: 12px;
  line-height: 1.5;
  pointer-events: none;
  box-shadow:
    0 0 0 1px rgba(99, 102, 241, 0.15),
    0 12px 40px rgba(0, 0, 0, 0.5),
    0 0 60px rgba(99, 102, 241, 0.08);
  min-width: 200px;
  max-width: 280px;
  font-family: var(--font-sans, system-ui);
  overflow: hidden;
}

.gg-tip-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px 6px;
  background: linear-gradient(135deg, rgba(99, 102, 241, 0.15), rgba(139, 92, 246, 0.08));
  border-bottom: 1px solid rgba(99, 102, 241, 0.12);
}

.gg-tip-hash {
  font-family: monospace;
  font-size: 11px;
  font-weight: 700;
  color: #a78bfa;
}

.gg-tip-label {
  font-weight: 600;
  color: var(--app-surface-subtle);
  font-size: 12px;
}

.gg-tip-body {
  padding: 8px 12px;
}

.gg-tip-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  padding: 2px 0;
}

.gg-tip-k {
  color: #64748b;
  font-size: 11px;
  flex-shrink: 0;
}

.gg-tip-v {
  color: #cbd5e1;
  font-size: 11px;
  display: flex;
  align-items: center;
  gap: 5px;
}

.gg-tip-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  flex-shrink: 0;
}

.gg-tip-branch-info .gg-tip-v.cyan { color: #22d3ee; }
.gg-tip-merge-info .gg-tip-v.purple { color: #a78bfa; }

.gg-tip-current {
  margin-top: 6px;
  padding-top: 6px;
  border-top: 1px solid rgba(245, 158, 11, 0.2);
  color: #f59e0b;
  font-weight: 600;
  font-size: 11px;
}

.gg-tip-footer {
  padding: 5px 12px 7px;
  border-top: 1px solid rgba(255, 255, 255, 0.05);
  text-align: center;
}

.gg-tip-hint {
  font-size: 10px;
  color: #475569;
}

/* ==================== 详情面板 ==================== */
.gg-detail-bar {
  flex-shrink: 0;
  background: linear-gradient(135deg, rgba(99, 102, 241, 0.08) 0%, rgba(139, 92, 246, 0.05) 100%);
  border-top: 1px solid rgba(99, 102, 241, 0.15);
  padding: 12px 16px;
  animation: slideUp 0.28s cubic-bezier(0.4, 0, 0.2, 1);
}

.gg-detail-main {
  display: flex;
  align-items: center;
  gap: 16px;
  flex-wrap: wrap;
}

.gg-detail-left {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

.gg-detail-badge {
  font-size: 10px;
  font-weight: 800;
  padding: 3px 10px;
  border-radius: 6px;
  background: linear-gradient(135deg, #6366f1, #818cf8);
  color: #fff;
  letter-spacing: 0.06em;
  font-family: var(--font-sans, monospace);
}

.gg-detail-badge--merge {
  background: linear-gradient(135deg, #a78bfa, #6366f1);
}

.gg-detail-hash {
  font-family: monospace;
  font-size: 11px;
  font-weight: 600;
  color: #a78bfa;
}

.gg-detail-label {
  font-size: 13px;
  font-weight: 600;
  color: #e2e8f0;
}

.gg-detail-head-tag {
  font-size: 9px;
  font-weight: 800;
  padding: 2px 8px;
  border-radius: 4px;
  background: linear-gradient(135deg, #f59e0b, #ef4444);
  color: #fff;
  letter-spacing: 0.05em;
}

.gg-detail-center {
  flex: 1;
  min-width: 220px;
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.gg-detail-meta {
  display: flex;
  gap: 16px;
  font-size: 12px;
  color: #94a3b8;
}

.gg-detail-meta b {
  color: #cbd5e1;
}

.gg-detail-branch .cyan { color: #22d3ee; font-size: 11px; }
.gg-detail-merge .purple { color: #a78bfa; font-size: 11px; }

.gg-detail-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

/* ==================== Footer ==================== */
.gg-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 6px 16px;
  background: linear-gradient(180deg, #13141c 0%, #161820 100%);
  border-top: 1px solid rgba(99, 102, 241, 0.1);
  font-size: 11px;
  color: #475569;
  flex-shrink: 0;
  border-radius: 0 0 12px 12px;
}

.gg-stats b {
  color: #94a3b8;
  font-weight: 600;
}

.gg-current-info {
  display: flex;
  align-items: center;
  gap: 5px;
  font-size: 11px;
  color: #f59e0b;
  font-weight: 600;
  font-family: var(--font-sans, monospace);
}

.gg-current-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #f59e0b;
  animation: blink-dot 1.5s ease-in-out infinite;
}

@keyframes blink-dot {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.3; }
}

/* ==================== 状态页 ==================== */
.gg-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 60px 20px;
  gap: 12px;
  color: #475569;
  font-size: 13px;
}

.gg-spinner {
  width: 32px;
  height: 32px;
  border: 3px solid rgba(99, 102, 241, 0.15);
  border-top-color: #6366f1;
  border-radius: 50%;
  animation: spin 0.7s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.gg-empty-icon {
  font-size: 40px;
  line-height: 1;
  opacity: 0.6;
}

.gg-empty-title {
  font-size: 15px;
  font-weight: 600;
  color: #94a3b8;
  margin: 0;
}

.gg-empty-desc {
  font-size: 12.5px;
  color: #475569;
  margin: 0;
  max-width: 280px;
  text-align: center;
  line-height: 1.55;
}

/* ==================== Transitions ==================== */
.gg-fade-enter-active { transition: opacity 0.15s ease; }
.gg-fade-leave-active { transition: opacity 0.1s ease; }
.gg-fade-enter-from, .gg-fade-leave-to { opacity: 0; }

.gg-slide-up-enter-active {
  transition: all 0.28s cubic-bezier(0.4, 0, 0.2, 1);
  overflow: hidden;
}
.gg-slide-up-leave-active {
  transition: all 0.2s ease;
  overflow: hidden;
}
.gg-slide-up-enter-from {
  opacity: 0;
  transform: translateY(12px);
  max-height: 0;
  padding-top: 0;
  padding-bottom: 0;
}
.gg-slide-up-leave-to {
  opacity: 0;
  max-height: 0;
  padding-top: 0;
  padding-bottom: 0;
}

@keyframes slideUp {
  from { opacity: 0; transform: translateY(12px); }
  to { opacity: 1; transform: translateY(0); }
}
</style>
