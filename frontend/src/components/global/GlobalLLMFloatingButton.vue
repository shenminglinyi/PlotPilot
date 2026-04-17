<template>
  <teleport to="body">
    <div
      class="global-llm-shell"
      :class="[
        `dock-${dockSide}`,
        `mode-${mode}`,
        { 'is-dragging': dragging, 'is-hovered': hovering },
      ]"
      :style="shellStyle"
    >
      <div
        class="global-llm-actions"
        :class="`dock-${dockSide}`"
        :style="actionsStyle"
        @mouseenter="setHovering(true)"
        @mouseleave="scheduleHideHover"
      >
        <button
          type="button"
          class="global-llm-action"
          :title="mode === 'expanded' ? '最小化' : '展开'"
          @pointerdown.stop
          @click.stop="toggleMinimize"
        >
          <n-icon v-if="mode === 'expanded'"><RemoveOutline /></n-icon>
          <n-icon v-else><ExpandOutline /></n-icon>
        </button>
      </div>

      <button
        ref="buttonRef"
        type="button"
        class="global-llm-main"
        :class="[`dock-${dockSide}`, `mode-${mode}`]"
        aria-label="打开全局 LLM 配置面板"
        @mouseenter="setHovering(true)"
        @mouseleave="scheduleHideHover"
        @pointerdown="onPointerDown"
        @keydown.enter.prevent="openPanel"
        @keydown.space.prevent="openPanel"
      >
        <span class="global-llm-glow"></span>

        <span class="global-llm-main-content">
          <span class="global-llm-icon-core">
            <span class="global-llm-icon-grid"></span>
            <n-icon class="global-llm-icon-chip"><HardwareChipOutline /></n-icon>
            <n-icon class="global-llm-icon-spark"><SparklesOutline /></n-icon>
          </span>

          <span v-if="mode === 'expanded'" class="global-llm-copy">
            <span class="global-llm-title-row">
              <span class="global-llm-title">AI 控制台</span>
              <span class="global-llm-status"></span>
            </span>
            <span class="global-llm-subtitle">LLM Gateway · OpenAI / Claude / Gemini</span>
          </span>
        </span>
      </button>
    </div>

    <n-drawer
      :show="showPanel"
      placement="right"
      :width="drawerWidth"
      :close-on-esc="true"
      :mask-closable="true"
      @update:show="handleDrawerShowChange"
    >
      <n-drawer-content
        closable
        :header-style="drawerHeaderStyle"
        :native-scrollbar="false"
        :body-content-style="drawerBodyStyle"
      >
        <template #header>
          <div class="global-llm-drawer-header">
            <div class="global-llm-drawer-title-wrap">
              <div class="global-llm-drawer-title">全局 LLM 设置</div>
              <div class="global-llm-drawer-subtitle">统一控制当前项目的模型网关、协议与激活配置</div>
            </div>

            <div class="global-llm-runtime-bar" :class="{ 'is-mock': runtimeSummary?.using_mock }">
              <div class="global-llm-runtime-main">
                <span class="global-llm-runtime-label">当前激活模型</span>
                <span class="global-llm-runtime-model">
                  {{ runtimeSummary?.model || (runtimeLoading ? '读取中…' : '未配置') }}
                </span>
              </div>
              <div class="global-llm-runtime-meta">
                <span class="global-llm-runtime-chip">
                  {{ runtimeSummary?.protocol || (runtimeLoading ? 'loading' : 'mock') }}
                </span>
                <span class="global-llm-runtime-name">
                  {{ runtimeSummary?.active_profile_name || runtimeSummary?.reason || '未激活任何配置' }}
                </span>
              </div>
            </div>
          </div>
        </template>
        <div class="global-llm-drawer-body">
          <LLMControlPanel
            scroll-state-key="global-drawer"
            @panel-updated="handlePanelUpdated"
          />
        </div>
      </n-drawer-content>
    </n-drawer>
  </teleport>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { NDrawer, NDrawerContent, NIcon } from 'naive-ui'
import {
  ExpandOutline,
  HardwareChipOutline,
  RemoveOutline,
  SparklesOutline,
} from '@vicons/ionicons5'
import {
  llmControlApi,
  type LLMControlPanelData,
  type LLMRuntimeSummary,
} from '../../api/llmControl'
import LLMControlPanel from '../workbench/LLMControlPanel.vue'

type DockSide = 'left' | 'right'
type FabMode = 'expanded' | 'minimized'

interface PersistedFabState {
  version: 4
  dock: DockSide
  yRatio: number
  mode: FabMode
}

const STORAGE_KEY = 'plotpilot.global-llm-fab.state.v4'
const EDGE_GAP = 10
const TOP_SAFE_GAP = 88
const BOTTOM_SAFE_GAP = 24
const CLICK_THRESHOLD = 6

const showPanel = ref(false)
const dragging = ref(false)
const hovering = ref(false)
const runtimeLoading = ref(false)
const buttonRef = ref<HTMLElement | null>(null)
const viewportWidth = ref(getViewportWidth())
const viewportHeight = ref(getViewportHeight())
const position = ref({ x: 0, y: 0 })
const dockSide = ref<DockSide>('right')
const mode = ref<FabMode>('expanded')
const yRatio = ref(0.84)
const runtimeSummary = ref<LLMRuntimeSummary | null>(null)

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

const drawerWidth = computed(() => {
  const width = viewportWidth.value
  if (width <= 640) return width
  if (width <= 900) return Math.max(360, Math.round(width * 0.96))
  if (width <= 1280) return Math.min(960, Math.round(width * 0.84))
  return 1040
})

const shellStyle = computed(() => ({
  left: `${position.value.x}px`,
  top: `${position.value.y}px`,
}))

const drawerBodyStyle = computed(() => ({
  padding: '0',
  height: viewportWidth.value <= 768 ? 'calc(100vh - 56px)' : 'calc(100vh - 68px)',
}))

const drawerHeaderStyle = computed(() => ({
  padding: viewportWidth.value <= 768 ? '16px 16px 12px' : '18px 20px 14px',
}))

const actionsStyle = computed(() =>
  dockSide.value === 'left' ? { left: '0' } : { right: '0' }
)

function getFallbackSize() {
  if (mode.value === 'minimized') return { width: 62, height: 62 }
  return { width: 248, height: 70 }
}

function getButtonSize() {
  const rect = buttonRef.value?.getBoundingClientRect()
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
    version: 4,
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

function openPanel() {
  void refreshRuntimeSummary()
  showPanel.value = true
}

async function refreshRuntimeSummary() {
  runtimeLoading.value = true
  try {
    const data = await llmControlApi.getPanel()
    runtimeSummary.value = data.runtime
  } catch {
    runtimeSummary.value = null
  } finally {
    runtimeLoading.value = false
  }
}

function handlePanelUpdated(data: LLMControlPanelData) {
  runtimeSummary.value = data.runtime
}

function handleDrawerShowChange(value: boolean) {
  showPanel.value = value
  if (value) {
    void refreshRuntimeSummary()
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
  openPanel()
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
  void refreshRuntimeSummary()
})

onBeforeUnmount(() => {
  clearHoverHideTimer()
  stopDragging()
  window.removeEventListener('resize', syncViewport)
})
</script>

<style scoped>
.global-llm-shell {
  position: fixed;
  z-index: 1200;
  user-select: none;
  touch-action: none;
  will-change: left, top, transform;
  transition:
    left 0.34s cubic-bezier(0.22, 1, 0.36, 1),
    top 0.34s cubic-bezier(0.22, 1, 0.36, 1),
    opacity 0.18s ease;
}

.global-llm-shell.is-dragging {
  transition: none;
}

.global-llm-main {
  position: relative;
  display: block;
  z-index: 1;
  overflow: hidden;
  border: 1px solid rgba(148, 163, 184, 0.22);
  background:
    radial-gradient(circle at 18% 18%, rgba(129, 140, 248, 0.32), transparent 28%),
    linear-gradient(135deg, rgba(15, 23, 42, 0.98), rgba(49, 46, 129, 0.95) 55%, rgba(37, 99, 235, 0.9));
  color: var(--app-text-inverse, #fff);
  box-shadow:
    0 12px 30px rgba(30, 41, 59, 0.2),
    0 10px 26px rgba(79, 70, 229, 0.22);
  backdrop-filter: blur(12px);
  cursor: grab;
  transition:
    transform 0.18s ease,
    box-shadow 0.18s ease,
    opacity 0.18s ease,
    border-color 0.18s ease,
    width 0.22s ease,
    min-height 0.22s ease,
    height 0.22s ease,
    border-radius 0.22s ease,
    padding 0.22s ease;
}

.global-llm-main:hover {
  transform: translateY(-1px);
  border-color: rgba(191, 219, 254, 0.45);
  box-shadow:
    0 14px 34px rgba(30, 41, 59, 0.24),
    0 14px 32px rgba(79, 70, 229, 0.28);
}

.global-llm-shell.is-dragging .global-llm-main {
  cursor: grabbing;
  transform: scale(1.02);
}

.global-llm-main.mode-expanded {
  width: 248px;
  min-height: 68px;
  padding: 12px 14px;
  border-radius: 20px;
}

.global-llm-main.mode-minimized {
  width: 62px;
  height: 62px;
  padding: 0;
  border-radius: 50%;
}

.global-llm-glow {
  position: absolute;
  inset: 0;
  background:
    radial-gradient(circle at 80% 20%, rgba(255, 255, 255, 0.18), transparent 24%),
    linear-gradient(180deg, rgba(255, 255, 255, 0.06), transparent 45%);
  pointer-events: none;
}

.global-llm-main-content {
  position: relative;
  z-index: 1;
  display: flex;
  align-items: center;
  gap: 12px;
}

.global-llm-icon-core {
  position: relative;
  flex: 0 0 auto;
  width: 40px;
  height: 40px;
  border-radius: 14px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(180deg, rgba(15, 23, 42, 0.5), rgba(15, 23, 42, 0.16));
  border: 1px solid rgba(255, 255, 255, 0.12);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.08);
}

.mode-minimized .global-llm-icon-core {
  width: 62px;
  height: 62px;
  border-radius: 50%;
  background:
    radial-gradient(circle at 30% 30%, rgba(96, 165, 250, 0.3), transparent 34%),
    linear-gradient(180deg, rgba(15, 23, 42, 0.5), rgba(15, 23, 42, 0.18));
}

.global-llm-icon-grid {
  position: absolute;
  inset: 8px;
  border-radius: inherit;
  opacity: 0.35;
  background-image:
    linear-gradient(rgba(191, 219, 254, 0.12) 1px, transparent 1px),
    linear-gradient(90deg, rgba(191, 219, 254, 0.12) 1px, transparent 1px);
  background-size: 7px 7px;
}

.global-llm-icon-chip,
.global-llm-icon-spark {
  position: relative;
  z-index: 1;
}

.global-llm-icon-chip {
  font-size: 20px;
}

.mode-minimized .global-llm-icon-chip {
  font-size: 24px;
}

.global-llm-icon-spark {
  position: absolute;
  top: 4px;
  right: 4px;
  font-size: 13px;
  color: #fef08a;
  filter: drop-shadow(0 0 6px rgba(253, 224, 71, 0.4));
}

.mode-minimized .global-llm-icon-spark {
  top: 10px;
  right: 10px;
}

.global-llm-copy {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 5px;
}

.global-llm-title-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.global-llm-title {
  font-size: 14px;
  font-weight: 700;
  letter-spacing: 0.02em;
}

.global-llm-status {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: linear-gradient(180deg, #86efac, #22c55e);
  box-shadow: 0 0 0 4px rgba(34, 197, 94, 0.14);
}

.global-llm-subtitle {
  max-width: 170px;
  color: rgba(226, 232, 240, 0.82);
  font-size: 11px;
  line-height: 1.35;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.global-llm-actions {
  position: absolute;
  z-index: 2;
  bottom: calc(100% + 10px);
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
  transform: translateY(6px) scale(0.96);
  opacity: 0;
  pointer-events: none;
  transition: opacity 0.16s ease, transform 0.16s ease;
}

.global-llm-shell.is-hovered .global-llm-actions,
.global-llm-shell.is-dragging .global-llm-actions {
  opacity: 1;
  pointer-events: auto;
  transform: translateY(0) scale(1);
}

.global-llm-action {
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

.global-llm-action:hover {
  transform: translateY(-1px);
  background: rgba(255, 255, 255, 0.16);
  color: var(--app-text-inverse, #fff);
}

.global-llm-drawer-header {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.global-llm-drawer-title-wrap {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.global-llm-drawer-title {
  font-size: 18px;
  font-weight: 700;
  color: #0f172a;
}

.global-llm-drawer-subtitle {
  font-size: 12px;
  color: #64748b;
}

.global-llm-runtime-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 14px;
  border-radius: 14px;
  background:
    linear-gradient(135deg, rgba(79, 70, 229, 0.08), rgba(59, 130, 246, 0.08)),
    var(--app-surface-subtle);
  border: 1px solid rgba(99, 102, 241, 0.1);
}

.global-llm-runtime-bar.is-mock {
  background:
    linear-gradient(135deg, rgba(245, 158, 11, 0.12), rgba(249, 115, 22, 0.1)),
    var(--color-gold-dim);
  border-color: rgba(245, 158, 11, 0.18);
}

.global-llm-runtime-main {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.global-llm-runtime-label {
  font-size: 11px;
  line-height: 1;
  color: #64748b;
}

.global-llm-runtime-model {
  font-size: 15px;
  font-weight: 700;
  line-height: 1.25;
  color: #0f172a;
}

.global-llm-runtime-meta {
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 8px;
}

.global-llm-runtime-chip {
  flex-shrink: 0;
  padding: 4px 9px;
  border-radius: 999px;
  background: rgba(79, 70, 229, 0.1);
  color: #4338ca;
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
}

.global-llm-runtime-name {
  max-width: 320px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: #475569;
  font-size: 12px;
}

.global-llm-drawer-body {
  height: 100%;
  min-height: 0;
  overflow: hidden;
}

@media (max-width: 768px) {
  .global-llm-runtime-bar {
    flex-direction: column;
    align-items: flex-start;
  }

  .global-llm-runtime-meta {
    width: 100%;
    flex-wrap: wrap;
  }

  .global-llm-runtime-name {
    max-width: 100%;
    white-space: normal;
  }
}
</style>
