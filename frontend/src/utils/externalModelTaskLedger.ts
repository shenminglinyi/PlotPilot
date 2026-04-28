export interface ExternalModelTaskRecord {
  id: string
  slug: string
  chapterNumber: number
  model: string
  prompt: string
  instruction: string
  sourceDraftId: string
  candidateDraftId: string
  responsePreview: string
  status: 'prompted' | 'imported' | 'accepted'
  createdAt: string
  updatedAt: string
}

const STORAGE_KEY = 'plotpilot.externalModelTaskLedger.v1'

function nowIso() {
  return new Date().toISOString()
}

function createTaskId(chapterNumber: number) {
  return `ext-${chapterNumber}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}

function readAll(): ExternalModelTaskRecord[] {
  if (typeof window === 'undefined') return []
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY)
    return raw ? JSON.parse(raw) as ExternalModelTaskRecord[] : []
  } catch {
    return []
  }
}

function writeAll(records: ExternalModelTaskRecord[]) {
  if (typeof window === 'undefined') return
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(records.slice(-200)))
}

export function listExternalModelTasks(slug: string, chapterNumber?: number): ExternalModelTaskRecord[] {
  return readAll()
    .filter(item => item.slug === slug && (chapterNumber == null || item.chapterNumber === chapterNumber))
    .sort((a, b) => b.updatedAt.localeCompare(a.updatedAt))
}

export function recordExternalModelPromptTask(input: {
  slug: string
  chapterNumber: number
  model: string
  prompt: string
  instruction?: string
  sourceDraftId?: string
}): ExternalModelTaskRecord {
  const records = readAll()
  const timestamp = nowIso()
  const task: ExternalModelTaskRecord = {
    id: createTaskId(input.chapterNumber),
    slug: input.slug,
    chapterNumber: input.chapterNumber,
    model: input.model,
    prompt: input.prompt,
    instruction: input.instruction || '',
    sourceDraftId: input.sourceDraftId || '',
    candidateDraftId: '',
    responsePreview: '',
    status: 'prompted',
    createdAt: timestamp,
    updatedAt: timestamp,
  }
  writeAll([...records, task])
  return task
}

export function recordExternalModelResponse(input: {
  slug: string
  taskId?: string
  chapterNumber: number
  model: string
  prompt?: string
  instruction?: string
  content: string
  candidateDraftId: string
}): ExternalModelTaskRecord {
  const records = readAll()
  const timestamp = nowIso()
  const index = input.taskId ? records.findIndex(item => item.id === input.taskId) : -1
  const preview = input.content.trim().slice(0, 160)

  if (index >= 0) {
    const updated = {
      ...records[index],
      model: input.model || records[index].model,
      instruction: input.instruction ?? records[index].instruction,
      candidateDraftId: input.candidateDraftId,
      responsePreview: preview,
      status: 'imported' as const,
      updatedAt: timestamp,
    }
    records[index] = updated
    writeAll(records)
    return updated
  }

  const created: ExternalModelTaskRecord = {
    id: createTaskId(input.chapterNumber),
    slug: input.slug,
    chapterNumber: input.chapterNumber,
    model: input.model,
    prompt: input.prompt || '',
    instruction: input.instruction || '',
    sourceDraftId: '',
    candidateDraftId: input.candidateDraftId,
    responsePreview: preview,
    status: 'imported',
    createdAt: timestamp,
    updatedAt: timestamp,
  }
  writeAll([...records, created])
  return created
}

export function markExternalModelTaskAccepted(slug: string, candidateDraftId: string): ExternalModelTaskRecord | null {
  const records = readAll()
  const index = records.findIndex(item => item.slug === slug && item.candidateDraftId === candidateDraftId)
  if (index < 0) return null
  records[index] = {
    ...records[index],
    status: 'accepted',
    updatedAt: nowIso(),
  }
  writeAll(records)
  return records[index]
}
