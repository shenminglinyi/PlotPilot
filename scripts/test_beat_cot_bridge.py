"""
测试三种节拍间 CoT 桥接提示词，选最优方案。

运行：python scripts/test_beat_cot_bridge.py
"""
import asyncio
import json
import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 真实测试数据
PREV_BEAT_CONTENT = """退婚书砸在林墨脸上的瞬间，大殿里爆发出一阵哄笑。

笑声从四面八方涌来,像潮水拍打在礁石上。林墨站在大殿中央,手指攥紧了那张薄薄的纸。纸边缘很锋利,划破了他的指腹,血珠渗出来,在白纸上晕开一小片红。

云岚站在高台上,一袭红色长裙在烛光下泛着金色的光。她的手还保持着扔东西的姿势,指尖微微颤抖,但脸上的笑容很稳。"林墨,三年前你还是天才的时候,我云岚高攀不起。现在嘛——"她停顿了一下,目光扫过大殿里的宾客,"一个废人,也配做我云家的女婿?"

又是一阵笑声。

林墨听见身后有人在窃窃私语。"听说他现在连灵气都感应不到了。""可不是,修炼事故嘛,经脉全毁了。""云家小姐这婚退得对,谁愿意嫁给一个废物?"

大殿里的烛火跳动着,光影在石柱上晃来晃去。空气很闷,带着檀香和脂粉的味道,还有一股说不清的潮湿气息。林墨的衣服贴在背上,汗水顺着脊椎往下流。

他低头看着手里的退婚书。墨迹还没干透,在烛光下泛着油亮的光。"云岚小姐与林墨自今日起解除婚约,此生再无瓜葛。"

林家的护卫站在大殿门口,十几个人排成一排,全都低着头。林天羽坐在侧席,背脊挺得笔直。他盯着面前的茶杯,杯子里的茶水已经凉了。

"林家主,你儿子可真是给你长脸啊。"云家的一位长老站起来端着酒杯走到林天羽面前。

林天羽抬起头,看了那长老一眼,又低下去了。他什么都没说。

大殿里的笑声更响了。"""

NEXT_BEAT_INTENT = "林墨接起退婚书的瞬间，体内封印松动，远古神魂气息骤然泄露——大殿温度骤降，所有人感受到窒息般的威压，云岚脸色骤变，林家护卫本能后退"

CHAPTER_OUTLINE = "云家大殿，宾客满座。云岚当众宣布退婚，将退婚书砸向林墨。全场哄笑，林家护卫低头，父亲林天羽沉默不语。就在林墨接过退婚书的瞬间，体内封印松动，一股远古气息泄露，大殿内所有人感到窒息般的威压。云岚脸色骤变，林墨眼中闪过金色符文，冷笑道：'三年之约，今日便是终点。'"


# ═══════════════════════════════════════════════
# 方案 A: 完整 CoT 步骤式 (分析 → 规划 → 输出)
# ═══════════════════════════════════════════════
PROMPT_A_SYSTEM = """你是资深中文网络小说编辑，专注于节拍间叙事衔接质量分析。

你的任务是帮助小说生成系统在每个节拍生成后，理性分析当前叙事状态，为下一个节拍生成准确的桥接指令。
好的桥接应该：让读者感觉正文是一气呵成写出来的，而不是拼接的。"""

PROMPT_A_USER = """## 当前节拍正文（刚生成完毕）：
{prev_beat}

## 下一节拍的叙事任务（意图）：
{next_intent}

请按以下步骤分析并输出节拍桥接 JSON：

**步骤1 - 现场盘点**：上一节拍结束时，主要人物在哪里、做什么、情绪是什么？
**步骤2 - 未关闭的叙事线**：什么动作/对话/情绪弧还没有关闭？读者的注意力聚焦在哪里？
**步骤3 - 过渡设计**：怎样从上一节拍的最后一句，自然地滑入下一节拍的第一句？写出那个开头。
**步骤4 - 感官基调**：下一节拍继承什么感官基调（温度、光线、声音）？

输出格式（严格 JSON，不加任何 Markdown 围栏）：
{{
  "state": "当前场景状态，人物位置与情绪（40字以内）",
  "open_threads": ["未关闭叙事线1", "未关闭叙事线2"],
  "opening_line": "下一节拍建议开头（一句话，25字以内，作为正文一部分直接使用）",
  "sensory_anchor": "继承的感官基调（10字以内）",
  "avoid": "此处最容易出现的叙事断层（15字以内）"
}}"""


# ═══════════════════════════════════════════════
# 方案 B: 简洁直接式 (轻量化，适合高频调用)
# ═══════════════════════════════════════════════
PROMPT_B_SYSTEM = """你是中文小说节拍衔接助手。根据上一节拍结尾分析叙事状态，给出下一节拍的开头指令。输出 JSON，简洁准确。"""

PROMPT_B_USER = """上一节拍结尾（最后300字）：
{prev_beat_tail}

下一节拍要写：{next_intent}

输出 JSON（不加围栏）：
{{
  "carry": "必须延续的核心叙事元素（20字以内）",
  "opening_line": "下一节拍第一句话，直接可用于正文（20字以内）",
  "tone": "情绪基调关键词（5字以内）"
}}"""


# ═══════════════════════════════════════════════
# 方案 C: 叙事状态机式 (结构化，可扩展)
# ═══════════════════════════════════════════════
PROMPT_C_SYSTEM = """你是叙事状态机分析器。
输入：已生成的节拍正文 + 下一节拍的叙事意图。
输出：叙事状态快照 + 过渡指令。
原则：连贯性 > 新鲜感。读者不应感受到「切换感」。"""

PROMPT_C_USER = """[节拍正文结尾]
{prev_beat_tail}

[下一节拍意图]
{next_intent}

分析上述正文结束时的叙事状态，然后给出精确的过渡指令。

输出格式（JSON，不加 Markdown 围栏）：
{{
  "active_scene": {{
    "location": "当前场景地点",
    "characters_present": ["人物1状态", "人物2状态"],
    "atmosphere": "氛围关键词"
  }},
  "narrative_momentum": "读者注意力此刻聚焦于什么（15字）",
  "transition": {{
    "type": "emotion_continue|action_continue|scene_cut|dialogue_continue",
    "opening_line": "下一节拍开头（可直接写入正文，25字以内）",
    "carry_forward": "必须延续的叙事要素（15字）"
  }},
  "risk": "最容易出现的断层点（10字）"
}}"""


async def call_llm(system: str, user: str, label: str) -> tuple[str, float]:
    """调用 LLM 并计时"""
    from interfaces.api.dependencies import get_llm_service
    from domain.ai.services.llm_service import GenerationConfig
    from domain.ai.value_objects.prompt import Prompt

    llm = get_llm_service()
    prompt = Prompt(system=system, user=user)
    config = GenerationConfig(max_tokens=600, temperature=0.3)

    print(f"\n{'='*60}")
    print(f"[{label}] 调用 LLM ...")
    t0 = time.time()
    pieces = []
    async for chunk in llm.stream_generate(prompt, config):
        pieces.append(chunk)
        print(chunk, end="", flush=True)
    elapsed = time.time() - t0
    print(f"\n\n[{label}] 耗时: {elapsed:.2f}s")
    return "".join(pieces), elapsed


def eval_response(label: str, response: str, elapsed: float) -> dict:
    """评估响应质量"""
    score = {"label": label, "elapsed": elapsed, "raw": response, "issues": []}
    
    # 1. JSON 可解析性
    try:
        cleaned = response.strip()
        if "```" in cleaned:
            cleaned = cleaned.split("```")[1]
            if cleaned.startswith("json"):
                cleaned = cleaned[4:]
        data = json.loads(cleaned)
        score["parsed"] = data
        score["json_ok"] = True
    except Exception as e:
        score["json_ok"] = False
        score["issues"].append(f"JSON解析失败: {e}")
        return score

    # 2. 开头句质量检查
    opening = data.get("opening_line") or (data.get("transition") or {}).get("opening_line", "")
    if opening:
        score["opening_line"] = opening
        if len(opening) > 50:
            score["issues"].append("开头句过长（>50字）")
        if "林墨" not in opening and "他" not in opening and "大殿" not in opening:
            score["issues"].append("开头句可能未与上一节拍衔接")
    else:
        score["issues"].append("缺少 opening_line 字段")

    # 3. 连贯性关键词检查
    full_text = json.dumps(data, ensure_ascii=False)
    continuity_keywords = ["威压", "退婚书", "林墨", "云岚", "大殿", "封印", "气息"]
    found = [kw for kw in continuity_keywords if kw in full_text]
    score["continuity_keywords"] = found
    if len(found) < 2:
        score["issues"].append("连贯性关键词不足（< 2个）")

    score["quality_score"] = 10 - len(score["issues"]) * 2 + len(found)
    return score


async def main():
    prev_tail = PREV_BEAT_CONTENT[-400:]  # 方案 B/C 用最后400字

    prompts = [
        (
            "方案A_完整CoT",
            PROMPT_A_SYSTEM,
            PROMPT_A_USER.format(prev_beat=PREV_BEAT_CONTENT, next_intent=NEXT_BEAT_INTENT),
        ),
        (
            "方案B_简洁",
            PROMPT_B_SYSTEM,
            PROMPT_B_USER.format(prev_beat_tail=prev_tail, next_intent=NEXT_BEAT_INTENT),
        ),
        (
            "方案C_状态机",
            PROMPT_C_SYSTEM,
            PROMPT_C_USER.format(prev_beat_tail=prev_tail, next_intent=NEXT_BEAT_INTENT),
        ),
    ]

    results = []
    for label, sys_p, usr_p in prompts:
        try:
            resp, elapsed = await call_llm(sys_p, usr_p, label)
            result = eval_response(label, resp, elapsed)
            results.append(result)
        except Exception as e:
            print(f"\n[{label}] 错误: {e}")
            results.append({"label": label, "error": str(e)})

    print("\n\n" + "="*60)
    print("📊 评估结果汇总")
    print("="*60)
    for r in results:
        print(f"\n【{r['label']}】")
        if "error" in r:
            print(f"  ❌ 错误: {r['error']}")
            continue
        print(f"  ⏱️  耗时: {r['elapsed']:.2f}s")
        print(f"  ✅ JSON: {'可解析' if r.get('json_ok') else '❌不可解析'}")
        if r.get("opening_line"):
            print(f"  📝 开头: {r['opening_line']}")
        if r.get("continuity_keywords"):
            print(f"  🔗 连贯词: {r['continuity_keywords']}")
        if r.get("issues"):
            print(f"  ⚠️  问题: {r['issues']}")
        print(f"  🏆 质量分: {r.get('quality_score', 'N/A')}")

    # 选出最优
    valid = [r for r in results if r.get("json_ok") and "quality_score" in r]
    if valid:
        best = max(valid, key=lambda x: x["quality_score"])
        print(f"\n🥇 推荐方案: 【{best['label']}】 (质量分: {best['quality_score']}, 耗时: {best['elapsed']:.2f}s)")


if __name__ == "__main__":
    asyncio.run(main())
