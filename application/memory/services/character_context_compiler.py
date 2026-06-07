from __future__ import annotations

from typing import Any, Dict, List


class CharacterContextCompiler:
    """Compile character projection data into T0/T1/T2 prompt locks."""

    def compile(self, projection: Dict[str, Any]) -> Dict[str, str]:
        name = str(projection.get("name") or projection.get("entity_id") or "")
        constitution = projection.get("constitution") or {}
        current_state = projection.get("current_state") or {}
        voice = projection.get("voice_fingerprint") or {}
        scars = projection.get("active_scars") or []
        motivations = projection.get("active_motivations") or []
        knowledge = projection.get("knowledge_boundary") or {}

        t0_parts: List[str] = [f"- {name}"]
        if constitution.get("public_profile"):
            t0_parts.append(f"公开面:{constitution['public_profile']}")
        if constitution.get("core_belief"):
            t0_parts.append(f"核心信念:{constitution['core_belief']}")
        for taboo in constitution.get("moral_taboos") or []:
            t0_parts.append(f"禁忌:{str(taboo)[:120]}")
        if current_state.get("summary"):
            t0_parts.append(f"当前状态:{current_state['summary']}")
        for scar in scars[:2]:
            impact = scar.get("impact") or scar.get("description") or ""
            source = scar.get("source_event") or ""
            if impact or source:
                t0_parts.append(f"创伤:{source}->{impact}".strip("->"))
        for motivation in motivations[:2]:
            desc = motivation.get("description") or ""
            if desc:
                t0_parts.append(f"驱动力:{desc}")
        if voice:
            bits = [str(voice.get(k) or "") for k in ("style", "sentence_pattern", "speech_tempo") if voice.get(k)]
            if bits:
                t0_parts.append("声线:" + " / ".join(bits[:3]))
            phrases = voice.get("catchphrases") or []
            if phrases:
                t0_parts.append("口癖:" + "、".join(str(x) for x in phrases[:3]))
        unknown = knowledge.get("unknown") or []
        if unknown:
            t0_parts.append("知识边界:" + "；".join(str(x) for x in unknown[:3]))
        if constitution.get("core_belief"):
            t0_parts.append(f"禁止漂移:不得无因违背核心信念：{constitution['core_belief'][:80]}")

        t1 = f"- {name}"
        if current_state.get("summary"):
            t1 += f" | 状态:{current_state['summary']}"
        rels = projection.get("relationships") or []
        if rels:
            t1 += " | 关系张力:" + "；".join(str(r.get("description") or r.get("text") or "") for r in rels[:2])

        return {
            "t0": " | ".join(x for x in t0_parts if x),
            "t1": t1,
            "t2": f"- {name}：允许过场/提及，禁止抢走主线焦点",
        }

