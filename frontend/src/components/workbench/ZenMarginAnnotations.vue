<template>
  <aside class="margin-rail" aria-label="本章卷边留批" :class="{ 'is-typing': typing }">
    <header class="margin-head" :class="{ 'has-attention': totalAttentionCount > 0 }"><strong>{{ totalAttentionCount ? `卷边留批 · ${totalAttentionCount} 处` : '卷边静默 · 0 处留批' }}</strong><p>套话 {{ antiAiHitTotal }} · 护栏 {{ guardrailViolations.length }} · 伏笔 {{ foreshadows.length }}</p></header>
          <p class="scan-label">{{ usingBaseline ? '基础净词巡检' : '模组净词巡检' }}<span v-if="typing" class="typing-note"> · 输入待定</span></p>
          <ul class="margin-list"><li v-for="hit in hits" :key="hit.word" class="attention-item">套话「{{ hit.word }}」· {{ hit.count }} 处</li><li v-for="(violation, i) in guardrailViolations" :key="`guard-${i}`" class="attention-item"><strong>护栏提醒 · {{ violation.dimension || violation.type || '叙事一致性' }}</strong><p>{{ violation.description }}</p><p v-if="violation.suggestion" class="reference-text">{{ violation.suggestion }}</p></li><li v-for="(thread, i) in foreshadows" :key="`thread-${i}`" class="reference-item"><strong>待回收伏笔</strong><p>伏笔待收 · {{ thread }}</p></li></ul>
          <details v-if="redlines.length" class="redline-reference"><summary>审稿红线 ({{ redlines.length }})</summary><ul class="margin-list"><li v-for="rule in redlines" :key="rule" class="reference-item">{{ rule }}</li></ul></details>
          <p class="margin-hint">按 Alt + Z 退出专注视图</p>
  </aside>
  <button ref="pillRef" type="button" class="margin-pill" :class="{ 'has-attention': totalAttentionCount > 0, 'keyboard-open': keyboardOpen }" :style="keyboardOpen ? { top: `${keyboardTop}px` } : undefined" :aria-expanded="drawerOpen" aria-controls="zen-margin-drawer" @click="openDrawer">留批 {{ totalAttentionCount }}</button>
  <teleport to="body">
    <div v-if="drawerOpen" class="margin-drawer-mask" @click.self="closeDrawer">
      <section id="zen-margin-drawer" ref="drawerRef" class="margin-drawer" role="dialog" aria-modal="true" aria-label="本章卷边留批" tabindex="-1">
        <div class="drawer-head"><h3>本章卷边留批</h3><button ref="drawerCloseRef" type="button" @click="closeDrawer">收起</button></div>
        <div class="drawer-content" :class="{ 'is-typing': typing }" tabindex="0" role="region" aria-label="本章卷边留批内容"><header class="margin-head" :class="{ 'has-attention': totalAttentionCount > 0 }"><strong>{{ totalAttentionCount ? `卷边留批 · ${totalAttentionCount} 处` : '卷边静默 · 0 处留批' }}</strong><p>套话 {{ antiAiHitTotal }} · 护栏 {{ guardrailViolations.length }} · 伏笔 {{ foreshadows.length }}</p></header>
          <p class="scan-label">{{ usingBaseline ? '基础净词巡检' : '模组净词巡检' }}<span v-if="typing" class="typing-note"> · 输入待定</span></p>
          <ul class="margin-list"><li v-for="hit in hits" :key="hit.word" class="attention-item">套话「{{ hit.word }}」· {{ hit.count }} 处</li><li v-for="(violation, i) in guardrailViolations" :key="`guard-${i}`" class="attention-item"><strong>护栏提醒 · {{ violation.dimension || violation.type || '叙事一致性' }}</strong><p>{{ violation.description }}</p><p v-if="violation.suggestion" class="reference-text">{{ violation.suggestion }}</p></li><li v-for="(thread, i) in foreshadows" :key="`thread-${i}`" class="reference-item"><strong>待回收伏笔</strong><p>伏笔待收 · {{ thread }}</p></li></ul>
          <details v-if="redlines.length" class="redline-reference"><summary>审稿红线 ({{ redlines.length }})</summary><ul class="margin-list"><li v-for="rule in redlines" :key="rule" class="reference-item">{{ rule }}</li></ul></details>
          <p class="margin-hint">按 Alt + Z 退出专注视图</p></div>
      </section>
    </div>
  </teleport>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { checkpointApi, type GuardrailViolationDTO } from '@/api/engineCore'
import { CURATED_MOD_PACKS } from '@/domain/modPack/curatedPacks'
import { useModHubStore } from '@/stores/modHubStore'

const props = withDefaults(
  defineProps<{
    slug: string
    liveContent: string
    guardrailViolations: GuardrailViolationDTO[]
    refreshTick?: number
  }>(),
  { refreshTick: 0 },
)
const modHub = useModHubStore()
const baseline = ['嘴角勾起一抹', '眼神中闪过一丝', '不禁让人', '仿佛在诉说着', '空气瞬间凝固', '倒吸一口凉气']
const installedPacks = computed(() => modHub.installedList.map(({ pack }) => {
  const curated = CURATED_MOD_PACKS.find(item => item.id === pack.id)
  return { antiAiWordlist: pack.antiAiWordlist ?? curated?.antiAiWordlist ?? [], reviewRedlines: pack.reviewRedlines ?? curated?.reviewRedlines ?? [] }
}))
const installedWords = computed(() => [...new Set(installedPacks.value.flatMap(pack => pack.antiAiWordlist).map(word => word.trim()).filter(Boolean))])
const usingBaseline = computed(() => !installedWords.value.length)
const words = computed(() => usingBaseline.value ? baseline : installedWords.value)
const redlines = computed(() => [...new Set(installedPacks.value.flatMap(pack => pack.reviewRedlines).map(rule => rule.trim()).filter(Boolean))])
const hits = ref<Array<{ word: string; count: number }>>([])
const antiAiHitTotal = computed(() => hits.value.reduce((sum, hit) => sum + hit.count, 0))
const foreshadows = ref<string[]>([])
const totalAttentionCount = computed(() => antiAiHitTotal.value + props.guardrailViolations.length + foreshadows.value.length)
const typing = ref(false)
let scanTimer: ReturnType<typeof setTimeout> | undefined
let settleTimer: ReturnType<typeof setTimeout> | undefined
let headEpoch = 0
function scan() {
  const text = props.liveContent
  const found: Array<{ word: string; count: number }> = []
  for (const word of words.value) {
    if (!word.length) continue
    let count = 0
    let idx = text.indexOf(word)
    while (idx !== -1) { count += 1; idx = text.indexOf(word, idx + word.length) }
    if (count) found.push({ word, count })
  }
  hits.value = found
}
watch([() => props.liveContent, words], ([text], previous) => {
  clearTimeout(scanTimer)
  if (previous && text !== previous[0]) {
    typing.value = true
    clearTimeout(settleTimer)
    settleTimer = setTimeout(() => { typing.value = false }, 1000)
  }
  scanTimer = setTimeout(scan, 350)
}, { immediate: true })
watch(
  [() => props.slug, () => props.refreshTick],
  async ([slug], prev) => {
    const epoch = ++headEpoch
    const prevSlug = prev?.[0]
    if (!slug) {
      foreshadows.value = []
      return
    }
    if (slug !== prevSlug) {
      foreshadows.value = []
    }
    try {
      const result = await checkpointApi.getHead(slug)
      if (epoch !== headEpoch) return
      foreshadows.value = (result.state?.active_foreshadows ?? [])
        .filter((item): item is string => typeof item === 'string' && Boolean(item.trim()))
        .slice(0, 4)
    } catch {
      if (epoch === headEpoch && slug !== prevSlug) {
        foreshadows.value = []
      }
    }
  },
  { immediate: true },
)
const drawerOpen = ref(false)
const drawerRef = ref<HTMLElement | null>(null)
const drawerCloseRef = ref<HTMLButtonElement | null>(null)
const pillRef = ref<HTMLButtonElement | null>(null)
const keyboardOpen = ref(false)
const keyboardTop = ref(60)
let viewport: VisualViewport | null = null
let pillResizeObserver: ResizeObserver | null = null
let baselineWidth = 0
let baselineHeight = 0
let lastScreenAngle: number | null = null
let opener: HTMLElement | null = null
let inertNodes: Array<{ el: HTMLElement; inert: boolean }> = []
function getScreenAngle(): number | null {
  if (typeof window === 'undefined') return null
  const angle = window.screen?.orientation?.angle
  return typeof angle === 'number' ? angle : null
}
function isEditableElementActive(): boolean {
  if (typeof document === 'undefined') return false
  const active = document.activeElement
  if (active instanceof HTMLTextAreaElement) return !active.disabled
  if (active instanceof HTMLInputElement) {
    const nonTextTypes = new Set(['button', 'checkbox', 'radio', 'submit', 'reset', 'file', 'range', 'color'])
    return !active.disabled && !nonTextTypes.has(active.type)
  }
  return active instanceof HTMLElement && active.isContentEditable
}
function resetViewportBaseline(): void {
  if (typeof window === 'undefined') return
  baselineWidth = window.innerWidth
  baselineHeight = window.innerHeight
  lastScreenAngle = getScreenAngle()
}
function syncViewport() {
  if (typeof window === 'undefined') return
  if (window.innerWidth >= 1180 && drawerOpen.value) closeDrawer()
  const currentAngle = getScreenAngle()
  const angleChanged =
    currentAngle !== null && lastScreenAngle !== null && currentAngle !== lastScreenAngle
  const widthChanged = baselineWidth === 0 || Math.abs(window.innerWidth - baselineWidth) > 16
  const editing = isEditableElementActive()
  if (angleChanged || widthChanged || !editing) {
    resetViewportBaseline()
  } else if (window.innerHeight > baselineHeight) {
    baselineHeight = window.innerHeight
  }
  const vpHeight = Math.max(0, viewport?.height ?? window.innerHeight)
  const visualDelta = window.innerHeight - vpHeight
  const layoutDelta = editing ? baselineHeight - vpHeight : 0
  const wasKeyboardOpen = keyboardOpen.value
  keyboardOpen.value = Math.max(visualDelta, layoutDelta) > 140
  const offsetTop = Math.max(0, viewport?.offsetTop ?? 0)
  const renderedPillHeight = pillRef.value
    ? Math.ceil(pillRef.value.getBoundingClientRect().height || pillRef.value.offsetHeight)
    : 0
  const pillHeight = Math.max(renderedPillHeight, 44)
  const topClearance = 12
  const bottomClearance = 12
  const preferredTop = offsetTop + 60
  const minSafeTop = offsetTop + topClearance
  const maxSafeTop = offsetTop + vpHeight - pillHeight - bottomClearance
  if (maxSafeTop >= minSafeTop) {
    keyboardTop.value = Math.min(Math.max(preferredTop, minSafeTop), maxSafeTop)
  } else {
    keyboardTop.value = offsetTop + Math.max(0, Math.floor((vpHeight - pillHeight) / 2))
  }
  if (!wasKeyboardOpen && keyboardOpen.value) {
    void nextTick(syncViewport)
  }
}
watch(totalAttentionCount, () => {
  if (keyboardOpen.value) {
    void nextTick(syncViewport)
  }
})
async function openDrawer() {
  if (drawerOpen.value) return
  opener = document.activeElement instanceof HTMLElement ? document.activeElement : pillRef.value
  drawerOpen.value = true
  document.addEventListener('keydown', drawerKeys, true)
  await nextTick()
  if (!drawerOpen.value) return
  const mask = drawerRef.value?.parentElement
  for (const child of Array.from(document.body.children)) {
    if (child instanceof HTMLElement && child !== mask && !child.contains(mask ?? null)) { inertNodes.push({ el: child, inert: child.inert }); child.inert = true }
  }
  drawerCloseRef.value?.focus()
}
function closeDrawer() {
  drawerOpen.value = false
  document.removeEventListener('keydown', drawerKeys, true)
  for (const node of inertNodes) node.el.inert = node.inert
  inertNodes = []
  if (opener?.isConnected) opener.focus()
  opener = null
}
function drawerKeys(event: KeyboardEvent) {
  if (event.key === 'Escape') { event.preventDefault(); event.stopPropagation(); closeDrawer(); return }
  if (event.key !== 'Tab') return
  const items = Array.from(drawerRef.value?.querySelectorAll<HTMLElement>('button:not(:disabled), summary, [tabindex="0"]') ?? []).filter(el => el.getClientRects().length > 0 && window.getComputedStyle(el).visibility !== 'hidden')
  const first = items[0], last = items[items.length - 1]
  if (!first || !last) { event.preventDefault(); drawerRef.value?.focus(); return }
  const active = document.activeElement
  const outside = active === drawerRef.value || !drawerRef.value?.contains(active)
  if (event.shiftKey && (active === first || outside)) { event.preventDefault(); last.focus() }
  else if (!event.shiftKey && (active === last || outside)) { event.preventDefault(); first.focus() }
}
onMounted(() => {
  viewport = window.visualViewport
  resetViewportBaseline()
  syncViewport()
  if (typeof ResizeObserver !== 'undefined' && pillRef.value) {
    pillResizeObserver = new ResizeObserver(() => syncViewport())
    pillResizeObserver.observe(pillRef.value)
  }
  viewport?.addEventListener('resize', syncViewport)
  viewport?.addEventListener('scroll', syncViewport)
  window.addEventListener('resize', syncViewport)
  window.addEventListener('orientationchange', syncViewport)
  document.addEventListener('focusin', syncViewport)
  document.addEventListener('focusout', syncViewport)
})
onBeforeUnmount(() => {
  headEpoch += 1
  clearTimeout(scanTimer)
  clearTimeout(settleTimer)
  pillResizeObserver?.disconnect()
  pillResizeObserver = null
  viewport?.removeEventListener('resize', syncViewport)
  viewport?.removeEventListener('scroll', syncViewport)
  window.removeEventListener('resize', syncViewport)
  window.removeEventListener('orientationchange', syncViewport)
  document.removeEventListener('focusin', syncViewport)
  document.removeEventListener('focusout', syncViewport)
  closeDrawer()
})
</script>

<style scoped>
.margin-rail, .margin-pill, .margin-drawer { font-family: 'Noto Sans SC', 'PingFang SC', -apple-system, BlinkMacSystemFont, sans-serif; font-size: 14px; font-variant-numeric: tabular-nums; color: var(--app-text-secondary, #4a4a46); }
.margin-rail { position: fixed; top: 72px; left: calc(50% + 410px + clamp(20px, 2.5vw, 36px)); width: clamp(144px, calc((100vw - 820px) / 2 - 40px), 236px); max-height: calc(100dvh - 120px); overflow-y: auto; background: transparent; z-index: 20; padding-right: 8px; box-sizing: border-box; }
.margin-head { border-left: 1.5px solid var(--app-border-strong, rgba(22,22,21,0.28)); padding-left: 12px; color: var(--app-text-muted, #595953); }
.margin-head.has-attention { border-left: 2px solid var(--color-brand, #1f5e5b); color: var(--app-text-primary, #161615); }
.margin-head strong { font-size: 14px; font-weight: 500; }
.margin-head p, .margin-list p { margin: 6px 0 0; font-size: 14px; line-height: 1.7; }
.scan-label, .margin-hint { font-size: 14px; line-height: 1.7; color: var(--app-text-muted, #595953); margin: 16px 0; }
.typing-note { color: var(--app-text-secondary, #4a4a46); }
.margin-list { padding: 0; margin: 12px 0; list-style: none; display: flex; flex-direction: column; gap: 16px; }
.margin-list li { font-size: 14px; line-height: 1.7; padding-left: 12px; overflow-wrap: anywhere; }
.margin-list strong { font-weight: 500; color: var(--app-text-primary, #161615); }
.attention-item { border-left: 2px solid var(--color-brand, #1f5e5b); color: var(--app-text-primary, #161615); }
.reference-item { border-left: 1.5px solid var(--app-border, rgba(22,22,21,0.14)); }
.reference-text { color: var(--app-text-muted, #595953); }
.redline-reference { font-size: 14px; }
.redline-reference summary { cursor: pointer; min-height: 44px; display: flex; align-items: center; }
.is-typing .margin-head { border-left-style: dashed; }
.margin-pill { display: none; position: fixed; right: 16px; bottom: calc(16px + env(safe-area-inset-bottom)); min-height: 44px; min-width: 76px; padding: 10px 14px; box-sizing: border-box; border: none; border-radius: 3px; background: var(--app-surface-subtle, #ecece8); color: var(--app-text-secondary, #4a4a46); z-index: 80; cursor: pointer; }
.margin-pill.has-attention::before { content: ''; display: inline-block; width: 2px; height: 12px; margin-right: 8px; background: var(--color-brand, #1f5e5b); }
.margin-pill.keyboard-open { bottom: auto; }
.margin-drawer-mask { position: fixed; inset: 0; z-index: 3300; background: rgba(22,22,21,0.32); display: flex; align-items: flex-end; }
.margin-drawer { width: 100%; max-height: 48dvh; background: var(--app-page-bg, #f4f4f2); padding: 16px 20px calc(16px + env(safe-area-inset-bottom)); box-sizing: border-box; display: flex; flex-direction: column; }
.drawer-head { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.drawer-head h3 { margin: 0; font-size: 18px; color: var(--app-text-primary, #161615); font-family: 'Noto Serif SC', 'Source Han Serif SC', 'Songti SC', serif; }
.drawer-head button { min-width: 44px; min-height: 44px; padding: 8px 12px; background: var(--app-surface-subtle, #ecece8); color: var(--app-text-secondary, #4a4a46); border: none; border-radius: 3px; font: inherit; cursor: pointer; }
.drawer-content { min-height: 0; overflow-y: auto; padding-top: 16px; }
.drawer-content .margin-list li { padding: 12px; background: var(--app-surface, #ffffff); }
.margin-rail :focus-visible, .margin-pill:focus-visible, .margin-drawer :focus-visible { outline: 1.5px solid var(--color-brand, #1f5e5b); outline-offset: 2px; }
@media (max-width: 1179px) { .margin-rail { display: none; } .margin-pill { display: block; } }
</style>
