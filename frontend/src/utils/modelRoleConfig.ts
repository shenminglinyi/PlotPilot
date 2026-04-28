export type ModelRole = 'writer' | 'supervisor' | 'both'

export interface ModelProfile {
  value: string
  label: string
  role: ModelRole
  note?: string
}

export interface ModelRoleConfig {
  writingModel: string
  supervisorModel: string
  profiles: ModelProfile[]
}

export const MODEL_ROLE_CONFIG_STORAGE_KEY = 'plotpilot.modelRoleConfig.v1'
export const MODEL_ROLE_CONFIG_UPDATED_EVENT = 'plotpilot:model-role-config-updated'

export const DEFAULT_MODEL_PROFILES: ModelProfile[] = [
  { value: 'kimi', label: 'Kimi', role: 'writer', note: '适合长文本正文写作' },
  { value: 'claude', label: 'Claude', role: 'both', note: '适合风格改写和长上下文审阅' },
  { value: 'chatgpt', label: 'ChatGPT / GPT', role: 'supervisor', note: '适合记忆审计、结构化检查和修稿方案' },
  { value: 'deepseek', label: 'DeepSeek', role: 'both', note: '适合辅助推理和改写' },
  { value: 'other', label: '其他模型', role: 'both' },
]

export const DEFAULT_MODEL_ROLE_CONFIG: ModelRoleConfig = {
  writingModel: 'kimi',
  supervisorModel: 'chatgpt',
  profiles: DEFAULT_MODEL_PROFILES,
}

function canUseForRole(profile: ModelProfile, role: 'writer' | 'supervisor') {
  return profile.role === role || profile.role === 'both'
}

function normalizeProfile(profile: ModelProfile): ModelProfile {
  const value = profile.value.trim() || profile.label.trim().toLowerCase().replace(/\s+/g, '-')
  return {
    value,
    label: profile.label.trim() || value,
    role: profile.role || 'both',
    note: profile.note?.trim() || '',
  }
}

export function loadModelRoleConfig(): ModelRoleConfig {
  if (typeof window === 'undefined') return DEFAULT_MODEL_ROLE_CONFIG
  try {
    const raw = window.localStorage.getItem(MODEL_ROLE_CONFIG_STORAGE_KEY)
    if (!raw) return DEFAULT_MODEL_ROLE_CONFIG
    const parsed = JSON.parse(raw) as Partial<ModelRoleConfig>
    const profiles = Array.isArray(parsed.profiles)
      ? parsed.profiles.map(normalizeProfile)
      : DEFAULT_MODEL_PROFILES
    return {
      writingModel: parsed.writingModel || DEFAULT_MODEL_ROLE_CONFIG.writingModel,
      supervisorModel: parsed.supervisorModel || DEFAULT_MODEL_ROLE_CONFIG.supervisorModel,
      profiles,
    }
  } catch {
    return DEFAULT_MODEL_ROLE_CONFIG
  }
}

export function saveModelRoleConfig(config: ModelRoleConfig): ModelRoleConfig {
  const normalized: ModelRoleConfig = {
    writingModel: config.writingModel || DEFAULT_MODEL_ROLE_CONFIG.writingModel,
    supervisorModel: config.supervisorModel || DEFAULT_MODEL_ROLE_CONFIG.supervisorModel,
    profiles: config.profiles.map(normalizeProfile),
  }
  if (typeof window !== 'undefined') {
    window.localStorage.setItem(MODEL_ROLE_CONFIG_STORAGE_KEY, JSON.stringify(normalized))
    window.dispatchEvent(new CustomEvent(MODEL_ROLE_CONFIG_UPDATED_EVENT, { detail: normalized }))
  }
  return normalized
}

export function getModelOptions(config: ModelRoleConfig, role: 'writer' | 'supervisor') {
  return config.profiles
    .filter(profile => canUseForRole(profile, role))
    .map(profile => ({
      label: profile.label,
      value: profile.value,
    }))
}

export function getModelLabel(config: ModelRoleConfig, model: string): string {
  return config.profiles.find(profile => profile.value === model)?.label || model || '外部模型'
}

export function upsertModelProfile(config: ModelRoleConfig, profile: ModelProfile): ModelRoleConfig {
  const normalized = normalizeProfile(profile)
  const profiles = config.profiles.filter(item => item.value !== normalized.value)
  return {
    ...config,
    profiles: [...profiles, normalized],
  }
}

export function buildModelRoleSummary(config: ModelRoleConfig): string {
  const writingModel = getModelLabel(config, config.writingModel)
  const supervisorModel = getModelLabel(config, config.supervisorModel)
  return `写作模型：${writingModel}；审稿/记忆模型：${supervisorModel}`
}
