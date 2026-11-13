export type ModTrustLevel = 'official' | 'cloud-verified' | 'community-unreviewed' | 'local'

export type ModRoleCategory =
  | 'all'
  | 'style-anti-ai'
  | 'opening-hook'
  | 'pacing-plot'
  | 'dialogue-voice'
  | 'review-guard'
  | 'worldbuilding'

export interface ModRoleCategoryMeta {
  key: ModRoleCategory
  label: string
  shortHint: string
}

export const MOD_ROLE_CATEGORIES: ModRoleCategoryMeta[] = [
  { key: 'all', label: '全部', shortHint: '所有叙事模组与社区能力包' },
  { key: 'style-anti-ai', label: '文风与去AI味', shortHint: '消除排比翻译腔，强化冷感与具象细节' },
  { key: 'opening-hook', label: '题材开局包', shortHint: '黄金三章切入点、核心冲突与书元设定' },
  { key: 'pacing-plot', label: '剧情节拍器', shortHint: '控制章纲密度、爽点兑现与悬念留钩' },
  { key: 'dialogue-voice', label: '人物声线与潜台词', shortHint: '告别直白传声筒，用动作停顿推进博弈' },
  { key: 'review-guard', label: '毒点审稿官', shortHint: '自动拦截人设崩塌、战力失衡与逻辑断层' },
  { key: 'worldbuilding', label: '世界观营造', shortHint: '力量体系、器物考据与势力暗线编织' },
]

export interface ModNodeOverride {
  /** 对应引擎 CPMS node_key */
  nodeKey: string
  /** 面向作者的人话环节名称 */
  nodeLabel: string
  /**
   * append_protocol: 在原节点 System 提示词尾部安全挂载模组协议块，100% 保留原有模板变量与输出契约
   * replace_system: 完整替换节点的 System 提示词（保留原 User 变量模板）
   * standalone_node: 作为独立自定义节点安装进本地库
   */
  mode: 'append_protocol' | 'replace_system' | 'standalone_node'
  systemContent: string
  userTemplate?: string
  backendCategory?: string
}

export interface ModShowcaseSample {
  scenario: string
  beforeLabel?: string
  beforeExcerpt: string
  afterLabel?: string
  afterExcerpt: string
}

export interface ModReadmeSection {
  heading: string
  body: string
}

export interface NarrativeModPack {
  id: string
  name: string
  /** 单字印章或两字符标识，显示在中性方章内 */
  glyph: string
  author: string
  repoOrOrigin: string
  trustLevel: ModTrustLevel
  roleCategory: Exclude<ModRoleCategory, 'all'>
  roleLabel: string
  /** 卡片正面展示的一句话人话价值说明 */
  summary: string
  readmeSections: ModReadmeSection[]
  version: string
  license: string
  updatedAt: string
  /** 真实数据标签，如 "内置精选"、"应用 24"、"新上架"，绝不伪造虚荣指标 */
  usageLabel: string
  /** 是否接管/增强引擎内置节点（对标 Magpie「替代内置」） */
  replacesBuiltin: boolean
  overrides: ModNodeOverride[]
  showcase?: ModShowcaseSample
  tags: string[]
  /** 若来自云端书元或社区资产，保留源 ID 便于溯源 */
  cloudSourceId?: string
}

export interface ReplacedNodeBackup {
  /** 安装 replace_system 模组前捕获的原始 System 基线快照 */
  baselineSystem: string
  /** 被替换目标节点的稳定唯一 ID（独立于 WAL 持久化） */
  targetNodeId?: string
}

export interface UnresolvedNodeMutation {
  /** 未确认落盘结果的操作类型 */
  kind: 'create' | 'patch' | 'delete'
  /** 目标节点的稳定唯一 ID */
  targetNodeId?: string
  priorSystem?: string
  priorName?: string
  priorDescription?: string
  priorUserTemplate?: string
  writtenSystem?: string
  writtenName?: string
  writtenDescription?: string
  writtenUserTemplate?: string
  /** 新建独立节点的 128-bit 随机归属凭证 */
  originToken?: string
  /** 新建独立节点写入的初始 User 模板基线 */
  initialUserTemplate?: string
  /** 自建节点 patch 提交后应同步对齐的模板基线（string 更新 / null 清除 / undefined 不变） */
  targetOwnedUserTemplate?: string | null
  /** 发起后端变更请求的客户端时间戳（ms） */
  startedAt?: number
}

export interface InstalledModRecord {
  pack: NarrativeModPack
  installedAt: string
  createdNodeIds: string[]
  ownedCustomTokens?: Record<string, string>
  ownedCustomUserTemplates?: Record<string, string>
  pendingCreateTokens?: Record<string, string>
  pendingCreateTemplates?: Record<string, string>
  patchedNodeKeys: string[]
  /** 被挂载或接管目标节点的稳定 ID 映射（nodeKey -> targetNodeId） */
  patchedNodeIds?: Record<string, string>
  replacedSystemBackups?: Record<string, ReplacedNodeBackup>
  unresolvedMutations?: Record<string, UnresolvedNodeMutation>
  walReservationPad?: string
}

export interface PlotPilotModManifest {
  schema: 'plotpilot-mod/v1'
  exportedAt: string
  pack: NarrativeModPack
}
