"""
上下文编排器 - 编译上下文和规则栈
Compose: 从真相文件选择相关上下文，编译规则栈
"""

import json
import yaml
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from .planner import ChapterIntent


@dataclass
class ContextSnippet:
    """上下文片段"""
    type: str          # character / location / relationship / hook / item / event
    content: str       # 具体内容
    source: str       # 来源文件
    chapter_ref: int = None  # 关联章节
    relevance_score: float = 1.0  # 相关性评分


@dataclass
class CompiledContext:
    """编译后的上下文"""
    chapter_num: int
    
    # 相关事实片段
    relevant_facts: List[ContextSnippet] = field(default_factory=list)
    
    # 活跃伏笔
    active_hooks: List[Dict] = field(default_factory=list)
    
    # 活跃支线
    active_subplots: List[Dict] = field(default_factory=list)
    
    # 资源状态
    resource_states: List[Dict] = field(default_factory=list)
    
    # 上下文来源
    context_sources: List[str] = field(default_factory=list)
    
    def to_json(self) -> Dict:
        return {
            "chapter": self.chapter_num,
            "relevant_facts": [
                {
                    "type": s.type,
                    "content": s.content,
                    "source": s.source,
                    "chapter_ref": s.chapter_ref,
                    "relevance_score": s.relevance_score
                }
                for s in self.relevant_facts
            ],
            "active_hooks": self.active_hooks,
            "active_subplots": self.active_subplots,
            "resource_states": self.resource_states,
            "context_sources": self.context_sources
        }


@dataclass
class RuleLayer:
    """规则层级"""
    name: str
    priority: int      # 数字越小优先级越高
    rules: List[str]
    source: str


@dataclass
class RuleStack:
    """规则栈"""
    chapter_num: int
    layers: List[RuleLayer] = field(default_factory=list)
    
    def to_yaml(self) -> str:
        data = {
            "chapter": self.chapter_num,
            "layers": [
                {
                    "name": layer.name,
                    "priority": layer.priority,
                    "rules": layer.rules,
                    "source": layer.source
                }
                for layer in self.layers
            ]
        }
        return yaml.dump(data, allow_unicode=True, default_flow_style=False)
    
    def to_prompt_section(self) -> str:
        """转换为Prompt中的规则栈部分"""
        lines = ["## 规则优先级（高优先级可覆盖低优先级）", ""]
        
        for layer in sorted(self.layers, key=lambda x: x.priority):
            lines.append(f"### 【{layer.name}】(优先级 {layer.priority})")
            for rule in layer.rules:
                lines.append(f"- {rule}")
            lines.append("")
        
        return "\n".join(lines)


class ContextComposer:
    """
    上下文编排器
    
    从真相文件系统中选择与当前章节相关的上下文，
    并编译规则栈供写作使用。
    """
    
    def __init__(self, truth_files_dir: str = "story/truth_files"):
        self.truth_files_dir = Path(truth_files_dir)
    
    def compile(
        self,
        intent: ChapterIntent,
        truth_files: Dict[str, str] = None,
        genre_rules: str = None,
        book_rules: List[str] = None
    ) -> Dict[str, Any]:
        """
        编译上下文和规则栈
        
        Args:
            intent: 本章意图文档
            truth_files: 真相文件字典 {文件名: 内容}
            genre_rules: 题材规则文本
            book_rules: 书籍级自定义规则列表
            
        Returns:
            {
                "context": CompiledContext,
                "rule_stack": RuleStack,
                "writing_prompt": str  # 完整写作Prompt
            }
        """
        # 1. 编译上下文
        context = self._compile_context(intent, truth_files or {})
        
        # 2. 编译规则栈
        rule_stack = self._compile_rule_stack(
            intent=intent,
            genre_rules=genre_rules,
            book_rules=book_rules or []
        )
        
        # 3. 生成写作Prompt（供外部LLM使用）
        prompt = self._generate_writing_prompt(intent, context, rule_stack)
        
        return {
            "context": context,
            "rule_stack": rule_stack,
            "writing_prompt": prompt
        }
    
    def _compile_context(
        self,
        intent: ChapterIntent,
        truth_files: Dict[str, str]
    ) -> CompiledContext:
        """从真相文件中提取相关上下文"""
        context = CompiledContext(chapter_num=intent.chapter_num)
        
        # 从真相文件提取相关内容
        for filename, content in truth_files.items():
            context.context_sources.append(filename)
            
            # 角色相关
            if "character" in filename.lower() or "state" in filename.lower():
                snippets = self._extract_character_snippets(content, intent)
                context.relevant_facts.extend(snippets)
            
            # 伏笔相关
            if "hook" in filename.lower():
                hooks = self._extract_active_hooks(content, intent)
                context.active_hooks = hooks
            
            # 支线相关
            if "subplot" in filename.lower():
                subplots = self._extract_active_subplots(content, intent)
                context.active_subplots = subplots
            
            # 资源相关
            if "resource" in filename.lower() or "ledger" in filename.lower():
                resources = self._extract_resource_states(content)
                context.resource_states = resources
        
        # 按相关性排序
        context.relevant_facts.sort(key=lambda x: x.relevance_score, reverse=True)
        
        return context
    
    def _extract_character_snippets(
        self,
        content: str,
        intent: ChapterIntent
    ) -> List[ContextSnippet]:
        """提取角色相关片段"""
        snippets = []
        
        # 简单的关键词匹配，实际应该用LLM或更复杂的匹配
        keywords = []
        for keep in intent.must_keep:
            keywords.extend(keep.split("：")[-1].split("、"))
        
        # 简化：假设content是纯文本，每行是一个条目
        for line in content.split("\n"):
            if line.strip():
                score = 0.5  # 默认相关性
                for kw in keywords:
                    if kw in line:
                        score += 0.2
                
                if score > 0.5:
                    snippets.append(ContextSnippet(
                        type="character",
                        content=line.strip(),
                        source="truth_files",
                        relevance_score=min(score, 1.0)
                    ))
        
        return snippets[:20]  # 最多20条
    
    def _extract_active_hooks(
        self,
        content: str,
        intent: ChapterIntent
    ) -> List[Dict]:
        """提取活跃伏笔"""
        hooks = []
        
        for line in content.split("\n"):
            if "open" in line.lower() or "progressing" in line.lower():
                hooks.append({
                    "content": line.strip(),
                    "status": "open"
                })
        
        # 如果意图中提到了具体伏笔ID，过滤只保留相关的
        if intent.related_hooks:
            hooks = [h for h in hooks if any(
                hid in h.get("content", "") for hid in intent.related_hooks
            )]
        
        return hooks[:10]  # 最多10条
    
    def _extract_active_subplots(
        self,
        content: str,
        intent: ChapterIntent
    ) -> List[Dict]:
        """提取活跃支线"""
        subplots = []
        
        for line in content.split("\n"):
            if "active" in line.lower() or "进行中" in line:
                subplots.append({
                    "content": line.strip(),
                    "status": "active"
                })
        
        return subplots[:5]  # 最多5条
    
    def _extract_resource_states(
        self,
        content: str
    ) -> List[Dict]:
        """提取资源状态"""
        resources = []
        
        for line in content.split("\n"):
            if line.strip() and ":" in line:
                key, value = line.split(":", 1)
                resources.append({
                    "item": key.strip(),
                    "status": value.strip()
                })
        
        return resources[:15]  # 最多15条
    
    def _compile_rule_stack(
        self,
        intent: ChapterIntent,
        genre_rules: str = None,
        book_rules: List[str] = None
    ) -> RuleStack:
        """编译规则栈"""
        stack = RuleStack(chapter_num=intent.chapter_num)
        
        # Layer 1: 本章意图（最高优先级）
        stack.layers.append(RuleLayer(
            name="本章意图",
            priority=1,
            rules=intent.must_keep + [f"避免: {a}" for a in intent.must_avoid],
            source="chapter_intent"
        ))
        
        # Layer 2: 书籍规则
        if book_rules:
            stack.layers.append(RuleLayer(
                name="书籍规则",
                priority=2,
                rules=book_rules,
                source="book_rules"
            ))
        
        # Layer 3: 题材规则
        if genre_rules:
            stack.layers.append(RuleLayer(
                name="题材规则",
                priority=3,
                rules=[genre_rules],
                source="genre_rules"
            ))
        
        # Layer 4: 通用规则（默认）
        stack.layers.append(RuleLayer(
            name="通用规则",
            priority=4,
            rules=[
                "禁止使用AI痕迹词：然而、因此、值得注意的是...",
                "长短句交错，避免整齐划一",
                "动作优先，少用'是...的'结构",
                "对话口语化，避免书面语",
                "删除所有总结句和升华段"
            ],
            source="common_rules"
        ))
        
        return stack
    
    def _generate_writing_prompt(
        self,
        intent: ChapterIntent,
        context: CompiledContext,
        rule_stack: RuleStack
    ) -> str:
        """生成完整的写作Prompt"""
        lines = [
            "# 写作任务",
            f"## 章节编号: {intent.chapter_num}",
            "",
            "## 本章必须达成",
        ]
        
        for item in intent.must_keep:
            lines.append(f"- {item}")
        
        lines.extend([
            "",
            "## 本章必须避免",
        ])
        for item in intent.must_avoid:
            lines.append(f"- {item}")
        
        lines.extend([
            "",
            "## 情感基调",
            f"- {intent.emotional_tone}: {intent.emotional_notes}" if intent.emotional_notes else f"- {intent.emotional_tone}",
            "",
            "## 字数要求",
            f"- 目标: {intent.word_count_target}字",
            f"- 允许范围: {intent.word_count_range[0]}~{intent.word_count_range[1]}字",
        ])
        
        # 添加上下文
        if context.active_hooks:
            lines.extend([
                "",
                "## 当前活跃伏笔",
                "（这些伏笔需要在本章或后续章节中处理）"
            ])
            for hook in context.active_hooks:
                lines.append(f"- {hook['content']}")
        
        if context.relevant_facts:
            lines.extend([
                "",
                "## 相关事实",
                "（写作时注意保持一致性）"
            ])
            for snippet in context.relevant_facts[:10]:
                lines.append(f"- [{snippet.type}] {snippet.content}")
        
        # 添加规则栈
        lines.extend([
            "",
            rule_stack.to_prompt_section()
        ])
        
        return "\n".join(lines)
    
    def save_compiled(
        self,
        chapter_num: int,
        context: CompiledContext,
        rule_stack: RuleStack,
        output_dir: str = "story/runtime"
    ) -> None:
        """保存编译结果"""
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        prefix = f"chapter-{chapter_num:04d}"
        
        # 保存 context.json
        with open(output_dir / f"{prefix}.context.json", 'w', encoding='utf-8') as f:
            json.dump(context.to_json(), f, ensure_ascii=False, indent=2)
        
        # 保存 rule-stack.yaml
        with open(output_dir / f"{prefix}.rule-stack.yaml", 'w', encoding='utf-8') as f:
            f.write(rule_stack.to_yaml())
        
        # 保存 trace.json（记录编译过程）
        with open(output_dir / f"{prefix}.trace.json", 'w', encoding='utf-8') as f:
            json.dump({
                "chapter": chapter_num,
                "compiled_at": intent.created_at if (intent := getattr(self, 'last_intent', None)) else None,
                "sources": context.context_sources,
                "layers": [l.name for l in rule_stack.layers]
            }, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    from planner import ChapterPlanner, ChapterIntent
    
    # 模拟测试
    planner = ChapterPlanner()
    intent = planner.create_intent(
        book_id="吞天魔帝",
        chapter_num=5,
        must_keep=[
            "师父发现徒弟偷学禁术",
            "师徒对峙，矛盾升级",
            "主角陷入两难"
        ],
        must_avoid=[
            "不要让师父直接出手惩罚"
        ],
        emotional_tone="oppressed",
        emotional_notes="压抑、紧张"
    )
    
    # 模拟真相文件
    truth_files = {
        "character_state.md": """
林烬：筑基后期，偷学禁术第3天
云清子：师父，元婴期，对徒弟期望很高
关系：敬畏但有裂痕
        """,
        "pending_hooks.md": """
[open] hook_003: 禁术副作用会在第7章显现
[open] hook_007: 师兄目睹了主角偷学
        """
    }
    
    composer = ContextComposer()
    result = composer.compile(
        intent=intent,
        truth_files=truth_files,
        genre_rules="玄幻题材规则..."
    )
    
    print("=== Context Preview ===")
    context = result["context"]
    print(f"活跃伏笔: {len(context.active_hooks)}")
    print(f"相关事实: {len(context.relevant_facts)}")
    
    print("\n=== Rule Stack ===")
    print(result["rule_stack"].to_prompt_section()[:500])
