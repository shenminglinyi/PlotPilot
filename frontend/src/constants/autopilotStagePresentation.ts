/** 全托管顶栏 / 流式区共用的阶段展示（文案 + 是否实时 + 语义配色） */

export type AutopilotStageSemantic =
  | 'plan'
  | 'write'
  | 'audit'
  | 'sync'
  | 'review'
  | 'idle'
  | 'stopped'
  | 'error'
  | 'daemon_wait'

export interface AutopilotStagePresentation {
  /** 纯文案，不含「⚡」等装饰；实时态由 UI 用圆点表示 */
  text: string
  /** 共享内存快车道：顶栏显示脉动「实时」圆点 */
  live: boolean
  semantic: AutopilotStageSemantic
}

const STAGE_NAMES: Record<string, string> = {
  planning: '宏观规划',
  macro_planning: '宏观规划',
  act_planning: '幕级规划',
  writing: '撰写中',
  auditing: '审计中',
  reviewing: '待审阅确认',
  paused_for_review: '待审阅',
  completed: '已完成',
  syncing: '数据同步中',
}

function semanticForRunningStage(stage: string | undefined): AutopilotStageSemantic {
  if (!stage) return 'idle'
  if (stage === 'planning' || stage === 'macro_planning' || stage === 'act_planning') return 'plan'
  if (stage === 'writing') return 'write'
  if (stage === 'auditing') return 'audit'
  if (stage === 'syncing') return 'sync'
  if (stage === 'reviewing' || stage === 'paused_for_review') return 'review'
  return 'idle'
}

/**
 * 与 AutopilotPanel 原 `stageLabel` 逻辑一致，拆出 live 与语义配色供顶栏/主题统一使用。
 */
export function buildAutopilotStagePresentation(input: {
  current_stage?: string | null
  autopilot_status?: string | null
  writing_substep?: string | null
  writing_substep_label?: string | null
  _from_shared_memory?: boolean
  _degraded?: boolean
  audit_progress?: string | null
  isRunning: boolean
  daemonAlive: boolean
}): AutopilotStagePresentation {
  const stage = input.current_stage ?? undefined
  const apStatus = input.autopilot_status ?? undefined
  const writingSubstep = String(input.writing_substep ?? '').trim()
  const writingSubstepLabel = String(input.writing_substep_label ?? '').trim()

  /** writing 阶段内：章前规划子步骤优先于笼统的「撰写中」 */
  const writingPhaseText = (): string | null => {
    if (stage !== 'writing') return null
    if (writingSubstep === 'chapter_found') {
      return writingSubstepLabel || '章节定位'
    }
    if (writingSubstep === 'outline_planning') {
      return writingSubstepLabel || '章前规划'
    }
    if (writingSubstep === 'context_assembly') {
      return writingSubstepLabel || '组装上下文'
    }
    if (writingSubstep === 'beat_magnification') {
      return writingSubstepLabel || '节拍拆分'
    }
    if (writingSubstep === 'llm_calling') {
      return writingSubstepLabel || '正文生成中'
    }
    if (writingSubstep === 'chapter_persist' || writingSubstep === 'persisting') {
      return writingSubstepLabel || '章节落盘'
    }
    if (writingSubstep === 'pipeline_run') {
      return writingSubstepLabel || '写作管线运行中'
    }
    return null
  }
  const writingPhase = writingPhaseText()

  if (apStatus === 'stopped' || apStatus === 'error') {
    if (apStatus === 'error') return { text: '异常挂起', live: false, semantic: 'error' }
    if (stage === 'completed') return { text: '已完成', live: false, semantic: 'stopped' }
    return { text: '已停止', live: false, semantic: 'stopped' }
  }

  if (input.isRunning && !input.daemonAlive) {
    return { text: '后端处理中（等待响应...）', live: false, semantic: 'daemon_wait' }
  }

  if (input._from_shared_memory) {
    if (stage === 'auditing') {
      const progress = input.audit_progress
      if (progress === 'voice_check')
        return { text: '审计中·文风检查', live: true, semantic: 'audit' }
      if (progress === 'aftermath_pipeline')
        return { text: '审计中·章后管线', live: true, semantic: 'audit' }
      if (progress === 'tension_scoring')
        return { text: '审计中·张力打分', live: true, semantic: 'audit' }
      return { text: '审计中', live: true, semantic: 'audit' }
    }
    if (stage === 'syncing') return { text: '数据同步中', live: true, semantic: 'sync' }
    if (writingPhase) {
      const sem =
        writingSubstep === 'outline_planning' ||
        writingSubstep === 'context_assembly' ||
        writingSubstep === 'beat_magnification' ||
        writingSubstep === 'chapter_found'
          ? 'plan'
          : semanticForRunningStage(stage)
      return { text: writingPhase, live: true, semantic: sem }
    }
    const name = (stage && STAGE_NAMES[stage]) || '待机'
    return { text: name, live: true, semantic: semanticForRunningStage(stage) }
  }

  if (input._degraded) {
    if (stage === 'auditing') {
      const progress = input.audit_progress
      if (progress === 'voice_check')
        return { text: '审计中·文风检查（数据同步中...）', live: false, semantic: 'audit' }
      if (progress === 'aftermath_pipeline')
        return { text: '审计中·章后管线（数据同步中...）', live: false, semantic: 'audit' }
      if (progress === 'tension_scoring')
        return { text: '审计中·张力打分（数据同步中...）', live: false, semantic: 'audit' }
      return { text: '审计中（数据同步中...）', live: false, semantic: 'audit' }
    }
    if (stage === 'syncing') return { text: '数据同步中...', live: false, semantic: 'sync' }
    if (writingPhase) {
      const sem =
        writingSubstep === 'outline_planning' ||
        writingSubstep === 'context_assembly' ||
        writingSubstep === 'beat_magnification' ||
        writingSubstep === 'chapter_found'
          ? 'plan'
          : semanticForRunningStage(stage)
      return { text: `${writingPhase}（数据同步中...）`, live: false, semantic: sem }
    }
    const name = (stage && STAGE_NAMES[stage]) || '待机'
    return { text: `${name}（数据同步中...）`, live: false, semantic: semanticForRunningStage(stage) }
  }

  if (stage === 'auditing') {
    const progress = input.audit_progress
    if (progress === 'voice_check') return { text: '审计中（文风检查）', live: false, semantic: 'audit' }
    if (progress === 'aftermath_pipeline') return { text: '审计中（章后管线）', live: false, semantic: 'audit' }
    if (progress === 'tension_scoring') return { text: '审计中（张力打分）', live: false, semantic: 'audit' }
    return { text: '审计中', live: false, semantic: 'audit' }
  }

  if (writingPhase) {
    const sem =
      writingSubstep === 'outline_planning' ||
      writingSubstep === 'context_assembly' ||
      writingSubstep === 'beat_magnification' ||
      writingSubstep === 'chapter_found'
        ? 'plan'
        : semanticForRunningStage(stage)
    return { text: writingPhase, live: false, semantic: sem }
  }

  const name = (stage && STAGE_NAMES[stage]) || '待机'
  return { text: name, live: false, semantic: semanticForRunningStage(stage) }
}
