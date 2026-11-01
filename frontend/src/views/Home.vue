<template>
  <div class="home">
    <StatsSidebar
      @create-book="openCreateModal"
      @refresh-list="handleRefreshList"
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
            aria-label="应用设置"
            @click="appSettingsShell.open()"
          >
            <template #icon>
              <n-icon :component="IconThemeSettings" :size="22" />
            </template>
          </n-button>
          <div class="header-content">
            <!-- 1. 眉标：定位语，小字距零缀留白 -->
            <div class="brand-eyebrow">长篇叙事工作台 · NARRATIVE WORKBENCH</div>
            <!-- 2. 水平 lockup：[印章][PlotPilot 字标][墨枢胶囊]，与启动屏/登录页同构 -->
            <div class="brand-lockup">
              <BrandMark :size="56" class="brand-seal" />
              <div class="brand-title">PlotPilot</div>
              <span class="brand-alias">墨枢</span>
            </div>
            <!-- 3. 副标题：价值主张，独立收在 lockup 下方 -->
            <p class="subtitle">
              以梗概与类型开局，选定目标篇幅；宏观结构、幕次与节拍由后台自动编排，你专注把故事写下去即可。
            </p>
          </div>
        </header>

        <!-- Create Card -->

        <!-- Books Section -->
        <section class="books-section">
          <div class="section-header">
            <div class="section-left">
              <h2 class="section-title">我的书目</h2>
              <span class="book-count" v-if="!loading">{{ filteredBooks.length }} 本</span>
            </div>
            <div class="section-right">
              <n-button tertiary round @click="showLibrary = true" class="library-btn">
                <template #icon>
                  <n-icon><IconLibrary /></n-icon>
                </template>
                全部书目
              </n-button>
              <n-button type="primary" round @click="openCreateModal" class="new-book-btn">
                <template #icon>
                  <n-icon><IconSpark /></n-icon>
                </template>
                新建书目
              </n-button>
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
            <p class="empty-desc">点「新建书目」，用一段梗概开启创作之旅</p>
            <n-button type="primary" size="large" round @click="openCreateModal">
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

          <!-- 书架舞台：自 pw fe 移植的 3D 书架（书脊朝外，选中抽出翻面） -->
          <!-- 舞台不带壳（标题/搜索/新建由 section-header 承担），搜索命中时给一行提示 -->
          <template v-else>
            <p v-if="searchQuery" class="search-result-hint">
              搜索「{{ searchQuery }}」命中 {{ filteredBooks.length }} 本
            </p>
            <ProjectDeck
              :books="filteredBooks"
              :loading="loading"
              :busy="Boolean(deletingSlug)"
              @open="navigateToBook"
              @delete="requestDeleteBooks([$event])"
              @new-book="openCreateModal"
            />
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

    <!-- 新建书目弹层：大表单从主页搬进对话框，主页面保持一屏（header + 书目网格） -->
    <n-modal
      v-model:show="createModalOpen"
      preset="card"
      class="create-modal"
      :style="{ width: 'min(760px, 94vw)' }"
      :bordered="false"
      :mask-closable="!creating"
      :close-on-esc="!creating"
      :segmented="{ footer: 'soft' }"
    >
      <template #header>
        <div class="create-title-wrap">
          <n-icon :component="IconSpark" :size="18" class="create-icon" />
          <span class="create-title">新建书目</span>
        </div>
      </template>
      <div class="create-modal-body">
        <n-space vertical :size="20">
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
              v-model:storyStructure="newBook.storyStructure"
              v-model:pacingControl="newBook.pacingControl"
              v-model:writingStyle="newBook.writingStyle"
              v-model:specialRequirements="newBook.specialRequirements"
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
                  <n-input-number v-model:value="newBook.words" :min="500" :max="20000" :step="500" class="w-full" />
                </n-form-item>
              </n-gi>
            </n-grid>
          </div>
        </n-space>
      </div>
      <template #action>
        <div class="create-modal-footer">
          <n-button text type="primary" :disabled="creating" @click="showAdvanced = !showAdvanced">
            <template #icon>
              <n-icon><component :is="showAdvanced ? IconChevronUp : IconChevronDown" /></n-icon>
            </template>
            {{ showAdvanced ? '收起高级' : '高级（自定义章数/每章字数）' }}
          </n-button>
          <n-button
            type="primary"
            size="large"
            round
            :loading="creating"
            :disabled="!newBook.premise.trim() || !newBook.genre.trim() || !newBook.worldPreset.trim() || !newBook.storyStructure.trim() || !newBook.pacingControl.trim() || !newBook.writingStyle.trim() || !newBook.specialRequirements.trim()"
            @click="handleCreate"
          >
            <template #icon>
              <n-icon><IconSpark /></n-icon>
            </template>
            建档并进入工作台
          </n-button>
        </div>
      </template>
    </n-modal>

    <!-- 书目录弹层（自 pw fe HomeLibraryModal 移植）：搜索/批量管理/删除 -->
    <LibraryModal
      v-model:show="showLibrary"
      :books="books"
      :deleting-slug="deletingSlug"
      @open="navigateToBook"
      @request-delete="requestDeleteBooks"
      @new-book="openCreateModal"
    />

    <!-- 删除确认（书架卡片/目录弹层触发，支持单本与批量） -->
    <n-modal
      v-model:show="showDeleteConfirm"
      preset="confirm"
      type="error"
      :title="`删除书目${pendingDeleteBooks.length > 1 ? `（${pendingDeleteBooks.length} 本）` : ''}`"
    >
      <template #default>
        <template v-if="pendingDeleteBooks.length === 1">
          将删除 <strong>《{{ pendingDeleteBooks[0].title }}》</strong> 及本地全部章节与设定，此操作不可恢复。
        </template>
        <template v-else>
          将删除 <strong>{{ pendingDeleteBooks.length }}</strong> 本书（{{
            pendingDeleteBooks.slice(0, 3).map(b => `《${b.title}》`).join('、')
          }}<template v-if="pendingDeleteBooks.length > 3">等</template>）及各自全部章节与设定，此操作不可恢复。
        </template>
      </template>
      <template #action>
        <n-space>
          <n-button @click="showDeleteConfirm = false">取消</n-button>
          <n-button type="error" :loading="deleting" @click="confirmDeleteBooks">确认删除</n-button>
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

  </div>
</template>

<script setup lang="ts">
import { defineAsyncComponent, h, ref, onMounted, computed, nextTick, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useMessage, NIcon } from 'naive-ui'
import { novelApi, type NovelDTO } from '../api/novel'
import { isWizardCompleted } from '@/utils/wizardStageCache'
import StatsSidebar from '@/components/stats/StatsSidebar.vue'
import BrandMark from '@/components/brand/BrandMark.vue'
import ProjectDeck, { type DeckBookItem } from '@/components/home/ProjectDeck.vue'
import LibraryModal from '@/components/home/LibraryModal.vue'
import { useAppSettingsShellStore } from '@/stores/appSettingsShellStore'
import { parseGenreWorldFromPremise } from '@/utils/premisePresets'
import { useStatsStore } from '@/stores/statsStore'
import { storageKeys } from '@/config/storageKeys'
import { readStorageBoolean } from '@/utils/storage'
import { formatApiError } from '@/utils/apiError'
import {
  NOVEL_LENGTH_TIER_OPTIONS,
  getNovelStageLabel,
  type NovelLengthTier,
} from '@/domain/novel'

const MarketTaxonomyPicker = defineAsyncComponent(
  () => import('@/components/taxonomy/MarketTaxonomyPicker.vue'),
)
const NovelSetupGuide = defineAsyncComponent(
  () => import('@/components/onboarding/NovelSetupGuide.vue'),
)

// Icons
const IconSpark = () =>
  h('svg', { xmlns: 'http://www.w3.org/2000/svg', viewBox: '0 0 24 24', width: '1em', height: '1em' },
    h('path', { fill: 'currentColor', d: 'M13 2L3 14h8l-1 8 10-12h-8l1-8z' }))

const IconLibrary = () =>
  h('svg', { xmlns: 'http://www.w3.org/2000/svg', viewBox: '0 0 24 24', width: '1em', height: '1em' },
    h('path', { fill: 'currentColor', d: 'M4 6H2v14c0 1.1.9 2 2 2h14v-2H4V6zm16-4H8c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2zm-9 12V6h7v2h-5v2h5v2h-5v2h5v2h-7z' }))

const IconSearch = () =>
  h('svg', { xmlns: 'http://www.w3.org/2000/svg', viewBox: '0 0 24 24', width: '1em', height: '1em' },
    h('path', { fill: 'currentColor', d: 'M15.5 14h-.79l-.28-.27A6.471 6.471 0 0 0 16 9.5 6.5 6.5 0 1 0 9.5 16c1.61 0 3.09-.59 4.23-1.57l.27.28v.79l5 4.99L20.49 19l-4.99-5zm-6 0C7.01 14 5 11.99 5 9.5S7.01 5 9.5 5 14 7.01 14 9.5 11.99 14 9.5 14z' }))

const IconChevronDown = () =>
  h('svg', { xmlns: 'http://www.w3.org/2000/svg', viewBox: '0 0 24 24', width: '1em', height: '1em' },
    h('path', { fill: 'currentColor', d: 'M7.41 8.59L12 13.17l4.59-4.58L18 10l-6 6-6-6 1.41-1.41z' }))

const IconChevronUp = () =>
  h('svg', { xmlns: 'http://www.w3.org/2000/svg', viewBox: '0 0 24 24', width: '1em', height: '1em' },
    h('path', { fill: 'currentColor', d: 'M7.41 15.41L12 10.83l4.59 4.58L18 14l-6-6-6 6 1.41 1.41z' }))

/** 与工作台顶栏一致：打开应用设置（默认「外观与主题」分区） */
const IconThemeSettings = () =>
  h('svg', { xmlns: 'http://www.w3.org/2000/svg', viewBox: '0 0 24 24', width: '1em', height: '1em' },
    h('path', {
      fill: 'currentColor',
      d: 'M19.14 12.94c.04-.3.06-.61.06-.94 0-.32-.02-.64-.07-.94l2.03-1.58a.49.49 0 0 0 .12-.61l-1.92-3.32a.49.49 0 0 0-.59-.22l-2.39.96c-.5-.38-1.03-.7-1.62-.94l-.36-2.54a.484.484 0 0 0-.48-.41h-3.84c-.24 0-.43.17-.47.41l-.36 2.54c-.59.24-1.13.57-1.62.94l-2.39-.96a.49.49 0 0 0-.59.22L2.74 8.87c-.12.21-.08.47.12.61l2.03 1.58c-.05.3-.09.63-.09.94s.02.64.07.94l-2.03 1.58a.49.49 0 0 0-.12.61l1.92 3.32c.12.22.37.29.59.22l2.39-.96c.5.38 1.03.7 1.62.94l.36 2.54c.05.24.24.41.48.41h3.84c.24 0 .44-.17.47-.41l.36-2.54c.59-.24 1.13-.56 1.62-.94l2.39.96c.22.08.47 0 .59-.22l1.92-3.32c.12-.22.07-.47-.12-.61l-2.01-1.58zM12 15.6A3.6 3.6 0 1 1 12 8.4a3.6 3.6 0 0 1 0 7.2z',
    }))

interface BookListItem extends DeckBookItem {}

const router = useRouter()
const message = useMessage()
const statsStore = useStatsStore()
const appSettingsShell = useAppSettingsShellStore()

const createInputRef = ref<any>(null)
const showAdvanced = ref(false)
const creating = ref(false)
const loading = ref(false)

const sidebarCollapsed = ref(readStorageBoolean(storageKeys.statsSidebarCollapsed))

function handleSidebarCollapsedChange(isCollapsed: boolean) {
  sidebarCollapsed.value = isCollapsed
}
const books = ref<BookListItem[]>([])
const searchQuery = ref('')
const deletingSlug = ref<string | null>(null)
/** 删除中（批量删除时确认按钮转圈） */
const deleting = ref(false)
/** 删除确认弹层（书架卡片/目录弹层触发） */
const showDeleteConfirm = ref(false)
const pendingDeleteBooks = ref<BookListItem[]>([])
/** 全部书目（书目录）弹层：书架管「当下在读」，这里管全部藏书 */
const showLibrary = ref(false)
/** 新建书目弹层开关：大表单已从主页搬进对话框，主页保持一屏 */
const createModalOpen = ref(false)
/** 有值时挂载向导；与 show 分离，挂载后始终 :show="true"，避免 Modal 先 false 再 true 闪烁 */
const setupWizard = ref<{ novelId: string; targetChapters: number } | null>(null)

const PREMISE_MAX_LEN = 2000

const newBook = ref({
  title: '',
  premise: '',
  genre: '',
  worldPreset: '',
  storyStructure: '',
  pacingControl: '',
  writingStyle: '',
  specialRequirements: '',
  chapters: 100,  // 默认 100 章
  words: 2500,
})

/** V1 目标篇幅档（与高级自定义二选一） */
const lengthTier = ref<NovelLengthTier>('standard')
const lengthTierOptions = NOVEL_LENGTH_TIER_OPTIONS

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
        stage_label: getNovelStageLabel(novel.stage),
        genre: g,
        premise: (novel.premise || '').trim(),
        chapter_count: novel.chapters?.length || 0,
        target_chapters: novel.target_chapters || 0,
        word_count: novel.total_word_count,
      }
    })
  } catch {
    message.error('加载失败')
  } finally {
    loading.value = false
  }
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
  if (!newBook.value.storyStructure.trim() || !newBook.value.pacingControl.trim() || !newBook.value.writingStyle.trim() || !newBook.value.specialRequirements.trim()) {
    message.warning('请补全四项写作规则')
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
      story_structure: newBook.value.storyStructure,
      pacing_control: newBook.value.pacingControl,
      writing_style: newBook.value.writingStyle,
      special_requirements: newBook.value.specialRequirements,
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
    // 成功即关弹层，后续 setupWizard 弹层接管流程
    createModalOpen.value = false

    setupWizard.value = {
      novelId: result.id,
      targetChapters: result.target_chapters,
    }
  } catch (error: unknown) {
    message.error(formatApiError(error, '创建失败'))
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
    setupWizard.value = {
      novelId,
      targetChapters: 100, // 默认值，向导内部会从 API 获取真实值
    }
    return
  }
  router.push(`/book/${novelId}/workbench`)
}

/** 删除入口（书架卡片单本 / 目录弹层单本或批量）：先弹确认框 */
const requestDeleteBooks = (slugs: string[]) => {
  const unique = Array.from(new Set(slugs.filter(Boolean)))
  pendingDeleteBooks.value = books.value.filter(b => unique.includes(b.slug))
  if (!pendingDeleteBooks.value.length) return
  showDeleteConfirm.value = true
}

const confirmDeleteBooks = async () => {
  if (!pendingDeleteBooks.value.length) return
  const pendingSlugs = new Set(pendingDeleteBooks.value.map(b => b.slug))
  deleting.value = true
  // 1. 逐本串行删除：后端无批量接口；失败不中断，最后统一报数
  let successCount = 0
  let failCount = 0
  const failed: BookListItem[] = []
  for (const book of pendingDeleteBooks.value) {
    deletingSlug.value = book.slug
    try {
      await novelApi.deleteNovel(book.slug)
      successCount += 1
    } catch {
      failCount += 1
      failed.push(book)
    }
  }
  // 2. 本地列表只移走删成功的；失败的留在架上（防止误清整个书架）
  const failedSlugs = new Set(failed.map(b => b.slug))
  if (successCount) {
    books.value = books.value.filter(
      b => failedSlugs.has(b.slug) || !pendingSlugs.has(b.slug)
    )
    await statsStore.loadGlobalStats(true)
  }
  deletingSlug.value = null
  pendingDeleteBooks.value = []
  showDeleteConfirm.value = false
  if (successCount) message.success(`已删除 ${successCount} 本书`)
  if (failCount) message.warning(`${failCount} 本书删除失败`)
  deleting.value = false
}

/** 打开新建书目弹层（侧边栏/空态/区头按钮共用入口） */
const openCreateModal = () => {
  createModalOpen.value = true
}

// 弹层打开后聚焦梗概输入框，保留原直达手感
watch(createModalOpen, (open) => {
  if (!open) return
  nextTick(() => {
    createInputRef.value?.focus()
  })
})

const handleRefreshList = async () => {
  await fetchBooks()
  message.success('列表已刷新')
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
  margin-bottom: 24px;
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
  color: var(--color-brand, #2563eb);
}

.header-content {
  padding: 0 44px;
}

/* 1. 眉标：定位语小字，字距拉宽 */
.brand-eyebrow {
  color: var(--app-text-secondary);
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 0.24em;
  margin-bottom: 14px;
}

/* 2. 水平 lockup：[印章][PlotPilot 字标][墨枢胶囊]同行垂直居中，与启动屏/登录页同构 */
.brand-lockup {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 14px;
  margin-bottom: 16px;
}

.brand-seal {
  flex-shrink: 0;
}

.brand-title {
  /* 品牌字标：Anton 紧凑超粗几何美术字（本地字体 /fonts/brand.css） */
  font-family: 'Anton', 'Arial Narrow', 'Inter', system-ui, sans-serif;
  font-size: clamp(40px, 4.2vw, 56px);
  font-weight: 400;
  letter-spacing: 0.01em;
  line-height: 0.96;
  color: var(--app-text-primary);
}

.brand-alias {
  /* 与启动屏同款胶囊：细描边 + 微透底 */
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 26px;
  padding: 0 12px;
  border: 1px solid var(--app-border, rgba(148, 163, 184, 0.35));
  border-radius: 999px;
  background: var(--app-surface-subtle);
  color: var(--app-text-secondary);
  font-size: 13px;
  font-weight: 600;
  letter-spacing: 0.16em;
  text-indent: 0.16em;
  line-height: 1;
}

.subtitle {
  font-size: 1.05rem;
  color: var(--app-text-secondary);
  margin: 0 auto;
  max-width: 560px;
  font-weight: 400;
  line-height: 1.7;
}


.create-title-wrap {
  display: flex;
  align-items: center;
  gap: 10px;
}

.create-icon {
  color: var(--color-gold);
}

.create-title {
  margin: 0;
  font-size: 17px;
  font-weight: 600;
}

/* 新建书目弹层（表单从主页搬入，主页保持一屏） */
.create-modal {
  border-radius: 16px;
  box-shadow: 0 8px 32px rgba(15, 23, 42, 0.12);
}

.create-modal-body {
  max-height: min(64vh, 660px);
  overflow-y: auto;
  padding-right: 4px;
}

.create-modal-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
}

.create-modal-footer .n-button--medium-type-primary {
  margin-left: auto;
}

/* 区头「新建书目」主按钮：与搜索框同行 */
.new-book-btn {
  flex-shrink: 0;
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
  background: rgba(37, 99, 235, 0.04);
  border-radius: 12px;
  border: 1px solid rgba(37, 99, 235, 0.1);
}

.w-full {
  width: 100%;
}

.books-section {
  background: var(--app-surface);
  border-radius: 16px;
  padding: 24px 28px 28px;
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

.search-result-hint {
  margin: 0 0 12px;
  font-size: 13px;
  color: var(--app-text-muted);
}

.section-right {
  display: flex;
  align-items: center;
  gap: 12px;
}

.search-input {
  width: 240px;
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
  padding: 20px 20px 24px;
  margin-top: 24px;
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

}

</style>
