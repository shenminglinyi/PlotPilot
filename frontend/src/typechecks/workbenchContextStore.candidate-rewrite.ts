import { useWorkbenchContextStore } from '@/stores/workbenchContextStore'

const store = useWorkbenchContextStore()

store.openCandidateRewriteSeed({
  slug: 'demo-slug',
  chapterNumber: 12,
  source: 'continuity-outline',
  title: '第12章 候选改稿',
  rationale: '根据连续性提醒创建候选改稿。',
  content: '示例正文',
})
