import {
  candidateDraftFocusTags,
  candidateDraftLineageTags,
  candidateDraftRewritePrompt,
  candidateDraftMemoryImpactHints,
  candidateDraftMemoryImpactPreview,
  candidateDraftSourceLabel,
  candidateDraftSourceType,
  isCandidateRewriteTask,
} from '@/utils/candidateDraftDisplay'
import type { ChapterCandidateDraftDTO } from '@/api/chapter'

const draft = {
  source: 'continuity-outline',
  metadata: {
    rewrite_focus: 'outline-deviation',
    outline_status: 'warning',
    warning_reasons: ['正文摘要与大纲重合度偏低'],
  },
} as unknown as ChapterCandidateDraftDTO

const label: string = candidateDraftSourceLabel(draft.source)
const tags: string[] = candidateDraftFocusTags(draft)
const tagType: string = candidateDraftSourceType(draft.source)
const rewriteTask: boolean = isCandidateRewriteTask(draft)
const prompt: string = candidateDraftRewritePrompt(draft)
const lineageTags: string[] = candidateDraftLineageTags({
  ...draft,
  metadata: {
    ...draft.metadata,
    rewrite_task_id: 'task-1',
  },
})
const memoryImpactHints: string[] = candidateDraftMemoryImpactHints(draft)
const memoryImpactPreview = candidateDraftMemoryImpactPreview(draft)
const firstImpact: string = memoryImpactPreview[0]?.label || ''

void label
void tags
void tagType
void rewriteTask
void prompt
void lineageTags
void memoryImpactHints
void memoryImpactPreview
void firstImpact
