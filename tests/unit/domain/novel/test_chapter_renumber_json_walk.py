from domain.novel.chapter_renumber.json_walk import renumber_chapter_integers_in_json
from domain.novel.value_objects.chapter_renumber_spec import ChapterRenumberSpec


def test_walk_nested_dict_and_list():
    spec = ChapterRenumberSpec(novel_id="n", deleted_chapter_number=2)
    data = {
        "a": 1,
        "chapter_number": 3,
        "nested": [{"planted_in_chapter": 2}, {"x": 5}],
    }
    out = renumber_chapter_integers_in_json(data, spec)
    assert out["a"] == 1
    assert out["chapter_number"] == 2
    assert out["nested"][0]["planted_in_chapter"] == 1
    assert out["nested"][1]["x"] == 5
