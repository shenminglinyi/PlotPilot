from pathlib import Path


def test_autopilot_modules_do_not_import_llm_service_directly():
    root = Path("application/ai_invocation/autopilot")
    offenders = []
    for path in root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if "from domain.ai.services.llm_service import LLMService" in text:
            offenders.append(path.as_posix())
    assert offenders == []
