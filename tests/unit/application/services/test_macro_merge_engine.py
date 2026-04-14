"""
宏观合并引擎单元测试
"""

import pytest
from application.audit.services.macro_merge_engine import MacroMergeEngine, MergePlan


class TestMacroMergeEngine:
    """测试宏观合并引擎"""

    def test_green_path_pure_empty_structure(self):
        """绿色通路：纯空框架覆盖"""
        # 旧结构：3 个空幕
        old_nodes = [
            {"id": "act-1", "novel_id": "novel-1", "parent_id": None, "node_type": "ACT", "title": "第一幕", "order_index": 0},
            {"id": "act-2", "novel_id": "novel-1", "parent_id": None, "node_type": "ACT", "title": "第二幕", "order_index": 1},
            {"id": "act-3", "novel_id": "novel-1", "parent_id": None, "node_type": "ACT", "title": "第三幕", "order_index": 2},
        ]

        # 新结构：2 个幕
        new_nodes = [
            {"id": "act-1", "novel_id": "novel-1", "parent_id": None, "node_type": "ACT", "title": "序章", "order_index": 0},
            {"id": "act-2", "novel_id": "novel-1", "parent_id": None, "node_type": "ACT", "title": "正章", "order_index": 1},
        ]

        engine = MacroMergeEngine(old_nodes, new_nodes)
        plan = engine.execute_diff()

        # 验证结果
        assert plan.has_fatal_conflict is False
        assert plan.summary["status"] == "GREEN"
        assert len(plan.creates) == 0  # 没有新增（act-1, act-2 都存在）
        assert len(plan.updates) == 2  # 更新 act-1, act-2 的标题
        assert len(plan.deletes) == 1  # 删除 act-3
        assert plan.deletes[0] == "act-3"

    def test_yellow_path_safe_merge(self):
        """黄色通路：安全合并（保留已写正文）"""
        # 旧结构：3 个幕，第一幕有正文
        old_nodes = [
            {"id": "act-1", "novel_id": "novel-1", "parent_id": None, "node_type": "ACT", "title": "第一幕", "order_index": 0},
            {"id": "chapter-1", "novel_id": "novel-1", "parent_id": "act-1", "node_type": "CHAPTER", "title": "第1章", "order_index": 1},
            {"id": "chapter-2", "novel_id": "novel-1", "parent_id": "act-1", "node_type": "CHAPTER", "title": "第2章", "order_index": 2},
            {"id": "act-2", "novel_id": "novel-1", "parent_id": None, "node_type": "ACT", "title": "第二幕", "order_index": 3},
            {"id": "act-3", "novel_id": "novel-1", "parent_id": None, "node_type": "ACT", "title": "第三幕", "order_index": 4},
        ]

        # 新结构：2 个幕（删除 act-3）
        new_nodes = [
            {"id": "act-1", "novel_id": "novel-1", "parent_id": None, "node_type": "ACT", "title": "序章·觉醒", "order_index": 0},
            {"id": "act-2", "novel_id": "novel-1", "parent_id": None, "node_type": "ACT", "title": "正章·征途", "order_index": 1},
        ]

        engine = MacroMergeEngine(old_nodes, new_nodes)
        plan = engine.execute_diff()

        # 验证结果
        assert plan.has_fatal_conflict is False
        assert plan.summary["status"] == "YELLOW"  # 有正文，黄色通路
        assert len(plan.creates) == 0
        assert len(plan.updates) == 2  # 更新 act-1, act-2 的标题
        assert len(plan.deletes) == 1  # 删除空的 act-3
        assert plan.deletes[0] == "act-3"

        # 验证 act-1 的标题被更新
        updated_act_1 = next(u for u in plan.updates if u["id"] == "act-1")
        assert updated_act_1["title"] == "序章·觉醒"

    def test_red_path_fatal_conflict(self):
        """红色阻断：试图删除包含正文的节点"""
        # 旧结构：3 个幕，第三幕有正文
        old_nodes = [
            {"id": "act-1", "novel_id": "novel-1", "parent_id": None, "node_type": "ACT", "title": "第一幕", "order_index": 0},
            {"id": "act-2", "novel_id": "novel-1", "parent_id": None, "node_type": "ACT", "title": "第二幕", "order_index": 1},
            {"id": "act-3", "novel_id": "novel-1", "parent_id": None, "node_type": "ACT", "title": "第三幕·大结局", "order_index": 2},
            {"id": "chapter-10", "novel_id": "novel-1", "parent_id": "act-3", "node_type": "CHAPTER", "title": "终章", "order_index": 3},
        ]

        # 新结构：只有 2 个幕（试图删除有正文的 act-3）
        new_nodes = [
            {"id": "act-1", "novel_id": "novel-1", "parent_id": None, "node_type": "ACT", "title": "第一幕", "order_index": 0},
            {"id": "act-2", "novel_id": "novel-1", "parent_id": None, "node_type": "ACT", "title": "第二幕", "order_index": 1},
        ]

        engine = MacroMergeEngine(old_nodes, new_nodes)
        plan = engine.execute_diff()

        # 验证结果
        assert plan.has_fatal_conflict is True
        assert plan.summary["status"] == "RED"
        assert len(plan.conflicts) == 1
        assert plan.conflicts[0]["node_id"] == "act-3"
        assert "第三幕·大结局" in plan.conflicts[0]["title"]

    def test_bottom_up_contagion(self):
        """测试自底向上感染机制"""
        # 旧结构：Part → Volume → Act → Chapter（四层嵌套）
        old_nodes = [
            {"id": "part-1", "novel_id": "novel-1", "parent_id": None, "node_type": "PART", "title": "第一部", "order_index": 0},
            {"id": "volume-1", "novel_id": "novel-1", "parent_id": "part-1", "node_type": "VOLUME", "title": "第一卷", "order_index": 1},
            {"id": "act-1", "novel_id": "novel-1", "parent_id": "volume-1", "node_type": "ACT", "title": "第一幕", "order_index": 2},
            {"id": "chapter-1", "novel_id": "novel-1", "parent_id": "act-1", "node_type": "CHAPTER", "title": "第1章", "order_index": 3},
        ]

        # 新结构：删除整个 part-1
        new_nodes = []

        engine = MacroMergeEngine(old_nodes, new_nodes)
        plan = engine.execute_diff()

        # 验证结果：part-1, volume-1, act-1 都应该被标记为 carrier（因为 chapter-1 有正文）
        assert plan.has_fatal_conflict is True
        assert len(plan.conflicts) == 3  # part-1, volume-1, act-1 都冲突
        conflict_ids = {c["node_id"] for c in plan.conflicts}
        assert "part-1" in conflict_ids
        assert "volume-1" in conflict_ids
        assert "act-1" in conflict_ids

    def test_create_new_nodes(self):
        """测试新增节点"""
        # 旧结构：2 个幕
        old_nodes = [
            {"id": "act-1", "novel_id": "novel-1", "parent_id": None, "node_type": "ACT", "title": "第一幕", "order_index": 0},
            {"id": "act-2", "novel_id": "novel-1", "parent_id": None, "node_type": "ACT", "title": "第二幕", "order_index": 1},
        ]

        # 新结构：3 个幕（新增 act-3）
        new_nodes = [
            {"id": "act-1", "novel_id": "novel-1", "parent_id": None, "node_type": "ACT", "title": "第一幕", "order_index": 0},
            {"id": "act-2", "novel_id": "novel-1", "parent_id": None, "node_type": "ACT", "title": "第二幕", "order_index": 1},
            {"id": "act-3", "novel_id": "novel-1", "parent_id": None, "node_type": "ACT", "title": "第三幕", "order_index": 2},
        ]

        engine = MacroMergeEngine(old_nodes, new_nodes)
        plan = engine.execute_diff()

        # 验证结果
        assert plan.has_fatal_conflict is False
        assert len(plan.creates) == 1
        assert plan.creates[0]["id"] == "act-3"
        assert len(plan.updates) == 2  # act-1, act-2 标题未变，但仍会更新
        assert len(plan.deletes) == 0

    def test_update_order_index(self):
        """测试更新 order_index（换皮不换骨）"""
        # 旧结构：act-1, act-2
        old_nodes = [
            {"id": "act-1", "novel_id": "novel-1", "parent_id": None, "node_type": "ACT", "title": "第一幕", "order_index": 0},
            {"id": "act-2", "novel_id": "novel-1", "parent_id": None, "node_type": "ACT", "title": "第二幕", "order_index": 1},
        ]

        # 新结构：act-1, act-2（调整 order_index）
        new_nodes = [
            {"id": "act-1", "novel_id": "novel-1", "parent_id": None, "node_type": "ACT", "title": "序章", "order_index": 10},
            {"id": "act-2", "novel_id": "novel-1", "parent_id": None, "node_type": "ACT", "title": "正章", "order_index": 20},
        ]

        engine = MacroMergeEngine(old_nodes, new_nodes)
        plan = engine.execute_diff()

        # 验证结果：order_index 应该被更新
        assert len(plan.updates) == 2
        updated_act_1 = next(u for u in plan.updates if u["id"] == "act-1")
        assert updated_act_1["order_index"] == 10
        assert updated_act_1["title"] == "序章"
