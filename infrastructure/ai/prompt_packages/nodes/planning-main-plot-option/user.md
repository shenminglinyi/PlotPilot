以下为小说设定输入。请只依据变量中心中的结构化事实推演主线候选。

【基础设定】
- 小说名称：{{ novel.title }}
- 原始设定：{{ novel.premise }}
- 类型大类：{{ novel.genre_major }}
- 类型主题：{{ novel.genre_theme }}
- 类型标签：{{ novel.genre_label }}
- 世界基调：{{ novel.world_preset }}
- 目标篇幅：{{ novel.target_chapters }} 章，每章约 {{ novel.target_words_per_chapter }} 字

【融合题材主轴锁】
{{ plot.fusion_contract }}

【主角】
{{ characters.protagonist }}

【角色列表】
{{ characters.list }}

【地点列表】
{{ locations.list }}

【文风公约】
{{ worldbuilding.style }}

【结构化世界观】
{{ worldbuilding.content }}

请输出仅包含 plot_options 数组的 JSON 对象。
