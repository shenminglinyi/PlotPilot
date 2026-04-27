from fastapi.testclient import TestClient
from typing import Optional

from interfaces.api.dependencies import get_continuity_overview_service
from interfaces.main import app


class _FakeContinuityOverviewService:
    def get_overview(self, novel_id: str, chapter_number: Optional[int] = None):
        return {
            "novel_id": novel_id,
            "chapter_number": chapter_number or 12,
            "latest_chapter_number": 12,
            "character_dropouts": [
                {
                    "character_id": "char-lin",
                    "character_name": "林羽",
                    "last_appearance_chapter": 4,
                    "chapters_absent": 8,
                    "appearance_count": 2,
                    "severity": "high",
                }
            ],
            "relationship_spotlights": [
                {
                    "source_character": "林羽",
                    "target_character": "苏晴",
                    "relation": "盟友",
                    "description": "目前仍互相信任",
                }
            ],
            "voice_drift": {
                "drift_alert": True,
                "latest_similarity_score": 0.63,
                "scored_chapters": 2,
                "alert_threshold": 0.75,
                "alert_consecutive": 5,
            },
            "timeline": {
                "total_events": 1,
                "current_chapter_has_event": False,
                "current_chapter_events": [],
                "recent_events": [
                    {
                        "id": "evt-11",
                        "chapter_number": 11,
                        "event": "深夜潜入",
                        "timestamp": "当夜",
                        "timestamp_type": "relative",
                    }
                ],
            },
        }


class TestContinuityAPI:
    def setup_method(self):
        app.dependency_overrides[get_continuity_overview_service] = lambda: _FakeContinuityOverviewService()
        self.client = TestClient(app)

    def teardown_method(self):
        app.dependency_overrides.clear()

    def test_get_continuity_overview(self):
        response = self.client.get(
            "/api/v1/novels/demo-novel/continuity/overview",
            params={"chapter_number": 12},
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["novel_id"] == "demo-novel"
        assert payload["chapter_number"] == 12
        assert payload["voice_drift"]["drift_alert"] is True
        assert payload["timeline"]["current_chapter_has_event"] is False
        assert payload["character_dropouts"][0]["character_name"] == "林羽"
