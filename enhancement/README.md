# PR2: 题材专属写作规则

## 解决的问题

不同类型的小说有不同的"好"的标准。玄幻需要升级体系和打斗描写，都市需要现实感和感情线，仙侠需要意境和修炼逻辑。用通用规则写所有题材，出来的文字会"不对味"。

## 解决方案

为每种题材提供专属写作规则，包括：
- 禁止事项（题材雷区）
- 语言风格（语气、句式、用词偏好）
- 节奏特点（打斗占比、感情线节奏、世界观展开速度）
- 审计维度（该题材特有的检查项）

## 文件结构

```
enhancement/
├── genre_rules_manager.py  # 规则管理器
├── genre_rule_loader.py    # 规则加载器
├── rules/                  # 题材规则库
│   ├── xuanhuan.md        # 玄幻规则
│   ├── urban.md           # 都市规则
│   ├── xiuxian.md         # 仙侠规则
│   ├── scifi.md           # 科幻规则
│   ├── romance.md         # 言情规则
│   └── common.md          # 通用规则（所有题材都适用）
└── __init__.py
```

## 支持的题材

| 题材 | 关键词 | 核心规则 |
|------|--------|---------|
| 玄幻 | 升级、打斗、异火/血脉/剑意 | 升级逻辑严密、战斗描写有层次感 |
| 都市 | 现实、职场、感情 | 场景真实、对话自然、无过度YY |
| 仙侠 | 修仙、意境、道 | 语言有意境、不沾俗世烟火气 |
| 科幻 | 科技、逻辑、未来 | 科学设定自洽、技术细节可信 |
| 言情 | 感情、虐/甜、人设 | 心理描写细腻、互动张力足 |

## 使用方式

```python
from genre_rules_manager import GenreRulesManager

manager = GenreRulesManager()

# 获取某题材的完整规则
rules = manager.get_rules("xuanhuan")

# 生成写作Prompt
prompt = manager.generate_writing_prompt(
    genre="xuanhuan",
    chapter_context="本章主角突破元婴期",
    custom_constraints=["不要写太多打斗，主要写心境变化"]
)

# 合并多题材规则
merged = manager.merge_genres(["xuanhuan", "romance"])

# 导出为Prompt格式
prompt_text = rules.to_prompt()
```

## 规则格式

每条规则包含：

```yaml
type: "genre_specific"
genre: "xuanhuan"
category: "forbidden"  # forbidden | style | rhythm | audit

# 禁用事项
forbidden:
  - "主角突破太快（每个大境界至少3章）"
  - "同一场战斗超过3个势力参与"
  - "女性角色只当花瓶"

# 风格要求
style:
  positive:
    - "战斗描写要有层次：试探→认真→底牌→逆转"
    - "升级时描写能量涌动、境界压制"
    - "宝物要有独特来历和限制条件"
  negative:
    - "避免'秒天秒地'式战斗"
    - "不要写'系统提示音'"

# 审计维度（该题材特有的检查项）
audit_dimensions:
  - "升级逻辑是否自洽（境界差不能太大）"
  - "宝物设定是否前后矛盾"
  - "打斗是否依赖主角光环"
```
