<template>
  <div class="writing-section">
    <template v-if="!novelSlug">
      <div class="empty-state">
        <div class="empty-title">未绑定书目</div>
        <p class="empty-desc">
          写作偏好保存在当前作品中，请先从书库打开作品并进入工作台
          （路由含 <span class="mono">/book/&lt;id&gt;</span>）后再配置。
        </p>
      </div>
    </template>

    <template v-else>
      <header class="section-header">
        <div>
          <h2 class="section-title">写作偏好</h2>
          <p class="section-sub">展示模式、目标字数与排版输出，按书目保存。</p>
        </div>
        <n-tag v-if="novelTitle" size="small" :bordered="false" class="book-tag">{{ novelTitle }}</n-tag>
      </header>

      <n-spin :show="loading">
        <div class="prefs-stack">

          <!-- ── 目标字数 ──────────────────────── -->
          <div class="pref-group">
            <div class="pref-group-header">
              <span class="pref-group-title">目标字数</span>
              <span class="pref-group-hint">设定每章写作目标，全托管据此分配节拍预算</span>
            </div>
            <div class="word-count-row">
              <div class="word-count-presets">
                <button
                  v-for="preset in wordCountPresets"
                  :key="preset.value"
                  type="button"
                  class="wc-preset-btn"
                  :class="{ active: targetWordsInput === preset.value }"
                  @click="targetWordsInput = preset.value"
                >
                  <span class="wc-value">{{ preset.label }}</span>
                  <span class="wc-desc">{{ preset.desc }}</span>
                </button>
              </div>
              <div class="word-count-custom">
                <n-input-number
                  v-model:value="targetWordsInput"
                  :min="300"
                  :max="20000"
                  :step="100"
                  :show-button="false"
                  placeholder="自定义"
                  class="wc-input"
                />
                <span class="wc-unit">字 / 章</span>
                <n-button
                  type="primary"
                  size="small"
                  :loading="savingWordCount"
                  :disabled="targetWordsInput === savedTargetWords"
                  @click="saveWordCount"
                >
                  保存
                </n-button>
              </div>
            </div>
          </div>

          <!-- ── 展示标签 ──────────────────────── -->
          <div class="pref-group">
            <div class="pref-group-header">
              <span class="pref-group-title">章节计数标签</span>
              <span class="pref-group-hint">影响工作台标题栏与进度展示文案</span>
            </div>
            <div class="toggle-row">
              <div class="toggle-label">
                <span class="toggle-name">阶段模式</span>
                <span class="toggle-hint">开启后以「阶段」替代「章」展示进度</span>
              </div>
              <n-switch
                :value="phaseDisplay"
                :loading="patching === 'phase_display_mode'"
                size="large"
                @update:value="onPhaseDisplaySwitch"
              >
                <template #checked>阶段</template>
                <template #unchecked>章</template>
              </n-switch>
            </div>
          </div>

          <!-- ── 落盘排版 ──────────────────────── -->
          <div class="pref-group">
            <div class="pref-group-header">
              <span class="pref-group-title">落盘排版</span>
              <span class="pref-group-hint">影响模型输出保存时的格式处理</span>
            </div>
            <div class="toggle-row">
              <div class="toggle-label">
                <span class="toggle-name">正文短句聚合</span>
                <span class="toggle-hint">
                  保存前将段内碎片换行合并为连片叙述；对话 「」 与 【】 分段仍保留。默认关闭。
                </span>
              </div>
              <n-switch
                :value="inlineProseAggregation"
                :loading="patching === 'inline_prose_aggregation_enabled'"
                size="large"
                @update:value="(v: boolean) => onBoolPref('inline_prose_aggregation_enabled', v)"
              >
                <template #checked>已启用</template>
                <template #unchecked>已关闭</template>
              </n-switch>
            </div>
          </div>

        </div>
      </n-spin>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useMessage } from 'naive-ui'
import { novelApi, type GenerationPrefsDTO } from '@/api/novel'
import { WORKBENCH_GENERATION_PREFS_UPDATED_EVENT } from '@/workbench/deskEvents'

const route = useRoute()
const message = useMessage()

const novelSlug = computed(() => String(route.params.slug ?? '').trim())
const loading = ref(false)
const novelTitle = ref('')
const patching = ref<string | null>(null)
const savingWordCount = ref(false)

const phaseDisplay = ref(true)
const inlineProseAggregation = ref(false)
const targetWordsInput = ref<number | null>(2000)
const savedTargetWords = ref<number | null>(2000)

const wordCountPresets: { value: number; label: string; desc: string }[] = [
  { value: 1500, label: '1,500', desc: '短章节' },
  { value: 2000, label: '2,000', desc: '标准' },
  { value: 3000, label: '3,000', desc: '长章节' },
  { value: 5000, label: '5,000', desc: '超长章' },
]

function applyNovel(n: { title?: string; generation_prefs?: GenerationPrefsDTO | null; target_words_per_chapter?: number | null }) {
  novelTitle.value = n.title ?? ''
  const p = n.generation_prefs ?? {}
  phaseDisplay.value = Object.prototype.hasOwnProperty.call(p, 'phase_display_mode')
    ? Boolean(p.phase_display_mode)
    : true
  inlineProseAggregation.value = Boolean(p.inline_prose_aggregation_enabled)
  const w = n.target_words_per_chapter
  targetWordsInput.value = typeof w === 'number' && w > 0 ? w : 2000
  savedTargetWords.value = targetWordsInput.value
}

async function loadNovel() {
  const slug = novelSlug.value
  if (!slug) return
  loading.value = true
  try {
    const n = await novelApi.getNovel(slug)
    applyNovel(n)
  } catch (e) {
    message.error(e instanceof Error ? e.message : '加载书目失败')
  } finally {
    loading.value = false
  }
}

async function mergePrefs(patch: Partial<GenerationPrefsDTO>) {
  const slug = novelSlug.value
  if (!slug) return
  const n = await novelApi.updateNovel(slug, { generation_prefs: patch })
  applyNovel(n)
  window.dispatchEvent(new CustomEvent(WORKBENCH_GENERATION_PREFS_UPDATED_EVENT))
}

async function onBoolPref(key: 'inline_prose_aggregation_enabled', value: boolean) {
  const slug = novelSlug.value
  if (!slug) return
  patching.value = key
  try {
    await mergePrefs({ [key]: value })
    message.success('已保存')
  } catch (e) {
    message.error(e instanceof Error ? e.message : '保存失败')
    await loadNovel()
  } finally {
    patching.value = null
  }
}

async function onPhaseDisplaySwitch(phaseOn: boolean) {
  const slug = novelSlug.value
  if (!slug) return
  patching.value = 'phase_display_mode'
  try {
    await mergePrefs({ phase_display_mode: phaseOn })
    message.success('已保存')
  } catch (e) {
    message.error(e instanceof Error ? e.message : '保存失败')
    await loadNovel()
  } finally {
    patching.value = null
  }
}

async function saveWordCount() {
  const slug = novelSlug.value
  if (!slug || targetWordsInput.value == null) return
  savingWordCount.value = true
  try {
    const n = await novelApi.updateNovel(slug, { target_words_per_chapter: targetWordsInput.value })
    applyNovel(n)
    message.success(`目标字数已设为 ${targetWordsInput.value.toLocaleString()} 字/章`)
  } catch (e) {
    message.error(e instanceof Error ? e.message : '保存失败')
  } finally {
    savingWordCount.value = false
  }
}

watch(
  novelSlug,
  (s) => { if (s) void loadNovel() },
  { immediate: true }
)
</script>

<style scoped>
.writing-section {
  max-width: 680px;
}

.section-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 24px;
}

.section-title {
  margin: 0 0 0.25rem;
  font-size: calc(var(--font-size-lg) * 1.06);
  font-weight: 700;
  color: var(--app-text-primary);
}

.section-sub {
  margin: 0;
  font-size: var(--font-size-sm);
  line-height: 1.55;
  color: var(--app-text-secondary);
}

.book-tag {
  flex-shrink: 0;
  font-weight: 500;
  border-radius: 999px;
  background: var(--app-surface-muted, rgba(148, 163, 184, 0.18)) !important;
}

.prefs-stack {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

/* ── 分组 ── */
.pref-group {
  border: 1px solid var(--app-border, #e2e8f0);
  border-radius: 0.875rem;
  overflow: hidden;
}

.pref-group-header {
  display: flex;
  flex-direction: column;
  gap: 0.19rem;
  padding: 0.875rem 1.125rem 0.75rem;
  background: var(--app-surface-subtle, #f8fafc);
  border-bottom: 1px solid var(--app-border, #e2e8f0);
}

.pref-group-title {
  font-size: calc(var(--font-size-sm) * 1.04);
  font-weight: 700;
  color: var(--app-text-primary);
}

.pref-group-hint {
  font-size: calc(var(--font-size-xs) * 0.96);
  color: var(--app-text-muted);
  line-height: 1.5;
}

/* ── 字数选择 ── */
.word-count-row {
  padding: 1rem 1.125rem;
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.word-count-presets {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 0.5rem;
}

.wc-preset-btn {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.125rem;
  padding: 0.625rem 0.5rem;
  border-radius: 0.625rem;
  border: 1.5px solid var(--app-border, #e2e8f0);
  background: var(--app-surface);
  cursor: pointer;
  transition: border-color 0.15s ease, background 0.15s ease, box-shadow 0.15s ease;
}

.wc-preset-btn:hover {
  border-color: var(--color-brand-hover, #3b82f6);
  box-shadow: 0 2px 8px rgba(37, 99, 235, 0.08);
}

.wc-preset-btn.active {
  border-color: var(--color-brand, #2563eb);
  background: rgba(37, 99, 235, 0.06);
  box-shadow: 0 0 0 2px rgba(37, 99, 235, 0.1);
}

[data-theme='anchor'] .wc-preset-btn.active {
  border-color: var(--color-gold, #d4a843);
  background: rgba(212, 168, 67, 0.07);
  box-shadow: 0 0 0 2px rgba(212, 168, 67, 0.1);
}

.wc-value {
  font-size: var(--font-size-base);
  font-weight: 700;
  color: var(--app-text-primary);
}

.wc-desc {
  font-size: calc(var(--font-size-xs) * 0.88);
  color: var(--app-text-muted);
}

.word-count-custom {
  display: flex;
  align-items: center;
  gap: 0.625rem;
}

.wc-input {
  width: 7.5rem;
}

.wc-unit {
  font-size: var(--font-size-sm);
  color: var(--app-text-secondary);
  white-space: nowrap;
}

/* ── 开关行 ── */
.toggle-row {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 1.25rem;
  padding: 1rem 1.125rem;
}

.toggle-label {
  flex: 1;
  min-width: 0;
}

.toggle-name {
  display: block;
  font-size: var(--font-size-base);
  font-weight: 600;
  color: var(--app-text-primary);
  margin-bottom: 0.25rem;
}

.toggle-hint {
  display: block;
  font-size: var(--font-size-xs);
  line-height: 1.55;
  color: var(--app-text-muted);
  max-width: 440px;
}

/* ── 空状态 ── */
.empty-state {
  padding: 1.75rem 1.25rem;
  border-radius: 0.875rem;
  border: 1px dashed var(--app-border-soft, rgba(148, 163, 184, 0.45));
  background: var(--app-surface-subtle, rgba(248, 250, 252, 0.6));
}

.empty-title {
  font-size: calc(var(--font-size-base) * 1.06);
  font-weight: 600;
  margin-bottom: 0.5rem;
  color: var(--app-text-primary);
}

.empty-desc {
  margin: 0;
  font-size: var(--font-size-sm);
  line-height: 1.6;
  color: var(--app-text-secondary);
}

.mono {
  font-size: calc(var(--font-size-xs) * 0.96);
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono', monospace;
  padding: 0 0.25rem;
  border-radius: 0.25rem;
  background: var(--app-surface-muted, rgba(148, 163, 184, 0.15));
}
</style>
