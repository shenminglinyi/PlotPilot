"""叙事引擎只读门面 — 聚合多域数据，不复制 chronicles/storyline 计算逻辑。"""

from __future__ import annotations

from typing import Any, Dict, List

from application.narrative_engine.story_phase_resolution import resolve_story_phase_payload
from application.engine.services.query_service import get_query_service


class NarrativeEngineReadFacade:
    """面向「故事演进 / 角色声线」工作台的引擎读模型组装器。"""

    def get_story_evolution_read_model(self, novel_id: str) -> Dict[str, Any]:
        """一书一页：生命周期 × 骨架 × 时空轴 × 章节 digest（+ 伏笔规模提示）。"""
        ctx = get_query_service().get_workbench_context(novel_id).to_dict()
        life = resolve_story_phase_payload(novel_id)
        foreshadow = ctx.get("foreshadow_ledger") or []
        return {
            "novel_id": novel_id,
            "schema_version": "1",
            "life_cycle": life,
            "plot_spine": {
                "storylines": ctx.get("storylines") or [],
                "plot_arc": ctx.get("plot_arc"),
                "confluence_points": ctx.get("confluence_points") or [],
            },
            "chronotope": ctx.get("chronicles") or {
                "rows": [],
                "max_chapter_in_book": 1,
                "note": "",
            },
            "chapters_digest": ctx.get("chapters_digest") or [],
            "subtext_surface": {
                "foreshadow_ledger_count": len(foreshadow),
            },
        }

    def get_persona_voice_read_model(self, novel_id: str, character_id: str) -> Dict[str, Any]:
        """单角一线：声线锚点 + 全书对白语料统计（正文抽取，与沙盒生成解耦）。"""
        from interfaces.api.dependencies import get_bible_service, get_sandbox_dialogue_service

        bible_service = get_bible_service()
        sandbox_service = get_sandbox_dialogue_service()

        bible = bible_service.get_bible_by_novel(novel_id)
        if not bible:
            raise ValueError("bible_not_found")

        character = next((c for c in bible.characters if c.id == character_id), None)
        if not character:
            raise ValueError("character_not_found")

        wl = sandbox_service.get_dialogue_whitelist(novel_id=novel_id)
        lines: List[Any] = list(wl.dialogues) if wl and wl.dialogues else []
        name = character.name
        in_voice = [d for d in lines if getattr(d, "speaker", "") == name]

        return {
            "novel_id": novel_id,
            "schema_version": "1",
            "character_id": character_id,
            "character_name": name,
            "voice_anchor": {
                "mental_state": getattr(character, "mental_state", None) or "NORMAL",
                "verbal_tic": getattr(character, "verbal_tic", None) or "",
                "idle_behavior": getattr(character, "idle_behavior", None) or "",
            },
            "dialogue_corpus": {
                "total_lines": wl.total_count if wl else 0,
                "lines_as_speaker": len(in_voice),
            },
        }
