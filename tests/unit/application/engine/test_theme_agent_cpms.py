from application.engine.theme.theme_agent import ThemeAgent, ThemeDirectives


class _Registry:
    def get_system(self, node_key: str) -> str:
        return ""

    def get_user_template(self, node_key: str) -> str:
        return ""


class _Theme(ThemeAgent):
    @property
    def genre_key(self) -> str:
        return "unit"

    @property
    def genre_name(self) -> str:
        return "单测"

    def get_system_persona(self) -> str:
        return "本地人设不应作为运行时降级"

    def get_writing_rules(self) -> list[str]:
        return ["本地规则不应作为运行时降级"]

    def get_context_directives(
        self,
        novel_id: str,
        chapter_number: int,
        outline: str,
    ) -> ThemeDirectives:
        return ThemeDirectives(world_rules="本地世界规则不应作为运行时降级")


def test_theme_agent_effective_methods_do_not_fallback_to_subclass_text(monkeypatch):
    monkeypatch.setattr(
        "infrastructure.ai.prompt_registry.get_prompt_registry",
        lambda: _Registry(),
    )

    agent = _Theme()

    assert agent.get_effective_system_persona() == ""
    assert agent.get_effective_writing_rules() == []
    assert agent.get_effective_context_directives("n1", 1, "大纲").to_context_text() == ""
