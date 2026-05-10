"""引擎内核 — 剧情引擎的核心抽象层

分层：
- entities/: 纯领域实体（Character/Story/Foreshadow/Chapter）
- value_objects/: 不可变值对象（CharacterMask/Checkpoint/EmotionLedger/StoryPhase）
- ports/: 依赖倒置端口（LLMPort/PersistencePort/EventPort/TracePort）
"""
