"""从结构化开篇指标生成类型开篇画像配置。

输入只读取聚合指标，不读取或保存章节正文。
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import yaml


PRIMARY_CONTRACTS: dict[str, list[str]] = {
    "玄幻": ["天赋差距或资源压迫要尽早成形", "成长路径和阶段性收益必须可感知", "第一章需要给出可继续追读的升级期待"],
    "奇幻": ["异常规则和世界危险要通过事件暴露", "能力或职业机制要有明确代价", "冒险目标不能停留在设定说明"],
    "武侠": ["江湖关系和武力压迫要先落地", "人物选择要牵出恩怨或道义代价", "动作场面服务于立场与关系变化"],
    "仙侠": ["修行目标、境界压力和资源稀缺要前置", "规则通过冲突暴露而不是长篇解释", "章末保留修行或身份问题的追问"],
    "都市": ["现实身份压迫要快速建立", "能力或机会触发后要有可见反转", "第一章至少兑现一个现实收益或情绪收益"],
    "现实题材": ["现实困境和职业矛盾要可信", "情绪落点比设定奇观更重要", "章末要保留生活问题或关系问题的继续性"],
    "科幻": ["技术异常、社会代价和生存压力要同步出现", "设定必须绑定主角选择", "不要用纯说明替代第一章事件"],
    "游戏": ["规则、任务、评分或奖励反馈要尽早可见", "失败代价和成长收益要成对出现", "读者需要看到可重复的爽点循环"],
    "体育": ["赛事目标、训练压力和胜负反馈要清晰", "竞技动作要绑定角色处境", "短线目标需要快速推进"],
    "历史": ["身份处境和时代约束要先成立", "选择代价要具体", "历史信息通过冲突和人物关系释放"],
    "军事": ["任务压力、组织纪律和危险边界要明确", "专业信息必须服务场景决策", "章末保留任务升级或威胁扩大"],
    "悬疑": ["反常细节和核心疑点要第一时间出现", "追问链要不断推动读者往下看", "解释不能早于悬念积累"],
    "诸天无限": ["副本规则、任务边界和失败代价要清楚", "跨世界收益要能持续驱动", "第一章必须建立进入机制和目标"],
    "轻小说": ["人设反差和关系张力要前置", "节奏要轻快但不能无冲突", "第一章需要给出角色互动期待"],
    "短篇": ["短线冲突和情绪闭环要更快", "信息密度高于长线铺垫", "章末钩子要服务下一段即时阅读"],
}


PRIMARY_ENTRIES: dict[str, tuple[str, str, str]] = {
    "玄幻": ("资源争夺", "规则冲突", "阶段性突破或地位反转"),
    "奇幻": ("异常事件", "世界规则", "能力代价或冒险目标"),
    "武侠": ("江湖压迫", "门派或恩怨规则", "立场选择或武力反击"),
    "仙侠": ("修行困境", "境界或资源规则", "修行机会或身份疑问"),
    "都市": ("现实困境", "能力或机会触发", "即时反击或收益兑现"),
    "现实题材": ("生活或职业困境", "现实规则", "情绪确认或问题升级"),
    "科幻": ("技术异常", "技术或社会规则", "生存选择或代价显现"),
    "游戏": ("任务或比赛入口", "规则反馈", "奖励、排名或能力成长"),
    "体育": ("赛事或训练压力", "竞技规则", "胜负反馈或目标推进"),
    "历史": ("身份处境", "时代规则", "选择代价或局势升级"),
    "军事": ("任务威胁", "组织或战场规则", "行动结果或威胁升级"),
    "悬疑": ("反常细节", "线索规则", "新疑点或追问升级"),
    "诸天无限": ("副本入口", "任务规则", "奖励、失败代价或世界切换"),
    "轻小说": ("人设反差", "关系规则", "互动期待或关系推进"),
    "短篇": ("即时冲突", "短线规则", "情绪落点或反转"),
}


PRIMARY_ALIASES: dict[str, str] = {
    "修仙": "仙侠",
    "修真": "仙侠",
    "仙侠武侠": "仙侠",
    "武侠仙侠": "仙侠",
    "幻想": "奇幻",
    "西幻": "奇幻",
    "现代": "都市",
    "城市": "都市",
    "都市脑洞": "都市",
    "电竞": "游戏",
    "无限流": "诸天无限",
}


def _strength(value: float, high: float, mid: float) -> str:
    if value >= high:
        return "强"
    if value >= mid:
        return "中"
    return "低"


def _payoff_interval(avg_chars: float, hook_ratio: float) -> str:
    if hook_ratio >= 0.68 or avg_chars <= 2400:
        return "短"
    if hook_ratio >= 0.55:
        return "中"
    return "中长"


def _profile_from_row(row: dict[str, Any]) -> dict[str, Any]:
    primary = str(row["primary"])
    conflict_entry, rule_entry, payoff_entry = PRIMARY_ENTRIES.get(primary, ("类型冲突", "类型规则", "阶段收益"))
    reader_promise = list(
        PRIMARY_CONTRACTS.get(primary, ["类型承诺要在第一章内可见", "冲突、规则和收益必须闭环", "避免只铺设定不推进事件"])
    )
    if row["system_ratio"] >= 0.45:
        reader_promise.append("规则反馈、面板或机制提示需要明确但不能替代剧情")
    if row["conflict_avg"] >= 9:
        reader_promise.append("第一章冲突强度要高于普通铺垫")
    if row["ending_hook_ratio"] >= 0.68:
        reader_promise.append("章末必须保留明确钩子，承接下一章行动")
    return {
        "reader_promise": reader_promise,
        "opening_mechanism": {
            "conflict_entry": conflict_entry,
            "rule_entry": rule_entry,
            "payoff_entry": payoff_entry,
            "information_release": "事件中释放",
        },
        "rhythm_constraints": {
            "first_screen_hook": _strength(row["opening_dialogue_ratio"] + row["conflict_avg"] / 20, 0.72, 0.48),
            "conflict_density": _strength(row["conflict_avg"], 9.0, 6.0),
            "mechanic_visibility": _strength(row["system_ratio"], 0.45, 0.2),
            "sensory_density": _strength(row["sensory_avg"], 28.0, 21.0),
            "ending_hook_strength": _strength(row["ending_hook_ratio"], 0.68, 0.55),
            "payoff_interval": _payoff_interval(row["avg_chars"], row["ending_hook_ratio"]),
            "target_avg_chars": int(round(row["avg_chars"])),
        },
        "metric_snapshot": {
            "book_count": row["book_count"],
            "chapter_count": row["chapter_count"],
            "avg_chars": row["avg_chars"],
            "dialogue_density": row["dialogue_density"],
            "system_ratio": row["system_ratio"],
            "ending_hook_ratio": row["ending_hook_ratio"],
        },
    }


def build_profiles(metrics: dict[str, Any]) -> dict[str, Any]:
    primary_defaults = {row["primary"]: _profile_from_row(row) for row in metrics["primary_metrics"]}
    profiles: dict[str, dict[str, Any]] = {}
    for row in metrics["secondary_metrics"]:
        profiles.setdefault(row["primary"], {})[row["secondary"]] = _profile_from_row(row)
    return {
        "schema_kind": "plotpilot.genre_opening_profiles",
        "schema_version": 1,
        "locale": "zh-CN",
        "source_metrics": "data/genre_intelligence/opening_pattern_metrics_2026-05-31.json",
        "copyright_policy": "只保存分类画像、聚合指标和结构化写作约束；不保存章节正文。",
        "resolution_policy": {
            "label_separators": ["/", "／", "-", "—", ">", "→"],
            "missing_profile": "block_generation",
            "fallback": "只允许回退到同一一级分类的 primary_defaults；禁止回退到硬编码提示词。",
        },
        "primary_aliases": PRIMARY_ALIASES,
        "primary_defaults": primary_defaults,
        "profiles": profiles,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--metrics",
        default="data/genre_intelligence/opening_pattern_metrics_2026-05-31.json",
    )
    parser.add_argument(
        "--output",
        default="shared/taxonomy/opening_pattern_profiles_cn_v1.yaml",
    )
    args = parser.parse_args()
    metrics = json.loads(Path(args.metrics).read_text(encoding="utf-8"))
    payload = build_profiles(metrics)
    Path(args.output).write_text(
        yaml.safe_dump(payload, allow_unicode=True, sort_keys=False, width=120),
        encoding="utf-8",
    )
    secondary_count = sum(len(items) for items in payload["profiles"].values())
    print(f"wrote {args.output} primary={len(payload['primary_defaults'])} secondary={secondary_count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

