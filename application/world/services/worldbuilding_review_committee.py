import json
from datetime import datetime
from typing import Any, Dict, List

from domain.ai.services.llm_service import GenerationConfig
from domain.ai.value_objects.prompt import Prompt


FACT_REVIEWER_SYSTEM_PROMPT = """你是“事实审查官”。你将审查世界观设定是否严格遵守《硬约束事实》与证据来源。

只输出有效 JSON，不要输出任何其他文字。"""

GENRE_REVIEWER_SYSTEM_PROMPT = """你是“题材审查官”。你将审查世界观是否符合题材与时代气质，是否跑偏。

只输出有效 JSON，不要输出任何其他文字。"""

READER_REVIEWER_SYSTEM_PROMPT = """你是“读者体验官”。你将从网文读者体验角度审查：爽点、冲突、可玩性、可读性、以及输出结构是否可用。

只输出有效 JSON，不要输出任何其他文字。"""


def build_review_prompt(
    reviewer_role: str,
    premise: str,
    research_injection: str,
    worldbuilding_json: Dict[str, Any],
) -> Prompt:
    if reviewer_role == "fact":
        system = FACT_REVIEWER_SYSTEM_PROMPT
    elif reviewer_role == "genre":
        system = GENRE_REVIEWER_SYSTEM_PROMPT
    else:
        system = READER_REVIEWER_SYSTEM_PROMPT

    schema = """输出 JSON schema：
{
  "reviewer_role": "fact|genre|reader",
  "verdict": "approve|rework|reject",
  "score": 0,
  "redlines_triggered": ["fact_conflict|format_invalid|genre_mismatch"],
  "needs_research_rework": true,
  "issues": [{"severity":"high|medium|low","title":"...","detail":"..."}],
  "fix_instructions": ["..."]
}
"""

    user = f"""故事创意：
{premise}

{research_injection}

世界观 JSON：
{json.dumps(worldbuilding_json, ensure_ascii=False)}

评审要求：
1. 严格按 schema 输出 JSON
2. redlines_triggered 必须是数组
3. needs_research_rework 仅在“需要补充事实/来源”时为 true

{schema}
"""
    return Prompt(system=system, user=user)


def _parse_json_loose(text: str) -> Dict[str, Any]:
    if not text:
        raise ValueError("empty")
    s = text.strip()
    if "```" in s:
        parts = s.split("```")
        if len(parts) >= 2:
            s = parts[1]
    s = s.strip()
    start = s.find("{")
    end = s.rfind("}")
    if start != -1 and end != -1 and end > start:
        s = s[start : end + 1]
    return json.loads(s)


async def run_reviewer(
    llm_service: Any,
    reviewer_role: str,
    premise: str,
    research_injection: str,
    worldbuilding_json: Dict[str, Any],
    model: str = "",
) -> Dict[str, Any]:
    prompt = build_review_prompt(reviewer_role, premise, research_injection, worldbuilding_json)
    config = GenerationConfig(model=model or "", max_tokens=1536, temperature=0.2)
    result = await llm_service.generate(prompt, config)
    parsed = _parse_json_loose(result.content)
    parsed["reviewer_role"] = reviewer_role
    if "redlines_triggered" not in parsed or not isinstance(parsed["redlines_triggered"], list):
        parsed["redlines_triggered"] = []
    if "needs_research_rework" not in parsed:
        parsed["needs_research_rework"] = False
    if "issues" not in parsed or not isinstance(parsed["issues"], list):
        parsed["issues"] = []
    if "fix_instructions" not in parsed or not isinstance(parsed["fix_instructions"], list):
        parsed["fix_instructions"] = []
    if "score" not in parsed:
        parsed["score"] = 0
    if "verdict" not in parsed:
        parsed["verdict"] = "rework"
    return parsed


def aggregate_reviews(reviews: List[Dict[str, Any]]) -> Dict[str, Any]:
    redline_veto = any(bool(r.get("redlines_triggered")) for r in reviews)
    needs_research_rework = any(bool(r.get("needs_research_rework")) for r in reviews)

    instructions: List[str] = []
    seen = set()
    for r in reviews:
        for ins in r.get("fix_instructions") or []:
            s = str(ins).strip()
            if s and s not in seen:
                seen.add(s)
                instructions.append(s)

    avg = 0
    if reviews:
        avg = int(sum(int(r.get("score") or 0) for r in reviews) / len(reviews))

    approve_votes = sum(1 for r in reviews if r.get("verdict") == "approve")

    if redline_veto:
        final_verdict = "rework"
    else:
        if approve_votes >= 2 and avg >= 75:
            final_verdict = "approve"
        else:
            final_verdict = "rework"

    return {
        "version": 1,
        "created_at": datetime.utcnow().isoformat(),
        "reviews": reviews,
        "final_verdict": final_verdict,
        "final_score": avg,
        "redline_veto": redline_veto,
        "needs_research_rework": needs_research_rework,
        "merged_fix_instructions": instructions,
    }
