"""EmbeddingConfigService — 嵌入模型配置管理服务（数据库驱动）。

将嵌入模型配置持久化到 SQLite embedding_config 表，
替代之前硬编码默认值的临时实现。
"""
from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class EmbeddingConfigModel(BaseModel):
    """嵌入配置数据模型。"""
    model_config = {"protected_namespaces": ()}
    id: str = "default"
    mode: str = "openai"  # local | openai（默认云端，轻量）
    api_key: str = ""
    base_url: str = ""
    model: str = "text-embedding-3-small"
    use_gpu: bool = True
    model_path: str = "BAAI/bge-small-zh-v1.5"
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "mode": self.mode,
            "api_key": self.api_key,
            "base_url": self.base_url,
            "model": self.model,
            "use_gpu": self.use_gpu,
            "model_path": self.model_path,
        }

    def to_api_dict(self) -> Dict[str, Any]:
        payload = self.to_dict()
        payload["created_at"] = self.created_at
        payload["updated_at"] = self.updated_at
        return payload

    @classmethod
    def from_row(cls, row: Dict[str, Any]) -> "EmbeddingConfigModel":
        return cls(
            id=row["id"],
            mode=row.get("mode", "openai"),
            api_key=row.get("api_key", ""),
            base_url=row.get("base_url", ""),
            model=row.get("model", "text-embedding-3-small"),
            use_gpu=bool(row.get("use_gpu", 1)),
            model_path=row.get("model_path", "BAAI/bge-small-zh-v1.5"),
            created_at=row.get("created_at", ""),
            updated_at=row.get("updated_at", ""),
        )


class EmbeddingConfigService:
    """嵌入模型配置服务 — 数据库 CRUD。

    设计决策：
    - 单行配置（id='default'），全局唯一
    - 首次读取时自动插入默认行
    - 所有写操作更新 updated_at
    """

    _DEFAULTS = {
        "id": "default",
        "mode": "openai",
        "api_key": "",
        "base_url": "",
        "model": "text-embedding-3-small",
        "use_gpu": 1,
        "model_path": "BAAI/bge-small-zh-v1.5",
    }

    def __init__(self, db_connection=None):
        self._db = db_connection

    def _get_db(self):
        """获取数据库连接（延迟导入避免循环依赖）。"""
        if self._db is not None:
            return self._db
        try:
            from interfaces.api.dependencies import get_db as _get_global_db
            return _get_global_db()
        except Exception:
            pass
        from infrastructure.persistence.database.connection import DatabaseConnection
        from application.paths import DATA_DIR
        db_path = str(DATA_DIR / "aitext.db")
        return DatabaseConnection(db_path)

    def _default_values(self) -> Dict[str, Any]:
        """优先从环境变量读取默认值，避免首次初始化覆盖本地开发配置。"""
        return {
            "id": "default",
            "mode": (os.getenv("EMBEDDING_SERVICE", self._DEFAULTS["mode"]) or self._DEFAULTS["mode"]).lower(),
            "api_key": os.getenv("EMBEDDING_API_KEY", self._DEFAULTS["api_key"]),
            "base_url": os.getenv("EMBEDDING_BASE_URL", self._DEFAULTS["base_url"]),
            "model": os.getenv("EMBEDDING_MODEL", self._DEFAULTS["model"]),
            "use_gpu": 1 if os.getenv("EMBEDDING_USE_GPU", "true").lower() == "true" else 0,
            "model_path": os.getenv("EMBEDDING_MODEL_PATH", self._DEFAULTS["model_path"]),
        }

    def _commit_db(self, db) -> None:
        """兼容 DatabaseConnection 与 sqlite3.Connection 的提交方式。"""
        if hasattr(db, "commit"):
            db.commit()
            return
        if hasattr(db, "get_connection"):
            db.get_connection().commit()
            return
        raise AttributeError("Database object does not support commit")

    def _ensure_row(self) -> None:
        """确保存在默认配置行（幂等）。"""
        db = self._get_db()
        row = db.execute(
            "SELECT id FROM embedding_config WHERE id = ? LIMIT 1",
            ("default",),
        ).fetchone()
        if row:
            return
        now = datetime.now().isoformat()
        defaults = self._default_values()
        db.execute("""
            INSERT OR IGNORE INTO embedding_config
            (id, mode, api_key, base_url, model, use_gpu, model_path, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            defaults["id"],
            defaults["mode"],
            defaults["api_key"],
            defaults["base_url"],
            defaults["model"],
            defaults["use_gpu"],
            defaults["model_path"],
            now,
            now,
        ))
        self._commit_db(db)
        logger.info("EmbeddingConfigService: 已初始化默认嵌入配置")

    def get_config(self) -> EmbeddingConfigModel:
        """获取当前嵌入配置。"""
        self._ensure_row()
        db = self._get_db()
        row = db.execute(
            "SELECT * FROM embedding_config WHERE id = ? LIMIT 1",
            ("default",),
        ).fetchone()
        if not row:
            # 兜底：返回默认模型
            return EmbeddingConfigModel()
        return EmbeddingConfigModel.from_row(dict(row))

    def update_config(self, **kwargs) -> EmbeddingConfigModel:
        """更新嵌入配置。

        Args:
            **kwargs: 要更新的字段（mode, api_key, base_url, model, use_gpu, model_path）

        Returns:
            更新后的配置
        """
        self._ensure_row()
        db = self._get_db()

        # 构建动态 UPDATE
        allowed = {"mode", "api_key", "base_url", "model", "use_gpu", "model_path"}
        set_clauses = []
        params: list = []
        for key, value in kwargs.items():
            if key not in allowed:
                continue
            if key == "use_gpu":
                value = 1 if value else 0
            set_clauses.append(f"{key} = ?")
            params.append(value)

        if not set_clauses:
            return self.get_config()

        now = datetime.now().isoformat()
        set_clauses.append("updated_at = ?")
        params.append(now)
        params.append("default")  # WHERE id = ?

        sql = f"UPDATE embedding_config SET {', '.join(set_clauses)} WHERE id = ?"
        db.execute(sql, params)
        self._commit_db(db)

        logger.info("EmbeddingConfigService: 配置已更新，字段: %s", list(kwargs.keys()))
        return self.get_config()

    def to_api_dict(self) -> Dict[str, Any]:
        """返回 API 友好的字典格式。"""
        cfg = self.get_config()
        return cfg.to_api_dict()


# ── 单例 ──────────────────────────────────────────────

_service_instance: Optional[EmbeddingConfigService] = None


def get_embedding_config_service() -> EmbeddingConfigService:
    """获取全局 EmbeddingConfigService 单例。"""
    global _service_instance
    if _service_instance is None:
        _service_instance = EmbeddingConfigService()
    return _service_instance
