import {
  buildCandidateDraftDiffSummary,
  buildCandidateDraftParagraphDiff,
  buildPartialCandidateContent,
} from '@/utils/candidateDraftDiff'

const summary = buildCandidateDraftDiffSummary('原稿内容', '候选稿内容更多一些')
const paragraphDiff = buildCandidateDraftParagraphDiff('第一段\n\n第二段', '第一段\n\n第三段')
const partialContent = buildPartialCandidateContent('第一段\n\n第二段', paragraphDiff, [1])

const wordDelta: number = summary.wordDelta
const similarityPercent: number = summary.similarityPercent
const changed: boolean = summary.changed
const firstChangeType: string = paragraphDiff[0]?.type || ''
const merged: string = partialContent

void wordDelta
void similarityPercent
void changed
void firstChangeType
void merged
