import { parseStreamGeneratedBeats, type StreamGeneratedBeat } from '../api/workflow'

const KEY_PREFIX = 'pp-assist-beats:'

export function persistAssistBeatSession(
  slug: string,
  chapterNumber: number,
  beats: StreamGeneratedBeat[],
): void {
  if (!slug || chapterNumber < 1 || !beats.length) return
  try {
    sessionStorage.setItem(`${KEY_PREFIX}${slug}:${chapterNumber}`, JSON.stringify(beats))
  } catch {
    /* quota / private mode */
  }
}

export function loadAssistBeatSession(slug: string, chapterNumber: number): StreamGeneratedBeat[] | null {
  if (!slug || chapterNumber < 1) return null
  try {
    const raw = sessionStorage.getItem(`${KEY_PREFIX}${slug}:${chapterNumber}`)
    if (!raw) return null
    const parsed = parseStreamGeneratedBeats(JSON.parse(raw) as unknown)
    return parsed.length > 0 ? parsed : null
  } catch {
    return null
  }
}
