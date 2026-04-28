import {
  EXTERNAL_MODEL_DRAFT_SOURCE,
  EXTERNAL_MODEL_OPTIONS,
  buildExternalModelDraftRationale,
  buildExternalModelPrompt,
  buildExternalModelDraftTitle,
} from '@/utils/externalModelDraft'

const source: string = EXTERNAL_MODEL_DRAFT_SOURCE
const model: string = EXTERNAL_MODEL_OPTIONS[0]?.value || 'kimi'
const title: string = buildExternalModelDraftTitle(12, model)
const rationale: string = buildExternalModelDraftRationale({
  model,
  instruction: '按本地记忆约束修订。',
})
const prompt: string = buildExternalModelPrompt({
  model,
  chapterNumber: 12,
  taskPrompt: '请降低 AI 味。',
  currentContent: '原始章节正文',
})

void source
void model
void title
void rationale
void prompt
