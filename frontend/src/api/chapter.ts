import { apiClient } from './config'

export interface ChapterDTO {
  id: string
  novel_id: string
  number: number
  title: string
  content: string
  status: string
  word_count: number
  created_at: string
  updated_at: string
}

export interface UpdateChapterRequest {
  content: string
}

export interface ChapterReviewDTO {
  status: string
  memo: string
  created_at: string
  updated_at: string
}

export interface ChapterStructureDTO {
  word_count: number
  paragraph_count: number
  dialogue_ratio: number
  scene_count: number
  pacing: string
}

export interface ChapterReviewAiResponse {
  ok: boolean
  status: string
  memo: string
  saved: boolean
}

export interface ChapterCandidateDraftDTO {
  id: string
  novel_id: string
  chapter_number: number
  branch_name: string
  source: string
  status: string
  title: string
  content: string
  rationale: string
  metadata: Record<string, unknown>
  created_at: string
  updated_at: string
}

export interface CreateChapterCandidateDraftRequest {
  source: string
  title?: string
  content: string
  rationale?: string
  metadata?: Record<string, unknown>
  branch_name?: string
}

export interface AcceptChapterCandidateDraftResponse {
  draft: ChapterCandidateDraftDTO
  chapter: ChapterDTO
  snapshot_id: string
}

export interface CandidateBranchSummary {
  branch_name: string
  draft_count: number
  accepted_count: number
  updated_at: string
}

export interface CandidateParagraphCompareItem {
  index: number
  type: 'unchanged' | 'added' | 'removed' | 'modified'
  primary: string
  candidate: string
  similarity: number
}

export interface CandidateDraftCompareResponse {
  draft: ChapterCandidateDraftDTO
  primary_word_count: number
  candidate_word_count: number
  similarity: number
  paragraphs: CandidateParagraphCompareItem[]
}

export interface BranchMemoryImpactItem {
  label: string
  level: 'info' | 'warning' | 'success' | 'error' | string
  detail: string
}

export interface BranchMemoryDiffResponse {
  novel_id: string
  chapter_number: number
  source_branch: string
  target_branch: string
  source_draft_count: number
  target_draft_count: number
  source_latest_draft_id: string
  target_latest_draft_id: string
  similarity: number
  memory_impacts: BranchMemoryImpactItem[]
}

export interface ExternalModelTaskDTO {
  id: string
  novel_id: string
  chapter_number: number
  model: string
  prompt: string
  instruction: string
  source_draft_id: string
  candidate_draft_id: string
  response_preview: string
  status: 'prompted' | 'imported' | 'accepted' | string
  execution_mode: 'copy_paste' | 'direct_api' | string
  created_at: string
  updated_at: string
}

export interface UpsertExternalModelTaskRequest {
  id?: string
  chapter_number: number
  model?: string
  prompt?: string
  instruction?: string
  source_draft_id?: string
  candidate_draft_id?: string
  response_preview?: string
  status?: string
  execution_mode?: string
}

export interface GenerateCandidateDraftRequest {
  chapter_number: number
  outline: string
  current_content?: string
  branch_name?: string
  title?: string
  source?: string
  model_label?: string
  llm_profile_id?: string
  task_prompt?: string
  max_tokens?: number
  temperature?: number
}

export interface GenerateCandidateDraftResponse {
  draft: ChapterCandidateDraftDTO
  task: ExternalModelTaskDTO
}

export interface EditorialReviewForPolishDTO {
  summary: string
  scores: {
    opening: number
    conflict: number
    character: number
    dialogue: number
    hook: number
    pacing: number
  }
  strengths: string[]
  problems: string[]
  actions: string[]
  verdict: string
}

export interface GenerateEditorialPolishCandidateRequest {
  chapter_number: number
  outline: string
  current_content: string
  editorial_review: EditorialReviewForPolishDTO
  target_word_count?: number
  branch_name?: string
  title?: string
  model_label?: string
  max_tokens?: number
  temperature?: number
}

export interface CreateWebWritingPromptRequest {
  chapter_number: number
  outline: string
  current_content?: string
  model_label?: string
  task_prompt?: string
}

export interface WebWritingPromptResponse {
  prompt: string
  task: ExternalModelTaskDTO
}

export interface SupervisorReviewCandidateDraftRequest {
  model_label?: string
  llm_profile_id?: string
  focus?: string
  max_tokens?: number
  temperature?: number
}

export interface SupervisorReviewCandidateDraftResponse {
  draft_id: string
  model_label: string
  review: string
  task: ExternalModelTaskDTO
}

export const chapterApi = {
  /**
   * List all chapters for a novel
   * GET /api/v1/novels/{novelId}/chapters
   */
  listChapters: (novelId: string) =>
    apiClient.get<ChapterDTO[]>(`/novels/${novelId}/chapters`) as Promise<ChapterDTO[]>,

  /**
   * Get a specific chapter by number
   * GET /api/v1/novels/{novelId}/chapters/{chapterNumber}
   */
  getChapter: (novelId: string, chapterNumber: number) =>
    apiClient.get<ChapterDTO>(`/novels/${novelId}/chapters/${chapterNumber}`) as Promise<ChapterDTO>,

  /**
   * Update a chapter
   * PUT /api/v1/novels/{novelId}/chapters/{chapterNumber}
   */
  updateChapter: (novelId: string, chapterNumber: number, data: UpdateChapterRequest) =>
    apiClient.put<ChapterDTO>(`/novels/${novelId}/chapters/${chapterNumber}`, data) as Promise<ChapterDTO>,

  /**
   * Get chapter review
   * GET /api/v1/novels/{novelId}/chapters/{chapterNumber}/review
   */
  getChapterReview: (novelId: string, chapterNumber: number) =>
    apiClient.get<ChapterReviewDTO>(`/novels/${novelId}/chapters/${chapterNumber}/review`) as Promise<ChapterReviewDTO>,

  /**
   * Save chapter review
   * PUT /api/v1/novels/{novelId}/chapters/{chapterNumber}/review
   */
  saveChapterReview: (novelId: string, chapterNumber: number, status: string, memo: string) =>
    apiClient.put<ChapterReviewDTO>(`/novels/${novelId}/chapters/${chapterNumber}/review`, { status, memo }) as Promise<ChapterReviewDTO>,

  /**
   * AI review chapter
   * POST /api/v1/novels/{novelId}/chapters/{chapterNumber}/review-ai
   */
  reviewChapterAi: (novelId: string, chapterNumber: number, save: boolean) =>
    apiClient.post<ChapterReviewAiResponse>(`/novels/${novelId}/chapters/${chapterNumber}/review-ai`, { save }) as Promise<ChapterReviewAiResponse>,

  /**
   * Get chapter structure analysis
   * GET /api/v1/novels/{novelId}/chapters/{chapterNumber}/structure
   */
  getChapterStructure: (novelId: string, chapterNumber: number) =>
    apiClient.get<ChapterStructureDTO>(`/novels/${novelId}/chapters/${chapterNumber}/structure`) as Promise<ChapterStructureDTO>,

  /**
   * 确保章节在正文库中存在；若不存在则创建空白记录
   * POST /api/v1/novels/{novelId}/chapters/{chapterNumber}/ensure
   */
  ensureChapter: (novelId: string, chapterNumber: number, title = '') =>
    apiClient.post<ChapterDTO>(`/novels/${novelId}/chapters/${chapterNumber}/ensure`, { title }) as Promise<ChapterDTO>,

  /**
   * GET /api/v1/novels/{novelId}/chapters/{chapterNumber}/candidate-drafts
   */
  listCandidateDrafts: (novelId: string, chapterNumber: number, branchName?: string) =>
    apiClient.get<ChapterCandidateDraftDTO[]>(
      `/novels/${novelId}/chapters/${chapterNumber}/candidate-drafts`,
      {
        params: branchName ? { branch_name: branchName } : undefined,
      }
    ) as Promise<ChapterCandidateDraftDTO[]>,

  /**
   * POST /api/v1/novels/{novelId}/chapters/{chapterNumber}/candidate-drafts
   */
  createCandidateDraft: (novelId: string, chapterNumber: number, data: CreateChapterCandidateDraftRequest) =>
    apiClient.post<ChapterCandidateDraftDTO>(`/novels/${novelId}/chapters/${chapterNumber}/candidate-drafts`, data) as Promise<ChapterCandidateDraftDTO>,

  /**
   * POST /api/v1/novels/{novelId}/chapters/{chapterNumber}/candidate-drafts/{draftId}/accept
   */
  acceptCandidateDraft: (novelId: string, chapterNumber: number, draftId: string) =>
    apiClient.post<AcceptChapterCandidateDraftResponse>(`/novels/${novelId}/chapters/${chapterNumber}/candidate-drafts/${draftId}/accept`, {}) as Promise<AcceptChapterCandidateDraftResponse>,

  /**
   * POST /api/v1/novels/{novelId}/chapters/{chapterNumber}/candidate-drafts/{draftId}/reject
   */
  rejectCandidateDraft: (novelId: string, chapterNumber: number, draftId: string) =>
    apiClient.post<ChapterCandidateDraftDTO>(`/novels/${novelId}/chapters/${chapterNumber}/candidate-drafts/${draftId}/reject`, {}) as Promise<ChapterCandidateDraftDTO>,

  listCandidateBranches: (novelId: string, chapterNumber: number) =>
    apiClient.get<CandidateBranchSummary[]>(`/novels/${novelId}/chapters/${chapterNumber}/candidate-drafts/branches`) as Promise<CandidateBranchSummary[]>,

  compareCandidateDraft: (novelId: string, chapterNumber: number, draftId: string) =>
    apiClient.get<CandidateDraftCompareResponse>(`/novels/${novelId}/chapters/${chapterNumber}/candidate-drafts/${draftId}/compare`) as Promise<CandidateDraftCompareResponse>,

  mergeCandidateBranch: (novelId: string, chapterNumber: number, sourceBranch: string, targetBranch = 'main', rule = 'latest_candidate') =>
    apiClient.post<ChapterCandidateDraftDTO>(
      `/novels/${novelId}/chapters/${chapterNumber}/candidate-drafts/merge-branch`,
      { source_branch: sourceBranch, target_branch: targetBranch, rule }
    ) as Promise<ChapterCandidateDraftDTO>,

  getBranchMemoryDiff: (novelId: string, chapterNumber: number, sourceBranch: string, targetBranch = 'main') =>
    apiClient.get<BranchMemoryDiffResponse>(
      `/novels/${novelId}/chapters/${chapterNumber}/candidate-drafts/branch-memory-diff`,
      { params: { source_branch: sourceBranch, target_branch: targetBranch } }
    ) as Promise<BranchMemoryDiffResponse>,

  listExternalModelTasks: (novelId: string, chapterNumber?: number) =>
    apiClient.get<ExternalModelTaskDTO[]>(
      `/novels/${novelId}/external-model-tasks`,
      { params: chapterNumber ? { chapter_number: chapterNumber } : undefined }
    ) as Promise<ExternalModelTaskDTO[]>,

  upsertExternalModelTask: (novelId: string, data: UpsertExternalModelTaskRequest) =>
    apiClient.post<ExternalModelTaskDTO>(`/novels/${novelId}/external-model-tasks`, data) as Promise<ExternalModelTaskDTO>,

  generateCandidateDraft: (novelId: string, data: GenerateCandidateDraftRequest) =>
    apiClient.post<GenerateCandidateDraftResponse>(`/novels/${novelId}/candidate-drafts/generate`, data) as Promise<GenerateCandidateDraftResponse>,

  generateEditorialPolishCandidate: (novelId: string, data: GenerateEditorialPolishCandidateRequest) =>
    apiClient.post<GenerateCandidateDraftResponse>(`/novels/${novelId}/candidate-drafts/editorial-polish`, data) as Promise<GenerateCandidateDraftResponse>,

  createWebWritingPrompt: (novelId: string, data: CreateWebWritingPromptRequest) =>
    apiClient.post<WebWritingPromptResponse>(`/novels/${novelId}/candidate-drafts/web-writing-prompt`, data) as Promise<WebWritingPromptResponse>,

  reviewCandidateDraft: (
    novelId: string,
    chapterNumber: number,
    draftId: string,
    data: SupervisorReviewCandidateDraftRequest,
  ) =>
    apiClient.post<SupervisorReviewCandidateDraftResponse>(
      `/novels/${novelId}/chapters/${chapterNumber}/candidate-drafts/${draftId}/supervisor-review`,
      data,
    ) as Promise<SupervisorReviewCandidateDraftResponse>,
}
