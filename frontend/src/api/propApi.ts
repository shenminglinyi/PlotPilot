import { apiClient } from './config'

export interface PropDTO {
  id: string
  novel_id: string
  name: string
  description: string
  aliases: string[]
  prop_category: 'WEAPON' | 'ARTIFACT' | 'TOOL' | 'CONSUMABLE' | 'TOKEN' | 'OTHER'
  lifecycle_state: 'DORMANT' | 'INTRODUCED' | 'ACTIVE' | 'DAMAGED' | 'RESOLVED'
  introduced_chapter: number | null
  resolved_chapter: number | null
  holder_character_id: string | null
  attributes: Record<string, unknown>
  created_at: string
  updated_at: string
}

export interface PropEventDTO {
  id: string
  prop_id: string
  chapter_number: number
  event_type: string
  source: 'AUTO_PATTERN' | 'AUTO_LLM' | 'MANUAL'
  description: string
  actor_character_id: string | null
  from_holder_id: string | null
  to_holder_id: string | null
  created_at: string
}

export const LIFECYCLE_LABELS: Record<PropDTO['lifecycle_state'], string> = {
  DORMANT:    '未登场',
  INTRODUCED: '已登场',
  ACTIVE:     '使用中',
  DAMAGED:    '损毁',
  RESOLVED:   '已结局',
}

export const LIFECYCLE_TAG_TYPES: Record<PropDTO['lifecycle_state'], 'default' | 'info' | 'success' | 'warning' | 'error'> = {
  DORMANT:    'default',
  INTRODUCED: 'info',
  ACTIVE:     'success',
  DAMAGED:    'error',
  RESOLVED:   'default',
}

export const CATEGORY_LABELS: Record<PropDTO['prop_category'], string> = {
  WEAPON:     '武器',
  ARTIFACT:   '法器',
  TOOL:       '工具',
  CONSUMABLE: '消耗品',
  TOKEN:      '信物',
  OTHER:      '其他',
}

export const CATEGORY_ICONS: Record<PropDTO['prop_category'], string> = {
  WEAPON:     '🗡',
  ARTIFACT:   '🔮',
  TOOL:       '🔧',
  CONSUMABLE: '💊',
  TOKEN:      '📜',
  OTHER:      '📦',
}

export const propApi = {
  list: (novelId: string) =>
    apiClient.get<PropDTO[]>(`/novels/${novelId}/props`) as unknown as Promise<PropDTO[]>,

  create: (novelId: string, body: Partial<PropDTO> & { name: string }) =>
    apiClient.post<PropDTO>(`/novels/${novelId}/props`, body) as unknown as Promise<PropDTO>,

  get: (novelId: string, propId: string) =>
    apiClient.get<PropDTO>(`/novels/${novelId}/props/${propId}`) as unknown as Promise<PropDTO>,

  patch: (novelId: string, propId: string, body: Partial<PropDTO>) =>
    apiClient.patch<PropDTO>(`/novels/${novelId}/props/${propId}`, body) as unknown as Promise<PropDTO>,

  remove: (novelId: string, propId: string) =>
    apiClient.delete(`/novels/${novelId}/props/${propId}`),

  listEvents: (novelId: string, propId: string) =>
    apiClient.get<PropEventDTO[]>(`/novels/${novelId}/props/${propId}/events`) as unknown as Promise<PropEventDTO[]>,

  createEvent: (novelId: string, propId: string, body: { chapter_number: number; event_type: string; description?: string; actor_character_id?: string | null; from_holder_id?: string | null; to_holder_id?: string | null }) =>
    apiClient.post<PropEventDTO>(`/novels/${novelId}/props/${propId}/events`, body) as unknown as Promise<PropEventDTO>,
}
