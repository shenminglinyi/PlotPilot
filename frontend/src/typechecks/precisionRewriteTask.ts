import {
  PRECISION_REWRITE_SOURCE,
  buildPrecisionRewriteRationale,
} from '@/utils/precisionRewriteTask'

const rationale: string = buildPrecisionRewriteRationale({
  objective: '降低 AI 味',
  instruction: '保留事件，只调整表达。',
  targetExcerpt: '他沉默片刻，转身离开。',
})

const source: string = PRECISION_REWRITE_SOURCE

void rationale
void source
