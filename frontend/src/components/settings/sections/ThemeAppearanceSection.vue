<template>
  <div class="theme-section">

    <!-- ── 主题模式 ───────────────────────────────── -->
    <div class="section-group">
      <div class="group-header">
        <span class="group-title">配色主题</span>
        <span class="group-hint">立即生效并自动保存</span>
      </div>
      <div class="theme-grid">
        <div
          v-for="option in themeOptions"
          :key="option.value"
          class="theme-tile"
          :class="{ active: themeStore.mode === option.value }"
          :data-mode="option.value"
          @click="handleThemeChange(option.value)"
        >
          <!-- 缩略预览 -->
          <div class="tile-preview" :class="option.previewClass">
            <div class="tile-preview-bar">
              <span class="tile-dot"></span>
              <span class="tile-dot"></span>
              <span class="tile-dot"></span>
            </div>
            <div class="tile-preview-lines">
              <div class="tile-line w-full"></div>
              <div class="tile-line w-3/4"></div>
              <div class="tile-line w-1/2"></div>
            </div>
          </div>
          <div class="tile-meta">
            <span class="tile-icon" v-html="option.icon"></span>
            <span class="tile-name">{{ option.label }}</span>
            <svg v-if="themeStore.mode === option.value" class="tile-check" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" width="16" height="16">
              <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.857-9.809a.75.75 0 00-1.214-.882l-3.483 4.79-1.88-1.88a.75.75 0 10-1.06 1.061l2.5 2.5a.75.75 0 001.137-.089l4-5.5z" clip-rule="evenodd"/>
            </svg>
          </div>
        </div>
      </div>
    </div>

    <!-- ── 界面字号 ────────────────────────────────── -->
    <div class="section-group">
      <div class="group-header">
        <span class="group-title">界面字号</span>
        <span class="group-hint">悬停预览 · 点击保存</span>
      </div>

      <div class="size-layout">
        <!-- 4 个字号卡 -->
        <div class="size-cards">
          <button
            v-for="opt in fontSizeOptions"
            :key="opt.value"
            type="button"
            class="size-card"
            :class="{ active: fontSizeStore.preset === opt.value, hovering: hoverPreset === opt.value }"
            @mouseenter="hoverPreset = opt.value"
            @mouseleave="hoverPreset = null"
            @click="handleFontSizeChange(opt.value)"
          >
            <span class="size-aa" :style="{ fontSize: opt.aaPx }">Aa</span>
            <span class="size-name">{{ opt.label }}</span>
            <span class="size-pct">{{ opt.hint }}</span>
          </button>
        </div>

        <!-- 实时预览区：字号随悬停/选中变化 -->
        <div class="size-preview-box" :style="previewBoxStyle">
          <div class="preview-chapter-label">第十二章 · 目标 {{ previewWordCount }} 字</div>
          <p class="preview-body-text">
            这是一段示例正文，展示当前字号下的阅读体验。全托管节拍续写已完成
            <strong>{{ previewWordCountDone }}</strong> 字，排版与行距随界面档位同步缩放。
          </p>
          <div class="preview-status-row">
            <span class="preview-progress-bar">
              <span class="preview-progress-fill" :style="{ width: '68%' }"></span>
            </span>
            <span class="preview-pct-label">68%</span>
          </div>
        </div>
      </div>
    </div>

  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useMessage } from 'naive-ui'
import { useThemeStore, type ThemeMode } from '@/stores/themeStore'
import { useFontSizeStore, type FontSizePreset } from '@/stores/fontSizeStore'

const message = useMessage()
const themeStore = useThemeStore()
const fontSizeStore = useFontSizeStore()

const hoverPreset = ref<FontSizePreset | null>(null)

const SCALE_MAP: Record<FontSizePreset, number> = {
  small: 0.875,
  medium: 1,
  large: 1.125,
  xlarge: 1.25,
}

const fontSizeOptions: { value: FontSizePreset; label: string; hint: string; aaPx: string }[] = [
  { value: 'small',  label: '较小', hint: '87.5%', aaPx: '18px' },
  { value: 'medium', label: '默认', hint: '100%',  aaPx: '22px' },
  { value: 'large',  label: '较大', hint: '112.5%',aaPx: '26px' },
  { value: 'xlarge', label: '特大', hint: '125%',  aaPx: '30px' },
]

const effectivePreset = computed<FontSizePreset>(() => hoverPreset.value ?? fontSizeStore.preset)

const previewBoxStyle = computed(() => {
  const scale = SCALE_MAP[effectivePreset.value]
  return { fontSize: `${scale * 14}px` }
})

const previewWordCount = computed(() => {
  const scale = SCALE_MAP[effectivePreset.value]
  return scale >= 1.2 ? '1,500' : scale >= 1.1 ? '1,800' : '2,000'
})
const previewWordCountDone = computed(() => {
  const scale = SCALE_MAP[effectivePreset.value]
  return scale >= 1.2 ? '1,020' : scale >= 1.1 ? '1,224' : '1,360'
})

const themeOptions = computed(() => [
  {
    value: 'light' as ThemeMode,
    label: '浅色',
    previewClass: 'prev-light',
    icon: '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="#f59e0b" width="14" height="14"><circle cx="10" cy="10" r="4"/><path d="M10 2v1.5M10 16.5V18M3.22 3.22l1.06 1.06m11.44 11.44 1.06 1.06M2 10h1.5M16.5 10H18M4.28 15.72l1.06-1.06M14.66 5.34l1.06-1.06" stroke="#f59e0b" stroke-width="1.5" stroke-linecap="round" fill="none"/></svg>',
  },
  {
    value: 'dark' as ThemeMode,
    label: '深色',
    previewClass: 'prev-dark',
    icon: '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="#818cf8" width="14" height="14"><path d="M17.293 13.293A8 8 0 016.707 2.707a8.001 8.001 0 1010.586 10.586z"/></svg>',
  },
  {
    value: 'anchor' as ThemeMode,
    label: '黑金',
    previewClass: 'prev-anchor',
    icon: '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" width="14" height="14"><defs><linearGradient id="g1" x1="0%" y1="0%" x2="100%" y2="100%"><stop offset="0%" stop-color="#d4a843"/><stop offset="100%" stop-color="#f5d485"/></linearGradient></defs><path d="M10 2l2.09 4.26L17 7.27l-3.5 3.41.83 4.82L10 13.27l-4.33 2.23.83-4.82L3 7.27l4.91-.71z" fill="url(#g1)"/></svg>',
  },
  {
    value: 'auto' as ThemeMode,
    label: '跟随系统',
    previewClass: 'prev-auto',
    icon: '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" width="14" height="14"><rect x="2" y="3" width="16" height="12" rx="2" stroke="#94a3b8" stroke-width="1.5" fill="none"/><path d="M7 15v2m6-2v2M5 17h10" stroke="#94a3b8" stroke-width="1.5" stroke-linecap="round"/></svg>',
  },
])

function handleFontSizeChange(next: FontSizePreset) {
  if (fontSizeStore.preset === next) return
  fontSizeStore.setPreset(next)
  const label = fontSizeOptions.find((o) => o.value === next)?.label ?? next
  message.success(`字号已设为「${label}」`)
}

function handleThemeChange(newMode: ThemeMode) {
  const opt = themeOptions.value.find((o) => o.value === newMode)
  const label = opt?.label ?? newMode
  const applyTheme = () => { themeStore.setTheme(newMode) }
  if ('startViewTransition' in document) {
    ;(document as Document & { startViewTransition: (cb: () => void) => void })
      .startViewTransition(applyTheme)
  } else {
    const root = (document as Document).documentElement as HTMLElement
    root.classList.add('theme-transitioning')
    applyTheme()
    setTimeout(() => root.classList.remove('theme-transitioning'), 360)
  }
  message.success(`已切换到${label}主题`)
}
</script>

<style scoped>
.theme-section {
  display: flex;
  flex-direction: column;
  gap: 1.75rem;
}

/* ── 分组 ── */
.section-group {
  display: flex;
  flex-direction: column;
  gap: 0.875rem;
}

.group-header {
  display: flex;
  align-items: baseline;
  gap: 0.625rem;
}

.group-title {
  font-size: var(--font-size-sm);
  font-weight: 700;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: var(--app-text-muted);
}

.group-hint {
  font-size: calc(var(--font-size-xs) * 0.96);
  color: var(--app-text-muted);
  opacity: 0.7;
}

/* ── 主题 2×2 网格 ── */
.theme-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 0.625rem;
}

@media (min-width: 500px) {
  .theme-grid {
    grid-template-columns: repeat(4, 1fr);
  }
}

.theme-tile {
  border-radius: 0.875rem;
  border: 1.5px solid var(--app-border, #e2e8f0);
  overflow: hidden;
  cursor: pointer;
  transition: border-color 0.18s ease, box-shadow 0.18s ease, transform 0.18s ease;
  background: var(--app-surface);
}

.theme-tile:hover {
  border-color: #a5b4fc;
  box-shadow: 0 3px 12px rgba(79, 70, 229, 0.1);
  transform: translateY(-1px);
}

.theme-tile.active {
  border-color: var(--color-brand, #2563eb);
  box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.1), 0 3px 12px rgba(37, 99, 235, 0.12);
}

.theme-tile.active[data-mode='anchor'] {
  border-color: var(--color-gold, #d4a843);
  box-shadow: 0 0 0 3px rgba(212, 168, 67, 0.12), 0 3px 12px rgba(212, 168, 67, 0.15);
}

/* 缩略预览 */
.tile-preview {
  height: 4rem;
  padding: 0.5rem 0.625rem;
  display: flex;
  flex-direction: column;
  gap: 0.375rem;
  transition: background 0.3s ease;
}

.prev-light  { background: #f8fafc; }
.prev-dark   { background: #0d1120; }
.prev-anchor { background: linear-gradient(135deg, #0d0e14, #12141c); }
.prev-auto   { background: linear-gradient(135deg, #f8fafc 50%, #0d1120 50%); }

.tile-preview-bar {
  display: flex;
  gap: 0.25rem;
}

.tile-dot {
  width: 0.375rem;
  height: 0.375rem;
  border-radius: 50%;
}

.prev-light  .tile-dot { background: #cbd5e1; }
.prev-dark   .tile-dot { background: #334155; }
.prev-anchor .tile-dot { background: rgba(212, 168, 67, 0.35); }
.prev-auto   .tile-dot { background: #94a3b8; }

.tile-preview-lines {
  display: flex;
  flex-direction: column;
  gap: 0.3rem;
}

.tile-line {
  height: 0.3rem;
  border-radius: 0.2rem;
}

.w-full { width: 100%; }
.w-3\/4  { width: 75%; }
.w-1\/2  { width: 50%; }

.prev-light  .tile-line { background: #e2e8f0; }
.prev-dark   .tile-line { background: #1e293b; }
.prev-anchor .tile-line { background: rgba(212, 168, 67, 0.18); }
.prev-auto   .tile-line { background: #cbd5e1; }

/* 底部标签区 */
.tile-meta {
  display: flex;
  align-items: center;
  gap: 0.375rem;
  padding: 0.44rem 0.625rem 0.56rem;
  border-top: 1px solid var(--app-border, #e2e8f0);
}

.tile-icon {
  display: flex;
  align-items: center;
  flex-shrink: 0;
}

.tile-name {
  flex: 1;
  font-size: var(--font-size-xs);
  font-weight: 600;
  color: var(--app-text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.tile-check {
  flex-shrink: 0;
  color: var(--color-brand, #2563eb);
}

.theme-tile.active[data-mode='anchor'] .tile-check {
  color: var(--color-gold, #d4a843);
}

/* ── 字号卡 + 预览 ── */
.size-layout {
  display: flex;
  flex-direction: column;
  gap: 0.875rem;
}

.size-cards {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 0.5rem;
}

.size-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.25rem;
  padding: 0.875rem 0.625rem 0.75rem;
  border-radius: 0.8125rem;
  border: 1.5px solid var(--app-border, #e2e8f0);
  background: var(--app-surface);
  cursor: pointer;
  text-align: center;
  transition: border-color 0.15s ease, box-shadow 0.15s ease, transform 0.15s ease;
}

.size-card:hover,
.size-card.hovering {
  border-color: #a5b4fc;
  box-shadow: 0 2px 10px rgba(79, 70, 229, 0.1);
  transform: translateY(-1px);
}

.size-card.active {
  border-color: var(--color-brand, #2563eb);
  background: rgba(37, 99, 235, 0.05);
  box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.09), 0 2px 8px rgba(37, 99, 235, 0.1);
}

[data-theme='anchor'] .size-card.active {
  border-color: var(--color-gold, #d4a843);
  background: rgba(212, 168, 67, 0.07);
  box-shadow: 0 0 0 3px rgba(212, 168, 67, 0.12), 0 2px 8px rgba(212, 168, 67, 0.1);
}

[data-theme='anchor'] .size-card:hover,
[data-theme='anchor'] .size-card.hovering {
  border-color: rgba(212, 168, 67, 0.5);
}

.size-aa {
  font-weight: 700;
  line-height: 1;
  color: var(--app-text-primary);
  letter-spacing: -0.02em;
  transition: font-size 0.1s ease;
}

.size-name {
  font-size: var(--font-size-xs);
  font-weight: 600;
  color: var(--app-text-secondary);
}

.size-pct {
  font-size: calc(var(--font-size-xs) * 0.88);
  color: var(--app-text-muted);
}

/* 实时预览框 */
.size-preview-box {
  border-radius: 0.75rem;
  border: 1px solid var(--app-border, #e2e8f0);
  background: var(--app-surface-subtle, #f8fafc);
  padding: 0.875rem 1rem;
  transition: font-size 0.18s cubic-bezier(0.4, 0, 0.2, 1);
  user-select: none;
}

.preview-chapter-label {
  font-size: 0.75em;
  font-weight: 700;
  color: var(--app-text-muted);
  letter-spacing: 0.03em;
  margin-bottom: 0.375rem;
}

.preview-body-text {
  line-height: 1.7;
  color: var(--app-text-secondary);
  margin-bottom: 0.625rem;
}

.preview-status-row {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.preview-progress-bar {
  flex: 1;
  height: 0.25rem;
  border-radius: 0.125rem;
  background: var(--app-border, #e2e8f0);
  overflow: hidden;
  display: block;
}

.preview-progress-fill {
  display: block;
  height: 100%;
  border-radius: 0.125rem;
  background: var(--color-brand, #2563eb);
  transition: width 0.3s ease;
}

[data-theme='anchor'] .preview-progress-fill {
  background: var(--color-gold, #d4a843);
}

.preview-pct-label {
  font-size: 0.75em;
  font-weight: 600;
  color: var(--app-text-muted);
  white-space: nowrap;
}
</style>
