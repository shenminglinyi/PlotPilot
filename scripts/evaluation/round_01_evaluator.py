"""第1轮迭代评测：扩充测试用例覆盖度 + 新增边界测试

目标：
1. 每个守门人至少增加5个边界测试用例
2. 覆盖误报(False Positive)和漏报(False Negative)场景
3. 检测守门人的鲁棒性
"""
from __future__ import annotations

import json
import sys
import os
import logging
from typing import Dict, Any, List, Tuple

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))

from engine.application.quality_guardrails.language_style_guardrail import (
    LanguageStyleGuardrail, StyleViolation,
)
from engine.application.quality_guardrails.character_consistency_guardrail import (
    CharacterConsistencyGuardrail, ConsistencyViolation,
)
from engine.application.quality_guardrails.plot_density_guardrail import (
    PlotDensityGuardrail, DensityViolation,
)
from engine.application.quality_guardrails.naming_guardrail import NamingGuardrail
from engine.application.quality_guardrails.viewpoint_guardrail import ViewpointGuardrail
from engine.application.quality_guardrails.rhythm_guardrail import RhythmGuardrail
from engine.domain.value_objects.character_mask import CharacterMask

logger = logging.getLogger(__name__)


class Round1Evaluator:
    """第1轮：扩充测试用例覆盖度"""

    def __init__(self):
        self.style = LanguageStyleGuardrail()
        self.consistency = CharacterConsistencyGuardrail()
        self.density = PlotDensityGuardrail()
        self.naming = NamingGuardrail()
        self.viewpoint = ViewpointGuardrail()
        self.rhythm = RhythmGuardrail()
        self.results = {"total": 0, "passed": 0, "failed": 0, "details": []}

    def _record(self, name: str, passed: bool, expected: Any, actual: Any, extra: str = ""):
        self.results["total"] += 1
        if passed:
            self.results["passed"] += 1
        else:
            self.results["failed"] += 1
        self.results["details"].append({
            "name": name,
            "passed": passed,
            "expected": expected,
            "actual": actual,
            "extra": extra,
        })

    # ===== 语言风格守门人 - 边界测试 =====
    def test_style_boundaries(self):
        """语言风格守门人边界测试"""
        print("\n--- 语言风格守门人 边界测试 ---")

        # 测试1: 微妙八股文 - 更隐蔽的模板化结构
        score, violations = self.style.check("他先是感到一阵困惑，随后便是愤怒，最终归于平静。")
        types = [v.violation_type for v in violations]
        # "先是...随后...最终" 是隐性的三段式，但当前模式可能未覆盖
        self._record("风格_隐性三段式", "eight_legs" in types or score < 1.0,
                     "eight_legs或score<1.0", f"types={types}, score={score}")

        # 测试2: 轻度数字比喻 - 只有一个明喻（应允许）
        score, violations = self.style.check("她笑起来像春天的风，让人心旷神怡。")
        types = [v.violation_type for v in violations]
        self._record("风格_单次明喻允许", "number_metaphor" not in types,
                     "不应报number_metaphor", f"types={types}")

        # 测试3: 多个明喻堆叠（应报违规）
        score, violations = self.style.check(
            "她的笑容像春天的阳光一样温暖，声音仿佛山泉一般清脆，"
            "眼神犹如星空般深邃。这种如同梦境似幻的感觉让人陶醉。"
        )
        types = [v.violation_type for v in violations]
        self._record("风格_明喻堆叠违规", "number_metaphor" in types,
                     "number_metaphor", f"types={types}")

        # 测试4: 正常文学性描写（不应误报）
        score, violations = self.style.check(
            "他站在那里，像是被钉住了一样。不是因为恐惧，而是因为认出了那张脸。"
        )
        types = [v.violation_type for v in violations]
        self._record("风格_正常文学描写不误报", "eight_legs" not in types and "detour" not in types,
                     "不应报eight_legs或detour", f"types={types}")

        # 测试5: 过度理性变体 - 情绪场景中突然理性分析
        score, violations = self.style.check(
            "看着她的背影消失在雨中，他开始评估自己在这段关系中的投入与回报是否成正比。"
        )
        types = [v.violation_type for v in violations]
        self._record("风格_情绪场景理性分析", "over_rational" in types,
                     "over_rational", f"types={types}")

        # 测试6: 拐弯描写变体
        score, violations = self.style.check(
            "一种无法言喻的、从心底深处涌上来的、仿佛要将整个人吞噬的感觉攫住了他。"
        )
        types = [v.violation_type for v in violations]
        self._record("风格_多重修饰拐弯", "detour" in types,
                     "detour", f"types={types}")

        # 测试7: 八股文总结式变体
        score, violations = self.style.check("综上所述，这次失败给了他深刻的教训。")
        types = [v.violation_type for v in violations]
        self._record("风格_总结式八股", "eight_legs" in types,
                     "eight_legs", f"types={types}")

    # ===== 角色一致性守门人 - 边界测试 =====
    def test_consistency_boundaries(self):
        """角色一致性守门人边界测试"""
        print("\n--- 角色一致性守门人 边界测试 ---")

        # 创建测试面具
        warrior_mask = CharacterMask(
            character_id="warrior",
            name="赵铁",
            core_belief="强者为尊，弱者不配活",
            moral_taboos=["绝不向任何人下跪"],
            voice_style="粗暴",
            sentence_pattern="陈述",
            active_wounds=[
                {"description": "幼年目睹母亲被杀", "trigger": "看到女性遇险", "effect": "失去理智暴怒"},
            ],
            chapter_number=30,
        )

        scholar_mask = CharacterMask(
            character_id="scholar",
            name="文清",
            core_belief="知识改变命运",
            voice_style="话多",
            sentence_pattern="反问",
            active_wounds=[],
            chapter_number=20,
        )

        # 测试1: OOC - 强者为尊角色示弱
        score, violations = self.consistency.check(
            "赵铁在对手面前退缩了，他害怕得直发抖。",
            {"warrior": warrior_mask}
        )
        types = [v.violation_type for v in violations]
        self._record("一致_强者信念退缩", "ooc" in types,
                     "ooc", f"types={types}")

        # 测试2: OOC - 信念冲突但行为表面合理
        score, violations = self.consistency.check(
            "赵铁表面退缩，实际上是在寻找对方的破绽。",
            {"warrior": warrior_mask}
        )
        types = [v.violation_type for v in violations]
        self._record("一致_表面退缩暗中设防", score >= 0.8,
                     "score>=0.8", f"score={score}, types={types}")

        # 测试3: 创伤反应 - 女性遇险场景无反应
        score, violations = self.consistency.check(
            "一个女人在他面前被打倒在地，赵铁转过身继续喝酒，没有任何反应。",
            {"warrior": warrior_mask}
        )
        types = [v.violation_type for v in violations]
        self._record("一致_创伤触发无反应", "wound_trigger_miss" in types,
                     "wound_trigger_miss", f"types={types}")

        # 测试4: 语言指纹 - 话多角色说太短
        score, violations = self.consistency.check(
            "文清\u201c嗯。\u201d",
            {"scholar": scholar_mask}
        )
        types = [v.violation_type for v in violations]
        self._record("一致_话多角色短句", "voice_mismatch" in types,
                     "voice_mismatch", f"types={types}")

        # 测试5: 语言指纹 - 话多角色说长句（应通过）
        score, violations = self.consistency.check(
            "文清\u201c这件事说来话长，你且听我细细道来，其中缘由曲折离奇，非三言两语能说清。\u201d",
            {"scholar": scholar_mask}
        )
        types = [v.violation_type for v in violations]
        self._record("一致_话多角色长句通过", "voice_mismatch" not in types,
                     "不应报voice_mismatch", f"types={types}")

        # 测试6: 多角色混合同一文本
        mixed_masks = {"warrior": warrior_mask, "scholar": scholar_mask}
        score, violations = self.consistency.check(
            "赵铁毫不犹豫地相信了对方的话。文清\u201c嗯。\u201d",
            mixed_masks
        )
        types = [v.violation_type for v in violations]
        self._record("一致_多角色混合检测", len(types) >= 1,
                     "至少1个违规", f"found {len(types)} violations: {types}")

    # ===== 情节密度守门人 - 边界测试 =====
    def test_density_boundaries(self):
        """情节密度守门人边界测试"""
        print("\n--- 情节密度守门人 边界测试 ---")

        # 测试1: 风景描写但有叙事功能（应通过）
        score, violations = self.density.check(
            "远处的山峰突然崩塌，碎石滚落的轰鸣声越来越近。"
            "他拉起她的手就跑——如果被碎石追上，两个人都得死。"
        )
        types = [v.violation_type for v in violations]
        self._record("密度_风景但有叙事功能", "no_goal_progression" not in types,
                     "不应报no_goal_progression", f"types={types}")

        # 测试2: 长段落纯情感独白无事件
        score, violations = self.density.check(
            "他感到内心深处涌起一股莫名的情绪，"
            "这情绪如同潮水般不可阻挡，将他的理智一点点淹没。"
            "他想起了过去种种，那些快乐与悲伤交织的时光，"
            "那些无法回去的日子，那些再也见不到的人。"
            "他觉得自己像是站在一个十字路口，"
            "每条路都通向不同的方向，而他不知道该选哪一条。"
        )
        types = [v.violation_type for v in violations]
        self._record("密度_纯情感独白无事件", "no_goal_progression" in types or "low_info_density" in types,
                     "no_goal_progression或low_info_density", f"types={types}")

        # 测试3: 极短文本（应不报密度问题）
        score, violations = self.density.check("他走了。")
        types = [v.violation_type for v in violations]
        self._record("密度_极短文本不误报", len(types) == 0,
                     "无违规", f"types={types}")

        # 测试4: 高密度文本（对话+动作+发现）
        score, violations = self.density.check(
            "\u201c你杀了他们。\u201d他拔出剑，剑尖指向对方的咽喉。"
            "\u201c我没有。\u201d她后退一步，却撞上了身后的墙壁。"
            "他发现了她袖口上的血迹——那不是她的血。"
        )
        types = [v.violation_type for v in violations]
        self._record("密度_高密度文本通过", "no_goal_progression" not in types and "low_info_density" not in types,
                     "不应报no_goal或low_density", f"types={types}")

        # 测试5: 填充词堆叠
        score, violations = self.density.check(
            "他似乎仿佛好像大概看到了一个身影，"
            "不由得忍不住情不自禁下意识地轻轻缓缓微微地后退了一步。"
            "非常十分极其格外特别安静的环境中，"
            "他默默地轻轻地缓缓地叹了一口气。"
        )
        types = [v.violation_type for v in violations]
        self._record("密度_填充词堆叠", "non_functional_adj" in types,
                     "non_functional_adj", f"types={types}")

    # ===== 命名守门人 - 边界测试 =====
    def test_naming_boundaries(self):
        """命名守门人边界测试"""
        print("\n--- 命名守门人 边界测试 ---")

        # 测试1: 陈旧姓氏
        score, violations = self.naming.check(["林风"], era="ancient")
        types = [v.violation_type for v in violations]
        self._record("命名_陈旧姓氏林风", "cliche_surname" in types,
                     "cliche_surname", f"types={types}")

        # 测试2: 时代错位名字
        score, violations = self.naming.check(["赵建国"], era="ancient")
        types = [v.violation_type for v in violations]
        self._record("命名_古代叫建国", "era_mismatch" in types,
                     "era_mismatch", f"types={types}")

        # 测试3: 正常有内涵的名字
        score, violations = self.naming.check(["苏晚卿"], era="ancient")
        self._record("命名_正常古代名字", score >= 0.8,
                     "score>=0.8", f"score={score}")

        # 测试4: 现代名字用于现代场景（应通过）
        score, violations = self.naming.check(["陈思远"], era="modern")
        self._record("命名_现代场景现代名", score >= 0.8,
                     "score>=0.8", f"score={score}")

        # 测试5: 复姓推荐
        score, violations = self.naming.check(["李风"], era="ancient")
        types = [v.violation_type for v in violations]
        self._record("命名_两字名复姓推荐", "cliche_surname" in types or "missing_compound_surname" in types,
                     "cliche或compound推荐", f"types={types}")

    # ===== 视角守门人 - 边界测试 =====
    def test_viewpoint_boundaries(self):
        """视角守门人边界测试"""
        print("\n--- 视角守门人 边界测试 ---")

        # 测试1: 限制性第三人称 - 不应知道他人内心
        score, violations = self.viewpoint.check(
            "林羽看着远处的敌人，心中盘算着对策。"
            "而对面的张将军心里想着：这个年轻人不简单。",
            scene_info={
                "viewpoint_character": "林羽",
                "characters_present": ["林羽", "张将军"],
                "key_event": "对峙",
                "information_asymmetry": {
                    "林羽": {"known_facts": ["敌人来了"]},
                    "张将军": {"known_facts": ["年轻人不简单", "已设埋伏"]},
                },
            }
        )
        types = [v.violation_type for v in violations]
        self._record("视角_视角泄露", "viewpoint_leak" in types or "suboptimal_viewpoint" in types,
                     "viewpoint_leak或suboptimal_viewpoint", f"types={types}, score={score}")

        # 测试2: 伏笔绑定层级不足
        score, violations = self.viewpoint.check(
            "测试文本",
            scene_info={"viewpoint_character": "林羽", "characters_present": ["林羽"]},
            foreshadows=[
                {"description": "灭门真相", "emotional_weight": 0.9, "binding_level": 1},
            ]
        )
        types = [v.violation_type for v in violations]
        self._record("视角_伏笔绑定层级不足", "weak_binding" in types,
                     "weak_binding", f"types={types}")

        # 测试3: 伏笔绑定层级足够
        score, violations = self.viewpoint.check(
            "测试文本",
            scene_info={"viewpoint_character": "林羽", "characters_present": ["林羽"]},
            foreshadows=[
                {"description": "灭门真相", "emotional_weight": 0.9, "binding_level": 3},
            ]
        )
        types = [v.violation_type for v in violations]
        self._record("视角_伏笔绑定层级足够", "weak_binding" not in types,
                     "不应报weak_binding", f"types={types}")

    # ===== 节奏守门人 - 边界测试 =====
    def test_rhythm_boundaries(self):
        """节奏守门人边界测试"""
        print("\n--- 节奏守门人 边界测试 ---")

        # 测试1: 动作场景应简洁
        score, violations = self.rhythm.check(
            "他一拳打过去，对方侧身闪避，紧接着一个回旋踢直奔面门。"
            "他向后翻滚卸力，单手撑地弹起，剑已出鞘。",
            scene_type="action",
        )
        self._record("节奏_动作场景简洁", score >= 0.5,
                     "score>=0.5", f"score={score}")

        # 测试2: 动作场景臃肿（长句太多）
        score, violations = self.rhythm.check(
            "他在心中飞速地权衡了各种可能性之后，以一个极其华丽的旋转姿势挥出了那把跟随他多年的长剑，"
            "剑光在月光下闪烁出耀眼的光芒，如同银河倾泻而下一般壮观，"
            "对方则以一种优雅而不失力量感的方式侧身闪避了这凌厉的一击。",
            scene_type="action",
        )
        types = [v.violation_type for v in violations]
        self._record("节奏_动作场景臃肿", "action_bloat" in types,
                     "action_bloat", f"types={types}")

        # 测试3: 揭秘场景仓促
        score, violations = self.rhythm.check(
            "真相是他杀了自己的父亲。",
            scene_type="reveal",
        )
        types = [v.violation_type for v in violations]
        self._record("节奏_揭秘仓促", "reveal_rush" in types,
                     "reveal_rush", f"types={types}")

        # 测试4: 揭秘场景有铺垫
        score, violations = self.rhythm.check(
            "他沉默了很久。手指一遍遍摩挲着那封信的边缘，纸已经被汗水洇湿了。"
            "屋外的雨声忽大忽小，像是在催促他。他终于开口了："
            "\u201c真相是——他杀了自己的父亲。\u201d",
            scene_type="reveal",
        )
        self._record("节奏_揭秘有铺垫", score >= 0.5,
                     "score>=0.5", f"score={score}")

        # 测试5: 大事件跑偏
        score, violations = self.rhythm.check(
            "决战开始了。将军却在一旁喝茶，悠闲地赏着城外的花。",
            scene_type="major_event",
        )
        types = [v.violation_type for v in violations]
        self._record("节奏_大事件跑偏", "event_detour" in types,
                     "event_detour", f"types={types}")

    def run(self) -> Dict[str, Any]:
        """运行第1轮评测"""
        print("=" * 60)
        print("第1轮迭代评测：扩充测试用例覆盖度 + 边界测试")
        print("=" * 60)

        self.test_style_boundaries()
        self.test_consistency_boundaries()
        self.test_density_boundaries()
        self.test_naming_boundaries()
        self.test_viewpoint_boundaries()
        self.test_rhythm_boundaries()

        # 汇总
        print(f"\n{'='*60}")
        print(f"第1轮结果: 总计 {self.results['total']}, "
              f"通过 {self.results['passed']}, "
              f"失败 {self.results['failed']}")
        if self.results['total'] > 0:
            print(f"通过率: {self.results['passed']/self.results['total']:.1%}")
        print(f"{'='*60}")

        # 打印失败详情
        failed = [d for d in self.results["details"] if not d["passed"]]
        if failed:
            print("\n失败项:")
            for f in failed:
                print(f"  X {f['name']}: 期望={f['expected']}, 实际={f['actual']}")

        return self.results


if __name__ == "__main__":
    evaluator = Round1Evaluator()
    results = evaluator.run()
