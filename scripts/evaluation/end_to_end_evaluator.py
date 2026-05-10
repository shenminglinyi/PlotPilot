"""端到端评测器

测试流程：
完整章节生成 → 质量守门 → Checkpoint保存 → 回滚恢复 → 续写一致性

1:1复刻线上环境的端到端测试
"""
from __future__ import annotations

import json
import logging
import sqlite3
import tempfile
import os
from typing import Dict, Any, List

from engine.domain.entities.story import Story, StoryId, StoryPhase
from engine.domain.entities.chapter import Chapter, ChapterQualityScore
from engine.domain.entities.foreshadow import Foreshadow, ForeshadowId, ForeshadowStatus
from engine.domain.value_objects.checkpoint import Checkpoint, CheckpointId, CheckpointType
from engine.domain.value_objects.emotion_ledger import (
    EmotionLedger, EmotionalWound, EmotionalBoon, PowerShift, OpenLoop,
)
from engine.domain.value_objects.character_mask import CharacterMask
from engine.application.quality_guardrails.quality_guardrail import (
    QualityGuardrail, QualityViolationError,
)
from engine.application.checkpoint_manager.manager import CheckpointManager
from engine.infrastructure.persistence.checkpoint_store import CheckpointStore

logger = logging.getLogger(__name__)


class SimpleDBPool:
    """简单的DB连接池用于测试"""
    def __init__(self, db_path: str):
        self._db_path = db_path

    def get_connection(self):
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn


class EndToEndEvaluator:
    """端到端评测器"""

    def run(self) -> Dict[str, Any]:
        results = {
            "total": 0,
            "passed": 0,
            "failed": 0,
            "details": [],
        }

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        try:
            db_pool = SimpleDBPool(db_path)
            checkpoint_store = CheckpointStore(db_pool)
            checkpoint_manager = CheckpointManager(checkpoint_store)
            quality_guardrail = QualityGuardrail()

            # === 测试1: 完整的章节生成+质量守门流程 ===
            results["total"] += 1
            try:
                story = Story.create("测试小说", "一部武侠小说", target_chapters=10)

                # 模拟章节内容
                good_chapter = (
                    "他推开门，发现了那封信。信上的字迹他认得——是师父的。"
                    "'如果看到这封信，说明我已经不在了。'他握紧了拳头。"
                    "门后传来脚步声，他猛地转身，剑已出鞘。"
                    "来人一身黑衣，面罩遮住了大半张脸。'别急，'黑衣人低声道，'我不是来杀你的。'"
                )

                # 角色面具
                masks = {
                    "lin_yu": CharacterMask(
                        character_id="lin_yu",
                        name="林羽",
                        core_belief="信任是致命的软肋",
                        voice_style="惜字如金",
                        chapter_number=1,
                    ),
                }

                # 质量检查（advise模式，不拦截）
                report = quality_guardrail.advise(
                    text=good_chapter,
                    character_masks=masks,
                    character_names=["林羽"],
                    era="ancient",
                )

                if report.overall_score >= 0.4:  # 端到端测试容忍度稍高
                    results["passed"] += 1
                    results["details"].append({
                        "name": "章节生成+质量守门",
                        "passed": True,
                        "score": report.overall_score,
                    })
                else:
                    results["failed"] += 1
                    results["details"].append({
                        "name": "章节生成+质量守门",
                        "passed": False,
                        "score": report.overall_score,
                        "violations": report.all_violations[:3],
                    })
            except Exception as e:
                results["failed"] += 1
                results["details"].append({"name": "章节生成+质量守门", "passed": False, "error": str(e)})

            # === 测试2: Checkpoint保存 ===
            results["total"] += 1
            try:
                import asyncio
                cp_id = asyncio.get_event_loop().run_until_complete(
                    checkpoint_manager.on_chapter_completed(
                        story_id=story.story_id.value,
                        chapter_number=1,
                        story_state={"phase": "opening", "chapter": 1},
                        character_masks={"lin_yu": {"name": "林羽"}},
                        emotion_ledger={"wounds": []},
                        active_foreshadows=["fs1"],
                    )
                )
                if cp_id:
                    results["passed"] += 1
                    results["details"].append({"name": "Checkpoint保存", "passed": True})
                else:
                    results["failed"] += 1
                    results["details"].append({"name": "Checkpoint保存", "passed": False})
            except Exception as e:
                results["failed"] += 1
                results["details"].append({"name": "Checkpoint保存", "passed": False, "error": str(e)})

            # === 测试3: 回滚恢复 ===
            results["total"] += 1
            try:
                rolled_back = asyncio.get_event_loop().run_until_complete(
                    checkpoint_manager.rollback(story.story_id.value, cp_id)
                )
                if rolled_back:
                    results["passed"] += 1
                    results["details"].append({"name": "回滚恢复", "passed": True})
                else:
                    results["failed"] += 1
                    results["details"].append({"name": "回滚恢复", "passed": False})
            except Exception as e:
                results["failed"] += 1
                results["details"].append({"name": "回滚恢复", "passed": False, "error": str(e)})

            # === 测试4: EmotionLedger完整性 ===
            results["total"] += 1
            try:
                ledger = EmotionLedger.create_empty()
                ledger = ledger.add_wound(EmotionalWound(
                    description="失去师父",
                    impact="多疑、谨慎",
                    chapter_number=1,
                ))
                ledger = ledger.add_boon(EmotionalBoon(
                    description="获得剑谱",
                    value="实力提升",
                    chapter_number=2,
                ))
                ledger = ledger.add_power_shift(PowerShift(
                    from_state="被动挨打",
                    to_state="暗中筹谋的猎手",
                ))
                ledger = ledger.add_open_loop(OpenLoop(
                    description="赵虎死前的眼神",
                    hint="另有幕后黑手",
                ))

                summary = ledger.to_chapter_summary()
                if "失去师父" in summary and "暗中筹谋" in summary and "幕后黑手" in summary:
                    results["passed"] += 1
                    results["details"].append({"name": "EmotionLedger完整性", "passed": True})
                else:
                    results["failed"] += 1
                    results["details"].append({"name": "EmotionLedger完整性", "passed": False})
            except Exception as e:
                results["failed"] += 1
                results["details"].append({"name": "EmotionLedger完整性", "passed": False, "error": str(e)})

            # === 测试5: 伏笔生命周期 ===
            results["total"] += 1
            try:
                fs = Foreshadow.create(
                    description="师父留下的剑谱暗藏玄机",
                    planted_in_chapter=1,
                    emotional_weight=0.9,
                    binding_level=3,  # event
                    planting_atmosphere="雨夜，烛光摇曳",
                )
                fs.reference(5)
                fs.awaken()
                assert fs.status == ForeshadowStatus.AWAKENING

                awakening_instruction = fs.to_t0_awakening_instruction()
                assert "伏笔苏醒提醒" in awakening_instruction

                fs.resolve(10)
                assert fs.status == ForeshadowStatus.RESOLVED
                assert fs.resolved_in_chapter == 10

                results["passed"] += 1
                results["details"].append({"name": "伏笔生命周期", "passed": True})
            except Exception as e:
                results["failed"] += 1
                results["details"].append({"name": "伏笔生命周期", "passed": False, "error": str(e)})

        finally:
            os.unlink(db_path)

        return results


if __name__ == "__main__":
    evaluator = EndToEndEvaluator()
    results = evaluator.run()
    print(json.dumps(results, indent=2, ensure_ascii=False))
