import { parseStreamGeneratedBeats, type StreamGeneratedBeat } from '../api/workflow'
import { readStorageJson, writeStorageJson } from '@/utils/storage'

const KEY_PREFIX = 'pp-assist-beats:'

export function persistAssistBeatSession(
  slug: string,
  chapterNumber: number,
  beats: StreamGeneratedBeat[],
): void {
  if (!slug || chapterNumber < 1 || !beats.length) return
  writeStorageJson(`${KEY_PREFIX}${slug}:${chapterNumber}`, beats, 'session')
}

export function loadAssistBeatSession(slug: string, chapterNumber: number): StreamGeneratedBeat[] | null {
  if (!slug || chapterNumber < 1) return null
  const raw = readStorageJson<unknown>(`${KEY_PREFIX}${slug}:${chapterNumber}`, null, 'session')
  if (!raw) return null
  const parsed = parseStreamGeneratedBeats(raw)
  return parsed.length > 0 ? parsed : null
}
