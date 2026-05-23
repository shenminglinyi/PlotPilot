from types import SimpleNamespace

from application.world.services.narrative_promise import (
    build_narrative_promise_block,
    extract_narrative_promise,
)


def test_extract_narrative_promise_strips_internal_header_and_keeps_conflict():
    premise = """【系统内部·叙事结构规划（勿向读者展示）】
规划目标体量：约 1,000,000 字。

【类型：仙侠 / 古典仙侠】

核心冲突：芦沉舟打破灵根垄断 vs 仙盟与天道法则
开篇钩子：矿洞坍塌后获得无根仙体碎片
"""

    promise = extract_narrative_promise("我不是剑仙", premise)

    assert promise.title == "我不是剑仙"
    assert promise.genre_signal == "仙侠 / 古典仙侠"
    assert "灵根垄断" in promise.core_conflict
    assert "无根仙体" in promise.opening_hook
    assert "无根仙体" in promise.promise_keywords


def test_build_narrative_promise_block_keeps_opening_from_full_resolution():
    novel = SimpleNamespace(
        title="我不是剑仙",
        premise="核心冲突：无根仙体挑战灵根枷锁\n开篇钩子：矿洞中发现天道骗局",
    )

    block = build_narrative_promise_block(novel, chapter_number=8)

    assert "叙事承诺锁" in block
    assert "前12章" in block
    assert "彻底平反" in block
    assert "反命题" in block
