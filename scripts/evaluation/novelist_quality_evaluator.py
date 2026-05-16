"""NovelistQualityEvaluator — 小说家角度写作质量评测

评测维度（专业小说家视角）:
1. 语言纯度 (25%) — 去AI味程度，白描/暗喻/动作密度
2. 角色辨识度 (25%) — 声线独特性，对话可辨识度，行为一致性
3. 情节推进效率 (20%) — 信息密度，段落目标推进，无水段落
4. 伏笔管理 (10%) — 埋设/苏醒/回收节奏，未闭环追踪
5. 叙事节奏 (10%) — 张力曲线，动作/揭秘/大事件节奏
6. 整体文学性 (10%) — 结构美感，意象系统，叙事声音

评级标准:
- S级 (≥0.9): 专业作家水平，可直接出版
- A级 (≥0.8): 优质网文，有少量瑕疵
- B级 (≥0.7): 合格网文，有明显AI痕迹
- C级 (≥0.6): 需大幅修改，AI味重
- D级 (<0.6): 质量不合格，需重写
"""
from __future__ import annotations

import re
import math
from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional, Tuple


@dataclass
class DimensionScore:
    """单维度评分"""
    name: str
    score: float  # 0.0-1.0
    weight: float  # 权重
    details: Dict[str, Any] = field(default_factory=dict)
    issues: List[str] = field(default_factory=list)

    @property
    def weighted_score(self) -> float:
        return self.score * self.weight


@dataclass
class NovelistAssessment:
    """小说家角度评估结果"""
    grade: str  # S/A/B/C/D
    overall_score: float  # 0.0-1.0
    dimensions: List[DimensionScore] = field(default_factory=list)
    chapter_scores: List[Dict[str, Any]] = field(default_factory=list)
    cross_chapter_issues: List[str] = field(default_factory=list)
    improvement_suggestions: List[str] = field(default_factory=list)

    @property
    def total_weighted(self) -> float:
        return sum(d.weighted_score for d in self.dimensions)


class NovelistQualityEvaluator:
    """小说家角度质量评测器

    从专业小说家视角评估生成文本的写作质量。
    不同于QualityGuardrail的硬性规则检查，
    本评测器更关注文学性和阅读体验。
    """

    # 维度权重
    WEIGHTS = {
        "language_purity": 0.25,
        "character_distinctiveness": 0.25,
        "plot_efficiency": 0.20,
        "foreshadow_management": 0.10,
        "narrative_rhythm": 0.10,
        "literary_quality": 0.10,
    }

    # AI写作伪影扩展列表
    AI_ARTIFACTS = [
        # 八股文
        r'(?:首先|其次|再次|最后|此外|另外|同时|与此同时|不仅如此)[，。]',
        # 数字比喻
        r'像.*?一样.*?像.*?一样',
        r'仿佛.*?般.*?仿佛.*?般',
        # 过度理性
        r'(?:显然|无疑|显而易见|不难发现|由此可见|毫无疑问)',
        # 微表情堆叠
        r'嘴角.{0,4}(?:上扬|微动|抽动).{0,20}眼中.{0,4}(?:闪过|浮现|掠过)',
        r'眉头.{0,4}(?:微蹙|紧锁).{0,20}眼神.{0,4}(?:复杂|深邃|变化)',
        # 情绪标签
        r'(?:他|她|它|这)(?:感?到|觉得|认为|意识到)(?:一种|一阵|一股)?(?:愤怒|悲伤|恐惧|惊讶|失望|欣慰|感动|痛苦|绝望|希望)',
        # 空洞修饰
        r'极其.{0,4}(?:重要|关键|危险|强大|恐怖|震撼)',
        r'无比.{0,4}(?:强大|震撼|美丽|悲伤|愤怒)',
        # 陈述替代展示
        r'(?:气氛|空气|环境)(?:变得|变得|瞬间变得)(?:凝重|紧张|压抑|沉重|尴尬)',
    ]

    # 白描质量指标
    SHOW_DONT_TELL_PATTERNS = [
        # 动作展示情绪
        (r'(?:攥紧|握紧|攥住|抓紧).{0,6}(?:拳头|手|掌心)', 'positive'),
        (r'(?:咬紧|咬住|紧咬).{0,4}(?:牙关|嘴唇|下唇)', 'positive'),
        (r'(?:后退|退后|倒退).{0,4}(?:一步|半步|两步)', 'positive'),
        (r'(?:低头|垂首|低头不语)', 'positive'),
        # 环境映射情绪
        (r'(?:风|雨|雷|雪|云).{0,10}(?:呼啸|怒号|翻涌|肆虐)', 'positive'),
    ]

    def evaluate_chapter(self, text: str, chapter_number: int = 1,
                         character_names: List[str] = None,
                         outline: str = "") -> Dict[str, DimensionScore]:
        """评估单章质量"""
        dimensions = {}

        dimensions["language_purity"] = self._eval_language_purity(text)
        dimensions["character_distinctiveness"] = self._eval_character_distinctiveness(
            text, character_names or []
        )
        dimensions["plot_efficiency"] = self._eval_plot_efficiency(text, outline)
        dimensions["foreshadow_management"] = self._eval_foreshadow(text, chapter_number)
        dimensions["narrative_rhythm"] = self._eval_narrative_rhythm(text)
        dimensions["literary_quality"] = self._eval_literary_quality(text)

        return dimensions

    def evaluate_novel(self, chapters: List[Dict[str, Any]]) -> NovelistAssessment:
        """评估整部小说（跨章评测）

        Args:
            chapters: [{"chapter": 1, "content": "...", "outline": "..."}, ...]
        """
        all_dimension_scores = {k: [] for k in self.WEIGHTS}
        chapter_scores = []

        for ch_data in chapters:
            text = ch_data.get("content", "")
            ch_num = ch_data.get("chapter", 0)
            outline = ch_data.get("outline", "")
            char_names = ch_data.get("character_names", [])

            dims = self.evaluate_chapter(text, ch_num, char_names, outline)
            ch_score = {
                "chapter": ch_num,
                "word_count": len(text),
            }
            for k, v in dims.items():
                all_dimension_scores[k].append(v.score)
                ch_score[k] = v.score
            chapter_scores.append(ch_score)

        # 计算平均维度分数
        final_dims = []
        for dim_name, weight in self.WEIGHTS.items():
            scores = all_dimension_scores[dim_name]
            avg_score = sum(scores) / max(len(scores), 1)
            dim = DimensionScore(
                name=dim_name,
                score=avg_score,
                weight=weight,
                details={"chapter_scores": scores},
            )
            final_dims.append(dim)

        # 计算总加权分
        overall = sum(d.weighted_score for d in final_dims)
        grade = self._score_to_grade(overall)

        # 跨章检查
        cross_issues = self._cross_chapter_analysis(chapters)

        # 改进建议
        suggestions = self._generate_suggestions(final_dims, cross_issues)

        return NovelistAssessment(
            grade=grade,
            overall_score=overall,
            dimensions=final_dims,
            chapter_scores=chapter_scores,
            cross_chapter_issues=cross_issues,
            improvement_suggestions=suggestions,
        )

    # === 维度1: 语言纯度 ===
    def _eval_language_purity(self, text: str) -> DimensionScore:
        """评估语言纯度 — 去AI味程度"""
        if not text.strip():
            return DimensionScore("language_purity", 0.0, self.WEIGHTS["language_purity"])

        issues = []
        total_chars = max(len(text), 1)

        # 1. AI伪影检测
        artifact_count = 0
        for pattern in self.AI_ARTIFACTS:
            matches = re.findall(pattern, text)
            artifact_count += len(matches)
            if matches:
                issues.append(f"AI伪影: {matches[0][:30]}...")

        # AI伪影密度
        artifact_density = artifact_count / (total_chars / 1000)
        purity_score = max(0, 1.0 - artifact_density * 0.15)

        # 2. 白描占比
        show_count = 0
        for pattern, _ in self.SHOW_DONT_TELL_PATTERNS:
            show_count += len(re.findall(pattern, text))

        # 3. 形容词密度（过高=AI味）
        adj_patterns = [
            r'极其', r'无比', r'异常', r'格外', r'分外',
            r'十分', r'非常', r'特别', r'相当', r'尤为',
        ]
        adj_count = sum(len(re.findall(p, text)) for p in adj_patterns)
        adj_density = adj_count / (total_chars / 1000)

        if adj_density > 5:
            purity_score -= 0.1
            issues.append(f"形容词密度过高: {adj_density:.1f}/千字")

        # 4. 明喻密度
        simile_count = len(re.findall(r'(?:像|如|似|仿佛|宛如|犹如).{1,10}(?:一样|般|似的|一般)', text))
        simile_density = simile_count / (total_chars / 1000)
        if simile_density > 3:
            purity_score -= 0.05 * (simile_density - 3)
            issues.append(f"明喻密度过高: {simile_density:.1f}/千字")

        purity_score = max(0, min(1, purity_score))

        return DimensionScore(
            "language_purity", purity_score, self.WEIGHTS["language_purity"],
            details={
                "artifact_count": artifact_count,
                "artifact_density": round(artifact_density, 2),
                "show_count": show_count,
                "adj_density": round(adj_density, 2),
                "simile_density": round(simile_density, 2),
            },
            issues=issues[:5],
        )

    # === 维度2: 角色辨识度 ===
    def _eval_character_distinctiveness(self, text: str, character_names: List[str]) -> DimensionScore:
        """评估角色辨识度 — 声线独特性"""
        if not character_names:
            return DimensionScore("character_distinctiveness", 0.7, self.WEIGHTS["character_distinctiveness"])

        issues = []
        distinctiveness_scores = []

        # 提取对话
        dialogue_pattern = re.compile(r'[\u201c\u201d"]([^\u201c\u201d"]+)[\u201d\u201c"]')
        all_dialogues = []
        for match in dialogue_pattern.finditer(text):
            all_dialogues.append((match.group(1), match.start()))

        if not all_dialogues:
            return DimensionScore(
                "character_distinctiveness", 0.5,
                self.WEIGHTS["character_distinctiveness"],
                issues=["无对话内容"],
            )

        # 为每个角色归因对话
        char_dialogues: Dict[str, List[str]] = {name: [] for name in character_names}
        for dialogue, pos in all_dialogues:
            pre_text = text[:pos]
            closest_name = None
            closest_pos = -1
            for name in character_names:
                name_pos = pre_text.rfind(name)
                if name_pos > closest_pos:
                    closest_pos = name_pos
                    closest_name = name
            if closest_name and closest_pos >= 0:
                char_dialogues[closest_name].append(dialogue)

        # 分析每个角色的对话特征
        for name, dialogues in char_dialogues.items():
            if not dialogues:
                continue

            # 对话长度方差 — 惜字如金vs话多
            lengths = [len(d) for d in dialogues]
            avg_len = sum(lengths) / max(len(lengths), 1)

            # 句式多样性 — 陈述/反问/感叹
            statement_count = sum(1 for d in dialogues if d.endswith(('。', '，')))
            question_count = sum(1 for d in dialogues if '？' in d or '?' in d)
            exclaim_count = sum(1 for d in dialogues if '！' in d or '!' in d)

            total_d = max(len(dialogues), 1)
            diversity = 1 - abs(statement_count/total_d - 0.5)

            # 基础辨识度分
            char_score = 0.5  # 基线

            # 对话长度有差异 → 加分
            if avg_len > 20:
                char_score += 0.15  # 话多型
            elif avg_len < 10:
                char_score += 0.15  # 惜字如金型

            # 句式多样性 → 加分
            char_score += diversity * 0.15

            # 有反问/感叹 → 加分（显示声线特征）
            if question_count > 0:
                char_score += 0.1
            if exclaim_count > 0:
                char_score += 0.1

            distinctiveness_scores.append(min(char_score, 1.0))

        # 跨角色辨识度 — 对话是否可区分
        if len(char_dialogues) >= 2:
            char_avgs = {}
            for name, dialogues in char_dialogues.items():
                if dialogues:
                    char_avgs[name] = sum(len(d) for d in dialogues) / len(dialogues)

            if len(char_avgs) >= 2:
                avg_values = list(char_avgs.values())
                max_diff = max(avg_values) - min(avg_values)
                if max_diff < 5:
                    issues.append("角色对话长度差异太小，辨识度低")
                    distinctiveness_scores = [s * 0.8 for s in distinctiveness_scores]

        avg_distinctiveness = sum(distinctiveness_scores) / max(len(distinctiveness_scores), 1) if distinctiveness_scores else 0.5

        return DimensionScore(
            "character_distinctiveness", avg_distinctiveness,
            self.WEIGHTS["character_distinctiveness"],
            details={
                "character_count": len(character_names),
                "dialogue_count": len(all_dialogues),
                "char_dialogue_counts": {k: len(v) for k, v in char_dialogues.items()},
            },
            issues=issues,
        )

    # === 维度3: 情节推进效率 ===
    def _eval_plot_efficiency(self, text: str, outline: str = "") -> DimensionScore:
        """评估情节推进效率"""
        if not text.strip():
            return DimensionScore("plot_efficiency", 0.0, self.WEIGHTS["plot_efficiency"])

        issues = []
        total_chars = max(len(text), 1)

        # 1. 信息密度 — 新信息点数量
        # 检测关键情节推进标志（扩展覆盖AI隐晦推进）
        plot_markers = [
            r'发现', r'揭露', r'揭示', r'暴露', r'揭晓',
            r'突破', r'击败', r'获得', r'失去', r'牺牲',
            r'背叛', r'转变', r'觉醒', r'领悟', r'决定',
            r'抵达', r'离开', r'相遇', r'重逢', r'分别',
            r'知道', r'明白', r'确认', r'否认', r'拒绝',
            r'开始', r'结束', r'改变', r'选择', r'放弃',
            r'追', r'逃', r'战', r'斗', r'杀',
            r'死', r'活', r'伤', r'愈',
            r'信', r'疑', r'怒', r'惊',
            r'接', r'给', r'拿', r'送',
        ]
        marker_count = sum(len(re.findall(p, text)) for p in plot_markers)
        info_density = marker_count / (total_chars / 1000)

        # 2. 无水段落检测
        paragraphs = [p.strip() for p in text.split('\n') if p.strip()]
        water_count = 0
        for p in paragraphs:
            # 纯环境描写+形容词堆叠 = 水
            if (len(re.findall(r'(?:的|地|得)', p)) > len(p) / 15
                    and not re.search(r'[\u201c\u201d"]', p)
                    and not re.search(r'(?:说|道|喊|问|答|笑|哭)', p)):
                water_count += 1

        water_ratio = water_count / max(len(paragraphs), 1)

        # 3. 对话推进率 — 有信息增量的对话占比
        dialogue_pattern = re.compile(r'[\u201c\u201d"]([^\u201c\u201d"]+)[\u201d\u201c"]')
        dialogues = dialogue_pattern.findall(text)
        info_dialogues = 0
        for d in dialogues:
            # 对话中包含新信息
            if re.search(r'(?:发现|知道|原来|其实|竟然|居然|没想到|真相|秘密|答案)', d):
                info_dialogues += 1

        dialogue_progress_rate = info_dialogues / max(len(dialogues), 1)

        # 综合得分（降低info_density阈值，从8改为12）
        efficiency = 0.4 * min(info_density / 12, 1.0) + \
                     0.3 * (1 - water_ratio) + \
                     0.3 * min(dialogue_progress_rate * 2, 1.0)

        if water_ratio > 0.3:
            issues.append(f"水段落占比过高: {water_ratio:.0%}")
        if info_density < 3:
            issues.append(f"信息密度过低: {info_density:.1f}/千字")

        return DimensionScore(
            "plot_efficiency", efficiency, self.WEIGHTS["plot_efficiency"],
            details={
                "info_density": round(info_density, 2),
                "water_ratio": round(water_ratio, 2),
                "dialogue_progress_rate": round(dialogue_progress_rate, 2),
                "paragraph_count": len(paragraphs),
            },
            issues=issues,
        )

    # === 维度4: 伏笔管理 ===
    def _eval_foreshadow(self, text: str, chapter_number: int = 1) -> DimensionScore:
        """评估伏笔管理"""
        if not text.strip():
            return DimensionScore("foreshadow_management", 0.0, self.WEIGHTS["foreshadow_management"])

        # 伏笔埋设标志（扩展覆盖）
        plant_markers = [
            r'似乎.{0,20}(?:隐藏|藏有|不简单|不同寻常)',
            r'(?:不知|未知).{0,15}(?:原因|真相|秘密|目的)',
            r'(?:隐约|隐约间|恍惚).{0,20}(?:感觉|察觉|看到|听到)',
            r'(?:暗藏|隐藏|潜藏).{0,15}(?:秘密|玄机|危机)',
            r'(?:神秘|诡异|奇怪|古怪)',
            r'(?:某种|一股|一道).{0,10}(?:力量|气息|目光)',
            r'(?:秘密|真相|答案).{0,10}(?:藏在|等待|尚未)',
        ]

        # 伏笔回收标志（扩展覆盖）
        resolve_markers = [
            r'(?:原来|其实|真相|答案|终于).{0,20}(?:是|就是|在)',
            r'(?:难怪|怪不得|难怪)',
            r'(?:终于|总算|终于).{0,15}(?:明白|理解|知道|看清)',
            r'(?:一切都|所有|全部).{0,10}(?:说通了|解释了|清楚了)',
            r'(?:所以|因此|这就是).{0,15}(?:原因|理由|答案)',
        ]

        # 悬念钩子（扩展覆盖）
        hook_markers = [
            r'(?:但|然而|可是|不过).{0,30}(?:不知|未知|还会|将要)',
            r'(?:远处|身后|黑暗中).{0,20}(?:传来|出现|浮现)',
            r'(?:不知道|不确定|未必|也许).{0,20}(?:会发生|能否|是不是)',
            r'(?:等待着|即将|马上|很快).{0,15}(?:到来|发生|出现)',
        ]

        plant_count = sum(len(re.findall(p, text)) for p in plant_markers)
        resolve_count = sum(len(re.findall(p, text)) for p in resolve_markers)
        hook_count = sum(len(re.findall(p, text)) for p in hook_markers)

        # 评分逻辑
        # 前期应多埋设，后期应多回收
        if chapter_number <= 5:
            # 开局期：埋设+钩子更重要（降低阈值从2/1改为1/1）
            score = 0.4 * min(plant_count / 1, 1.0) + \
                    0.4 * min(hook_count / 1, 1.0) + \
                    0.2 * 0.5  # 回收基础分
        else:
            # 发展/收敛期：回收更重要
            score = 0.3 * min(plant_count / 1, 1.0) + \
                    0.2 * min(hook_count / 1, 1.0) + \
                    0.5 * min(resolve_count / 1, 1.0)

        return DimensionScore(
            "foreshadow_management", score, self.WEIGHTS["foreshadow_management"],
            details={
                "plant_count": plant_count,
                "resolve_count": resolve_count,
                "hook_count": hook_count,
                "chapter": chapter_number,
            },
        )

    # === 维度5: 叙事节奏 ===
    def _eval_narrative_rhythm(self, text: str) -> DimensionScore:
        """评估叙事节奏 — 张力曲线"""
        if not text.strip():
            return DimensionScore("narrative_rhythm", 0.0, self.WEIGHTS["narrative_rhythm"])

        issues = []

        # 1. 段落长度变化 — 节奏变化指标
        paragraphs = [p.strip() for p in text.split('\n') if p.strip()]
        if len(paragraphs) < 3:
            return DimensionScore("narrative_rhythm", 0.3, self.WEIGHTS["narrative_rhythm"],
                                  issues=["段落过少，节奏单调"])

        para_lengths = [len(p) for p in paragraphs]
        avg_len = sum(para_lengths) / max(len(para_lengths), 1)

        # 标准差 — 越大节奏变化越明显
        variance = sum((l - avg_len) ** 2 for l in para_lengths) / max(len(para_lengths), 1)
        std_dev = math.sqrt(variance)
        rhythm_variation = min(std_dev / max(avg_len, 1), 1.0)

        # 2. 动作节奏 — 短句=快节奏
        short_sentences = 0
        long_sentences = 0
        for p in paragraphs:
            sentences = re.split(r'[。！？；]', p)
            for s in sentences:
                s = s.strip()
                if len(s) <= 10:
                    short_sentences += 1
                elif len(s) >= 40:
                    long_sentences += 1

        total_sentences = max(short_sentences + long_sentences, 1)
        fast_ratio = short_sentences / total_sentences

        # 3. 张力标志密度
        tension_markers = [
            r'(?:突然|猛地|骤然|蓦然|霎时|刹那)',
            r'(?:危险|致命|生死|绝境|危机)',
            r'(?:惊|震|骇|恐|惧)',
            r'(?:逃|追|战|斗|搏)',
        ]
        tension_count = sum(len(re.findall(p, text)) for p in tension_markers)
        tension_density = tension_count / max(len(text) / 1000, 1)

        # 综合
        rhythm_score = 0.3 * rhythm_variation + \
                       0.3 * min(fast_ratio * 3, 1.0) + \
                       0.4 * min(tension_density / 5, 1.0)

        if rhythm_variation < 0.3:
            issues.append("段落长度变化太小，节奏单调")
        if fast_ratio < 0.1:
            issues.append("缺少短句，动作场景节奏不够快")

        return DimensionScore(
            "narrative_rhythm", rhythm_score, self.WEIGHTS["narrative_rhythm"],
            details={
                "rhythm_variation": round(rhythm_variation, 3),
                "fast_ratio": round(fast_ratio, 3),
                "tension_density": round(tension_density, 2),
                "paragraph_count": len(paragraphs),
            },
            issues=issues,
        )

    # === 维度6: 整体文学性 ===
    def _eval_literary_quality(self, text: str) -> DimensionScore:
        """评估整体文学性"""
        if not text.strip():
            return DimensionScore("literary_quality", 0.0, self.WEIGHTS["literary_quality"])

        issues = []
        total_chars = max(len(text), 1)

        # 1. 意象系统 — 重复出现的核心意象
        image_words = [
            r'(?:月|风|雨|雪|花|叶|血|火|水|雾|霜|雷|光|影|尘|沙)',
        ]
        image_count = sum(len(re.findall(p, text)) for p in image_words)
        image_density = image_count / (total_chars / 1000)

        # 2. 感官多样性 — 视/听/触/嗅/味
        sensory = {
            "visual": len(re.findall(r'(?:看|望|见|视|瞪|瞥|注视|凝视)', text)),
            "auditory": len(re.findall(r'(?:听|闻声|声响|声音|回响|轰鸣|低语)', text)),
            "tactile": len(re.findall(r'(?:摸|触|冰|热|冷|暖|刺|痛|麻|颤)', text)),
            "olfactory": len(re.findall(r'(?:嗅|闻|气味|香味|腥味|血腥)', text)),
        }
        sensory_types = sum(1 for v in sensory.values() if v > 0)

        # 3. 句式多样性
        sentences = re.split(r'[。！？]', text)
        sentences = [s.strip() for s in sentences if s.strip()]

        if sentences:
            sent_lengths = [len(s) for s in sentences]
            avg_sent_len = sum(sent_lengths) / max(len(sent_lengths), 1)
            # 好的文学文本句长应在10-25字之间
            len_score = 1 - abs(avg_sent_len - 18) / 18
            len_score = max(0, min(1, len_score))
        else:
            len_score = 0.3

        # 综合
        literary_score = 0.3 * min(image_density / 15, 1.0) + \
                         0.3 * sensory_types / 4 + \
                         0.4 * len_score

        if sensory_types < 2:
            issues.append(f"感官描写单一，仅{sensory_types}种感官")

        return DimensionScore(
            "literary_quality", literary_score, self.WEIGHTS["literary_quality"],
            details={
                "image_density": round(image_density, 2),
                "sensory_types": sensory_types,
                "sensory": sensory,
                "avg_sentence_length": round(avg_sent_len, 1) if sentences else 0,
            },
            issues=issues,
        )

    # === 跨章分析 ===
    def _cross_chapter_analysis(self, chapters: List[Dict[str, Any]]) -> List[str]:
        """跨章节一致性检查"""
        issues = []

        if len(chapters) < 2:
            return issues

        # 1. 角色名突变检测
        all_names = set()
        for ch in chapters:
            text = ch.get("content", "")
            # 提取2-4字中文名
            names = re.findall(r'[\u4e00-\u9fff]{2,4}(?=说道|道|喊|问|答|笑)', text)
            all_names.update(names)

        # 2. 字数波动检测
        word_counts = [len(ch.get("content", "")) for ch in chapters]
        if word_counts:
            avg_wc = sum(word_counts) / len(word_counts)
            for i, wc in enumerate(word_counts):
                if wc < avg_wc * 0.4:
                    issues.append(f"第{i+1}章字数异常偏少: {wc}字 (平均{avg_wc:.0f}字)")

        # 3. 章首衔接检测
        for i in range(1, len(chapters)):
            prev_text = chapters[i-1].get("content", "")
            curr_text = chapters[i].get("content", "")
            # 简单检测：当前章首是否与前章末有关联
            if prev_text and curr_text:
                prev_end = prev_text[-50:] if len(prev_text) > 50 else prev_text
                curr_start = curr_text[:50] if len(curr_text) > 50 else curr_text
                # 检查是否有角色名在两章中出现
                prev_names = set(re.findall(r'[\u4e00-\u9fff]{2,4}', prev_end))
                curr_names = set(re.findall(r'[\u4e00-\u9fff]{2,4}', curr_start))
                overlap = prev_names & curr_names
                if not overlap and len(prev_names) > 0:
                    issues.append(f"第{i+1}章与前章缺乏角色名衔接")

        return issues

    # === 生成建议 ===
    def _generate_suggestions(self, dimensions: List[DimensionScore],
                              cross_issues: List[str]) -> List[str]:
        """根据评测结果生成改进建议"""
        suggestions = []

        for dim in dimensions:
            if dim.score < 0.6:
                if dim.name == "language_purity":
                    suggestions.append(
                        "语言纯度不足：减少AI伪影（八股文/微表情/情绪标签），"
                        "增加白描和动作描写，用1个精准动词替代3个形容词"
                    )
                elif dim.name == "character_distinctiveness":
                    suggestions.append(
                        "角色辨识度不足：为每个角色建立独特声线（句式/口头禅/语气），"
                        "让读者不看名字也能分辨是谁在说话"
                    )
                elif dim.name == "plot_efficiency":
                    suggestions.append(
                        "情节推进效率低：减少纯环境描写段落，让对话携带信息增量，"
                        "每段至少推进一个小目标"
                    )
                elif dim.name == "foreshadow_management":
                    suggestions.append(
                        "伏笔管理需改善：前期多埋设悬念钩子，中后期逐步回收，"
                        "避免大量未闭环伏笔堆积"
                    )
                elif dim.name == "narrative_rhythm":
                    suggestions.append(
                        "叙事节奏平淡：增加短句（动作场景），减少长段落堆叠，"
                        "关键转折用骤然/猛地等节奏加速词"
                    )
                elif dim.name == "literary_quality":
                    suggestions.append(
                        "文学性不足：建立核心意象系统（月/风/血等重复出现），"
                        "增加多感官描写（听/触/嗅），调整句长至10-25字"
                    )
            elif dim.score < 0.8:
                if dim.name == "language_purity":
                    suggestions.append(
                        "语言纯度可提升：注意减少明喻堆叠和空洞修饰词"
                    )
                elif dim.name == "character_distinctiveness":
                    suggestions.append(
                        "角色辨识度可提升：增加角色间的对话长度差异和句式差异"
                    )

        for issue in cross_issues:
            suggestions.append(f"跨章问题: {issue}")

        return suggestions

    @staticmethod
    def _score_to_grade(score: float) -> str:
        if score >= 0.9:
            return "S"
        elif score >= 0.8:
            return "A"
        elif score >= 0.7:
            return "B"
        elif score >= 0.6:
            return "C"
        else:
            return "D"
