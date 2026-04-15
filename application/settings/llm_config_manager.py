"""LLM 配置管理器 — 多配置存储 + 热重载"""
from __future__ import annotations

import json
import logging
import os
import threading
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Literal, Optional

logger = logging.getLogger(__name__)

ProviderType = Literal["openai", "anthropic"]
EmbeddingMode = Literal["local", "openai"]


@dataclass
class LLMConfigProfile:
    id: str
    name: str
    provider: ProviderType
    api_key: str
    base_url: str = ""
    model: str = ""
    system_model: str = ""
    writing_model: str = ""
    created_at: str = ""
    updated_at: str = ""


@dataclass
class EmbeddingConfig:
    mode: EmbeddingMode = "local"
    api_key: str = ""
    base_url: str = ""
    model: str = "text-embedding-3-small"
    use_gpu: bool = True
    model_path: str = "BAAI/bge-small-zh-v1.5"


@dataclass
class LLMConfigStore:
    active_id: Optional[str] = None
    configs: List[LLMConfigProfile] = field(default_factory=list)
    embedding: EmbeddingConfig = field(default_factory=EmbeddingConfig)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class LLMConfigManager:
    def __init__(self, config_path: Path):
        self._path = config_path
        self._lock = threading.Lock()

    # ── persistence ──────────────────────────────────────────

    def _load(self) -> LLMConfigStore:
        if not self._path.is_file():
            return LLMConfigStore()
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
            configs = [LLMConfigProfile(**c) for c in raw.get("configs", [])]
            emb_raw = raw.get("embedding")
            embedding = EmbeddingConfig(**emb_raw) if emb_raw else EmbeddingConfig()
            return LLMConfigStore(active_id=raw.get("active_id"), configs=configs, embedding=embedding)
        except Exception as exc:
            logger.warning("Failed to load LLM configs: %s", exc)
            return LLMConfigStore()

    def _save(self, store: LLMConfigStore) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(".tmp")
        tmp.write_text(
            json.dumps(
                {
                    "active_id": store.active_id,
                    "configs": [asdict(c) for c in store.configs],
                    "embedding": asdict(store.embedding),
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        tmp.replace(self._path)

    # ── CRUD ─────────────────────────────────────────────────

    def list_configs(self) -> dict:
        with self._lock:
            store = self._load()
            return {"active_id": store.active_id, "configs": [asdict(c) for c in store.configs]}

    def create_config(self, data: dict) -> dict:
        with self._lock:
            store = self._load()
            now = _now_iso()
            profile = LLMConfigProfile(
                id=str(uuid.uuid4()),
                name=data["name"],
                provider=data["provider"],
                api_key=data["api_key"],
                base_url=data.get("base_url", ""),
                model=data.get("model", ""),
                system_model=data.get("system_model", ""),
                writing_model=data.get("writing_model", ""),
                created_at=now,
                updated_at=now,
            )
            store.configs.append(profile)
            became_active = store.active_id is None
            if became_active:
                store.active_id = profile.id
                self._save(store)
                self._apply_to_env(profile)
            else:
                self._save(store)
        if became_active:
            self._invalidate_caches()
        return asdict(profile)

    def update_config(self, config_id: str, data: dict) -> dict:
        with self._lock:
            store = self._load()
            for cfg in store.configs:
                if cfg.id == config_id:
                    for k in ("name", "provider", "api_key", "base_url", "model", "system_model", "writing_model"):
                        if k in data:
                            setattr(cfg, k, data[k])
                    cfg.updated_at = _now_iso()
                    self._save(store)
                    is_active = store.active_id == config_id
                    if is_active:
                        self._apply_to_env(cfg)
                    result = asdict(cfg)
                    break
            else:
                raise KeyError(f"Config {config_id} not found")
        if is_active:
            self._invalidate_caches()
        return result

    def delete_config(self, config_id: str) -> None:
        with self._lock:
            store = self._load()
            store.configs = [c for c in store.configs if c.id != config_id]
            if store.active_id == config_id:
                store.active_id = store.configs[0].id if store.configs else None
            self._save(store)

    def set_active(self, config_id: str) -> None:
        with self._lock:
            store = self._load()
            profile = next((c for c in store.configs if c.id == config_id), None)
            if profile is None:
                raise KeyError(f"Config {config_id} not found")
            store.active_id = config_id
            self._save(store)
            self._apply_to_env(profile)
        self._invalidate_caches()
        logger.info("LLM config activated: %s (%s / %s)", profile.name, profile.provider, profile.model)

    # ── embedding config ────────────────────────────────────

    def get_embedding_config(self) -> dict:
        with self._lock:
            store = self._load()
            return asdict(store.embedding)

    def update_embedding_config(self, data: dict) -> dict:
        with self._lock:
            store = self._load()
            for k in ("mode", "api_key", "base_url", "model", "use_gpu", "model_path"):
                if k in data:
                    setattr(store.embedding, k, data[k])
            self._save(store)
            self._apply_embedding_to_env(store.embedding)
        self._invalidate_caches()
        return asdict(store.embedding)

    # ── hot-reload ───────────────────────────────────────────

    def _apply_embedding_to_env(self, cfg: EmbeddingConfig) -> None:
        env = os.environ
        env["EMBEDDING_SERVICE"] = cfg.mode
        env["EMBEDDING_MODEL_PATH"] = cfg.model_path
        env["EMBEDDING_USE_GPU"] = str(cfg.use_gpu).lower()

        if cfg.mode == "openai":
            if cfg.api_key:
                env["EMBEDDING_API_KEY"] = cfg.api_key
            if cfg.base_url:
                env["EMBEDDING_BASE_URL"] = cfg.base_url
            if cfg.model:
                env["EMBEDDING_MODEL"] = cfg.model
        else:
            for k in ("EMBEDDING_API_KEY", "EMBEDDING_BASE_URL", "EMBEDDING_MODEL"):
                env.pop(k, None)

        logger.info("Embedding config applied: mode=%s", cfg.mode)

    def _apply_to_env(self, profile: LLMConfigProfile) -> None:
        env = os.environ
        if profile.provider == "openai":
            env["LLM_PROVIDER"] = "openai"
            env["OPENAI_API_KEY"] = profile.api_key
            env["OPENAI_BASE_URL"] = profile.base_url
            env["ARK_API_KEY"] = profile.api_key
            env["ARK_BASE_URL"] = profile.base_url
            env["ARK_MODEL"] = profile.model
            for k in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL"):
                env.pop(k, None)
        else:
            env["LLM_PROVIDER"] = "anthropic"
            env["ANTHROPIC_API_KEY"] = profile.api_key
            env["ANTHROPIC_BASE_URL"] = profile.base_url
            for k in ("OPENAI_API_KEY", "OPENAI_BASE_URL", "ARK_API_KEY", "ARK_BASE_URL", "ARK_MODEL"):
                env.pop(k, None)

        writing = profile.writing_model or profile.model
        system = profile.system_model or profile.model
        env["WRITING_MODEL"] = writing
        env["SYSTEM_MODEL"] = system

    def _invalidate_caches(self) -> None:
        try:
            from interfaces.api.dependencies import get_background_task_service
            get_background_task_service.cache_clear()
        except Exception:
            pass
        try:
            from interfaces.main import restart_autopilot_daemon
            restart_autopilot_daemon()
        except Exception:
            pass

    def apply_active_on_startup(self) -> None:
        store = self._load()
        if store.active_id:
            profile = next((c for c in store.configs if c.id == store.active_id), None)
            if profile:
                self._apply_to_env(profile)
                logger.info("Startup: applied LLM config '%s' (%s)", profile.name, profile.provider)
        self._apply_embedding_to_env(store.embedding)
