import { apiClient } from './config'

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

export interface BiblePropRow {
  id: string
  novel_id: string
  name: string
  description: string
  aliases_json: string
  holder_character_id: string | null
  first_chapter: number | null
  created_at: string
  updated_at: string
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
    apiClient.get<{ characters: LexiconCharacter[]; locations: LexiconLocation[]; props: BiblePropRow[] }>(
      `/novels/${novelId}/manuscript/entity-lexicon`,
    ) as Promise<{ characters: LexiconCharacter[]; locations: LexiconLocation[]; props: BiblePropRow[] }>,

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

  listProps: (novelId: string) =>
    apiClient.get<{ props: BiblePropRow[] }>(`/novels/${novelId}/manuscript/props`) as Promise<{ props: BiblePropRow[] }>,

  createProp: (
    novelId: string,
    body: {
      name: string
      description?: string
      aliases?: string[]
      holder_character_id?: string | null
      first_chapter?: number | null
    },
  ) => apiClient.post<BiblePropRow>(`/novels/${novelId}/manuscript/props`, body) as Promise<BiblePropRow>,

  patchProp: (
    novelId: string,
    propId: string,
    body: Partial<{
      name: string
      description: string
      aliases: string[]
      holder_character_id: string | null
      first_chapter: number | null
    }>,
  ) => apiClient.patch<BiblePropRow>(`/novels/${novelId}/manuscript/props/${propId}`, body) as Promise<BiblePropRow>,

  deleteProp: (novelId: string, propId: string) =>
    apiClient.delete(`/novels/${novelId}/manuscript/props/${propId}`) as Promise<void>,
}
