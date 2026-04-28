export interface CandidateDraftDiffSummary {
  baseWordCount: number
  candidateWordCount: number
  wordDelta: number
  similarityPercent: number
  changed: boolean
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
