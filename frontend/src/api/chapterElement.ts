/**
 * 章节元素关联 API
 * 管理章节与 Bible 元素（人物/地点/道具/事件）的关联
 */

import { apiClient } from './config'

// ==================== 类型 ====================

export type ElementType = 'character' | 'location' | 'item' | 'organization' | 'event'
export type RelationType = 'appears' | 'mentioned' | 'scene' | 'uses' | 'involved' | 'occurs'
export type Importance = 'major' | 'normal' | 'minor'

export interface ChapterElementDTO {
  id: string
  chapter_id: string
  element_type: ElementType
  element_id: string
  relation_type: RelationType
  importance: Importance
  appearance_order: number | null
  notes: string | null
  created_at: string
}

export interface ChapterElementCreate {
  element_type: ElementType
  element_id: string
  relation_type: RelationType
  importance?: Importance
  appearance_order?: number
  notes?: string
}

// ==================== API ====================

export const chapterElementApi = {
  /** GET /api/v1/chapters/{chapter_id}/elements */
  getElements(chapterId: string, elementType?: ElementType): Promise<{ success: boolean; data: ChapterElementDTO[] }> {
    return apiClient.get(
      `/api/v1/chapters/${chapterId}/elements`,
      { params: elementType ? { element_type: elementType } : undefined }
    ) as unknown as Promise<{ success: boolean; data: ChapterElementDTO[] }>
  },

  /** POST /api/v1/chapters/{chapter_id}/elements */
  addElement(chapterId: string, data: ChapterElementCreate): Promise<{ success: boolean; data: ChapterElementDTO }> {
    return apiClient.post(
      `/api/v1/chapters/${chapterId}/elements`,
      data
    ) as unknown as Promise<{ success: boolean; data: ChapterElementDTO }>
  },

  /** PUT /api/v1/chapters/{chapter_id}/elements（批量替换） */
  batchUpdate(chapterId: string, elements: ChapterElementCreate[]): Promise<{ success: boolean; data: { updated_count: number; elements: ChapterElementDTO[] } }> {
    return apiClient.put(
      `/api/v1/chapters/${chapterId}/elements`,
      { elements }
    ) as unknown as Promise<{ success: boolean; data: { updated_count: number; elements: ChapterElementDTO[] } }>
  },

  /** DELETE /api/v1/chapters/{chapter_id}/elements/{element_id} */
  deleteElement(chapterId: string, elementId: string): Promise<{ success: boolean; message: string }> {
    return apiClient.delete(
      `/api/v1/chapters/${chapterId}/elements/${elementId}`
    ) as unknown as Promise<{ success: boolean; message: string }>
  },

  /** GET /api/v1/chapters/elements/{element_type}/{element_id}/chapters — 反向查哪些章用了该元素 */
  getElementChapters(elementType: ElementType, elementId: string): Promise<{ success: boolean; data: { appearance_count: number; chapters: unknown[] } }> {
    return apiClient.get(
      `/api/v1/chapters/elements/${elementType}/${elementId}/chapters`
    ) as unknown as Promise<{ success: boolean; data: { appearance_count: number; chapters: unknown[] } }>
  },
}
