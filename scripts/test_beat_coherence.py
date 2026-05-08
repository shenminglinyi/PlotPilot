#!/usr/bin/env python3
"""
节拍连贯性测试脚本

用于测试和验证节拍连贯性优化的效果
"""

import asyncio
import logging
import sys
import os
from typing import List

# 添加项目根目录到Python路径
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from application.engine.services.beat_coherence_enhancer import BeatCoherenceEnhancer, BeatContext

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def test_coherence_enhancer():
    """测试节拍连贯性增强器的基础功能"""
    enhancer = BeatCoherenceEnhancer()
    
    # 测试1: 分析节拍上下文
    test_content1 = "李明站在窗前，望着远处的天空。他皱着眉头，似乎在思考什么重要的事情。"
    test_content2 = "突然，他转身快步走向门口，用力推开门走了出去。"
    
    context1 = enhancer.analyze_beat_context(test_content1, "sensory")
    context2 = enhancer.analyze_beat_context(test_content2, "action")
    
    logger.info(f"测试1 - 节拍1上下文: 角色={context1.characters}, 场景={context1.scene}, 情绪={context1.mood}")
    logger.info(f"测试1 - 节拍2上下文: 角色={context2.characters}, 场景={context2.scene}, 情绪={context2.mood}")
    
    # 测试2: 检查连贯性
    issues = enhancer.check_coherence_between_beats(test_content1, test_content2, context1, context2)
    logger.info(f"测试2 - 连贯性问题: {len(issues)} 个")
    for issue in issues:
        logger.info(f"  - {issue.type}: {issue.description} (严重度: {issue.severity})")
    
    # 测试3: 生成连贯性指导
    instructions = enhancer.generate_coherence_instructions(
        previous_content=test_content1,
        current_beat_description="角色快速行动，从思考转为行动",
        previous_context=context1,
        beat_index=1,
        total_beats=3
    )
    logger.info(f"测试3 - 连贯性指导:\n{instructions}")

def test_sample_beats():
    """使用示例节拍内容测试连贯性分析"""
    enhancer = BeatCoherenceEnhancer()
    
    # 示例节拍内容
    sample_beats = [
        {
            "content": "夜幕降临，王小明独自一人坐在咖啡厅的角落。温暖的灯光洒在他的脸上，映出一丝疲惫。他轻轻搅动着已经凉了的咖啡，思绪飘向远方。",
            "focus": "sensory",
            "description": "主角在咖啡厅沉思，营造孤寂氛围"
        },
        {
            "content": "突然，门铃响起，一个熟悉的身影走了进来。是李小红，她穿着红色的外套，脸上带着微笑。小明抬起头，眼中闪过一丝惊讶。",
            "focus": "dialogue",
            "description": "重要角色登场，打破主角的孤独"
        },
        {
            "content": "他们开始交谈，声音低沉而急促。小红似乎在传达什么重要的消息，小明的表情逐渐变得严肃。",
            "focus": "dialogue", 
            "description": "角色间紧张对话，推进情节发展"
        }
    ]
    
    logger.info("开始分析示例节拍的连贯性...")
    
    previous_context = None
    previous_content = ""
    
    for i, beat in enumerate(sample_beats):
        content = beat["content"]
        focus = beat["focus"]
        description = beat["description"]
        
        logger.info(f"\n节拍 {i+1}: {description}")
        
        # 分析当前节拍的上下文
        current_context = enhancer.analyze_beat_context(content, focus)
        logger.info(f"上下文分析: 角色={current_context.characters}, 场景={current_context.scene}, 情绪={current_context.mood}")
        
        # 如果是第二个及以后的节拍，检查与前一个节拍的连贯性
        if previous_context:
            issues = enhancer.check_coherence_between_beats(
                previous_content, content, previous_context, current_context
            )
            
            if issues:
                logger.info(f"发现连贯性问题 ({len(issues)} 个):")
                for issue in issues:
                    logger.warning(f"  [{issue.severity}] {issue.type}: {issue.description}")
            else:
                logger.info("✓ 节拍间连贯性良好")
        
        previous_context = current_context
        previous_content = content
        
        # 为下一个节拍生成连贯性指导（如果有下一个节拍）
        if i < len(sample_beats) - 1:
            next_beat_desc = sample_beats[i+1]["description"]
            instructions = enhancer.generate_coherence_instructions(
                previous_content=content,
                current_beat_description=next_beat_desc,
                previous_context=current_context,
                beat_index=i+1,
                total_beats=len(sample_beats)
            )
            logger.debug(f"下一节拍的连贯性指导:\n{instructions}")

def demonstrate_coherence_improvement():
    """展示连贯性改进的效果（概念验证）"""
    logger.info("\n" + "="*60)
    logger.info("节拍连贯性优化演示")
    logger.info("="*60)
    
    enhancer = BeatCoherenceEnhancer()
    
    # 原始版（有连贯性问题）
    logger.info("\n📖 原始版本（存在连贯性问题）:")
    logger.info("节拍1: 李明在办公室工作到深夜。")
    logger.info("节拍2: 张华在公园里晨跑。")  # 场景和人物突然跳跃
    logger.info("节拍3: 会议室里大家激烈争论。")  # 缺乏过渡
    
    # 分析问题
    beats_content = [
        "李明在办公室工作到深夜，电脑屏幕的光映在他的脸上。",
        "张华在公园里晨跑，清新的空气让他感到精神焕发。",
        "会议室里大家激烈争论，气氛十分紧张。"
    ]
    
    contexts = []
    for i, content in enumerate(beats_content):
        context = enhancer.analyze_beat_context(content, "narrative")
        contexts.append(context)
        logger.info(f"节拍{i+1}分析: 角色={context.characters}, 场景={context.scene}")
    
    # 检查连贯性问题
    for i in range(1, len(beats_content)):
        issues = enhancer.check_coherence_between_beats(
            beats_content[i-1], beats_content[i], contexts[i-1], contexts[i]
        )
        if issues:
            logger.warning(f"节拍{i+1}的问题: {[issue.description for issue in issues]}")
    
    # 展示改进版本
    logger.info("\n✨ 优化版本（提供连贯性指导）:")
    
    for i in range(1, len(beats_content)):
        instructions = enhancer.generate_coherence_instructions(
            previous_content=beats_content[i-1],
            current_beat_description=f"节拍{i+1}的情节发展",
            previous_context=contexts[i-1],
            beat_index=i,
            total_beats=len(beats_content)
        )
        
        logger.info(f"\n节拍{i+1}的连贯性指导:")
        logger.info(f"  - 需要处理前文中的情节线索")
        logger.info(f"  - 保持人物和场景的连续性")
        logger.info(f"  - 提供合理的过渡")

async def main():
    """主测试函数"""
    logger.info("开始节拍连贯性测试...")
    
    try:
        # 运行基础测试
        test_coherence_enhancer()
        
        # 运行示例测试
        test_sample_beats()
        
        # 展示改进效果
        demonstrate_coherence_improvement()
        
        logger.info("\n✅ 所有测试完成！")
        logger.info("\n优化总结:")
        logger.info("1. 🔍 智能分析节拍间的情节连贯性")
        logger.info("2. ⚠️ 自动检测潜在的连贯性问题")
        logger.info("3. 📝 为LLM提供具体的连贯性写作指导")
        logger.info("4. 🎯 减少场景跳跃和人物断裂")
        
    except Exception as e:
        logger.error(f"测试过程中出现错误: {e}", exc_info=True)

if __name__ == "__main__":
    asyncio.run(main())