import type { BibleRelationshipEntry, CharacterDTO } from '@/api/bible'

export interface EditableVoiceProfile {
  style: string
  sentence_pattern: string
  speech_tempo: string
  metaphors?: string[]
  catchphrases?: string[]
  [key: string]: unknown
}

export interface EditableWound {
  description: string
  trigger: string
  effect: string
  [key: string]: string
}

export interface EditableRelationship {
  target: string
  relation: string
  description: string
}

export interface EditableCharacter {
  id: string
  name: string
  role: string
  description: string
  gender: string
  age: string
  appearance: string
  personality: string
  background: string
  core_motivation: string
  inner_lack: string
  mental_state: string
  mental_state_reason: string
  verbal_tic: string
  idle_behavior: string
  relationships: EditableRelationship[]
  public_profile: string
  hidden_profile: string
  reveal_chapter: number | null
  core_belief: string
  moral_taboos: string[]
  voice_profile: EditableVoiceProfile
  active_wounds: EditableWound[]
}

export interface GeneratedCharacterPayload extends Partial<CharacterDTO> {
  role?: string
  gender?: string
  age?: string
  appearance?: string
  personality?: string
  background?: string
  core_motivation?: string
  inner_lack?: string
  ghost?: string
  want?: string
  need?: string
  flaw?: string
}

export function normalizeVoiceProfile(raw: Record<string, unknown> | undefined): EditableVoiceProfile {
  return {
    ...(raw || {}),
    style: String(raw?.style ?? ''),
    sentence_pattern: String(raw?.sentence_pattern ?? ''),
    speech_tempo: String(raw?.speech_tempo ?? ''),
  }
}

export function normalizeWounds(raw: Array<Record<string, string>> | undefined): EditableWound[] {
  return (raw || []).map(wound => ({
    ...wound,
    description: String(wound.description ?? ''),
    trigger: String(wound.trigger ?? ''),
    effect: String(wound.effect ?? ''),
  }))
}

export function normalizeRelationships(raw: BibleRelationshipEntry[] | undefined): EditableRelationship[] {
  return (raw || []).map((relationship) => {
    if (typeof relationship === 'string') {
      return { target: relationship, relation: '', description: '' }
    }
    return {
      target: String(relationship.target ?? ''),
      relation: String(relationship.relation ?? ''),
      description: String(relationship.description ?? ''),
    }
  })
}

export function serializeRelationships(raw: EditableRelationship[]): BibleRelationshipEntry[] {
  return raw
    .map(relationship => ({
      target: relationship.target.trim(),
      relation: relationship.relation.trim(),
      description: relationship.description.trim(),
    }))
    .filter(relationship => relationship.target || relationship.relation || relationship.description)
}

export function createEmptyRelationship(): EditableRelationship {
  return { target: '', relation: '', description: '' }
}

export function formatRelationship(relationship: BibleRelationshipEntry | string): string {
  if (typeof relationship === 'string') return relationship
  return relationship.relation || relationship.description || relationship.target || ''
}

export function normalizeCharacterRoleAndDescription(
  role: string | undefined,
  description: string | undefined,
): { role: string; description: string } {
  let nextRole = role || ''
  let nextDescription = description || ''
  if (!nextRole && nextDescription.includes(' - ')) {
    const sepIdx = nextDescription.indexOf(' - ')
    nextRole = nextDescription.slice(0, sepIdx).trim()
    nextDescription = nextDescription.slice(sepIdx + 3).trim()
  } else if (nextRole && nextDescription.startsWith(nextRole) && nextDescription.includes(' - ')) {
    const sepIdx = nextDescription.indexOf(' - ')
    nextDescription = nextDescription.slice(sepIdx + 3).trim()
  }
  return {
    role: nextRole,
    description: nextDescription,
  }
}

export function formatCharacterDescriptionForSave(role: string, description: string): string {
  const normalized = normalizeCharacterRoleAndDescription(role, description)
  if (!normalized.role) return normalized.description
  if (!normalized.description) return normalized.role
  return `${normalized.role} - ${normalized.description}`
}

export function characterDraftKey(value: { id?: string; name?: string }): string {
  return String(value.id || value.name || '').trim().toLowerCase()
}

export function mapGeneratedCharacterToEditable(character: GeneratedCharacterPayload): EditableCharacter {
  const normalized = normalizeCharacterRoleAndDescription(character.role, character.description)
  return {
    id: character.id || '',
    name: character.name || '',
    role: normalized.role,
    description: normalized.description,
    gender: character.gender || '',
    age: character.age || '',
    appearance: character.appearance || '',
    personality: character.personality || character.flaw || '',
    background: character.background || character.ghost || '',
    core_motivation: character.core_motivation || character.want || '',
    inner_lack: character.inner_lack || character.need || '',
    mental_state: character.mental_state || '',
    mental_state_reason: character.mental_state_reason || '',
    verbal_tic: character.verbal_tic || '',
    idle_behavior: character.idle_behavior || '',
    relationships: normalizeRelationships(character.relationships || []),
    public_profile: character.public_profile || '',
    hidden_profile: character.hidden_profile || '',
    reveal_chapter: character.reveal_chapter ?? null,
    core_belief: character.core_belief || '',
    moral_taboos: [...(character.moral_taboos || [])],
    voice_profile: normalizeVoiceProfile(character.voice_profile || {}),
    active_wounds: normalizeWounds(character.active_wounds as Array<Record<string, string>> | undefined),
  }
}

export function mapCharacterToEditable(
  character: CharacterDTO,
  fallback?: Partial<EditableCharacter>,
): EditableCharacter {
  const normalized = normalizeCharacterRoleAndDescription(character.role, character.description)
  return {
    id: character.id || '',
    name: character.name || '',
    role: normalized.role,
    description: normalized.description,
    gender: character.gender || fallback?.gender || '',
    age: character.age || fallback?.age || '',
    appearance: character.appearance || fallback?.appearance || '',
    personality: character.personality || fallback?.personality || '',
    background: character.background || fallback?.background || '',
    core_motivation: character.core_motivation || fallback?.core_motivation || '',
    inner_lack: character.inner_lack || fallback?.inner_lack || '',
    mental_state: character.mental_state || '',
    mental_state_reason: character.mental_state_reason || '',
    verbal_tic: character.verbal_tic || '',
    idle_behavior: character.idle_behavior || '',
    relationships: normalizeRelationships((character.relationships && character.relationships.length
      ? character.relationships
      : fallback?.relationships) as BibleRelationshipEntry[] | undefined),
    public_profile: character.public_profile || fallback?.public_profile || '',
    hidden_profile: character.hidden_profile || fallback?.hidden_profile || '',
    reveal_chapter: character.reveal_chapter ?? null,
    core_belief: character.core_belief || fallback?.core_belief || '',
    moral_taboos: [...((character.moral_taboos && character.moral_taboos.length
      ? character.moral_taboos
      : fallback?.moral_taboos) || [])],
    voice_profile: normalizeVoiceProfile((character.voice_profile && Object.keys(character.voice_profile).length
      ? character.voice_profile
      : fallback?.voice_profile) as Record<string, unknown> | undefined),
    active_wounds: normalizeWounds((character.active_wounds && character.active_wounds.length
      ? character.active_wounds
      : fallback?.active_wounds) as Array<Record<string, string>> | undefined),
  }
}
