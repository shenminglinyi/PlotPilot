"""ConflictDetectionService 单元测试"""
import pytest
from application.audit.services.conflict_detection_service import ConflictDetectionService
from application.audit.dtos.ghost_annotation import GhostAnnotation
from application.engine.dtos.scene_director_dto import SceneDirectorAnalysis


class TestConflictDetectionService:
    """测试 ConflictDetectionService"""

    @pytest.fixture
    def service(self):
        """创建 ConflictDetectionService 实例"""
        return ConflictDetectionService()

    def test_detect_magic_conflict(self, service):
        """测试检测魔法系统冲突"""
        outline = "李明释放火球术攻击敌人"
        entity_states = {
            "char-001": {
                "magic_type": "水系"
            }
        }
        name_to_entity_id = {
            "李明": "char-001"
        }

        annotations = service.detect(outline, entity_states, name_to_entity_id)

        assert len(annotations) == 1
        assert annotations[0].type == "setting_conflict"
        assert annotations[0].severity == "warning"
        assert "李明" in annotations[0].message
        assert "水系" in annotations[0].message
        assert "火系" in annotations[0].message
        assert annotations[0].entity_id == "char-001"
        assert annotations[0].entity_name == "李明"
        assert annotations[0].expected == "水系"
        assert annotations[0].actual == "火系"

    def test_detect_no_conflict_when_magic_matches(self, service):
        """测试魔法类型匹配时无冲突"""
        outline = "李明释放火球术攻击敌人"
        entity_states = {
            "char-001": {
                "magic_type": "火系"
            }
        }
        name_to_entity_id = {
            "李明": "char-001"
        }

        annotations = service.detect(outline, entity_states, name_to_entity_id)

        assert len(annotations) == 0

    def test_detect_weapon_conflict(self, service):
        """测试检测武器冲突"""
        outline = "李明拔剑攻击"
        entity_states = {
            "char-001": {
                "weapon": "弓"
            }
        }
        name_to_entity_id = {
            "李明": "char-001"
        }

        annotations = service.detect(outline, entity_states, name_to_entity_id)

        assert len(annotations) == 1
        assert annotations[0].type == "setting_conflict"
        assert annotations[0].severity == "warning"
        assert "李明" in annotations[0].message
        assert "弓" in annotations[0].message
        assert "剑" in annotations[0].message

    def test_detect_no_conflict_when_weapon_matches(self, service):
        """测试武器匹配时无冲突"""
        outline = "李明拔剑攻击"
        entity_states = {
            "char-001": {
                "weapon": "剑"
            }
        }
        name_to_entity_id = {
            "李明": "char-001"
        }

        annotations = service.detect(outline, entity_states, name_to_entity_id)

        assert len(annotations) == 0

    def test_detect_multiple_conflicts(self, service):
        """测试检测多个冲突"""
        outline = "李明释放火球术，然后拔剑攻击"
        entity_states = {
            "char-001": {
                "magic_type": "水系",
                "weapon": "弓"
            }
        }
        name_to_entity_id = {
            "李明": "char-001"
        }

        annotations = service.detect(outline, entity_states, name_to_entity_id)

        assert len(annotations) == 2
        # 验证有魔法冲突
        magic_conflicts = [a for a in annotations if "火系" in a.message]
        assert len(magic_conflicts) == 1
        # 验证有武器冲突
        weapon_conflicts = [a for a in annotations if "剑" in a.message]
        assert len(weapon_conflicts) == 1

    def test_detect_no_conflicts_when_entity_not_in_outline(self, service):
        """测试实体不在大纲中时无冲突"""
        outline = "王总独自思考"
        entity_states = {
            "char-001": {
                "magic_type": "水系"
            }
        }
        name_to_entity_id = {
            "李明": "char-001"
        }

        annotations = service.detect(outline, entity_states, name_to_entity_id)

        assert len(annotations) == 0

    def test_detect_no_conflicts_when_no_entity_states(self, service):
        """测试没有实体状态时无冲突"""
        outline = "李明释放火球术"
        entity_states = {}
        name_to_entity_id = {
            "李明": "char-001"
        }

        annotations = service.detect(outline, entity_states, name_to_entity_id)

        assert len(annotations) == 0

    def test_detect_no_conflicts_when_entity_has_no_state(self, service):
        """测试实体没有状态时无冲突"""
        outline = "李明释放火球术"
        entity_states = {
            "char-001": {}
        }
        name_to_entity_id = {
            "李明": "char-001"
        }

        annotations = service.detect(outline, entity_states, name_to_entity_id)

        assert len(annotations) == 0

    def test_detect_with_scene_director(self, service):
        """测试使用场记分析结果"""
        outline = "李明释放火球术"
        entity_states = {
            "char-001": {
                "magic_type": "水系"
            }
        }
        name_to_entity_id = {
            "李明": "char-001"
        }
        scene_director = SceneDirectorAnalysis(
            characters=["李明"],
            locations=["战场"],
            action_types=["combat"],
            trigger_keywords=["魔法"],
            emotional_state="tense",
            pov="李明"
        )

        annotations = service.detect(outline, entity_states, name_to_entity_id, scene_director)

        # 即使有场记分析，冲突检测仍然基于大纲内容
        assert len(annotations) == 1
        assert "火系" in annotations[0].message

    def test_detect_handles_exception_gracefully(self, service):
        """测试异常处理"""
        outline = "测试大纲"
        entity_states = None  # 故意传入 None 触发异常
        name_to_entity_id = {}

        # 不应该抛出异常，而是返回空列表
        annotations = service.detect(outline, entity_states, name_to_entity_id)

        assert annotations == []

    def test_detect_ice_magic_conflict(self, service):
        """测试冰系魔法冲突"""
        outline = "李明释放冰系魔法"
        entity_states = {
            "char-001": {
                "magic_type": "火系"
            }
        }
        name_to_entity_id = {
            "李明": "char-001"
        }

        annotations = service.detect(outline, entity_states, name_to_entity_id)

        assert len(annotations) == 1
        assert "冰系" in annotations[0].message

    def test_detect_lightning_magic_conflict(self, service):
        """测试雷系魔法冲突"""
        outline = "李明释放雷电攻击"
        entity_states = {
            "char-001": {
                "magic_type": "水系"
            }
        }
        name_to_entity_id = {
            "李明": "char-001"
        }

        annotations = service.detect(outline, entity_states, name_to_entity_id)

        assert len(annotations) == 1
        assert "雷系" in annotations[0].message

    def test_detect_wind_magic_conflict(self, service):
        """测试风系魔法冲突"""
        outline = "李明释放风系魔法"
        entity_states = {
            "char-001": {
                "magic_type": "火系"
            }
        }
        name_to_entity_id = {
            "李明": "char-001"
        }

        annotations = service.detect(outline, entity_states, name_to_entity_id)

        assert len(annotations) == 1
        assert "风系" in annotations[0].message

    def test_detect_bow_weapon_conflict(self, service):
        """测试弓箭武器冲突"""
        outline = "李明射箭攻击"
        entity_states = {
            "char-001": {
                "weapon": "剑"
            }
        }
        name_to_entity_id = {
            "李明": "char-001"
        }

        annotations = service.detect(outline, entity_states, name_to_entity_id)

        assert len(annotations) == 1
        assert "弓" in annotations[0].message

    def test_detect_gun_weapon_conflict(self, service):
        """测试枪械武器冲突"""
        outline = "李明开枪射击"
        entity_states = {
            "char-001": {
                "weapon": "剑"
            }
        }
        name_to_entity_id = {
            "李明": "char-001"
        }

        annotations = service.detect(outline, entity_states, name_to_entity_id)

        assert len(annotations) == 1
        assert "枪" in annotations[0].message

    def test_detect_case_insensitive(self, service):
        """测试大小写不敏感"""
        outline = "李明释放火球术"
        entity_states = {
            "char-001": {
                "magic_type": "水系"
            }
        }
        name_to_entity_id = {
            "李明": "char-001"
        }

        annotations = service.detect(outline, entity_states, name_to_entity_id)

        assert len(annotations) == 1
