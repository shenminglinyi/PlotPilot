"""CharacterId 统一来源测试"""
from domain.shared.character_id import CharacterId
from domain.bible.value_objects.character_id import CharacterId as BibleCharacterId
from domain.cast.value_objects.character_id import CharacterId as CastCharacterId
from domain.character.value_objects.character_id import CharacterId as CharacterDomainId
from engine.core.entities.character import CharacterId as EngineCharacterId


def test_all_import_paths_are_same_class():
    assert BibleCharacterId is CharacterId
    assert CastCharacterId is CharacterId
    assert CharacterDomainId is CharacterId
    assert EngineCharacterId is CharacterId


def test_cross_module_equality():
    a = BibleCharacterId("char-123")
    b = CastCharacterId("char-123")
    c = EngineCharacterId("char-123")
    assert a == b == c


def test_generate():
    cid = CharacterId.generate()
    assert cid.value
    assert isinstance(cid, CharacterId)
