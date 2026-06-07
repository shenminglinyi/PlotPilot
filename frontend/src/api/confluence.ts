import { apiClient } from './config'

export interface ConfluencePointDTO {
  id: string
  novel_id: string
  source_storyline_id: string
  target_storyline_id: string
  target_chapter: number
  merge_type: 'intersect' | 'absorb' | 'reveal' | string
  context_summary: string
  pre_reveal_hint: string
  behavior_guards: string[]
  resolved: boolean
}

export const confluenceApi = {
  list: (novelId: string) =>
    apiClient.get<ConfluencePointDTO[]>(`/novels/${novelId}/confluence-points`) as unknown as Promise<ConfluencePointDTO[]>,
}
