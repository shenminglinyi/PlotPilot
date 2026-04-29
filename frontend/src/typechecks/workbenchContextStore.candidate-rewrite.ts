import { useWorkbenchContextStore } from '@/stores/workbenchContextStore'
import type { ChapterCandidateDraftDTO } from '@/api/chapter'

const store = useWorkbenchContextStore()

store.openCandidateRewriteSeed({
  slug: 'demo-slug',
  chapterNumber: 12,
  source: 'continuity-outline',
  title: '第12章 候选改稿',
  rationale: '根据连续性提醒创建候选改稿。',
  content: '示例正文',
})

store.openCandidateRewriteExecution({
  slug: 'demo-slug',
  draft: {
    id: 'draft-1',
    novel_id: 'demo-slug',
    chapter_number: 12,
    branch_name: 'main',
    source: 'continuity-outline',
    status: 'draft',
    title: '第12章 候选改稿',
    content: '示例正文',
    rationale: '根据连续性提醒创建候选改稿。',
    metadata: {
      rewrite_focus: 'outline-deviation',
    },
    created_at: '2026-04-28T00:00:00Z',
    updated_at: '2026-04-28T00:00:00Z',
  } satisfies ChapterCandidateDraftDTO,
})
