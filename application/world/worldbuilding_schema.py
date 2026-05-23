"""世界观五维 schema（单一数据源）。"""
from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, Mapping

from application.world.services.worldbuilding_field_text import worldbuilding_value_to_prose
from application.world.worldbuilding_merge import WORLD_BUILDING_DIMENSION_KEYS

# 与 AutoBibleGenerator / CPMS fields_desc 一致
WORLDBUILDING_DIMENSION_DEFS: Dict[str, Dict[str, Any]] = {
    "core_rules": {
        "label": "核心法则",
        "fields": {
            "power_system": "能力/竞技体系总览",
            "progression_path": "成长路径与训练门槛",
            "combat_resolution": "攻防判定与胜负规则",
            "physics_rules": "底层物理/时间/生理规律",
            "magic_tech": "技术接口与运作机制",
            "version_rules": "赛季版本与规则重置机制",
            "forbidden_methods": "禁用外挂/禁药/非法手段",
            "cost_and_limitation": "力量使用的代价与限制",
            "resource_scarcity": "稀缺资源及其分配",
        },
    },
    "geography": {
        "label": "地理生态",
        "fields": {
            "terrain": "主要地形特征",
            "climate": "气候特点与环境",
            "resources": "自然资源分布",
            "ecology": "生态系统与生物链",
            "forbidden_zones": "禁区/危险区域",
            "urban_core": "核心城市/聚居地",
            "hidden_realms": "秘境/隐藏空间",
        },
    },
    "society": {
        "label": "社会结构",
        "fields": {
            "politics": "政治体制与权力架构",
            "economy": "经济模式与贸易",
            "class_system": "阶级/等级系统",
            "power_structure": "明暗权力结构（明面与暗面的统治体系）",
            "oppression_mechanism": "压迫/控制机制（强者如何压制弱者）",
            "class_division": "阶层划分与流动壁垒",
        },
    },
    "culture": {
        "label": "历史文化",
        "fields": {
            "history": "关键历史事件与时代背景",
            "religion": "宗教信仰体系",
            "taboos": "文化禁忌与违逆后果",
            "worship": "崇拜对象与祭祀仪式",
            "oaths_and_curses": "誓言体系与诅咒",
        },
    },
    "daily_life": {
        "label": "沉浸感细节",
        "fields": {
            "food_clothing": "衣食住行的日常细节",
            "language_slang": "俚语、口音与方言",
            "entertainment": "娱乐方式与消遣",
            "survival_tactics": "底层/弱者的生存策略",
            "market_reality": "市场/交易的真实状况",
            "food_and_drink": "饮食文化与特色食物",
            "slang_and_profanity": "粗话、黑话与市井语言",
        },
    },
}

WORLDBUILDING_FIELD_SCOPE_HINTS: Dict[str, Dict[str, str]] = {
    "core_rules": {
        "power_system": "只写能力体系/竞技体系的核心分类和基本目标；不要写训练门槛、代价、资源价格",
        "progression_path": "只写玩家/选手如何成长、晋级、训练和被淘汰；不要写判定公式和医疗代价",
        "combat_resolution": "只写攻防判定、胜负结算、操作输入如何转化为结果；不要写社会制度",
        "physics_rules": "只写时间流速、神经反馈、生理极限等底层规律；不要写训练资源和黑市",
        "magic_tech": "只写游戏舱、同步接口、引擎、服务器等技术如何运作；不要写禁药和职业寿命",
        "version_rules": "只写赛季更新、版本重置、判定模型变化如何影响选手；不要写日常训练大段",
        "forbidden_methods": "只写外挂、禁药、非法同步率等明令禁止手段和检测/处罚机制；不要写普通代价",
        "cost_and_limitation": "只写身体、心理、职业寿命、戒断或后遗症等代价；不要重复成长路径",
        "resource_scarcity": "只写游戏舱、药剂、医疗、服务器权限、训练席位等稀缺资源；不要写地形",
    },
    "geography": {
        "terrain": "只写世界版图、地貌和空间边界；不要写宗门名单、矿工制度或禁区细节",
        "climate": "只写气候、天象、季节和环境对修炼的影响；不要写政治和经济",
        "resources": "只写资源分布在哪里、为何难取；不要写货币制度和市场交易",
        "ecology": "只写妖兽、灵植、生物链和环境危险；不要写人族阶级制度",
        "forbidden_zones": "只写禁区名称、危险机制和进入代价；不要写普通地形总览",
        "urban_core": "只写核心城市/聚居地的功能、控制者和叙事用途；不要写整洲地图",
        "hidden_realms": "只写秘境、洞天、隐藏空间的开启规则和风险；不要写社会制度",
    },
    "society": {
        "politics": "只写统治结构和明面规则；不要写经济价格、宗教神话或日常生活",
        "economy": "只写货币、贸易、黑市和资源流通；不要写阶级身份大段定义",
        "class_system": "只写阶级层级和身份差异；不要写具体压迫手段细节",
        "power_structure": "只写明暗权力如何分工、谁能拍板；不要写货币和日常细节",
        "oppression_mechanism": "只写强者控制弱者的具体机制；不要重复阶级名单",
        "class_division": "只写阶层流动壁垒和跨层代价；不要写政治组织沿革",
    },
    "culture": {
        "history": "只写关键历史事件及遗留后果；不要写娱乐、教育和通信",
        "religion": "只写信仰叙事和神话如何服务秩序；不要写禁忌清单",
        "taboos": "只写禁忌、触犯后果和维稳用途；不要写完整历史",
        "worship": "只写祭祀、仪式、崇拜对象和参与者；不要写宗门政治",
        "oaths_and_curses": "只写誓言、诅咒、血契等约束机制；不要写普通宗教教义",
    },
    "daily_life": {
        "food_clothing": "只写衣食住行和生活成本；不要写完整社会阶级",
        "language_slang": "只写方言、称呼、口头禅和说话习惯；必须给2-4个可入正文的短语",
        "entertainment": "只写娱乐、节庆、赌博、斗法观看等消遣；不要写教育通信",
        "survival_tactics": "只写底层、散修、凡人的保命办法；不要写市场价格表",
        "market_reality": "只写坊市、黑市、交易规则、骗术和保护费；不要写普通衣食住行",
        "food_and_drink": "只写饮食、酒水、药膳和阶层差异；不要写居住与交通",
        "slang_and_profanity": "只写粗话、黑话、暗号、忌讳称呼；必须给3-5个短句或词",
    },
}

def schema_field_keys(dim_key: str) -> frozenset[str]:
    dim = WORLDBUILDING_DIMENSION_DEFS.get(dim_key, {})
    fields = dim.get("fields") or {}
    return frozenset(fields.keys())


def resolve_canonical_field(dim_key: str, raw_key: str) -> str:
    """仅接受 schema 约定字段；未知字段不做猜测。"""
    key = str(raw_key).strip()
    return key if key in schema_field_keys(dim_key) else ""


def canonicalize_dimension_fields(
    dim_key: str,
    raw: Mapping[str, Any],
) -> Dict[str, str]:
    """维度 dict → 仅含 schema 规范字段键的中文段落。"""
    buckets: Dict[str, list[str]] = defaultdict(list)

    for raw_k, raw_v in raw.items():
        prose = worldbuilding_value_to_prose(raw_v)
        if not prose:
            continue
        target = resolve_canonical_field(dim_key, str(raw_k))
        if not target:
            continue
        if target in buckets and prose in buckets[target]:
            continue
        buckets[target].append(prose)

    return {k: "\n\n".join(parts) for k, parts in buckets.items() if parts}


def build_fields_desc_for_prompt(dimension_keys: Any = None) -> str:
    """CPMS user.md 的 {fields_desc} 占位内容。"""
    lines: list[str] = []
    keys = tuple(dimension_keys or WORLD_BUILDING_DIMENSION_KEYS)
    for dim_key in keys:
        dim_def = WORLDBUILDING_DIMENSION_DEFS[dim_key]
        lines.append(f'    "{dim_key}": {{')
        fields = list(dim_def["fields"].items())
        for idx, (fk, desc) in enumerate(fields):
            comma = "," if idx < len(fields) - 1 else ""
            scope = WORLDBUILDING_FIELD_SCOPE_HINTS.get(dim_key, {}).get(fk, "")
            scope_text = f"{scope}；" if scope else ""
            lines.append(
                f'      "{fk}": "（{desc}。{scope_text}只写1-2句、60-120字、单段；不得换行；勿嵌套JSON或英文键）"{comma}'
            )
        dim_comma = "," if dim_key != keys[-1] else ""
        lines.append(f"    }}{dim_comma}")
    return "\n".join(lines)
