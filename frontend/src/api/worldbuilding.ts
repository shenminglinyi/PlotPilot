import { apiClient } from './config'

export interface CoreRules {
  power_system: string
  progression_path?: string
  combat_resolution?: string
  physics_rules: string
  magic_tech: string
  version_rules?: string
  forbidden_methods?: string
  cost_and_limitation?: string
  resource_scarcity?: string
}

export interface Geography {
  terrain: string
  climate: string
  resources: string
  ecology: string
}

export interface Society {
  politics: string
  economy: string
  class_system: string
}

export interface Culture {
  history: string
  religion: string
  taboos: string
}

export interface DailyLife {
  food_clothing: string
  language_slang: string
  entertainment: string
}

export interface Worldbuilding {
  id: string
  novel_id: string
  schema_version?: number
  dimensions?: Record<string, Record<string, string>>
  core_rules: CoreRules
  geography: Geography
  society: Society
  culture: Culture
  daily_life: DailyLife
  created_at: string
  updated_at: string
}

export const worldbuildingApi = {
  getWorldbuilding: (slug: string): Promise<Worldbuilding> =>
    // silentGlobalFeedback: the interceptor skips toast for this call;
    // callers handle 404 (not-yet-generated) themselves.
    apiClient.get<Worldbuilding>(`/novels/${slug}/worldbuilding`, { silentGlobalFeedback: true } as never),

  updateWorldbuilding: (slug: string, data: Partial<Worldbuilding>): Promise<Worldbuilding> =>
    apiClient.put<Worldbuilding>(`/novels/${slug}/worldbuilding`, data),
}
