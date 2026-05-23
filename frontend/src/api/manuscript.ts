import { apiClient } from './config'
import type { PropDTO } from './propApi'

export interface LexiconCharacter {
  id: string
  name: string
  aliases: string[]
}

export interface LexiconLocation {
  id: string
  name: string
  location_type: string
  aliases: string[]
}

export interface ChapterEntityMention {
  entity_kind: string
  entity_id: string
  display_label: string
  mention_count: number
  updated_at: string
}

export const manuscriptApi = {
  getEntityLexicon: (novelId: string) =>
    apiClient.get<{ characters: LexiconCharacter[]; locations: LexiconLocation[]; props: PropDTO[] }>(
      `/novels/${novelId}/manuscript/entity-lexicon`,
    ) as Promise<{ characters: LexiconCharacter[]; locations: LexiconLocation[]; props: PropDTO[] }>,

  listChapterMentions: (novelId: string, chapterNumber: number) =>
    apiClient.get<{ mentions: ChapterEntityMention[] }>(
      `/novels/${novelId}/chapters/${chapterNumber}/entity-mentions`,
    ) as Promise<{ mentions: ChapterEntityMention[] }>,

  reindexChapterMentions: (novelId: string, chapterNumber: number, content?: string | null) => {
    const cfg =
      content != null && content !== ''
        ? { params: { content } as Record<string, string> }
        : undefined
    return apiClient.post<{ ok: boolean; mentions: ChapterEntityMention[] }>(
      `/novels/${novelId}/chapters/${chapterNumber}/entity-mentions/reindex`,
      {},
      cfg,
    ) as Promise<{ ok: boolean; mentions: ChapterEntityMention[] }>
  },
}
