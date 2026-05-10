"""跑文核心入口 — 调API生成章节 + 质量评估 + 小说家评测

使用方式:
  python scripts/evaluation/novel_writing_runner.py --chapters 5 --round 1
  python scripts/evaluation/novel_writing_runner.py --chapters 20 --round 4

核心流程:
  1. 初始化LLM服务（复用项目的DynamicLLMService）
  2. 创建Story + 角色
  3. 逐章生成 -> WritingOrchestrator质量检查 -> 保存结果
  4. 输出小说家角度评估报告
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
import time
from datetime import datetime
from typing import Dict, Any, List, Optional

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))

from engine.application.writing_orchestrator import WritingOrchestrator, ChapterResult
from engine.core.entities.story import Story, StoryPhase
from engine.core.entities.character import Character, VoiceStyle, Wound
from engine.core.value_objects.emotion_ledger import EmotionLedger

logger = logging.getLogger(__name__)

# 仙侠小说设定
PREMISE = (
    "苍穹大陆，灵气复苏。少年林羽出身寒门，幼年目睹师父被神秘势力追杀，"
    "从此心中埋下'信任是致命软肋'的信念。他带着师父留下的半卷残经踏上修行路，"
    "一路遭遇背叛与试探，却在最危险的时刻遇到永远乐观的师妹苏晚卿。"
    "两人一冷一热，在修真界的暗流中相互守护，逐渐揭开苍穹大陆隐藏的惊天秘密。"
)

OUTLINES = [
    "林羽独自走在荒原上，回忆起三年前师父的惨死。他来到一座废弃的城池，意外发现墙上刻着师父留下的暗号。暗号指向一个名字——'天机阁'。夜色降临，林羽在废墟中修炼残经，体内灵气第一次出现异动。章末钩子：远处传来脚步声，一个少女的声音响起。",
    "来人竟是苏晚卿，她自称是林羽师妹，奉师命寻找他。林羽本能地不信任她，两人在废墟中发生冲突。苏晚卿以一招'云舒掌'证明身份，这是师父独创的功法。林羽半信半疑，决定暂时同行。章末钩子：苏晚卿说出师父临终前的话——'天机阁里有答案'。",
    "两人前往天机阁，途中经过迷雾森林。林羽在森林中遇到伏击，对方使用'噬魂针'——这是师父被杀那晚看到的暗器。林羽旧伤发作，苏晚卿挺身而出用'云舒掌'击退敌人。战斗后林羽发现敌人身上有天机阁的令牌。章末钩子：天机阁为什么追杀师父，又为什么伏击他？",
    "两人抵达天机阁外围，发现这里远比想象中庞大。林羽潜入阁中，发现师父留下的半卷残经竟然是天机阁的镇阁之宝。阁中长老告诉他一个惊人真相：师父当年是天机阁叛逃的护法，带走残经是为了阻止一个更大的阴谋。章末钩子：长老说'你师父不是被杀的，他是自愿赴死'。",
    "林羽震惊之余开始修炼残经下半卷，实力突飞猛进。天机阁内部分成两派：一派要杀林羽夺回残经，一派认为林羽是命中注定的继承者。苏晚卿在暗中保护林羽，却意外被少阁主慕容霜发现。章末钩子：慕容霜对苏晚卿说'你猜，你师父为什么要让你找到他？'",
    "林羽突破修行瓶颈，残经修炼至第三重。天机阁阴谋派发动突袭，林羽在生死关头悟出'信任不是软弱，选择信任才是真正的强大'。他与苏晚卿联手击退敌人，但慕容霜在混乱中带走了残经下半卷。章末钩子：慕容霜留下一句话'三天后，天机台见，我给你看真相'。",
    "林羽内心挣扎，不确定是否该信任慕容霜。苏晚卿坚定支持他，两人决定赴约。天机台上，慕容霜展示天机阁千年秘密——苍穹大陆灵气正在枯竭，残经是重启灵脉的关键。师父当年出走，是不愿用万人性命重启灵脉。章末钩子：慕容霜问'你会选万人的生路，还是残经的安全？'",
    "林羽陷入两难。苏晚卿说出一个一直隐瞒的秘密——她身上有灵脉的钥匙，师父临终前注入她体内的。如果重启灵脉，她可能无法承受。林羽第一次握住苏晚卿的手，说'我不会让你有事'。章末钩子：窗外的月亮变成血红色——灵脉开始异动了。",
    "灵脉异动引发各地灾变，林羽必须尽快抉择。阴谋派趁乱再次攻击，目标是苏晚卿。林羽在战斗中第一次使用残经全部力量，实力达到前所未有的高度，但代价是身体开始出现灵力反噬。章末钩子：林羽的左臂开始石化——残经的诅咒。",
    "林羽左臂石化加剧，苏晚卿拼命寻找破解之法。慕容霜带来选择：如果林羽愿意用残经重启灵脉，天机阁可用禁术保住苏晚卿性命，但林羽将失去所有修为。林羽看着苏晚卿坚定的眼神，做出决定。章末钩子：灵脉重启仪式开始，但仪式中出现谁都没想到的变数。",
    "仪式被第三股势力打断——幕后黑手不是阴谋派，而是早已被认为灭绝的'噬灵族'。他们一直在暗中操控一切，目的是趁灵脉重启时吞噬全部灵气。林羽在失去修为的情况下，凭借意志力和苏晚卿的灵脉钥匙，触发残经终极奥义。章末钩子：林羽的左臂石化突然碎裂，露出金色纹路——灵脉选中者的标记。",
    "林羽觉醒灵脉选中者力量，与噬灵族首领展开决战。战斗中林羽发现噬灵族首领与师父有旧——当年正是师父封印了他。林羽利用残经记忆碎片重施封印术，苏晚卿用灵脉钥匙增幅封印效果，噬灵族首领被再次封印。但林羽的身体再也承受不住，倒在了苏晚卿怀中。章末钩子：林羽的金色纹路正在缓慢消散。",
    "林羽昏迷三天三夜，苏晚卿寸步不离。天机阁正派接管阁务，开始重建秩序。慕容霜发现林羽的金色纹路并非消失，而是在向心脏聚拢——灵脉在自我修复。林羽醒来后发现修为尽失，但体内多了一股温暖的灵脉之力。章末钩子：天机阁长老送来一封信——'北方灵脉也异动了'。",
    "林羽决定继续守护灵脉。虽然修为尽失，但灵脉选中者的体质让他能感应异动。苏晚卿坚持同行，两人关系在生死考验后更加深厚。慕容霜将天机阁历代守护者记录交给林羽，其中记载：每代选中者都面临最终抉择——融入灵脉成为永恒守护，或放弃灵脉回归凡人。章末钩子：最后一页是师父的字迹——'无论你如何选择，为师都以你为傲'。",
    "林羽和苏晚卿踏上北行之路，途中遭遇噬灵族残党。林羽修为尽失，但灵脉之力让他能预判敌人攻击。两人配合默契，找到了全新的战斗方式——灵脉感知加精准配合。章末钩子：北方灵脉核心处，一个被冰封千年的身影正在缓缓睁眼。",
    "北方灵脉守护者醒来，竟是传说中第一代灵脉选中者——他选择融入灵脉成为永恒守护，却被束缚了千年。他告诉林羽，灵脉枯竭因天地灵气循环被打破，唯一方法是让所有选中者同时开启'归源'。但归源意味着选中者将永远与灵脉融为一体。章末钩子：'你不必现在决定，但灵脉不会等你太久'。",
    "林羽面临最艰难的抉择。苏晚卿提出用灵脉钥匙开启归源通道让林羽不用牺牲自己，林羽坚决不同意，两人第一次真正争吵。苏晚卿流泪说'你以为我为你牺牲是软弱吗？这是我的选择'。林羽沉默良久，终于说出'那就一起，无论生死'。章末钩子：归源仪式的星象出现了——就在今夜。",
    "归源仪式开始，林羽和第一代选中者同时引导灵脉之力。苏晚卿用灵脉钥匙开启通道，慕容霜用天机阁禁术稳定能量场。灵脉即将重启的瞬间，噬灵族封印崩裂——始祖挣脱束缚试图吞噬归源能量。林羽在最后关头以全部力量将始祖一同拉入归源通道。章末钩子：归源完成，灵气复苏，但林羽的身影在光芒中渐渐消散。",
    "灵脉重启成功，灵气复苏。苏晚卿在归源之地守了七天七夜，第八天黎明等到奇迹——林羽从光芒中走出。归源重塑了他的身体，他不再是修士却也不完全是凡人——成了灵脉的'守护灵'。苏晚卿扑进他怀里，说什么也不肯松手。章末钩子：远处，灵脉节点上开出一朵从未见过的金色花朵。",
    "苍穹大陆进入新纪元。灵气充盈，万物复苏。林羽和苏晚卿继续守护灵脉，游历四方修复节点。慕容霜成为新一代天机阁阁主。林羽逐渐理解了师父当年的选择——有些路注定孤独，但走这条路时遇到的人，让孤独变成了力量。故事最后，两人站在大陆最高峰上，看着灵气如潮水涌向天际。林羽说'师父，我明白了'。全剧终。",
]


def init_llm_service():
    """初始化LLM服务 — 复用项目的动态LLM Provider"""
    try:
        from infrastructure.ai.llm_client import LLMClient
        client = LLMClient()
        # 测试是否能正常工作
        provider = client.provider
        ptype = type(provider).__name__
        print(f"  LLM 初始化成功: {ptype}")
        return client
    except Exception as e1:
        print(f"  LLMClient方式失败: {e1}")

    try:
        from infrastructure.ai.provider_factory import LLMProviderFactory
        factory = LLMProviderFactory()
        provider = factory.create_active_provider()
        ptype = type(provider).__name__
        print(f"  LLM 初始化成功 (Factory): {ptype}")
        return provider
    except Exception as e2:
        print(f"  Factory方式失败: {e2}")

    try:
        from infrastructure.ai.providers.mock_provider import MockProvider
        print("  未找到API配置, 使用MockProvider")
        return MockProvider()
    except Exception as e3:
        print(f"  所有LLM初始化方式失败: {e3}")
        return None


async def generate_chapter_content(
    llm_service, novel_title: str, chapter_number: int,
    outline: str, prev_chapter_summary: str = "",
    character_profiles: str = "",
) -> str:
    """调用LLM生成章节内容"""
    from domain.ai.value_objects.prompt import Prompt
    from domain.ai.services.llm_service import GenerationConfig

    system_msg = (
        f"你是专业的网络小说作家，正在创作仙侠小说《{novel_title}》。\n\n"
        "=== 写作铁律 ===\n"
        "1. 绝不写情绪标签→用动作替代（'他攥紧拳头'而非'他感到愤怒'）\n"
        "2. 绝不堆叠明喻（每章最多1个'像X一样'）\n"
        "3. 绝不写八股文（'首先...其次...最后...'）\n"
        "4. 绝不写微表情→写完整姿态（'他后退一步'而非'嘴角上扬'）\n"
        "5. 每段推进一个小目标（新发现/冲突/信息/变化）\n"
        "6. 对话必须带信息增量，禁止无内容寒暄\n"
        "7. 章末必有钩子（悬念/反转/新线索）\n"
        "8. 每章至少1个暗线细节（看似无关但后续重要）\n"
        "9. 角色对话长度差异明显（话多vs惜字如金）\n"
        "10. 章首衔接上章结尾（场景延续或时间流逝）\n"
    )

    user_parts = []
    if prev_chapter_summary:
        user_parts.append(f"=== 上一章结尾 ===\n{prev_chapter_summary}\n")
    if character_profiles:
        user_parts.append(f"=== 角色声线 ===\n{character_profiles}\n")
    user_parts.append(f"=== 本章大纲 ===\n{outline}")
    user_parts.append(f"\n请创作第{chapter_number}章，约2000字。严格遵循写作铁律。")

    user_msg = "\n\n".join(user_parts)

    prompt = Prompt(system=system_msg, user=user_msg)
    config = GenerationConfig(max_tokens=4000, temperature=0.85)

    try:
        from infrastructure.ai.llm_client import LLMClient
        if isinstance(llm_service, LLMClient):
            provider = llm_service.provider
            result = await provider.generate(prompt, config)
            return result.content
    except (ImportError, AttributeError):
        pass

    try:
        result = await llm_service.generate(prompt, config)
        return result.content
    except Exception as e:
        logger.error(f"LLM生成失败: {e}")
        return f"[LLM生成失败: {e}]"


def create_test_characters() -> List[Character]:
    """创建测试用角色"""
    lin_yu = Character.create(name="林羽", core_belief="信任是致命的软肋，轻信必死")
    lin_yu.moral_taboos = ["绝不杀手无寸铁之人"]
    lin_yu.voice_profile = VoiceStyle(
        style="惜字如金", sentence_pattern="陈述",
        catchphrases=["走", "不必", "我知道了"],
    )
    lin_yu.active_wounds = [Wound(
        description="师父被追杀时自己无力相助",
        trigger="看到有人陷入绝境",
        effect="握紧拳头，眼神变冷",
    )]

    su_wan = Character.create(name="苏晚卿", core_belief="善良是最大的力量")
    su_wan.voice_profile = VoiceStyle(
        style="话多", sentence_pattern="反问",
        catchphrases=["你听我说", "不会的"],
    )
    su_wan.active_wounds = [Wound(
        description="师父临终前的嘱托",
        trigger="听到师父的事",
        effect="声音变柔，眼眶微红",
    )]

    return [lin_yu, su_wan]


async def run_writing_evaluation(
    num_chapters: int = 5,
    round_number: int = 1,
    output_dir: str = "",
):
    """运行写作评测"""
    print("=" * 70)
    print(f"第{round_number}轮 API跑文评测 — 生成{num_chapters}章")
    print("=" * 70)

    # 1. 初始化LLM
    print("\n[1/5] 初始化LLM服务...")
    llm_service = init_llm_service()
    if not llm_service:
        print("  无法初始化LLM服务，退出")
        return None

    # 2. 创建Story和角色
    print("\n[2/5] 创建故事和角色...")
    orchestrator = WritingOrchestrator()
    characters = create_test_characters()
    story = orchestrator.init_story(
        title="残经录", premise=PREMISE,
        target_chapters=num_chapters, characters=characters,
    )
    print(f"  故事: 《{story.title}》")
    print(f"  角色: {', '.join(c.name for c in story.characters)}")

    # 3. 逐章生成 + 质量检查
    print(f"\n[3/5] 开始生成{num_chapters}章...")
    chapter_results: List[ChapterResult] = []

    # 构建角色声线摘要
    character_profiles = ""
    for c in story.characters:
        vp = getattr(c, 'voice_profile', None)
        if vp:
            character_profiles += (
                f"- {c.name}: 声线={vp.style}, 句式={vp.sentence_pattern}, "
                f"口头禅={','.join(vp.catchphrases)}, "
                f"核心信念={c.core_belief}\n"
            )

    for i in range(num_chapters):
        chapter_num = i + 1
        outline = OUTLINES[i] if i < len(OUTLINES) else f"第{chapter_num}章大纲待补充"
        print(f"\n  --- 第{chapter_num}章 ---")
        print(f"  大纲: {outline[:50]}...")

        # 前章摘要（取最后200字）
        prev_summary = ""
        if chapter_results:
            prev_content = chapter_results[-1].content
            prev_summary = prev_content[-200:] if len(prev_content) > 200 else prev_content

        start_time = time.time()
        content = await generate_chapter_content(
            llm_service, story.title, chapter_num, outline,
            prev_chapter_summary=prev_summary,
            character_profiles=character_profiles,
        )
        gen_time = time.time() - start_time
        print(f"  生成完成: {len(content)}字, 耗时{gen_time:.1f}s")

        result = orchestrator.process_chapter(
            story=story, chapter_number=chapter_num,
            content=content, outline=outline, scene_type="auto",
        )
        chapter_results.append(result)

        if result.quality_report:
            qr = result.quality_report
            status = "OK" if result.quality_passed else "FAIL"
            print(f"  质量: {status} (score={qr.overall_score:.2f})")
            if qr.all_violations:
                for v in qr.all_violations[:3]:
                    print(f"    - {v.get('dimension', '?')}.{v.get('type', '?')}: {v.get('description', '')[:50]}")

        preview = content[:80].replace("\n", " ")
        print(f"  预览: {preview}...")

    # 4. 评估报告
    print(f"\n[4/5] 生成小说家评估报告...")
    assessment = orchestrator.generate_novelist_assessment(chapter_results)

    print(f"\n  评级: {assessment['grade']}")
    print(f"  总分: {assessment['overall_score']:.3f}")
    print(f"  总字数: {assessment['total_words']}")
    print(f"  质量通过率: {assessment['quality_pass_rate']:.1%}")
    print(f"  各维度:")
    for dim, score in assessment['scores'].items():
        print(f"    {dim}: {score:.3f}")
    if assessment.get('top_violations'):
        print(f"  高频违规:")
        for vtype, count in list(assessment['top_violations'].items())[:5]:
            print(f"    {vtype}: {count}次")

    # 5. 保存
    print(f"\n[5/5] 保存结果...")
    if not output_dir:
        output_dir = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "..", "..", "data", "logs", "prompt_v2_tests",
            f"round_{round_number:02d}",
        )
    os.makedirs(output_dir, exist_ok=True)

    chapters_data = []
    for r in chapter_results:
        chapters_data.append({
            "chapter": r.chapter_number,
            "content": r.content,
            "word_count": r.word_count,
            "quality_passed": r.quality_passed,
            "overall_score": r.quality_report.overall_score if r.quality_report else 0,
            "phase": r.phase.value,
        })

    result_file = os.path.join(output_dir, f"round_{round_number:02d}_results.json")
    with open(result_file, "w", encoding="utf-8") as f:
        json.dump({
            "round": round_number,
            "num_chapters": num_chapters,
            "timestamp": datetime.now().isoformat(),
            "story_title": story.title,
            "assessment": assessment,
            "chapters": chapters_data,
        }, f, ensure_ascii=False, indent=2)
    print(f"  结果: {result_file}")

    text_file = os.path.join(output_dir, f"round_{round_number:02d}_novel.txt")
    with open(text_file, "w", encoding="utf-8") as f:
        f.write(f"《{story.title}》\n\n")
        for r in chapter_results:
            f.write(f"{'='*40}\n第{r.chapter_number}章\n{'='*40}\n\n")
            f.write(r.content + "\n\n")
    print(f"  文本: {text_file}")

    return assessment


def main():
    parser = argparse.ArgumentParser(description="跑文评测")
    parser.add_argument("--chapters", type=int, default=5, help="生成章节数")
    parser.add_argument("--round", type=int, default=1, help="评测轮次")
    parser.add_argument("--output", type=str, default="", help="输出目录")
    args = parser.parse_args()

    logging.basicConfig(level=logging.WARNING)
    asyncio.run(run_writing_evaluation(
        num_chapters=args.chapters,
        round_number=args.round,
        output_dir=args.output,
    ))


if __name__ == "__main__":
    main()
