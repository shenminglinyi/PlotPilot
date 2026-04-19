/**
 * 子项目 8：工作流 / 长任务 / 一致性 / 故事线
 * 后端路由实现见 `docs/superpowers/plans/2026-04-02-subproject-8-frontend-extensions.md`
 */
import { WIZARD_STEP_TIMEOUT_MS } from '@/constants/wizard'
import { apiClient, resolveHttpUrl } from './config'
import type { JobStatusResponse } from '../types/api'

export interface StorylineMilestoneDTO {
  order: number
  title: string
  description?: string
  target_chapter_start: number
  target_chapter_end: number
  prerequisites: string[]
  triggers: string[]
}

export interface StorylineMergePointDTO {
  chapter_number: number
  storyline_ids: string[]
  merge_type: 'convergence' | 'divergence'
  description?: string
}

export interface StorylineGraphDataDTO {
  storylines: StorylineDTO[]
  merge_points: StorylineMergePointDTO[]
  total_chapters: number
}

export interface StorylineDTO {
  id: string
  storyline_type: string
  status: string
  estimated_chapter_start: number
  estimated_chapter_end: number
  name?: string
  description?: string
  milestones?: StorylineMilestoneDTO[]
  current_milestone_index?: number
  last_active_chapter?: number
  progress_summary?: string
}

export interface MainPlotOptionDTO {
  id: string
  type: string
  title: string
  logline: string
  core_conflict: string
  starting_hook: string
}

export interface PlotPointDTO {
  chapter_number: number
  point_type: string
  tension: number
  description: string
}

export interface PlotArcDTO {
  id: string
  novel_id: string
  key_points: PlotPointDTO[]
}

export interface GenerateChapterWithContextPayload {
  chapter_number: number
  outline: string
  scene_director_result?: Record<string, unknown>
}

export interface SceneDirectorAnalysis {
  chapter_number: number
  outline: string
  pov_character?: string
  location?: string
  entities?: string[]
  tone?: string
  [key: string]: unknown
}

/**
 * POST /api/v1/novels/{novel_id}/scene-director/analyze
 * 分析章节大纲，提取场记信息（角色、地点、基调），用于过滤生成上下文。
 */
export async function analyzeScene(
  novelId: string,
  chapterNumber: number,
  outline: string
): Promise<SceneDirectorAnalysis> {
  return apiClient.post<SceneDirectorAnalysis>(
    `/novels/${novelId}/scene-director/analyze`,
    { chapter_number: chapterNumber, outline }
  ) as unknown as Promise<SceneDirectorAnalysis>
}

/** 与 `interfaces/api/v1/generation.py` GenerateChapterResponse 对齐 */
export interface ConsistencyIssueDTO {
  type: string
  severity: string
  description: string
  location: number
}

export interface ConsistencyReportDTO {
  issues: ConsistencyIssueDTO[]
  warnings: ConsistencyIssueDTO[]
  suggestions: string[]
}

export interface StyleWarning {
  pattern: string
  text: string
  start: number
  end: number
  severity: 'info' | 'warning'
}

export interface GenerateChapterWorkflowResponse {
  content: string
  consistency_report: ConsistencyReportDTO
  token_count: number
  style_warnings?: StyleWarning[]
  ghost_annotations?: unknown[]
}

export interface ChunkStats {
  chars: number
  chunks: number
  estimated_tokens: number
}

export type GenerateChapterStreamEvent =
  | { type: 'phase'; phase: 'planning' | 'context' | 'llm' | 'post' }
  | { type: 'chunk'; text: string; stats: ChunkStats }
  | { type: 'done'; content: string; consistency_report: ConsistencyReportDTO; token_count: number; output_tokens: number; total_tokens: number; chars: number; style_warnings?: StyleWarning[]; ghost_annotations?: unknown[] }
  | { type: 'error'; message: string }

function parseSseDataLine(line: string): unknown | null {
  if (!line.startsWith('data: ')) return null
  try {
    return JSON.parse(line.slice(6)) as unknown
  } catch {
    return null
  }
}

/**
 * POST /api/v1/novels/{novel_id}/generate-chapter-stream（SSE）
 * 阶段进度 + 正文流式；结束事件含 done 或 error。
 */
export async function consumeGenerateChapterStream(
  novelId: string,
  data: GenerateChapterWithContextPayload,
  handlers: {
    onEvent?: (ev: GenerateChapterStreamEvent) => void
    onPhase?: (phase: string) => void
    onChunk?: (text: string, stats?: ChunkStats) => void
    onDone?: (result: GenerateChapterWorkflowResponse) => void
    onError?: (message: string) => void
    signal?: AbortSignal
  }
): Promise<void> {
  const res = await fetch(resolveHttpUrl(`/api/v1/novels/${novelId}/generate-chapter-stream`), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
    signal: handlers.signal,
  })
  if (!res.ok || !res.body) {
    const t = await res.text().catch(() => '')
    handlers.onError?.(t || `HTTP ${res.status}`)
    return
  }
  const reader = res.body.getReader()
  const dec = new TextDecoder()
  let buf = ''
  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buf += dec.decode(value, { stream: true })
      let sep: number
      while ((sep = buf.indexOf('\n\n')) >= 0) {
        const block = buf.slice(0, sep)
        buf = buf.slice(sep + 2)
        for (const line of block.split('\n')) {
          const raw = parseSseDataLine(line)
          if (!raw || typeof raw !== 'object' || raw === null) continue
          const o = raw as Record<string, unknown>
          const typ = o.type as string
          if (typ === 'phase') {
            const ph = String(o.phase ?? '')
            const ev: GenerateChapterStreamEvent = { type: 'phase', phase: ph as 'planning' | 'context' | 'llm' | 'post' }
            handlers.onEvent?.(ev)
            handlers.onPhase?.(ph)
          } else if (typ === 'chunk') {
            const text = String(o.text ?? '')
            const stats = o.stats as ChunkStats | undefined
            const ev: GenerateChapterStreamEvent = { type: 'chunk', text, stats: stats || { chars: 0, chunks: 0, estimated_tokens: 0 } }
            handlers.onEvent?.(ev)
            handlers.onChunk?.(text, stats)
          } else if (typ === 'done') {
            const rawReport = o.consistency_report
            const consistency_report: ConsistencyReportDTO =
              rawReport && typeof rawReport === 'object'
                ? (rawReport as ConsistencyReportDTO)
                : { issues: [], warnings: [], suggestions: [] }
            const result: GenerateChapterWorkflowResponse = {
              content: String(o.content ?? ''),
              consistency_report,
              token_count: Number(o.token_count ?? 0),
            }
            if (Array.isArray(o.style_warnings)) {
              result.style_warnings = o.style_warnings as StyleWarning[]
            }
            if (o.ghost_annotations != null) {
              result.ghost_annotations = o.ghost_annotations as unknown[]
            }
            const ev: GenerateChapterStreamEvent = {
              type: 'done',
              ...result,
              output_tokens: Number(o.output_tokens ?? 0),
              total_tokens: Number(o.total_tokens ?? 0),
              chars: Number(o.chars ?? 0),
            }
            handlers.onEvent?.(ev)
            handlers.onDone?.(result)
            return
          } else if (typ === 'error') {
            const msg = String(o.message ?? '生成失败')
            const ev: GenerateChapterStreamEvent = { type: 'error', message: msg }
            handlers.onEvent?.(ev)
            handlers.onError?.(msg)
            return
          }
        }
      }
    }
  } catch (e: unknown) {
    if (e instanceof Error && e.name === 'AbortError') return
    const msg = e instanceof Error ? e.message : '流式连接失败'
    handlers.onError?.(msg)
  }
}

export interface HostedWritePayload {
  from_chapter: number
  to_chapter: number
  auto_save: boolean
  auto_outline: boolean
}

/**
 * POST /api/v1/novels/{novel_id}/hosted-write-stream — 托管多章连写（SSE，每行 JSON）
 */
export async function consumeHostedWriteStream(
  novelId: string,
  body: HostedWritePayload,
  handlers: {
    onEvent?: (o: Record<string, unknown>) => void
    onError?: (message: string) => void
    signal?: AbortSignal
  }
): Promise<void> {
  const res = await fetch(resolveHttpUrl(`/api/v1/novels/${novelId}/hosted-write-stream`), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    signal: handlers.signal,
  })
  if (!res.ok || !res.body) {
    const t = await res.text().catch(() => '')
    handlers.onError?.(t || `HTTP ${res.status}`)
    return
  }
  const reader = res.body.getReader()
  const dec = new TextDecoder()
  let buf = ''
  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buf += dec.decode(value, { stream: true })
      let sep: number
      while ((sep = buf.indexOf('\n\n')) >= 0) {
        const block = buf.slice(0, sep)
        buf = buf.slice(sep + 2)
        for (const line of block.split('\n')) {
          const raw = parseSseDataLine(line)
          if (!raw || typeof raw !== 'object' || raw === null) continue
          const o = raw as Record<string, unknown>
          handlers.onEvent?.(o)
          if (o.type === 'error') {
            handlers.onError?.(String(o.message ?? 'error'))
            return
          }
        }
      }
    }
  } catch (e: unknown) {
    if (e instanceof Error && e.name === 'AbortError') return
    handlers.onError?.(e instanceof Error ? e.message : '流式连接失败')
  }
}

export const workflowApi = {
  /** GET /api/v1/novels/{novel_id}/storylines */
  getStorylines: (novelId: string) =>
    apiClient.get<StorylineDTO[]>(`/novels/${novelId}/storylines`) as unknown as Promise<StorylineDTO[]>,

  /** GET /api/v1/novels/{novel_id}/storylines/graph-data (Git Graph 全量数据) */
  getStorylineGraphData: (novelId: string) =>
    apiClient.get<StorylineGraphDataDTO>(`/novels/${novelId}/storylines/graph-data`) as unknown as Promise<StorylineGraphDataDTO>,

  /** POST /api/v1/novels/{novel_id}/setup/suggest-main-plot-options（单次 LLM；引导页默认 400s） */
  suggestMainPlotOptions: (novelId: string) =>
    apiClient.post<{ plot_options: MainPlotOptionDTO[] }>(
      `/novels/${novelId}/setup/suggest-main-plot-options`,
      {},
      { timeout: WIZARD_STEP_TIMEOUT_MS }
    ) as unknown as Promise<{ plot_options: MainPlotOptionDTO[] }>,

  /** POST /api/v1/novels/{novel_id}/storylines */
  createStoryline: (
    novelId: string,
    data: {
      storyline_type: string
      estimated_chapter_start: number
      estimated_chapter_end: number
      name?: string
      description?: string
    }
  ) => apiClient.post<StorylineDTO>(`/novels/${novelId}/storylines`, data) as unknown as Promise<StorylineDTO>,

  /** PUT /api/v1/novels/{novel_id}/storylines/{storyline_id} */
  updateStoryline: (novelId: string, storylineId: string, data: Partial<{ storyline_type: string; estimated_chapter_start: number; estimated_chapter_end: number; status: string }>) =>
    apiClient.put<StorylineDTO>(`/novels/${novelId}/storylines/${storylineId}`, data) as unknown as Promise<StorylineDTO>,

  /** DELETE /api/v1/novels/{novel_id}/storylines/{storyline_id} */
  deleteStoryline: (novelId: string, storylineId: string) =>
    apiClient.delete(`/novels/${novelId}/storylines/${storylineId}`) as unknown as Promise<void>,

  /** GET /api/v1/novels/{novel_id}/plot-arc */
  getPlotArc: (novelId: string) =>
    apiClient.get<PlotArcDTO>(`/novels/${novelId}/plot-arc`) as unknown as Promise<PlotArcDTO>,

  /** POST /api/v1/novels/{novel_id}/plot-arc（body 含 key_points 等，见后端 CreatePlotArcRequest） */
  createPlotArc: (novelId: string, data: { key_points: PlotPointDTO[] }) =>
    apiClient.post<PlotArcDTO>(`/novels/${novelId}/plot-arc`, data) as unknown as Promise<PlotArcDTO>,

  /** GET /api/v1/jobs/{job_id} — JobStatusIndicator 使用 */
  getJobStatus: (jobId: string) =>
    apiClient.get<JobStatusResponse>(`/jobs/${jobId}`) as unknown as Promise<JobStatusResponse>,

  /** POST /api/v1/jobs/{job_id}/cancel — JobStatusIndicator 使用 */
  cancelJob: (jobId: string) =>
    apiClient.post<{ ok: boolean }>(`/jobs/${jobId}/cancel`, {}) as unknown as Promise<{ ok: boolean }>,

  // ============================================================================
  // 新增：大纲规划、章节审稿、续写大纲
  // ============================================================================

  /** POST /api/v1/novels/{novel_id}/plan */
  planNovel: (novelId: string, mode: 'initial' | 'revise' = 'initial', dryRun = false) =>
    apiClient.post<{
      success: boolean
      message: string
      bible_updated: boolean
      outline_updated: boolean
      chapters_planned: number
    }>(`/novels/${novelId}/plan`, { mode, dry_run: dryRun }),

  /** POST /api/v1/novels/{novel_id}/chapters/{chapter_number}/review */
  reviewChapter: (novelId: string, chapterNumber: number) =>
    apiClient.post<{
      chapter_number: number
      suggestions: string[]
      score: number
    }>(`/novels/${novelId}/chapters/${chapterNumber}/review`, {}) as unknown as Promise<{
      chapter_number: number
      suggestions: string[]
      score: number
    }>,

  /** POST /api/v1/novels/{novel_id}/outline/extend */
  extendOutline: (novelId: string, fromChapter: number, count = 5) =>
    apiClient.post<{
      success: boolean
      chapters_added: number
      outlines: string[]
    }>(`/novels/${novelId}/outline/extend`, { from_chapter: fromChapter, count }),
}

// ── 上下文预览 ──────────────────────────────────────────────

export interface ContextLayerContent {
  content: string
}

export interface ContextTokenUsage {
  layer1: number
  layer2: number
  layer3: number
  total: number
  limit: number
}

export interface ContextPreviewResult {
  layer1: ContextLayerContent
  layer2: ContextLayerContent
  layer3: ContextLayerContent
  token_usage: ContextTokenUsage
}

export async function retrieveContext(
  novelId: string,
  chapterNumber: number,
  outline: string,
  maxTokens = 16000,
  sceneDirectorResult?: Record<string, unknown>,
): Promise<ContextPreviewResult> {
  return apiClient.post<ContextPreviewResult>(
    `/novels/${novelId}/context/retrieve`,
    {
      chapter_number: chapterNumber,
      outline,
      max_tokens: maxTokens,
      scene_director_result: sceneDirectorResult,
    }
  ) as unknown as Promise<ContextPreviewResult>
}
