import { apiClient } from './config'

export interface StyleSampleDTO {
  id: string
  title: string
  content: string
  source_type: string
  genre: string
  scene_type: string
  pov: string
  allowed_for_generation: boolean
  novel_id: string
  profile_id: string
  content_hash: string
  char_count: number
}

export interface StyleChunkDTO {
  id: string
  sample_id: string
  chunk_type: 'chapter' | 'scene' | 'paragraph' | string
  sequence: number
  chapter_number: number
  title: string
  content: string
  char_count: number
  metrics: Record<string, any>
}

export interface StyleTechniqueCardDTO {
  id: string
  profile_id: string
  title: string
  category: string
  scene_type: string
  rule_text: string
  example_summary: string
  prompt_instruction: string
  enabled: boolean
  weight: number
}

export interface StyleProfileDTO {
  id: string
  name: string
  description: string
  status: string
  novel_id: string
  profile: Record<string, any>
  metrics: Record<string, any>
  rules: any[]
  forbidden_patterns: string[]
  version: number
}

export interface StyleProfileDetail {
  profile: StyleProfileDTO
  cards: StyleTechniqueCardDTO[]
}

export interface StyleSampleImportResultDTO {
  sample: StyleSampleDTO
  chunks: StyleChunkDTO[]
  profile?: StyleProfileDTO | null
  cards: StyleTechniqueCardDTO[]
}

export interface StyleProfileGenerateResultDTO {
  profile: StyleProfileDTO
  cards: StyleTechniqueCardDTO[]
}

export interface StyleProfileMatchReportDTO {
  profile_id: string
  score: number
  metrics: Record<string, any>
  issues: string[]
}

export interface StylePromptOverlayDTO {
  prompt: string
  profile_id: string
  profile_name: string
  card_ids: string[]
}

export interface ImportStyleSamplePayload {
  title: string
  content: string
  source_type?: string
  genre?: string
  scene_type?: string
  pov?: string
  allowed_for_generation?: boolean
  novel_id?: string
  profile_id?: string
  create_profile?: boolean
  profile_name?: string
}

export interface GenerateStyleProfilePayload {
  novel_id?: string
  name: string
  description?: string
  sample_ids?: string[]
  use_llm?: boolean
  llm_profile_id?: string
}

export interface UpdateTechniqueCardPayload {
  title?: string
  category?: string
  scene_type?: string
  rule_text?: string
  example_summary?: string
  prompt_instruction?: string
  enabled?: boolean
  weight?: number
}

export interface MatchStyleProfilePayload {
  novel_id?: string
  content: string
}

export const styleBibleApi = {
  importSample: (payload: ImportStyleSamplePayload) =>
    apiClient.post<StyleSampleImportResultDTO>('/style-bible/samples', payload) as Promise<StyleSampleImportResultDTO>,

  listSamples: (params?: { novel_id?: string; profile_id?: string }) =>
    apiClient.get<StyleSampleDTO[]>('/style-bible/samples', { params }) as Promise<StyleSampleDTO[]>,

  generateProfile: (payload: GenerateStyleProfilePayload) =>
    apiClient.post<StyleProfileGenerateResultDTO>('/style-bible/profiles', payload) as Promise<StyleProfileGenerateResultDTO>,

  listProfiles: (params?: { novel_id?: string; status?: string }) =>
    apiClient.get<StyleProfileDetail[]>('/style-bible/profiles', { params }) as Promise<StyleProfileDetail[]>,

  getProfile: (profileId: string) =>
    apiClient.get<StyleProfileDetail>(`/style-bible/profiles/${profileId}`) as Promise<StyleProfileDetail>,

  updateCard: (cardId: string, payload: UpdateTechniqueCardPayload) =>
    apiClient.patch<StyleTechniqueCardDTO>(`/style-bible/cards/${cardId}`, payload) as Promise<StyleTechniqueCardDTO>,

  matchProfile: (profileId: string, payload: MatchStyleProfilePayload) =>
    apiClient.post<StyleProfileMatchReportDTO>(`/style-bible/profiles/${profileId}/match`, payload) as Promise<StyleProfileMatchReportDTO>,

  previewOverlay: (payload: { novel_id?: string; style_profile_id: string; scene_type?: string; max_cards?: number }) =>
    apiClient.post<StylePromptOverlayDTO>('/style-bible/overlay/preview', payload) as Promise<StylePromptOverlayDTO>,
}
