export const EXTERNAL_MODEL_DRAFT_SOURCE = 'external-model'

export const EXTERNAL_MODEL_OPTIONS = [
  { label: 'Kimi', value: 'kimi' },
  { label: 'Claude', value: 'claude' },
  { label: 'ChatGPT', value: 'chatgpt' },
  { label: 'DeepSeek', value: 'deepseek' },
  { label: '其他模型', value: 'other' },
]

const MODEL_LABELS = new Map(EXTERNAL_MODEL_OPTIONS.map((item) => [item.value, item.label]))

export function externalModelLabel(model: string): string {
  return MODEL_LABELS.get(model) || model || '外部模型'
}

export function buildExternalModelDraftTitle(chapterNumber: number, model: string): string {
  return `第${chapterNumber}章 ${externalModelLabel(model)} 外部模型稿`
}

export interface ExternalModelDraftRationaleInput {
  model: string
  instruction?: string
}

export function buildExternalModelDraftRationale(input: ExternalModelDraftRationaleInput): string {
  const parts = [
    `外部模型：${externalModelLabel(input.model)}`,
    input.instruction?.trim() ? `作者要求：${input.instruction.trim()}` : '',
    '导入方式：仅保存为候选稿；采纳后才写入主稿并触发本地记忆更新。',
  ]

  return parts.filter(Boolean).join('\n')
}

export interface ExternalModelPromptInput {
  model: string
  chapterNumber: number
  taskPrompt: string
  currentContent: string
}

export function buildExternalModelPrompt(input: ExternalModelPromptInput): string {
  return [
    `你将作为 ${externalModelLabel(input.model)} 帮我改写第 ${input.chapterNumber} 章。`,
    '请只输出完整章节正文，不要输出解释、标题、分析或 Markdown 代码块。',
    '',
    '【本地记忆与任务约束】',
    input.taskPrompt.trim(),
    '',
    '【当前主稿】',
    input.currentContent.trim() || '（当前主稿为空，请根据任务约束生成整章正文。）',
    '',
    '【写作要求】',
    '1. 保留主线事实、角色关系和关键事件。',
    '2. 不要覆盖本地记忆中已确定的事实。',
    '3. 如果需要调整表达，请优先改语气、节奏、对白和动作细节。',
    '4. 输出会被导入 PlotPilot 候选稿区，由我手动采纳后才进入主稿。',
  ].join('\n')
}
