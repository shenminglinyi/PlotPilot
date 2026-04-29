from domain.knowledge.chapter_summary import ChapterSummary
from domain.knowledge.knowledge_triple import KnowledgeTriple
from domain.knowledge.story_knowledge import StoryKnowledge

from application.analyst.services.novelpro_monitor_service import NovelProMonitorService


class FakeKnowledgeService:
    def __init__(self, knowledge):
        self.knowledge = knowledge

    def get_knowledge(self, novel_id):
        return self.knowledge


class FakeObsidianMemoryService:
    def __init__(self, knowledge):
        self.knowledge = knowledge
        self.vault_root = "/vault"
        self.synced = []

    def load_knowledge(self, novel_id):
        return self.knowledge

    def get_relationship_graph_path(self, novel_id):
        return f"/vault/{novel_id}/03_Entities/Character_Relationships.md"

    def is_obsidian_installed(self):
        return True

    def sync_chapter(self, novel_id, chapter_number):
        self.synced.append((novel_id, chapter_number))
        return {
            "synced": True,
            "chapter_note": f"/vault/{novel_id}/02_Chapters/Chapter_{chapter_number:04d}.md",
        }


class FakeContinuityService:
    def get_overview(self, novel_id, chapter_number=None):
        return {
            "novel_id": novel_id,
            "chapter_number": chapter_number or 3,
            "latest_chapter_number": 3,
            "character_dropouts": [
                {
                    "character_name": "林夜",
                    "severity": "high",
                    "chapters_absent": 7,
                }
            ],
            "relationship_tracking": {
                "tracked_pairs": 2,
                "active_signals": [],
                "stale_pairs": [
                    {
                        "source_character": "林夜",
                        "target_character": "玄鸦",
                        "chapters_since_joint": 6,
                        "severity": "warning",
                    }
                ],
            },
            "voice_drift": {
                "drift_alert": True,
                "latest_similarity_score": 0.61,
            },
            "timeline": {
                "conflict_count": 1,
                "current_chapter_has_event": False,
            },
            "outline_deviation": {
                "status": "warning",
                "warning_reasons": ["正文没有覆盖黑塔潜入节点"],
            },
        }


class FakePowerSystemService:
    def get_overview(self, novel_id):
        return {
            "profiles": [{"character_name": "林夜"}],
            "warnings": [
                {
                    "severity": "error",
                    "title": "第3章战力跳升过快",
                    "message": "单次变化 +3，建议补代价。",
                }
            ],
        }


class SoftTimelineContinuityService:
    def get_overview(self, novel_id, chapter_number=None):
        return {
            "novel_id": novel_id,
            "chapter_number": chapter_number or 1,
            "relationship_tracking": {
                "active_signals": [{"source_character": "林夜", "target_character": "苏晚"}],
                "stale_pairs": [],
            },
            "voice_drift": {"drift_alert": False},
            "timeline": {
                "conflict_count": 1,
                "current_chapter_has_event": True,
            },
            "outline_deviation": {"status": "aligned"},
        }


class EmptyPowerSystemService:
    def get_overview(self, novel_id):
        return {"profiles": [{"character_name": "林夜"}], "warnings": []}


def test_novelpro_monitor_aggregates_obsidian_continuity_and_power_alerts():
    knowledge = StoryKnowledge(
        novel_id="novel-monitor",
        premise_lock="黑塔城禁止灵脉外泄。",
        chapters=[ChapterSummary(1, summary="林夜潜入黑塔城。")],
        facts=[
            KnowledgeTriple(
                id="fact-1",
                subject="林夜",
                predicate="敌对",
                object="黑塔会",
                tags=["角色关系"],
            )
        ],
    )
    service = NovelProMonitorService(
        knowledge_service=FakeKnowledgeService(knowledge),
        obsidian_memory_service=FakeObsidianMemoryService(knowledge),
        continuity_service=FakeContinuityService(),
        power_system_service=FakePowerSystemService(),
    )

    overview = service.get_overview("novel-monitor", chapter_number=3)

    assert overview["obsidian"]["primary_memory"] is True
    assert overview["obsidian"]["vault_path"] == "/vault"
    assert overview["obsidian"]["obsidian_app_installed"] is True
    assert overview["obsidian"]["relationship_graph_path"].endswith("Character_Relationships.md")
    assert overview["knowledge_graph"]["relationship_count"] == 1
    assert overview["continuity"]["timeline_conflict_count"] == 1
    assert overview["power"]["warning_count"] == 1
    alert_titles = [alert["title"] for alert in overview["alerts"]]
    assert "Obsidian 主记忆已接管" in alert_titles
    assert "角色掉线：林夜" in alert_titles
    assert "大纲偏离提醒" in alert_titles
    assert "第3章战力跳升过快" in alert_titles
    assert overview["health"]["status"] == "error"


def test_novelpro_monitor_keeps_soft_timeline_conflict_as_warning():
    knowledge = StoryKnowledge(
        novel_id="novel-monitor",
        premise_lock="黑塔城禁止灵脉外泄。",
        chapters=[ChapterSummary(1, summary="林夜潜入黑塔城。")],
        facts=[
            KnowledgeTriple(
                id="fact-1",
                subject="林夜",
                predicate="敌对",
                object="黑塔会",
                tags=["角色关系"],
            )
        ],
    )
    service = NovelProMonitorService(
        knowledge_service=FakeKnowledgeService(knowledge),
        obsidian_memory_service=FakeObsidianMemoryService(knowledge),
        continuity_service=SoftTimelineContinuityService(),
        power_system_service=EmptyPowerSystemService(),
    )

    overview = service.get_overview("novel-monitor", chapter_number=1)

    assert overview["continuity"]["timeline_conflict_count"] == 1
    assert overview["health"]["status"] == "warning"
    assert overview["health"]["error_count"] == 0
    assert any(
        alert["title"] == "时间线需确认" and alert["severity"] == "warning"
        for alert in overview["alerts"]
    )


def test_novelpro_monitor_can_sync_current_chapter_to_obsidian():
    knowledge = StoryKnowledge(
        novel_id="novel-monitor",
        chapters=[ChapterSummary(3, summary="林夜打开黑塔密门。")],
    )
    obsidian = FakeObsidianMemoryService(knowledge)
    service = NovelProMonitorService(
        knowledge_service=FakeKnowledgeService(knowledge),
        obsidian_memory_service=obsidian,
        continuity_service=FakeContinuityService(),
        power_system_service=FakePowerSystemService(),
    )

    result = service.sync_obsidian_chapter("novel-monitor", 3)

    assert result["synced"] is True
    assert result["chapter_note"].endswith("Chapter_0003.md")
    assert obsidian.synced == [("novel-monitor", 3)]
