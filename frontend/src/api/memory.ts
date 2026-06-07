import { apiClient } from './config'

export interface MemoryAtom {
  id: string
  novel_id: string
  entity_id: string
  entity_type: string
  memory_type: string
  scope: string
  source: string
  status: string
  payload: Record<string, unknown>
  chapter_number?: number | null
  text_span: string
  confidence: number
}

export interface CharacterProjection {
  novel_id: string
  entity_id: string
  character_id: string
  name: string
  constitution: Record<string, unknown>
  current_state: Record<string, unknown>
  active_scars: Array<Record<string, unknown>>
  active_motivations: Array<Record<string, unknown>>
  emotional_arc: Array<Record<string, unknown>>
  relationships: Array<Record<string, unknown>>
  knowledge_boundary: Record<string, unknown>
  voice_fingerprint: Record<string, unknown>
  arc_debts: Array<Record<string, unknown>>
  recent_evidence: MemoryAtom[]
  candidate_memories: MemoryAtom[]
  context_locks: { t0?: string; t1?: string; t2?: string }
}

export const memoryApi = {
  getCharacterProjection: (novelId: string, characterId: string) =>
    apiClient.get<CharacterProjection>(
      `/novels/${novelId}/characters/${characterId}/projection`,
    ) as unknown as Promise<CharacterProjection>,

  getChapterCandidates: (novelId: string, chapterNumber: number) =>
    apiClient.get<{ chapter_number: number; candidates: MemoryAtom[] }>(
      `/novels/${novelId}/chapters/${chapterNumber}/memory-candidates`,
    ) as unknown as Promise<{ chapter_number: number; candidates: MemoryAtom[] }>,

  confirm: (novelId: string, atomId: string, note = '') =>
    apiClient.post<{ ok: boolean; atom: MemoryAtom }>(
      `/novels/${novelId}/memory-atoms/${atomId}/confirm`,
      { note },
    ) as unknown as Promise<{ ok: boolean; atom: MemoryAtom }>,

  reject: (novelId: string, atomId: string, note = '') =>
    apiClient.post<{ ok: boolean; atom: MemoryAtom }>(
      `/novels/${novelId}/memory-atoms/${atomId}/reject`,
      { note },
    ) as unknown as Promise<{ ok: boolean; atom: MemoryAtom }>,

  promote: (novelId: string, atomId: string, note = '') =>
    apiClient.post<{ ok: boolean; atom: MemoryAtom }>(
      `/novels/${novelId}/memory-atoms/${atomId}/promote`,
      { note },
    ) as unknown as Promise<{ ok: boolean; atom: MemoryAtom }>,
}
