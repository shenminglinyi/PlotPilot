"""
自动修订循环
写章节 → 审计 → 不通过 → 修订 → 再审计 → ... → 通过
"""

from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime
import json
from pathlib import Path


@dataclass
class AuditIssue:
    """审计问题"""
    dimension: str      # 维度，如 "logic", "character", "style"
    sub_dimension: str # 子维度，如 "L3", "C2"
    type: str          # 问题类型，如 "logic_hole", "ai_pattern"
    severity: str      # critical / medium / minor
    title: str        # 简述
    description: str # 详细描述
    location: str      # 位置，如 "第124行"
    suggestion: str   # 修订建议
    fixed: bool = False  # 是否已修复


@dataclass
class AuditResult:
    """审计结果"""
    chapter_num: int
    total_score: int
    dimension_scores: Dict[str, int]
    issues: List[AuditIssue]
    passed: bool
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    
    def get_critical_issues(self) -> List[AuditIssue]:
        return [i for i in self.issues if i.severity == "critical"]
    
    def get_medium_issues(self) -> List[AuditIssue]:
        return [i for i in self.issues if i.severity == "medium"]
    
    def get_minor_issues(self) -> List[AuditIssue]:
        return [i for i in self.issues if i.severity == "minor"]
    
    def get_issues_by_type(self, type_prefix: str) -> List[AuditIssue]:
        return [i for i in self.issues if i.type.startswith(type_prefix)]
    
    def to_dict(self) -> dict:
        return {
            "chapter_num": self.chapter_num,
            "total_score": self.total_score,
            "dimension_scores": self.dimension_scores,
            "passed": self.passed,
            "issues": [
                {
                    "dimension": i.dimension,
                    "sub_dimension": i.sub_dimension,
                    "type": i.type,
                    "severity": i.severity,
                    "title": i.title,
                    "description": i.description,
                    "location": i.location,
                    "suggestion": i.suggestion,
                    "fixed": i.fixed
                }
                for i in self.issues
            ],
            "timestamp": self.timestamp
        }


@dataclass
class RevisionResult:
    """修订结果"""
    final_text: str
    loops: int
    audit_results: List[AuditResult]
    passed: bool
    reason: str = ""  # "passed" / "max_loops_reached" / "no_improvement"
    issues_fixed: List[str] = field(default_factory=list)
    remaining_issues: List[AuditIssue] = field(default_factory=list)
    
    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "loops": self.loops,
            "reason": self.reason,
            "final_score": self.audit_results[-1].total_score if self.audit_results else 0,
            "issues_fixed": self.issues_fixed,
            "remaining_issues": [
                {"dimension": i.dimension, "title": i.title, "severity": i.severity}
                for i in self.remaining_issues
            ],
            "audit_summary": [
                {
                    "loop": idx + 1,
                    "score": r.total_score,
                    "critical_count": len(r.get_critical_issues()),
                    "passed": r.passed
                }
                for idx, r in enumerate(self.audit_results)
            ]
        }


class QualityGate:
    """
    质量门禁
    判断审计结果是否达到通过标准
    """
    
    def __init__(
        self,
        min_score: int = 70,
        max_critical: int = 0,
        max_logic_errors: int = 0,
        max_medium_warnings: int = 5
    ):
        self.min_score = min_score
        self.max_critical = max_critical
        self.max_logic_errors = max_logic_errors
        self.max_medium_warnings = max_medium_warnings
    
    def is_passed(self, audit_result: AuditResult) -> bool:
        """判断是否通过质量门禁"""
        # 必须条件1：总分 >= min_score
        if audit_result.total_score < self.min_score:
            return False
        
        # 必须条件2：关键问题数量 = 0
        critical_count = len(audit_result.get_critical_issues())
        if critical_count > self.max_critical:
            return False
        
        # 必须条件3：逻辑问题 = 0
        logic_count = len(audit_result.get_issues_by_type("logic_"))
        if logic_count > self.max_logic_errors:
            return False
        
        # 软条件（警告但不阻止）
        medium_count = len(audit_result.get_medium_issues())
        if medium_count > self.max_medium_warnings:
            self._add_warning("medium_issues_too_many", medium_count)
        
        return True
    
    def get_blocking_issues(self, audit_result: AuditResult) -> List[AuditIssue]:
        """获取阻止通过的问题"""
        blocking = []
        
        if audit_result.total_score < self.min_score:
            blocking.append(AuditIssue(
                dimension="structure",
                sub_dimension="ST4",
                type="score_too_low",
                severity="critical",
                title=f"总分过低 ({audit_result.total_score})",
                description=f"总分 {audit_result.total_score} 低于最低要求 {self.min_score}",
                location="整章",
                suggestion="需要全面修订以提高质量"
            ))
        
        for issue in audit_result.get_critical_issues():
            blocking.append(issue)
        
        for issue in audit_result.get_issues_by_type("logic_"):
            blocking.append(issue)
        
        return blocking
    
    def _add_warning(self, warning_type: str, count: int = None):
        """添加警告（不阻止通过）"""
        # 警告会被记录但不会阻止通过
        pass


class RevisionEngine:
    """
    修订执行引擎
    根据审计问题生成修订指令并执行修订
    """
    
    def __init__(self, llm_call_func=None):
        """
        Args:
            llm_call_func: LLM调用函数，签名: (prompt: str) -> str
                          如果不提供，则只生成修订指令文本
        """
        self.llm_call_func = llm_call_func
    
    def revise(
        self,
        text: str,
        issues: List[AuditIssue],
        chapter_num: int,
        genre_rules: str = None
    ) -> str:
        """
        执行修订
        
        Args:
            text: 当前章节文本
            issues: 审计发现的问题
            chapter_num: 章节编号
            genre_rules: 题材规则（可选）
            
        Returns:
            修订后的文本
        """
        # 生成修订指令
        instruction = self.generate_revision_instruction(issues, text, genre_rules)
        
        # 调用LLM执行修订
        if self.llm_call_func:
            prompt = self._build_revision_prompt(text, instruction, chapter_num)
            return self.llm_call_func(prompt)
        else:
            # 不提供LLM时，返回修订指令供人工处理
            return f"[修订指令]\n{instruction}\n\n[原文未修改，需外部LLM执行修订]"
    
    def generate_revision_instruction(
        self,
        issues: List[AuditIssue],
        context: str = None,
        genre_rules: str = None
    ) -> str:
        """
        根据问题生成具体的修订指令
        
        这是核心方法，根据不同类型的问题生成有针对性的修订指导。
        """
        if not issues:
            return "无需修订，文本质量良好。"
        
        lines = [
            "## 修订要求",
            "",
            "请根据以下问题修订文本。修订时请：",
            "1. 尽量保持原文的风格和情节不变",
            "2. 只修复指定的问题，不要引入新问题",
            "3. 修复后检查是否引入新的逻辑矛盾",
            "",
        ]
        
        # 按严重程度分组
        critical = [i for i in issues if i.severity == "critical"]
        medium = [i for i in issues if i.severity == "medium"]
        minor = [i for i in issues if i.severity == "minor"]
        
        if critical:
            lines.extend(["\n### 🔴 关键问题（必须修复）\n"])
            for i, issue in enumerate(critical, 1):
                lines.append(f"**问题{i}: {issue.title}**")
                lines.append(f"- 位置: {issue.location}")
                lines.append(f"- 描述: {issue.description}")
                lines.append(f"- 修订: {issue.suggestion}")
                lines.append("")
        
        if medium:
            lines.extend(["\n### 🟡 中等问题（建议修复）\n"])
            for i, issue in enumerate(medium, 1):
                lines.append(f"**问题{i}: {issue.title}**")
                lines.append(f"- 位置: {issue.location}")
                lines.append(f"- 修订: {issue.suggestion}")
                lines.append("")
        
        if minor and len(minor) <= 5:
            lines.extend(["\n### ⚪ 轻微问题（可选修复）\n"])
            for i, issue in enumerate(minor, 1):
                lines.append(f"**问题{i}: {issue.title}** - {issue.suggestion}")
        
        if genre_rules:
            lines.extend(["\n## 题材规则提醒\n", genre_rules])
        
        return "\n".join(lines)
    
    def _build_revision_prompt(
        self,
        text: str,
        instruction: str,
        chapter_num: int
    ) -> str:
        """构建修订用的Prompt"""
        return f"""## 修订任务

请修订第{chapter_num}章的文本，修复以下问题。

### 当前文本

{text}

### 修订要求

{instruction}

### 输出格式

请直接输出修订后的完整章节文本，不要添加任何解释或标记。
"""


class RevisionLoop:
    """
    自动修订循环主控制器
    
    控制 审计 → 判断 → 修订 的循环流程
    """
    
    def __init__(
        self,
        max_loops: int = 3,
        min_score: int = 70,
        auditor=None,  # 审计器，传入后自动调用
        revision_engine: RevisionEngine = None
    ):
        """
        Args:
            max_loops: 最大循环次数
            min_score: 通过最低分数
            auditor: 审计器（需要有 audit(text, chapter_num, truth_files) 方法）
            revision_engine: 修订引擎
        """
        self.max_loops = max_loops
        self.min_score = min_score
        self.auditor = auditor
        self.revision_engine = revision_engine or RevisionEngine()
        self.quality_gate = QualityGate(min_score=min_score)
        
        # 记录已尝试的修复（避免重复）
        self._fix_history = {}  # {issue_type: [attempts]}
    
    def run(
        self,
        chapter_text: str,
        chapter_num: int,
        truth_files: Dict[str, str] = None,
        genre: str = None,
        genre_rules: str = None
    ) -> RevisionResult:
        """
        运行修订循环
        
        Args:
            chapter_text: 初始章节文本
            chapter_num: 章节编号
            truth_files: 真相文件字典
            genre: 题材（用于审计器）
            genre_rules: 题材规则文本
            
        Returns:
            RevisionResult
        """
        current_text = chapter_text
        audit_results = []
        issues_fixed = []
        
        for loop in range(self.max_loops):
            # 1. 审计
            if self.auditor:
                audit_result = self.auditor.audit(
                    current_text, chapter_num, truth_files, genre
                )
            else:
                # 如果没有审计器，创建一个模拟结果（实际使用时必须提供）
                raise ValueError("必须提供 auditor 参数")
            
            audit_results.append(audit_result)
            
            # 2. 检查是否通过
            if self.quality_gate.is_passed(audit_result):
                return RevisionResult(
                    final_text=current_text,
                    loops=loop + 1,
                    audit_results=audit_results,
                    passed=True,
                    reason="passed",
                    issues_fixed=issues_fixed,
                    remaining_issues=audit_result.get_minor_issues()
                )
            
            # 3. 记录已修复的问题
            for issue in audit_result.issues:
                issue_type = issue.type
                if issue_type not in self._fix_history:
                    self._fix_history[issue_type] = []
            
            # 4. 获取阻止通过的问题
            blocking_issues = self.quality_gate.get_blocking_issues(audit_result)
            
            # 5. 检查是否达到最大循环
            if loop == self.max_loops - 1:
                return RevisionResult(
                    final_text=current_text,
                    loops=loop + 1,
                    audit_results=audit_results,
                    passed=False,
                    reason="max_loops_reached",
                    issues_fixed=issues_fixed,
                    remaining_issues=blocking_issues + audit_result.get_medium_issues()
                )
            
            # 6. 修订
            current_text = self.revision_engine.revise(
                current_text,
                blocking_issues,
                chapter_num,
                genre_rules
            )
            
            # 记录本次修复的问题
            for issue in blocking_issues:
                issues_fixed.append(
                    f"[{issue.severity}] {issue.title} ({issue.location})"
                )
        
        # 不应该到达这里
        return RevisionResult(
            final_text=current_text,
            loops=self.max_loops,
            audit_results=audit_results,
            passed=False,
            reason="max_loops_reached",
            issues_fixed=issues_fixed
        )
    
    def generate_report(self, result: RevisionResult) -> str:
        """生成修订报告"""
        lines = [
            "=" * 50,
            "自动修订循环报告",
            "=" * 50,
            f"章节: {result.audit_results[0].chapter_num if result.audit_results else 'N/A'}",
            f"循环次数: {result.loops}",
            f"最终状态: {'✅ 通过' if result.passed else '❌ 未通过'}",
            f"原因: {result.reason}",
            "",
            "审计记录:",
        ]
        
        for idx, ar in enumerate(result.audit_results):
            status = "✅" if ar.passed else "❌"
            lines.append(
                f"  第{idx+1}轮: 评分 {ar.total_score}/100 "
                f"关键问题 {len(ar.get_critical_issues())} "
                f"{status}"
            )
        
        if result.issues_fixed:
            lines.extend(["", "已修复问题:"])
            for fix in result.issues_fixed:
                lines.append(f"  ✅ {fix}")
        
        if result.remaining_issues:
            lines.extend(["", "未解决问题:"])
            for issue in result.remaining_issues:
                lines.append(f"  ⚠️ [{issue.severity}] {issue.title}")
        
        return "\n".join(lines)


if __name__ == "__main__":
    # 模拟测试（不依赖真实审计器）
    print("RevisionLoop 已就绪")
    print("需要配合 PR5 审计器使用")
