"""LLM 文风分析服务

使用 LLM 分析章节的写作风格特征，生成风格向量用于漂移检测。
相比统计特征方法，能捕捉更深层的风格特点：
- 叙事视角和人称使用
- 对话与描写的比例
- 情感表达方式
- 节奏和韵律
- 用词偏好和修辞手法

成本：约 500 token/章（300 输入 + 200 输出）
"""
import json
import logging
from typing import Any, Dict, List, Optional

from domain.ai.services.llm_service import LLMService, GenerationConfig
from domain.ai.value_objects.prompt import Prompt

logger = logging.getLogger(__name__)

# 风格维度定义
STYLE_DIMENSIONS = [
    "narrative_voice",      # 叙事声音：第一人称/第三人称/全知视角
    "dialogue_ratio",       # 对话占比：0-1
    "description_depth",    # 描写深度：0-1（浮光掠影 vs 细腻入微）
    "emotional_intensity",  # 情感强度：0-1
    "pacing",               # 节奏：0-1（舒缓 vs 紧凑）
    "sensory_richness",     # 感官丰富度：0-1
    "metaphor_usage",       # 修辞使用：0-1
    "sentence_variety",     # 句式变化：0-1
]

# 风格分析 Prompt（中文）
STYLE_ANALYSIS_PROMPT = """你是专业的小说风格分析师。请分析以下章节的写作风格特征。

## 分析要求
输出 JSON 格式，包含以下维度（每项 0-1 分）：
1. narrative_voice: 叙事声音（0=第一人称，0.5=第三人称限制，1=全知视角）
2. dialogue_ratio: 对话占比（估算对话内容占正文的比重）
3. description_depth: 描写深度（0=轻描淡写，1=细腻入微）
4. emotional_intensity: 情感强度（0=冷静客观，1=情绪饱满）
5. pacing: 节奏（0=舒缓悠长，1=紧凑急促）
6. sensory_richness: 感官丰富度（视觉/听觉/触觉/嗅觉/味觉描写）
7. metaphor_usage: 修辞使用频率（比喻/拟人/排比等）
8. sentence_variety: 句式变化程度（长短句交替、句型多样性）

## 章节内容
{content}

## 输出格式
只输出 JSON，不要其他文字：
{{"narrative_voice": 0.5, "dialogue_ratio": 0.3, "description_depth": 0.7, "emotional_intensity": 0.6, "pacing": 0.4, "sensory_richness": 0.5, "metaphor_usage": 0.3, "sentence_variety": 0.6}}"""

# 基准风格提取 Prompt（从多章节中提取平均风格）
BASELINE_PROMPT = """你是专业的小说风格分析师。请根据以下章节风格数据，提取这本小说的基准写作风格。

## 已分析章节的风格数据
{style_data}

## 输出要求
1. 计算各维度的平均值和标准差
2. 输出 JSON 格式，包含：
   - baseline: 各维度的平均值
   - tolerance: 各维度的可接受偏差范围（通常设为 1.5 倍标准差）

只输出 JSON，不要其他文字：
{{"baseline": {{...}}, "tolerance": {{...}}}}"""


class LLMVoiceAnalysisService:
    """LLM 文风分析服务"""

    def __init__(self, llm_service: LLMService):
        self._llm = llm_service
        # 缓存已分析的章节风格
        self._cache: Dict[str, Dict[str, float]] = {}

    async def analyze_chapter_style(
        self,
        novel_id: str,
        chapter_number: int,
        content: str,
    ) -> Dict[str, Any]:
        """分析单个章节的写作风格

        Args:
            novel_id: 小说 ID
            chapter_number: 章节号
            content: 章节内容

        Returns:
            风格向量字典，包含各维度分数和元数据
        """
        cache_key = f"{novel_id}:{chapter_number}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        # 截取内容（最多 2000 字，节省 token）
        snippet = content[:2000] if len(content) > 2000 else content

        try:
            prompt = Prompt(
                system="你是专业的小说风格分析师，输出纯 JSON 格式。",
                user=STYLE_ANALYSIS_PROMPT.format(content=snippet)
            )
            config = GenerationConfig(max_tokens=200, temperature=0.1)

            result = await self._llm.generate(prompt, config)
            raw = result.content.strip()

            # 解析 JSON
            style_vector = self._parse_style_json(raw)

            # 添加元数据
            style_vector["_meta"] = {
                "chapter_number": chapter_number,
                "content_length": len(content),
                "snippet_length": len(snippet),
            }

            # 缓存结果
            self._cache[cache_key] = style_vector

            logger.debug(
                "LLM 文风分析完成 novel=%s ch=%d dimensions=%s",
                novel_id, chapter_number, list(style_vector.keys())[:8]
            )

            return style_vector

        except Exception as e:
            logger.warning(
                "LLM 文风分析失败 novel=%s ch=%d: %s",
                novel_id, chapter_number, e
            )
            # 返回中性值，避免阻断流程
            return self._get_neutral_style(chapter_number)

    async def compute_baseline(
        self,
        novel_id: str,
        style_vectors: List[Dict[str, float]],
    ) -> Dict[str, Any]:
        """从多个风格向量中计算基准风格

        Args:
            novel_id: 小说 ID
            style_vectors: 已分析的章节风格向量列表

        Returns:
            包含 baseline（基准值）和 tolerance（容差）的字典
        """
        if not style_vectors:
            return self._get_default_baseline()

        # 如果样本少，直接计算平均值
        if len(style_vectors) < 5:
            return self._compute_simple_baseline(style_vectors)

        # 样本足够时，用 LLM 提取更智能的基准
        try:
            # 准备数据
            style_data = []
            for i, vec in enumerate(style_vectors[-10:]):  # 最多取最近 10 章
                clean_vec = {k: v for k, v in vec.items() if not k.startswith("_")}
                style_data.append(f"章节{i+1}: {json.dumps(clean_vec, ensure_ascii=False)}")

            prompt = Prompt(
                system="你是专业的小说风格分析师，输出纯 JSON 格式。",
                user=BASELINE_PROMPT.format(style_data="\n".join(style_data))
            )
            config = GenerationConfig(max_tokens=300, temperature=0.1)

            result = await self._llm.generate(prompt, config)
            raw = result.content.strip()

            baseline_data = self._parse_baseline_json(raw)
            logger.info("LLM 基准风格提取完成 novel=%s", novel_id)
            return baseline_data

        except Exception as e:
            logger.warning("LLM 基准风格提取失败 novel=%s: %s", novel_id, e)
            return self._compute_simple_baseline(style_vectors)

    def compute_drift_score(
        self,
        style_vector: Dict[str, float],
        baseline: Dict[str, Any],
    ) -> float:
        """计算风格漂移分数（0-1，越高越接近基准）

        Args:
            style_vector: 当前章节的风格向量
            baseline: 基准风格数据（含 baseline 和 tolerance）

        Returns:
            相似度分数（0-1）
        """
        if not baseline or "baseline" not in baseline:
            return 1.0  # 无基准时不判漂移

        base = baseline.get("baseline", {})
        tol = baseline.get("tolerance", {})

        total_diff = 0.0
        dimensions = 0

        for dim in STYLE_DIMENSIONS:
            if dim not in base:
                continue

            current_val = style_vector.get(dim, 0.5)
            base_val = base.get(dim, 0.5)
            tolerance = tol.get(dim, 0.2)  # 默认容差

            # 计算相对偏差
            if tolerance > 0:
                rel_diff = abs(current_val - base_val) / tolerance
            else:
                rel_diff = abs(current_val - base_val)

            # 归一化到 0-1
            normalized_diff = min(1.0, rel_diff)
            total_diff += normalized_diff
            dimensions += 1

        if dimensions == 0:
            return 1.0

        # 相似度 = 1 - 平均偏差
        avg_diff = total_diff / dimensions
        similarity = max(0.0, 1.0 - avg_diff)

        return round(similarity, 4)

    def _parse_style_json(self, raw: str) -> Dict[str, float]:
        """解析风格 JSON"""
        try:
            # 尝试直接解析
            data = json.loads(raw)
            result = {}
            for dim in STYLE_DIMENSIONS:
                val = data.get(dim, 0.5)
                result[dim] = max(0.0, min(1.0, float(val)))
            return result
        except json.JSONDecodeError:
            # 尝试提取 JSON 块
            import re
            match = re.search(r'\{[^}]+\}', raw)
            if match:
                try:
                    data = json.loads(match.group())
                    result = {}
                    for dim in STYLE_DIMENSIONS:
                        val = data.get(dim, 0.5)
                        result[dim] = max(0.0, min(1.0, float(val)))
                    return result
                except:
                    pass
            return self._get_neutral_style(0)

    def _parse_baseline_json(self, raw: str) -> Dict[str, Any]:
        """解析基准风格 JSON"""
        try:
            data = json.loads(raw)
            return {
                "baseline": data.get("baseline", {}),
                "tolerance": data.get("tolerance", {}),
            }
        except json.JSONDecodeError:
            import re
            match = re.search(r'\{.*\}', raw, re.DOTALL)
            if match:
                try:
                    data = json.loads(match.group())
                    return {
                        "baseline": data.get("baseline", {}),
                        "tolerance": data.get("tolerance", {}),
                    }
                except:
                    pass
            return self._get_default_baseline()

    def _get_neutral_style(self, chapter_number: int) -> Dict[str, Any]:
        """返回中性风格向量"""
        return {
            dim: 0.5 for dim in STYLE_DIMENSIONS
        }

    def _get_default_baseline(self) -> Dict[str, Any]:
        """返回默认基准"""
        baseline = {dim: 0.5 for dim in STYLE_DIMENSIONS}
        tolerance = {dim: 0.3 for dim in STYLE_DIMENSIONS}
        return {"baseline": baseline, "tolerance": tolerance}

    def _compute_simple_baseline(self, style_vectors: List[Dict[str, float]]) -> Dict[str, Any]:
        """简单平均计算基准"""
        if not style_vectors:
            return self._get_default_baseline()

        # 过滤掉元数据
        clean_vectors = []
        for vec in style_vectors:
            clean = {k: v for k, v in vec.items() if not k.startswith("_")}
            clean_vectors.append(clean)

        # 计算平均值和标准差
        baseline = {}
        tolerance = {}

        for dim in STYLE_DIMENSIONS:
            values = [v.get(dim, 0.5) for v in clean_vectors if dim in v]
            if values:
                avg = sum(values) / len(values)
                # 标准差
                if len(values) > 1:
                    variance = sum((x - avg) ** 2 for x in values) / len(values)
                    std = variance ** 0.5
                else:
                    std = 0.2
                baseline[dim] = round(avg, 4)
                tolerance[dim] = round(max(0.1, std * 1.5), 4)
            else:
                baseline[dim] = 0.5
                tolerance[dim] = 0.3

        return {"baseline": baseline, "tolerance": tolerance}
