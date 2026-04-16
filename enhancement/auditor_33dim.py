"""
33维审计系统
从角色、逻辑、叙事、文风、结构5个大类33个维度全面审计章节
"""

import re
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from .revision_loop import AuditIssue, AuditResult


# ========================
# 审计维度定义
# ========================

DIMENSIONS = {
    # 角色维度（8个）
    "C1_character_memory": {
        "name": "角色记忆",
        "category": "character",
        "description": "角色是否"记起"了从未亲眼见过的事",
        "severity_default": "critical",
        "weight": 1.5
    },
    "C2_character_consistency": {
        "name": "角色一致性",
        "category": "character",
        "description": "行为是否符合人设（性格/能力/弱点）",
        "severity_default": "critical",
        "weight": 2.0
    },
    "C3_character_ability_boundary": {
        "name": "角色能力边界",
        "category": "character",
        "description": "角色做了一件能力做不到的事",
        "severity_default": "critical",
        "weight": 1.5
    },
    "C4_relationship_change": {
        "name": "角色关系变化",
        "category": "character",
        "description": "关系变化是否有铺垫和逻辑",
        "severity_default": "medium",
        "weight": 1.0
    },
    "C5_perspective_limit": {
        "name": "视角限制",
        "category": "character",
        "description": "视角人物知道的信息是否超出范围",
        "severity_default": "critical",
        "weight": 1.5
    },
    "C6_emotional_arc": {
        "name": "角色情绪弧线",
        "category": "character",
        "description": "情绪变化是否平滑、有迹可循",
        "severity_default": "medium",
        "weight": 1.0
    },
    "C7_death_reasonableness": {
        "name": "角色死亡合理性",
        "category": "character",
        "description": "角色死亡是否合理、是否需要更多铺垫",
        "severity_default": "critical",
        "weight": 1.5
    },
    "C8_side_character_function": {
        "name": "配角功能",
        "category": "character",
        "description": "配角是否只是工具人，有没有自己的性格",
        "severity_default": "minor",
        "weight": 0.5
    },
    
    # 逻辑维度（6个）
    "L1_causation": {
        "name": "因果逻辑",
        "category": "logic",
        "description": "事件A是否必然导致事件B",
        "severity_default": "critical",
        "weight": 2.0
    },
    "L2_timeline_contradiction": {
        "name": "时间线矛盾",
        "category": "logic",
        "description": "同一时间点出现两个矛盾的事件",
        "severity_default": "critical",
        "weight": 2.0
    },
    "L3_motivation_missing": {
        "name": "动机缺失",
        "category": "logic",
        "description": "角色做重要决定时是否交代了动机",
        "severity_default": "critical",
        "weight": 1.5
    },
    "L4_resource_conservation": {
        "name": "资源守恒",
        "category": "logic",
        "description": "物品/金钱/能力使用后是否减少/消耗",
        "severity_default": "medium",
        "weight": 1.0
    },
    "L5_knowledge_acquisition": {
        "name": "知识获取",
        "category": "logic",
        "description": "角色获得某个信息是否有合理渠道",
        "severity_default": "critical",
        "weight": 1.5
    },
    "L6_physics_rules": {
        "name": "物理规则",
        "category": "logic",
        "description": "世界观内的物理规则是否被打破",
        "severity_default": "critical",
        "weight": 1.5
    },
    
    # 叙事维度（7个）
    "N1_foreshadow_unresolved": {
        "name": "伏笔未回收",
        "category": "narrative",
        "description": "铺垫过的钩子是否有回收",
        "severity_default": "medium",
        "weight": 1.0
    },
    "N2_foreshadow_insufficient": {
        "name": "伏笔铺垫不足",
        "category": "narrative",
        "description": "回收伏笔时是否提供了足够线索",
        "severity_default": "medium",
        "weight": 1.0
    },
    "N3_suspense_maintenance": {
        "name": "悬念维持",
        "category": "narrative",
        "description": "悬念是否在合适时机释放",
        "severity_default": "medium",
        "weight": 1.0
    },
    "N4_information_rhythm": {
        "name": "信息节奏",
        "category": "narrative",
        "description": "重要信息是否在合适时机披露",
        "severity_default": "medium",
        "weight": 1.0
    },
    "N5_subplot_drift": {
        "name": "支线游离",
        "category": "narrative",
        "description": "支线是否与主线有足够关联",
        "severity_default": "medium",
        "weight": 0.8
    },
    "N6_chapter_ending_hook": {
        "name": "章节结尾钩子",
        "category": "narrative",
        "description": "每章结尾是否有吸引人继续读的钩子",
        "severity_default": "minor",
        "weight": 0.5
    },
    "N7_redundant_description": {
        "name": "冗余描写",
        "category": "narrative",
        "description": "是否有对情节毫无推进的冗余段落",
        "severity_default": "minor",
        "weight": 0.5
    },
    
    # 文风维度（6个）
    "S1_ai_pattern": {
        "name": "AI痕迹",
        "category": "style",
        "description": "高频词、句式单调、过度总结",
        "severity_default": "medium",
        "weight": 1.0
    },
    "S2_dialogue_naturalness": {
        "name": "对话自然度",
        "category": "style",
        "description": "对话是否像真人说话",
        "severity_default": "medium",
        "weight": 1.0
    },
    "S3_description_specificity": {
        "name": "描写具体性",
        "category": "style",
        "description": "是否用具体细节代替抽象描述",
        "severity_default": "minor",
        "weight": 0.5
    },
    "S4_sentence_variation": {
        "name": "句式变化",
        "category": "style",
        "description": "长短句是否有变化",
        "severity_default": "minor",
        "weight": 0.5
    },
    "S5_sensory_layers": {
        "name": "感官层次",
        "category": "style",
        "description": "是否有多感官的描写（视觉/听觉/嗅觉/触觉）",
        "severity_default": "minor",
        "weight": 0.5
    },
    "S6_style_consistency": {
        "name": "语言风格一致性",
        "category": "style",
        "description": "是否符合当前题材的风格要求",
        "severity_default": "medium",
        "weight": 1.0
    },
    
    # 结构维度（6个）
    "ST1_pacing_distribution": {
        "name": "节奏分布",
        "category": "structure",
        "description": "章节内紧张/平缓段落是否合理分布",
        "severity_default": "medium",
        "weight": 1.0
    },
    "ST2_chapter_goal_achieved": {
        "name": "章节目标达成",
        "category": "structure",
        "description": "本章是否完成了设定的写作目标",
        "severity_default": "critical",
        "weight": 1.5
    },
    "ST3_outline_deviation": {
        "name": "大纲偏离",
        "category": "structure",
        "description": "是否严重偏离了预先设定的大纲",
        "severity_default": "critical",
        "weight": 1.5
    },
    "ST4_word_count_governance": {
        "name": "字数治理",
        "category": "structure",
        "description": "字数是否在允许范围内",
        "severity_default": "medium",
        "weight": 0.8
    },
    "ST5_scene_transition": {
        "name": "场景转换",
        "category": "structure",
        "description": "场景转换是否平滑、是否交代了时间/地点变化",
        "severity_default": "medium",
        "weight": 1.0
    },
    "ST6_paragraph_length": {
        "name": "段落长度",
        "category": "structure",
        "description": "是否有超长段落影响阅读体验",
        "severity_default": "minor",
        "weight": 0.5
    }
}


@dataclass
class AuditDimension:
    """审计维度"""
    id: str
    name: str
    category: str
    description: str
    severity_default: str
    weight: float


class Auditor33Dim:
    """
    33维审计器
    
    支持通过LLM进行深度审计，也支持基于规则的快速检查。
    """
    
    # AI痕迹词表
    AI_FORBIDDEN_WORDS = {
        "然而", "因此", "值得注意的是", "综上所述", "显而易见",
        "实际上", "毫无疑问", "毋庸置疑", "不难发现", "有目共睹",
        "众所周知", "不言而喻", "总的来说", "总之", "换句话说",
        "与此同时", "无独有偶", "更值得一提的是", "首先", "其次",
        "最后", "综上所述", "由此可见", "总而言之"
    }
    
    # AI句式模式
    AI_PATTERNS = [
        r"^首先，",
        r"^其次，",
        r"^最后，",
        r"^总而言之，",
        r"^由此可见，",
        r"他[是否]?[不禁|不由得]?想[到|起]",
        r"他的[内心|心里]活动",
        r"这是一个[巨大|重要|关键]的[时刻|转折|挑战)",
        r"故事继续",
        r"与此同时",
    ]
    
    def __init__(
        self,
        llm_call_func=None,
        truth_files_dir: str = "story/truth_files",
        genre: str = None
    ):
        """
        Args:
            llm_call_func: LLM调用函数，签名: (prompt: str) -> str
            truth_files_dir: 真相文件目录
            genre: 当前题材
        """
        self.llm_call_func = llm_call_func
        self.truth_files_dir = truth_files_dir
        self.genre = genre
        self._truth_cache = {}
    
    def audit(
        self,
        text: str,
        chapter_num: int,
        truth_files: Dict[str, str] = None,
        genre: str = None
    ) -> AuditResult:
        """
        执行完整审计
        
        Args:
            text: 章节文本
            chapter_num: 章节编号
            truth_files: 真相文件字典
            genre: 题材
            
        Returns:
            AuditResult
        """
        issues = []
        genre = genre or self.genre
        
        # 1. 基于规则的快速检查
        rule_issues = self._run_rule_based_checks(text, chapter_num)
        issues.extend(rule_issues)
        
        # 2. 基于LLM的深度审计（如果提供了LLM）
        if self.llm_call_func:
            llm_issues = self._run_llm_audit(text, chapter_num, truth_files, genre)
            issues.extend(llm_issues)
        
        # 3. 计算各维度评分
        dimension_scores = self._calculate_dimension_scores(issues)
        
        # 4. 计算总分
        total_score = self._calculate_total_score(dimension_scores)
        
        # 5. 判断是否通过（70分为界）
        passed = total_score >= 70 and len([
            i for i in issues if i.severity == "critical"
        ]) == 0
        
        return AuditResult(
            chapter_num=chapter_num,
            total_score=total_score,
            dimension_scores=dimension_scores,
            issues=issues,
            passed=passed
        )
    
    def _run_rule_based_checks(
        self,
        text: str,
        chapter_num: int
    ) -> List[AuditIssue]:
        """运行基于规则的检查"""
        issues = []
        lines = text.split("\n")
        
        # === S1: AI痕迹检查 ===
        issues.extend(self._check_ai_patterns(text, lines))
        
        # === S2: 对话自然度检查 ===
        issues.extend(self._check_dialogue_naturalness(lines))
        
        # === S4: 句式变化检查 ===
        issues.extend(self._check_sentence_variation(lines))
        
        # === N7: 冗余描写检查 ===
        issues.extend(self._check_redundant_description(text, lines))
        
        # === ST4: 字数治理 ===
        issues.extend(self._check_word_count(text, chapter_num))
        
        # === ST6: 段落长度 ===
        issues.extend(self._check_paragraph_length(lines))
        
        return issues
    
    def _check_ai_patterns(
        self,
        text: str,
        lines: List[str]
    ) -> List[AuditIssue]:
        """检查AI痕迹"""
        issues = []
        
        # 检查禁用词
        found_words = []
        for word in self.AI_FORBIDDEN_WORDS:
            if word in text:
                # 找到位置
                for i, line in enumerate(lines):
                    if word in line:
                        found_words.append((word, i + 1))
        
        if found_words:
            words_text = "、".join([f"'{w}'" for w, _ in found_words[:5]])
            location = f"第{found_words[0][1]}行等"
            issues.append(AuditIssue(
                dimension="style",
                sub_dimension="S1",
                type="forbidden_word",
                severity="medium",
                title="使用了AI痕迹词",
                description=f"发现禁用词: {words_text}，共{found_words.__len__()}处",
                location=location,
                suggestion="替换为更口语化、自然的表达"
            ))
        
        # 检查AI句式模式
        for pattern in self.AI_PATTERNS:
            matches = []
            for i, line in enumerate(lines):
                if re.search(pattern, line):
                    matches.append(i + 1)
            if matches:
                issues.append(AuditIssue(
                    dimension="style",
                    sub_dimension="S1",
                    type="ai_pattern",
                    severity="medium",
                    title=f"使用了AI常见句式",
                    description=f"发现{matches.__len__()}处疑似AI句式",
                    location=f"第{matches[0]}行等",
                    suggestion="改写为更自然的表达，避免使用'首先、其次、最后'等模板句式"
                ))
                break  # 只报告一种模式
        
        return issues
    
    def _check_dialogue_naturalness(
        self,
        lines: List[str]
    ) -> List[AuditIssue]:
        """检查对话自然度"""
        issues = []
        unnatural_count = 0
        
        for i, line in enumerate(lines):
            # 检测对话行
            if '"' in line or '"' in line or '「' in line:
                # 检查是否过于书面化
                if any(kw in line for kw in ["综上所述", "因此", "然而"]):
                    unnatural_count += 1
        
        if unnatural_count > 3:
            issues.append(AuditIssue(
                dimension="style",
                sub_dimension="S2",
                type="unnatural_dialogue",
                severity="medium",
                title="对话过于书面化",
                description=f"发现{unnatural_count}处对话使用了书面语",
                location="多处",
                suggestion="对话应该口语化，有停顿、有废话、有潜台词"
            ))
        
        return issues
    
    def _check_sentence_variation(
        self,
        lines: List[str]
    ) -> List[AuditIssue]:
        """检查句式变化"""
        issues = []
        
        # 检查连续相同句式开头
        consecutive = 0
        prev_start = None
        problematic_lines = []
        
        for line in lines:
            if len(line.strip()) > 5:
                # 提取句子开头
                words = line.strip().split("，")
                if words:
                    start = words[0][:3] if len(words[0]) >= 3 else words[0]
                    if start == prev_start and len(start) > 0:
                        consecutive += 1
                        problematic_lines.append(line.strip()[:20])
                    else:
                        consecutive = 0
                    prev_start = start
        
        if consecutive >= 3:
            issues.append(AuditIssue(
                dimension="style",
                sub_dimension="S4",
                type="monotonous_start",
                severity="minor",
                title="句子开头变化不足",
                description="连续多行句子开头相同",
                location="连续段落",
                suggestion="增加句子开头变化，避免整齐划一"
            ))
        
        return issues
    
    def _check_redundant_description(
        self,
        text: str,
        lines: List[str]
    ) -> List[AuditIssue]:
        """检查冗余描写"""
        issues = []
        
        # 检查是否有无意义的总结段
        for i, line in enumerate(lines):
            stripped = line.strip()
            # 检测段尾升华
            if any(kw in stripped for kw in ["这让他明白", "从此以后", "就这样", "故事到此"]):
                if len(stripped) < 50:  # 短总结段
                    issues.append(AuditIssue(
                        dimension="narrative",
                        sub_dimension="N7",
                        type="redundant_summary",
                        severity="minor",
                        title="发现总结性/升华段",
                        description=stripped,
                        location=f"第{i+1}行",
                        suggestion="删除总结句，让读者自己体会"
                    ))
        
        return issues
    
    def _check_word_count(
        self,
        text: str,
        chapter_num: int
    ) -> List[AuditIssue]:
        """检查字数"""
        issues = []
        
        # 简单按字符数估算（中文约2字符=1词）
        char_count = len(text.replace("\n", "").replace(" ", ""))
        word_estimate = char_count // 2
        
        target = 14000
        min_allowed = 12600
        max_allowed = 15400
        
        if word_estimate < min_allowed:
            issues.append(AuditIssue(
                dimension="structure",
                sub_dimension="ST4",
                type="word_count_too_short",
                severity="medium",
                title=f"字数不足 ({word_estimate})",
                description=f"字数约{word_estimate}字，低于最低要求{min_allowed}字",
                location="整章",
                suggestion="补充内容至目标字数"
            ))
        elif word_estimate > max_allowed:
            issues.append(AuditIssue(
                dimension="structure",
                sub_dimension="ST4",
                type="word_count_too_long",
                severity="medium",
                title=f"字数超出 ({word_estimate})",
                description=f"字数约{word_estimate}字，高于最高限制{max_allowed}字",
                location="整章",
                suggestion="精简内容至允许范围内"
            ))
        
        return issues
    
    def _check_paragraph_length(
        self,
        lines: List[str]
    ) -> List[AuditIssue]:
        """检查段落长度"""
        issues = []
        long_paragraph_lines = []
        current_para_start = 1
        current_para_len = 0
        
        for i, line in enumerate(lines):
            if line.strip() == "":
                if current_para_len > 300:  # 超长段落
                    long_paragraph_lines.append((current_para_start, current_para_len))
                current_para_start = i + 2
                current_para_len = 0
            else:
                current_para_len += len(line)
        
        if long_paragraph_lines:
            issues.append(AuditIssue(
                dimension="structure",
                sub_dimension="ST6",
                type="long_paragraph",
                severity="minor",
                title=f"发现{len(long_paragraph_lines)}处超长段落",
                description="段落超过300字，影响阅读体验",
                location=f"约第{long_paragraph_lines[0][0]}行",
                suggestion="拆分长段落，增加呼吸感"
            ))
        
        return issues
    
    def _run_llm_audit(
        self,
        text: str,
        chapter_num: int,
        truth_files: Dict[str, str],
        genre: str
    ) -> List[AuditIssue]:
        """基于LLM进行深度审计"""
        if not self.llm_call_func:
            return []
        
        # 构建审计Prompt
        prompt = self._build_llm_audit_prompt(text, chapter_num, truth_files, genre)
        
        try:
            response = self.llm_call_func(prompt)
            # 解析LLM返回的问题
            issues = self._parse_llm_audit_response(response)
            return issues
        except Exception as e:
            # LLM审计失败时返回空列表
            return []
    
    def _build_llm_audit_prompt(
        self,
        text: str,
        chapter_num: int,
        truth_files: Dict[str, str],
        genre: str
    ) -> str:
        """构建LLM审计Prompt"""
        truth_context = ""
        if truth_files:
            truth_context = "\n\n".join([
                f"### {name}\n{content[:500]}"
                for name, content in truth_files.items()
            ])
        
        return f"""## 任务：33维深度审计

你是专业的网文编辑，需要对第{chapter_num}章进行深度审计。

### 题材
{genre or "未指定"}

### 真相文件（参考事实）
{truth_context}

### 待审计文本
{text[:8000]}

### 审计维度（33个）

**角色维度：** 角色记忆(C1)、角色一致性(C2)、能力边界(C3)、关系变化(C4)、视角限制(C5)、情绪弧线(C6)、死亡合理性(C7)、配角功能(C8)

**逻辑维度：** 因果逻辑(L1)、时间线矛盾(L2)、动机缺失(L3)、资源守恒(L4)、知识获取(L5)、物理规则(L6)

**叙事维度：** 伏笔未回收(N1)、伏笔铺垫不足(N2)、悬念维持(N3)、信息节奏(N4)、支线游离(N5)、章节结尾钩子(N6)、冗余描写(N7)

**文风维度：** AI痕迹(S1)、对话自然度(S2)、描写具体性(S3)、句式变化(S4)、感官层次(S5)、风格一致性(S6)

**结构维度：** 节奏分布(ST1)、章节目标达成(ST2)、大纲偏离(ST3)、字数治理(ST4)、场景转换(ST5)、段落长度(ST6)

### 输出格式

请输出JSON格式的审计结果：

```json
{{
  "issues": [
    {{
      "dimension": "logic",
      "sub_dimension": "L3",
      "type": "motivation_missing",
      "severity": "critical/medium/minor",
      "title": "问题简述",
      "description": "详细描述",
      "location": "第X行或'整章'",
      "suggestion": "修订建议"
    }}
  ]
}}
```

请仔细检查每个维度，发现问题时按格式输出。如果某维度没有问题，可以不输出。
"""
    
    def _parse_llm_audit_response(self, response: str) -> List[AuditIssue]:
        """解析LLM返回的审计结果"""
        issues = []
        
        try:
            # 尝试提取JSON
            import json
            json_match = re.search(r'\{[\s\S]*"issues"[\s\S]*\}', response)
            if json_match:
                data = json.loads(json_match.group())
                for item in data.get("issues", []):
                    issues.append(AuditIssue(
                        dimension=item.get("dimension", "unknown"),
                        sub_dimension=item.get("sub_dimension", ""),
                        type=item.get("type", ""),
                        severity=item.get("severity", "medium"),
                        title=item.get("title", ""),
                        description=item.get("description", ""),
                        location=item.get("location", "未知"),
                        suggestion=item.get("suggestion", "")
                    ))
        except:
            pass
        
        return issues
    
    def _calculate_dimension_scores(
        self,
        issues: List[AuditIssue]
    ) -> Dict[str, int]:
        """计算各维度评分"""
        scores = {
            "character": 100,
            "logic": 100,
            "narrative": 100,
            "style": 100,
            "structure": 100
        }
        
        # 各维度权重
        weights = {
            "character": 1.0,
            "logic": 1.2,   # 逻辑权重稍高
            "narrative": 1.0,
            "style": 0.8,   # 文风权重稍低
            "structure": 1.0
        }
        
        # 扣分规则
        deduction = {
            "critical": 20,
            "medium": 8,
            "minor": 3
        }
        
        # 按类别统计问题
        category_issues = {}
        for issue in issues:
            cat = issue.dimension
            if cat not in category_issues:
                category_issues[cat] = {"critical": 0, "medium": 0, "minor": 0}
            category_issues[cat][issue.severity] += 1
        
        # 计算每个类别的分数
        for cat, counts in category_issues.items():
            total_deduct = (
                counts["critical"] * deduction["critical"] +
                counts["medium"] * deduction["medium"] +
                counts["minor"] * deduction["minor"]
            )
            scores[cat] = max(0, int(100 - total_deduct * weights.get(cat, 1.0)))
        
        return scores
    
    def _calculate_total_score(self, dimension_scores: Dict[str, int]) -> int:
        """计算总分"""
        # 加权平均
        weights = {
            "character": 1.0,
            "logic": 1.2,
            "narrative": 1.0,
            "style": 0.8,
            "structure": 1.0
        }
        
        total_weight = sum(weights.values())
        weighted_sum = sum(scores * weights[dim] for dim, scores in dimension_scores.items())
        
        return int(weighted_sum / total_weight)
    
    def print_summary(self, result: AuditResult) -> None:
        """打印审计摘要"""
        print("=" * 50)
        print(f"Chapter {result.chapter_num} 审计报告")
        print("=" * 50)
        
        grade = "A" if result.total_score >= 90 else \
                "B" if result.total_score >= 80 else \
                "C" if result.total_score >= 70 else "D"
        
        print(f"综合评分: {result.total_score}/100 ({grade} {'良好' if result.total_score >= 80 else '合格' if result.total_score >= 70 else '不合格'})")
        
        # 维度评分
        dim_names = {
            "character": "角色",
            "logic": "逻辑",
            "narrative": "叙事",
            "style": "文风",
            "structure": "结构"
        }
        for dim, score in result.dimension_scores.items():
            icon = "✅" if score >= 80 else "⚠️" if score >= 70 else "❌"
            print(f"  {dim_names.get(dim, dim)}维度: {score}/100 {icon}")
        
        # 问题统计
        critical = result.get_critical_issues()
        medium = result.get_medium_issues()
        minor = result.get_minor_issues()
        
        print(f"\n发现问题: {len(result.issues)} 个")
        if critical:
            print(f"  🔴 critical: {len(critical)}")
        if medium:
            print(f"  🟡 medium: {len(medium)}")
        if minor:
            print(f"  ⚪ minor: {len(minor)}")
        
        # 关键问题
        if critical:
            print("\n关键问题（必须修复）:")
            for issue in critical[:5]:
                print(f"  🔴 [{issue.sub_dimension}] {issue.title}")
                print(f"      位置: {issue.location}")
                print(f"      建议: {issue.suggestion}")
        
        print(f"\n通过: {'是' if result.passed else '否'}")


if __name__ == "__main__":
    # 模拟测试
    auditor = Auditor33Dim()
    
    test_text = """
    他微微一笑，心中充满了复杂的情绪。然而，他知道这是唯一的选择。
    
    就在这时，天空突然暗了下来。首先，他感到一股强大的压力从天而降。
    其次，地面开始震动。最后，一切都安静了。
    
    主角林烬站在城墙上，俯瞰着整个城市。他的内心活动非常复杂。
    
    '我们必须离开这里。'他说道。'因此，我们要做好准备。'
    
    总之，这就是故事的全部。他的嘴角抽动了一下。他想哭，但最终没有。
    
    主角突然决定离开师门，因为他需要去寻找真相。
    """
    
    result = auditor.audit(test_text, 5)
    auditor.print_summary(result)
