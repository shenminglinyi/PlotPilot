import pytest

from application.ai_invocation.autopilot.helper_invoker import (
    AutopilotHelperInvoker,
    AutopilotHelperRequest,
)
from infrastructure.ai.prompt_utils import PromptTemplateUnavailable


@pytest.mark.asyncio
async def test_helper_invoker_wraps_contract_failures_as_prompt_unavailable(monkeypatch):
    def _fail_contract(_operation, _node_key, _db=None):
        raise RuntimeError("CPMS 节点未发布")

    monkeypatch.setattr(
        "application.ai_invocation.contracts.ensure_invocation_contract",
        _fail_contract,
    )

    invoker = AutopilotHelperInvoker(orchestrator=object())

    with pytest.raises(PromptTemplateUnavailable):
        await invoker.invoke_text(
            AutopilotHelperRequest(
                novel_id="novel-1",
                stage="writing",
                operation="autopilot.bridge.extract",
                node_key="chapter-bridge-extract",
            )
        )
