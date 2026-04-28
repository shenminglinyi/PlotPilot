import {
  listExternalModelTasks,
  markExternalModelTaskAccepted,
  recordExternalModelPromptTask,
  recordExternalModelResponse,
  type ExternalModelTaskRecord,
} from '@/utils/externalModelTaskLedger'

const task: ExternalModelTaskRecord = recordExternalModelPromptTask({
  slug: 'novel-id',
  chapterNumber: 1,
  model: 'kimi',
  prompt: '请改写',
})

recordExternalModelResponse({
  slug: 'novel-id',
  taskId: task.id,
  chapterNumber: 1,
  model: 'kimi',
  content: '回稿正文',
  candidateDraftId: 'draft-id',
})

const records: ExternalModelTaskRecord[] = listExternalModelTasks('novel-id', 1)
const accepted = markExternalModelTaskAccepted('novel-id', 'draft-id')

void records
void accepted
