import type { NarrativeModPack } from './types'

/**
 * 墨枢官方精选叙事模组包（Curated Narrative Mods）
 * 全部精确绑定 PlotPilot 真实内置 CPMS node_key，采用无损协议块挂载（append_protocol），
 * 100% 保留原有 {context} / {outline} 等变量插槽与 Pydantic 输出契约。
 */
export const CURATED_MOD_PACKS: NarrativeModPack[] = [
  {
    id: 'mod-cold-realism-anti-ai',
    name: '冷峻纪实 · 深度去 AI 味滤镜',
    glyph: '纪',
    author: '墨枢社区精选',
    repoOrOrigin: 'github:plotpilot-mods/cold-realism-filter',
    trustLevel: 'official',
    roleCategory: 'style-anti-ai',
    roleLabel: '文风滤镜',
    summary: '以具象器物动作与生理冷感替代空泛情绪总结，根治“嘴角勾起弧度、眼中闪过精光、排比升华”等网文重灾区。',
    version: 'v1.4.0',
    license: 'MIT',
    updatedAt: '2026-11-10',
    usageLabel: '官方精选',
    replacesBuiltin: true,
    tags: ['去AI味', '冷峻叙事', '动作显影', '悬疑硬派'],
    readmeSections: [
      {
        heading: '解决什么创作痛点',
        body: '大模型默认生成小说时极易滑向“心理说明书”：高频出现“心中五味杂陈”“空气仿佛凝固了”“他深知这一步意味着什么”。本模组在正文生成与场景描写两处核心节点注入物理显影协议，强制将抽象情绪转化为可拍摄的手部动作、视线落点与环境器物变化。',
      },
      {
        heading: '作用范围与回滚保障',
        body: '启用后自动增强「主工作流章节生成」与「场景正文生成」两个内置节点，不改动任何大纲变量与人物设定读取逻辑。随时可在「已安装」页签一键停用并无损回滚至初始内置版本。',
      },
    ],
    showcase: {
      scenario: '审讯室博弈场景 · 同一大纲输入对比',
      beforeLabel: '未启用模组（典型 AI 总结腔）',
      beforeExcerpt: '听到这个名字，陆沉的眼中闪过一丝不易察觉的寒芒，嘴角勾起一抹冷笑。空气在这一刻仿佛凝固了，他心中清楚，对方已经彻底露出了狐狸尾巴，接下来的每一步都将是万丈深渊。',
      afterLabel: '启用本模组后（具象动作显影）',
      afterExcerpt: '陆沉把记号笔的笔帽按回去，“咔”地一声轻响。他没抬头看审讯桌对面的人，只用指腹把卷宗折角抹平：“城南冷库那批货，签收单上的墨迹还没干。你现在改口，来得及吗？”',
    },
    overrides: [
      {
        nodeKey: 'chapter-generation-main',
        nodeLabel: '主工作流章节生成',
        mode: 'append_protocol',
        systemContent: [
          '【墨枢模组协议 · 冷峻纪实去AI味 v1.4】',
          '1. 严禁直接总结人物心理状态（禁用“心中暗道/深知/五味杂陈/掀起惊涛骇浪”），所有心理波动必须通过具体肢体小动作、呼吸停顿或对身边器物的操作呈现。',
          '2. 严禁网文套路化五官描写（禁用“嘴角勾起一抹弧度/眼中闪过一丝精光/瞳孔骤缩”）。',
          '3. 段落结尾禁止拔高升华或排比抒情，落在具体未完的动作、冷淡的一句反问或环境声响上即止。',
        ].join('\n'),
      },
      {
        nodeKey: 'scene-generation',
        nodeLabel: '场景正文生成',
        mode: 'append_protocol',
        systemContent: [
          '【墨枢模组协议 · 场景物理触感增强】',
          '写环境时拒绝形容词堆砌（如“阴森恐怖、金碧辉煌”），必须写出两处以上可触摸的材质温度、光线切角或背景杂音（如日光灯管电流声、潮湿桌面粘手、铁门锈渣掉落）。',
        ].join('\n'),
      },
    ],
  },
  {
    id: 'mod-subtext-blade-dialogue',
    name: '话留三分 · 高张力潜台词对白包',
    glyph: '潜',
    author: '墨枢社区精选',
    repoOrOrigin: 'github:plotpilot-mods/subtext-dialogue',
    trustLevel: 'official',
    roleCategory: 'dialogue-voice',
    roleLabel: '对白增强',
    summary: '打破全员“信息传声筒”弊病，让角色答非所问、借事喻人，用倒茶、看表与沉默构筑真实身份压迫感。',
    version: 'v1.2.1',
    license: 'MIT',
    updatedAt: '2026-11-08',
    usageLabel: '官方精选',
    replacesBuiltin: true,
    tags: ['潜台词', '人物声线', '权谋智斗', '拒绝说明文对白'],
    readmeSections: [
      {
        heading: '核心能力说明',
        body: 'AI 写对话最容易犯的错是“甲问什么，乙就老老实实解释什么”，甚至在台词里帮读者复述世界观设定。本模组接管「角色对白生成」与「Anti-AI 角色状态锁」，强制每轮对话存在隐瞒、试探或利益错位，高位者少字短句，心虚者找补细节。',
      },
    ],
    showcase: {
      scenario: '宗门长老敲打越界弟子',
      beforeLabel: '未启用模组（直白传声筒）',
      beforeExcerpt: '“林凡，你昨天擅闯藏经阁三层，我已经知道了！虽然你天赋异禀，但宗门规矩不可废，如果你不交出那卷残图，执法堂绝不会轻饶你！”',
      afterLabel: '启用本模组后（潜台词与身份位差）',
      afterExcerpt: '徐长老拿茶盖撇去浮沫，眼皮都没抬：“三层东面那扇窗，铰链坏了三年没人修，昨晚倒是被人上了油。”他把茶盏推到桌沿，“外门今年冬衣还没发齐，执法堂最近闲得很。”',
    },
    overrides: [
      {
        nodeKey: 'dialogue-generation',
        nodeLabel: '角色对白生成',
        mode: 'append_protocol',
        systemContent: [
          '【墨枢模组协议 · 潜台词博弈对白 v1.2】',
          '1. 禁止“问答机式”对白：面对尖锐问题，角色应优先采用反问、转移话题到手头琐事、只答一半或故意误解来试探底线。',
          '2. 严禁在台词中大段科普双方早已熟知的背景设定（避免“众所周知我们家族……”）。',
          '3. 身份与句长挂钩：处于上位或掌控局面的一方台词精炼短促，绝不主动解释理由；处于防守或焦虑的一方才会抢话、重复修饰词。',
        ].join('\n'),
      },
      {
        nodeKey: 'anti-ai-character-state-lock',
        nodeLabel: '角色状态锁协议',
        mode: 'append_protocol',
        systemContent: [
          '【墨枢模组协议 · 声线辨识度锚定】',
          '严格区分不同人物的口语颗粒度（方言虚词、行业黑话、断句习惯），遮住人名也能凭语调一眼分辨说话者。',
        ].join('\n'),
      },
    ],
  },
  {
    id: 'mod-golden-three-poison-guard',
    name: '黄金三章 · 劝退毒点严审官',
    glyph: '审',
    author: '墨枢社区精选',
    repoOrOrigin: 'github:plotpilot-mods/golden-chapter-auditor',
    trustLevel: 'official',
    roleCategory: 'review-guard',
    roleLabel: '审稿插件',
    summary: '按商业连载留存标准扫描章节：精准揪出开局设定灌水、主角无收益憋屈、反派降智送脸与伏笔遗忘。',
    version: 'v1.3.0',
    license: 'MIT',
    updatedAt: '2026-11-09',
    usageLabel: '官方精选',
    replacesBuiltin: true,
    tags: ['毒点排查', '黄金三章', '追读留存', 'OOC拦截'],
    readmeSections: [
      {
        heading: '检查哪些网文致命伤',
        body: '普通 AI 审稿只会夸“文笔流畅、情节紧凑”。本模组专门按商业网文责编视角重构审稿标准，重点拦截四类直接导致读者弃书的毒点：1）连续 400 字无人物行动的世界观百科全书；2）主角吃亏受辱却超过两章无实质反制筹码；3）知情边界混乱（角色突然知道自己不在场的信息）；4）章末悬念断在平淡睡觉或赶路上。',
      },
    ],
    showcase: {
      scenario: '审稿报告输出颗粒度对比',
      beforeLabel: '默认审稿反馈',
      beforeExcerpt: '本章整体节奏较好，主角与家族的矛盾进一步升级，建议适当丰富环境描写以增强代入感。',
      afterLabel: '启用本模组后（责编级毒点定位）',
      afterExcerpt: '【高危劝退预警 · 第2段-第5段】开篇连续 580 字介绍九品灵根划分，主角零行动，前30秒划走率极高；建议删去设定百科，直接从当铺掌柜压价三成、主角当场掰断验灵石切入。',
    },
    overrides: [
      {
        nodeKey: 'review-character-consistency',
        nodeLabel: '人物一致性与OOC检查',
        mode: 'append_protocol',
        systemContent: [
          '【墨枢模组协议 · 商业连载人设与知情权红线】',
          '1. 严查知情权越界（POV Firewall）：核对角色台词与决策是否引用了其当前视角尚未获知的情报。',
          '2. 严查主角被动憋屈：若主角在本章遭遇打压或危机，必须核验其是否展现出符合人设的观察、留后手或反击准备，杜绝无脑隐忍与圣母原谅。',
        ].join('\n'),
      },
      {
        nodeKey: 'review-storyline-consistency',
        nodeLabel: '故事线连贯性与留存检查',
        mode: 'append_protocol',
        systemContent: [
          '【墨枢模组协议 · 追读留存毒点扫描】',
          '重点标记：连续超过 350 字的无冲突设定说明段、无因果铺垫的机械降神救援、以及章末缺乏具体利益/危机钩子的平淡收尾，并给出精确到段落的可执行删改方案。',
        ].join('\n'),
      },
    ],
  },
  {
    id: 'mod-webnovel-fast-pacing-beat',
    name: '快节奏爽点 · 节拍推进引擎',
    glyph: '节',
    author: '墨枢社区精选',
    repoOrOrigin: 'github:plotpilot-mods/fast-pacing-beats',
    trustLevel: 'official',
    roleCategory: 'pacing-plot',
    roleLabel: '节拍引擎',
    summary: '压缩无效寒暄与过场赶路，强制每章构建“微目标受阻 → 信息差破局 → 新悬念抛出”的紧凑叙事闭环。',
    version: 'v1.1.2',
    license: 'MIT',
    updatedAt: '2026-11-05',
    usageLabel: '官方精选',
    replacesBuiltin: true,
    tags: ['快节奏', '章纲拆解', '期待感管理', '拒绝水字数'],
    readmeSections: [
      {
        heading: '如何改善长篇水字数与拖沓',
        body: '写到中后期最怕一章三千字全在“吃饭、赶路、互相客套”，主线一步没推。本模组介入「节拍表拆解」与「章纲节拍划分」，要求每个节拍（Beat）必须产生明确的状态改变（筹码增减、关系翻转或真相揭露），砍掉一切无信息增量的过渡水戏。',
      },
    ],
    overrides: [
      {
        nodeKey: 'beat-sheet-decomposition',
        nodeLabel: '节拍表拆解',
        mode: 'append_protocol',
        systemContent: [
          '【墨枢模组协议 · 零水戏高密度节拍铁律】',
          '1. 每一个节拍必须回答“这一幕结束后，局势或人物筹码发生了什么不可逆的变化”；若无变化，立即合并或删除该过场。',
          '2. 严禁安排纯寒暄、纯赶路、纯重复已知情报的过渡节拍；转场直接切入冲突发生的那一秒。',
          '3. 章末最后一个节拍必须落在“预期反转”或“倒计时危机逼近”的瞬态画面上。',
        ].join('\n'),
      },
      {
        nodeKey: 'outline-beat-partition',
        nodeLabel: '章纲节拍划分',
        mode: 'append_protocol',
        systemContent: [
          '【墨枢模组协议 · 黄金冷热波形分配】',
          '单章内保持“压迫蓄力 → 局部破局兑现 → 更大暗流浮现”的张力梯度，避免整章平铺直叙或连续高压疲劳。',
        ].join('\n'),
      },
    ],
  },
  {
    id: 'mod-oriental-mystery-folklore',
    name: '诡秘民俗 · 器物考据与暗线营造',
    glyph: '诡',
    author: '白鹭洲 (社区贡献)',
    repoOrOrigin: 'github:bailuzhou/plotpilot-folklore-pack',
    trustLevel: 'cloud-verified',
    roleCategory: 'worldbuilding',
    roleLabel: '世界观营造',
    summary: '专为中式悬疑、志怪仙侠与蒸汽诡秘题材打造：用旧规矩、手艺行话与日常异变构建毛骨悚然的真实感。',
    version: 'v0.9.4',
    license: 'Apache-2.0',
    updatedAt: '2026-11-02',
    usageLabel: '社区认证',
    replacesBuiltin: true,
    tags: ['民俗志怪', '诡秘悬疑', '规则怪谈', '器物考据'],
    readmeSections: [
      {
        heading: '模组特色',
        body: '真正的诡异感从不靠“恐怖至极”四个字，而是靠“违反常识的生活死规矩”——比如夜里掌灯不添第三次油、当铺收死契不收活扣。本模组同时强化「世界观与文风生成」和「场景正文生成」，在设定阶段自动生成行业禁忌与民俗器物锚点。',
      },
    ],
    showcase: {
      scenario: '古镇客栈入夜场景',
      beforeLabel: '常规生成',
      beforeExcerpt: '这家客栈看起来十分诡异，四周弥漫着浓浓的黑雾，老板娘的笑容让人不寒而栗，似乎隐藏着可怕的秘密。',
      afterLabel: '启用本模组后',
      afterExcerpt: '柜台上的算盘珠子是用老羊骨磨的，缺了最底下那排五珠。掌柜把铜钥匙往桌上一搁，顺手将门栓反插进左边槽口：“戌时过后，走廊里有人喊你名字，应一声就成，别开门看鞋尖朝哪。”',
    },
    overrides: [
      {
        nodeKey: 'bible-worldbuilding',
        nodeLabel: '世界观与文风生成',
        mode: 'append_protocol',
        systemContent: [
          '【墨枢模组协议 · 民俗器物与行规锚定】',
          '构建世界观设定时，拒绝宏大空洞的神魔编年史，优先设计底层生计行当、器物材质、交易暗语与日常行为禁忌（“不解释为什么，只交代违背后的具体代价”）。',
        ].join('\n'),
      },
      {
        nodeKey: 'scene-generation',
        nodeLabel: '场景正文生成',
        mode: 'append_protocol',
        systemContent: [
          '【墨枢模组协议 · 日常异变悬疑感】',
          '用极其平实克制的生活细节衬托不合常理的微小异样，禁止使用感叹号一惊一乍。',
        ].join('\n'),
      },
    ],
  },
  {
    id: 'mod-high-concept-opening-engine',
    name: '强反差开局 · 书元利益钩子生成器',
    glyph: '钩',
    author: '墨枢社区精选',
    repoOrOrigin: 'github:plotpilot-mods/opening-hook-engine',
    trustLevel: 'official',
    roleCategory: 'opening-hook',
    roleLabel: '题材开局',
    summary: '专治开篇慢热：在宏观规划与首幕排布阶段，强制绑定“身份错位 + 48小时生存倒计时 + 唯一破局筹码”。',
    version: 'v1.0.8',
    license: 'MIT',
    updatedAt: '2026-10-29',
    usageLabel: '官方精选',
    replacesBuiltin: true,
    tags: ['开书冷启', '强冲突开局', '倒计时危机', '幕级规划'],
    readmeSections: [
      {
        heading: '适用场景',
        body: '新书开局最忌讳“先写主角身世、再写偶遇机缘、十章后才进主线”。本模组作用于「极速宏观规划」与「幕级章节规划」，确保第一幕前三章即把核心利益冲突与身份反差拉满。',
      },
    ],
    overrides: [
      {
        nodeKey: 'planning-quick-macro',
        nodeLabel: '极速宏观规划',
        mode: 'append_protocol',
        systemContent: [
          '【墨枢模组协议 · 强反差开篇发动机】',
          '首卷开局必须包含三个硬支点：1）明确的近身利益危机或生存倒计时；2）主角独有的信息差/机制筹码首次验证；3）前3章内完成第一次小闭环反杀或立足契约，严禁慢热铺垫。',
        ].join('\n'),
      },
      {
        nodeKey: 'planning-act',
        nodeLabel: '幕级章节规划',
        mode: 'append_protocol',
        systemContent: [
          '【墨枢模组协议 · 幕首钩子与幕末翻转】',
          '每幕第1章直接切入突发变故或交易现场，幕末最后1章必须兑现本幕核心悬念并撕开高一维度的势力矛盾。',
        ].join('\n'),
      },
    ],
  },
]
