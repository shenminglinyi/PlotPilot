# PR4: 自动修订循环

## 解决的问题

现有的审计只是"发现问题并报告"，问题不会被自动修复。人工处理审计结果效率低，而且即使知道有问题，AI重新写的时候也容易忘掉这些教训。

## 解决方案

审计不通过 → 自动触发修订 → 重新审计 → 循环直到通过（或达到最大次数）

```
写章节 → 审计 → ❌不通过 → 修订 → 审计 → ❌ → 修订 → ... → ✅通过
```

## 文件结构

```
enhancement/
├── revision_loop.py       # 修订循环主控制器
├── revision_engine.py    # 修订执行引擎
├── quality_gate.py        # 质量门禁（判断是否通过）
├── max_loop.py            # 最大循环次数保护
└── __init__.py
```

## 核心逻辑

```python
class RevisionLoop:
    """
    自动修订循环
    
    最多循环 max_loops 次，每次：
    1. 审计当前版本
    2. 如果有关键问题，打回修订
    3. 如果通过或达到上限，退出
    """
    
    def __init__(self, max_loops=3, critical_threshold=70):
        self.max_loops = max_loops
        self.critical_threshold = critical_threshold  # 低于此分必须修订
        
    def run(self, chapter_text: str, chapter_num: int, 
            truth_files: dict) -> RevisionResult:
        """
        运行修订循环
        
        Returns:
            RevisionResult:
                - final_text: 最终通过的文本
                - loops: 循环次数
                - audit_results: 每次审计的结果
                - issues_fixed: 修复的问题列表
        """
        current_text = chapter_text
        results = []
        
        for i in range(self.max_loops):
            # 审计
            audit_result = self.auditor.audit(current_text, chapter_num, truth_files)
            results.append(audit_result)
            
            # 检查是否通过
            if self.quality_gate.is_passed(audit_result):
                return RevisionResult(
                    final_text=current_text,
                    loops=i + 1,
                    audit_results=results,
                    passed=True
                )
            
            # 检查是否可以继续修订
            if self._is_max_loops_reached(i):
                return RevisionResult(
                    final_text=current_text,
                    loops=i + 1,
                    audit_results=results,
                    passed=False,
                    reason="max_loops_reached"
                )
            
            # 修订
            current_text = self.revision_engine.revise(
                current_text,
                audit_result.issues,
                chapter_num
            )
        
        return RevisionResult(
            final_text=current_text,
            loops=self.max_loops,
            audit_results=results,
            passed=False,
            reason="max_loops_reached"
        )
```

## 质量门禁规则

```python
class QualityGate:
    """
    决定是否通过质量门禁
    """
    
    def is_passed(self, audit_result) -> bool:
        # 必须条件1：总分 >= 70
        if audit_result.score < 70:
            return False
        
        # 必须条件2：关键问题（critical）数量 = 0
        critical_count = len(audit_result.get_critical_issues())
        if critical_count > 0:
            return False
        
        # 必须条件3：逻辑问题 = 0
        logic_count = len(audit_result.get_issues_by_type("logic"))
        if logic_count > 0:
            return False
        
        # 软条件（警告但不阻止）
        medium_count = audit_result.get_medium_issues()
        if len(medium_count) > 5:
            self._add_warning("medium_issues_too_many")
        
        return True
```

## 修订指令生成

修订引擎不只是说"重写"，而是根据问题类型生成具体的修订指令：

```python
def generate_revision_instruction(self, issues: list, context: dict) -> str:
    """根据问题生成具体的修订指令"""
    
    instructions = []
    
    for issue in issues:
        if issue.type == "forbidden_word":
            instructions.append(
                f"替换所有'{issue.word}'，使用更自然的表达方式。"
            )
        elif issue.type == "logic_hole":
            instructions.append(
                f"修复第{issue.line}行的逻辑问题：{issue.description}\n"
                f"修订要求：{issue.suggestion}"
            )
        elif issue.type == "character_inconsistency":
            instructions.append(
                f"角色'{issue.character}'的行为不一致：\n"
                f"  问题：{issue.description}\n"
                f"  角色设定：{issue.character_profile}\n"
                f"  请修改行为使其符合角色设定。"
            )
        elif issue.type == "ai_pattern":
            instructions.append(
                f"第{issue.line}行有AI痕迹，改写为更自然的表达：\n"
                f"  原文：{issue.original}\n"
                f"  问题：{issue.description}\n"
                f"  要求：参考上下文的人说话方式，写出口语化、有性格的对话。"
            )
    
    return "\n".join(instructions)
```

## 与其他PR的集成

```
PR3（输入治理） → PR1（去AI味） → PR5（33维审计） → PR4（修订循环）
                                                         ↓
                                                         ↓不通过
                                                    ← ← ← ← ←
```

## 防止死循环

- 最大循环次数：默认3次，超过则暂停等人工处理
- 每次修订后记录"已尝试的修复"，避免重复无效修复
- 如果同一问题连续出现2次，标记为"顽固问题"并给出特殊提示

## 输出报告

```python
{
    "chapter": 5,
    "passed": True,
    "final_score": 82,
    "loops": 2,
    "issues_summary": {
        "total": 8,
        "critical": 0,
        "medium": 3,
        "minor": 5
    },
    "issues_fixed": [
        "替换禁用词'然而' x3",
        "修复逻辑漏洞（第87行）",
        "改写AI痕迹段落"
    ],
    "remaining_issues": [
        "（只有minor级别，可以接受）"
    ]
}
```
