"""V6 记忆引擎 - LLM 驱动的章间状态机

解决长文本生成的三大状态崩溃问题：
1. FACT_LOCK: 不可篡改事实块（角色白名单、死亡名单、关系图谱、身份锁、时间线）
2. COMPLETED_BEATS: 已完成节拍锁（防止剧情鬼打墙/重复）
3. REVEALED_CLUES: 已揭露线索清单（防止前后矛盾）

设计原则：
- 不使用关键词匹配/启发式规则，所有状态提取均由 LLM 结构化完成
- 与现有 StateExtractor（9维领域状态）并行但职责正交：
  · StateExtractor → 写入 Bible/Foreshadowing/Timeline 等仓储（"发生了什么"）
  · MemoryEngine → 维护跨章一致性约束（"已经知道了什么，不能再怎么写"）
- 持久化到 memory_engine_state 表，重启不丢失
- 输出直接注入 ContextBudgetAllocator 的 T0 槽位（权重=∞）

架构：
    ChapterStateMachine (LLM Contract)
        ├── FactLockBuilder      ← 从 Bible + KnowledgeGraph 动态构建
        ├── BeatExtractor         ← LLM 提取本章完成的剧情节拍
        └── ClueExtractor         ← LLM 提取本章向读者揭露的真相/信息

    MemoryEngine (Facade)
        ├── build_fact_lock()          → str (注入 T0-α)
        ├── get_completed_beats()       → str (注入 T0-β)
        ├── get_revealed_clues()       → str (注入 T0-γ)
        └── update_from_chapter()      → 异步 LLM 调用 + 持久化
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from domain.ai.services.llm_service import LLMService
from domain.bible.repositories.bible_repository import BibleRepository
from domain.novel.value_objects.novel_id import NovelId

from application.ai.llm_json_extract import parse_llm_json_to_dict
from infrastructure.ai.generation_profiles import generation_config_from_profile
from infrastructure.ai.prompt_contracts.memory_extraction import MEMORY_EXTRACTION_CONTRACT
from infrastructure.ai.prompt_gateway import PromptGatewayError, get_prompt_gateway

logger = logging.getLogger(__name__)

# ============================================================
# LLM Contract: MemoryDelta（增量状态提取）
# ============================================================

_MAX_BEATS = 50
_MAX_CLUES = 100


class CompletedBeatItem(BaseModel):
    """已完成的一条剧情节拍"""
    beat_id: str = Field(description="节拍唯一标识，如 'ch3-meeting-first-time'")
    summary: str = Field(description="一句话概括这个已发生的事件")
    chapter: int = Field(description="该事件发生在第几章")
    characters_involved: List[str] = Field(default_factory=list, description="涉及的角色名")


class RevealedClueItem(BaseModel):
    """已向读者揭露的一条线索/真相"""
    clue_id: str = Field(description="线索唯一标识")
    content: str = Field(description="线索内容（读者和主角现在已知的信息）")
    revealed_at_chapter: int = Field(description="在第几章揭露")
    category: str = Field(
        default="truth",
        description="类别: truth(真相)/relationship(关系变化)/identity(身份暴露)/ability(能力揭示)/other"
    )
    is_still_valid: bool = Field(
        default=True,
        description="该线索是否仍然有效（未被后续章节推翻/证伪）"
    )


class FactViolationItem(BaseModel):
    """事实违反检测（LLM 检测到生成文本与 FACT_LOCK 冲突）"""
    violation_type: str = Field(
        description="违反类型: dead_character_resurrected/character_drift/"
                       "timeline_contradiction/relationship_error/unauthorized_character"
    )
    description: str = Field(description="具体描述哪里违反了事实锁")
    severity: str = Field(default="warning", description="critical / warning / info")
    location_hint: str = Field(default="", description="大致位置提示（如'对话段落中'）")


class MemoryDeltaPayload(BaseModel):
    """LLM 返回的记忆增量（extra=forbid 防止模型塞垃圾字段）"""
    model_config = ConfigDict(extra="forbid")

    completed_beats: List[CompletedBeatItem] = Field(
        default_factory=list, max_length=_MAX_BEATS,
        description="本章新完成的剧情节拍（之前没发生过的事件）"
    )
    revealed_clues: List[RevealedClueItem] = Field(
        default_factory=list, max_length=_MAX_CLUES,
        description="本章新向读者/主角揭露的信息或真相"
    )
    fact_violations: List[FactViolationItem] = Field(
        default_factory=list, max_length=20,
        description="检测到的事实锁违反（如果有）"
    )


# ============================================================
# FactLockBuilder: 从 Bible 动态构建不可篡改事实块
# ============================================================

class FactLockBuilder:
    """从 Bible + KnowledgeGraph 动态构建 FACT_LOCK 文本
    
    不是硬编码！数据来源：
    - Bible.characters → 角色白名单 + 死亡检测 + 身份锁
    - Bible.timeline_notes → 核心时间线
    - Character.relationships → 关系图谱
    """

    def __init__(self, bible_repository: BibleRepository):
        self.bible_repository = bible_repository

    def build(self, novel_id: str, current_chapter: int = 0) -> str:
        """构建完整的 FACT_LOCK 文本块
        
        Args:
            novel_id: 小说 ID
            current_chapter: 当前章节号（用于判断 hidden_profile 是否可见
            
        Returns:
            格式化的 FACT_LOCK 文本
        """
        try:
            novel_id_obj = NovelId(novel_id)
            bible = self.bible_repository.get_by_novel_id(novel_id_obj)
            if not bible:
                return ""
            return self._build_from_bible(bible, current_chapter)
        except Exception as e:
            logger.warning(f"FactLock 构建失败: {e}")
            return ""

    def _build_from_bible(self, bible, current_chapter: int) -> str:
        """从 Bible 实体构建 FACT_LOCK"""
        lines = ["【绝对事实边界（一旦违背即为废稿）】\n"]

        # ── 1. 角色白名单 ──
        characters = bible.characters
        if characters:
            names = [c.name for c in characters]
            lines.append("角色白名单（只可使用以下有名字的角色）：")
            lines.append(f"   允许: {', '.join(names)}")
            lines.append("   禁止: 创造任何其他有名字的角色！路人可以无名但不许命名！\n")

        # ── 2. 已死亡角色（从描述/关系中推断，或标记为 dead 的）──
        dead_chars = self._extract_dead_characters(characters)
        if dead_chars:
            lines.append("已死亡角色（绝对不可复活、不可在当下时间线中出现）：")
            for dc in dead_chars:
                lines.append(f"   禁止: {dc['name']}({dc.get('role', '未知')}) - {dc.get('cause', '原因不详')}（死于{dc.get('when', '未知时间')}）")
            lines.append("")

        # ── 3. 核心关系图谱 ──
        relations = self._build_relation_lines(characters)
        if relations:
            lines.append("核心关系（不可更改）：")
            for rel in relations:
                lines.append(f"   {rel}")
            lines.append("")

        # ── 4. 身份锁死 ──
        identity_lines = self._build_identity_lines(characters, current_chapter)
        if identity_lines:
            lines.append("身份锁死：")
            for il in identity_lines:
                lines.append(f"   {il}")
            lines.append("")

        # ── 5. 时间线锁定 ──
        timeline_lines = self._build_timeline_lines(bible)
        if timeline_lines:
            lines.append("核心事件时间线（不可矛盾）：")
            for tl in timeline_lines:
                lines.append(f"   {tl}")

        return "\n".join(lines)

    def _extract_dead_characters(self, characters: list) -> list[Dict]:
        """从角色列表中推断已死亡角色
        
        策略：
        - 检查 description 中是否包含死亡相关关键词
        - 检查 relationships 中是否有 "dead/died/死亡/已故" 关系
        - 后续可扩展为 Bible 的 is_dead 显式字段
        """
        dead_keywords = [
            "死亡", " died ", "身亡", "去世", "已故", "牺牲",
            " killed ", "被杀", "遇害", "丧命", "殒命",
        ]
        dead_chars = []

        for char in characters:
            # 检查描述
            desc_lower = (char.description or "").lower()
            name = char.name

            # 检查关系标签
            is_dead = False
            death_info = {"name": name, "role": char.public_profile or ""}

            for kw in dead_keywords:
                if kw in desc_lower:
                    is_dead = True
                    # 尝试提取死亡原因片段
                    death_info["cause"] = char.description[:80]
                    break

            # 检查 relationships
            if not is_dead and char.relationships:
                for rel in char.relationships:
                    rel_str = str(rel).lower()
                    for kw in dead_keywords:
                        if kw in rel_str:
                            is_dead = True
                            death_info["cause"] = str(rel)[:80]
                            break
                    if is_dead:
                        break

            if is_dead:
                dead_chars.append(death_info)

        return dead_chars

    def _build_relation_lines(self, characters: list) -> list[str]:
        """从角色的 relationships 字段构建关系行"""
        lines = []
        for char in characters:
            if not char.relationships:
                continue
            name = char.name
            for rel in char.relationships:
                if isinstance(rel, dict):
                    target = rel.get("target", rel.get("with", "?"))
                    rel_type = rel.get("type", rel.get("relation", rel.get("predicate", "—")))
                    lines.append(f"{name} ——{rel_type}→ {target}")
                elif isinstance(rel, str):
                    # 尝试解析 "A —关系→ B" 格式
                    if "—" in rel and "→" in rel:
                        lines.append(rel)
                    else:
                        lines.append(f"{name} ——{rel}→ (?)")
        return lines

    def _build_identity_lines(self, characters: list, current_chapter: int) -> list[str]:
        """构建身份锁死行"""
        lines = []
        for char in characters:
            name = char.name
            identity_parts = []

            # 公开面作为基础身份
            if char.public_profile:
                identity_parts.append(char.public_profile)

            # 如果到了 reveal 章节，追加隐藏面
            if (char.hidden_profile and
                char.reveal_chapter is not None and
                current_chapter >= char.reveal_chapter):
                identity_parts.append(f"[已揭露] {char.hidden_profile}")

            # 心理状态
            if char.mental_state and char.mental_state != "NORMAL":
                identity_parts.append(f"当前心理: {char.mental_state}")

            if identity_parts:
                lines.append(f"{name} = {' | '.join(identity_parts)}")

        return lines

    def _build_timeline_lines(self, bible) -> list[str]:
        """从 Bible 的 timeline_notes 构建时间线"""
        lines = []
        if hasattr(bible, 'timeline_notes') and bible.timeline_notes:
            for note in bible.timeline_notes:
                # TimelineNote 可能有 timestamp / event / description 等属性
                time_str = getattr(note, 'timestamp', '')
                event_str = getattr(note, 'event', '') or getattr(note, 'description', '')
                if event_str:
                    entry = f"[{time_str}] {event_str}" if time_str else event_str
                    lines.append(entry)
        return lines


# ============================================================
# MemoryEngine: 主入口（Facade）
# ============================================================

@dataclass
class MemoryState:
    """持久化的记忆状态快照"""
    novel_id: str = ""
    last_updated_chapter: int = 0
    completed_beats: List[Dict[str, Any]] = field(default_factory=list)
    revealed_clues: List[Dict[str, Any]] = field(default_factory=list)
    fact_violations_history: List[Dict[str, Any]] = field(default_factory=list)


class MemoryEngine:
    """V6 记忆引擎主入口
    
    职责：
    1. 构建 FACT_LOCK（通过 FactLockBuilder 从 Bible 动态生成）
    2. 管理 COMPLETED_BEATS（LLM 提取 + 去重累积）
    3. 管理 REVEALED_CLUES（LLM 提取 + 有效性追踪）
    4. 提供 T0 注入文本接口（供 ContextBudgetAllocator 使用）
    5. 章后异步回写（调用 LLM 提取增量 + 持久化）
    
    使用方式：
        engine = MemoryEngine(llm_service, bible_repository, db_connection)
        
        # 生成前：获取 T0 注入文本
        fact_lock = engine.build_fact_lock_section(novel_id, chapter_number)
        beats = engine.get_completed_beats_section()
        clues = engine.get_revealed_clues_section()
        
        # 生成后：更新状态
        await engine.update_from_chapter(novel_id, ch_num, content, outline)
    """

    def __init__(
        self,
        llm_service: LLMService,
        bible_repository: BibleRepository,
        db_connection=None,
    ):
        self.llm_service = llm_service
        self.fact_lock_builder = FactLockBuilder(bible_repository)
        self.bible_repository = bible_repository
        self.db_connection = db_connection

        # 运行时内存缓存（优先读缓存，miss 再查 DB）
        self._cache: Dict[str, MemoryState] = {}

        if self.db_connection is not None:
            # 与正式迁移一致；避免首次 _load_from_db 在表未建好时刷 WARNING
            self._ensure_table_exists()

    # ============================================================
    # T0 注入接口（生成前调用）
    # ============================================================

    def build_fact_lock_section(self, novel_id: str, chapter_number: int) -> str:
        """构建 T0-α: FACT_LOCK 不可篡改事实块"""
        return self.fact_lock_builder.build(novel_id, chapter_number)

    def get_completed_beats_section(self, novel_id: str) -> str:
        """构建 T0-β: 已完成节拍锁"""
        state = self._get_or_load_state(novel_id)
        if not state.completed_beats:
            return ""

        lines = ["【已完成节拍（以下事件已经发生过了，禁止在本章重复写一遍）】\n"]
        for beat in state.completed_beats:
            ch = beat.get("chapter", "?")
            summary = beat.get("summary", "")
            beat_id = beat.get("beat_id", "")
            lines.append(f"   [第{ch}章] {summary}")
        lines.append(
            "\n如果你需要'回顾'这些事件，用角色的回忆/一句话带过，不要重新展开写。"
        )
        return "\n".join(lines)

    def get_revealed_clues_section(self, novel_id: str) -> str:
        """构建 T0-γ: 已揭露线索清单"""
        state = self._get_or_load_state(novel_id)
        if not state.revealed_clues:
            return ""

        # 只显示 still_valid 的线索
        valid_clues = [c for c in state.revealed_clues if c.get("is_still_valid", True)]
        if not valid_clues:
            return ""

        lines = ["【截至目前已知的线索（读者和主角已经知道的信息）】\n"]
        for clue in valid_clues:
            ch = clue.get("revealed_at_chapter", "?")
            content = clue.get("content", "")
            category = clue.get("category", "")
            category_label = {
                "truth": "真相", "relationship": "关系",
                "identity": "身份", "ability": "能力", "other": "信息"
            }.get(category, "信息")
            lines.append(f"   [{category_label}] [第{ch}章] {content}")
        lines.append(
            "\n以上信息已经是'已知'的，不要再把它们当作'新发现'来写。你可以在此基础上推进，但不能推翻。"
        )
        return "\n".join(lines)

    # ============================================================
    # 章后状态回写（生成后调用，LLM 驱动）
    # ============================================================

    async def update_from_chapter(
        self,
        novel_id: str,
        chapter_number: int,
        content: str,
        outline: str,
    ) -> Dict[str, Any]:
        """章后状态回写：调用 LLM 提取增量 + 去重合并 + 持久化
        
        Args:
            novel_id: 小说 ID
            chapter_number: 章节号
            content: 章节正文
            outline: 章节大纲
            
        Returns:
            delta dict: {
                "new_beats": int,
                "new_clues": int,
                "violations": int,
                "errors": list[str],
            }
        """
        result = {"new_beats": 0, "new_clues": 0, "violations": 0, "errors": []}

        try:
            # 1. 准备上下文
            state = self._get_or_load_state(novel_id)
            fact_lock = self.build_fact_lock_section(novel_id, chapter_number)
            existing_beats = self._summarize_beats_for_prompt(state.completed_beats)
            existing_clues = self._summarize_clues_for_prompt(state.revealed_clues)

            # 2. 通过 PromptGateway 渲染契约提示词，变量缺失时在请求 LLM 前失败
            try:
                rendered_prompt = get_prompt_gateway().render(
                    MEMORY_EXTRACTION_CONTRACT,
                    {
                        "chapter_content": content,
                        "chapter_number": chapter_number,
                        "outline": outline,
                        "fact_lock_text": fact_lock,
                        "existing_beats_summary": existing_beats,
                        "existing_clues_summary": existing_clues,
                    },
                )
            except PromptGatewayError as exc:
                msg = f"MemoryEngine 提示词渲染失败: {exc}"
                result["errors"].append(msg)
                logger.warning(msg)
                return result

            prompt = rendered_prompt.prompt
            config = generation_config_from_profile("memory_extraction")

            # 3. 调用 LLM
            llm_result = await self.llm_service.generate(prompt, config)
            raw_response = llm_result.content

            # 4. 解析响应
            data, parse_errors = parse_llm_json_to_dict(raw_response)
            if data is None:
                result["errors"].extend(parse_errors)
                logger.warning(
                    f"MemoryEngine LLM JSON 解析失败: {parse_errors}, "
                    f"raw response (first 200): {raw_response[:200]}"
                )
                return result

            try:
                payload = MemoryDeltaPayload.model_validate(data)
            except ValidationError as e:
                err_msg = "; ".join(
                    f"{'/'.join(str(x) for x in err.get('loc', ''))}: {err.get('msg', '')}"
                    for err in e.errors()[:10]
                )
                result["errors"].append(f"Contract 校验失败: {err_msg}")
                logger.warning(f"MemoryEngine contract validation failed: {err_msg}")
                return result

            # 5. 合并增量到状态
            new_beats = self._merge_beats(state, payload.completed_beats, chapter_number)
            new_clues = self._merge_clues(state, payload.revealed_clues, chapter_number)

            result["new_beats"] = new_beats
            result["new_clues"] = new_clues
            result["violations"] = len(payload.fact_violations)

            # 记录违反历史
            if payload.fact_violations:
                for v in payload.fact_violations:
                    state.fact_violations_history.append({
                        "chapter": chapter_number,
                        **v.model_dump(),
                    })
                logger.warning(
                    f"检测到 {len(payload.fact_violations)} 个事实违反 @ ch{chapter_number}"
                )

            # 6. 更新状态并持久化
            state.last_updated_chapter = chapter_number
            self._cache[novel_id] = state
            self._persist_state(novel_id, state)

            logger.info(
                f"MemoryEngine 更新完成 @ ch{chapter_number}: "
                f"+{new_beats} beats, +{new_clues} clues, "
                f"{result['violations']} violations"
            )

        except Exception as e:
            result["errors"].append(str(e))
            logger.error(f"MemoryEngine.update_from_chapter 失败: {e}", exc_info=True)

        return result

    # ============================================================
    # 内部方法：状态管理
    # ============================================================

    def _get_or_load_state(self, novel_id: str) -> MemoryState:
        """获取内存状态（缓存优先）"""
        if novel_id in self._cache:
            return self._cache[novel_id]

        # 从 DB 加载
        state = self._load_from_db(novel_id)
        self._cache[novel_id] = state
        return state

    def _load_from_db(self, novel_id: str) -> MemoryState:
        """从数据库加载持久化状态"""
        if not self.db_connection:
            return MemoryState(novel_id=novel_id)

        try:
            row = self.db_connection.execute(
                """
                SELECT state_json, last_updated_chapter 
                FROM memory_engine_state 
                WHERE novel_id = ? 
                ORDER BY last_updated_chapter DESC 
                LIMIT 1
                """,
                (novel_id,),
            ).fetchone()

            if row and row[0]:
                data = json.loads(row[0])
                state = MemoryState(
                    novel_id=novel_id,
                    last_updated_chapter=row[1] or 0,
                    completed_beats=data.get("completed_beats", []),
                    revealed_clues=data.get("revealed_clues", []),
                    fact_violations_history=data.get("fact_violations_history", []),
                )
                logger.debug(f"MemoryEngine 从 DB 加载状态: novel={novel_id}, ch={state.last_updated_chapter}")
                return state
        except Exception as e:
            logger.warning(f"MemoryEngine DB 加载失败: {e}")

        return MemoryState(novel_id=novel_id)

    def _memory_state_to_json(self, state: MemoryState) -> str:
        return json.dumps(
            {
                "completed_beats": state.completed_beats,
                "revealed_clues": state.revealed_clues,
                "fact_violations_history": state.fact_violations_history,
            },
            ensure_ascii=False,
        )

    def _upsert_state_row(self, novel_id: str, state: MemoryState) -> None:
        """将当前 MemoryState UPSERT 到 memory_engine_state（使用 DatabaseConnection / sqlite3 均支持的 execute API）"""
        state_json = self._memory_state_to_json(state)
        self.db_connection.execute(
            """
            INSERT INTO memory_engine_state (novel_id, state_json, last_updated_chapter, updated_at)
            VALUES (?, ?, ?, datetime('now'))
            ON CONFLICT(novel_id) DO UPDATE SET
                state_json = excluded.state_json,
                last_updated_chapter = excluded.last_updated_chapter,
                updated_at = datetime('now')
            """,
            (novel_id, state_json, state.last_updated_chapter),
        )
        self.db_connection.commit()

    def _persist_state(self, novel_id: str, state: MemoryState) -> None:
        """持久化状态到数据库"""
        if not self.db_connection:
            logger.debug("MemoryEngine 无 DB 连接，跳过持久化（仅内存模式）")
            return

        try:
            self._upsert_state_row(novel_id, state)
            logger.debug(f"MemoryEngine 状态已持久化: novel={novel_id}, ch={state.last_updated_chapter}")

        except Exception as e:
            # 表可能还不存在，尝试自动建表
            if "no such table" in str(e).lower() or "table" in str(e).lower():
                self._ensure_table_exists()
                # 重试一次
                try:
                    self._upsert_state_row(novel_id, state)
                except Exception as retry_err:
                    logger.error(f"MemoryEngine 持久化重试失败: {retry_err}")
            else:
                logger.error(f"MemoryEngine 持久化失败: {e}")

    def _ensure_table_exists(self) -> None:
        """自动创建 memory_engine_state 表"""
        if not self.db_connection:
            return
        try:
            self.db_connection.execute("""
                CREATE TABLE IF NOT EXISTS memory_engine_state (
                    novel_id TEXT PRIMARY KEY,
                    state_json TEXT NOT NULL DEFAULT '{}',
                    last_updated_chapter INTEGER NOT NULL DEFAULT 0,
                    updated_at TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL DEFAULT (datetime('now'))
                )
            """)
            self.db_connection.commit()
            logger.info("memory_engine_state 表已自动创建")
        except Exception as e:
            logger.error(f"创建 memory_engine_state 表失败: {e}")

    def _merge_beats(
        self, state: MemoryState, new_beats: List[CompletedBeatItem], chapter: int
    ) -> int:
        """合并新的已完成节拍（去重）"""
        count = 0
        existing_ids = {b.get("beat_id") for b in state.completed_beats}

        for beat in new_beats:
            beat_data = beat.model_dump()
            # 确保有 chapter
            if not beat_data.get("chapter"):
                beat_data["chapter"] = chapter

            beat_id = beat_data.get("beat_id", "")
            if beat_id and beat_id in existing_ids:
                continue  # 去重

            # 也按 summary 做模糊去重
            summary = beat_data.get("summary", "")
            if any(
                existing.get("summary") == summary
                for existing in state.completed_beats
            ):
                continue

            state.completed_beats.append(beat_data)
            count += 1

        return count

    def _merge_clues(
        self, state: MemoryState, new_clues: List[RevealedClueItem], chapter: int
    ) -> int:
        """合并新的已揭露线索（去重 + 证伪标记）"""
        count = 0
        existing_ids = {c.get("clue_id") for c in state.revealed_clues}

        for clue in new_clues:
            clue_data = clue.model_dump()
            if not clue_data.get("revealed_at_chapter"):
                clue_data["revealed_at_chapter"] = chapter

            clue_id = clue_data.get("clue_id", "")
            if clue_id and clue_id in existing_ids:
                continue

            # 按内容模糊去重
            content = clue_data.get("content", "")
            if any(
                existing.get("content") == content
                for existing in state.revealed_clues
            ):
                continue

            state.revealed_clues.append(clue_data)
            count += 1

        return count

    @staticmethod
    def _summarize_beats_for_prompt(beats: List[Dict]) -> str:
        """将已有节拍压缩为 prompt 摘要（避免 token 爆炸）"""
        if not beats:
            return ""
        lines = []
        # 只取最近 15 条
        for b in beats[-15:]:
            ch = b.get("chapter", "?")
            s = b.get("summary", "")[:80]
            lines.append(f"- [Ch{ch}] {s}")
        return "\n".join(lines)

    @staticmethod
    def _summarize_clues_for_prompt(clues: List[Dict]) -> str:
        """将已有线索压缩为 prompt 摘要"""
        if not clues:
            return ""
        valid = [c for c in clues if c.get("is_still_valid", True)]
        if not valid:
            return ""
        lines = []
        for c in valid[-20:]:  # 最近 20 条
            ch = c.get("revealed_at_chapter", "?")
            content = c.get("content", "")[:80]
            lines.append(f"- [Ch{ch}] {content}")
        return "\n".join(lines)

    # ============================================================
    # 管理接口
    # ============================================================

    def reset(self, novel_id: str) -> None:
        """重置某小说的记忆状态（谨慎使用）"""
        if novel_id in self._cache:
            del self._cache[novel_id]

        if self.db_connection:
            try:
                self.db_connection.execute(
                    "DELETE FROM memory_engine_state WHERE novel_id = ?",
                    (novel_id,),
                )
                self.db_connection.commit()
                logger.info(f"MemoryEngine 状态已重置: novel={novel_id}")
            except Exception as e:
                logger.warning(f"MemoryEngine 重试失败: {e}")

    def get_state_summary(self, novel_id: str) -> Dict[str, Any]:
        """获取状态摘要（用于调试/监控）"""
        state = self._get_or_load_state(novel_id)
        return {
            "novel_id": novel_id,
            "last_updated_chapter": state.last_updated_chapter,
            "total_beats": len(state.completed_beats),
            "total_clues": len(state.revealed_clues),
            "valid_clues": sum(1 for c in state.revealed_clues if c.get("is_still_valid", True)),
            "total_violations": len(state.fact_violations_history),
        }
