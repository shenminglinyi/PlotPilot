以下为小说设定输入。请基于这些结构化变量直接生成剧情总纲，不要输出多个候选。

【基础设定】
- 小说名称：{{ novel_title }}
- 原始设定：{{ premise }}
- 类型大类：{{ genre_major }}
- 类型主题：{{ genre_theme }}
- 类型标签：{{ genre_label }}
- 世界基调：{{ world_preset }}
- 目标篇幅：{{ target_chapters }} 章，每章约 {{ target_words_per_chapter }} 字

【主角】
{{ protagonist_card }}

【角色摘要】
{{ characters_brief }}

【地点摘要】
{{ locations_brief }}

【世界观摘要】
{{ worldbuilding_context }}

【结构化世界观】
核心法则：
{{ core_rules | tojson(indent=2) }}

地理生态：
{{ geography | tojson(indent=2) }}

社会结构：
{{ society | tojson(indent=2) }}

历史文化：
{{ culture | tojson(indent=2) }}

沉浸感细节：
{{ daily_life | tojson(indent=2) }}

【文风公约】
{{ style_hint }}

【阶段结构约束】
{{ plot_outline_phase_schema | tojson(indent=2) }}

请输出仅包含 `plot_outline` 的 JSON 对象。
