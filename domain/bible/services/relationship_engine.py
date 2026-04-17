from collections import deque
from enum import Enum
from typing import List, Optional, Set
from domain.bible.value_objects.character_id import CharacterId
from domain.bible.value_objects.relationship import Relationship, RelationType
from domain.bible.value_objects.relationship_graph import RelationshipGraph


class RelationshipTrend(Enum):
    """关系趋势枚举"""
    IMPROVING = "improving"
    DETERIORATING = "deteriorating"
    STABLE = "stable"
    VOLATILE = "volatile"


class RelationshipEngine:
    """关系引擎领域服务

    提供基于图的角色关系管理功能，包括：
    - 关系管理
    - 路径查找
    - 共同连接分析
    - 关系强度计算
    - 关系趋势分析
    - 关系发展建议
    """

    # 关系类型的基础强度值
    _BASE_STRENGTH = {
        RelationType.FAMILY: 10.0,
        RelationType.LOVER: 9.0,
        RelationType.CLOSE_FRIEND: 8.0,
        RelationType.FRIEND: 6.0,
        RelationType.RIVAL: 4.0,
        RelationType.ACQUAINTANCE: 3.0,
        RelationType.ENEMY: 2.0,
        RelationType.STRANGER: 1.0,
    }

    def __init__(self, graph: RelationshipGraph):
        """初始化关系引擎

        Args:
            graph: 关系图对象
        """
        self._graph = graph

    def add_relationship(
        self,
        char1_id: CharacterId,
        char2_id: CharacterId,
        relation: Relationship
    ) -> None:
        """添加关系

        Args:
            char1_id: 角色1 ID
            char2_id: 角色2 ID
            relation: 关系对象
        """
        self._graph.add_relationship(char1_id, char2_id, relation)

    def get_current_relationship(
        self,
        char1_id: CharacterId,
        char2_id: CharacterId
    ) -> Optional[Relationship]:
        """获取最新关系

        Args:
            char1_id: 角色1 ID
            char2_id: 角色2 ID

        Returns:
            最新的关系对象，如果不存在则返回 None
        """
        return self._graph.get_current_relationship(char1_id, char2_id)

    def get_relationship_history(
        self,
        char1_id: CharacterId,
        char2_id: CharacterId
    ) -> List[Relationship]:
        """获取关系演变历史

        Args:
            char1_id: 角色1 ID
            char2_id: 角色2 ID

        Returns:
            关系历史列表，按时间顺序排列
        """
        return self._graph.get_relationship_history(char1_id, char2_id)

    def find_path(
        self,
        char1_id: CharacterId,
        char2_id: CharacterId,
        max_depth: int = 3
    ) -> Optional[List[CharacterId]]:
        """使用 BFS 查找两个角色之间的路径

        Args:
            char1_id: 起始角色 ID
            char2_id: 目标角色 ID
            max_depth: 最大搜索深度

        Returns:
            路径列表（包含起点和终点），如果不存在则返回 None
        """
        # 自己到自己
        if char1_id == char2_id:
            return [char1_id]

        # BFS
        queue = deque([(char1_id, [char1_id])])
        visited = {char1_id}

        while queue:
            current, path = queue.popleft()

            # 检查深度限制
            if len(path) > max_depth:
                continue

            # 获取当前角色的所有关系
            relationships = self._graph.get_all_relationships(current)

            for neighbor_id, _ in relationships:
                if neighbor_id == char2_id:
                    return path + [neighbor_id]

                if neighbor_id not in visited:
                    visited.add(neighbor_id)
                    queue.append((neighbor_id, path + [neighbor_id]))

        return None

    def get_common_connections(
        self,
        char1_id: CharacterId,
        char2_id: CharacterId
    ) -> List[CharacterId]:
        """查找共同连接

        Args:
            char1_id: 角色1 ID
            char2_id: 角色2 ID

        Returns:
            共同连接的角色 ID 列表
        """
        adjacency = getattr(self._graph, "_adjacency_list", {})
        char1_connections = set(adjacency.get(char1_id, {}).keys())
        char2_connections = set(adjacency.get(char2_id, {}).keys())

        # 找出共同连接（排除彼此）
        common = char1_connections & char2_connections
        common.discard(char1_id)
        common.discard(char2_id)

        return list(common)

    def get_relationship_cluster(
        self,
        char_id: CharacterId,
        depth: int = 2
    ) -> List[CharacterId]:
        """获取关系网络聚类

        Args:
            char_id: 角色 ID
            depth: 搜索深度

        Returns:
            关系网络中的所有角色 ID（不包含自己）
        """
        visited = {char_id}
        queue = deque([(char_id, 0)])

        while queue:
            current, current_depth = queue.popleft()

            if current_depth >= depth:
                continue

            relationships = self._graph.get_all_relationships(current)

            for neighbor_id, _ in relationships:
                if neighbor_id not in visited:
                    visited.add(neighbor_id)
                    queue.append((neighbor_id, current_depth + 1))

        # 移除起始角色自己
        visited.discard(char_id)
        return list(visited)

    def calculate_relationship_strength(
        self,
        char1_id: CharacterId,
        char2_id: CharacterId
    ) -> float:
        """计算关系强度

        强度计算公式：
        - 基础强度：根据关系类型
        - 互动奖励：每次关系变化 +1
        - 共同连接奖励：每个共同连接 +0.5

        Args:
            char1_id: 角色1 ID
            char2_id: 角色2 ID

        Returns:
            关系强度分数
        """
        # 获取当前关系
        current = self.get_current_relationship(char1_id, char2_id)
        if current is None:
            return 0.0

        # 基础强度
        base_strength = self._BASE_STRENGTH.get(current.relation_type, 0.0)

        # 互动奖励（历史记录数量 - 1）
        history = self.get_relationship_history(char1_id, char2_id)
        interaction_bonus = len(history) - 1

        # 共同连接奖励
        common_connections = self.get_common_connections(char1_id, char2_id)
        common_bonus = len(common_connections) * 0.5

        return base_strength + interaction_bonus + common_bonus

    def analyze_relationship_trend(
        self,
        char1_id: CharacterId,
        char2_id: CharacterId
    ) -> RelationshipTrend:
        """分析关系趋势

        趋势类型：
        - IMPROVING: 强度递增
        - DETERIORATING: 强度递减
        - STABLE: 无显著变化
        - VOLATILE: 频繁波动

        Args:
            char1_id: 角色1 ID
            char2_id: 角色2 ID

        Returns:
            关系趋势
        """
        history = self.get_relationship_history(char1_id, char2_id)

        # 没有关系或只有一个关系点
        if len(history) <= 1:
            return RelationshipTrend.STABLE

        # 计算每个关系的强度
        strengths = [self._BASE_STRENGTH.get(rel.relation_type, 0.0) for rel in history]

        # 计算变化方向
        changes = [strengths[i + 1] - strengths[i] for i in range(len(strengths) - 1)]

        # 分析趋势
        positive_changes = sum(1 for c in changes if c > 0)
        negative_changes = sum(1 for c in changes if c < 0)
        total_changes = len(changes)

        # 波动：正负变化都很多
        if positive_changes > 0 and negative_changes > 0:
            volatility_ratio = min(positive_changes, negative_changes) / total_changes
            if volatility_ratio >= 0.3:  # 至少30%的变化是反向的
                return RelationshipTrend.VOLATILE

        # 改善：主要是正向变化
        if positive_changes > negative_changes:
            return RelationshipTrend.IMPROVING

        # 恶化：主要是负向变化
        if negative_changes > positive_changes:
            return RelationshipTrend.DETERIORATING

        # 稳定：没有变化或变化很小
        return RelationshipTrend.STABLE

    def suggest_relationship_development(
        self,
        char1_id: CharacterId,
        char2_id: CharacterId
    ) -> List[str]:
        """建议关系发展方向

        Args:
            char1_id: 角色1 ID
            char2_id: 角色2 ID

        Returns:
            建议列表
        """
        current = self.get_current_relationship(char1_id, char2_id)
        trend = self.analyze_relationship_trend(char1_id, char2_id)
        common = self.get_common_connections(char1_id, char2_id)

        suggestions = []

        # 没有关系
        if current is None:
            suggestions.append("Introduce the characters through a chance encounter or mutual friend")
            suggestions.append("Create a situation where they must work together")
            if common:
                suggestions.append(f"Use their {len(common)} mutual connection(s) to bring them together")
            return suggestions

        # 根据当前关系类型给建议
        if current.relation_type == RelationType.STRANGER:
            suggestions.append("Have them engage in meaningful conversation")
            suggestions.append("Create opportunities for repeated interactions")
            suggestions.append("Introduce a shared interest or goal")

        elif current.relation_type == RelationType.ACQUAINTANCE:
            suggestions.append("Develop a shared experience or challenge")
            suggestions.append("Have them discover common interests")
            suggestions.append("Create a situation requiring trust")

        elif current.relation_type == RelationType.FRIEND:
            suggestions.append("Deepen their bond through shared vulnerability")
            suggestions.append("Test their friendship with a conflict or challenge")
            suggestions.append("Explore romantic potential or strengthen platonic bond")

        elif current.relation_type == RelationType.CLOSE_FRIEND:
            suggestions.append("Introduce a major life event that affects both")
            suggestions.append("Explore deeper emotional territory")
            suggestions.append("Consider evolving to romantic relationship or lifelong friendship")

        elif current.relation_type == RelationType.LOVER:
            suggestions.append("Introduce relationship challenges or external obstacles")
            suggestions.append("Deepen emotional intimacy through shared experiences")
            suggestions.append("Explore commitment or future planning")

        elif current.relation_type == RelationType.ENEMY:
            suggestions.append("Create a conflict or confrontation scene")
            suggestions.append("Explore the root cause of their enmity")
            suggestions.append("Consider a path to reconciliation or escalation")

        elif current.relation_type == RelationType.RIVAL:
            suggestions.append("Create a competitive situation")
            suggestions.append("Explore mutual respect despite rivalry")
            suggestions.append("Consider evolving to friendship or deeper conflict")

        elif current.relation_type == RelationType.FAMILY:
            suggestions.append("Explore family dynamics and history")
            suggestions.append("Introduce family conflict or bonding moment")
            suggestions.append("Develop their unique family relationship")

        # 根据趋势给建议
        if trend == RelationshipTrend.IMPROVING:
            suggestions.append("Continue the positive momentum with meaningful interactions")
            suggestions.append("Consider a milestone moment in their relationship")

        elif trend == RelationshipTrend.DETERIORATING:
            suggestions.append("Address the underlying issues causing the decline")
            suggestions.append("Create a turning point: reconciliation or final break")

        elif trend == RelationshipTrend.VOLATILE:
            suggestions.append("Stabilize the relationship or embrace the dramatic tension")
            suggestions.append("Explore why their relationship is so unstable")

        # 共同连接建议
        if len(common) > 3:
            suggestions.append(f"Leverage their {len(common)} mutual connections for plot development")

        return suggestions
