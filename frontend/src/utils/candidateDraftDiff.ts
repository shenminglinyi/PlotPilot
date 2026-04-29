export interface CandidateDraftDiffSummary {
  baseWordCount: number
  candidateWordCount: number
  wordDelta: number
  similarityPercent: number
  changed: boolean
}

export type CandidateDraftParagraphDiffType = 'unchanged' | 'added' | 'removed' | 'modified'

export interface CandidateDraftParagraphDiffItem {
  index: number
  type: CandidateDraftParagraphDiffType
  baseParagraph: string
  candidateParagraph: string
  similarityPercent: number
}

function compactChars(value: string): string[] {
  return Array.from(value.replace(/\s/g, ''))
}

function diceSimilarity(a: string[], b: string[]): number {
  if (a.length === 0 && b.length === 0) return 1
  if (a.length === 0 || b.length === 0) return 0

  const counts = new Map<string, number>()
  for (const char of a) {
    counts.set(char, (counts.get(char) || 0) + 1)
  }

  let overlap = 0
  for (const char of b) {
    const count = counts.get(char) || 0
    if (count > 0) {
      overlap += 1
      counts.set(char, count - 1)
    }
  }

  return (2 * overlap) / (a.length + b.length)
}

export function buildCandidateDraftDiffSummary(
  baseContent: string,
  candidateContent: string,
): CandidateDraftDiffSummary {
  const baseChars = compactChars(baseContent)
  const candidateChars = compactChars(candidateContent)
  const similarity = diceSimilarity(baseChars, candidateChars)

  return {
    baseWordCount: baseChars.length,
    candidateWordCount: candidateChars.length,
    wordDelta: candidateChars.length - baseChars.length,
    similarityPercent: Math.round(similarity * 100),
    changed: baseContent !== candidateContent,
  }
}

function splitParagraphs(content: string): string[] {
  return content
    .split(/\n{2,}/)
    .map((item) => item.trim())
    .filter(Boolean)
}

function paragraphSimilarityPercent(baseParagraph: string, candidateParagraph: string): number {
  return Math.round(diceSimilarity(compactChars(baseParagraph), compactChars(candidateParagraph)) * 100)
}

export function buildCandidateDraftParagraphDiff(
  baseContent: string,
  candidateContent: string,
): CandidateDraftParagraphDiffItem[] {
  const baseParagraphs = splitParagraphs(baseContent)
  const candidateParagraphs = splitParagraphs(candidateContent)
  const maxLength = Math.max(baseParagraphs.length, candidateParagraphs.length)

  return Array.from({ length: maxLength }, (_, index) => {
    const baseParagraph = baseParagraphs[index] || ''
    const candidateParagraph = candidateParagraphs[index] || ''
    const similarityPercent = paragraphSimilarityPercent(baseParagraph, candidateParagraph)
    let type: CandidateDraftParagraphDiffType = 'unchanged'

    if (!baseParagraph && candidateParagraph) {
      type = 'added'
    } else if (baseParagraph && !candidateParagraph) {
      type = 'removed'
    } else if (baseParagraph !== candidateParagraph) {
      type = 'modified'
    }

    return {
      index,
      type,
      baseParagraph,
      candidateParagraph,
      similarityPercent,
    }
  })
}

export function buildPartialCandidateContent(
  baseContent: string,
  paragraphDiff: CandidateDraftParagraphDiffItem[],
  selectedIndexes: number[],
): string {
  const selected = new Set(selectedIndexes)
  const baseParagraphs = splitParagraphs(baseContent)
  const mergedParagraphs = paragraphDiff
    .map((item) => {
      if (selected.has(item.index)) {
        return item.type === 'removed' ? '' : item.candidateParagraph
      }
      return item.baseParagraph || baseParagraphs[item.index] || ''
    })
    .filter((item) => item.trim())

  return mergedParagraphs.join('\n\n')
}
