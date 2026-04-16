"""
章节规划器 - 生成意图文档
Plan: 基于指令生成 chapter-XXXX.intent.md
"""

from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass, field
from datetime import datetime
import json


@dataclass
class ChapterIntent:
    """本章意图文档"""
    chapter_num: int
    book_id: str
    
    # 本章必须达成
    must_keep: List[str] = field(default_factory=list)
    
    # 本章必须避免
    must_avoid: List[str] = field(default_factory=list)
    
    # 情感基调
    emotional_tone: str = "neutral"
    emotional_notes: str = ""
    
    # 章节目标
    chapter_goal: str = ""
    word_count_target: int = 14000
    word_count_range: tuple = (12600, 15400)
    
    # 冲突处理
    conflict_resolution: str = "prefer_new"
    conflict_notes: str = ""
    
    # 关联伏笔
    related_hooks: List[str] = field(default_factory=list)
    
    # 视角限制
    perspective_limit: List[str] = field(default_factory=list)
    
    # 元数据
    created_at: str = field(default_factory="")
    
    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now().isoformat()
    
    def to_markdown(self) -> str:
        """导出为Markdown格式"""
        lines = [
            f"# Chapter {self.chapter_num} Intent",
            f"",
            f"**Book:** {self.book_id}",
            f"**Created:** {self.created_at}",
            f"",
            f"## 本章必须达成 (Must-Keep)",
            f""
        ]
        
        for item in self.must_keep:
            lines.append(f"- {item}")
        
        lines.extend([
            f"",
            f"## 本章必须避免 (Must-Avoid)",
            f""
        ])
        
        for item in self.must_avoid:
            lines.append(f"- {item}")
        
        lines.extend([
            f"",
            f"## 情感基调",
            f"- **{self.emotional_tone}**: {self.emotional_notes}" if self.emotional_notes else f"- **{self.emotional_tone}**",
            f"",
            f"## 章节目标",
            f"- 目标字数: {self.word_count_target}",
            f"- 允许范围: {self.word_count_range[0]} ~ {self.word_count_range[1]}",
            f"- 核心任务: {self.chapter_goal}",
            f"",
            f"## 冲突处理原则",
            f"- 策略: {self.conflict_resolution}",
            f"- 说明: {self.conflict_notes}" if self.conflict_notes else "",
            f"",
        ])
        
        if self.related_hooks:
            lines.extend([
                f"## 关联伏笔",
                f""
            ])
            for hook in self.related_hooks:
                lines.append(f"- {hook}")
        
        if self.perspective_limit:
            lines.extend([
                f"",
                f"## 视角限制",
                f"- 本章视角人物: {', '.join(self.perspective_limit)}",
                f"- 视角人物不知道: 不要写视角人物未亲眼见证/未亲耳听闻的事件"
            ])
        
        return "\n".join(line for line in lines if line)
    
    def to_dict(self) -> dict:
        """导出为字典"""
        return {
            "chapter_num": self.chapter_num,
            "book_id": self.book_id,
            "must_keep": self.must_keep,
            "must_avoid": self.must_avoid,
            "emotional_tone": self.emotional_tone,
            "emotional_notes": self.emotional_notes,
            "chapter_goal": self.chapter_goal,
            "word_count_target": self.word_count_target,
            "word_count_range": list(self.word_count_range),
            "conflict_resolution": self.conflict_resolution,
            "conflict_notes": self.conflict_notes,
            "related_hooks": self.related_hooks,
            "perspective_limit": self.perspective_limit,
            "created_at": self.created_at
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'ChapterIntent':
        """从字典加载"""
        data = data.copy()
        data['word_count_range'] = tuple(data.get('word_count_range', (12600, 15400)))
        return cls(**data)


class ChapterPlanner:
    """
    章节规划器
    
    基于用户指令生成本章的意图文档。
    这个类不依赖LLM调用，只是将用户指令解析成结构化的意图文档。
    LLM调用由外部系统完成，这里只负责生成Prompt供LLM解析。
    """
    
    def __init__(self, runtime_dir: str = "story/runtime"):
        self.runtime_dir = Path(runtime_dir)
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
    
    def generate_planning_prompt(
        self,
        book_id: str,
        chapter_num: int,
        user_context: str,
        book_brief: str = None,
        current_focus: str = None,
        previous_chapter_summary: str = None
    ) -> str:
        """
        生成规划Prompt，让LLM生成意图文档
        
        这个方法生成一个Prompt，外部LLM会根据这个Prompt生成意图文档。
        或者，如果外部已经有意图文档的结构化数据，可以直接用 create_intent() 创建。
        """
        lines = [
            "## 任务：生成章节意图文档",
            "",
            f"**书籍ID:** {book_id}",
            f"**章节编号:** {chapter_num}",
            f"",
            f"### 用户指令",
            f"{user_context}",
            f""
        ]
        
        if current_focus:
            lines.extend([
                f"### 当前阶段关注点",
                f"{current_focus}",
                f""
            ])
        
        if book_brief:
            lines.extend([
                f"### 书籍简介",
                f"{book_brief}",
                f""
            ])
        
        if previous_chapter_summary:
            lines.extend([
                f"### 上一章摘要",
                f"{previous_chapter_summary}",
                f""
            ])
        
        lines.extend([
            f"### 输出要求",
            f"请生成以下JSON格式的意图文档：",
            f"",
            f"```json",
            f"{{",
            f'  "chapter_num": {chapter_num},',
            f'  "book_id": "{book_id}",',
            f'  "must_keep": ["必须达成的事件1", "必须达成的事件2"],',
            f'  "must_avoid": ["必须避免的事件1", "必须避免的事件2"],',
            f'  "emotional_tone": "紧张/压抑/温情/热血...",',
            f'  "emotional_notes": "情感基调的具体描述",',
            f'  "chapter_goal": "本章的核心任务",',
            f'  "word_count_target": 14000,',
            f'  "word_count_range": [12600, 15400],',
            f'  "conflict_resolution": "prefer_new / prefer_old / mark_conflict",',
            f'  "related_hooks": ["伏笔ID1", "伏笔ID2"]',
            f"}}",
            f"```",
            f"",
            f"**must_keep 规则:**",
            f"- 列出本章必须发生的关键事件",
            f"- 每个事件用一句话描述",
            f"- 通常3-5条，不要超过7条",
            f"",
            f"**must_avoid 规则:**",
            f"- 列出本章必须避免的问题",
            f"- 如'不要让师父直接出手'、'不要让主角立刻做出选择'",
            f"- 通常2-4条",
            f"",
            f"**emotional_tone 选项:**",
            f"- neutral（中性）、tense（紧张）、oppressed（压抑）",
            f"- warm（温情）、passionate（热血）、mysterious（神秘）",
            f"- tragic（悲剧）、comedic（喜剧）、bittersweet（苦乐参半）"
        ])
        
        return "\n".join(lines)
    
    def create_intent(
        self,
        book_id: str,
        chapter_num: int,
        must_keep: List[str],
        must_avoid: List[str],
        emotional_tone: str = "neutral",
        chapter_goal: str = "",
        word_count_target: int = 14000,
        word_count_range: tuple = (12600, 15400),
        related_hooks: List[str] = None,
        perspective_limit: List[str] = None,
        conflict_resolution: str = "prefer_new"
    ) -> ChapterIntent:
        """
        直接创建意图文档（当已有结构化数据时使用）
        """
        intent = ChapterIntent(
            chapter_num=chapter_num,
            book_id=book_id,
            must_keep=must_keep,
            must_avoid=must_avoid,
            emotional_tone=emotional_tone,
            chapter_goal=chapter_goal,
            word_count_target=word_count_target,
            word_count_range=word_count_range,
            related_hooks=related_hooks or [],
            perspective_limit=perspective_limit or [],
            conflict_resolution=conflict_resolution
        )
        
        return intent
    
    def save_intent(self, intent: ChapterIntent) -> Path:
        """
        保存意图文档到 runtime 目录
        """
        filename = f"chapter-{intent.chapter_num:04d}.intent"
        filepath = self.runtime_dir / f"{filename}.md"
        jsonpath = self.runtime_dir / f"{filename}.json"
        
        # 保存 markdown 版本（给人看）
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(intent.to_markdown())
        
        # 保存 json 版本（给系统用）
        with open(jsonpath, 'w', encoding='utf-8') as f:
            json.dump(intent.to_dict(), f, ensure_ascii=False, indent=2)
        
        return filepath
    
    def load_intent(self, chapter_num: int) -> Optional[ChapterIntent]:
        """加载意图文档"""
        jsonpath = self.runtime_dir / f"chapter-{chapter_num:04d}.intent.json"
        
        if not jsonpath.exists():
            return None
        
        with open(jsonpath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        return ChapterIntent.from_dict(data)


if __name__ == "__main__":
    planner = ChapterPlanner()
    
    # 示例：基于用户指令生成规划Prompt
    prompt = planner.generate_planning_prompt(
        book_id="吞天魔帝",
        chapter_num=5,
        user_context="本章重点写师徒矛盾，师父发现徒弟偷学禁术",
        current_focus="把注意力拉回师徒线",
        previous_chapter_summary="第4章主角在秘境中获得禁术传承，但被师兄看到了"
    )
    
    print(prompt)
    print("\n" + "=" * 50 + "\n")
    
    # 示例：直接创建意图文档
    intent = planner.create_intent(
        book_id="吞天魔帝",
        chapter_num=5,
        must_keep=[
            "师父发现徒弟偷学禁术",
            "师徒对峙，矛盾升级",
            "主角陷入两难（遵命还是反抗）",
            "埋下下一章决裂的种子"
        ],
        must_avoid=[
            "不要让师父直接出手惩罚（太早）",
            "不要让主角立刻做出选择"
        ],
        emotional_tone="oppressed",
        emotional_notes="压抑、紧张，师徒对话要有火药味但不失尊重",
        chapter_goal="让师徒矛盾不可逆转",
        related_hooks=["hook_003", "hook_007"]
    )
    
    planner.save_intent(intent)
    print(f"已保存意图文档: chapter-{intent.chapter_num:04d}.intent.md")
