from domain.novel.value_objects.storyline_role import StorylineRole

def test_storyline_role_values():
    assert StorylineRole.MAIN.value == "main"
    assert StorylineRole.SUB.value == "sub"
    assert StorylineRole.DARK.value == "dark"

def test_storyline_role_from_string():
    assert StorylineRole("main") == StorylineRole.MAIN
    assert StorylineRole("sub") == StorylineRole.SUB
