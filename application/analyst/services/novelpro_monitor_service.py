"""NovelPro 自动监控聚合服务。"""
from __future__ import annotations

from typing import Any, Optional


RELATIONSHIP_MARKERS = (
    "关系",
    "敌",
    "友",
    "同盟",
    "盟友",
    "师",
    "徒",
    "亲",
    "父",
    "母",
    "兄",
    "姐",
    "妹",
    "爱",
    "恨",
    "追随",
    "背叛",
    "保护",
    "隶属",
)


class NovelProMonitorService:
    """把 Obsidian 主记忆、连续性和战力风险收束成右侧监控中心。"""

    def __init__(
        self,
        *,
        knowledge_service,
        obsidian_memory_service,
        obsidian_sync_service=None,
        continuity_service,
        power_system_service,
    ) -> None:
        self.knowledge_service = knowledge_service
        self.obsidian_memory_service = obsidian_memory_service
        self.obsidian_sync_service = obsidian_sync_service or obsidian_memory_service
        self.continuity_service = continuity_service
        self.power_system_service = power_system_service

    def get_overview(self, novel_id: str, chapter_number: Optional[int] = None) -> dict[str, Any]:
        knowledge = self._safe_call(lambda: self.knowledge_service.get_knowledge(novel_id))
        obsidian_knowledge = self._safe_call(lambda: self.obsidian_memory_service.load_knowledge(novel_id))
        continuity = self._safe_call(
            lambda: self.continuity_service.get_overview(novel_id, chapter_number)
        ) or {}
        power = self._safe_call(lambda: self.power_system_service.get_overview(novel_id)) or {}

        effective_knowledge = obsidian_knowledge or knowledge
        alerts = []

        obsidian = self._build_obsidian_summary(novel_id, obsidian_knowledge)
        knowledge_graph = self._build_knowledge_graph_summary(effective_knowledge)
        continuity_summary = self._build_continuity_summary(continuity)
        power_summary = self._build_power_summary(power)

        alerts.extend(self._build_obsidian_alerts(obsidian, knowledge_graph))
        alerts.extend(self._build_continuity_alerts(continuity))
        alerts.extend(self._build_power_alerts(power))

        health = self._build_health(alerts)
        return {
            "novel_id": novel_id,
            "chapter_number": int(continuity.get("chapter_number") or chapter_number or 0),
            "health": health,
            "obsidian": obsidian,
            "knowledge_graph": knowledge_graph,
            "continuity": continuity_summary,
            "power": power_summary,
            "alerts": alerts,
        }

    def sync_obsidian_chapter(self, novel_id: str, chapter_number: int) -> dict[str, Any]:
        sync_chapter = getattr(self.obsidian_sync_service, "sync_chapter", None)
        if not callable(sync_chapter):
            return {
                "synced": False,
                "reason": "obsidian memory service unavailable",
            }
        return sync_chapter(novel_id, chapter_number)

    def _build_obsidian_summary(self, novel_id: str, knowledge: Any) -> dict[str, Any]:
        graph_path = ""
        get_graph_path = getattr(self.obsidian_memory_service, "get_relationship_graph_path", None)
        if callable(get_graph_path):
            graph_path = str(get_graph_path(novel_id))
        is_installed = getattr(self.obsidian_memory_service, "is_obsidian_installed", None)
        is_configured = getattr(self.obsidian_memory_service, "is_vault_configured", None)
        return {
            "primary_memory": knowledge is not None,
            "premise_locked": bool(getattr(knowledge, "premise_lock", "") if knowledge else ""),
            "fact_count": len(getattr(knowledge, "facts", []) or []) if knowledge else 0,
            "chapter_count": len(getattr(knowledge, "chapters", []) or []) if knowledge else 0,
            "relationship_graph_path": graph_path,
            "vault_path": str(getattr(self.obsidian_memory_service, "vault_root", "") or ""),
            "vault_configured": bool(is_configured()) if callable(is_configured) else False,
            "obsidian_app_installed": bool(is_installed()) if callable(is_installed) else False,
        }

    def _build_knowledge_graph_summary(self, knowledge: Any) -> dict[str, Any]:
        facts = list(getattr(knowledge, "facts", []) or []) if knowledge else []
        entities = set()
        relationship_count = 0
        for fact in facts:
            subject = str(getattr(fact, "subject", "") or "").strip()
            obj = str(getattr(fact, "object", "") or "").strip()
            if subject:
                entities.add(subject)
            if obj:
                entities.add(obj)
            if self._is_relationship_fact(fact):
                relationship_count += 1
        return {
            "fact_count": len(facts),
            "relationship_count": relationship_count,
            "entity_count": len(entities),
        }

    @staticmethod
    def _build_continuity_summary(continuity: dict[str, Any]) -> dict[str, Any]:
        relationship_tracking = continuity.get("relationship_tracking") or {}
        voice_drift = continuity.get("voice_drift") or {}
        timeline = continuity.get("timeline") or {}
        outline = continuity.get("outline_deviation") or {}
        return {
            "dropout_count": len(continuity.get("character_dropouts") or []),
            "stale_relationship_count": len(relationship_tracking.get("stale_pairs") or []),
            "active_relationship_signal_count": len(relationship_tracking.get("active_signals") or []),
            "voice_drift_alert": bool(voice_drift.get("drift_alert", False)),
            "timeline_conflict_count": int(timeline.get("conflict_count") or 0),
            "current_chapter_has_timeline_event": bool(timeline.get("current_chapter_has_event", False)),
            "outline_status": str(outline.get("status") or "unavailable"),
        }

    @staticmethod
    def _build_power_summary(power: dict[str, Any]) -> dict[str, Any]:
        return {
            "profile_count": len(power.get("profiles") or []),
            "warning_count": len(power.get("warnings") or []),
        }

    def _build_obsidian_alerts(
        self,
        obsidian: dict[str, Any],
        knowledge_graph: dict[str, Any],
    ) -> list[dict[str, str]]:
        alerts = []
        if obsidian["primary_memory"]:
            alerts.append(self._alert(
                "info",
                "obsidian",
                "Obsidian 主记忆已接管",
                "当前 PP 知识读取会优先使用 Obsidian vault，并把结果同步回 PP 缓存。",
                "继续写作时会自动导出章节摘要、事实锁和关系图。",
            ))
        else:
            alerts.append(self._alert(
                "warning",
                "obsidian",
                "Obsidian 主记忆尚未建立",
                "还没有检测到可回读的 Obsidian 长期记忆，建议先保存或采纳一章触发章后管线。",
                "写入章节后等待自动同步，或检查 PLOTPILOT_OBSIDIAN_VAULT 配置。",
            ))
        if knowledge_graph["relationship_count"] == 0:
            alerts.append(self._alert(
                "warning",
                "knowledge",
                "关系图缺少结构化关系",
                "当前知识三元组里没有明显角色/故事关系，关系图和掉线监控会偏弱。",
                "在设定或正文中补充角色关系，章后管线会自动沉淀到 Obsidian。",
            ))
        return alerts

    def _build_continuity_alerts(self, continuity: dict[str, Any]) -> list[dict[str, str]]:
        alerts = []
        for item in continuity.get("character_dropouts") or []:
            name = str(item.get("character_name") or item.get("character_id") or "未知角色")
            alerts.append(self._alert(
                self._normalize_severity(item.get("severity"), default="warning"),
                "continuity",
                f"角色掉线：{name}",
                f"{name} 已缺席 {int(item.get('chapters_absent') or 0)} 章，可能需要回收人物线或说明离场。",
                "可在连续性巡检中创建候选改稿任务。",
            ))
        relationship_tracking = continuity.get("relationship_tracking") or {}
        for item in relationship_tracking.get("stale_pairs") or []:
            source = str(item.get("source_character") or "")
            target = str(item.get("target_character") or "")
            alerts.append(self._alert(
                self._normalize_severity(item.get("severity"), default="warning"),
                "continuity",
                f"关系线沉默：{source} / {target}",
                f"这条关系线已沉默 {int(item.get('chapters_since_joint') or 0)} 章。",
                "继续写作前建议安排互动、冲突或明确暂时搁置。",
            ))
        voice_drift = continuity.get("voice_drift") or {}
        if voice_drift.get("drift_alert"):
            alerts.append(self._alert(
                "warning",
                "continuity",
                "文风漂移提醒",
                "最近章节低于口吻相似度阈值，建议先做口吻锁定或精细改稿。",
                "打开口吻锁定面板校准作者样本和角色锚点。",
            ))
        timeline = continuity.get("timeline") or {}
        if int(timeline.get("conflict_count") or 0) > 0:
            alerts.append(self._alert(
                "error",
                "continuity",
                "时间线冲突提醒",
                "当前时间线存在冲突或顺序异常，需要先确认事件先后再继续写。",
                "打开连续性巡检查看冲突证据。",
            ))
        elif not timeline.get("current_chapter_has_event") and int(continuity.get("chapter_number") or 0) > 0:
            alerts.append(self._alert(
                "warning",
                "continuity",
                "当前章节缺少时间锚点",
                "本章没有进入时间线注册表，后续容易出现时间漂移。",
                "若本章发生了时间推进，请补充时间线事件。",
            ))
        outline = continuity.get("outline_deviation") or {}
        if outline.get("status") in {"warning", "watch"}:
            reasons = "；".join(outline.get("warning_reasons") or [])
            alerts.append(self._alert(
                "warning" if outline.get("status") == "warning" else "info",
                "continuity",
                "大纲偏离提醒",
                reasons or "当前章节和大纲节点覆盖不完整。",
                "打开连续性巡检生成结构化修稿方案。",
            ))
        return alerts

    def _build_power_alerts(self, power: dict[str, Any]) -> list[dict[str, str]]:
        alerts = []
        for item in power.get("warnings") or []:
            alerts.append(self._alert(
                self._normalize_severity(item.get("severity"), default="warning"),
                "power",
                str(item.get("title") or "战力系统提醒"),
                str(item.get("message") or "战力规则存在待确认项。"),
                "打开战力系统面板补齐规则、角色限制或升级代价。",
            ))
        return alerts

    @staticmethod
    def _build_health(alerts: list[dict[str, str]]) -> dict[str, Any]:
        error_count = sum(1 for alert in alerts if alert["severity"] == "error")
        warning_count = sum(1 for alert in alerts if alert["severity"] == "warning")
        status = "error" if error_count else "warning" if warning_count else "ok"
        score = max(0, 100 - error_count * 30 - warning_count * 12)
        return {
            "status": status,
            "score": score,
            "error_count": error_count,
            "warning_count": warning_count,
            "alert_count": len(alerts),
        }

    @staticmethod
    def _safe_call(factory):
        try:
            return factory()
        except Exception:
            return None

    @staticmethod
    def _is_relationship_fact(fact: Any) -> bool:
        text = " ".join(
            [
                str(getattr(fact, "predicate", "") or ""),
                " ".join(getattr(fact, "tags", []) or []),
            ]
        )
        return any(marker in text for marker in RELATIONSHIP_MARKERS)

    @staticmethod
    def _normalize_severity(value: Any, default: str = "info") -> str:
        severity = str(value or default).lower()
        if severity == "high":
            return "error"
        if severity == "medium":
            return "warning"
        if severity in {"info", "success", "warning", "error"}:
            return severity
        return default

    @staticmethod
    def _alert(severity: str, source: str, title: str, message: str, action: str) -> dict[str, str]:
        return {
            "severity": severity,
            "source": source,
            "title": title,
            "message": message,
            "action": action,
        }
