"""Manifest-driven read → model → artifact, separate from human adoption."""
import asyncio
import json
import uuid

from pydantic import ValidationError

from application.plugin_pilot.contracts import (
    CharacterPatch, MAX_CALLS, MAX_INPUT_TOKENS, MAX_OUTPUT_BYTES,
    MAX_OUTPUT_TOKENS, TIMEOUT_SECONDS, PilotError,
)
from application.plugin_pilot.loader import load_official
from domain.ai.value_objects.prompt import Prompt


class PilotService:
    def __init__(self, queue, model, packages=None):
        self.queue = queue
        self.model = model
        self._packages = packages
        # One local manual generation at a time; no background daemon or retries.
        self._running = False

    def packages(self):
        return self._packages if self._packages is not None else load_official()

    async def command(self, action, **kwargs):
        return await self.queue.execute_confirmed("plugin_pilot", {"action": action, **kwargs})

    def catalog(self):
        return {"plugins": [{**p.manifest.model_dump(), "digest": p.digest} for p in self.packages().values()],
                "limits": {"input_tokens": MAX_INPUT_TOKENS, "output_tokens": MAX_OUTPUT_TOKENS,
                           "calls": MAX_CALLS, "timeout_seconds": TIMEOUT_SECONDS,
                           "chapter_characters": 8000, "field_characters": 600}}

    async def run(self, request):
        if self._running:
            raise PilotError("Another pilot run is active; wait for its result", 429)
        package = self.packages().get(request.plugin_id)
        if package is None:
            raise PilotError("Official plugin not found", 404)
        self._running = True
        state = {"calls": 0}
        try:
            # No branch on plugin ID. The manifest selects a finite capability
            # sequence; the host owns every implementation and output type.
            handlers = {"read_snapshot": self._read, "render_template": self._render,
                        "invoke_model": self._invoke, "validate_artifact": self._validate,
                        "submit_artifact": self._submit}
            for action in package.manifest.steps:
                await handlers[action](state, package, request)
            return state["candidate"]
        finally:
            self._running = False

    async def _read(self, state, package, request):
        state["snapshot"] = await self.command("snapshot", project_id=request.project_id,
            chapter_id=request.chapter_id, character_id=request.character_id)

    async def _render(self, state, package, request):
        data = json.dumps(state["snapshot"], ensure_ascii=False, separators=(",", ":"))
        prompt = Prompt(system="Generate only the host-defined character_card_patch@1 JSON candidate.",
                        user=package.template.replace("{{snapshot}}", data))
        # UTF-8 bytes plus protocol reserve is a conservative token budget;
        # provider-reported usage is separately checked after generation.
        state["input_token_upper_bound"] = len((prompt.system + prompt.user).encode("utf-8")) + 1024
        if state["input_token_upper_bound"] > MAX_INPUT_TOKENS:
            raise PilotError("Selected input exceeds conservative pilot token budget", 422)
        state["prompt"] = prompt

    async def _invoke(self, state, package, request):
        if state["calls"] >= MAX_CALLS:
            raise PilotError("Model call budget exhausted", 422)
        state["calls"] += 1
        try:
            result, identity = await asyncio.wait_for(
                self.model.generate(state["prompt"], request.model_signature), TIMEOUT_SECONDS)
        except asyncio.TimeoutError as exc:
            raise PilotError("Model timed out; no candidate saved. Upstream completion is unknown.", 504) from exc
        except PilotError:
            raise
        except Exception as exc:
            raise PilotError("Model request failed; no candidate saved. Check the configured endpoint.", 502) from exc
        if len(result.content.encode("utf-8")) > MAX_OUTPUT_BYTES:
            raise PilotError("Model output exceeds byte limit", 422)
        if result.token_usage.input_tokens > MAX_INPUT_TOKENS or result.token_usage.output_tokens > MAX_OUTPUT_TOKENS:
            raise PilotError("Model token usage exceeds pilot budget", 422)
        state.update(result=result, model=identity)

    async def _validate(self, state, package, request):
        try:
            output = CharacterPatch.model_validate_json(state["result"].content)
        except ValidationError as exc:
            raise PilotError("Model output failed character_card_patch@1 schema validation", 422) from exc
        chapter = state["snapshot"]["chapter"]["content"]
        if any(e.quote not in chapter for e in output.evidence):
            raise PilotError("Evidence must be an exact quote from the selected chapter", 422)
        state["output"] = output.model_dump()

    async def _submit(self, state, package, request):
        output = state["output"]
        candidate = {"id": uuid.uuid4().hex, "artifact_type": "character_card_patch@1",
            "plugin": {"id": package.manifest.id, "version": package.manifest.version,
                       "digest": package.digest, "host_api": package.manifest.host_api},
            "snapshot": state["snapshot"], "output": output,
            "output_schema": CharacterPatch.model_json_schema(),
            "model": state["model"], "consent": {"confirmed": True, "scope": "one saved chapter and one existing character"},
            "usage": {"input_tokens": state["result"].token_usage.input_tokens,
                      "output_tokens": state["result"].token_usage.output_tokens,
                      "input_token_upper_bound": state["input_token_upper_bound"], "calls": state["calls"]},
            "diff": [{"field": key, "before": state["snapshot"]["character"][key], "after": value}
                     for key, value in output["patch"].items()]}
        state["candidate"] = await self.command("store", candidate=candidate)
