import type { GlobalStats, ChapterStats, WritingProgress } from '../types/api'
import { legacyStatsHttp } from './config'
import { novelApi } from './novel'

const request = legacyStatsHttp

function enc(slug: string): string {
  return encodeURIComponent(slug)
}

export const statsApi = {
  /**
   * Get global statistics across all books
   * GET /stats/global
   */
  getGlobal: () => request.get<GlobalStats>('/stats/global') as unknown as Promise<GlobalStats>,

  /**
   * Get statistics for a specific chapter
   * GET /stats/book/{slug}/chapter/{chapterId}
   */
  getChapter: (slug: string, chapterId: number) =>
    request.get<ChapterStats>(`/stats/book/${enc(slug)}/chapter/${chapterId}`) as unknown as Promise<ChapterStats>,

  /**
   * Get writing progress over time
   * GET /stats/book/{slug}/progress
   */
  getProgress: (slug: string, days = 30) =>
    request.get<WritingProgress[]>(`/stats/book/${enc(slug)}/progress`, {
      params: { days },
    }) as unknown as Promise<WritingProgress[]>,

  /**
   * 书目统计（v1 novel statistics）+ 写作进度（legacy /api/stats）
   */
  getBookAllStats: async (slug: string, days = 30) => {
    const [bookStats, progress] = await Promise.all([
      novelApi.getNovelStatistics(slug),
      statsApi.getProgress(slug, days),
    ])
    return { bookStats, progress }
  },
}
