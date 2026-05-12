import { ref, computed, toValue, type MaybeRefOrGetter } from 'vue'
import { useRouter } from 'vue-router'
import { useMessage } from 'naive-ui'
import { novelApi } from '../api/novel'
import { chapterApi } from '../api/chapter'
import { useStatsStore } from '../stores/statsStore'

// Constants
const STATS_DAYS = 30

function formatApiErrorDetail(error: unknown): string {
  const e = error as { response?: { data?: { detail?: unknown } }; message?: string }
  const d = e?.response?.data?.detail
  if (typeof d === 'string' && d.trim()) return d
  if (Array.isArray(d)) {
    const parts = d.map((x: { msg?: string }) => (typeof x?.msg === 'string' ? x.msg : JSON.stringify(x)))
    return parts.join('; ') || ''
  }
  if (e?.message && typeof e.message === 'string') return e.message
  return ''
}

// Type definitions
export interface BookMeta {
  has_bible?: boolean
  has_outline?: boolean
}

export interface UseWorkbenchOptions {
  /** 支持 `computed(() => route.params.slug)`，换书时 API 始终用当前 slug */
  slug: MaybeRefOrGetter<string>
}

export function useWorkbench(options: UseWorkbenchOptions) {
  const { slug } = options
  const router = useRouter()
  const message = useMessage()
  const statsStore = useStatsStore()

  // State - Business logic only, no UI state
  const bookTitle = ref('')
  const chapters = ref<{ id: number; number: number; title: string; word_count: number }[]>([])
  const bookMeta = ref<BookMeta>({})
  const pageLoading = ref(true)
  const currentChapterId = ref<number | null>(null)
  const chapterContent = ref('')
  const chapterLoading = ref(false)
  const currentJobId = ref<string | null>(null)

  /** 右栏子面板 id，与 SettingsPanel 中 foundation / narrative / tactical 的 tab name 一致 */
  const rightPanel = ref<string>('bible')

  const hasStructure = computed(() => {
    return bookMeta.value.has_bible || bookMeta.value.has_outline
  })

  const setRightPanel = (panel: string) => {
    rightPanel.value = panel
  }

  const loadDesk = async () => {
    const novelId = toValue(slug)
    // Use new novelApi and chapterApi instead of bookApi.getDesk
    const [novelData, chaptersData] = await Promise.all([
      novelApi.getNovel(novelId),
      chapterApi.listChapters(novelId)
    ])

    bookTitle.value = novelData.title || novelId

    // Map ChapterDTO[] to the format expected by the UI
    chapters.value = chaptersData.map(ch => ({
      id: ch.number,
      number: ch.number,
      title: ch.title,
      word_count: ch.word_count || 0
    }))

    // Use metadata from NovelDTO
    bookMeta.value = {
      has_bible: novelData.has_bible,
      has_outline: novelData.has_outline,
    }
  }

  const loadData = async (includeStats = false) => {
    pageLoading.value = true
    try {
      const promises: Promise<unknown>[] = [loadDesk()]
      if (includeStats) {
        promises.push(statsStore.loadBookAllStats(toValue(slug), STATS_DAYS, true))
      }
      await Promise.all(promises)
    } finally {
      pageLoading.value = false
    }
  }

  const handleJobCompleted = async () => {
    // Notify stats store to invalidate cache and reload
    statsStore.onJobCompleted(toValue(slug))
    // Refresh workbench data
    await loadDesk()
    // 作品设定页若已挂载：软刷新 Bible（避免整组件 :key 重建导致闪烁）
    if (rightPanel.value === 'bible') {
      window.dispatchEvent(new CustomEvent('aitext:bible-panel:soft-reload'))
    }
  }

  const restoreJobState = () => {
    // Note: localStorage recovery not currently used in the architecture
    // Job state is managed through API polling and component lifecycle
    // This method is a no-op but preserved for future expansion
  }


  const goHome = () => {
    router.push('/')
  }

  /**
   * 判断错误是否为 404（后端 EntityNotFoundError / HTTP 404）
   */
  function is404(error: unknown): boolean {
    const e = error as { response?: { status?: number }; message?: string }
    if (e?.response?.status === 404) return true
    const detail = formatApiErrorDetail(error)
    return /not\s*found|不存在/i.test(detail)
  }

  const goToChapter = async (id: number, nodeTitle?: string) => {
    if (!Number.isFinite(id) || id < 1) {
      message.error('无效的章节号')
      return
    }

    chapterLoading.value = true
    const novelId = toValue(slug)
    try {
      let chapter = await chapterApi.getChapter(novelId, id).catch(async (err) => {
        if (!is404(err)) throw err
        // 章节正文不存在：静默创建空白记录（对应结构树手动添加的节点）
        await chapterApi.ensureChapter(novelId, id, nodeTitle ?? '')
        return chapterApi.getChapter(novelId, id)
      })
      currentChapterId.value = id
      chapterContent.value = chapter.content || ''
      // 若刚刚是新建的空白章节，刷新侧栏章节列表
      const existed = chapters.value.some((c) => c.number === id)
      if (!existed) {
        await loadDesk()
      }
    } catch (error) {
      const detail = formatApiErrorDetail(error)
      currentChapterId.value = null
      chapterContent.value = ''
      message.error(
        detail
          ? `加载第 ${id} 章失败：${detail}`
          : `加载第 ${id} 章失败，请确认后端已启动。`
      )
    } finally {
      chapterLoading.value = false
    }
  }

  /** 路由换书：清空当前章视图后重载 desk（由 Workbench watch slug 调用） */
  const reloadDeskForSlugChange = async () => {
    currentChapterId.value = null
    chapterContent.value = ''
    await loadDesk()
  }

  const handleChapterSelect = async (chapterId: number, title = '') => {
    await goToChapter(chapterId, title)
  }

  const handleUpdateSettings = async (_settings: Record<string, unknown>) => {
    // Settings are managed by child components (BiblePanel, KnowledgePanel)
    // This method provides a consistent interface for future use
    // Current architecture uses delegation pattern
  }

  return {
    // State
    bookTitle,
    chapters,
    rightPanel,
    pageLoading,
    bookMeta,
    currentJobId,
    currentChapterId,
    chapterContent,
    chapterLoading,

    // Methods
    setRightPanel,
    loadDesk,
    reloadDeskForSlugChange,
    handleChapterSelect,
    goHome,
    goToChapter,
  }
}
