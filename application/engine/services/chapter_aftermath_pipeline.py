"""章节保存后的统一管线：叙事落库、向量检索、文风、图谱推断与后台抽取。

供 HTTP 保存、托管连写、自动驾驶审计复用，避免：
- 索引用正文截断 vs 叙事层用 LLM 总结 两套逻辑；
- 文风既入队 VOICE_ANALYSIS 又同步 score_chapter 重复计算。

顺序（重要产物均落库）：
1. 分章叙事同步：一次 LLM 产出摘要/事件/埋线 + 三元组 + 伏笔 + 因果边 + 人物状态突变 → StoryKnowledge + triples + ForeshadowingRegistry + CausalEdges + CharacterStates + NarrativeDebts，再向量索引（chapter_narrative_sync）
2. 文风评分：写入 chapter_style_scores（仅一次，不再入队 VOICE_ANALYSIS）
3. 结构树知识图谱推断：KnowledgeGraphService.infer_from_chapter（与 LLM 三元组互补，非重复）
"""
from __future__ import annotations

import logging
from typing import Any, Dict, TYPE_CHECKING

from domain.ai.services.llm_service import LLMService

if TYPE_CHECKING:
    from application.world.services.knowledge_service import KnowledgeService

logger = logging.getLogger(__name__)


async def infer_kg_from_chapter(novel_id: str, chapter_number: int) -> None:
    """结构树章节节点 → 知识图谱增量推断（与 HTTP 原 _try_infer_kg_chapter 一致）。"""
    try:
        from application.paths import get_db_path
        from infrastructure.persistence.database.connection import get_database
        from infrastructure.persistence.database.sqlite_knowledge_repository import SqliteKnowledgeRepository
        from infrastructure.persistence.database.triple_repository import TripleRepository
        from infrastructure.persistence.database.chapter_element_repository import ChapterElementRepository
        from infrastructure.persistence.database.story_node_repository import StoryNodeRepository
        from application.world.services.knowledge_graph_service import KnowledgeGraphService

        db_path = get_db_path()
        kr = SqliteKnowledgeRepository(get_database())
        story_node_id = kr.find_story_node_id_for_chapter_number(novel_id, chapter_number)
        if not story_node_id:
            logger.debug("KG 推断跳过：章节 %d 无故事节点 novel=%s", chapter_number, novel_id)
            return

        kg_service = KnowledgeGraphService(
            TripleRepository(),
            ChapterElementRepository(db_path),
            StoryNodeRepository(db_path),
        )
        triples = await kg_service.infer_from_chapter(story_node_id)
        logger.debug("KG 推断完成 novel=%s ch=%d 新三元组=%d", novel_id, chapter_number, len(triples))
    except Exception as e:
        logger.warning("KG 推断失败 novel=%s ch=%d: %s", novel_id, chapter_number, e)


class ChapterAftermathPipeline:
    """章节保存后分析与落库的统一入口。

    V8 Feed-forward 升级：集成因果边提取、人物状态突变评估、叙事债务更新。
    """

    def __init__(
        self,
        knowledge_service: "KnowledgeService",
        chapter_indexing_service: Any,
        llm_service: LLMService,
        voice_drift_service: Any = None,
        triple_repository: Any = None,
        foreshadowing_repository: Any = None,
        storyline_repository: Any = None,
        chapter_repository: Any = None,
        plot_arc_repository: Any = None,
        narrative_event_repository: Any = None,
        # ★ V8 Feed-forward: 新增仓储
        causal_edge_repository: Any = None,
        character_state_repository: Any = None,
        debt_repository: Any = None,
        bible_repository: Any = None,
        unified_checkpoint_service: Any = None,
        prop_lifecycle_syncer: Any = None,
    ) -> None:
        self._knowledge = knowledge_service
        self._indexing = chapter_indexing_service
        self._llm = llm_service
        self._voice = voice_drift_service
        self._triple_repository = triple_repository
        self._foreshadowing_repository = foreshadowing_repository
        self._storyline_repository = storyline_repository
        self._chapter_repository = chapter_repository
        self._plot_arc_repository = plot_arc_repository
        self._narrative_event_repository = narrative_event_repository
        # ★ V8 Feed-forward: 因果图谱 / 人物状态机 / 叙事债务
        self._causal_edge_repository = causal_edge_repository
        self._character_state_repository = character_state_repository
        self._debt_repository = debt_repository
        self._bible_repository = bible_repository
        self._unified_checkpoint = unified_checkpoint_service
        self._prop_syncer = prop_lifecycle_syncer

    async def run_after_chapter_saved(
        self,
        novel_id: str,
        chapter_number: int,
        content: str,
    ) -> Dict[str, Any]:
        """保存正文后执行完整管线。返回文风结果供托管/审计门控使用。

        三元组与伏笔、故事线、张力、对话、因果边、人物状态、债务
        已在 narrative_sync 单次 LLM 中落库。
        """
        out: Dict[str, Any] = {
            "drift_alert": False,
            "similarity_score": None,
            "narrative_sync_ok": False,
            "vector_stored": False,
            "foreshadow_stored": False,
            "triples_extracted": False,
            "causal_edges_stored": False,
            "character_mutations_stored": False,
            "debt_updated": False,
            "guardrail_passed": None,
            "guardrail_score": None,
        }

        if not content or not str(content).strip():
            logger.debug("aftermath 跳过：正文为空 novel=%s ch=%s", novel_id, chapter_number)
            return out

        # 1) 叙事 + 向量 + 故事线 + 张力 + 对话 + 因果边 + 人物状态 + 债务
        try:
            from application.world.services.chapter_narrative_sync import (
                sync_chapter_narrative_after_save,
            )

            sync_flags = await sync_chapter_narrative_after_save(
                novel_id,
                chapter_number,
                content,
                self._knowledge,
                self._indexing,
                self._llm,
                triple_repository=self._triple_repository,
                foreshadowing_repo=self._foreshadowing_repository,
                storyline_repository=self._storyline_repository,
                chapter_repository=self._chapter_repository,
                plot_arc_repository=self._plot_arc_repository,
                narrative_event_repository=self._narrative_event_repository,
                causal_edge_repository=self._causal_edge_repository,
                character_state_repository=self._character_state_repository,
                debt_repository=self._debt_repository,
                bible_repository=self._bible_repository,
            )
            out["narrative_sync_ok"] = True
            out["vector_stored"] = bool(sync_flags.get("vector_stored"))
            out["foreshadow_stored"] = bool(sync_flags.get("foreshadow_stored"))
            out["triples_extracted"] = bool(sync_flags.get("triples_extracted"))
            out["causal_edges_stored"] = bool(sync_flags.get("causal_edges_stored"))
            out["character_mutations_stored"] = bool(sync_flags.get("character_mutations_stored"))
            out["debt_updated"] = bool(sync_flags.get("debt_updated"))
            # 🔥 传递多维张力评分（0-100），供审计流程替代旧式 _score_tension
            out["tension_composite"] = sync_flags.get("tension_composite")
        except Exception as e:
            logger.warning(
                "叙事同步/向量失败 novel=%s ch=%s: %s", novel_id, chapter_number, e
            )

        # 2) 文风（落库 chapter_style_scores）
        # 支持 LLM 模式（异步）和统计模式（同步）
        if self._voice:
            try:
                # 检查是否使用 LLM 模式
                if getattr(self._voice, "use_llm_mode", False):
                    vr = await self._voice.score_chapter_async(
                        novel_id=novel_id,
                        chapter_number=chapter_number,
                        content=content,
                    )
                else:
                    vr = self._voice.score_chapter(
                        novel_id=novel_id,
                        chapter_number=chapter_number,
                        content=content,
                    )
                out["drift_alert"] = bool(vr.get("drift_alert", False))
                out["similarity_score"] = vr.get("similarity_score")
                out["voice_mode"] = vr.get("mode", "statistics")
                logger.debug(
                    "文风评分完成 novel=%s ch=%s mode=%s drift=%s",
                    novel_id,
                    chapter_number,
                    out.get("voice_mode"),
                    out["drift_alert"],
                )
            except Exception as e:
                logger.warning("文风评分失败 novel=%s ch=%s: %s", novel_id, chapter_number, e)

        # 3) 结构树 KG 推断
        await infer_kg_from_chapter(novel_id, chapter_number)

        # 4) 质量护栏（建议模式）+ 快照落库 + 溯源（与手动 POST /guardrail/check 同源）
        try:
            import asyncio
            import time
            import uuid
            from datetime import datetime, timezone

            from application.engine.services.guardrail_execution import run_guardrail_advise_sync
            from engine.core.ports.ports import TraceRecord
            from engine.infrastructure.persistence.trace_store import SqliteTraceStore
            from infrastructure.persistence.database.chapter_guardrail_snapshot_repository import (
                ChapterGuardrailSnapshotRepository,
            )
            from infrastructure.persistence.database.connection import get_database

            t0 = time.perf_counter()
            dto = await asyncio.to_thread(
                run_guardrail_advise_sync,
                novel_id,
                content,
                f"第{chapter_number}章（保存后自动）",
            )
            elapsed_ms = int((time.perf_counter() - t0) * 1000)
            out["guardrail_passed"] = bool(dto.get("passed"))
            out["guardrail_score"] = dto.get("overall_score")

            db = get_database()
            repo = ChapterGuardrailSnapshotRepository(db)
            await asyncio.to_thread(repo.upsert, novel_id, chapter_number, dto)

            vsummary: list[str] = []
            for v in dto.get("violations") or []:
                if isinstance(v, dict) and v.get("description"):
                    vsummary.append(str(v["description"])[:120])
                if len(vsummary) >= 20:
                    break

            store = SqliteTraceStore(db)
            trace = TraceRecord(
                trace_id=str(uuid.uuid4()),
                node_type="guardrail",
                operation="chapter_after_save",
                input_summary=f"{novel_id} ch{chapter_number} len={len(content)}"[:200],
                output_summary=(
                    f"passed={dto.get('passed')} score={dto.get('overall_score')} "
                    f"viol={len(dto.get('violations') or [])}"
                )[:200],
                score=float(dto.get("overall_score") or 0.0),
                violations=vsummary,
                duration_ms=elapsed_ms,
                timestamp=datetime.now(timezone.utc).isoformat(),
                novel_id=novel_id,
            )
            await store.record(trace)
        except Exception as e:
            logger.warning("自动护栏/溯源失败 novel=%s ch=%s: %s", novel_id, chapter_number, e)

        # 5) 世界线快照 — 章节完成后自动打 CHAPTER checkpoint
        try:
            if self._unified_checkpoint:
                import asyncio
                cp_id = await asyncio.to_thread(
                    self._unified_checkpoint.create_checkpoint,
                    novel_id,
                    "CHAPTER",
                    f"第{chapter_number}章自动快照",
                    None,        # description
                    "main",      # branch_name
                    None,        # parent_id
                    {"chapter": chapter_number},  # story_state（轻量）
                )
                out["worldline_checkpoint_id"] = cp_id
                logger.debug("[Worldline] CHAPTER checkpoint novel=%s ch=%s id=%s", novel_id, chapter_number, cp_id)
        except Exception as e:
            logger.warning("[Worldline] 自动 checkpoint 失败（非致命）novel=%s ch=%s: %s", novel_id, chapter_number, e)

        # 6) 道具生命周期同步 — 事件提取、状态机转换、知识库三元组
        try:
            if self._prop_syncer:
                import asyncio
                sync_result = await self._prop_syncer.sync(novel_id, chapter_number, content)
                out["prop_sync"] = sync_result
                logger.debug(
                    "[PropSync] 完成 novel=%s ch=%s result=%s",
                    novel_id, chapter_number, sync_result,
                )
        except Exception as e:
            logger.warning(
                "[PropSync] 失败（非致命）novel=%s ch=%s: %s", novel_id, chapter_number, e
            )

        # ── 汇流点到达检查 ──
        try:
            from interfaces.api.dependencies import get_confluence_point_repository as _get_cp_repo
            _confluence_repo = _get_cp_repo()
            _hit_cps = [
                cp for cp in _confluence_repo.get_by_novel_id(novel_id)
                if cp.target_chapter == chapter_number and not cp.resolved
            ]
            if _hit_cps:
                for _cp in _hit_cps:
                    logger.info(
                        "[汇流点] 第%d章完成，汇流点 %s (source=%s → target=%s) 建议标记为 resolved",
                        chapter_number, _cp.id, _cp.source_storyline_id, _cp.target_storyline_id,
                    )
        except Exception as _cp_err:
            logger.warning("汇流点检查失败（非致命）: %s", _cp_err)

        return out
