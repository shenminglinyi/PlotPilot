<template>
  <!-- 裸舞台：壳（标题/搜索/新建）由 Home 的 books-section 提供，本组件不再自带面板壳 -->
  <div class="project-deck-shell">
    <div
      v-if="books.length"
      ref="deckRef"
      class="project-deck"
      :class="{ 'is-dragging': pointer.active, 'is-settling': settling }"
      role="listbox"
      :aria-activedescendant="selectedBook ? 'deck-book-' + selectedBook.slug : undefined"
      tabindex="0"
      @keydown.left.prevent="selectAt(selectedIndex - 1)"
      @keydown.right.prevent="selectAt(selectedIndex + 1)"
      @keydown.home.prevent="selectAt(0)"
      @keydown.end.prevent="selectAt(books.length - 1)"
      @keydown.enter.prevent="selectedBook && emit('open', selectedBook.slug)"
      @keydown.space.prevent="selectedBook && emit('open', selectedBook.slug)"
      @wheel="handleWheel"
      @pointerdown="handlePointerDown"
      @pointermove="handlePointerMove"
      @pointerup="handlePointerUp"
      @pointercancel="releasePointer"
      @lostpointercapture="releasePointer"
    >
      <div class="project-deck__tree" aria-hidden="true" />
      <div class="project-deck__floor" aria-hidden="true" />
      <article
        v-for="(book, index) in books"
        :id="'deck-book-' + book.slug"
        :key="book.slug"
        class="project-deck-card project-deck-book"
        :data-book-index="index"
        :class="[
          'is-stage-' + (book.stage || 'planning'),
          {
            'is-active': index === selectedIndex,
            'is-hovered': index === hover.index,
            'is-near': Math.abs(index - selectedIndex) <= 5,
          },
        ]"
        :style="{ ...cardStyle(index), '--kind-accent': kindAccent(book.genre) }"
        role="option"
        :aria-selected="index === selectedIndex"
        :aria-label="`${book.title}，${book.stage_label}`"
        @click="handleCardClick(index)"
        @pointerenter="handleCardPointerEnter(index, $event)"
        @pointermove="handleCardPointerMove(index, $event)"
        @pointerleave="handleCardPointerLeave(index)"
      >
        <span class="project-deck-card__back" aria-hidden="true" />
        <span class="project-deck-card__contact-shadow" aria-hidden="true" />
        <span class="project-deck-card__spine" aria-hidden="true">
          <span class="project-deck-card__spine-number numeric">{{ String(index + 1).padStart(2, '0') }}</span>
          <strong>{{ book.title }}</strong>
          <svg class="deck-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true">
            <path d="M12 7v14" />
            <path d="M3 18a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1h5a4 4 0 0 1 4 4 4 4 0 0 1 4-4h5a1 1 0 0 1 1 1v13a1 1 0 0 1-1 1h-6a3 3 0 0 0-3 3 3 3 0 0 0-3-3z" />
          </svg>
        </span>
        <span class="project-deck-card__thickness" aria-hidden="true" />
        <span class="project-deck-card__gloss" aria-hidden="true">
          <span class="project-deck-card__edge" />
          <span class="project-deck-card__specular" />
          <span class="project-deck-card__grain" />
        </span>
        <span class="project-deck-card__number numeric">{{ String(index + 1).padStart(2, '0') }}</span>
        <div class="project-deck-card__toolbar">
          <span class="project-deck-card__state"><i />{{ book.stage_label }}</span>
          <span v-if="book.genre" class="project-deck-card__genre">{{ book.genre }}</span>
          <button
            type="button"
            class="project-deck-card__settings is-delete"
            title="删除书目"
            :aria-label="`删除《${book.title}》`"
            :disabled="busy"
            @pointerdown.stop
            @click.stop="emit('delete', book.slug)"
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" aria-hidden="true">
              <path d="M3 6h18" />
              <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6" />
              <path d="M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
              <path d="M10 11v6" />
              <path d="M14 11v6" />
            </svg>
          </button>
        </div>
        <span class="project-deck-card__icon" aria-hidden="true">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.55" aria-hidden="true">
            <path d="M12 7v14" />
            <path d="M3 18a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1h5a4 4 0 0 1 4 4 4 4 0 0 1 4-4h5a1 1 0 0 1 1 1v13a1 1 0 0 1-1 1h-6a3 3 0 0 0-3 3 3 3 0 0 0-3-3z" />
          </svg>
        </span>
        <div class="project-deck-card__title">
          <small>{{ book.genre || '未分类' }}</small>
          <strong>{{ book.title }}</strong>
          <p>{{ bookSummary(book) }}</p>
        </div>
        <div v-if="book.target_chapters" class="project-deck-card__progress">
          <span><i :style="{ width: bookProgress(book) + '%' }" /></span>
          <em class="numeric">{{ bookProgress(book) }}%</em>
        </div>
        <footer>
          <span class="numeric">{{ book.chapter_count || 0 }}<template v-if="book.target_chapters">/{{ book.target_chapters }}</template> 章</span>
          <strong>{{ formatCount(book.word_count) }} 字</strong>
          <button v-if="index === selectedIndex" type="button" title="进入创作" aria-label="进入创作" @pointerdown.stop @click.stop="emit('open', book.slug)">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
              <path d="M7 7h10v10" />
              <path d="M7 17 17 7" />
            </svg>
          </button>
        </footer>
      </article>
    </div>

    <div v-else-if="loading" class="project-deck project-deck--loading" aria-label="正在同步项目库">
      <span v-for="index in 7" :key="index" />
    </div>
    <button v-else type="button" class="project-deck-empty" @click="emit('new-book')">
      <span>
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true">
          <path d="M5 12h14" />
          <path d="M12 5v14" />
        </svg>
      </span><strong>建立第一本书</strong><em>从作品设定开始</em>
    </button>

    <div v-if="books.length > 1" class="project-deck-dots" aria-label="书籍快速切换">
      <button
        v-for="(book, index) in books"
        :key="'dot-' + book.slug"
        type="button"
        :class="{ 'is-active': index === selectedIndex }"
        :aria-label="`选择《${book.title}》`"
        :aria-current="index === selectedIndex ? 'true' : undefined"
        @click="selectAt(index)"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onUnmounted, reactive, ref, watch } from 'vue'

export interface DeckBookItem {
  slug: string
  title: string
  stage: string
  stage_label: string
  genre: string
  premise: string
  chapter_count?: number
  target_chapters?: number
  word_count?: number
}

const props = defineProps<{ books: DeckBookItem[]; loading?: boolean; busy?: boolean }>()
const emit = defineEmits<{ open: [slug: string]; delete: [slug: string]; 'new-book': [] }>()

const deckRef = ref<HTMLElement | null>(null)
const deckWidth = ref(0)
const dragX = ref(0)
const settling = ref(false)
const suppressClick = ref(false)
// 检视器持久选中不会自动展开书；悬停即选，停止交互 3 秒后收回书脊。
const expandedSlug = ref<string | null>(null)
let collapseTimer: ReturnType<typeof setTimeout> | undefined

function cancelCollapse() {
  clearTimeout(collapseTimer)
  collapseTimer = undefined
}

function scheduleCollapse() {
  cancelCollapse()
  collapseTimer = setTimeout(() => {
    expandedSlug.value = null
    hover.index = -1
    collapseTimer = undefined
  }, 3000)
}
const pointer = reactive({
  active: false,
  id: -1,
  startX: 0,
  lastX: 0,
  lastAt: 0,
  velocity: 0,
  moved: false,
  pressIndex: -1,
})
const hover = reactive({ index: -1, x: 0, y: 0 })
let lastWheelAt = 0
let springFrame = 0
let springVelocity = 0

const selectedIndex = computed(() => {
  return props.books.findIndex(book => book.slug === expandedSlug.value)
})
const selectedBook = computed(() => props.books[selectedIndex.value] || null)

/** 封面类型指纹色：类型字符串哈希 → 稳定色相（与旧网格卡片同一指纹算法），仅用于图标描环 */
function kindAccent(genre: string): string {
  if (!genre) return '#2563eb'
  let hash = 0
  for (let i = 0; i < genre.length; i++) {
    hash = (hash * 31 + genre.charCodeAt(i)) | 0
  }
  const hue = 200 + (Math.abs(hash) % 130)
  return `hsl(${hue}, 52%, 38%)`
}

function bookSummary(book: DeckBookItem): string {
  const premise = book.premise?.trim()
  if (premise) return premise
  if (book.chapter_count) return `第 ${book.chapter_count + 1} 章待推进 · ${book.stage_label}`
  return '从故事锚点开始建立创作方向'
}

function bookProgress(book: DeckBookItem): number {
  const target = book.target_chapters || 0
  if (!target) return 0
  return Math.max(0, Math.min(100, Math.round(((book.chapter_count || 0) / target) * 100)))
}

function formatCount(count?: number): string {
  const value = count || 0
  if (value >= 10000) return (value / 10000).toFixed(1) + '万'
  return String(value)
}

function selectAt(index: number) {
  if (!props.books.length) return
  const normalized = Math.max(0, Math.min(props.books.length - 1, index))
  const book = props.books[normalized]
  if (book) {
    cancelCollapse()
    expandedSlug.value = book.slug
    if (hover.index < 0) scheduleCollapse()
  }
}

/*
 * 静置书脊朝外。只有选中书向前抽出并把封面转向读者；相邻槽位为封面让出空间。
 */
const RACK_ROTATE_Y = 82
const ACTIVE_ROTATE_Y = -8
const RACK_ROTATE_Z = -1.8
const RACK_GAP = 88

/*
 * 槽距随舞台自适应：短书架拉开到能读成多本书，长书架收紧保证都在框内。
 */
const RACK_PITCH_MAX = 100
const rackPitch = computed(() => {
  const span = deckWidth.value
  const count = props.books.length
  if (!span || count <= 1) return 0
  return Math.max(62, Math.min(RACK_PITCH_MAX, (span - RACK_GAP * 2) / count))
})

/*
 * 固定槽位整体平移，保证无论选中谁书架都居中。
 */
const rackCenterOffset = computed(() => {
  const gaps = props.books.length - 1
  if (gaps <= 0) return 0
  return -(gaps / 2) * rackPitch.value
})

function cardStyle(index: number): Record<string, string | number> {
  const offset = index - selectedIndex.value
  const distance = Math.abs(offset)
  const shelfOffset = index - (props.books.length - 1) / 2
  const isActive = offset === 0
  const isHovered = index === hover.index && !pointer.active
  const gap = selectedIndex.value >= 0 ? RACK_GAP : 0
  const rackX = index * rackPitch.value
    + (isActive ? 0 : Math.sign(offset) * gap)
    + rackCenterOffset.value
  const dragInfluence = dragX.value * Math.max(0.52, 1 - distance * 0.06)
  const hoverX = isHovered ? hover.x * 8 : 0
  const hoverY = isHovered ? -18 + hover.y * 2.2 : 0
  const hoverZ = isHovered ? 16 : 0
  const baseRotationY = isActive ? ACTIVE_ROTATE_Y : RACK_ROTATE_Y
  const rotationY = baseRotationY + (isActive && isHovered ? hover.x * 2.8 : 0)
  const rotationX = isHovered ? hover.y * -2.2 : -1.5
  const thickness = 30
  // 共享倾斜让整排书像一副书架在自重下微微沉肩。
  const rotationZ = RACK_ROTATE_Z + (isHovered ? hover.x * 0.12 : 0)
  return {
    '--deck-x': `${rackX + dragInfluence + hoverX}px`,
    '--deck-y': `${(isActive ? -12 : 0) + hoverY}px`,
    '--deck-z': `${(isActive ? 100 : 0) + hoverZ}px`,
    '--deck-rotate-x': `${rotationX}deg`,
    '--deck-rotate-y': `${rotationY}deg`,
    '--deck-rotate-z': `${rotationZ}deg`,
    '--deck-scale': String((isActive ? 1.012 : 1) + (isHovered ? 0.018 : 0)),
    '--deck-shade': String(isActive ? 0 : Math.min(0.12, distance * 0.018)),
    '--deck-thickness': `${thickness}px`,
    '--shine-x': `${hover.x * 26}px`,
    '--shine-y': `${hover.y * 20}px`,
    // 左侧书页压住右侧书页；悬停书压过所有人。
    zIndex: isHovered ? 200 : isActive ? 180 : 120 - index,
  }
}

function handleCardPointerEnter(index: number, event: PointerEvent) {
  if (pointer.active || event.pointerType === 'touch') return
  cancelCollapse()
  hover.index = index
  hover.x = 0
  hover.y = 0
  // 卡片旋转过程中指针可能落到移动中的卡上：move 也负责选中，不只靠 enter。
  if (index !== selectedIndex.value) selectAt(index)
}

function handleCardPointerMove(index: number, event: PointerEvent) {
  if (pointer.active || event.pointerType === 'touch') return
  cancelCollapse()
  const target = event.currentTarget as HTMLElement
  const bounds = target.getBoundingClientRect()
  hover.index = index
  if (index !== selectedIndex.value) selectAt(index)
  hover.x = Math.max(-1, Math.min(1, ((event.clientX - bounds.left) / bounds.width - 0.5) * 2))
  hover.y = Math.max(-1, Math.min(1, ((event.clientY - bounds.top) / bounds.height - 0.5) * 2))
}

function handleCardPointerLeave(index: number) {
  if (hover.index !== index || pointer.active) return
  hover.index = -1
  hover.x = 0
  hover.y = 0
  scheduleCollapse()
}

function handleCardClick(index: number) {
  if (suppressClick.value) return
  activateCard(index)
}

function activateCard(index: number) {
  const book = props.books[index]
  if (!book) return
  emit('open', book.slug)
}

function handlePointerDown(event: PointerEvent) {
  if (event.button !== 0 || (event.target as HTMLElement).closest('button')) return
  cancelCollapse()
  const card = (event.target as HTMLElement).closest<HTMLElement>('.project-deck-card')
  cancelAnimationFrame(springFrame)
  settling.value = false
  pointer.active = true
  pointer.id = event.pointerId
  pointer.startX = event.clientX
  pointer.lastX = event.clientX
  pointer.lastAt = event.timeStamp
  pointer.velocity = 0
  pointer.moved = false
  pointer.pressIndex = Number(card?.dataset.bookIndex ?? -1)
  hover.index = -1
  dragX.value = 0
  deckRef.value?.setPointerCapture(event.pointerId)
}

function handlePointerMove(event: PointerEvent) {
  if (!pointer.active || event.pointerId !== pointer.id) return
  const elapsed = Math.max(8, event.timeStamp - pointer.lastAt)
  const movement = event.clientX - pointer.lastX
  pointer.velocity = pointer.velocity * 0.62 + (movement / elapsed) * 0.38
  pointer.lastX = event.clientX
  pointer.lastAt = event.timeStamp
  dragX.value = Math.max(-220, Math.min(220, event.clientX - pointer.startX))
  pointer.moved ||= Math.abs(dragX.value) > 6
}

function handlePointerUp(event: PointerEvent) {
  if (!pointer.active || event.pointerId !== pointer.id) return
  const shouldOpenPressedBook = !pointer.moved && pointer.pressIndex >= 0
  const pressedIndex = shouldOpenPressedBook ? pointer.pressIndex : -1
  const projected = dragX.value + pointer.velocity * 105
  const steps = Math.max(-3, Math.min(3, Math.round(projected / 72)))
  if (Math.abs(projected) >= 38 && steps) selectAt(selectedIndex.value - steps)
  if (pointer.moved || shouldOpenPressedBook) {
    suppressClick.value = true
    window.setTimeout(() => { suppressClick.value = false }, 0)
  }
  releasePointer()
  springVelocity = pointer.velocity * 7
  startSpring()
  if (pressedIndex >= 0) activateCard(pressedIndex)
}

function releasePointer() {
  pointer.active = false
  pointer.id = -1
  pointer.pressIndex = -1
  if (expandedSlug.value) scheduleCollapse()
}

function startSpring() {
  cancelAnimationFrame(springFrame)
  settling.value = true
  const tick = () => {
    springVelocity += -dragX.value * 0.14
    springVelocity *= 0.72
    dragX.value += springVelocity
    if (Math.abs(dragX.value) < 0.25 && Math.abs(springVelocity) < 0.25) {
      dragX.value = 0
      settling.value = false
      return
    }
    springFrame = requestAnimationFrame(tick)
  }
  springFrame = requestAnimationFrame(tick)
}

function handleWheel(event: WheelEvent) {
  // 竖屏窄页放行纵向滚动，避免劫持整页。
  const verticalPageScroll = window.matchMedia('(max-width: 820px)').matches
    && Math.abs(event.deltaY) >= Math.abs(event.deltaX)
  if (verticalPageScroll) return
  event.preventDefault()
  const now = performance.now()
  if (now - lastWheelAt < 180) return
  const delta = Math.abs(event.deltaX) > Math.abs(event.deltaY) ? event.deltaX : event.deltaY
  if (Math.abs(delta) < 7) return
  lastWheelAt = now
  selectAt(selectedIndex.value + (delta > 0 ? 1 : -1))
}

// deck 元素只在书列表加载后才存在，因此监听 ref 而非在 mount 时测量。
let observer: ResizeObserver | null = null
watch(deckRef, element => {
  observer?.disconnect()
  observer = null
  if (!element) return
  deckWidth.value = element.clientWidth
  observer = new ResizeObserver(entries => {
    for (const entry of entries) deckWidth.value = entry.contentRect.width
  })
  observer.observe(element)
}, { immediate: true })

onUnmounted(() => {
  cancelCollapse()
  cancelAnimationFrame(springFrame)
  observer?.disconnect()
})
</script>

<style scoped>
/* ══ 书架舞台（自 pw fe home-cockpit 移植；台面/面板走主题 token，
      书籍封面是品牌资产固定色，不随主题换肤）══════════════════ */

.project-deck-shell {
  position: relative;
  min-width: 0;
  isolation: isolate;
}

/* 舞台背景：树影纹理极低透明度叠主题表面，浅深主题共用 */
.project-deck-shell::before {
  content: '';
  position: absolute;
  z-index: -1;
  inset: 0;
  background: url('/images/home/sakura-bloom-tree.webp') center 44% / cover no-repeat;
  opacity: 0.06;
}

.project-deck {
  position: relative;
  /* 卡片 absolute 不撑高：舞台必须自带腔体，否则 3D 场景以 0 高容器塌陷 */
  min-height: 400px;
  overflow: hidden;
  outline: none;
  perspective: 1180px;
  perspective-origin: 43% 48%;
  transform-style: preserve-3d;
  touch-action: pan-y;
  isolation: isolate;
}

.project-deck:focus-visible {
  box-shadow: inset 0 0 0 2px color-mix(in srgb, var(--color-brand) 52%, transparent);
}

.project-deck.is-dragging {
  cursor: grabbing;
}

/* 书架台面：抬升面到页底的纵深井 */
.project-deck__tree {
  position: absolute;
  inset: 8px 10px 7px;
  border: 1px solid var(--app-border);
  border-radius: 8px;
  background:
    radial-gradient(ellipse 42% 34% at 50% 52%, color-mix(in srgb, var(--color-brand) 7%, transparent), transparent 74%),
    linear-gradient(180deg, var(--app-surface-subtle), var(--app-page-bg));
  box-shadow: inset 0 1px color-mix(in srgb, var(--app-text-primary) 7%, transparent), inset 0 -48px 80px color-mix(in srgb, var(--app-text-primary) 10%, transparent);
}

/* 台面接地线：中性色，跟随主题 */
.project-deck__floor {
  position: absolute;
  z-index: 2;
  left: 50%;
  bottom: 15%;
  width: min(94%, 1080px);
  height: 1px;
  transform: translateX(-50%) skewX(-15deg);
  background: linear-gradient(90deg, transparent, color-mix(in srgb, var(--app-text-primary) 22%, transparent) 30%, color-mix(in srgb, var(--color-brand) 24%, transparent) 55%, color-mix(in srgb, var(--app-text-primary) 12%, transparent) 82%, transparent);
}

/* ── 书籍封面：品牌资产，颜色固定（宣纸 + 选中亮绿），不随主题换肤 ── */

.project-deck-card {
  position: absolute;
  top: 50%;
  left: 50%;
  width: 190px;
  height: 270px;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  padding: 18px;
  border: 1px solid rgba(248, 255, 251, 0.56);
  border-radius: 8px;
  background:
    linear-gradient(180deg, rgba(10, 13, 13, var(--deck-shade, 0)), rgba(10, 13, 13, var(--deck-shade, 0))),
    linear-gradient(145deg, rgba(255, 255, 255, 0.42), transparent 26%, rgba(255, 255, 255, 0.12) 72%),
    linear-gradient(148deg, rgba(244, 247, 244, 0.62), rgba(207, 216, 209, 0.42) 54%, rgba(223, 231, 225, 0.5));
  box-shadow: inset 0 1px rgba(255, 255, 255, 0.62), inset 1px 0 rgba(255, 255, 255, 0.3), inset -1px 0 rgba(24, 36, 30, 0.16);
  color: #1a221d;
  cursor: grab;
  opacity: 1;
  transform:
    translate(-50%, -50%)
    translate3d(var(--deck-x), var(--deck-y), var(--deck-z))
    rotateX(var(--deck-rotate-x, 0deg))
    rotateY(var(--deck-rotate-y))
    rotateZ(var(--deck-rotate-z))
    scale(var(--deck-scale));
  transform-origin: 50% 88%;
  transform-style: preserve-3d;
  contain: layout;
  will-change: transform;
  transition:
    transform 430ms cubic-bezier(0.16, 0.82, 0.25, 1),
    opacity 220ms ease,
    border-color 220ms ease,
    box-shadow 360ms ease,
    background 360ms ease;
}

.project-deck.is-dragging .project-deck-card,
.project-deck.is-settling .project-deck-card {
  transition: opacity 120ms ease, box-shadow 180ms ease;
}

.project-deck-card:hover:not(.is-active) {
  border-color: rgba(255, 255, 255, 0.9);
}

/* 选中封面：亮绿材质（pw 原版书架选中色，属品牌资产固定色） */
.project-deck-card.is-active {
  border-color: rgba(226, 255, 240, 0.72);
  background:
    radial-gradient(circle at 78% 15%, rgba(226, 255, 240, 0.24), transparent 29%),
    linear-gradient(136deg, rgba(255, 255, 255, 0.27), transparent 28%, rgba(8, 66, 38, 0.13) 76%),
    linear-gradient(148deg, #4ce595, #0c9c58 60%, #088449);
  box-shadow: inset 0 1px rgba(255, 255, 255, 0.5), inset 1px 0 rgba(255, 255, 255, 0.28), inset -1px 0 rgba(6, 44, 27, 0.2);
  color: #062c1b;
  cursor: pointer;
}

/* 书芯侧面：暖纸页缘 */
.project-deck-card__thickness {
  position: absolute;
  top: 4px;
  left: calc(100% - 3px);
  width: calc(var(--deck-thickness, 28px) - 6px);
  height: calc(100% - 8px);
  pointer-events: none;
  border-radius: 1px;
  background:
    repeating-linear-gradient(90deg, transparent 0 2px, rgba(88, 104, 94, 0.22) 2px 3px),
    linear-gradient(90deg, #c8d2cb, #f4f8f5 20%, #dde5de 84%, #b3bfb6);
  box-shadow: inset 0 2px 3px rgba(48, 62, 54, 0.2), inset 0 -2px 3px rgba(48, 62, 54, 0.18);
  transform: translateZ(-3px) rotateY(90deg);
  transform-origin: 0 50%;
  backface-visibility: visible;
}

/* 封底：灰纸 */
.project-deck-card__back {
  position: absolute;
  inset: 0;
  border: 1px solid rgba(244, 250, 247, 0.8);
  border-radius: 5px;
  background: linear-gradient(140deg, #cfd8d1, #a8b4ac);
  transform: translateZ(calc(-1 * var(--deck-thickness, 28px)));
  pointer-events: none;
}

/* 书脊：纸材质 + 墨绿文字 */
.project-deck-card__spine {
  position: absolute;
  inset: 0 auto 0 0;
  width: var(--deck-thickness, 28px);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: space-between;
  box-sizing: border-box;
  padding: 16px 4px;
  color: #2c3a30;
  border: 1px solid rgba(244, 250, 247, 0.75);
  border-radius: 4px;
  background: linear-gradient(90deg, #a8b4ac, #dfe7e1 24%, #c2cec6 70%, #96a29a);
  transform: translateZ(calc(-1 * var(--deck-thickness, 28px))) rotateY(-90deg);
  transform-origin: 0 50%;
  backface-visibility: hidden;
  pointer-events: auto;
}

.project-deck-card__spine strong {
  writing-mode: vertical-rl;
  text-orientation: mixed;
  max-height: calc(100% - 62px);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 14px;
  font-weight: 700;
  letter-spacing: 2px;
}

.project-deck-card__spine-number {
  font-size: 10px;
  opacity: 0.65;
}

.project-deck-card__spine .deck-icon {
  width: 16px;
  height: 16px;
}

/* 封面接地投影 */
.project-deck-card__contact-shadow {
  position: absolute;
  top: calc(100% + 3px);
  left: 50%;
  width: 48px;
  height: 12px;
  border-radius: 50%;
  background: radial-gradient(ellipse, rgba(0, 0, 0, 0.22), rgba(0, 0, 0, 0.07) 42%, transparent 72%);
  pointer-events: none;
  /* 反向旋转，避免侧对封面把投影压成一条线 */
  transform: translateX(-50%) rotateZ(calc(-1 * var(--deck-rotate-z))) rotateY(calc(-1 * var(--deck-rotate-y))) rotateX(calc(-1 * var(--deck-rotate-x)));
  transition: width 430ms ease, height 430ms ease, opacity 430ms ease;
}

.project-deck-card.is-active .project-deck-card__contact-shadow {
  width: 160px;
  height: 18px;
  opacity: 0.7;
}

/* 光泽层容器：裁切高光，让书芯侧面能伸出卡片盒 */
.project-deck-card__gloss {
  position: absolute;
  z-index: 1;
  inset: 0;
  overflow: hidden;
  pointer-events: none;
  border-radius: inherit;
}

.project-deck-card__gloss::after {
  content: '';
  position: absolute;
  inset: 0 auto 0 7px;
  width: 5px;
  background: linear-gradient(90deg, rgba(24, 40, 32, 0.16), rgba(255, 255, 255, 0.38), transparent);
}

/* 封面右缘：纸页厚度感 */
.project-deck-card__edge {
  position: absolute;
  inset: 0 0 0 auto;
  width: 10px;
  background:
    linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.42) 38%, rgba(20, 40, 30, 0.3)),
    linear-gradient(180deg, rgba(255, 255, 255, 0.52), transparent 20%, rgba(0, 0, 0, 0.22));
  box-shadow: 6px 0 16px rgba(255, 255, 255, 0.08);
}

/* 金属高光带：随指针位置移动的反光 */
.project-deck-card__specular {
  position: absolute;
  z-index: 1;
  inset: -40% -20% 30% -34%;
  transform: rotate(-19deg) translate(var(--shine-x, 0), var(--shine-y, 0));
  border-radius: 50%;
  background: linear-gradient(
    112deg,
    transparent 22%,
    rgba(255, 255, 255, 0.62) 44%,
    rgba(255, 255, 255, 0.16) 60%,
    transparent 74%
  );
  filter: blur(7px);
  opacity: 0.8;
  pointer-events: none;
  transition: transform 320ms ease, opacity 220ms ease;
}

.project-deck-card.is-active .project-deck-card__specular {
  background: linear-gradient(
    112deg,
    transparent 22%,
    rgba(226, 255, 240, 0.42) 44%,
    rgba(255, 255, 255, 0.1) 62%,
    transparent 74%
  );
  opacity: 0.7;
}

/* 纸纹肌理 */
.project-deck-card__grain {
  position: absolute;
  inset: 0;
  background:
    linear-gradient(90deg, rgba(24, 40, 32, 0.045) 1px, transparent 1px),
    linear-gradient(rgba(24, 40, 32, 0.038) 1px, transparent 1px),
    radial-gradient(circle at 82% 20%, rgba(24, 40, 32, 0.18) 0 2px, transparent 3px);
  background-size: 22px 22px, 22px 22px, auto;
  opacity: 0.62;
  pointer-events: none;
}

.project-deck-card.is-active .project-deck-card__grain {
  background:
    linear-gradient(90deg, rgba(230, 255, 242, 0.07) 1px, transparent 1px),
    linear-gradient(rgba(230, 255, 242, 0.05) 1px, transparent 1px),
    radial-gradient(circle at 82% 20%, rgba(230, 255, 242, 0.28) 0 2px, transparent 3px);
  background-size: 22px 22px, 22px 22px, auto;
}

/* ── 封面前景内容 ── */

.project-deck-card__state,
.project-deck-card__toolbar,
.project-deck-card__number,
.project-deck-card__icon,
.project-deck-card__title,
.project-deck-card__progress,
.project-deck-card footer {
  position: relative;
  z-index: 2;
}

.project-deck-card__toolbar {
  display: flex;
  align-items: center;
  gap: 6px;
  align-self: stretch;
  min-height: 26px;
  padding-right: 28px;
}

.project-deck-card:not(.is-active):not(.is-hovered) .project-deck-card__title p,
.project-deck-card:not(.is-active):not(.is-hovered) .project-deck-card__progress,
.project-deck-card:not(.is-active):not(.is-hovered) footer,
.project-deck-card:not(.is-active):not(.is-hovered) .project-deck-card__toolbar {
  opacity: 0;
  pointer-events: none;
}

.project-deck-card__title p,
.project-deck-card__progress,
.project-deck-card footer,
.project-deck-card__toolbar {
  transition: opacity 260ms ease;
}

.project-deck-card__settings {
  width: 22px;
  height: 22px;
  display: grid;
  flex: 0 0 auto;
  place-items: center;
  border: 1px solid rgba(28, 46, 38, 0.2);
  border-radius: 6px;
  background: rgba(244, 250, 247, 0.2);
  color: inherit;
  cursor: pointer;
  margin-left: auto;
  transition: background-color 160ms ease, color 160ms ease, border-color 160ms ease;
}

.project-deck-card__settings svg {
  display: block;
  width: 13px;
  height: 13px;
}

.project-deck-card__settings.is-delete:hover,
.project-deck-card__settings.is-delete:focus-visible {
  border-color: var(--color-danger);
  background: var(--color-danger);
  color: #ffffff;
}

.project-deck-card__settings:focus-visible {
  outline: 2px solid #ffffff;
  outline-offset: 2px;
}

.project-deck-card__settings:disabled {
  cursor: not-allowed;
  opacity: 0.5;
}

.project-deck-card__number {
  position: absolute;
  top: 15px;
  right: 15px;
  color: currentColor;
  font-size: 10px;
  font-weight: 800;
  opacity: 0.58;
}

.project-deck-card__state {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  align-self: flex-start;
  min-height: 26px;
  padding: 5px 8px;
  border: 1px solid rgba(28, 46, 38, 0.18);
  border-radius: 5px;
  background: rgba(244, 250, 247, 0.22);
  color: inherit;
  font-size: 10px;
  font-weight: 700;
}

.project-deck-card__state i {
  width: 6px;
  height: 6px;
  display: block;
  border-radius: 50%;
  background: currentColor;
  box-shadow: 0 0 10px currentColor;
}

/* 阶段灯：固定语义色（状态色例外允许，与旧卡片契约一致） */
.project-deck-card.is-stage-planning .project-deck-card__state i { background: #3b82f6; }
.project-deck-card.is-stage-writing .project-deck-card__state i { background: #f59e0b; }
.project-deck-card.is-stage-reviewing .project-deck-card__state i { background: #8b5cf6; }
.project-deck-card.is-stage-completed .project-deck-card__state i { background: #10b981; }

/* 类型指纹小签：悬停时与操作行同现 */
.project-deck-card__genre {
  overflow: hidden;
  max-width: 92px;
  padding: 3px 7px;
  border: 1px solid color-mix(in srgb, var(--kind-accent, #2563eb) 38%, rgba(28, 46, 38, 0.14));
  border-radius: 999px;
  color: var(--kind-accent, #2563eb);
  background: rgba(255, 255, 255, 0.18);
  font-size: 10px;
  font-weight: 650;
  letter-spacing: 0.02em;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.project-deck-card__icon {
  position: relative;
  width: 44px;
  height: 44px;
  display: grid;
  align-self: flex-end;
  place-items: center;
  margin: 8px 2px 0 0;
  border: 1px solid color-mix(in srgb, var(--kind-accent, #2563eb) 32%, rgba(20, 36, 28, 0.17));
  border-radius: 50%;
  background:
    radial-gradient(circle at 34% 26%, color-mix(in srgb, var(--kind-accent, #2563eb) 35%, white), rgba(255, 255, 255, 0.12) 54%, rgba(20, 36, 28, 0.08));
  box-shadow: inset 0 1px rgba(255, 255, 255, 0.55), 0 7px 16px rgba(40, 32, 20, 0.08);
  color: inherit;
}

.project-deck-card__icon svg {
  width: 21px;
  height: 21px;
}

.project-deck-card.is-active .project-deck-card__icon {
  border-color: rgba(226, 255, 240, 0.34);
  background: radial-gradient(circle at 34% 26%, rgba(255, 255, 255, 0.36), rgba(255, 255, 255, 0.06) 54%, rgba(80, 30, 20, 0.14));
  box-shadow: inset 0 1px rgba(255, 255, 255, 0.34), 0 9px 20px rgba(80, 30, 20, 0.14);
}

.project-deck-card__title {
  display: grid;
  gap: 5px;
  margin-top: auto;
}

.project-deck-card__title small {
  color: currentColor;
  font-size: 10px;
  font-weight: 700;
  opacity: 0.72;
  max-width: 145px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.project-deck-card__title strong {
  display: -webkit-box;
  overflow: hidden;
  color: currentColor;
  font-family: 'Noto Serif SC', 'Songti SC', 'SimSun', serif;
  font-size: 19px;
  font-weight: 700;
  line-height: 1.3;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
}

.project-deck-card__title p {
  display: -webkit-box;
  overflow: hidden;
  margin: 2px 0 0;
  color: currentColor;
  font-size: 10px;
  line-height: 1.45;
  opacity: 0.72;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
  min-height: 29px;
}

.project-deck-card.is-active .project-deck-card__title strong,
.project-deck-card.is-active .project-deck-card__title p,
.project-deck-card.is-active footer,
.project-deck-card.is-active footer strong {
  text-shadow: 0 1px rgba(255, 255, 255, 0.12);
}

.project-deck-card__progress {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 11px;
}

.project-deck-card__progress > span {
  height: 4px;
  flex: 1;
  overflow: hidden;
  border-radius: 999px;
  background: rgba(0, 0, 0, 0.14);
}

.project-deck-card.is-active .project-deck-card__progress > span {
  background: rgba(0, 0, 0, 0.22);
}

.project-deck-card__progress i {
  height: 100%;
  display: block;
  border-radius: inherit;
  background: currentColor;
  opacity: 0.88;
}

.project-deck-card__progress em {
  min-width: 29px;
  color: currentColor;
  font-size: 10px;
  font-style: normal;
  font-weight: 700;
  text-align: right;
}

.project-deck-card footer {
  display: flex;
  align-items: center;
  gap: 6px;
  min-height: 27px;
  margin-top: 8px;
  color: currentColor;
  font-size: 9px;
  opacity: 0.75;
}

.project-deck-card footer span {
  white-space: nowrap;
}

.project-deck-card footer strong {
  overflow: hidden;
  max-width: 84px;
  font-size: 10px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.project-deck-card footer button {
  width: 25px;
  height: 25px;
  margin-left: auto;
  display: grid;
  place-items: center;
  border: 1px solid currentColor;
  border-radius: 6px;
  color: currentColor;
  opacity: 0.86;
}

.project-deck-card footer button svg {
  width: 15px;
  height: 15px;
}

.project-deck-card footer button:hover,
.project-deck-card footer button:focus-visible {
  outline: none;
  background: rgba(255, 255, 255, 0.19);
}

.project-deck-card:not(.is-active) footer button {
  visibility: hidden;
}

/* ── 书架切换圆点 ── */

.project-deck-dots {
  position: relative;
  z-index: 5;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 8px 14px 10px;
}

.project-deck-dots button {
  width: 6px;
  height: 6px;
  padding: 0;
  border: 0;
  border-radius: 999px;
  background: color-mix(in srgb, var(--app-text-primary) 20%, transparent);
  cursor: pointer;
  transition: width 160ms ease, background-color 160ms ease;
}

.project-deck-dots button.is-active {
  width: 24px;
  background: var(--color-brand);
  box-shadow: 0 0 12px color-mix(in srgb, var(--color-brand) 38%, transparent);
}

/* ── 空态 / 加载骨架 ── */

.project-deck-empty {
  min-height: 280px;
  display: grid;
  place-content: center;
  gap: 8px;
  border: 0;
  background: transparent;
  color: var(--app-text-secondary);
  cursor: pointer;
}

.project-deck-empty > span {
  width: 54px;
  height: 54px;
  display: grid;
  place-items: center;
  justify-self: center;
  border: 1px dashed var(--app-border-strong);
  border-radius: 50%;
}

.project-deck-empty > span svg {
  width: 26px;
  height: 26px;
}

.project-deck-empty strong {
  color: var(--app-text-primary);
  font-size: 14px;
}

.project-deck-empty em {
  color: var(--app-text-muted);
  font-size: 11px;
  font-style: normal;
}

.project-deck--loading {
  display: grid;
  place-items: center;
  perspective: 2000px;
  perspective-origin: 34% 46%;
  min-height: 280px;
}

/* 骨架屏：主题原语混合的微光扫过，浅深主题都可见 */
.project-deck--loading > span {
  position: absolute;
  width: 164px;
  height: 214px;
  border: 1px solid var(--app-border);
  border-radius: 8px;
  background: linear-gradient(
    108deg,
    color-mix(in srgb, var(--app-text-primary) 5%, transparent),
    color-mix(in srgb, var(--app-text-primary) 13%, transparent),
    color-mix(in srgb, var(--app-text-primary) 5%, transparent)
  );
  transform:
    translateX(calc((var(--skeleton-i) - 3) * 52px))
    rotateY(-58deg)
    rotateZ(-4deg);
  animation: deck-skeleton 1.5s ease-in-out infinite;
}

.project-deck--loading > span:nth-child(1) { --skeleton-i: 0; opacity: 0.42; }
.project-deck--loading > span:nth-child(2) { --skeleton-i: 1; opacity: 0.58; }
.project-deck--loading > span:nth-child(3) { --skeleton-i: 2; opacity: 0.76; }
.project-deck--loading > span:nth-child(4) { --skeleton-i: 3; opacity: 0.9; }
.project-deck--loading > span:nth-child(5) { --skeleton-i: 4; opacity: 0.76; }
.project-deck--loading > span:nth-child(6) { --skeleton-i: 5; opacity: 0.58; }
.project-deck--loading > span:nth-child(7) { --skeleton-i: 6; opacity: 0.42; }

@keyframes deck-skeleton {
  0%, 100% { opacity: 0.42; }
  50% { opacity: 0.88; }
}

.numeric {
  font-variant-numeric: tabular-nums;
}

/* 窄屏：舞台退化为正常流，竖向滚动放行 */
@media (max-width: 820px) {
  .project-deck-shell {
    min-height: 0;
  }
}

@media (prefers-reduced-motion: reduce) {
  .project-deck-card {
    transition: none;
  }
  .project-deck--loading > span {
    animation: none;
  }
}
</style>
