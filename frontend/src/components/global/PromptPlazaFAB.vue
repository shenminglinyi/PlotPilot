<template>
  <teleport to="body">
    <div
      class="plaza-fab-shell"
      :class="{ 'is-dragging': dragging, 'is-hovered': hovering }"
      :style="shellStyle"
    >
      <div
        class="plaza-fab-actions"
        @mouseenter="setHovering(true)"
        @mouseleave="scheduleHideHover"
      >
        <button
          type="button"
          class="plaza-fab-action"
          :title="mode === 'expanded' ? '最小化' : '展开'"
          @pointerdown.stop
          @click.stop="toggleMinimize"
        >
          <svg v-if="mode === 'expanded'" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" width="16" height="16">
            <rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect>
            <line x1="8" y1="12" x2="16" y2="12"></line>
          </svg>
          <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" width="16" height="16">
            <rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect>
            <line x1="8" y1="12" x2="16" y2="12"></line>
            <line x1="12" y1="8" x2="12" y2="16"></line>
          </svg>
        </button>
      </div>

      <!-- FAB 主按钮 -->
      <button
        ref="fabRef"
        type="button"
        class="plaza-fab-main"
        :class="[`mode-${mode}`, { 'is-open': showDrawer }]"
        aria-label="打开提示词广场"
        @mouseenter="setHovering(true)"
        @mouseleave="scheduleHideHover"
        @pointerdown="onPointerDown"
        @keydown.enter.prevent="toggleDrawer"
        @keydown.space.prevent="toggleDrawer"
      >
        <span class="fab-glow"></span>
        <span class="fab-content">
          <span class="fab-icon">🏪</span>
          <span v-if="mode === 'expanded'" class="fab-label">提示词广场</span>
        </span>
        <!-- 角标：提示词数量 -->
        <span v-if="promptCount > 0" class="fab-badge">{{ promptCount }}</span>
      </button>

      <!-- 抽屉 -->
      <n-drawer
        :show="showDrawer"
        placement="right"
        :width="720"
        :close-on-esc="true"
        :mask-closable="true"
        @update:show="handleDrawerChange"
      >
        <n-drawer-content
          closable
          :header-style="{ padding: '16px 20px' }"
          :native-scrollbar="false"
          :body-content-style="{ padding: 0, overflow: 'hidden' }"
        >
          <template #header>
            <div class="drawer-header">
              <div class="drawer-title-row">
                <span class="drawer-icon">🏪</span>
                <span class="drawer-title">提示词广场</span>
                <n-tag size="small" type="info" :bordered="false" v-if="stats">
                  {{ stats.total_nodes }} 个 · {{ stats.total_versions }} 版本
                </n-tag>
              </div>
              <p class="drawer-subtitle">
                浏览、编辑、版本管理所有 AI 提示词
              </p>
            </div>
          </template>

          <PromptPlaza @refresh-stats="loadStats" />
        </n-drawer-content>
      </n-drawer>
    </div>
  </teleport>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { NDrawer, NDrawerContent, NTag } from 'naive-ui'
import PromptPlaza from '../workbench/PromptPlaza.vue'
import { promptPlazaApi, type PromptStats } from '../../api/llmControl'

type DockSide = 'left' | 'right'
type FabMode = 'expanded' | 'minimized'

interface PersistedFabState {
  version: 1
  dock: DockSide
  yRatio: number
  mode: FabMode
}

const STORAGE_KEY = 'plotpilot.prompt-plaza-fab.state.v1'
const EDGE_GAP = 10
const TOP_SAFE_GAP = 88
const BOTTOM_SAFE_GAP = 24
const CLICK_THRESHOLD = 6

const fabRef = ref<HTMLButtonElement>()
const showDrawer = ref(false)
const promptCount = ref(0)
const stats = ref<PromptStats | null>(null)
const dragging = ref(false)
const hovering = ref(false)
const viewportWidth = ref(getViewportWidth())
const viewportHeight = ref(getViewportHeight())
const position = ref({ x: 0, y: 0 })
const dockSide = ref<DockSide>('right')
const mode = ref<FabMode>('expanded')
const yRatio = ref(0.8)

const dragState = {
  active: false,
  moved: false,
  startX: 0,
  startY: 0,
  originX: 0,
  originY: 0,
}

let hoverHideTimer: ReturnType<typeof setTimeout> | null = null

function getViewportWidth(): number {
  if (typeof window === 'undefined') return 1440
  return document.documentElement?.clientWidth || window.innerWidth || 1440
}

function getViewportHeight(): number {
  if (typeof window === 'undefined') return 900
  return document.documentElement?.clientHeight || window.innerHeight || 900
}

const shellStyle = computed(() => ({
  left: `${position.value.x}px`,
  top: `${position.value.y}px`,
}))

function getFallbackSize() {
  if (mode.value === 'minimized') return { width: 52, height: 52 }
  return { width: 140, height: 52 }
}

function getButtonSize() {
  const rect = fabRef.value?.getBoundingClientRect()
  if (!rect || !rect.width || !rect.height) return getFallbackSize()
  return {
    width: rect.width,
    height: rect.height,
  }
}

function getVerticalBounds(height: number) {
  const minY = TOP_SAFE_GAP
  const maxY = Math.max(minY, viewportHeight.value - height - BOTTOM_SAFE_GAP)
  return { minY, maxY }
}

function getDockedX(width: number) {
  return dockSide.value === 'left'
    ? EDGE_GAP
    : Math.max(EDGE_GAP, viewportWidth.value - width - EDGE_GAP)
}

function getYFromRatio(height: number) {
  const { minY, maxY } = getVerticalBounds(height)
  if (maxY <= minY) return minY
  const ratio = Math.min(Math.max(yRatio.value, 0), 1)
  return minY + (maxY - minY) * ratio
}

function setRatioFromY(y: number, height: number) {
  const { minY, maxY } = getVerticalBounds(height)
  if (maxY <= minY) {
    yRatio.value = 0
    return
  }
  const safeY = Math.min(Math.max(minY, y), maxY)
  yRatio.value = (safeY - minY) / (maxY - minY)
}

function clampFreePosition(nextX: number, nextY: number) {
  const { width, height } = getButtonSize()
  const maxX = Math.max(0, viewportWidth.value - width)
  const { minY, maxY } = getVerticalBounds(height)
  return {
    x: Math.min(Math.max(0, nextX), maxX),
    y: Math.min(Math.max(minY, nextY), maxY),
  }
}

function saveState() {
  const payload: PersistedFabState = {
    version: 1,
    dock: dockSide.value,
    yRatio: Number(yRatio.value.toFixed(4)),
    mode: mode.value,
  }
  localStorage.setItem(STORAGE_KEY, JSON.stringify(payload))
}

function applyDockPosition(shouldPersist = false) {
  const { width, height } = getButtonSize()
  position.value = {
    x: getDockedX(width),
    y: getYFromRatio(height),
  }
  if (shouldPersist) saveState()
}

function defaultState() {
  dockSide.value = 'right'
  mode.value = 'minimized'
  yRatio.value = 0.8
}

function restoreState() {
  defaultState()
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return
    const parsed = JSON.parse(raw) as Partial<PersistedFabState> & { mode?: string }
    if (parsed.dock === 'left' || parsed.dock === 'right') {
      dockSide.value = parsed.dock
    }
    if (parsed.mode === 'expanded' || parsed.mode === 'minimized') {
      mode.value = parsed.mode
    }
    if (typeof parsed.yRatio === 'number' && Number.isFinite(parsed.yRatio)) {
      yRatio.value = Math.min(Math.max(parsed.yRatio, 0), 1)
    }
  } catch {
    defaultState()
  }
}

function toggleDrawer() {
  showDrawer.value = !showDrawer.value
}

function handleDrawerChange(val: boolean) {
  showDrawer.value = val
}

async function loadStats() {
  try {
    const res = await promptPlazaApi.getStats()
    const data = res as unknown as PromptStats
    stats.value = data
    promptCount.value = data?.total_nodes || 0
  } catch {
    // 静默失败
  }
}

function clearHoverHideTimer() {
  if (hoverHideTimer) {
    clearTimeout(hoverHideTimer)
    hoverHideTimer = null
  }
}

function setHovering(value: boolean) {
  clearHoverHideTimer()
  hovering.value = value
}

function scheduleHideHover() {
  clearHoverHideTimer()
  hoverHideTimer = setTimeout(() => {
    hovering.value = false
  }, 160)
}

function toggleMinimize() {
  mode.value = mode.value === 'expanded' ? 'minimized' : 'expanded'
}

function syncViewport() {
  viewportWidth.value = getViewportWidth()
  viewportHeight.value = getViewportHeight()
  applyDockPosition()
}

function stopDragging() {
  dragState.active = false
  dragging.value = false
  window.removeEventListener('pointermove', onPointerMove)
  window.removeEventListener('pointerup', onPointerUp)
  window.removeEventListener('pointercancel', onPointerCancel)
}

function onPointerMove(event: PointerEvent) {
  if (!dragState.active) return
  const dx = event.clientX - dragState.startX
  const dy = event.clientY - dragState.startY
  if (!dragState.moved && (Math.abs(dx) >= CLICK_THRESHOLD || Math.abs(dy) >= CLICK_THRESHOLD)) {
    dragState.moved = true
    dragging.value = true
  }
  if (!dragState.moved) return
  position.value = clampFreePosition(dragState.originX + dx, dragState.originY + dy)
}

function snapToEdge() {
  const { width, height } = getButtonSize()
  const centerX = position.value.x + width / 2
  dockSide.value = centerX < viewportWidth.value / 2 ? 'left' : 'right'
  setRatioFromY(position.value.y, height)
  applyDockPosition(true)
}

function onPointerUp() {
  const moved = dragState.moved
  stopDragging()
  if (moved) {
    snapToEdge()
    return
  }
  toggleDrawer()
}

function onPointerCancel() {
  stopDragging()
  applyDockPosition()
}

function onPointerDown(event: PointerEvent) {
  if (event.button !== 0) return
  dragState.active = true
  dragState.moved = false
  dragState.startX = event.clientX
  dragState.startY = event.clientY
  dragState.originX = position.value.x
  dragState.originY = position.value.y
  window.addEventListener('pointermove', onPointerMove)
  window.addEventListener('pointerup', onPointerUp)
  window.addEventListener('pointercancel', onPointerCancel)
}

watch(mode, async () => {
  await nextTick()
  applyDockPosition(true)
})

onMounted(async () => {
  restoreState()
  await nextTick()
  applyDockPosition()
  window.addEventListener('resize', syncViewport)
  loadStats()
})

onBeforeUnmount(() => {
  clearHoverHideTimer()
  stopDragging()
  window.removeEventListener('resize', syncViewport)
})

// 暴露方法供外部调用
defineExpose({
  open: () => { showDrawer.value = true },
  close: () => { showDrawer.value = false },
})
</script>

<style scoped>
.plaza-fab-shell {
  position: fixed;
  z-index: 890; /* 略低于 AI 控制台的 900 */
  user-select: none;
  touch-action: none;
  will-change: left, top, transform;
  transition:
    left 0.34s cubic-bezier(0.22, 1, 0.36, 1),
    top 0.34s cubic-bezier(0.22, 1, 0.36, 1),
    opacity 0.18s ease;
}

.plaza-fab-shell.is-dragging {
  transition: none;
}

/* ---- FAB 主按钮 ---- */
.plaza-fab-main {
  position: relative;
  display: block;
  z-index: 1;
  width: 140px;
  height: 52px;
  border-radius: 16px;
  border: none;
  cursor: grab;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #6366f1, #8b5cf6);
  color: white;
  box-shadow:
    0 4px 14px rgba(99, 102, 241, 0.35),
    0 2px 6px rgba(0, 0, 0, 0.1);
  transition:
    transform 0.18s ease,
    box-shadow 0.18s ease,
    opacity 0.18s ease,
    border-color 0.18s ease,
    width 0.22s ease,
    height 0.22s ease,
    border-radius 0.22s ease,
    padding 0.22s ease;
  outline: none;
  overflow: visible;
}

.plaza-fab-main.mode-minimized {
  width: 52px;
  height: 52px;
  border-radius: 50%;
}

.plaza-fab-main:hover {
  transform: translateY(-2px) scale(1.05);
  box-shadow:
    0 8px 24px rgba(99, 102, 241, 0.45),
    0 4px 10px rgba(0, 0, 0, 0.15);
}

.plaza-fab-main:active {
  transform: scale(0.96);
}

.plaza-fab-shell.is-dragging .plaza-fab-main {
  cursor: grabbing;
  transform: scale(1.02);
}

.plaza-fab-main.is-open {
  background: linear-gradient(135deg, #4f46e5, #7c3aed);
  box-shadow:
    0 2px 8px rgba(79, 70, 229, 0.3),
    inset 0 1px 0 rgba(255, 255, 255, 0.15);
}

.fab-glow {
  position: absolute;
  inset: -2px;
  border-radius: 18px;
  background: conic-gradient(
    from 180deg,
    transparent,
    rgba(167, 139, 250, 0.4),
    transparent,
    rgba(99, 102, 241, 0.4),
    transparent
  );
  opacity: 0;
  transition: opacity 0.3s;
  z-index: -1;
  animation: glow-spin 4s linear infinite paused;
}

.plaza-fab-main:hover .fab-glow,
.plaza-fab-main.is-open .fab-glow {
  opacity: 1;
  animation-play-state: running;
}

@keyframes glow-spin {
  to { transform: rotate(360deg); }
}

.fab-content {
  display: flex;
  align-items: center;
  gap: 6px;
  position: relative;
  z-index: 1;
}

.fab-icon {
  font-size: 22px;
  line-height: 1;
  transition: transform 0.3s;
}

.plaza-fab-main:hover .fab-icon,
.plaza-fab-main.is-open .fab-icon {
  transform: scale(1.15) rotate(-5deg);
}

.fab-label {
  font-size: 13px;
  font-weight: 600;
  white-space: nowrap;
  letter-spacing: 0.3px;
  animation: fade-in 0.25s ease-out;
}

@keyframes fade-in {
  from { opacity: 0; transform: translateX(8px); }
  to { opacity: 1; transform: translateX(0); }
}

/* 角标 */
.fab-badge {
  position: absolute;
  top: -4px;
  right: -4px;
  min-width: 20px;
  height: 20px;
  padding: 0 5px;
  border-radius: 10px;
  background: #ef4444;
  color: white;
  font-size: 11px;
  font-weight: 700;
  line-height: 20px;
  text-align: center;
  border: 2px solid white;
  box-shadow: 0 2px 4px rgba(239, 68, 68, 0.35);
  pointer-events: none;
}

/* 操作按钮 */
.plaza-fab-actions {
  position: absolute;
  z-index: 2;
  bottom: calc(100% + 10px);
  left: 50%;
  transform: translateX(-50%);
  display: flex;
  flex-direction: row;
  gap: 8px;
  align-items: center;
  padding: 8px;
  border: 1px solid rgba(148, 163, 184, 0.16);
  border-radius: 16px;
  background: rgba(15, 23, 42, 0.56);
  box-shadow: 0 16px 32px rgba(15, 23, 42, 0.18);
  backdrop-filter: blur(14px);
  transform: translate(-50%, 6px) scale(0.96);
  opacity: 0;
  pointer-events: none;
  transition: opacity 0.16s ease, transform 0.16s ease;
}

.plaza-fab-shell.is-hovered .plaza-fab-actions,
.plaza-fab-shell.is-dragging .plaza-fab-actions {
  opacity: 1;
  pointer-events: auto;
  transform: translate(-50%, 0) scale(1);
}

.plaza-fab-action {
  width: 36px;
  height: 36px;
  border: 0;
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.08);
  color: #e2e8f0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: transform 0.16s ease, background 0.16s ease, color 0.16s ease;
}

.plaza-fab-action:hover {
  transform: translateY(-1px);
  background: rgba(255, 255, 255, 0.16);
  color: white;
}

/* ---- 抽屉头部 ---- */
.drawer-header {
  width: 100%;
}

.drawer-title-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.drawer-icon {
  font-size: 22px;
}

.drawer-title {
  font-size: 17px;
  font-weight: 700;
  color: var(--n-text-color-1, #333);
}

.drawer-subtitle {
  margin: 4px 0 0;
  font-size: 12.5px;
  color: var(--n-text-color-3, #999);
  letter-spacing: 0.2px;
}
</style>
