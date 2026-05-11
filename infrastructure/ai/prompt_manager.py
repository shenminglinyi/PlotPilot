"""PromptManager — 提示词统一管理服务（数据库驱动版）。

核心设计：
- 提示词存入 SQLite（prompt_templates / prompt_nodes / prompt_versions）
- 单节点版本管理（每次编辑创建新版本，支持回滚）
- 整体模板概念（template 包含多个 node，可组合成工作流）
- 内置种子优先从 ``infrastructure/ai/prompt_packages/`` 加载（YAML 元数据 + Markdown 正文）
- 若包目录为空则回退合并旧版 ``prompts_defaults.json`` + ``prompts_*.json``（兼容未迁移工作区）
- Jinja2 兼容的变量渲染

数据模型：
  prompt_templates (1) ──→ (N) prompt_nodes (1) ──→ (N) prompt_versions
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# 旧版 JSON 种子目录（仅当 prompt_packages 为空时回退合并）
_PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"

# 分类定义（与 prompts_*.json 的 category 对应）
BUILTIN_CATEGORIES = [
    {"key": "anti-ai", "name": "🛡️ Anti-AI 防御", "icon": "🛡️",
     "description": "七层纵深防御体系：从提示词重构到Token级拦截再到章后审计，系统性消除AI味", "color": "#dc2626",
     "sort_order": 0},
    {"key": "generation", "name": "✍️ 内容生成", "icon": "✍️",
     "description": "核心创作引擎：章节正文、场景、对白、节拍流式写作。以'展示而非告知'为灵魂，拒绝AI味，追求人味叙事。", "color": "#4f46e5",
     "sort_order": 1},
    {"key": "extraction", "name": "🔍 信息提取", "icon": "🔎",
     "description": "基于文学批评视角的结构化文本逆向解析：状态提取、张力评分、叙事同步、文风指纹", "color": "#0891b2",
     "sort_order": 2},
    {"key": "review", "name": "🔬 审稿质检", "icon": "🔬",
     "description": "主编级的人物OOC预警、逻辑自洽与节奏体检。双刀策略：OOC检测+AI味检测。", "color": "#b45309",
     "sort_order": 3},
    {"key": "planning", "name": "📐 规划设计", "icon": "📋",
     "description": "好莱坞三幕剧与英雄之旅结合的宏观及微观拆解：节拍表、幕规划、主线推演、各级摘要", "color": "#6d28d9",
     "sort_order": 4},
    {"key": "world", "name": "🏰 世界设定", "icon": "🏰",
     "description": "基于5维度沉浸式框架的Bible知识库构建：完整Bible、世界观、人物群像、地点地图", "color": "#15803d",
     "sort_order": 5},
    {"key": "creative", "name": "💡 创意辅助", "icon": "💡",
     "description": "打破写作瓶颈，提供高概念推演与潜台词对话重塑、卡文诊断", "color": "#be185d",
     "sort_order": 6},
]


def _uid() -> str:
    """生成短 UUID。"""
    return uuid.uuid4().hex[:12]


class VersionInfo:
    """单个版本信息。"""

    __slots__ = ("id", "version_number", "system_prompt", "user_template",
                 "change_summary", "created_by", "created_at")

    def __init__(self, row: Optional[Dict[str, Any]] = None):
        if row:
            self.id: str = row["id"]
            self.version_number: int = row["version_number"]
            self.system_prompt: str = row["system_prompt"] or ""
            self.user_template: str = row["user_template"] or ""
            self.change_summary: str = row["change_summary"] or ""
            self.created_by: str = row["created_by"] or "system"
            self.created_at: str = row["created_at"] or ""
        else:
            self.id = ""
            self.version_number = 0
            self.system_prompt = ""
            self.user_template = ""
            self.change_summary = ""
            self.created_by = "system"
            self.created_at = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "version_number": self.version_number,
            "change_summary": self.change_summary,
            "created_by": self.created_by,
            "created_at": self.created_at,
            # 预览截断
            "system_preview": self._preview(self.system_prompt, 150),
            "user_preview": self._preview(self.user_template, 150),
        }

    def to_detail_dict(self) -> Dict[str, Any]:
        d = self.to_dict()
        d["system_prompt"] = self.system_prompt
        d["user_template"] = self.user_template
        return d

    @staticmethod
    def _preview(text: str, max_len: int) -> str:
        if not text or len(text) <= max_len:
            return text or ""
        return text[:max_len] + "... (共 {} 字)".format(len(text))


class NodeInfo:
    """提示词节点信息（含当前激活版本）。"""

    __slots__ = (
        "id", "node_key", "name", "description", "category", "source",
        "output_format", "contract_module", "contract_model",
        "tags", "variables", "system_file", "is_builtin", "sort_order",
        "template_id", "active_version_id", "version_count",
        "_active_version",
    )

    def __init__(self, row: Optional[Dict[str, Any]] = None):
        if row:
            self.id: str = row["id"]
            self.node_key: str = row["node_key"]
            self.name: str = row["name"]
            self.description: str = row["description"] or ""
            self.category: str = row["category"] or "generation"
            self.source: str = row["source"] or ""
            self.output_format: str = row["output_format"] or "text"
            self.contract_module: Optional[str] = row.get("contract_module")
            self.contract_model: Optional[str] = row.get("contract_model")
            self.tags: List[str] = self._parse_json_list(row.get("tags"))
            self.variables: List[Dict[str, Any]] = self._parse_json(
                row.get("variables"), []
            )
            self.system_file: Optional[str] = row.get("system_file")
            self.is_builtin: bool = bool(row.get("is_builtin", 0))
            self.sort_order: int = row.get("sort_order", 0)
            self.template_id: str = row["template_id"]
            self.active_version_id: Optional[str] = row.get("active_version_id")
            self.version_count: int = row.get("version_count", 0)
        else:
            self.id = _uid()
            self.node_key = ""
            self.name = ""
            self.description = ""
            self.category = "generation"
            self.source = ""
            self.output_format = "text"
            self.contract_module = None
            self.contract_model = None
            self.tags = []
            self.variables = []
            self.system_file = None
            self.is_builtin = False
            self.sort_order = 0
            self.template_id = ""
            self.active_version_id = None
            self.version_count = 0
        self._active_version: Optional[VersionInfo] = None

    @staticmethod
    def _parse_json(val: Any, default=None):
        if val is None:
            return default
        if isinstance(val, (list, dict)):
            return val
        try:
            return json.loads(val)
        except (json.JSONDecodeError, TypeError):
            return default

    @staticmethod
    def _parse_json_list(val: Any) -> List[str]:
        result = NodeInfo._parse_json(val, [])
        if isinstance(result, list):
            return [str(x) for x in result]
        return []

    def set_active_version(self, version: VersionInfo) -> None:
        self._active_version = version

    def get_active_system(self) -> str:
        if self._active_version:
            return self._active_version.system_prompt
        return ""

    def get_active_user_template(self) -> str:
        if self._active_version:
            return self._active_version.user_template
        return ""

    def to_dict(self) -> Dict[str, Any]:
        av = self._active_version
        return {
            "id": self.id,
            "node_key": self.node_key,
            "name": self.name,
            "description": self.description,
            "category": self.category,
            "source": self.source,
            "output_format": self.output_format,
            "contract_module": self.contract_module,
            "contract_model": self.contract_model,
            "tags": self.tags,
            "variables": self.variables,
            "variable_names": [v.get("name", "") for v in self.variables],
            "system_file": self.system_file,
            "is_builtin": self.is_builtin,
            "sort_order": self.sort_order,
            "template_id": self.template_id,
            "version_count": self.version_count,
            # 当前激活版本的预览
            "system_preview": av.system_prompt[:200] + "..." if av and len(av.system_prompt) > 200 else (av.system_prompt or ""),
            "user_template_preview": av.user_template[:200] + "..." if av and len(av.user_template) > 200 else (av.user_template or ""),
            "has_user_edit": av.created_by == "user" if av else False,
        }

    def to_detail_dict(self) -> Dict[str, Any]:
        d = self.to_dict()
        d["system"] = self.get_active_system()
        d["user_template"] = self.get_active_user_template()
        return d


class TemplateInfo:
    """模板包信息。"""

    __slots__ = ("id", "name", "description", "category", "version",
                 "author", "icon", "color", "is_builtin", "metadata",
                 "node_count")

    def __init__(self, row: Optional[Dict[str, Any]] = None):
        if row:
            self.id: str = row["id"]
            self.name: str = row["name"]
            self.description: str = row["description"] or ""
            self.category: str = row["category"] or "user"
            self.version: str = row["version"] or "1.0.0"
            self.author: str = row["author"] or ""
            self.icon: str = row["icon"] or "📦"
            self.color: str = row["color"] or "#6b7280"
            self.is_builtin: bool = bool(row.get("is_builtin", 0))
            self.metadata: Dict[str, Any] = {}
            raw_meta = row.get("metadata")
            if raw_meta:
                try:
                    self.metadata = json.loads(raw_meta) if isinstance(raw_meta, str) else raw_meta
                except (json.JSONDecodeError, TypeError):
                    pass
            self.node_count: int = row.get("node_count", 0)
        else:
            self.id = _uid()
            self.name = ""
            self.description = ""
            self.category = "user"
            self.version = "1.0.0"
            self.author = ""
            self.icon = "📦"
            self.color = "#6b7280"
            self.is_builtin = False
            self.metadata = {}
            self.node_count = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "category": self.category,
            "version": self.version,
            "author": self.author,
            "icon": self.icon,
            "color": self.color,
            "is_builtin": self.is_builtin,
            "metadata": self.metadata,
            "node_count": self.node_count,
        }


class PromptManager:
    """提示词管理器 — 数据库驱动版。

    职责：
    1. 从 DB 加载/查询提示词（nodes + versions）
    2. 版本管理：每次编辑 → 新建版本；支持回滚到历史版本
    3. 模板包管理：一组相关节点的集合
    4. 内置种子初始化：优先从 ``prompt_packages/`` 导入，失败则回退 legacy JSON
    5. 变量渲染：{variable} 占位符替换
    """

    def __init__(self, db_connection=None):
        """
        Args:
            db_connection: DatabaseConnection 实例（延迟注入，避免循环导入）。
                           为 None 时使用全局 get_database()（与 FastAPI / paths.DATA_DIR 一致）。
        """
        self._db = db_connection
        self._seeded = False

    def _get_db(self):
        """与主应用共用同一 SQLite（含桌面版 AITEXT_PROD_DATA_DIR）。"""
        if self._db is not None:
            return self._db
        from infrastructure.persistence.database.connection import get_database

        return get_database()

    # ------------------------------------------------------------------
    # 种子初始化
    # ------------------------------------------------------------------

    def ensure_seeded(self) -> bool:
        """确保内置种子已导入数据库（幂等）。

        v4 加载策略：
        1. 优先 ``prompt_packages/nodes/*/``（package.yaml + system.md + user.md + extras.json）
        2. 若包为空，回退合并 ``prompts_defaults.json`` + ``prompts_*.json``（与 v3 行为一致）
        """
        if self._seeded:
            return True
        db = self._get_db()
        conn = db.get_connection()

        from infrastructure.ai.prompt_seed.loader import load_seed_bundle, merge_legacy_json_prompts

        bundle_meta, prompt_list = load_seed_bundle()
        seed_data: Optional[Dict[str, Any]] = None
        if prompt_list:
            seed_data = {"_meta": bundle_meta, "prompts": prompt_list}
            logger.info("PromptManager: 使用 prompt_packages 种子（%d 个节点）", len(prompt_list))
        else:
            merged_meta, plist = merge_legacy_json_prompts(_PROMPTS_DIR)
            if plist:
                seed_data = {"_meta": merged_meta, "prompts": plist}
                logger.warning(
                    "prompt_packages 无节点，已回退 legacy JSON（%d 个）；"
                    "请运行: python -m infrastructure.ai.prompt_seed.export_legacy",
                    len(plist),
                )

        if not seed_data or not seed_data.get("prompts"):
            logger.error("没有找到任何提示词种子（prompt_packages 与 legacy JSON 均为空）")
            return False

        meta = seed_data.get("_meta", {})
        seed_version = meta.get("version", "1.0.0")
        prompts = seed_data.get("prompts", [])

        # 检查是否已有内置模板包
        row = conn.execute(
            "SELECT id, metadata FROM prompt_templates WHERE is_builtin=1 LIMIT 1"
        ).fetchone()

        if not row:
            # 首次导入：完整初始化
            return self._do_full_seed(conn, seed_data, meta)

        # 已有种子，检查版本
        template_id = row["id"]
        existing_meta = {}
        try:
            existing_meta = json.loads(row["metadata"]) if row["metadata"] else {}
        except (json.JSONDecodeError, TypeError):
            pass

        existing_version = existing_meta.get("version", "")

        if existing_version == seed_version:
            self._seeded = True
            logger.info("PromptManager: 种子版本相同 (%s)，跳过更新", seed_version)
            return True

        # 版本不同，执行增量更新
        logger.info(
            "PromptManager: 检测到种子更新 %s → %s，开始增量同步...",
            existing_version, seed_version
        )
        return self._do_incremental_update(conn, seed_data, meta, template_id)

    def _do_full_seed(self, conn, seed_data: Dict, meta: Dict) -> bool:
        """完整导入种子（首次启动）。"""
        template_id = _uid()
        now = datetime.now().isoformat()

        # 创建内置模板包
        conn.execute("""
            INSERT INTO prompt_templates
            (id, name, description, category, version, author, icon, color, is_builtin, metadata, created_at, updated_at)
            VALUES (?, ?, ?, 'builtin', ?, ?, '🏗️', '#4f46e5', 1, ?, ?, ?)
        """, (
            template_id,
            meta.get("name", "PlotPilot 内置"),
            meta.get("description", ""),
            meta.get("version", "1.0.0"),
            meta.get("author", "PlotPilot Team"),
            json.dumps(meta, ensure_ascii=False),
            now, now,
        ))

        # 批量插入节点和初始版本
        prompts = seed_data.get("prompts", [])
        for idx, p in enumerate(prompts):
            self._insert_node(conn, template_id, idx, p, now)

        conn.commit()
        self._seeded = True
        logger.info("PromptManager: 已导入 %d 个内置提示词种子", len(prompts))
        return True

    def _do_incremental_update(
        self, conn, seed_data: Dict, meta: Dict, template_id: str
    ) -> bool:
        """增量更新种子（已有用户数据）。"""
        now = datetime.now().isoformat()
        prompts = seed_data.get("prompts", [])
        updated_count = 0
        added_count = 0
        preserved_count = 0

        # 获取已存在的节点信息
        existing_nodes = conn.execute(
            "SELECT id, node_key FROM prompt_nodes WHERE template_id = ?",
            (template_id,)
        ).fetchall()
        existing_keys = {r["node_key"]: r["id"] for r in existing_nodes}

        for idx, p in enumerate(prompts):
            node_key = p.get("id", f"node-{idx}")

            if node_key not in existing_keys:
                # 新增的提示词，直接插入
                self._insert_node(conn, template_id, idx, p, now)
                added_count += 1
            else:
                # 已存在的提示词，检查是否需要更新
                node_id = existing_keys[node_key]
                if self._should_update_node(conn, node_id, p, now):
                    updated_count += 1
                else:
                    preserved_count += 1

        # 更新模板包的版本信息
        conn.execute("""
            UPDATE prompt_templates
            SET version = ?, metadata = ?, updated_at = ?
            WHERE id = ?
        """, (meta.get("version", "1.0.0"), json.dumps(meta, ensure_ascii=False), now, template_id))

        conn.commit()
        self._seeded = True
        logger.info(
            "PromptManager: 增量同步完成 - 新增 %d，更新 %d，保留用户修改 %d",
            added_count, updated_count, preserved_count
        )
        return True

    def _insert_node(self, conn, template_id: str, idx: int, p: Dict, now: str) -> str:
        """插入新节点及其初始版本。"""
        from infrastructure.ai.prompt_seed.normalize import normalize_prompt_record

        p = normalize_prompt_record(dict(p))
        sort_order = int(p.get("sort_order", idx))

        node_id = _uid()
        ver_id = _uid()
        tags_json = json.dumps(p.get("tags", []), ensure_ascii=False)
        vars_json = json.dumps(p.get("variables", []), ensure_ascii=False)

        conn.execute("""
            INSERT INTO prompt_nodes
            (id, template_id, node_key, name, description, category, source,
             output_format, contract_module, contract_model, tags, variables,
             system_file, is_builtin, sort_order, active_version_id, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?)
        """, (
            node_id, template_id,
            p.get("id", f"node-{idx}"),
            p.get("name", ""),
            p.get("description", ""),
            p.get("category", "generation"),
            p.get("source", ""),
            p.get("output_format", "text"),
            p.get("contract_module"),
            p.get("contract_model"),
            tags_json, vars_json,
            p.get("system_file"),
            sort_order,
            ver_id, now, now,
        ))

        conn.execute("""
            INSERT INTO prompt_versions
            (id, node_id, version_number, system_prompt, user_template,
             change_summary, created_by, created_at)
            VALUES (?, ?, 1, ?, ?, '初始种子', 'system', ?)
        """, (ver_id, node_id, p.get("system", ""), p.get("user_template", ""), now))

        return node_id

    def _should_update_node(self, conn, node_id: str, new_data: Dict, now: str) -> bool:
        """检查节点是否需要更新，并执行更新。

        策略：
        - 用户修改过（created_by == 'user'）：保留用户版本，跳过更新
        - 用户未修改过（created_by == 'system'）：用新系统版本覆盖
        """
        from infrastructure.ai.prompt_seed.normalize import normalize_prompt_record

        # 获取当前激活版本 + 节点 variables（扩展字段如 _directives 存于此）
        row = conn.execute("""
            SELECT v.id, v.version_number, v.system_prompt, v.user_template, v.created_by,
                   n.variables AS node_variables_json
            FROM prompt_versions v
            INNER JOIN prompt_nodes n ON n.active_version_id = v.id
            WHERE n.id = ?
        """, (node_id,)).fetchone()

        if not row:
            # 没有激活版本，直接插入新版本
            return self._update_system_version(conn, node_id, new_data, 1, now)

        created_by = row["created_by"]

        # 比较内容是否有变化
        new_norm = normalize_prompt_record(dict(new_data))
        new_system = new_norm.get("system", "")
        new_user = new_norm.get("user_template", "")
        new_vars = new_norm.get("variables", [])
        old_system = row["system_prompt"] or ""
        old_user = row["user_template"] or ""

        try:
            old_vars = json.loads(row["node_variables_json"]) if row["node_variables_json"] else []
        except (json.JSONDecodeError, TypeError):
            old_vars = []
        if not isinstance(old_vars, list):
            old_vars = []

        def _vars_sig(obj: Any) -> str:
            return json.dumps(obj or [], ensure_ascii=False, sort_keys=True)

        if (
            new_system == old_system
            and new_user == old_user
            and _vars_sig(new_vars) == _vars_sig(old_vars)
        ):
            # 内容相同，无需更新
            return False

        if created_by == "user":
            # 用户修改过：保留用户版本，跳过更新
            logger.info(
                "节点 %s 有用户修改，保留用户版本，跳过系统更新",
                new_data.get("id", node_id)
            )
            return False
        else:
            # 系统版本：直接覆盖
            return self._overwrite_system_version(conn, node_id, row["id"], new_norm, now)

    def _update_system_version(self, conn, node_id: str, new_data: Dict, next_ver: int, now: str) -> bool:
        """创建新的系统版本。"""
        from infrastructure.ai.prompt_seed.normalize import normalize_prompt_record

        new_data = normalize_prompt_record(dict(new_data))
        new_ver_id = _uid()
        new_system = new_data.get("system", "")
        new_user = new_data.get("user_template", "")

        conn.execute("""
            INSERT INTO prompt_versions
            (id, node_id, version_number, system_prompt, user_template,
             change_summary, created_by, created_at)
            VALUES (?, ?, ?, ?, ?, '系统更新', 'system', ?)
        """, (new_ver_id, node_id, next_ver, new_system, new_user, now))

        # 更新节点的激活版本和元数据
        conn.execute("""
            UPDATE prompt_nodes
            SET active_version_id = ?, updated_at = ?
            WHERE id = ?
        """, (new_ver_id, now, node_id))

        self._update_node_metadata(conn, node_id, new_data, now)
        return True

    def _overwrite_system_version(self, conn, node_id: str, version_id: str, new_data: Dict, now: str) -> bool:
        """直接覆盖系统版本内容。"""
        from infrastructure.ai.prompt_seed.normalize import normalize_prompt_record

        new_data = normalize_prompt_record(dict(new_data))
        new_system = new_data.get("system", "")
        new_user = new_data.get("user_template", "")

        conn.execute("""
            UPDATE prompt_versions
            SET system_prompt = ?, user_template = ?, created_at = ?
            WHERE id = ?
        """, (new_system, new_user, now, version_id))

        self._update_node_metadata(conn, node_id, new_data, now)
        logger.info("节点 %s 系统版本已覆盖更新", new_data.get("id", node_id))
        return True

    def _update_node_metadata(self, conn, node_id: str, p: Dict, now: str) -> None:
        """更新节点元数据（name, description, tags, variables 等）。"""
        tags_json = json.dumps(p.get("tags", []), ensure_ascii=False)
        vars_json = json.dumps(p.get("variables", []), ensure_ascii=False)

        conn.execute("""
            UPDATE prompt_nodes
            SET name = ?, description = ?, category = ?, source = ?,
                output_format = ?, tags = ?, variables = ?, updated_at = ?
            WHERE id = ?
        """, (
            p.get("name", ""),
            p.get("description", ""),
            p.get("category", "generation"),
            p.get("source", ""),
            p.get("output_format", "text"),
            tags_json, vars_json,
            now, node_id
        ))

    # ------------------------------------------------------------------
    # 模板包 CRUD
    # ------------------------------------------------------------------

    def list_templates(self) -> List[TemplateInfo]:
        """列出所有模板包。"""
        db = self._get_db()
        rows = db.execute("""
            SELECT t.*, COUNT(n.id) AS node_count
            FROM prompt_templates t
            LEFT JOIN prompt_nodes n ON n.template_id = t.id
            GROUP BY t.id
            ORDER BY t.is_builtin DESC, t.created_at ASC
        """).fetchall()
        return [TemplateInfo(dict(r)) for r in rows]

    def get_template(self, template_id: str) -> Optional[TemplateInfo]:
        """获取单个模板包详情。"""
        db = self._get_db()
        row = db.execute("""
            SELECT t.*, COUNT(n.id) AS node_count
            FROM prompt_templates t
            LEFT JOIN prompt_nodes n ON n.template_id = t.id
            WHERE t.id = ?
            GROUP BY t.id
        """, (template_id,)).fetchone()
        return TemplateInfo(dict(row)) if row else None

    def create_template(self, name: str, description: str = "",
                        category: str = "user", **kwargs) -> TemplateInfo:
        """创建自定义模板包。"""
        db = self._get_db()
        tid = _uid()
        now = datetime.now().isoformat()
        conn = db.get_connection()
        conn.execute("""
            INSERT INTO prompt_templates
            (id, name, description, category, version, author, icon, color,
             is_builtin, metadata, created_at, updated_at)
            VALUES (?, ?, ?, ?, '1.0.0', '', '📦', '#6b7280', 0, '{}', ?, ?)
        """, (tid, name, description, category, now, now))
        conn.commit()
        return TemplateInfo({"id": tid, "name": name, "description": description,
                             "category": category, "node_count": 0})

    # ------------------------------------------------------------------
    # 节点 CRUD
    # ------------------------------------------------------------------

    def list_nodes(
        self,
        category: Optional[str] = None,
        template_id: Optional[str] = None,
        include_versions: bool = False,
    ) -> List[NodeInfo]:
        """列举提示词节点，可按分类/模板过滤。"""
        db = self._get_db()
        params: List[Any] = []
        where_clauses = ["1=1"]

        if category:
            where_clauses.append("n.category = ?")
            params.append(category)
        if template_id:
            where_clauses.append("n.template_id = ?")
            params.append(template_id)

        where_sql = " AND ".join(where_clauses)

        rows = db.execute(f"""
            SELECT n.*, COUNT(v.id) AS version_count
            FROM prompt_nodes n
            LEFT JOIN prompt_versions v ON v.node_id = n.id
            WHERE {where_sql}
            GROUP BY n.id
            ORDER BY n.sort_order ASC, n.node_key ASC
        """, params).fetchall()

        nodes = [NodeInfo(dict(r)) for r in rows]

        if include_versions:
            self._attach_active_versions(nodes)

        return nodes

    def get_node(self, node_key_or_id: str,
                 by_key: bool = True) -> Optional[NodeInfo]:
        """获取单个节点详情（含激活版本内容）。"""
        db = self._get_db()
        if by_key:
            col = "node_key"
        else:
            col = "id"

        row = db.execute(f"""
            SELECT n.*, COUNT(v.id) AS version_count
            FROM prompt_nodes n
            LEFT JOIN prompt_versions v ON v.node_id = n.id
            WHERE n.{col} = ?
            GROUP BY n.id
        """, (node_key_or_id,)).fetchone()

        if not row:
            return None

        node = NodeInfo(dict(row))
        self._attach_active_versions([node])
        return node

    def search_nodes(self, query: str) -> List[NodeInfo]:
        """搜索节点（匹配 name/description/tags/source/node_key）。"""
        q = query.lower().strip()
        if not q:
            return self.list_nodes(include_versions=True)

        db = self._get_db()
        pattern = f"%{q}%"
        rows = db.execute("""
            SELECT n.*, COUNT(v.id) AS version_count
            FROM prompt_nodes n
            LEFT JOIN prompt_versions v ON v.node_id = n.id
            WHERE LOWER(n.name) LIKE ? OR LOWER(n.description) LIKE ?
               OR LOWER(n.source) LIKE ? OR LOWER(n.node_key) LIKE ?
               OR n.tags LIKE ?
            GROUP BY n.id
            ORDER BY n.sort_order ASC
        """, (pattern, pattern, pattern, pattern, pattern)).fetchall()

        nodes = [NodeInfo(dict(r)) for r in rows]
        self._attach_active_versions(nodes)
        return nodes

    def create_node(self, template_id: str, node_key: str, name: str,
                    system_prompt: str = "", user_template: str = "",
                    **kwargs) -> NodeInfo:
        """在指定模板包下创建新节点（v1）。"""
        db = self._get_db()
        node_id = _uid()
        ver_id = _uid()
        now = datetime.now().isoformat()

        tags_s = json.dumps(kwargs.get("tags", []), ensure_ascii=False)
        vars_s = json.dumps(kwargs.get("variables", []), ensure_ascii=False)
        out_fmt = kwargs.get("output_format") or "text"
        src = kwargs.get("source") or ""
        cm = kwargs.get("contract_module")
        cmodel = kwargs.get("contract_model")

        db.execute("""
            INSERT INTO prompt_nodes
            (id, template_id, node_key, name, description, category,
             source, output_format, contract_module, contract_model, tags, variables,
             is_builtin, sort_order, active_version_id, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 0, ?, ?, ?)
        """, (
            node_id, template_id, node_key, name,
            kwargs.get("description", ""), kwargs.get("category", "generation"),
            src, out_fmt, cm, cmodel, tags_s, vars_s,
            ver_id, now, now,
        ))

        db.execute("""
            INSERT INTO prompt_versions
            (id, node_id, version_number, system_prompt, user_template,
             change_summary, created_by, created_at)
            VALUES (?, ?, 1, ?, ?, '初始版本', 'user', ?)
        """, (ver_id, node_id, system_prompt, user_template, now))

        db.commit()
        return self.get_node(node_id, by_key=False)

    def delete_node(self, node_id: str) -> bool:
        """删除节点及其所有版本。"""
        db = self._get_db()
        cursor = db.execute("DELETE FROM prompt_nodes WHERE id = ?", (node_id,))
        db.commit()
        return cursor.rowcount > 0

    # ------------------------------------------------------------------
    # 版本管理（核心！）
    # ------------------------------------------------------------------

    def get_node_versions(self, node_id: str) -> List[VersionInfo]:
        """获取节点的所有版本列表（时间线）。"""
        db = self._get_db()
        rows = db.execute("""
            SELECT * FROM prompt_versions
            WHERE node_id = ?
            ORDER BY version_number DESC
        """, (node_id,)).fetchall()
        return [VersionInfo(dict(r)) for r in rows]

    def get_version(self, version_id: str) -> Optional[VersionInfo]:
        """获取单个版本详情。"""
        db = self._get_db()
        row = db.execute(
            "SELECT * FROM prompt_versions WHERE id = ?", (version_id,)
        ).fetchone()
        return VersionInfo(dict(row)) if row else None

    def update_node(
        self,
        node_id: str,
        system_prompt: Optional[str] = None,
        user_template: Optional[str] = None,
        change_summary: str = "",
        **kwargs,
    ) -> Optional[NodeInfo]:
        """更新节点内容 —— 自动创建新版本（不覆盖旧版）。

        Returns:
            更新后的节点（含新激活版本）。
        """
        db = self._get_db()

        # 获取当前最新版本号
        row = db.execute(
            "SELECT COALESCE(MAX(version_number), 0) AS max_ver "
            "FROM prompt_versions WHERE node_id = ?",
            (node_id,),
        ).fetchone()
        next_ver = (row["max_ver"] if row else 0) + 1
        new_ver_id = _uid()
        now = datetime.now().isoformat()

        # 获取当前版本作为基础
        current = self._get_current_version(db, node_id)
        new_system = system_prompt if system_prompt is not None else (
            current.system_prompt if current else ""
        )
        new_user = user_template if user_template is not None else (
            current.user_template if current else ""
        )

        # 创建新版本
        db.execute("""
            INSERT INTO prompt_versions
            (id, node_id, version_number, system_prompt, user_template,
             change_summary, created_by, created_at)
            VALUES (?, ?, ?, ?, ?, ?, 'user', ?)
        """, (new_ver_id, node_id, next_ver, new_system, new_user,
              change_summary or f"v{next_ver} 编辑", now))

        # 更新节点的 active_version_id 和元字段
        set_clauses = ["active_version_id = ?", "updated_at = ?"]
        params: List[Any] = [new_ver_id, now]

        if kwargs.get("name"):
            set_clauses.append("name = ?")
            params.append(kwargs["name"])
        if kwargs.get("description") is not None:
            set_clauses.append("description = ?")
            params.append(kwargs["description"])
        if kwargs.get("tags") is not None:
            set_clauses.append("tags = ?")
            params.append(json.dumps(kwargs["tags"], ensure_ascii=False))
        if kwargs.get("variables") is not None:
            set_clauses.append("variables = ?")
            params.append(json.dumps(kwargs["variables"], ensure_ascii=False))
        if kwargs.get("output_format") is not None:
            set_clauses.append("output_format = ?")
            params.append(kwargs["output_format"])
        if kwargs.get("contract_module") is not None:
            set_clauses.append("contract_module = ?")
            params.append(kwargs["contract_module"])
        if kwargs.get("contract_model") is not None:
            set_clauses.append("contract_model = ?")
            params.append(kwargs["contract_model"])
        if kwargs.get("source") is not None:
            set_clauses.append("source = ?")
            params.append(kwargs["source"])
        if kwargs.get("category") is not None:
            set_clauses.append("category = ?")
            params.append(kwargs["category"])

        params.append(node_id)
        sql = f"UPDATE prompt_nodes SET {', '.join(set_clauses)} WHERE id = ?"
        db.execute(sql, params)
        db.commit()

        return self.get_node(node_id, by_key=False)

    def rollback_node(self, node_id: str,
                      target_version_id: str) -> Optional[NodeInfo]:
        """回滚节点到指定历史版本（创建一个新版本作为「回滚快照」）。

        这样做的好处：
        - 不删除任何历史记录
        - 回滚本身也是一个版本，可以再次回滚回来
        """
        db = self._get_db()

        # 获取目标版本
        target = self.get_version(target_version_id)
        if not target:
            return None

        # 获取当前最新版本号
        row = db.execute(
            "SELECT COALESCE(MAX(version_number), 0) AS max_ver "
            "FROM prompt_versions WHERE node_id = ?",
            (node_id,),
        ).fetchone()
        next_ver = (row["max_ver"] if row else 0) + 1
        new_ver_id = _uid()
        now = datetime.now().isoformat()

        # 以目标版本的内容创建新版本（标记为回滚）
        db.execute("""
            INSERT INTO prompt_versions
            (id, node_id, version_number, system_prompt, user_template,
             change_summary, created_by, created_at)
            VALUES (?, ?, ?, ?, ?, ?, 'user', ?)
        """, (
            new_ver_id, node_id, next_ver,
            target.system_prompt, target.user_template,
            f"回滚到 v{target.version_number}",
            now,
        ))

        db.execute(
            "UPDATE prompt_nodes SET active_version_id=?, updated_at=? WHERE id=?",
            (new_ver_id, now, node_id),
        )
        db.commit()

        return self.get_node(node_id, by_key=False)

    def compare_versions(self, version_id_1: str,
                         version_id_2: str) -> Dict[str, Any]:
        """对比两个版本的差异。"""
        v1 = self.get_version(version_id_1)
        v2 = self.get_version(version_id_2)
        if not v1 or not v2:
            raise ValueError("版本不存在")

        return {
            "v1": v1.to_detail_dict(),
            "v2": v2.to_detail_dict(),
            "diff": {
                "system_changed": v1.system_prompt != v2.system_prompt,
                "user_changed": v1.user_template != v2.user_template,
            },
        }

    # ------------------------------------------------------------------
    # 渲染
    # ------------------------------------------------------------------

    def render(self, node_key: str,
               variables: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, str]]:
        """渲染指定节点的提示词。

        Args:
            node_key: 节点唯一标识
            variables: 模板变量字典

        Returns:
            {"system": ..., "user": ...} 或 None
        """
        node = self.get_node(node_key, by_key=True)
        if not node:
            return None

        var_map = variables or {}
        system = self._render_template(node.get_active_system(), var_map)
        user = self._render_template(node.get_active_user_template(), var_map)

        return {"system": system, "user": user}

    @staticmethod
    def _render_template(template: str, variables: Dict[str, Any]) -> str:
        """简单模板渲染：{variable} 替换。"""
        if not template:
            return ""

        class SafeDict(dict):
            def __missing__(self, key):
                return "{" + key + "}"

        try:
            return template.format_map(SafeDict(variables))
        except (KeyError, ValueError, IndexError):
            return template

    # ------------------------------------------------------------------
    # 统计 & 分组
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        """获取提示词库统计。"""
        db = self._get_db()
        total_nodes = db.execute("SELECT COUNT(*) AS c FROM prompt_nodes").fetchone()["c"]
        total_templates = db.execute("SELECT COUNT(*) AS c FROM prompt_templates").fetchone()["c"]
        total_versions = db.execute("SELECT COUNT(*) AS c FROM prompt_versions").fetchone()["c"]
        builtin_count = db.execute(
            "SELECT COUNT(*) AS c FROM prompt_nodes WHERE is_builtin=1"
        ).fetchone()["c"]
        custom_count = total_nodes - builtin_count

        # 各分类数量
        cat_rows = db.execute(
            "SELECT category, COUNT(*) AS c FROM prompt_nodes GROUP BY category"
        ).fetchall()
        categories = {r["category"]: r["c"] for r in cat_rows}

        return {
            "total_nodes": total_nodes,
            "total_templates": total_templates,
            "total_versions": total_versions,
            "builtin_count": builtin_count,
            "custom_count": custom_count,
            "categories": categories,
        }

    def get_nodes_by_category(self) -> Dict[str, List[NodeInfo]]:
        """按分类分组的所有节点。"""
        nodes = self.list_nodes(include_versions=True)
        result: Dict[str, List[NodeInfo]] = {}
        for node in nodes:
            result.setdefault(node.category, []).append(node)
        return result

    def get_categories_info(self) -> List[Dict[str, Any]]:
        """返回分类定义列表（含节点计数）。"""
        stats = self.get_stats()
        cat_counts = stats.get("categories", {})
        result = []
        for cat_def in BUILTIN_CATEGORIES:
            info = dict(cat_def)
            info["count"] = cat_counts.get(cat_def["key"], 0)
            result.append(info)
        return result

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------

    def _attach_active_versions(self, nodes: List[NodeInfo]) -> None:
        """批量加载节点的激活版本。"""
        if not nodes:
            return
        db = self._get_db()
        ids = [n.active_version_id for n in nodes if n.active_version_id]
        if not ids:
            return
        placeholders = ",".join("?" * len(ids))
        rows = db.execute(
            f"SELECT * FROM prompt_versions WHERE id IN ({placeholders})", ids
        ).fetchall()
        ver_map = {r["id"]: VersionInfo(dict(r)) for r in rows}
        for node in nodes:
            if node.active_version_id and node.active_version_id in ver_map:
                node.set_active_version(ver_map[node.active_version_id])

    @staticmethod
    def _get_current_version(db, node_id: str) -> Optional[VersionInfo]:
        """获取节点当前激活版本。"""
        row = db.execute("""
            SELECT v.* FROM prompt_versions v
            INNER JOIN prompt_nodes n ON n.active_version_id = v.id
            WHERE n.id = ?
        """, (node_id,)).fetchone()
        return VersionInfo(dict(row)) if row else None


# ------------------------------------------------------------------
# 单例
# ------------------------------------------------------------------

_manager_instance: Optional[PromptManager] = None


def get_prompt_manager() -> PromptManager:
    """获取全局 PromptManager 单例。"""
    global _manager_instance
    if _manager_instance is None:
        _manager_instance = PromptManager()
    return _manager_instance
