"""情节密度守门人 — 检测无营养的文字（专业小说家视角重构版）

核心判断框架（三层递进）：
1. 形容词冗余堆叠：同一名词前连续3+个纯修饰定语，或副词叠词连用
2. 全文叙事推进比例：无推进段落占比过高（≥60%且绝对数≥4段）时才聚合报一条
3. 信息密度：每千字有效信息点低于阈值（信息点定义更宽泛）

评分机制（类别封顶，防爆炸）：
- 形容词冗余最多扣30分
- 段落推进最多扣35分
- 信息密度最多扣35分
- 各类独立计算后加总，不线性叠加

专业小说家角度：
- 环境描写若折射人物心境或暗藏张力，属于有效叙事
- 内心独白若有认知转变或情感转折，属于有效叙事
- 形容词堆叠是真正的问题，但要区分"修辞叠用"和"正常定语链"
"""
from __future__ import annotations

import re
import logging
from dataclasses import dataclass
from typing import List, Tuple

logger = logging.getLogger(__name__)


@dataclass
class DensityViolation:
    """密度违规"""
    violation_type: str    # adj_redundancy / low_progression_ratio / low_info_density
    severity: float
    description: str
    suggestion: str
    position: str = ""


class PlotDensityGuardrail:
    """情节密度守门人（重构版）"""

    # 信息密度阈值（有效信息点/千字）——宽泛定义下的合理基准
    MIN_INFO_DENSITY = 4

    # ── 形容词冗余堆叠模式（严格版，减少误判）──────────────────────
    # 规则：同一名词前出现3+个2字以上的定语（每个定语本身是纯修饰词）
    # 例："冷漠的孤傲的不可接近的气质" → 触发
    # 例："林墨点开地图上标注的位置" → 不触发（是正常定语链）
    ADJ_STACK_PATTERN = re.compile(
        r'(?:[\u4e00-\u9fff]{2,5}的){3,}[\u4e00-\u9fff]{1,4}',
    )

    # 副词叠词连用：同一种叠词副词连用（轻轻地缓缓地 / 微微地轻轻地 等）
    ADV_STACK_PATTERN = re.compile(
        r'(?:(?:轻轻|缓缓|微微|慢慢|静静|默默|悄悄|深深|淡淡|柔柔|沉沉|徐徐|幽幽)地){2,}'
    )

    # 常见填充修饰词（每100字出现4次以上才报）
    FILLER_WORDS = [
        "不由得", "忍不住", "情不自禁", "下意识地",
        "似乎", "仿佛", "好像",
        "非常", "十分", "极其", "格外",
    ]

    # ── 叙事推进信号（宽泛定义）──────────────────────────────────
    # 以下任意一类信号出现，段落被视为"有叙事推进"

    # A. 人物主动完成的具体动作（动作词+了；排除纯状态变化词）
    # 注：用词根白名单代替宽泛的"任意汉字+了"，避免"消散了/飘散了/弥漫了"误判
    _RE_ACTION = re.compile(
        r'(?:推|拉|打|踢|抓|握|拔|刺|砍|扔|摔|踩|拿|放|给|递|接|撕|扯|绑|锁'
        r'|走|跑|冲|跳|站|坐|蹲|跪|躺|爬|飞奔|转身|回头|停下|起身|俯身'
        r'|说|叫|喊|问|答|骂|斥|呵|嘲|劝|哭|笑|叹|吐|咬|吞'
        r'|打开|关上|推开|拉开|锁上|扔掉|拿起|放下|捡起|拎起'
        r'|发现|找到|拿到|得到|失去|丢失|藏起|取出'
        r')(?:了|掉|完|开|起来|出去|进来|出来|下去|回来|过去)?'
    )

    # B. 对话
    _RE_DIALOGUE = re.compile(r'["\u201c\u300c]')

    # C. 认知/发现类
    _RE_DISCOVERY = re.compile(r'(?:发现|意识到|明白了?|知道了?|想起|看出|听出|察觉|注意到|想清楚|看到了|听到了)')

    # D. 冲突/转折
    _RE_CONFLICT = re.compile(r'(?:却|但|然而|可是|偏偏|居然|竟然|没想到|不料|突然|猛地|忽然)')

    # E. 心理转变（内心状态改变，不是单纯描述情绪）
    _RE_PSYCHE_CHANGE = re.compile(r'(?:决定|选择|放弃|打算|后悔|不再|开始了|停止了|改变了|下定决心)')

    # F. 明确的空间位移（双字以上词，避免单字歧义）
    _RE_SPATIAL = re.compile(r'(?:走进|走出|离开|来到|到达|进入|退出|靠近|远离|转身|追上|拦住|冲进|冲出|跑进|跑出)')

    # ── 信息点统计（宽泛版）─────────────────────────────────────
    _RE_INFO_ACTION = re.compile(
        r'(?:推|拉|打|踢|抓|握|拔|刺|砍|扔|拿|放|给|递|接|走|跑|冲|跳'
        r'|说|叫|喊|问|答|打开|关上|推开|发现|找到|拿到|得到|失去'
        r')(?:了|掉|完|开|起来|出去|进来|出来|下去|回来)?'
    )
    _RE_INFO_DIALOGUE = re.compile(r'["\u201c\u300c]')
    _RE_INFO_REVEAL = re.compile(r'(?:发现|揭示|暴露|坦白|承认|说出|透露|告诉)')
    _RE_INFO_DECISION = re.compile(r'(?:决定|选择|放弃|答应|拒绝|同意|反对)')
    _RE_INFO_CONFLICT = re.compile(r'(?:冲突|对抗|争吵|对峙|翻脸|威胁|质问|反驳)')
    _RE_INFO_SPATIAL = re.compile(r'(?:走进|走出|离开|来到|到达|进入|退出|靠近|远离|追上|拦住|冲进|冲出)')

    # ── 纯描写快速过滤 ─────────────────────────────────────────

    # 感官/自然动词（多=倾向于景物/氛围描写）
    _RE_SENSORY = re.compile(r'[映照洒飘飞流唱舞散弥漫悬浮绕荡]')

    # 人物叙事动词（出现=有明确人物行为，不含歧义单字）
    # 注意：不用"出/进/回/转"这类单字，它们太容易作为词的一部分误触发
    _RE_SUBJECT_ACT = re.compile(
        r'[\u4e00-\u9fff]{1,4}(?:说话|问道|回答|叫道|喊道'
        r'|走过来|走过去|跑过来|跑过去|站起来|坐下来'
        r'|推开|拉开|打开|关上|拿起|放下|捡起'
        r'|打了|踢了|抓住|握住|扔掉|摔了'
        r'|发现了|看到了|听到了|意识到|注意到)'
    )

    # ──────────────────────────────────────────────────────────────

    def check(self, text: str, chapter_goal: str = "") -> Tuple[float, List[DensityViolation]]:
        """检查文本的情节密度

        Returns:
            (score 0.0~1.0, violations)
        """
        adj_v = self._check_adjective_redundancy(text)
        para_v = self._check_progression_ratio(text)
        density_v = self._check_info_density(text)

        # 各类独立封顶后加总（防止爆炸）
        adj_penalty = min(sum(v.severity for v in adj_v), 0.30)
        para_penalty = min(sum(v.severity for v in para_v), 0.35)
        density_penalty = min(sum(v.severity for v in density_v), 0.35)

        total_penalty = adj_penalty + para_penalty + density_penalty
        score = max(0.0, 1.0 - total_penalty)

        return score, adj_v + para_v + density_v

    # ── 检测1：形容词冗余堆叠 ───────────────────────────────────

    def _check_adjective_redundancy(self, text: str) -> List[DensityViolation]:
        violations: List[DensityViolation] = []

        # 1a. 同名词前3+个定语堆叠
        seen_spans: List[Tuple[int, int]] = []
        for m in self.ADJ_STACK_PATTERN.finditer(text):
            # 过滤：若匹配片段内含冲突/转折词，是有效修辞，跳过
            snippet = m.group()
            if self._RE_CONFLICT.search(snippet):
                continue
            # 过滤重叠匹配
            if any(s <= m.start() < e for s, e in seen_spans):
                continue
            seen_spans.append((m.start(), m.end()))
            # 只报前80字以内的位置片段，避免description过长
            display = snippet[:30] + ("…" if len(snippet) > 30 else "")
            violations.append(DensityViolation(
                violation_type="adj_redundancy",
                severity=0.18,
                description=f"定语堆叠：「{display}」— 连续3+个修饰定语叠加在同一名词上",
                suggestion="保留最有画面感的1个定语，其余转化为动作或细节",
                position=f"第{self._char_pos_to_line(text, m.start())}行附近",
            ))

        # 1b. 副词叠词连用（缓缓地轻轻地…）
        for m in self.ADV_STACK_PATTERN.finditer(text):
            violations.append(DensityViolation(
                violation_type="adj_redundancy",
                severity=0.15,
                description=f"副词连用：「{m.group()}」— 相近副词叠用，语气稀释",
                suggestion="只保留一个副词，或直接写动作效果",
                position=f"第{self._char_pos_to_line(text, m.start())}行附近",
            ))

        # 1c. 填充词密集（每100字超过3个）
        char_count = max(len(text.replace(" ", "").replace("\n", "")), 1)
        filler_total = sum(text.count(w) for w in self.FILLER_WORDS)
        density_per_100 = filler_total / (char_count / 100)
        if density_per_100 > 3:
            violations.append(DensityViolation(
                violation_type="adj_redundancy",
                severity=0.12,
                description=f"填充词密集：共{filler_total}个（每百字{density_per_100:.1f}个）",
                suggestion="减少「似乎、仿佛、非常、不由得」等模糊填充词，直接用细节说话",
            ))

        return violations

    # ── 检测2：全文叙事推进比例（聚合报告，不逐段报警）────────────

    def _check_progression_ratio(self, text: str) -> List[DensityViolation]:
        violations: List[DensityViolation] = []

        # 按双换行分段；退化成整段时不做检查（无分段）
        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
        if len(paragraphs) < 3:
            return violations  # 段落太少，不判断

        no_prog: List[int] = []  # 无推进段落的序号（1-based）
        for i, para in enumerate(paragraphs, 1):
            if len(para) < 12:  # 极短段落（章节号/分隔行等）跳过
                continue
            if not self._has_progression(para) and self._is_pure_description(para):
                no_prog.append(i)

        total_valid = sum(1 for p in paragraphs if len(p.strip()) >= 12)
        if total_valid == 0:
            return violations

        ratio = len(no_prog) / total_valid

        # 阈值：纯描写比例≥60% 且绝对数≥4段，才报警（聚合为一条）
        if ratio >= 0.60 and len(no_prog) >= 4:
            seg_list = "、".join(f"第{n}段" for n in no_prog[:6])
            if len(no_prog) > 6:
                seg_list += f"等共{len(no_prog)}段"
            violations.append(DensityViolation(
                violation_type="low_progression_ratio",
                severity=0.30,
                description=f"叙事推进比例偏低：{len(no_prog)}/{total_valid}段（{ratio*100:.0f}%）属于纯描写/纯氛围，缺少角色行为或事件推进",
                suggestion=f"在以下段落中加入人物动作、认知转变或情节钩子：{seg_list}",
            ))
        elif len(no_prog) >= 6:
            # 绝对数≥6段时也报（哪怕比例未到60%）
            seg_list = "、".join(f"第{n}段" for n in no_prog[:6])
            if len(no_prog) > 6:
                seg_list += f"等共{len(no_prog)}段"
            violations.append(DensityViolation(
                violation_type="low_progression_ratio",
                severity=0.22,
                description=f"多段落（{len(no_prog)}段）缺乏叙事推进，整体节奏偏慢",
                suggestion=f"重点检查：{seg_list}",
            ))

        return violations

    # ── 检测3：信息密度阈值 ─────────────────────────────────────

    def _check_info_density(self, text: str) -> List[DensityViolation]:
        violations: List[DensityViolation] = []

        char_count = len(text.replace(" ", "").replace("\n", ""))
        if char_count < 150:
            return violations

        info_pts = 0
        info_pts += len(self._RE_INFO_ACTION.findall(text))
        info_pts += len(self._RE_INFO_DIALOGUE.findall(text)) // 2
        info_pts += len(self._RE_INFO_REVEAL.findall(text))
        info_pts += len(self._RE_INFO_DECISION.findall(text))
        info_pts += len(self._RE_INFO_CONFLICT.findall(text))
        info_pts += len(self._RE_INFO_SPATIAL.findall(text))

        density = info_pts / (char_count / 1000)
        if density < self.MIN_INFO_DENSITY:
            gap = self.MIN_INFO_DENSITY - density
            sev = min(0.25, gap * 0.06)
            violations.append(DensityViolation(
                violation_type="low_info_density",
                severity=sev,
                description=f"信息密度偏低：{density:.1f}点/千字（基准{self.MIN_INFO_DENSITY}）",
                suggestion="增加有效信息点：角色做出决策、发现新情报、产生空间位移或与他人发生真实冲突",
            ))

        return violations

    # ── 辅助：叙事推进判断（宽泛定义）──────────────────────────

    def _has_progression(self, para: str) -> bool:
        """判断段落是否含有叙事推进信号（满足任一即为有推进）"""
        return bool(
            self._RE_ACTION.search(para)
            or self._RE_DIALOGUE.search(para)
            or self._RE_DISCOVERY.search(para)
            or self._RE_CONFLICT.search(para)
            or self._RE_PSYCHE_CHANGE.search(para)
            or self._RE_SPATIAL.search(para)
        )

    def _is_pure_description(self, para: str) -> bool:
        """判断是否为纯描写（无叙事功能）。

        策略：只要满足以下任一条件即认为是纯描写：
        - 自然/感官动词≥2 且 无明确叙事主体动词
        - 文段完全没有人称代词/角色叙事迹象（全是景物）
        """
        # 明确叙事主体动词（严格版，无单字歧义）
        if self._RE_SUBJECT_ACT.search(para):
            return False
        # 感官/自然动词密集
        sensory_count = len(self._RE_SENSORY.findall(para))
        if sensory_count >= 2:
            return True
        # 全段均为环境/自然词汇（无人称代词/角色行为迹象）
        has_person_marker = bool(re.search(r'[他她它我你们]|[\u4e00-\u9fff]{2,4}(?:道|说|问|答)', para))
        if not has_person_marker and len(para) > 20:
            return True
        return False

    @staticmethod
    def _char_pos_to_line(text: str, pos: int) -> int:
        """将字符位置转换为大约的行号（1-based）"""
        return text[:pos].count("\n") + 1

    # ── 对外兼容接口 ────────────────────────────────────────────

    def compute_density_score(self, text: str) -> float:
        """计算信息密度评分（供外部调用）"""
        char_count = len(text.replace(" ", "").replace("\n", ""))
        if char_count < 50:
            return 1.0

        info_pts = 0
        info_pts += len(self._RE_INFO_ACTION.findall(text))
        info_pts += len(self._RE_INFO_DIALOGUE.findall(text)) // 2
        info_pts += len(self._RE_INFO_REVEAL.findall(text))
        info_pts += len(self._RE_INFO_DECISION.findall(text))
        info_pts += len(self._RE_INFO_CONFLICT.findall(text))
        info_pts += len(self._RE_INFO_SPATIAL.findall(text))

        density = info_pts / (char_count / 1000)
        return min(1.0, density / (self.MIN_INFO_DENSITY * 2))
