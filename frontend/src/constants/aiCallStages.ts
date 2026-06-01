/** 与 application/ai/ai_call_stage.py AI_CALL_STAGES 保持一致（单源在后端 /ai-traces/stages/taxonomy） */
export interface StageDef {
  key: string
  label: string
  domain: string
  semantic: 'plan' | 'write' | 'audit' | 'sync' | 'review' | 'generate'
}

/** 本地常量镜像，供 UI 离线使用；运行时优先从 API 拉取。 */
export const AI_CALL_STAGES: StageDef[] = [
  // ── Autopilot Daemon ──
  { key: 'autopilot.macro.planning',       label: '宏观规划',   domain: 'autopilot', semantic: 'plan' },
  { key: 'autopilot.act.beat_sheet',       label: '幕级节拍',   domain: 'autopilot', semantic: 'plan' },
  { key: 'autopilot.act.planning',         label: '幕级规划',   domain: 'autopilot', semantic: 'plan' },
  { key: 'autopilot.post_chapter.pipeline',label: '章后管线',   domain: 'autopilot', semantic: 'sync' },

  // ── Story Pipeline ──
  { key: 'pipeline.chapter.script',        label: '剧本生成',   domain: 'pipeline',  semantic: 'plan' },
  { key: 'pipeline.chapter.prose',         label: '正文撰写',   domain: 'pipeline',  semantic: 'write' },
  { key: 'pipeline.chapter.validate',      label: '策略校验',   domain: 'pipeline',  semantic: 'audit' },
  { key: 'pipeline.chapter.voice',         label: '文风审计',   domain: 'pipeline',  semantic: 'audit' },
  { key: 'pipeline.chapter.tension',       label: '张力打分',   domain: 'pipeline',  semantic: 'audit' },

  // ── DAG Engine ──
  { key: 'dag.planning.outline',           label: '大纲规划',   domain: 'dag',       semantic: 'plan' },
  { key: 'dag.planning.beat',              label: '节拍规划',   domain: 'dag',       semantic: 'plan' },
  { key: 'dag.execution.prose',            label: '正文执行',   domain: 'dag',       semantic: 'write' },
  { key: 'dag.execution.supplement',       label: '补充生成',   domain: 'dag',       semantic: 'write' },
  { key: 'dag.review.consistency',         label: '一致性审查', domain: 'dag',       semantic: 'audit' },
  { key: 'dag.review.quality',             label: '质量审查',   domain: 'dag',       semantic: 'audit' },
  { key: 'dag.validation.gate',            label: '门禁校验',   domain: 'dag',       semantic: 'audit' },
  { key: 'dag.anti_ai.detect',             label: '反AI检测',   domain: 'dag',       semantic: 'audit' },
  { key: 'dag.world.context',              label: '世界观上下文',domain: 'dag',       semantic: 'sync' },
  { key: 'dag.props.extract',              label: '道具提取',   domain: 'dag',       semantic: 'sync' },

  // ── Audit ──
  { key: 'audit.chapter.review',           label: '章节审稿',   domain: 'audit',     semantic: 'audit' },
  { key: 'audit.macro.refactor',           label: '宏观重构',   domain: 'audit',     semantic: 'audit' },

  // ── Analyst ──
  { key: 'analyst.style.drift',            label: '风格漂移',   domain: 'analyst',   semantic: 'audit' },
  { key: 'analyst.tension.score',          label: '张力评分',   domain: 'analyst',   semantic: 'audit' },
  { key: 'analyst.voice.analyze',          label: '声线分析',   domain: 'analyst',   semantic: 'audit' },

  // ── Blueprint ──
  { key: 'blueprint.beat.generate',        label: '节拍生成',   domain: 'blueprint', semantic: 'plan' },
  { key: 'blueprint.continuous.plan',      label: '连续规划',   domain: 'blueprint', semantic: 'plan' },
  { key: 'blueprint.volume.summary',       label: '卷总结',     domain: 'blueprint', semantic: 'sync' },

  // ── World ──
  { key: 'world.bible.generate',           label: '圣经生成',   domain: 'world',     semantic: 'generate' },
  { key: 'world.knowledge.extract',        label: '知识抽取',   domain: 'world',     semantic: 'sync' },
  { key: 'world.narrative.sync',           label: '叙事同步',   domain: 'world',     semantic: 'sync' },

  // ── Memory ──
  { key: 'memory.context.compile',         label: '上下文编译', domain: 'memory',    semantic: 'sync' },
  { key: 'memory.emotion.extract',         label: '情感抽取',   domain: 'memory',    semantic: 'sync' },

  // ── Evolution ──
  { key: 'evolution.state.change',         label: '状态变更',   domain: 'evolution', semantic: 'sync' },

  // ── Reader ──
  { key: 'reader.simulation.run',          label: '读者模拟',   domain: 'reader',    semantic: 'audit' },

  // ── Prop ──
  { key: 'prop.llm.extract',               label: '道具LLM提取',domain: 'prop',      semantic: 'sync' },

  // ── Engine / Misc ──
  { key: 'engine.scene.generate',          label: '场景生成',   domain: 'engine',    semantic: 'write' },
  { key: 'engine.scene.director',          label: '场景导演',   domain: 'engine',    semantic: 'plan' },
  { key: 'engine.chapter.bridge',          label: '章节桥接',   domain: 'engine',    semantic: 'plan' },
  { key: 'engine.beat.cot',                label: '节拍思维链', domain: 'engine',    semantic: 'plan' },
]

export const STAGE_BY_KEY: Record<string, StageDef> = {}
for (const s of AI_CALL_STAGES) { STAGE_BY_KEY[s.key] = s }

export function stageLabel(key: string): string { return STAGE_BY_KEY[key]?.label ?? key }
