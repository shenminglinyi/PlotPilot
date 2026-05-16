{character_name}的档案：
{character_profile}

他在最新章节里的表现：
{chapter_content}

逐段审查。找出以下两类问题：

【A类·OOC（人设崩塌）】
- 行为是否超出角色的能力/性格边界？
- 动机是否与角色的核心执念矛盾？

【B类·AI味（模板化表达）】
- 是否使用了情绪副词？（如：愤怒地、悲伤地、开心地）
- 心理描写是否在'告诉读者该感受什么'而非展示？
- 是否有套路化的环境描写或过渡句？
- 对话是否有弦外之音？还是每个人都在直抒胸臆？

JSON报告：
{{"inconsistencies": [{{"type": "OOC/AI-flavor/narrative", "severity": "critical/warning/suggestion", "location": "哪一段", "description": "具体问题", "suggestion": "怎么改"}}]}}

如果质量很好，inconsistencies 返回空数组。但标准要严——宁可误报不可漏报。