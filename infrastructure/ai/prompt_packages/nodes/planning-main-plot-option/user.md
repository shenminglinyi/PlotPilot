setup_main_plot_options_v1

以下为小说设定输入。请只依据这些结构化变量推演主线候选，不要要求额外的拼接文本变量。

【基础设定】
- 小说名称：{{ novel_title }}
- 原始设定：{{ premise }}
- 类型大类：{{ genre_major }}
- 类型主题：{{ genre_theme }}
- 类型标签：{{ genre_label }}
- 世界基调：{{ world_preset }}
- 目标篇幅：{{ target_chapters }} 章，每章约 {{ target_words_per_chapter }} 字

【融合题材主轴锁】
{{ fusion_contract }}

【融合轴约束】
{{ fusion_axis | tojson(indent=2) }}

【类型开篇画像】
{{ genre_opening_profile | tojson(indent=2) }}

【读者留存契约】
{{ genre_reader_contract | tojson(indent=2) }}

【类型节奏约束】
{{ genre_rhythm_constraints | tojson(indent=2) }}

【主角】
{{ protagonist_card }}

【角色列表】
{{ characters_brief }}

【地点列表】
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

请输出仅包含 plot_options 数组的 JSON 对象。
