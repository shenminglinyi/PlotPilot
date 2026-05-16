/**
 * 叙事引擎（小说家向只读聚合）— 与后端 `narrative_engine_routes` 对齐。
 * @see application.narrative_engine.read_facade.NarrativeEngineReadFacade
 */
import { apiClient } from './config'
import type { StorylineDTO } from './workflow'
import type { StoryPhaseDTO } from './engineCore'

export interface StoryEvolutionReadModel {
  novel_id: string
  schema_version: string
  life_cycle: StoryPhaseDTO
  plot_spine: {
    storylines: StorylineDTO[]
    plot_arc: Record<string, unknown> | null
  }
  chronotope: {
    rows: unknown[]
    max_chapter_in_book: number
    note?: string
  }
  chapters_digest: unknown[]
  subtext_surface: {
    foreshadow_ledger_count: number
  }
}

export interface PersonaVoiceReadModel {
  novel_id: string
  schema_version: string
  character_id: string
  character_name: string
  voice_anchor: {
    mental_state: string
    verbal_tic: string
    idle_behavior: string
  }
  dialogue_corpus: {
    total_lines: number
    lines_as_speaker: number
  }
}

export interface SurfaceCatalogLens {
  id: string
  title: string
  summary: string
}

export interface SurfaceCatalogFamily {
  id: string
  lens: string
  path_prefixes: string[]
  client_modules: string[]
  backend_router_hint: string
  note_zh: string
}

export interface SurfaceCatalogResponse {
  schema_version: string
  generated_at: string
  lenses: SurfaceCatalogLens[]
  families: SurfaceCatalogFamily[]
  notes_zh: string[]
}

export const narrativeEngineApi = {
  /** GET /narrative-engine/surface-catalog — 小说家维度 × 前端模块 × 路径族 */
  getSurfaceCatalog: () =>
    apiClient.get<SurfaceCatalogResponse>('/narrative-engine/surface-catalog') as unknown as Promise<SurfaceCatalogResponse>,

  /** GET /novels/{id}/narrative-engine/story-evolution */
  getStoryEvolution: (novelId: string) =>
    apiClient.get<StoryEvolutionReadModel>(
      `/novels/${novelId}/narrative-engine/story-evolution`,
    ) as unknown as Promise<StoryEvolutionReadModel>,

  /** GET /novels/{id}/narrative-engine/persona-voice/{characterId} */
  getPersonaVoice: (novelId: string, characterId: string) =>
    apiClient.get<PersonaVoiceReadModel>(
      `/novels/${novelId}/narrative-engine/persona-voice/${characterId}`,
    ) as unknown as Promise<PersonaVoiceReadModel>,
}
