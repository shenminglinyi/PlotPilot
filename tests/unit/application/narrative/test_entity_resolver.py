from dataclasses import dataclass, field

from application.narrative.entity_resolver import EntityResolver


@dataclass
class _Id:
    value: str


@dataclass
class _Character:
    id: _Id
    name: str


@dataclass
class _Prop:
    id: _Id
    name: str
    aliases: list[str] = field(default_factory=list)


class _Repo:
    def __init__(self, rows):
        self.rows = rows

    def list_by_novel(self, novel_id):
        return self.rows


def test_resolves_character_by_name():
    resolver = EntityResolver(
        character_repo=_Repo([_Character(_Id("char-1"), "林澈")]),
    )

    entity = resolver.resolve("novel-1", "林澈")

    assert entity is not None
    assert entity.id == "char-1"
    assert entity.entity_type == "character"
    assert entity.matched_by == "name"


def test_resolves_prop_by_alias():
    resolver = EntityResolver(
        prop_repo=_Repo([_Prop(_Id("prop-1"), "青铜罗盘", ["罗盘", "司南"])]),
    )

    entity = resolver.resolve("novel-1", "司南", allowed_types=["prop"])

    assert entity is not None
    assert entity.id == "prop-1"
    assert entity.entity_type == "prop"
    assert entity.matched_by == "alias"
