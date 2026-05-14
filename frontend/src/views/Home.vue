<template>
  <div class="home">
    <StatsSidebar
      @create-book="focusCreateInput"
      @refresh-list="handleRefreshList"
      @open-settings="showLLMSettings = true"
      @collapsed-change="handleSidebarCollapsedChange"
    />
    <div class="home-content" :class="{ 'sidebar-collapsed': sidebarCollapsed }">
      <div class="home-bg" aria-hidden="true" />

      <div class="container">
        <!-- Header -->
        <header class="header">
          <n-button
            quaternary
            circle
            size="medium"
            class="header-theme-btn"
            aria-label="主题设置"
            @click="showLLMSettings = true"
          >
            <template #icon>
              <n-icon :component="IconThemeSettings" :size="22" />
            </template>
          </n-button>
          <div class="header-content">
            <h1 class="title">墨枢 · 长篇叙事工作台</h1>
            <p class="subtitle">
              以梗概与类型开局，选定目标篇幅；宏观结构、幕次与节拍由后台自动编排，你专注把故事写下去即可。
            </p>
          </div>
        </header>

        <!-- Create Card -->
        <n-card class="create-card" :bordered="false">
          <n-space vertical :size="20">
            <div class="create-header">
              <div class="create-title-wrap">
                <span class="create-icon">✨</span>
                <h3 class="create-title">新建书目</h3>
              </div>
              <n-button text type="primary" @click="showAdvanced = !showAdvanced">
                <template #icon>
                  <n-icon><component :is="showAdvanced ? IconChevronUp : IconChevronDown" /></n-icon>
                </template>
                {{ showAdvanced ? '收起高级' : '高级（自定义章数/每章字数）' }}
              </n-button>
            </div>

            <n-input
              ref="createInputRef"
              v-model:value="newBook.premise"
              type="textarea"
              placeholder="用一段话写清主线与爽点预期（不超过 2000 字）…&#10;&#10;例如：废柴赘婿觉醒签到系统，从被退婚到一方巨擘。"
              :rows="5"
              :disabled="creating"
              size="large"
              class="premise-input"
              show-count
              :maxlength="PREMISE_MAX_LEN"
            />

            <div class="taxonomy-block">
              <div class="taxonomy-block-head">
                <span class="taxonomy-block-title">市场分区</span>
                <span class="taxonomy-block-sub">大类 → 细分主题 → 自动写入「类型 / 世界观」；均可再改。</span>
              </div>
              <MarketTaxonomyPicker
                v-model:genre="newBook.genre"
                v-model:worldPreset="newBook.worldPreset"
                :disabled="creating"
              />
            </div>

            <div v-show="!showAdvanced" class="length-tier-block">
              <div class="length-tier-label">目标篇幅（选一个即可，系统按网文常用节奏推导章数）</div>
              <n-radio-group v-model:value="lengthTier" name="lengthTier" class="length-tier-group">
                <n-space :size="14" :wrap="true" align="flex-start" class="length-tier-space">
                  <n-radio
                    v-for="opt in lengthTierOptions"
                    :key="opt.value"
                    :value="opt.value"
                    :disabled="creating"
                    class="length-tier-radio"
                  >
                    <div class="length-tier-option-inner">
                      <span class="length-tier-title">{{ opt.title }}</span>
                      <span class="length-tier-hint">{{ opt.hint }}</span>
                    </div>
                  </n-radio>
                </n-space>
              </n-radio-group>
            </div>

            <div v-show="showAdvanced" class="advanced-settings">
              <n-alert type="info" :show-icon="true" style="margin-bottom: 12px; font-size: 12px">
                自定义章数与每章字数时，不再使用「目标篇幅」档位推导；结构提示仍会在后台写入梗概供模型使用。
              </n-alert>
              <n-grid :cols="2" :x-gap="16" :y-gap="16" responsive="screen">
                <n-gi>
                  <n-form-item label="书名">
                    <n-input v-model:value="newBook.title" placeholder="留空则从梗概自动截取" />
                  </n-form-item>
                </n-gi>
                <n-gi>
                  <n-form-item label="章节数">
                    <n-input-number v-model:value="newBook.chapters" :min="1" :max="9999" class="w-full" placeholder="默认 100 章" />
                  </n-form-item>
                </n-gi>
                <n-gi>
                  <n-form-item label="每章字数">
                    <n-input-number v-model:value="newBook.words" :min="500" :max="10000" :step="500" class="w-full" />
                  </n-form-item>
                </n-gi>
              </n-grid>
            </div>

            <n-space justify="end">
              <n-button
                type="primary"
                size="large"
                round
                :loading="creating"
                :disabled="!newBook.premise.trim() || !newBook.genre.trim() || !newBook.worldPreset.trim()"
                @click="handleCreate"
              >
                <template #icon>
                  <n-icon><IconSpark /></n-icon>
                </template>
                建档并进入工作台
              </n-button>
            </n-space>
          </n-space>
        </n-card>

        <!-- Books Section -->
        <section class="books-section">
          <div class="section-header">
            <div class="section-left">
              <h2 class="section-title">我的书目</h2>
              <span class="book-count" v-if="!loading">{{ filteredBooks.length }} 本</span>
            </div>
            <div class="section-right">
              <n-input
                v-model:value="searchQuery"
                placeholder="搜索书名或类型…"
                clearable
                round
                class="search-input"
              >
                <template #prefix>
                  <n-icon><IconSearch /></n-icon>
                </template>
              </n-input>
              <n-button
                v-if="selectedBooks.length > 0"
                type="error"
                secondary
                @click="showBatchDeleteConfirm = true"
              >
                <template #icon>
                  <n-icon><IconTrash /></n-icon>
                </template>
                删除选中 ({{ selectedBooks.length }})
              </n-button>
            </div>
          </div>

          <!-- Loading State -->
          <div v-if="loading" class="loading-state">
            <n-spin size="large" />
            <p>加载中…</p>
          </div>

          <!-- Empty State -->
          <div v-else-if="books.length === 0" class="empty-state">
            <div class="empty-illustration">
              <span class="empty-icon">📚</span>
            </div>
            <h3 class="empty-title">还没有书目</h3>
            <p class="empty-desc">在上方输入你的故事创意，开启创作之旅</p>
            <n-button type="primary" size="large" round @click="focusCreateInput">
              <template #icon>
                <n-icon><IconSpark /></n-icon>
              </template>
              创建第一本书
            </n-button>
          </div>

          <!-- No Results State -->
          <div v-else-if="filteredBooks.length === 0" class="no-results-state">
            <span class="no-results-icon">🔍</span>
            <p>未找到匹配「{{ searchQuery }}」的书目</p>
            <n-button text type="primary" @click="searchQuery = ''">清除搜索</n-button>
          </div>

          <!-- Books Grid -->
          <template v-else>
            <!-- Selection Bar (仅搜索模式下显示) -->
            <div class="selection-bar" v-if="filteredBooks.length > 0 && searchQuery">
              <n-checkbox
                :checked="isAllSelected"
                :indeterminate="isPartialSelected"
                @update:checked="toggleSelectAll"
              >
                全选
              </n-checkbox>
              <span class="selection-hint" v-if="selectedBooks.length > 0">
                已选择 {{ selectedBooks.length }} 本
              </span>
            </div>

            <!-- 书目卡片：单行横排，多于可视宽度时横向滚动 -->
            <div class="books-list-wrap">
              <div class="books-grid">
                <div
                  v-for="(book, idx) in displayBooks"
                  :key="book.slug"
                  class="book-card"
                  :class="{ 'is-selected': selectedBooks.includes(book.slug) }"
                  :style="{ animationDelay: `${idx * 0.04}s` }"
                  @click="navigateToBook(book.slug)"
                >
                  <div class="card-top">
                    <span class="book-dot" :class="`dot-${book.stage}`"></span>
                    <span class="book-card-title">{{ book.title }}</span>
                  </div>
                  <div class="card-meta">
                    <n-tag :type="getStageType(book.stage)" size="small" round borderable>
                      {{ book.stage_label }}
                    </n-tag>
                    <span class="meta-genre">{{ book.genre || '未分类' }}</span>
                  </div>
                  <div class="card-stats" v-if="book.chapter_count || book.word_count">
                    <template v-if="book.chapter_count">
                      <span>{{ book.chapter_count }} 章</span>
                    </template>
                    <template v-if="book.word_count">
                      <span>{{ formatWordCount(book.word_count) }}</span>
                    </template>
                  </div>
                  <div class="card-actions" @click.stop>
                    <n-checkbox
                      :checked="selectedBooks.includes(book.slug)"
                      @update:checked="(val: boolean) => toggleBookSelection(book.slug, val)"
                    />
                    <n-popconfirm
                      positive-text="删除"
                      negative-text="取消"
                      @positive-click="() => handleDeleteBook(book.slug)"
                    >
                      <template #trigger>
                        <n-button
                          quaternary
                          circle
                          size="tiny"
                          type="error"
                          :loading="deletingSlug === book.slug"
                          aria-label="删除书目"
                        >
                          <template #icon>
                            <n-icon><IconTrash /></n-icon>
                          </template>
                        </n-button>
                      </template>
                      将删除「{{ book.title }}」及本地全部章节与设定，且不可恢复。确定删除吗？
                    </n-popconfirm>
                  </div>
                </div>
              </div>

              <!-- 折叠提示 + 查看全部按钮 -->
              <div v-if="hiddenCount > 0 && !searchQuery" class="books-fold-bar">
                <span class="fold-hint">还有 {{ hiddenCount }} 本书未展示</span>
                <n-button size="small" type="primary" secondary round @click="showAllModal = true">
                  查看全部 {{ filteredBooks.length }} 本
                </n-button>
              </div>
            </div>
          </template>
        </section>

        <!-- 底部版权 -->
        <footer class="home-footer">
          <span class="footer-brand">PlotPilot</span>
          <span class="footer-sep">·</span>
          <span class="footer-sub">墨枢</span>
          <span class="footer-text">由 PlotPilot（墨枢）团队倾力开发</span>
          <a class="footer-link" href="https://www.douyin.com/user/MS4wLjABAAAA91472902104" target="_blank" rel="noopener noreferrer">
            抖音：林亦 91472902104
          </a>
          <span class="footer-text">每晚 9 点随缘直播</span>
        </footer>
      </div>
    </div>

    <!-- Batch Delete Confirm Modal -->
    <n-modal v-model:show="showBatchDeleteConfirm" preset="confirm" type="error" title="确认批量删除">
      <template #default>
        确定要删除选中的 <strong>{{ selectedBooks.length }}</strong> 本书籍吗？此操作不可恢复。
      </template>
      <template #action>
        <n-space>
          <n-button @click="showBatchDeleteConfirm = false">取消</n-button>
          <n-button type="error" :loading="batchDeleting" @click="handleBatchDelete">
            确认删除
          </n-button>
        </n-space>
      </template>
    </n-modal>

    <!-- 新书向导：仅挂载一次且 show 恒为 true，避免「先关再开」的双过渡（原 newNovelId + showSetupGuide 分步更新导致） -->
    <NovelSetupGuide
      v-if="setupWizard"
      :key="setupWizard.novelId"
      :novel-id="setupWizard.novelId"
      :target-chapters="setupWizard.targetChapters"
      :show="true"
      @update:show="(open) => { if (!open) setupWizard = null }"
      @complete="handleSetupComplete"
      @skip="handleSetupSkip"
    />

    <!-- LLM Settings Modal -->
    <LLMSettingsModal v-model:show="showLLMSettings" />

    <!-- 查看全部书目弹窗 -->
    <n-modal
      v-model:show="showAllModal"
      preset="card"
      title=""
      :style="{ width: '92vw', maxWidth: '960px', height: '80vh', marginTop: '8vh' }"
      :bordered="true"
      :segmented="{ content: true, footer: 'soft' }"
      :mask-closable="true"
      :close-on-esc="true"
    >
      <template #header>
        <div class="all-books-header">
          <span class="all-books-header-title">全部书目</span>
          <n-tag size="small" type="info" :bordered="false">
            {{ filteredBooks.length }} 本
          </n-tag>
        </div>
      </template>

      <div class="all-books-body">
        <n-input
          v-model:value="modalSearchQuery"
          placeholder="搜索书目…"
          clearable
          size="small"
          style="max-width: 280px; margin-bottom: 16px"
        >
          <template #prefix>
            <n-icon><IconSearch /></n-icon>
          </template>
        </n-input>
        <div class="all-books-grid">
          <div
            v-for="book in modalFilteredBooks"
            :key="book.slug"
            class="book-card"
            @click="navigateToBook(book.slug); showAllModal = false"
          >
            <div class="card-top">
              <span class="book-dot" :class="`dot-${book.stage}`"></span>
              <span class="book-card-title">{{ book.title }}</span>
            </div>
            <div class="card-meta">
              <n-tag :type="getStageType(book.stage)" size="small" round borderable>
                {{ book.stage_label }}
              </n-tag>
              <span class="meta-genre">{{ book.genre || '未分类' }}</span>
            </div>
            <div class="card-stats" v-if="book.chapter_count || book.word_count">
              <template v-if="book.chapter_count">
                <span>{{ book.chapter_count }} 章</span>
              </template>
              <template v-if="book.word_count">
                <span>{{ formatWordCount(book.word_count) }}</span>
              </template>
            </div>
            <div class="card-actions" @click.stop>
              <n-popconfirm
                positive-text="删除"
                negative-text="取消"
                @positive-click="() => handleDeleteBook(book.slug)"
              >
                <template #trigger>
                  <n-button
                    quaternary
                    circle
                    size="tiny"
                    type="error"
                    :loading="deletingSlug === book.slug"
                    aria-label="删除书目"
                  >
                    <template #icon>
                      <n-icon><IconTrash /></n-icon>
                    </template>
                  </n-button>
                </template>
                将删除「{{ book.title }}」及本地全部章节与设定，且不可恢复。确定删除吗？
              </n-popconfirm>
            </div>
          </div>
        </div>
      </div>
    </n-modal>
  </div>
</template>

<script setup lang="ts">
import { h, ref, onMounted, computed, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { useMessage, NIcon } from 'naive-ui'
import { novelApi, type NovelDTO } from '../api/novel'
import { isWizardCompleted } from '@/utils/wizardStageCache'
import StatsSidebar from '@/components/stats/StatsSidebar.vue'
import NovelSetupGuide from '@/components/onboarding/NovelSetupGuide.vue'
import LLMSettingsModal from '@/components/LLMSettingsModal.vue'
import MarketTaxonomyPicker from '@/components/taxonomy/MarketTaxonomyPicker.vue'
import { parseGenreWorldFromPremise } from '@/utils/premisePresets'
import { useStatsStore } from '@/stores/statsStore'

// Icons
const IconSpark = () =>
  h('svg', { xmlns: 'http://www.w3.org/2000/svg', viewBox: '0 0 24 24', width: '1em', height: '1em' },
    h('path', { fill: 'currentColor', d: 'M13 2L3 14h8l-1 8 10-12h-8l1-8z' }))

const IconSearch = () =>
  h('svg', { xmlns: 'http://www.w3.org/2000/svg', viewBox: '0 0 24 24', width: '1em', height: '1em' },
    h('path', { fill: 'currentColor', d: 'M15.5 14h-.79l-.28-.27A6.471 6.471 0 0 0 16 9.5 6.5 6.5 0 1 0 9.5 16c1.61 0 3.09-.59 4.23-1.57l.27.28v.79l5 4.99L20.49 19l-4.99-5zm-6 0C7.01 14 5 11.99 5 9.5S7.01 5 9.5 5 14 7.01 14 9.5 11.99 14 9.5 14z' }))

const IconTrash = () =>
  h('svg', { xmlns: 'http://www.w3.org/2000/svg', viewBox: '0 0 24 24', width: '1em', height: '1em' },
    h('path', { fill: 'currentColor', d: 'M6 19c0 1.1.9 2 2 2h8c1.1 0 2-.9 2-2V7H6v12zM19 4h-3.5l-1-1h-5l-1 1H5v2h14V4z' }))

const IconChevronDown = () =>
  h('svg', { xmlns: 'http://www.w3.org/2000/svg', viewBox: '0 0 24 24', width: '1em', height: '1em' },
    h('path', { fill: 'currentColor', d: 'M7.41 8.59L12 13.17l4.59-4.58L18 10l-6 6-6-6 1.41-1.41z' }))

const IconChevronUp = () =>
  h('svg', { xmlns: 'http://www.w3.org/2000/svg', viewBox: '0 0 24 24', width: '1em', height: '1em' },
    h('path', { fill: 'currentColor', d: 'M7.41 15.41L12 10.83l4.59 4.58L18 14l-6-6-6 6 1.41 1.41z' }))

/** 与工作台顶栏「设置」一致，打开主题设置弹窗 */
const IconThemeSettings = () =>
  h('svg', { xmlns: 'http://www.w3.org/2000/svg', viewBox: '0 0 24 24', width: '1em', height: '1em' },
    h('path', {
      fill: 'currentColor',
      d: 'M19.14 12.94c.04-.3.06-.61.06-.94 0-.32-.02-.64-.07-.94l2.03-1.58a.49.49 0 0 0 .12-.61l-1.92-3.32a.49.49 0 0 0-.59-.22l-2.39.96c-.5-.38-1.03-.7-1.62-.94l-.36-2.54a.484.484 0 0 0-.48-.41h-3.84c-.24 0-.43.17-.47.41l-.36 2.54c-.59.24-1.13.57-1.62.94l-2.39-.96a.49.49 0 0 0-.59.22L2.74 8.87c-.12.21-.08.47.12.61l2.03 1.58c-.05.3-.09.63-.09.94s.02.64.07.94l-2.03 1.58a.49.49 0 0 0-.12.61l1.92 3.32c.12.22.37.29.59.22l2.39-.96c.5.38 1.03.7 1.62.94l.36 2.54c.05.24.24.41.48.41h3.84c.24 0 .44-.17.47-.41l.36-2.54c.59-.24 1.13-.56 1.62-.94l2.39.96c.22.08.47 0 .59-.22l1.92-3.32c.12-.22.07-.47-.12-.61l-2.01-1.58zM12 15.6A3.6 3.6 0 1 1 12 8.4a3.6 3.6 0 0 1 0 7.2z',
    }))

interface BookListItem {
  slug: string
  title: string
  stage: string
  stage_label: string
  genre: string
  chapter_count?: number
  word_count?: number
}

const router = useRouter()
const message = useMessage()
const statsStore = useStatsStore()

const createInputRef = ref<any>(null)
const showAdvanced = ref(false)
const creating = ref(false)
const loading = ref(false)

const SIDEBAR_COLLAPSED_KEY = 'plotpilot_sidebar_collapsed'
const sidebarCollapsed = ref(localStorage.getItem(SIDEBAR_COLLAPSED_KEY) === 'true')

function handleSidebarCollapsedChange(isCollapsed: boolean) {
  sidebarCollapsed.value = isCollapsed
}
const books = ref<BookListItem[]>([])
const searchQuery = ref('')
const deletingSlug = ref<string | null>(null)
const showLLMSettings = ref(false)
const showAllModal = ref(false)
const modalSearchQuery = ref('')
/** 有值时挂载向导；与 show 分离，挂载后始终 :show="true"，避免 Modal 先 false 再 true 闪烁 */
const setupWizard = ref<{ novelId: string; targetChapters: number } | null>(null)

// Batch delete
const selectedBooks = ref<string[]>([])
const showBatchDeleteConfirm = ref(false)
const batchDeleting = ref(false)

const PREMISE_MAX_LEN = 2000

const newBook = ref({
  title: '',
  premise: '',
  genre: '',
  worldPreset: '',
  chapters: 100,  // 默认 100 章
  words: 2500,
})

/** V1 目标篇幅档（与高级自定义二选一） */
const lengthTier = ref<'short' | 'standard' | 'epic'>('standard')
const lengthTierOptions = [
  {
    value: 'short' as const,
    title: 'A · 短篇快穿 / 脑洞文',
    hint: '约 30 万字（按约 2000 字/章推导章数）',
  },
  {
    value: 'standard' as const,
    title: 'B · 标准商业连载',
    hint: '约 100 万字',
  },
  {
    value: 'epic' as const,
    title: 'C · 宏大史诗巨著',
    hint: '约 300 万字',
  },
]

const filteredBooks = computed(() => {
  if (!searchQuery.value.trim()) {
    return books.value
  }
  const query = searchQuery.value.toLowerCase()
  return books.value.filter(
    book =>
      book.title.toLowerCase().includes(query) ||
      (book.genre && book.genre.toLowerCase().includes(query))
  )
})

/** 页面主区域最多展示的书目数量 */
const MAX_VISIBLE_BOOKS = 6

/** 页面实际展示的书目（截断，不滚动） */
const displayBooks = computed(() => {
  if (searchQuery.value.trim()) return filteredBooks.value
  return filteredBooks.value.slice(0, MAX_VISIBLE_BOOKS)
})

/** 被隐藏的数量 */
const hiddenCount = computed(() => {
  if (searchQuery.value.trim()) return 0
  return Math.max(0, filteredBooks.value.length - MAX_VISIBLE_BOOKS)
})

/** 弹窗内的过滤 */
const modalFilteredBooks = computed(() => {
  if (!modalSearchQuery.value.trim()) return filteredBooks.value
  const q = modalSearchQuery.value.toLowerCase()
  return filteredBooks.value.filter(
    book =>
      book.title.toLowerCase().includes(q) ||
      (book.genre && book.genre.toLowerCase().includes(q))
  )
})

const isAllSelected = computed(() => {
  return filteredBooks.value.length > 0 && selectedBooks.value.length === filteredBooks.value.length
})

const isPartialSelected = computed(() => {
  return selectedBooks.value.length > 0 && selectedBooks.value.length < filteredBooks.value.length
})

const fetchBooks = async () => {
  loading.value = true
  try {
    const novels = await novelApi.listNovels()
    books.value = novels.map((novel: NovelDTO) => {
      const fromPrefix = parseGenreWorldFromPremise(novel.premise || '').genre
      const g = novel.locked_genre?.trim() || fromPrefix || ''
      return {
        slug: novel.id,
        title: novel.title,
        stage: novel.stage,
        stage_label: getStageLabel(novel.stage),
        genre: g,
        chapter_count: novel.chapters?.length || 0,
        word_count: novel.total_word_count,
      }
    })
  } catch {
    message.error('加载失败')
  } finally {
    loading.value = false
  }
}

const getStageLabel = (stage: string): string => {
  const labels: Record<string, string> = {
    planning: '规划中',
    writing: '写作中',
    reviewing: '审稿中',
    completed: '已完成',
  }
  return labels[stage] || stage
}

const formatWordCount = (count: number): string => {
  if (count >= 10000) {
    return (count / 10000).toFixed(1) + '万字'
  }
  return count + '字'
}

const handleCreate = async () => {
  if (!newBook.value.premise.trim()) {
    message.warning('请输入核心梗概')
    return
  }
  if (!newBook.value.genre.trim()) {
    message.warning('请在「市场分区」中选定大类与主题')
    return
  }
  if (!newBook.value.worldPreset.trim()) {
    message.warning('请填写或确认世界观基调')
    return
  }

  creating.value = true
  try {
    const title = newBook.value.title || newBook.value.premise.substring(0, 20)
    const novelId = `novel-${Date.now()}`

    const base = {
      novel_id: novelId,
      title: title,
      author: '作者',
      premise: newBook.value.premise.trim(),
      genre: newBook.value.genre,
      world_preset: newBook.value.worldPreset,
    }
    const result = await novelApi.createNovel(
      showAdvanced.value
        ? {
            ...base,
            target_chapters: newBook.value.chapters || 100,
            target_words_per_chapter: newBook.value.words || 2500,
          }
        : {
            ...base,
            length_tier: lengthTier.value,
            target_chapters: 0,
          }
    )
    message.success('创建成功')

    setupWizard.value = {
      novelId: result.id,
      targetChapters: result.target_chapters,
    }
  } catch (error: any) {
    message.error(error.response?.data?.detail || '创建失败')
  } finally {
    creating.value = false
  }
}

const handleSetupComplete = () => {
  const id = setupWizard.value?.novelId
  setupWizard.value = null
  if (id) router.push(`/book/${id}/workbench`)
}

const handleSetupSkip = () => {
  const id = setupWizard.value?.novelId
  setupWizard.value = null
  if (id) router.push(`/book/${id}/workbench`)
}

const navigateToBook = (novelId: string) => {
  // 未完成向导的书重新打开向导
  if (!isWizardCompleted(novelId)) {
    // 查找该书的 target_chapters
    const novel = books.value.find(b => b.slug === novelId)
    setupWizard.value = {
      novelId,
      targetChapters: 100, // 默认值，向导内部会从 API 获取真实值
    }
    return
  }
  router.push(`/book/${novelId}/workbench`)
}

const handleDeleteBook = async (slug: string) => {
  deletingSlug.value = slug
  try {
    await novelApi.deleteNovel(slug)
    message.success('书目已删除')
    books.value = books.value.filter(b => b.slug !== slug)
    selectedBooks.value = selectedBooks.value.filter(s => s !== slug)
    await statsStore.loadGlobalStats(true)
  } catch (error: any) {
    const detail = error?.response?.data?.detail
    message.error(typeof detail === 'string' ? detail : '删除失败')
  } finally {
    deletingSlug.value = null
  }
}

const toggleBookSelection = (slug: string, selected: boolean) => {
  if (selected) {
    if (!selectedBooks.value.includes(slug)) {
      selectedBooks.value.push(slug)
    }
  } else {
    selectedBooks.value = selectedBooks.value.filter(s => s !== slug)
  }
}

const toggleSelectAll = (checked: boolean) => {
  if (checked) {
    selectedBooks.value = filteredBooks.value.map(b => b.slug)
  } else {
    selectedBooks.value = []
  }
}

const handleBatchDelete = async () => {
  batchDeleting.value = true
  try {
    let successCount = 0
    let failCount = 0
    
    for (const slug of selectedBooks.value) {
      try {
        await novelApi.deleteNovel(slug)
        successCount++
      } catch {
        failCount++
      }
    }
    
    if (successCount > 0) {
      message.success(`成功删除 ${successCount} 本书目`)
      books.value = books.value.filter(b => !selectedBooks.value.includes(b.slug))
      selectedBooks.value = []
      await statsStore.loadGlobalStats(true)
    }
    if (failCount > 0) {
      message.warning(`${failCount} 本删除失败`)
    }
    showBatchDeleteConfirm.value = false
  } finally {
    batchDeleting.value = false
  }
}

const focusCreateInput = () => {
  nextTick(() => {
    createInputRef.value?.focus()
  })
  // Scroll to top
  window.scrollTo({ top: 0, behavior: 'smooth' })
}

const handleRefreshList = async () => {
  await fetchBooks()
  message.success('列表已刷新')
}

const getStageType = (stage: string) => {
  const map: Record<string, string> = {
    planning: 'info',
    writing: 'warning',
    reviewing: 'default',
    completed: 'success',
  }
  return map[stage] || 'default'
}

onMounted(() => {
  fetchBooks()
})
</script>

<style scoped>
.home {
  display: flex;
  min-height: 100vh;
  height: 100vh;
  overflow: hidden;
}

.home-content {
  flex: 1;
  min-height: 0;
  margin-left: 300px;
  padding: 32px;
  position: relative;
  overflow-x: hidden;
  overflow-y: auto;
  -webkit-overflow-scrolling: touch;
  transition: margin-left 0.22s cubic-bezier(0.4, 0, 0.2, 1);
}

.home-content.sidebar-collapsed {
  margin-left: 52px;
}

/* 顶栏：与 StatsTopBar 同款渐变，AI 控制台 / 提示词广场 / 设置 */

.home-bg {
  position: absolute;
  inset: 0;
  background:
    radial-gradient(ellipse 110% 80% at 50% -30%, var(--color-brand-light), transparent 55%),
    radial-gradient(ellipse 60% 50% at 100% 20%, rgba(14, 165, 233, 0.12), transparent 45%),
    radial-gradient(ellipse 50% 40% at 0% 60%, var(--color-gold-dim), transparent 50%),
    linear-gradient(180deg, var(--app-page-bg) 0%, var(--app-surface-subtle) 45%, var(--app-page-bg) 100%);
  z-index: 0;
}

.container {
  position: relative;
  z-index: 1;
  max-width: 1200px;
  margin: 0 auto;
}

.header {
  position: relative;
  text-align: center;
  margin-bottom: 40px;
  animation: fade-up 0.55s ease both;
}

.header-theme-btn {
  position: absolute;
  top: 0;
  right: 0;
  z-index: 2;
  color: var(--app-text-secondary);
}

.header-theme-btn:hover {
  color: var(--color-brand, #4f46e5);
}

.header-content {
  padding: 0 44px;
}

.title {
  font-size: clamp(2rem, 4vw, 2.5rem);
  font-weight: 700;
  margin: 0 0 12px;
  letter-spacing: -0.03em;
  color: var(--app-text-primary);
}

.subtitle {
  font-size: 1.05rem;
  color: var(--app-text-secondary);
  margin: 0;
  font-weight: 400;
}


.create-card {
  margin-bottom: 32px;
  border-radius: 16px;
  box-shadow: 0 4px 20px rgba(15, 23, 42, 0.06);
  animation: fade-up 0.55s ease 0.08s both;
}

.create-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.create-title-wrap {
  display: flex;
  align-items: center;
  gap: 10px;
}

.create-icon {
  font-size: 20px;
}

.create-title {
  margin: 0;
  font-size: 17px;
  font-weight: 600;
}

.premise-input :deep(textarea) {
  font-size: 15px;
  line-height: 1.6;
}

.taxonomy-block {
  margin-top: 4px;
  padding: 14px 16px;
  border-radius: 12px;
  background: rgba(15, 23, 42, 0.02);
  border: 1px solid var(--app-border);
}
.taxonomy-block-head {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-bottom: 12px;
}
.taxonomy-block-title {
  font-size: 13px;
  font-weight: 700;
  color: var(--app-text-primary);
  letter-spacing: 0.04em;
}
.taxonomy-block-sub {
  font-size: 12px;
  color: var(--app-text-muted);
  line-height: 1.45;
}

.length-tier-block {
  margin-top: 8px;
  padding: 4px 0 4px;
}

.length-tier-label {
  font-size: 13px;
  color: var(--app-text-secondary);
  margin-bottom: 10px;
}

.length-tier-space {
  width: 100%;
}

.length-tier-group :deep(.n-radio) {
  align-items: flex-start;
}

.length-tier-radio {
  flex: 1 1 200px;
  min-width: min(200px, 100%);
}

.length-tier-option-inner {
  display: flex;
  flex-direction: column;
  gap: 4px;
  align-items: flex-start;
  max-width: 280px;
}

.length-tier-title {
  font-weight: 600;
  line-height: 1.35;
}

.length-tier-hint {
  font-size: 12px;
  color: var(--app-text-muted);
  line-height: 1.45;
}

.advanced-settings {
  padding: 16px;
  background: rgba(79, 70, 229, 0.04);
  border-radius: 12px;
  border: 1px solid rgba(79, 70, 229, 0.1);
}

.w-full {
  width: 100%;
}

.books-section {
  background: var(--app-surface);
  border-radius: 16px;
  padding: 28px;
  box-shadow: 0 4px 20px rgba(15, 23, 42, 0.04);
  animation: fade-up 0.55s ease 0.14s both;
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 16px;
  margin-bottom: 20px;
  flex-wrap: wrap;
}

.section-left {
  display: flex;
  align-items: center;
  gap: 12px;
}

.section-title {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
  color: var(--app-text-primary);
}

.book-count {
  font-size: 13px;
  color: var(--app-text-muted);
  background: var(--app-surface-subtle);
  padding: 4px 10px;
  border-radius: 12px;
}

.section-right {
  display: flex;
  align-items: center;
  gap: 12px;
}

.search-input {
  width: 240px;
}

.selection-bar {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 12px 16px;
  background: var(--app-surface-subtle);
  border-radius: 10px;
  margin-bottom: 20px;
}

.selection-hint {
  font-size: 13px;
  color: var(--app-text-muted);
}

.loading-state,
.empty-state,
.no-results-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 72px 20px;
  color: var(--app-text-muted);
}

.loading-state p {
  margin-top: 16px;
  font-size: 14px;
}

.empty-state {
  gap: 16px;
}

.empty-illustration {
  width: 100px;
  height: 100px;
  background: linear-gradient(135deg, var(--app-surface-subtle) 0%, var(--app-border) 100%);
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
}

.empty-icon {
  font-size: 48px;
}

.empty-title {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
  color: var(--app-text-primary);
}

.empty-desc {
  margin: 0;
  font-size: 14px;
  color: var(--app-text-muted);
}

.no-results-state {
  gap: 12px;
}

.no-results-icon {
  font-size: 40px;
}

.no-results-state p {
  margin: 0;
  font-size: 14px;
}

/* ── 书目：单行横排，多本时横向滚动 ── */
.books-list-wrap {
  display: flex;
  flex-direction: column;
  gap: 0;
}

.books-grid {
  display: flex;
  flex-direction: row;
  flex-wrap: nowrap;
  gap: 16px;
  overflow-x: auto;
  overflow-y: hidden;
  padding-bottom: 6px;
  -webkit-overflow-scrolling: touch;
  scrollbar-width: thin;
}

/* 卡片（固定宽度，保证单行横滑） */
.book-card {
  position: relative;
  flex: 0 0 auto;
  width: 260px;
  max-width: min(260px, 82vw);
  display: flex;
  flex-direction: column;
  padding: 20px;
  background: var(--app-surface);
  border: 1px solid var(--app-border);
  border-radius: 14px;
  cursor: pointer;
  transition: all 0.2s ease;
  animation: fade-up 0.35s ease both;
  overflow: hidden;
}

.book-card:hover {
  border-color: var(--color-brand, #4f46e5);
  box-shadow: 0 4px 16px rgba(79, 70, 229, 0.1);
  transform: translateY(-2px);
}

.book-card.is-selected {
  border-color: var(--color-brand, #4f46e5);
  background: var(--color-brand-light, rgba(79, 70, 229, 0.04));
}

/* 阶段状态小圆点 */
.book-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  flex-shrink: 0;
  display: inline-block;
}

.book-dot.dot-planning { background: #3b82f6; }
.book-dot.dot-writing { background: #f59e0b; }
.book-dot.dot-reviewing { background: #8b5cf6; }
.book-dot.dot-completed { background: #10b981; }

/* 卡片顶部：标题 + 圆点 */
.card-top {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
}

.book-card-title {
  font-size: 15px;
  font-weight: 650;
  color: var(--app-text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  line-height: 1.3;
}

/* 卡片元信息行：标签 + 类型 */
.card-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
  flex-wrap: wrap;
}

.meta-genre {
  font-size: 12px;
  color: var(--app-text-muted);
}

/* 卡片统计信息 */
.card-stats {
  display: flex;
  gap: 10px;
  font-size: 12px;
  color: var(--app-text-muted);
  margin-bottom: 12px;
  flex: 1;
}

/* 卡片操作按钮 */
.card-actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 6px;
  opacity: 0;
  transition: opacity 0.18s ease;
  padding-top: 4px;
  border-top: 1px solid transparent;
}

.book-card:hover .card-actions {
  opacity: 1;
}

/* 折叠提示栏 */
.books-fold-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 12px;
  padding: 12px 16px;
  background: var(--color-brand-light, rgba(79, 70, 229, 0.05));
  border: 1px dashed var(--color-brand-border, rgba(79, 70, 229, 0.2));
  border-radius: 10px;
}

.fold-hint {
  font-size: 13px;
  color: var(--app-text-secondary);
}

@keyframes fade-up {
  from {
    opacity: 0;
    transform: translateY(12px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

/* Responsive */
@media (max-width: 1200px) {
  .home-content {
    padding: 24px;
  }


}

/* ── 底部版权 ──────────────────────────────── */
.home-footer {
  position: relative;
  z-index: 1;
  text-align: center;
  padding: 28px 20px 32px;
  margin-top: 40px;
  border-top: 1px solid var(--app-border);
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  flex-wrap: wrap;
  font-size: 12px;
  color: var(--app-text-muted);
  line-height: 1.6;
}

.footer-brand {
  font-weight: 700;
  color: var(--color-gold);
  letter-spacing: 0.03em;
}

.footer-sep {
  opacity: 0.4;
}

.footer-sub {
  font-weight: 600;
  color: var(--color-gold-light);
  opacity: 0.8;
}

.footer-text {
  color: var(--app-text-muted);
}

.footer-link {
  color: var(--color-gold);
  text-decoration: none;
  font-weight: 600;
  border-bottom: 1px dashed var(--color-gold-border);
  transition: all 0.2s ease;
  white-space: nowrap;
}

.footer-link:hover {
  color: var(--color-gold-light);
  border-bottom-style: solid;
  box-shadow: 0 0 8px var(--color-glow-gold);
}

@media (max-width: 768px) {
  .home-content {
    margin-left: 0;
    padding: 16px;
  }

  .section-header {
    flex-direction: column;
    align-items: stretch;
  }
  
  .section-right {
    flex-direction: column;
  }
  
  .search-input {
    width: 100%;
  }

  .card-actions {
    opacity: 1; /* 移动端始终显示操作按钮 */
  }
}

/* ── 查看全部书目弹窗样式 ── */
.all-books-header {
  display: flex;
  align-items: center;
  gap: 10px;
}

.all-books-header-title {
  font-size: 17px;
  font-weight: 700;
  color: var(--app-text-primary);
}

.all-books-body {
  height: calc(80vh - 100px);
  overflow-y: auto;
  padding-right: 4px;
}

.all-books-grid {
  max-height: none;
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: 12px;
}
</style>
