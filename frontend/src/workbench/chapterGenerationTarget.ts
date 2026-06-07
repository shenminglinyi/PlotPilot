export interface ChapterGenerationChapterLike {
  id: number
  number: number
  title: string
  word_count?: number
  content?: string
}

export type ProseGenerationChapterTarget = Pick<ChapterGenerationChapterLike, 'id' | 'number' | 'title'>

export interface SelectProsePrimaryGenerationTargetOptions {
  proseOnlyWorkbench: boolean
  currentChapter: ChapterGenerationChapterLike | null
  chapters: ChapterGenerationChapterLike[]
  hasChapterContent: boolean
  nextChapterNumber?: number
}

export function buildSyntheticChapterTarget(chapterNumber: number): ProseGenerationChapterTarget {
  return {
    id: chapterNumber,
    number: chapterNumber,
    title: '',
  }
}

export function getNextProseChapterNumber(chapters: ChapterGenerationChapterLike[]): number {
  const maxChapterNumber = chapters.reduce(
    (max, chapter) => Math.max(max, Number(chapter.number || 0)),
    0,
  )
  return Math.max(1, maxChapterNumber + 1)
}

export function selectNextChapterGenerationTarget(
  currentChapter: ChapterGenerationChapterLike | null,
  chapters: ChapterGenerationChapterLike[],
  nextChapterNumber = getNextProseChapterNumber(chapters),
): ProseGenerationChapterTarget | null {
  if (!currentChapter) return null

  const firstUnwrittenFutureChapter = chapters
    .filter(chapter => chapter.number > currentChapter.number)
    .sort((a, b) => a.number - b.number)
    .find(chapter => (chapter.word_count || 0) <= 0)

  if (firstUnwrittenFutureChapter) {
    return firstUnwrittenFutureChapter
  }

  return buildSyntheticChapterTarget(Math.max(currentChapter.number + 1, nextChapterNumber))
}

export function hasEditableChapterContent(
  editorContent: string | null | undefined,
  chapterListContent: string | null | undefined,
): boolean {
  return !!((editorContent ?? '').trim() || (chapterListContent ?? '').trim())
}

export function selectProsePrimaryGenerationTarget(
  options: SelectProsePrimaryGenerationTargetOptions,
): ProseGenerationChapterTarget | null {
  if (!options.proseOnlyWorkbench) return options.currentChapter
  const nextNumber = options.nextChapterNumber ?? getNextProseChapterNumber(options.chapters)
  if (!options.currentChapter) return buildSyntheticChapterTarget(nextNumber)
  return options.hasChapterContent
    ? selectNextChapterGenerationTarget(options.currentChapter, options.chapters, nextNumber)
    : options.currentChapter
}

export function getProsePrimaryActionLabel(
  proseOnlyWorkbench: boolean,
  hasChapterContent: boolean,
): string {
  if (!proseOnlyWorkbench) return '⚡ 快速生成'
  return hasChapterContent ? '生文（下一章）' : '生文'
}
