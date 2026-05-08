#!/usr/bin/env python3
"""
简化的节拍连贯性测试

验证优化后的连贯性效果
"""

import sys
import os

# 添加项目根目录到Python路径
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from application.engine.services.beat_coherence_enhancer import BeatCoherenceEnhancer

def test_character_extraction():
    """测试角色提取功能"""
    enhancer = BeatCoherenceEnhancer()
    
    test_contents = [
        "李明站在窗前，望着远处的天空。他皱着眉头思考着。",
        "王小华走了进来：'你找我有什么事吗？'",
        "张小红心想这件事情应该怎么办。",
        "老朋友陈大明从远方赶来。"
    ]
    
    for i, content in enumerate(test_contents, 1):
        characters = enhancer._extract_characters(content)
        print(f"测试内容 {i}: {content}")
        print(f"提取的角色: {characters}")
        print()

def test_coherence_scenarios():
    """测试各种连贯性场景"""
    enhancer = BeatCoherenceEnhancer()
    
    # 场景1：正常连贯的节拍
    beat1_content = "李明坐在咖啡厅里，轻轻搅动着咖啡。他皱着眉头，似乎在思考什么。"
    beat2_content = "突然，李明站起身，决定现在就去找王小华问个清楚。"
    
    context1 = enhancer.analyze_beat_context(beat1_content, "sensory")
    context2 = enhancer.analyze_beat_context(beat2_content, "action")
    
    print("场景1：正常连贯的节拍")
    print(f"节拍1: {beat1_content}")
    print(f"分析: 角色={context1.characters}, 场景={context1.scene}, 情绪={context1.mood}")
    print(f"节拍2: {beat2_content}")
    print(f"分析: 角色={context2.characters}, 场景={context2.scene}, 情绪={context2.mood}")
    
    issues = enhancer.check_coherence_between_beats(beat1_content, beat2_content, context1, context2)
    print(f"连贯性问题: {len(issues)} 个")
    for issue in issues:
        print(f"  - {issue.type}: {issue.description}")
    print()
    
    # 场景2：可能出现问题的节拍
    beat3_content = "李明坐在咖啡厅里，轻轻搅动着咖啡。"
    beat4_content = "张小红在公园里跑步，呼吸着新鲜空气。"
    
    context3 = enhancer.analyze_beat_context(beat3_content, "sensory")
    context4 = enhancer.analyze_beat_context(beat4_content, "action")
    
    print("场景2：可能出现连贯性问题的节拍")
    print(f"节拍3: {beat3_content}")
    print(f"分析: 角色={context3.characters}, 场景={context3.scene}, 情绪={context3.mood}")
    print(f"节拍4: {beat4_content}")
    print(f"分析: 角色={context4.characters}, 场景={context4.scene}, 情绪={context4.mood}")
    
    issues = enhancer.check_coherence_between_beats(beat3_content, beat4_content, context3, context4)
    print(f"连贯性问题: {len(issues)} 个")
    for issue in issues:
        print(f"  - {issue.type}: {issue.description}")
    print()
    
    # 生成连贯性指导
    instructions = enhancer.generate_coherence_instructions(
        previous_content=beat3_content,
        current_beat_description="切换到另一个角色的情节",
        previous_context=context3,
        beat_index=1,
        total_beats=2
    )
    print("节拍4的连贯性指导:")
    print(instructions)

def main():
    print("节拍连贯性优化测试")
    print("=" * 50)
    
    test_character_extraction()
    test_coherence_scenarios()
    
    print("\n✅ 测试完成！")
    print("\n优化要点总结:")
    print("1. 🧠 新增BeatCoherenceEnhancer模块分析节拍上下文")
    print("2. 📝 在Prompt中增加连贯性要求和过渡指导")
    print("3. ⚙️ 调整ChapterConductor减少过度压缩")
    print("4. 🔗 增强SoftLanding的上下文关联")
    print("5. 🔄 全程追踪节拍间的人物、场景、情绪连贯")

if __name__ == "__main__":
    main()