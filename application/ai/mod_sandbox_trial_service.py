"""Purely in-memory 300-word A/B Sandbox Trial service for Narrative Mod Packs.

Strict invariants:
- ZERO SQLite writes (no PromptManager.get_node / ensure_seeded, no INSERT/UPDATE/DELETE/ALTER/commit).
- Control (baseline) always recovers the clean unmounted prompt (stripping any PlotPilot-Mod blocks
  and rolling back in memory across prompt_versions if the active version is :START:replaced]).
- Treatment (mod) assembles the candidate pack purely in memory.
- Control & Treatment execute concurrently via asyncio.gather against the main LLM role.
"""
from __future__ import annotations

import asyncio
import re
import sqlite3
import threading
import time
from typing import Any, Callable, Dict, List, Literal, Optional, Tuple

from pydantic import BaseModel, ConfigDict, Field

from application.ai.llm_control_service import LLMControlService
from domain.ai.errors import LLMNotConfiguredError
from domain.ai.services.llm_service import GenerationConfig, LLMService
from domain.ai.value_objects.prompt import Prompt
from infrastructure.ai.prompt_seed.loader import load_seed_bundle
from infrastructure.persistence.database.connection import get_database

SAFE_MOD_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,95}$")
SAFE_NODE_KEY_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
RESERVED_MOD_MARKER_RE = re.compile(r"PlotPilot-Mod:", re.IGNORECASE)
ASCII_CONTROL_CHAR_RE = re.compile(r"[\x00-\x1f\x7f]")
# Allows standard multiline text formatting (\t, \n, \r) while rejecting NUL and other C0/DEL controls
DISALLOWED_MULTILINE_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

_MOD_DELIMITER_TOKEN_RE = re.compile(
    r"<!--\s*\[PlotPilot-Mod:(?P<mod_id>[A-Za-z0-9][A-Za-z0-9_.-]{0,95}):(?P<kind>START(?::(?:standalone|appended|replaced)|:custom:[0-9a-f]{16,64})?|END)\]\s*-->"
)

_SEED_CACHE_LOCK = threading.Lock()
_SEED_PROMPTS_BY_KEY: Optional[Dict[str, Dict[str, Any]]] = None

_FALLBACK_CHAPTER_SYSTEM = (
    "你是一位经验丰富的小说作家与叙事工程师。请严格遵循设定约束与人物性格，"
    "用克制、画面感强且具有人味的中文叙事笔法完成创作。"
)


class ModSandboxValidationError(ValueError):
    """Raised when sandbox A/B trial inputs fail strict validation or safety checks."""


class ModTrialOverrideInput(BaseModel):
    model_config = ConfigDict(extra="ignore")

    nodeKey: str
    nodeLabel: str = ""
    mode: Literal["append_protocol", "replace_system", "standalone_node"] = "append_protocol"
    systemContent: str
    userTemplate: Optional[str] = None


class ModTrialPackInput(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    name: str
    summary: str = ""
    overrides: list[ModTrialOverrideInput] = Field(default_factory=list)


class ModSandboxAbTrialRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    pack: ModTrialPackInput
    novel_id: str = ""
    scenario: str = ""
    target_words: int = 300


class ModSandboxAbTrialResult(BaseModel):
    pack_id: str
    target_node_key: str
    mounted_node_keys: list[str]
    novel_id: str = ""
    novel_title: str = ""
    scenario_used: str
    target_words: int
    baseline_text: str
    mod_text: str
    baseline_char_count: int
    mod_char_count: int
    model: str
    latency_ms: int


def _get_seed_prompts_map() -> Dict[str, Dict[str, Any]]:
    """Load and cache built-in prompt seeds purely in memory (never writes to SQLite)."""
    global _SEED_PROMPTS_BY_KEY
    if _SEED_PROMPTS_BY_KEY is not None:
        return _SEED_PROMPTS_BY_KEY
    with _SEED_CACHE_LOCK:
        if _SEED_PROMPTS_BY_KEY is None:
            _, rows = load_seed_bundle()
            _SEED_PROMPTS_BY_KEY = {
                str(row["id"]).strip(): row
                for row in rows
                if isinstance(row, dict) and str(row.get("id") or "").strip()
            }
    return _SEED_PROMPTS_BY_KEY


def _strip_well_formed_mod_blocks(text: str, *, allow_replaced: bool = True) -> str:
    """Iteratively remove only canonical innermost (START(id), END(id)) blocks."""
    cleaned = text
    for _ in range(64):
        tokens = list(_MOD_DELIMITER_TOKEN_RE.finditer(cleaned))
        if len(tokens) < 2:
            break
        removed_any = False
        rebuilt: List[str] = []
        cursor = 0
        idx = 0
        while idx < len(tokens):
            tok = tokens[idx]
            kind = tok.group("kind")
            is_open = kind.startswith("START") and (
                allow_replaced or kind != "START:replaced"
            )
            if is_open and idx + 1 < len(tokens):
                nxt = tokens[idx + 1]
                if (
                    nxt.group("kind") == "END"
                    and tok.group("mod_id") == nxt.group("mod_id")
                ):
                    rebuilt.append(cleaned[cursor : tok.start()])
                    cursor = nxt.end()
                    if cursor < len(cleaned) and cleaned[cursor] == "\r":
                        cursor += 1
                    if cursor < len(cleaned) and cleaned[cursor] == "\n":
                        cursor += 1
                    idx += 2
                    removed_any = True
                    continue
            idx += 1
        if not removed_any:
            break
        rebuilt.append(cleaned[cursor:])
        cleaned = "".join(rebuilt)
    return cleaned


def _strip_dangling_mod_comments(text: str) -> str:
    """Single-pass O(N) forward stripper for `<!-- [PlotPilot-Mod:...] -->` comments without suffix rescanning."""
    if "<!--" not in text:
        return text
    out: List[str] = []
    idx = 0
    length = len(text)
    while idx < length:
        comment_start = text.find("<!--", idx)
        if comment_start == -1:
            out.append(text[idx:])
            break
        out.append(text[idx:comment_start])
        p = comment_start + 4
        while p < length and text[p].isspace():
            p += 1
        if text[p : p + 15].lower() != "[plotpilot-mod:":
            out.append("<!--")
            idx = comment_start + 4
            continue
        rb = text.find("]", p + 15)
        if rb == -1:
            # No closing bracket exists anywhere in the suffix; no comment can close.
            out.append(text[comment_start:])
            break
        q = rb + 1
        while q < length and text[q].isspace():
            q += 1
        if text.startswith("-->", q):
            end_pos = q + 3
            if end_pos < length and text[end_pos] == "\r":
                end_pos += 1
            if end_pos < length and text[end_pos] == "\n":
                end_pos += 1
            idx = end_pos
            continue
        # No `]` existed in [comment_start, rb), so every opener before `rb` shares this failed `rb`.
        out.append(text[comment_start : rb + 1])
        idx = rb + 1
    return "".join(out)


def strip_all_mod_blocks(text: str) -> str:
    """Strip all canonical PlotPilot-Mod protocol blocks and delimiter comments in memory.

    Uses canonical delimiter-aware adjacent pairing so a dangling or malformed START marker
    never pairs across intervening START/END delimiters to swallow clean baseline prose.
    """
    if not text:
        return ""
    cleaned = _strip_well_formed_mod_blocks(text, allow_replaced=True)
    cleaned = _strip_dangling_mod_comments(cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def _try_extract_well_formed_baseline(text: str) -> Optional[str]:
    """Return clean unmounted baseline if and only if:
    1. Every PlotPilot-Mod: occurrence in text belongs to a canonical _MOD_DELIMITER_TOKEN_RE token
       (rejecting malformed opening kinds like START_BROKEN, trailing-space START:replaced ,
       case-mismatched delimiters, or malformed markers nested inside outer blocks);
    2. No token is START:replaced;
    3. Every canonical START/END token pairs cleanly with zero residual PlotPilot-Mod: markers.
    """
    if not text or not text.strip():
        return None
    raw_marker_count = len(RESERVED_MOD_MARKER_RE.findall(text))
    if raw_marker_count > 0:
        canonical_tokens = list(_MOD_DELIMITER_TOKEN_RE.finditer(text))
        if len(canonical_tokens) != raw_marker_count:
            return None
        if any(tok.group("kind") == "START:replaced" for tok in canonical_tokens):
            return None
    stripped = _strip_well_formed_mod_blocks(text, allow_replaced=False)
    if RESERVED_MOD_MARKER_RE.search(stripped):
        return None
    normalized = re.sub(r"\n{3,}", "\n\n", stripped).strip()
    return normalized or None


def validate_trial_request(request: ModSandboxAbTrialRequest) -> ModSandboxAbTrialRequest:
    """Validate and normalize A/B trial request inputs strictly."""
    if request.pack is None:
        raise ModSandboxValidationError("缺少模组包定义（pack）")

    raw_pack_id = request.pack.id or ""
    if ASCII_CONTROL_CHAR_RE.search(raw_pack_id):
        raise ModSandboxValidationError("模组标识（pack.id）包含非法控制字符")
    pack_id = raw_pack_id.strip()
    if (
        not SAFE_MOD_ID_RE.fullmatch(pack_id)
        or ".." in pack_id
    ):
        raise ModSandboxValidationError(
            f"模组标识（pack.id: {request.pack.id!r}）格式非法：禁止 '..'，仅允许字母、数字、点、下划线与连字符（1-96 字符）"
        )

    raw_pack_name = request.pack.name or ""
    if ASCII_CONTROL_CHAR_RE.search(raw_pack_name):
        raise ModSandboxValidationError("模组名称（pack.name）包含非法控制字符")
    if RESERVED_MOD_MARKER_RE.search(raw_pack_name):
        raise ModSandboxValidationError("模组名称（pack.name）包含受保护协议标记（PlotPilot-Mod:），已拒绝")
    pack_name = raw_pack_name.strip()
    if not pack_name or len(pack_name) > 120:
        raise ModSandboxValidationError("模组名称（pack.name）不能为空且不得超过 120 字符")

    raw_summary = request.pack.summary or ""
    if DISALLOWED_MULTILINE_CONTROL_RE.search(raw_summary):
        raise ModSandboxValidationError("模组摘要（pack.summary）包含非法控制字符")
    if RESERVED_MOD_MARKER_RE.search(raw_summary):
        raise ModSandboxValidationError("模组摘要（pack.summary）包含受保护协议标记（PlotPilot-Mod:），已拒绝")
    clean_summary = raw_summary.strip()
    if len(clean_summary) > 4000:
        raise ModSandboxValidationError("模组摘要（pack.summary）不得超过 4000 字符")

    overrides = request.pack.overrides or []
    if not (1 <= len(overrides) <= 24):
        raise ModSandboxValidationError("模组节点规则（pack.overrides）数量必须在 1 到 24 之间")

    seen_keys: set[str] = set()
    normalized_overrides: List[ModTrialOverrideInput] = []
    for ov in overrides:
        raw_node_key = ov.nodeKey or ""
        if ASCII_CONTROL_CHAR_RE.search(raw_node_key):
            raise ModSandboxValidationError("节点键（nodeKey）包含非法控制字符")
        node_key = raw_node_key.strip()
        if not SAFE_NODE_KEY_RE.fullmatch(node_key) or ".." in node_key:
            raise ModSandboxValidationError(
                f"节点键（nodeKey: {ov.nodeKey!r}）格式非法：禁止包含 '..' 或受限字符"
            )
        if node_key in seen_keys:
            raise ModSandboxValidationError(f"模组包包含重复的节点键：{node_key}")
        seen_keys.add(node_key)

        raw_node_label = ov.nodeLabel or ""
        if ASCII_CONTROL_CHAR_RE.search(raw_node_label):
            raise ModSandboxValidationError(f"节点「{node_key}」的 nodeLabel 包含非法控制字符")
        if RESERVED_MOD_MARKER_RE.search(raw_node_label):
            raise ModSandboxValidationError(
                f"节点「{node_key}」的 nodeLabel 包含受保护协议标记（PlotPilot-Mod:），已拒绝"
            )
        clean_node_label = raw_node_label.strip()
        if len(clean_node_label) > 120:
            raise ModSandboxValidationError(f"节点「{node_key}」的 nodeLabel 不得超过 120 字符")

        raw_system = ov.systemContent or ""
        if DISALLOWED_MULTILINE_CONTROL_RE.search(raw_system):
            raise ModSandboxValidationError(
                f"节点「{node_key}」的 systemContent 包含非法控制字符"
            )
        sys_trimmed = raw_system.strip()
        if not sys_trimmed or len(raw_system) > 65536 or len(sys_trimmed) > 65536:
            raise ModSandboxValidationError(
                f"节点「{node_key}」的 systemContent 不能为空且不得超过 65536 字符"
            )
        if RESERVED_MOD_MARKER_RE.search(raw_system):
            raise ModSandboxValidationError(
                f"节点「{node_key}」的 systemContent 包含受保护协议标记（PlotPilot-Mod:），已拒绝"
            )

        user_tpl = ov.userTemplate
        if user_tpl is not None:
            if DISALLOWED_MULTILINE_CONTROL_RE.search(user_tpl):
                raise ModSandboxValidationError(
                    f"节点「{node_key}」的 userTemplate 包含非法控制字符"
                )
            if len(user_tpl) > 65536:
                raise ModSandboxValidationError(
                    f"节点「{node_key}」的 userTemplate 不得超过 65536 字符"
                )
            if RESERVED_MOD_MARKER_RE.search(user_tpl):
                raise ModSandboxValidationError(
                    f"节点「{node_key}」的 userTemplate 包含受保护协议标记（PlotPilot-Mod:），已拒绝"
                )

        normalized_overrides.append(
            ModTrialOverrideInput(
                nodeKey=node_key,
                nodeLabel=clean_node_label,
                mode=ov.mode,
                systemContent=sys_trimmed,
                userTemplate=user_tpl,
            )
        )

    target_words = request.target_words
    if isinstance(target_words, bool) or not isinstance(target_words, int) or not (120 <= target_words <= 600):
        raise ModSandboxValidationError("试写目标字数（target_words）必须为 120 到 600 之间的整数")

    raw_novel_id = request.novel_id or ""
    if ASCII_CONTROL_CHAR_RE.search(raw_novel_id):
        raise ModSandboxValidationError("书目 ID（novel_id）包含非法控制字符")
    novel_id = raw_novel_id.strip()
    if len(novel_id) > 128:
        raise ModSandboxValidationError("书目 ID（novel_id）不得超过 128 字符")

    raw_scenario = request.scenario or ""
    if DISALLOWED_MULTILINE_CONTROL_RE.search(raw_scenario):
        raise ModSandboxValidationError("试写测试命题（scenario）包含非法控制字符")
    if RESERVED_MOD_MARKER_RE.search(raw_scenario):
        raise ModSandboxValidationError("试写测试命题（scenario）包含受保护协议标记（PlotPilot-Mod:），已拒绝")
    scenario = raw_scenario.strip()
    if len(scenario) > 4000:
        raise ModSandboxValidationError("试写测试命题（scenario）不得超过 4000 字符")

    return ModSandboxAbTrialRequest(
        pack=ModTrialPackInput(
            id=pack_id,
            name=pack_name,
            summary=clean_summary,
            overrides=normalized_overrides,
        ),
        novel_id=novel_id,
        scenario=scenario,
        target_words=target_words,
    )


def select_primary_override(overrides: List[ModTrialOverrideInput]) -> ModTrialOverrideInput:
    """Select the primary override for A/B trial comparison by priority order."""
    by_key = {ov.nodeKey: ov for ov in overrides}
    for preferred in ("chapter-generation-main", "scene-generation", "dialogue-generation"):
        if preferred in by_key:
            return by_key[preferred]
    for ov in overrides:
        low = ov.nodeKey.lower()
        if "generation" in low or "chapter" in low or "opening" in low:
            return ov
    return overrides[0]


class ModSandboxTrialService:
    """Side-effect-free 300-word A/B Sandbox Trial service."""

    def __init__(
        self,
        *,
        db_provider: Optional[Callable[[], Any]] = None,
        control_service: Optional[LLMControlService] = None,
        llm_service: Optional[LLMService] = None,
    ) -> None:
        self._db_provider = db_provider or get_database
        self._control_service = control_service
        self._llm_service = llm_service

    def _get_control_service(self) -> LLMControlService:
        if self._control_service is None:
            self._control_service = LLMControlService(db_provider=self._db_provider)
        return self._control_service

    async def _resolve_main_profile_readonly(self, db: Any) -> Optional[ Any ]:
        """Resolve effective 'main' LLM profile strictly without SQLite DDL or default seeding."""
        control_service = self._get_control_service()
        if isinstance(control_service, LLMControlService):
            target_db = db if db is not None else control_service._db_provider()
            if target_db is None:
                return None
            try:
                profiles, _, meta_map = control_service._read_snapshot_from_adapter(target_db)
            except sqlite3.OperationalError:
                return None
            if not profiles:
                return None
            cfg = control_service._assemble_config_from_snapshot(profiles, meta_map)
            return await control_service.resolve_role_profile_async("main", config=cfg)

        if hasattr(control_service, "resolve_role_profile_async"):
            return await control_service.resolve_role_profile_async("main")
        return control_service.resolve_role_profile("main")

    @staticmethod
    async def _close_ephemeral_provider(provider: Optional[LLMService]) -> None:
        if provider is None:
            return
        try:
            if hasattr(provider, "aclose"):
                await provider.aclose()
                return
            for sync_attr in ("_http_client_sync",):
                sync_client = getattr(provider, sync_attr, None)
                if (
                    sync_client is not None
                    and hasattr(sync_client, "is_closed")
                    and not sync_client.is_closed
                ):
                    sync_client.close()
            for async_attr in ("_http_client_async", "_http_client", "_stream_http_client"):
                async_client = getattr(provider, async_attr, None)
                if async_client is not None and hasattr(async_client, "aclose"):
                    await async_client.aclose()
        except Exception:
            pass

    def validate_trial_request(self, request: ModSandboxAbTrialRequest) -> ModSandboxAbTrialRequest:
        return validate_trial_request(request)

    def _node_exists_in_db_or_seed(self, db: Any, node_key: str) -> bool:
        seed_map = _get_seed_prompts_map()
        if node_key in seed_map:
            return True
        if db is None:
            return False
        try:
            row = db.fetch_one(
                "SELECT id FROM prompt_nodes WHERE node_key = ? LIMIT 1",
                (node_key,),
            )
            return row is not None
        except sqlite3.OperationalError:
            return False

    def _load_clean_baseline_system(self, db: Any, anchor_key: str) -> str:
        """Recover the clean unmounted baseline system prompt purely via read-only SELECT or seed cache.

        If the active version contains :START:replaced] (case-insensitive) or malformed/dangling
        PlotPilot-Mod delimiters that prevent provably clean extraction, walks backward through
        prompt_versions and falls back to the in-memory seed bundle.
        """
        seed_map = _get_seed_prompts_map()
        recovered: Optional[str] = None

        if db is not None:
            try:
                row = db.fetch_one(
                    """
                    SELECT n.id, n.active_version_id, v.system_prompt, v.user_template
                    FROM prompt_nodes n
                    LEFT JOIN prompt_versions v ON v.id = n.active_version_id
                    WHERE n.node_key = ?
                    """,
                    (anchor_key,),
                )
            except sqlite3.OperationalError:
                row = None

            if row is not None:
                active_system = str(row.get("system_prompt") or "")
                recovered = _try_extract_well_formed_baseline(active_system)
                if recovered is None:
                    node_id = row.get("id")
                    if node_id:
                        try:
                            versions = db.fetch_all(
                                """
                                SELECT system_prompt, user_template
                                FROM prompt_versions
                                WHERE node_id = ?
                                ORDER BY version_number DESC
                                """,
                                (node_id,),
                            )
                        except sqlite3.OperationalError:
                            versions = []
                        for ver in versions:
                            cand = str(ver.get("system_prompt") or "")
                            recovered = _try_extract_well_formed_baseline(cand)
                            if recovered is not None:
                                break

        if recovered is None:
            seed_row = seed_map.get(anchor_key)
            if seed_row is not None:
                recovered = strip_all_mod_blocks(str(seed_row.get("system") or "")) or None

        if not recovered:
            seed_fallback = seed_map.get("chapter-generation-main")
            if seed_fallback is not None:
                recovered = strip_all_mod_blocks(str(seed_fallback.get("system") or "")) or None
        return recovered or _FALLBACK_CHAPTER_SYSTEM

    def _load_novel_context_readonly(
        self, db: Any, novel_id: str
    ) -> Tuple[str, str, List[str]]:
        """Read-only lookup for novel title, premise, and up to 3 character summaries."""
        if not novel_id:
            return "", "", []

        try:
            novel_row = db.fetch_one(
                "SELECT id, title, premise FROM novels WHERE id = ?",
                (novel_id,),
            )
        except sqlite3.OperationalError as exc:
            raise ModSandboxValidationError(f"未找到指定书目：{novel_id}") from exc

        if novel_row is None:
            raise ModSandboxValidationError(f"未找到指定书目：{novel_id}")

        novel_title = str(novel_row.get("title") or "").strip()
        novel_premise = str(novel_row.get("premise") or "").strip()

        char_summaries: List[str] = []
        for char_sql in (
            "SELECT name, role, personality FROM unified_characters WHERE novel_id = ? LIMIT 3",
            "SELECT name, role, personality FROM bible_characters WHERE novel_id = ? LIMIT 3",
        ):
            try:
                char_rows = db.fetch_all(char_sql, (novel_id,))
                for cr in char_rows or []:
                    cname = str(cr.get("name") or "").strip()
                    if not cname:
                        continue
                    crole = str(cr.get("role") or "").strip()
                    cpers = str(cr.get("personality") or "").strip()
                    parts = [p for p in (crole, cpers) if p]
                    char_summaries.append(f"{cname}（{'；'.join(parts)}）" if parts else cname)
                if char_summaries:
                    break
            except Exception:
                continue

        return novel_title, novel_premise, char_summaries

    def _assemble_mod_system(
        self,
        *,
        pack_id: str,
        primary: ModTrialOverrideInput,
        overrides: List[ModTrialOverrideInput],
        baseline_system: str,
    ) -> Tuple[str, List[str]]:
        """Assemble Treatment system prompt and mounted node keys purely in memory."""
        if primary.mode == "append_protocol":
            base_trimmed = baseline_system.rstrip()
            block = (
                f"<!-- [PlotPilot-Mod:{pack_id}:START:appended] -->\n"
                f"{primary.systemContent.strip()}\n"
                f"<!-- [PlotPilot-Mod:{pack_id}:END] -->"
            )
            mod_system = f"{base_trimmed}\n\n{block}" if base_trimmed else block
        else:
            # replace_system or standalone_node
            mod_system = primary.systemContent.strip()

        mounted_node_keys: List[str] = [primary.nodeKey]
        extra_overrides = [ov for ov in overrides if ov.nodeKey != primary.nodeKey][:3]
        for ov in extra_overrides:
            label = ov.nodeLabel.strip() or ov.nodeKey
            mod_system = (
                f"{mod_system}\n\n"
                f"[同包协同规则 · {label}]\n"
                f"{ov.systemContent.strip()}"
            )
            mounted_node_keys.append(ov.nodeKey)

        return mod_system, mounted_node_keys

    def _build_prompts(
        self,
        *,
        baseline_system: str,
        mod_system: str,
        baseline_anchor_key: str,
        primary_node_key: str,
        primary_user_template: Optional[str],
        novel_title: str,
        novel_premise: str,
        char_summaries: List[str],
        scenario_used: str,
        target_words: int,
    ) -> Tuple[Prompt, Prompt]:
        output_constraint = (
            f"\n\n[沙盒 A/B 试写输出约束]\n"
            f"请直接围绕下方测试命题与书目上下文，创作一段约 {target_words} 字（中文字符）的生动小说正文片段。"
            "仅输出小说正文，严禁输出 JSON、Markdown 标题、分点大纲或任何元解释。"
        )
        baseline_prompt_system = f"{baseline_system.rstrip()}{output_constraint}"
        mod_prompt_system = f"{mod_system.rstrip()}{output_constraint}"

        context_lines: List[str] = []
        if novel_title:
            context_lines.append(f"书名：《{novel_title}》")
        if novel_premise:
            context_lines.append(f"核心设定/梗概：{novel_premise}")
        if char_summaries:
            context_lines.append(f"主要人物：{'；'.join(char_summaries)}")

        context_text = "\n".join(context_lines)
        context_section = (
            f"[书目设定上下文]\n{context_text}\n\n"
            if context_text
            else ""
        )
        output_tail = (
            f"[输出要求]\n"
            f"请直接写出一整段约 {target_words} 字（~{target_words} 字）的连续叙事小说正文，生动演绎上述命题与设定。"
            "只输出纯小说正文，不要输出 JSON、Markdown 标题或任何说明文字。"
        )
        baseline_user_message = (
            f"{context_section}"
            f"[试写测试命题]\n{scenario_used}\n\n"
            f"{output_tail}"
        )

        custom_utpl = (primary_user_template or "").strip()
        if custom_utpl:
            rendered_utpl = (
                custom_utpl.replace("{context}", context_text or "（未绑定特定书目设定）")
                .replace("{outline}", scenario_used)
                .replace("{scenario}", scenario_used)
            )
            mod_user_message = (
                f"{baseline_user_message}\n\n"
                f"[模组用户侧模板补充指令]\n{rendered_utpl}"
            )
        else:
            mod_user_message = baseline_user_message

        baseline_prompt = Prompt(
            system=baseline_prompt_system,
            user=baseline_user_message,
            node_key=baseline_anchor_key,
        )
        mod_prompt = Prompt(
            system=mod_prompt_system,
            user=mod_user_message,
            node_key=primary_node_key,
        )
        return baseline_prompt, mod_prompt

    async def run_ab_trial(
        self, request: ModSandboxAbTrialRequest
    ) -> ModSandboxAbTrialResult:
        """Validate inputs, assemble Control & Treatment prompts in memory, and run concurrent LLM A/B trial."""
        cleaned = self.validate_trial_request(request)
        pack = cleaned.pack

        db = self._db_provider()
        primary = select_primary_override(pack.overrides)
        if primary.mode == "standalone_node" and not self._node_exists_in_db_or_seed(
            db, primary.nodeKey
        ):
            baseline_anchor_key = "chapter-generation-main"
        else:
            baseline_anchor_key = primary.nodeKey

        baseline_system = self._load_clean_baseline_system(db, baseline_anchor_key)
        novel_title, novel_premise, char_summaries = self._load_novel_context_readonly(
            db, cleaned.novel_id
        )

        scenario_used = (
            cleaned.scenario
            or novel_premise
            or pack.summary
            or pack.name
        ).strip()
        if not scenario_used:
            raise ModSandboxValidationError("请提供试写测试命题或选择已有设定书目")

        resolved_main = await self._resolve_main_profile_readonly(db)
        if (
            resolved_main is None
            or not (resolved_main.api_key or "").strip()
            or not (resolved_main.model or "").strip()
        ):
            raise LLMNotConfiguredError(
                "当前未配置可用的主力（main）LLM 模型或 API Key，请先在「LLM 控制」中补全并激活后再试写"
            )

        mod_system, mounted_node_keys = self._assemble_mod_system(
            pack_id=pack.id,
            primary=primary,
            overrides=pack.overrides,
            baseline_system=baseline_system,
        )

        baseline_prompt, mod_prompt = self._build_prompts(
            baseline_system=baseline_system,
            mod_system=mod_system,
            baseline_anchor_key=baseline_anchor_key,
            primary_node_key=primary.nodeKey,
            primary_user_template=primary.userTemplate,
            novel_title=novel_title,
            novel_premise=novel_premise,
            char_summaries=char_summaries,
            scenario_used=scenario_used,
            target_words=cleaned.target_words,
        )

        gen_cfg = GenerationConfig(
            model=resolved_main.model,
            temperature=resolved_main.temperature,
            max_tokens=min(max(cleaned.target_words * 4, 900), 2048),
            role_hint="main",
        )

        ephemeral_provider: Optional[LLMService] = None
        if self._llm_service is not None:
            llm_runner = self._llm_service
        else:
            from infrastructure.ai.provider_factory import LLMProviderFactory

            ephemeral_provider = LLMProviderFactory(
                self._get_control_service()
            ).create_from_resolved_profile(resolved_main)
            llm_runner = ephemeral_provider

        started = time.perf_counter()
        baseline_task = asyncio.create_task(llm_runner.generate(baseline_prompt, gen_cfg))
        mod_task = asyncio.create_task(llm_runner.generate(mod_prompt, gen_cfg))

        async def _drain_children_and_close_provider() -> None:
            try:
                pending_tasks = [t for t in (baseline_task, mod_task) if not t.done()]
                for pending in pending_tasks:
                    pending.cancel()
                if pending_tasks:
                    await asyncio.gather(*pending_tasks, return_exceptions=True)
                for finished in (baseline_task, mod_task):
                    if finished.done() and not finished.cancelled():
                        _ = finished.exception()
            finally:
                if ephemeral_provider is not None:
                    await self._close_ephemeral_provider(ephemeral_provider)

        try:
            baseline_res, mod_res = await asyncio.gather(baseline_task, mod_task)
        finally:
            cleanup_task = asyncio.create_task(_drain_children_and_close_provider())
            await asyncio.shield(cleanup_task)

        latency_ms = max(0, int((time.perf_counter() - started) * 1000))

        baseline_text = (getattr(baseline_res, "content", "") or "").strip()
        mod_text = (getattr(mod_res, "content", "") or "").strip()
        if not baseline_text or not mod_text:
            raise RuntimeError("上游模型返回了空正文，请核对模型名、配额状态或网关连接")

        return ModSandboxAbTrialResult(
            pack_id=pack.id,
            target_node_key=primary.nodeKey,
            mounted_node_keys=mounted_node_keys,
            novel_id=cleaned.novel_id,
            novel_title=novel_title,
            scenario_used=scenario_used,
            target_words=cleaned.target_words,
            baseline_text=baseline_text,
            mod_text=mod_text,
            baseline_char_count=len(re.sub(r"\s+", "", baseline_text)),
            mod_char_count=len(re.sub(r"\s+", "", mod_text)),
            model=resolved_main.model,
            latency_ms=latency_ms,
        )
