import type { ChapterMicroBeatPayload } from '@/api/chapter'
import type { StreamGeneratedBeat } from '@/api/workflow'

export type AutopilotStatusLike = Record<string, unknown>

export const AUTOPILOT_AFTER_OUTLINE_PLAN_SUBSTEPS = new Set([
  'chapter_plan_ready',
  'llm_calling',
  'persisting',
  'continuity_check',
  'chapter_persist',
  'audit_voice_check',
  'audit_aftermath',
  'audit_tension',
  'audit_anti_ai',
])

export function isAutopilotAfterOutlinePlanSubstep(substep: unknown): boolean {
  return AUTOPILOT_AFTER_OUTLINE_PLAN_SUBSTEPS.has(String(substep ?? ''))
}

/** Fields that can change chapter list / story tree shape; excludes high-frequency writing telemetry. */
export function buildAutopilotDeskSnapshot(status: AutopilotStatusLike | null | undefined): string {
  if (!status) return ''
  const audit = status.last_chapter_audit as AutopilotStatusLike | undefined
  const auditCh = audit != null ? (audit.chapter_number ?? audit.chapterNumber ?? '') : ''
  return [
    status.completed_chapters ?? 0,
    status.manuscript_chapters ?? 0,
    status.current_stage ?? '',
    status.current_act ?? 0,
    status.current_chapter_in_act ?? 0,
    status.current_chapter_number ?? '',
    status.needs_review === true ? '1' : '0',
    status.autopilot_status ?? '',
    auditCh,
  ].join('|')
}

/** Fingerprint only reader-visible state, avoiding heartbeat/context-token churn. */
export function buildAutopilotReactiveFingerprint(status: AutopilotStatusLike): string {
  const audit = status.last_chapter_audit as AutopilotStatusLike | undefined
  const auditMini = audit
    ? [
        audit.chapter_number ?? audit.chapterNumber ?? '',
        audit.tension ?? '',
        audit.narrative_sync_ok === true ? '1' : '0',
        audit.similarity_score ?? '',
        audit.at ?? '',
        audit.drift_alert === true ? '1' : '0',
      ].join(':')
    : ''

  return [
    status.autopilot_status,
    status.current_stage,
    status.current_chapter_number,
    status.completed_chapters,
    status.manuscript_chapters,
    status.current_beat_index,
    status.total_beats,
    Array.isArray(status.planned_micro_beats) ? status.planned_micro_beats.length : 0,
    status.outline_plan_mode,
    status.writing_substep,
    status.writing_substep_label,
    status.accumulated_words,
    status.beat_phase,
    status.beat_focus,
    status.beat_target_words,
    status.chapter_target_words,
    status.beat_remaining_budget,
    status.beat_max_words_hint,
    auditMini,
  ].join('|')
}

export function toChapterMicroBeatPayloads(beats: StreamGeneratedBeat[]): ChapterMicroBeatPayload[] {
  return beats.map(beat => ({
    description: beat.description,
    target_words: beat.target_words,
    focus: beat.focus,
    location_id: beat.location_id,
    active_action: beat.active_action,
    emotion_gap: beat.emotion_gap,
    forbidden_drift: beat.forbidden_drift,
  }))
}

export function assistedAutopilotPollDelayMs(
  failureCount: number,
  options: { baseMs?: number; maxMs?: number } = {},
): number {
  const base = options.baseMs ?? 4000
  const max = options.maxMs ?? 60_000
  const mult = Math.min(2 ** Math.min(failureCount, 8), 128)
  return Math.min(base * mult, max)
}
