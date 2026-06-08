以下为小说设定输入。请基于这些结构化变量直接生成剧情总纲，不要输出多个候选。

【基础设定】
- 小说名称：{{ novel.title }}
- 原始设定：{{ novel.premise }}
- 类型大类：{{ novel.genre_major }}
- 类型主题：{{ novel.genre_theme }}
- 类型标签：{{ novel.genre_label }}
- 世界基调：{{ novel.world_preset }}
- 剧情结构：{{ novel.story_structure }}
- 节奏把控：{{ novel.pacing_control }}
- 写作风格：{{ novel.writing_style }}
- 特殊要求：{{ novel.special_requirements }}
- 目标篇幅：{{ novel.target_chapters }} 章，每章约 {{ novel.target_words_per_chapter }} 字

【角色列表】
{{ characters.list }}

【地点列表】
{{ locations.list }}

【结构化世界观】
{{ worldbuilding.content }}

请按照 JSON 结构输出，可被 Python `json.loads` 直接解析。不要输出解释文字。

{
    "outline_main": "字符串，200-500字：全书主线概括，主角出身、金手指、核心目标、完整成长线、故事核心卖点",
    "stage_plan": {
        "stage_opening_1_15": "开篇阶段1%-15%：世界观搭建、主角登场、金手指初次启用、首个核心矛盾落地",
        "stage_develop_15_40": "发展阶段15%-40%：冲突升级、资源争夺、多方势力博弈、连续阶段性小高潮",
        "stage_deepen_40_70": "深化阶段40%-70%：世界观真相挖掘、主角实力蜕变、关键强敌登场、局势反转",
        "stage_climax_70_90": "高潮阶段70%-90%：终极矛盾爆发、巅峰决战、长线伏笔集中回收",
        "stage_end_90_100": "收尾阶段90%-100%：全线索收拢、恩怨了结、各大角色落地归宿"
    },
    "ending_expect": "字符串：明确全书最终走向、主角最终地位、敌对势力结局、整体世界格局",
    "core_conflict": "字符串：提炼全书核心矛盾，势力/宿命/恩怨/阶级等底层冲突，全书剧情驱动根源"
}
