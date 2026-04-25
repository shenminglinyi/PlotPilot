"""读者模拟 Agent 模块

模拟不同类型读者（硬核粉、休闲读者、挑刺党）阅读每章后的反馈，
输出悬疑保持度、爽感评分、劝退风险、情感共鸣度等多维度评估。

核心组件：
- ReaderSimulationService: 读者模拟分析服务（LLM 驱动）
- ReaderPersona: 读者人设枚举（硬核粉/休闲读者/挑刺党）
- ReaderFeedback: 单个读者视角的反馈结果
- ChapterReaderReport: 章节级的综合读者报告
"""
