"""叙事引擎只读门面 — 聚合多域数据，不复制 chronicles/storyline 计算逻辑。"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from application.narrative_engine.story_phase_resolution import resolve_story_phase_payload
from application.engine.services.query_service import get_query_service


class NarrativeEngineReadFacade:
    """面向「故事演进 / 角色声线」工作台的引擎读模型组装器。"""

    def __init__(
        self,
        *,
        query_service: Any = None,
        story_phase_resolver: Callable[[str], Dict[str, Any]] = resolve_story_phase_payload,
        evolution_repository_factory: Optional[Callable[[], Any]] = None,
        context_presenter_factory: Optional[Callable[[], Any]] = None,
        bible_service: Any = None,
        sandbox_dialogue_service: Any = None,
    ) -> None:
        self._query_service = query_service
        self._story_phase_resolver = story_phase_resolver
        self._evolution_repository_factory = evolution_repository_factory
        self._context_presenter_factory = context_presenter_factory
        self._bible_service = bible_service
        self._sandbox_dialogue_service = sandbox_dialogue_service

    def _query(self) -> Any:
        return self._query_service or get_query_service()

    def get_story_evolution_read_model(self, novel_id: str) -> Dict[str, Any]:
        """一书一页：生命周期 × 骨架 × 时空轴 × 章节 digest（+ 伏笔规模提示）。"""
        ctx = self._query().get_workbench_context(novel_id).to_dict()
        life = self._story_phase_resolver(novel_id)
        foreshadow = ctx.get("foreshadow_ledger") or []
        evolution_surface: Dict[str, Any] = {
            "active_snapshot": None,
            "counts": {"active": 0, "stale": 0, "blocked": 0},
            "recent_gate_risks": [],
            "required_continuations": [],
        }
        try:
            if not self._evolution_repository_factory or not self._context_presenter_factory:
                raise RuntimeError("evolution dependencies not injected")
            repo = self._evolution_repository_factory()
            latest = repo.get_latest_active(novel_id, "main")
            counts = repo.count_by_status(novel_id, "main")
            if latest:
                required = latest.ending_state.scene.get("unresolved_actions") or []
                presenter = self._context_presenter_factory()
                evolution_surface = {
                    "active_snapshot": {
                        "snapshot_id": latest.snapshot_id,
                        "chapter_number": latest.chapter_number,
                        "status": latest.status,
                        "schema_version": latest.schema_version,
                        "summary": presenter.present(latest.ending_state, max_lines=12),
                    },
                    "counts": {
                        "active": int(counts.get("active", 0)),
                        "stale": int(counts.get("stale", 0)),
                        "blocked": int(counts.get("blocked", 0)),
                    },
                    "recent_gate_risks": latest.conflicts[-5:],
                    "required_continuations": [str(x) for x in required],
                }
            else:
                evolution_surface["counts"] = {
                    "active": int(counts.get("active", 0)),
                    "stale": int(counts.get("stale", 0)),
                    "blocked": int(counts.get("blocked", 0)),
                }
        except Exception:
            pass
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
            "evolution_surface": evolution_surface,
        }

    def get_persona_voice_read_model(self, novel_id: str, character_id: str) -> Dict[str, Any]:
        """单角一线：声线锚点 + 全书对白语料统计（正文抽取，与沙盒生成解耦）。"""
        if not self._bible_service or not self._sandbox_dialogue_service:
            raise RuntimeError("persona voice dependencies not injected")

        bible = self._bible_service.get_bible_by_novel(novel_id)
        if not bible:
            raise ValueError("bible_not_found")

        character = next((c for c in bible.characters if c.id == character_id), None)
        if not character:
            raise ValueError("character_not_found")

        wl = self._sandbox_dialogue_service.get_dialogue_whitelist(novel_id=novel_id)
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
