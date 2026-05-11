"""PromptRuntimeService — 提示词运行时服务

核心改进：
- DB激活版优先 → JSON回退
- render方法支持rule_keys组合 + 变量注入 + 上下文块去重
- 支持节点类型分类（rule/template/workflow/extractor/reviewer/formatter）
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Dict, Any, List, Optional, Set

logger = logging.getLogger(__name__)


class PromptRuntimeService:
    """提示词运行时服务

    设计原则：
    - DB激活版优先，JSON回退
    - rule_keys组合渲染 + 变量注入
    - 上下文块去重（避免重复信息）
    - 二级分类 + 节点类型
    """

    def __init__(self, db_pool=None, prompts_dir: str = None):
        self._db_pool = db_pool
        self._prompts_dir = Path(prompts_dir) if prompts_dir else None
        self._json_cache: Dict[str, Dict[str, Any]] = {}
        self._load_json_prompts()

    def _load_json_prompts(self):
        """加载规则类 JSON（rules_seed.json）。CPMS 节点种子已迁至 prompt_packages/。"""
        if not self._prompts_dir or not self._prompts_dir.exists():
            return

        rules_file = self._prompts_dir / "rules_seed.json"
        if rules_file.is_file():
            try:
                with open(rules_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, list):
                    for item in data:
                        if isinstance(item, dict) and "name" in item:
                            self._json_cache[item["name"]] = item
                logger.debug("已加载规则种子: %s", rules_file.name)
            except Exception as e:
                logger.warning(f"加载规则种子失败 {rules_file}: {e}")

    async def get_prompt(self, name: str) -> Optional[Dict[str, Any]]:
        """获取提示词（DB优先 → JSON回退）

        Args:
            name: 提示词名称

        Returns:
            提示词对象
        """
        # 1. 尝试从DB读取激活版
        if self._db_pool:
            try:
                with self._db_pool.get_connection() as conn:
                    row = conn.execute(
                        """SELECT * FROM prompts
                           WHERE name = ? AND is_active = 1
                           ORDER BY version DESC LIMIT 1""",
                        (name,)
                    ).fetchone()

                    if row:
                        return dict(row)
            except Exception as e:
                logger.debug(f"DB读取提示词失败: {e}")

        # 2. 回退到JSON缓存
        if name in self._json_cache:
            return self._json_cache[name]

        return None

    async def render(
        self,
        rule_keys: List[str],
        variables: Dict[str, str] = None,
        context_blocks: List[str] = None,
        deduplicate: bool = True,
    ) -> str:
        """渲染提示词组合

        Args:
            rule_keys: rule节点名称列表（按优先级排序）
            variables: 变量注入 {variable_name: value}
            context_blocks: 上下文块列表
            deduplicate: 是否去重

        Returns:
            渲染后的提示词字符串
        """
        sections: List[str] = []
        seen_content: Set[str] = set()

        # 1. 加载rule节点
        for key in rule_keys:
            prompt = await self.get_prompt(key)
            if not prompt:
                logger.warning(f"提示词节点不存在: {key}")
                continue

            content = prompt.get("content", "") or prompt.get("template", "")

            # 变量注入
            if variables:
                content = self._inject_variables(content, variables)

            # 去重
            if deduplicate:
                content_hash = hash(content.strip())
                if content_hash in seen_content:
                    continue
                seen_content.add(content_hash)

            sections.append(content)

        # 2. 添加上下文块（去重）
        if context_blocks:
            for block in context_blocks:
                if deduplicate:
                    block_hash = hash(block.strip())
                    if block_hash in seen_content:
                        continue
                    seen_content.add(block_hash)
                sections.append(block)

        return "\n\n".join(sections)

    def _inject_variables(self, template: str, variables: Dict[str, str]) -> str:
        """变量注入 — 替换 {variable_name} 占位符"""
        def replace_var(match):
            var_name = match.group(1)
            if var_name in variables:
                return str(variables[var_name])
            return match.group(0)  # 未找到变量，保留原样

        return re.sub(r'\{(\w+)\}', replace_var, template)

    def scan_variables(self, template: str) -> List[str]:
        """扫描模板中的变量占位符

        Args:
            template: 模板字符串

        Returns:
            变量名列表
        """
        return re.findall(r'\{(\w+)\}', template)

    async def list_prompts(
        self,
        node_type: str = None,
        subcategory: str = None,
    ) -> List[Dict[str, Any]]:
        """列出提示词节点

        Args:
            node_type: 节点类型过滤 (rule/template/workflow/extractor/reviewer/formatter)
            subcategory: 二级分类过滤

        Returns:
            提示词节点列表
        """
        results = []

        # 从JSON缓存收集
        for name, prompt in self._json_cache.items():
            metadata = prompt.get("metadata", {})
            if node_type and metadata.get("node_type") != node_type:
                continue
            if subcategory and metadata.get("subcategory") != subcategory:
                continue
            results.append(prompt)

        # 从DB收集
        if self._db_pool:
            try:
                with self._db_pool.get_connection() as conn:
                    query = "SELECT * FROM prompts WHERE is_active = 1"
                    params = []
                    if node_type:
                        query += " AND metadata->>'node_type' = ?"
                        params.append(node_type)
                    if subcategory:
                        query += " AND metadata->>'subcategory' = ?"
                        params.append(subcategory)

                    rows = conn.execute(query, params).fetchall()
                    for row in rows:
                        results.append(dict(row))
            except Exception as e:
                logger.debug(f"DB列出提示词失败: {e}")

        return results

    async def create_or_update(self, name: str, content: str, metadata: Dict[str, Any] = None) -> bool:
        """创建或更新提示词节点"""
        if not self._db_pool:
            # 只能更新JSON缓存
            self._json_cache[name] = {
                "name": name,
                "content": content,
                "metadata": metadata or {},
            }
            return True

        try:
            with self._db_pool.get_connection() as conn:
                conn.execute(
                    """INSERT INTO prompts (name, content, metadata, is_active, version)
                       VALUES (?, ?, ?, 1, 1)
                       ON CONFLICT(name) DO UPDATE SET
                           content = excluded.content,
                           metadata = excluded.metadata,
                           version = version + 1""",
                    (name, content, json.dumps(metadata or {}, ensure_ascii=False))
                )
                conn.commit()
            return True
        except Exception as e:
            logger.error(f"创建/更新提示词失败: {e}")
            return False
