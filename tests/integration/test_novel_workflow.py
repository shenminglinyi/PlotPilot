"""端到端集成测试 - Novel 工作流

注意：此测试引用已废弃的 FileNovelRepository 和 FileChapterRepository。
这些仓储已被 SQLite 实现替代，此测试已禁用。
如需恢复，请更新为使用 SQLite 仓储。
"""
import pytest

@pytest.mark.skip(reason="废弃的测试：FileNovelRepository/FileChapterRepository 已被 SQLite 实现替代")
def test_novel_workflow_skip_placeholder():
    pass
