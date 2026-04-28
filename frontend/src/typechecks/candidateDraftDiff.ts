import { buildCandidateDraftDiffSummary } from '@/utils/candidateDraftDiff'

const summary = buildCandidateDraftDiffSummary('原稿内容', '候选稿内容更多一些')

const wordDelta: number = summary.wordDelta
const similarityPercent: number = summary.similarityPercent
const changed: boolean = summary.changed

void wordDelta
void similarityPercent
void changed
