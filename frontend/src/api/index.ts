// New RESTful API exports (v1)
export * from './config'
export * from './llmControl'
export * from './novel'
export { chapterApi } from './chapter'
export type {
  UpdateChapterRequest,
  ChapterReviewDTO,
  ChapterStructureDTO,
  ChapterReviewAiResponse,
} from './chapter'
export * from './bible'
export * from './workflow'
export * from './chronicles'

// Legacy API exports
export * from './book'
export * from './stats'
