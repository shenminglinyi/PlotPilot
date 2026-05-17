"""PromptRuntimeService — 提示词运行时服务（CPMS 统一代理）

重构后：
- 所有读取操作委托给 PromptRegistry（CPMS 核心门面）
- 保留 render 方法兼容评估脚本
- 消除旧 JSON / 旧 prompts 表的直接读取
- rule_keys 组合渲染 + 变量注入 + 上下文块去重
"""
from __future__ import annotations

import logging
import re
from typing import Dict, Any, List, Optional, Set

from infrastructure.ai.prompt_registry import get_prompt_registry

logger = logging.getLogger(__name__)


class PromptRuntimeService:
    """提示词运行时服务（CPMS 统一代理）

    设计原则：
    - 所有读取委托 PromptRegistry
    - rule_keys 组合渲染 + 变量注入
    - 上下文块去重（避免重复信息）
    """

    def __init__(self, db_pool=None, prompts_dir: str = None):
        """初始化。

        Args:
            db_pool: 保留参数（兼容旧调用），不再直接使用
            prompts_dir: 保留参数（兼容旧调用），不再直接使用
        """
        self._registry = get_prompt_registry()

    async def get_prompt(self, name: str) -> Optional[Dict[str, Any]]:
        """获取提示词节点详情（通过 PromptRegistry）。

        Args:
            name: 提示词节点 node_key

        Returns:
            节点详情字典，不存在则 None
        """
        node = self._registry.get_node(name)
        if not node:
            return None

        return {
            "name": node.node_key,
            "content": node.get_active_system(),
            "template": node.get_active_user_template(),
            "category": node.category,
            "description": node.description,
            "tags": node.tags,
            "variables": node.variables,
            "is_builtin": node.is_builtin,
        }

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
            node = self._registry.get_node(key)
            if not node:
                logger.warning("提示词节点不存在: %s", key)
                continue

            # 优先取 system，回退取 user_template
            content = node.get_active_system() or node.get_active_user_template()

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
        """列出提示词节点（通过 PromptRegistry）。

        Args:
            node_type: 节点类型过滤 (rule/template/workflow/extractor/reviewer/formatter)
            subcategory: 二级分类过滤（映射为 category）

        Returns:
            提示词节点列表
        """
        category = subcategory or node_type
        nodes = self._registry.list_nodes(category=category)
        results = []
        for node in nodes:
            results.append({
                "name": node.node_key,
                "content": node.get_active_system(),
                "template": node.get_active_user_template(),
                "category": node.category,
                "description": node.description,
                "tags": node.tags,
                "is_builtin": node.is_builtin,
            })
        return results

    async def create_or_update(self, name: str, content: str, metadata: Dict[str, Any] = None) -> bool:
        """创建或更新提示词节点（通过 PromptRegistry）。

        注意：CPMS 中节点的创建/更新由 PromptManager 管理。
        此方法提供兼容接口，直接委托给 PromptManager。
        """
        from infrastructure.ai.prompt_manager import get_prompt_manager

        try:
            mgr = get_prompt_manager()
            mgr.ensure_seeded()
            # 通过 PromptManager 更新节点
            mgr.upsert_node_content(
                node_key=name,
                system_content=content,
                user_template=metadata.get("template", "") if metadata else "",
            )
            # 刷新缓存
            self._registry.invalidate_cache(name)
            return True
        except Exception as e:
            logger.error("创建/更新提示词失败: %s", e)
            return False
