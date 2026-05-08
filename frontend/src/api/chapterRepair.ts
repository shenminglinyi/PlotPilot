/** 章节修复 API */
import { apiClient, resolveHttpUrl } from './config'

// ── 类型 ──

export interface ShortChapterDTO {
  chapter_number: number
  title: string
  word_count: number
  status: string
  content_preview: string
  severity: 'critical' | 'warning' | 'info'
}

export interface ChapterRepairScanResult {
  novel_id: string
  threshold: number
  total_chapters: number
  short_chapters: ShortChapterDTO[]
  summary: { critical: number; warning: number; info: number }
}

export type ChapterRepairStreamEvent =
  | { type: 'phase'; phase: string; chapter_number?: number }
  | { type: 'chunk'; text: string; chapter_number?: number }
  | { type: 'done'; content: string; word_count: number; chapter_number: number }
  | { type: 'error'; message: string }
  | { type: 'session'; novel_id: string; chapters: number[]; total: number }
  | { type: 'chapter_start'; chapter_number: number; index: number; total: number }
  | { type: 'chapter_done'; chapter_number: number; index: number; total: number }
  | { type: 'session_done' }

// ── REST API ──

export const chapterRepairApi = {
  scanShortChapters: (novelId: string, threshold: number = 4000) =>
    apiClient.get<ChapterRepairScanResult>(
      `/novels/${novelId}/chapter-repair/scan?threshold=${threshold}`
    ),
}

// ── SSE 工具 ──

function parseSseDataLine(line: string): unknown | null {
  if (!line.startsWith('data: ')) return null
  try {
    return JSON.parse(line.slice(6)) as unknown
  } catch {
    return null
  }
}

// ── SSE 消费者：单章扩写 ──

export async function consumeExpandChapterStream(
  novelId: string,
  chapterNumber: number,
  targetWords: number,
  handlers: {
    onEvent?: (ev: ChapterRepairStreamEvent) => void
    onPhase?: (phase: string) => void
    onChunk?: (text: string) => void
    onDone?: (result: { content: string; word_count: number }) => void
    onError?: (message: string) => void
    signal?: AbortSignal
  }
): Promise<void> {
  const res = await fetch(resolveHttpUrl(`/api/v1/novels/${novelId}/chapter-repair/expand/${chapterNumber}`), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ target_words: targetWords }),
    signal: handlers.signal,
  })
  if (!res.ok || !res.body) {
    const t = await res.text().catch(() => '')
    handlers.onError?.(t || `HTTP ${res.status}`)
    return
  }
  await _consumeSse(res.body, handlers)
}

// ── SSE 消费者：批量扩写 ──

export async function consumeBatchExpandStream(
  novelId: string,
  chapterNumbers: number[],
  targetWords: number,
  handlers: {
    onEvent?: (ev: ChapterRepairStreamEvent) => void
    onPhase?: (phase: string) => void
    onChunk?: (text: string, chapterNumber?: number) => void
    onChapterStart?: (chapterNumber: number, index: number, total: number) => void
    onChapterDone?: (chapterNumber: number, index: number, total: number) => void
    onDone?: () => void
    onError?: (message: string) => void
    signal?: AbortSignal
  }
): Promise<void> {
  const res = await fetch(resolveHttpUrl(`/api/v1/novels/${novelId}/chapter-repair/batch-expand`), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ chapter_numbers: chapterNumbers, target_words: targetWords }),
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
          const ev = o as unknown as ChapterRepairStreamEvent
          handlers.onEvent?.(ev)

          if (typ === 'phase') {
            handlers.onPhase?.(String(o.phase ?? ''))
          } else if (typ === 'chunk') {
            handlers.onChunk?.(String(o.text ?? ''), o.chapter_number as number | undefined)
          } else if (typ === 'chapter_start') {
            handlers.onChapterStart?.(
              Number(o.chapter_number), Number(o.index), Number(o.total)
            )
          } else if (typ === 'chapter_done') {
            handlers.onChapterDone?.(
              Number(o.chapter_number), Number(o.index), Number(o.total)
            )
          } else if (typ === 'session_done') {
            handlers.onDone?.()
            return
          } else if (typ === 'error') {
            handlers.onError?.(String(o.message ?? '扩写失败'))
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

// ── 内部：通用 SSE 消费 ──

async function _consumeSse(
  body: ReadableStream<Uint8Array>,
  handlers: {
    onEvent?: (ev: ChapterRepairStreamEvent) => void
    onPhase?: (phase: string) => void
    onChunk?: (text: string) => void
    onDone?: (result: { content: string; word_count: number }) => void
    onError?: (message: string) => void
  }
): Promise<void> {
  const reader = body.getReader()
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
          const ev = o as unknown as ChapterRepairStreamEvent
          handlers.onEvent?.(ev)

          if (typ === 'phase') {
            handlers.onPhase?.(String(o.phase ?? ''))
          } else if (typ === 'chunk') {
            handlers.onChunk?.(String(o.text ?? ''))
          } else if (typ === 'done') {
            handlers.onDone?.({
              content: String(o.content ?? ''),
              word_count: Number(o.word_count ?? 0),
            })
            return
          } else if (typ === 'error') {
            handlers.onError?.(String(o.message ?? '扩写失败'))
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
