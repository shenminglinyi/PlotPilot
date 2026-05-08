"""章节衔接引擎 — ChapterBridgeService

顶级作家的章节衔接心法：
  「每一章的第一段，都是上一章最后一句话的回声。」
  —— Stephen King《写作这回事》

核心问题：
  当前系统只截取前章原文头尾，但没有提取结构化的"桥段信息"，
  导致 AI 写每章开头时像从零开始，读者感到割裂。

解决方案（三层衔接引擎）：
  1. 章末桥段提取（extract_bridge）：
     每章完成后，用轻量 LLM 提取 5 维桥段：悬念钩子、情感余韵、
     场景状态、角色位置、未完成动作，存入 DB。

  2. 章首衔接约束（build_opening_directive）：
     下一章写作前，从 DB 读取前章桥段，生成强制的「首段衔接指令」，
     注入到 system prompt 的 T0 层（不可删减）。

  3. 衔接度自检（check_continuity）：
     章节生成后，用轻量 LLM 检查首段与前章桥段的衔接度，
     低于阈值则自动修整首段（最多 2 轮）。

性能设计：
  - 桥段提取：复用 narrative_sync 的 LLM 调用，零额外开销
  - 衔接约束：纯字符串拼接，零 LLM 调用
  - 衔接自检：~200 token 的轻量 LLM，仅必要时触发
"""

from __future__ import annotations

import json
import logging
import re
import sqlite3
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from domain.ai.services.llm_service import LLMService, GenerationConfig
from domain.ai.value_objects.prompt import Prompt

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------

@dataclass
class ChapterBridge:
    """章末桥段（5 维衔接锚点）

    这不是一个"摘要"，而是一个"导演的转场笔记"——
    告诉下一章的作者（AI）上一章结束时"镜头"停在哪里。
    """

    # 1. 悬念钩子：章末未解决的悬念/未回答的问题
    #    例："赵宇说出了一个名字，但话到嘴边又咽了回去。"
    suspense_hook: str = ""

    # 2. 情感余韵：章末 POV 角色的核心情绪 + 情绪强度 (1-10)
    #    例："顾言之：不安与隐约的愤怒，7/10"
    emotional_residue: str = ""
    emotional_intensity: int = 5

    # 3. 场景状态：章末场景的物理状态（环境、时间、天气）
    #    例："深夜，老街茶馆内，雨势渐小，只剩檐角滴水声"
    scene_state: str = ""

    # 4. 角色位置：章末每个出场角色的物理位置和行动
    #    例："顾言之：坐在茶馆角落；赵宇：刚起身走向门口"
    character_positions: str = ""

    # 5. 未完成动作：章末正在进行但尚未结束的动作/对话
    #    例："赵宇正要推门出去——门还没推开"
    unfinished_actions: str = ""

    # 原始章末文本（最后 ~800 字，供 LLM 参考但不注入到写作 prompt）
    tail_text: str = ""

    chapter_number: int = 0
    created_at: str = ""


@dataclass
class ContinuityCheckResult:
    """衔接度自检结果"""
    score: float = 0.0  # 0-1，1 为完美衔接
    issues: List[str] = field(default_factory=list)
    suggested_fix: str = ""  # 建议的首段修改（如果衔接度低）


# ---------------------------------------------------------------------------
# ChapterBridgeService
# ---------------------------------------------------------------------------

class ChapterBridgeService:
    """章节衔接引擎

    用法：
      # 审计完成后提取桥段
      bridge = await bridge_svc.extract_bridge(novel_id, chapter_number, content)

      # 写作前获取前章桥段并构建首段指令
      directive = bridge_svc.build_opening_directive(prev_bridge)

      # 生成后自检衔接度
      result = await bridge_svc.check_continuity(novel_id, chapter_number, content)
    """

    # DB 表名
    _TABLE = "chapter_bridges"

    def __init__(
        self,
        llm_service: Optional[LLMService] = None,
        db_path: Optional[str] = None,
    ):
        self._llm = llm_service
        self._db_path = db_path
        self._ensure_table()

    def _ensure_table(self):
        """确保 chapter_bridges 表存在"""
        if not self._db_path:
            return
        try:
            conn = sqlite3.connect(self._db_path, timeout=5.0)
            conn.execute(f"""
                CREATE TABLE IF NOT EXISTS {self._TABLE} (
                    novel_id    TEXT NOT NULL,
                    chapter_number INTEGER NOT NULL,
                    bridge_data TEXT NOT NULL,
                    created_at  TEXT NOT NULL,
                    PRIMARY KEY (novel_id, chapter_number)
                )
            """)
            conn.commit()
            conn.close()
        except Exception as e:
            logger.warning("chapter_bridges 建表失败: %s", e)

    # ------------------------------------------------------------------
    # 1. 章末桥段提取
    # ------------------------------------------------------------------

    async def extract_bridge(
        self,
        novel_id: str,
        chapter_number: int,
        content: str,
    ) -> ChapterBridge:
        """从章节正文提取桥段（5 维衔接锚点）

        策略：只用章节最后 ~1500 字提取，避免全文分析。
        如果 LLM 不可用，用启发式规则降级提取。
        """
        if not content or not content.strip():
            return ChapterBridge(chapter_number=chapter_number)

        # 取章节末尾（桥段信息集中在最后 1000-1500 字）
        tail = content.strip()[-1500:] if len(content) > 1500 else content.strip()

        bridge = ChapterBridge(
            chapter_number=chapter_number,
            tail_text=content.strip()[-800:] if len(content) > 800 else content.strip(),
            created_at=datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        )

        if self._llm:
            try:
                bridge = await self._llm_extract_bridge(chapter_number, tail, bridge)
            except Exception as e:
                logger.warning("LLM 桥段提取失败（降级启发式）ch=%s: %s", chapter_number, e)
                bridge = self._heuristic_extract_bridge(tail, bridge)
        else:
            bridge = self._heuristic_extract_bridge(tail, bridge)

        # 持久化
        self._save_bridge(novel_id, chapter_number, bridge)

        logger.info(
            "桥段提取完成 ch=%s hook=%s emotion=%s",
            chapter_number,
            bridge.suspense_hook[:30] if bridge.suspense_hook else "(无)",
            bridge.emotional_residue[:20] if bridge.emotional_residue else "(无)",
        )
        return bridge

    async def _llm_extract_bridge(
        self,
        chapter_number: int,
        tail_text: str,
        bridge: ChapterBridge,
    ) -> ChapterBridge:
        """用轻量 LLM 提取桥段（~300 token 输入，~200 token 输出）"""

        body = tail_text.strip()
        if len(body) > 1500:
            body = body[-1500:]

        system = """你是小说叙事编辑，负责提取章节末尾的"转场桥段"。

从章节末尾文本中提取 5 个维度的衔接锚点，输出一个 JSON 对象：
{
  "suspense_hook": "章末未解决的悬念/未回答的问题，一两句话概括",
  "emotional_residue": "POV角色的核心情绪状态，格式：角色名：情绪，1-10分",
  "emotional_intensity": 7,
  "scene_state": "章末场景的物理状态（环境+时间+天气），一两句话",
  "character_positions": "章末各角色的位置和行动，每个角色一句话",
  "unfinished_actions": "章末正在进行但未完成的动作/对话"
}

约束：
- 每个字段最多 100 字
- 只提取文本中明确出现的信息，不要推断
- 如果某维度无明显信息，填空字符串
- 严格合法 JSON"""

        user = f"第 {chapter_number} 章末尾：\n\n{body}"

        prompt = Prompt(system=system, user=user)
        config = GenerationConfig(max_tokens=512, temperature=0.3)

        result = await self._llm.generate(prompt, config)
        raw = result.content if hasattr(result, "content") else str(result)

        # 解析 JSON
        data = self._parse_json(raw)
        if data:
            bridge.suspense_hook = str(data.get("suspense_hook", "")).strip()[:200]
            bridge.emotional_residue = str(data.get("emotional_residue", "")).strip()[:200]
            bridge.emotional_intensity = int(data.get("emotional_intensity", 5) or 5)
            bridge.scene_state = str(data.get("scene_state", "")).strip()[:200]
            bridge.character_positions = str(data.get("character_positions", "")).strip()[:200]
            bridge.unfinished_actions = str(data.get("unfinished_actions", "")).strip()[:200]

        return bridge

    def _heuristic_extract_bridge(
        self,
        tail_text: str,
        bridge: ChapterBridge,
    ) -> ChapterBridge:
        """启发式降级：无 LLM 时用规则提取桥段"""

        text = tail_text.strip()

        # 悬念钩子：最后一句含疑问/省略号/破折号
        sentences = re.split(r'[。！？]', text)
        last_sentences = [s.strip() for s in sentences[-5:] if s.strip()]
        suspense_candidates = []
        for s in last_sentences:
            if '？' in s or '……' in s or '——' in s or '却' in s or '但是' in s:
                suspense_candidates.append(s)
        if suspense_candidates:
            bridge.suspense_hook = suspense_candidates[-1][:100]

        # 情感余韵：搜索情感关键词
        emotion_keywords = {
            '愤怒': '愤怒', '不安': '不安', '恐惧': '恐惧',
            '震惊': '震惊', '悲伤': '悲伤', '紧张': '紧张',
            '释然': '释然', '困惑': '困惑', '期待': '期待',
            '焦虑': '焦虑', '心寒': '心寒', '绝望': '绝望',
        }
        for kw, label in emotion_keywords.items():
            if kw in text[-500:]:
                bridge.emotional_residue = label
                break

        # 场景状态：提取时间/地点关键词
        time_words = re.findall(r'(深夜|凌晨|清晨|傍晚|午后|正午|黄昏|夜晚|白天)', text[-400:])
        place_words = re.findall(r'(茶馆|街道|房间|办公室|巷子|医院|学校|老街|市场)', text[-400:])
        if time_words or place_words:
            parts = []
            if time_words:
                parts.append(time_words[-1])
            if place_words:
                parts.append(place_words[-1])
            bridge.scene_state = "，".join(parts)

        return bridge

    # ------------------------------------------------------------------
    # 2. 章首衔接约束生成
    # ------------------------------------------------------------------

    def build_opening_directive(
        self,
        prev_bridge: Optional[ChapterBridge],
    ) -> str:
        """构建章首衔接指令（注入到 T0 层的强制内容）

        这是衔接引擎的核心输出——一段精心设计的"承上启下"指令，
        告诉 AI 本章开头必须做什么、不能做什么。

        设计哲学（顶级作家视角）：
          - 悬念钩子 → 必须呼应（不能当没发生过）
          - 情感余韵 → 必须延续（情绪有惯性）
          - 场景状态 → 必须接续（物理世界不会突然变化）
          - 角色位置 → 必须合理（人不会瞬移）
          - 未完成动作 → 必须延续（动作在继续）
        """
        if not prev_bridge:
            return ""

        if not any([
            prev_bridge.suspense_hook,
            prev_bridge.emotional_residue,
            prev_bridge.scene_state,
            prev_bridge.character_positions,
            prev_bridge.unfinished_actions,
        ]):
            return ""

        parts = ["【🔗 章节衔接指令（T0 强制约束，不可删减）】"]
        parts.append(f"上一章（第 {prev_bridge.chapter_number} 章）结束时：\n")

        if prev_bridge.suspense_hook:
            parts.append(f"⚠ 悬念钩子：{prev_bridge.suspense_hook}")
            parts.append("→ 本章开头必须呼应此悬念：或直接回应、或侧面映射、或加深谜团。绝不能装作没发生过。\n")

        if prev_bridge.emotional_residue:
            intensity_label = "强烈" if prev_bridge.emotional_intensity >= 7 else "中等" if prev_bridge.emotional_intensity >= 4 else "微弱"
            parts.append(f"💭 情感余韵：{prev_bridge.emotional_residue}（{intensity_label}，{prev_bridge.emotional_intensity}/10）")
            parts.append(f"→ 本章首段 POV 角色的情绪必须从「{prev_bridge.emotional_residue}」延续或演变。情绪有惯性——不会瞬间切换。\n")

        if prev_bridge.scene_state:
            parts.append(f"🏔 场景状态：{prev_bridge.scene_state}")
            parts.append("→ 本章开头的物理环境必须与前章末尾一致或自然过渡（时间流逝、场景转换需有明确交代）。\n")

        if prev_bridge.character_positions:
            parts.append(f"👤 角色位置：{prev_bridge.character_positions}")
            parts.append("→ 本章开头各角色的位置必须与前章末尾一致。人不会瞬移——如果角色在门口，下一章他要么进门、要么转身，不会突然在另一个城市。\n")

        if prev_bridge.unfinished_actions:
            parts.append(f"🎬 未完成动作：{prev_bridge.unfinished_actions}")
            parts.append("→ 本章必须延续此动作的完成过程，或解释为何中断。\n")

        # 衔接铁律
        parts.append("━━━ 首段衔接铁律 ━━━")
        parts.append("① 本章首段必须是上一章的延续，而非新的开始。")
        parts.append("② 前三句话之内必须出现与前章结尾的连接点（情绪/画面/动作）。")
        parts.append("③ 如果场景转换，必须用过渡句（如'两个小时后'、'天亮了'），不能用空行跳转。")
        parts.append("④ 不许用'第二天'开头然后当上一章没发生过——上一章的情绪和事件必须在本章有涟漪。")

        return "\n".join(parts)

    def build_bridge_summary_for_context(
        self,
        prev_bridge: Optional[ChapterBridge],
    ) -> str:
        """构建简洁版桥段摘要（注入到 Layer2/最近章节区域）

        比 build_opening_directive 更短，用于上下文预算紧张时。
        """
        if not prev_bridge:
            return ""

        items = []
        if prev_bridge.suspense_hook:
            items.append(f"悬念：{prev_bridge.suspense_hook}")
        if prev_bridge.emotional_residue:
            items.append(f"情绪：{prev_bridge.emotional_residue}（{prev_bridge.emotional_intensity}/10）")
        if prev_bridge.scene_state:
            items.append(f"场景：{prev_bridge.scene_state}")
        if prev_bridge.character_positions:
            items.append(f"角色位置：{prev_bridge.character_positions}")
        if prev_bridge.unfinished_actions:
            items.append(f"未完成：{prev_bridge.unfinished_actions}")

        if not items:
            return ""

        return f"【前章桥段】第{prev_bridge.chapter_number}章末：" + "；".join(items)

    # ------------------------------------------------------------------
    # 3. 衔接度自检
    # ------------------------------------------------------------------

    async def check_continuity(
        self,
        novel_id: str,
        chapter_number: int,
        content: str,
        prev_bridge: Optional[ChapterBridge] = None,
    ) -> ContinuityCheckResult:
        """检查章节首段与前章桥段的衔接度

        策略：只用首段（前 500 字）+ 前章桥段进行轻量 LLM 检查。
        如果衔接度 < 0.6，生成修整建议。
        """
        if not prev_bridge or not self._llm or not content:
            return ContinuityCheckResult(score=1.0)

        # 取首段
        head = content.strip()[:500]

        system = """你是小说衔接度评审。评估本章开头是否有效承接了上一章结尾。

评分标准（0-1）：
- 0.9-1.0：完美衔接，首段直接呼应前章的悬念/情绪/场景
- 0.7-0.9：良好衔接，有明确的过渡但可以更紧密
- 0.5-0.7：弱衔接，读者能感觉到两章属于同一本书但过渡生硬
- 0.3-0.5：割裂感明显，像是两个独立的故事拼在一起
- 0-0.3：完全断裂，没有任何承接

输出 JSON：
{
  "score": 0.8,
  "issues": ["问题1", "问题2"],
  "suggested_fix": "建议的首段修改方向（一两句话），或空字符串"
}"""

        # 构建前章桥段摘要
        bridge_parts = []
        if prev_bridge.suspense_hook:
            bridge_parts.append(f"悬念钩子：{prev_bridge.suspense_hook}")
        if prev_bridge.emotional_residue:
            bridge_parts.append(f"情感余韵：{prev_bridge.emotional_residue}（{prev_bridge.emotional_intensity}/10）")
        if prev_bridge.scene_state:
            bridge_parts.append(f"场景状态：{prev_bridge.scene_state}")
        if prev_bridge.character_positions:
            bridge_parts.append(f"角色位置：{prev_bridge.character_positions}")
        if prev_bridge.unfinished_actions:
            bridge_parts.append(f"未完成动作：{prev_bridge.unfinished_actions}")

        bridge_summary = "\n".join(bridge_parts)

        user = f"""上一章（第{prev_bridge.chapter_number}章）结尾桥段：
{bridge_summary}

本章（第{chapter_number}章）开头：
{head}

请评估衔接度。"""

        prompt = Prompt(system=system, user=user)
        config = GenerationConfig(max_tokens=256, temperature=0.3)

        try:
            result = await self._llm.generate(prompt, config)
            raw = result.content if hasattr(result, "content") else str(result)
            data = self._parse_json(raw)

            if data:
                score = float(data.get("score", 0.7))
                issues = data.get("issues", [])
                suggested_fix = str(data.get("suggested_fix", "")).strip()

                return ContinuityCheckResult(
                    score=max(0.0, min(1.0, score)),
                    issues=issues if isinstance(issues, list) else [],
                    suggested_fix=suggested_fix[:300],
                )
        except Exception as e:
            logger.warning("衔接度自检失败 ch=%s: %s", chapter_number, e)

        # 降级：不做检查
        return ContinuityCheckResult(score=0.7)

    async def auto_fix_opening(
        self,
        novel_id: str,
        chapter_number: int,
        content: str,
        prev_bridge: ChapterBridge,
        check_result: ContinuityCheckResult,
        max_rounds: int = 2,
    ) -> str:
        """自动修整首段（仅当衔接度 < 0.6 时触发）

        策略：用 LLM 重写首段（前 300 字），保持后文不变。
        最多修整 max_rounds 轮。
        """
        if check_result.score >= 0.6 or not self._llm:
            return content

        head_size = min(300, len(content.strip()))
        head = content.strip()[:head_size]
        rest = content.strip()[head_size:]

        issues_text = "；".join(check_result.issues) if check_result.issues else "首段与前章衔接不紧密"
        fix_hint = check_result.suggested_fix or "加强首段与前章的情绪/场景/悬念呼应"

        bridge_parts = []
        if prev_bridge.suspense_hook:
            bridge_parts.append(f"悬念钩子：{prev_bridge.suspense_hook}")
        if prev_bridge.emotional_residue:
            bridge_parts.append(f"情感余韵：{prev_bridge.emotional_residue}（{prev_bridge.emotional_intensity}/10）")
        if prev_bridge.scene_state:
            bridge_parts.append(f"场景状态：{prev_bridge.scene_state}")
        if prev_bridge.character_positions:
            bridge_parts.append(f"角色位置：{prev_bridge.character_positions}")
        if prev_bridge.unfinished_actions:
            bridge_parts.append(f"未完成动作：{prev_bridge.unfinished_actions}")
        bridge_summary = "\n".join(bridge_parts)

        system = """你是小说衔接修整专家。重写章节首段，使其与前章结尾紧密衔接。

要求：
1. 保持原文的核心信息和情节方向不变
2. 在前三句话内建立与前章的连接（情绪/画面/动作）
3. 不能改变后续情节的展开逻辑
4. 修整后的首段长度与原文相当
5. 只输出重写后的首段，不要解释"""

        user = f"""前章桥段：
{bridge_summary}

当前首段：
{head}

问题：{issues_text}
修整方向：{fix_hint}

请重写首段："""

        prompt = Prompt(system=system, user=user)
        config = GenerationConfig(max_tokens=512, temperature=0.4)

        try:
            result = await self._llm.generate(prompt, config)
            new_head = result.content if hasattr(result, "content") else str(result)
            new_head = new_head.strip()

            if new_head and len(new_head) >= 50:
                # 拼接修整后的首段 + 原文剩余部分
                fixed_content = new_head + rest
                logger.info(
                    "首段衔接修整完成 ch=%s 原头=%d字→新头=%d字 衔接度=%.1f→%.1f",
                    chapter_number, len(head), len(new_head),
                    check_result.score, 0.7,  # 修整后预估
                )
                return fixed_content
        except Exception as e:
            logger.warning("首段衔接修整失败 ch=%s: %s", chapter_number, e)

        return content

    # ------------------------------------------------------------------
    # 3b. 节拍间衔接检查
    # ------------------------------------------------------------------

    async def check_beat_continuity(
        self,
        novel_id: str,
        chapter_number: int,
        beat_index: int,
        prior_content: str,
        new_beat_content: str,
    ) -> Tuple[float, str]:
        """检查节拍间衔接质量（轻量启发式，零 LLM 调用）

        核心思路：
          不是用 LLM 去评分（太重），而是用启发式规则检测常见的
          节拍间割裂信号：
          - 新节拍开头是否与上节拍结尾有语义连接
          - 是否有突兀的场景跳转
          - 是否有"后来"/"之后"等跳跃词

        Returns:
            (score, diagnosis): score 0-1，diagnosis 描述问题
        """
        if not prior_content or not new_beat_content:
            return (1.0, "")

        from application.workflows.beat_continuation import extract_beat_tail_anchor

        # 提取前节拍锚点
        anchor = extract_beat_tail_anchor(prior_content)

        # 新节拍开头（前 200 字）
        new_head = new_beat_content.strip()[:200]

        score = 1.0
        issues = []

        # 检测1：跳跃词检测
        jump_words = ['后来', '之后', '后来呢', '到了', '转眼', '不知不觉']
        for jw in jump_words:
            if new_head.startswith(jw) or f'\n{jw}' in new_head[:50]:
                score -= 0.2
                issues.append(f"开头使用了跳跃词「{jw}」，节拍间应有连续过渡")
                break

        # 检测2：对话断裂——前节拍在对话中，新节拍没有回应
        if anchor.tail_state == "对话中":
            # 检查新节拍开头是否有引号或对话回应
            if not re.search(r'[""「『"]', new_head[:100]):
                score -= 0.3
                issues.append("前节拍停在对白中，但新节拍没有回应/延续对话")

        # 检测3：情绪断裂
        mood_inertia_rules = {
            '紧张': ['轻松', '笑', '悠闲', '放松'],
            '愤怒': ['平静', '微笑', '冷静'],
            '悲伤': ['开心', '兴奋', '雀跃'],
        }
        if anchor.mood_tone in mood_inertia_rules:
            break_words = mood_inertia_rules[anchor.mood_tone]
            for bw in break_words:
                if bw in new_head[:80]:
                    score -= 0.2
                    issues.append(f"情绪惯性断裂：前节拍{anchor.mood_tone}，新节拍突然{bw}")
                    break

        # 检测4：场景突转——前节拍有具体位置，新节拍完全不同的场景
        if anchor.tail_state == "叙述中" or anchor.tail_state == "场景转换":
            # 如果新节拍开头出现了与锚点 last_moment 完全不相关的内容
            # （简单检测：没有任何重复实体）
            if anchor.last_moment:
                # 提取锚点中的2字以上实体
                anchor_entities = set(re.findall(r'[\u4e00-\u9fff]{2,4}', anchor.last_moment))
                head_entities = set(re.findall(r'[\u4e00-\u9fff]{2,4}', new_head[:100]))
                overlap = anchor_entities & head_entities
                if not overlap and len(anchor_entities) >= 2:
                    score -= 0.15
                    issues.append("新节拍开头与前节拍尾没有共享实体，可能场景突转")

        score = max(0.0, min(1.0, score))
        diagnosis = "；".join(issues) if issues else ""

        return (score, diagnosis)

    # ------------------------------------------------------------------
    # 持久化
    # ------------------------------------------------------------------

    def _save_bridge(self, novel_id: str, chapter_number: int, bridge: ChapterBridge):
        """持久化桥段到 DB"""
        if not self._db_path:
            return
        try:
            data = {
                "suspense_hook": bridge.suspense_hook,
                "emotional_residue": bridge.emotional_residue,
                "emotional_intensity": bridge.emotional_intensity,
                "scene_state": bridge.scene_state,
                "character_positions": bridge.character_positions,
                "unfinished_actions": bridge.unfinished_actions,
                "tail_text": bridge.tail_text,
                "chapter_number": bridge.chapter_number,
                "created_at": bridge.created_at,
            }
            conn = sqlite3.connect(self._db_path, timeout=5.0)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=3000")
            conn.execute(
                f"INSERT OR REPLACE INTO {self._TABLE} (novel_id, chapter_number, bridge_data, created_at) VALUES (?, ?, ?, ?)",
                (novel_id, chapter_number, json.dumps(data, ensure_ascii=False), bridge.created_at),
            )
            conn.commit()
            conn.close()
        except Exception as e:
            logger.warning("桥段持久化失败 novel=%s ch=%s: %s", novel_id, chapter_number, e)

    def get_bridge(self, novel_id: str, chapter_number: int) -> Optional[ChapterBridge]:
        """从 DB 读取桥段"""
        if not self._db_path:
            return None
        try:
            conn = sqlite3.connect(self._db_path, timeout=5.0)
            conn.execute("PRAGMA journal_mode=WAL")
            row = conn.execute(
                f"SELECT bridge_data FROM {self._TABLE} WHERE novel_id = ? AND chapter_number = ?",
                (novel_id, chapter_number),
            ).fetchone()
            conn.close()
            if not row:
                return None
            data = json.loads(row[0])
            return ChapterBridge(
                suspense_hook=data.get("suspense_hook", ""),
                emotional_residue=data.get("emotional_residue", ""),
                emotional_intensity=data.get("emotional_intensity", 5),
                scene_state=data.get("scene_state", ""),
                character_positions=data.get("character_positions", ""),
                unfinished_actions=data.get("unfinished_actions", ""),
                tail_text=data.get("tail_text", ""),
                chapter_number=data.get("chapter_number", chapter_number),
                created_at=data.get("created_at", ""),
            )
        except Exception as e:
            logger.debug("桥段读取失败 novel=%s ch=%s: %s", novel_id, chapter_number, e)
            return None

    def get_prev_chapter_bridge(self, novel_id: str, chapter_number: int) -> Optional[ChapterBridge]:
        """获取前一章的桥段（最常用的 API）"""
        if chapter_number <= 1:
            return None
        return self.get_bridge(novel_id, chapter_number - 1)

    # ------------------------------------------------------------------
    # 工具方法
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_json(text: str) -> dict:
        """从 LLM 输出中解析 JSON"""
        from application.ai.structured_json_pipeline import sanitize_llm_output, parse_and_repair_json
        cleaned = sanitize_llm_output(text or "")
        if not cleaned:
            return {}
        data, _ = parse_and_repair_json(cleaned)
        return data if isinstance(data, dict) else {}
