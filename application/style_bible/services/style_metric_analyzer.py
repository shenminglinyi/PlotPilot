"""写作手法知识库风格指标分析。"""
from __future__ import annotations

import re
from typing import Any

from application.audit.services.cliche_scanner import ClicheScanner


class StyleMetricAnalyzer:
    """用确定性启发式提取可用于提示词的写作指标。"""

    SENTENCE_RE = re.compile(r"[^。！？!?]+[。！？!?]?")
    QUOTED_DIALOGUE_RE = re.compile(r"[“「『](.*?)[”」』]")
    BLANK_LINE_RE = re.compile(r"\n\s*\n+")

    DIALOGUE_MARKERS = ("说", "问", "答", "喊", "低声", "开口", "道")
    ACTION_MARKERS = ("走", "推", "拉", "抬", "转", "握", "冲", "停", "看", "拿")
    PSYCHOLOGY_MARKERS = ("想", "觉得", "意识到", "心里", "脑海", "明白", "害怕", "犹豫")
    ENVIRONMENT_MARKERS = ("雨", "风", "灯", "门", "窗", "街", "夜", "屋", "楼", "光", "影")

    def __init__(self, cliche_scanner: ClicheScanner | None = None):
        self.cliche_scanner = cliche_scanner or ClicheScanner()

    def analyze(self, text: str) -> dict[str, Any]:
        content = (text or "").strip()
        if not content:
            return self._empty_metrics(sample_count=1)

        paragraphs = self._split_paragraphs(content)
        sentences = self._split_sentences(content)
        sentence_count = len(sentences)
        char_count = len(re.sub(r"\s+", "", content))
        dialogue_chars = self._dialogue_char_count(content, sentences)
        cliche_hits = self.cliche_scanner.scan_cliches(content)

        return {
            "sample_count": 1,
            "char_count": char_count,
            "sentence_count": sentence_count,
            "paragraph_count": len(paragraphs),
            "avg_sentence_length": round(char_count / sentence_count, 2)
            if sentence_count
            else 0.0,
            "avg_paragraph_length": round(char_count / len(paragraphs), 2)
            if paragraphs
            else 0.0,
            "dialogue_ratio": self._ratio(dialogue_chars, char_count),
            "action_ratio": self._sentence_ratio(sentences, self.ACTION_MARKERS),
            "psychology_ratio": self._sentence_ratio(sentences, self.PSYCHOLOGY_MARKERS),
            "environment_ratio": self._sentence_ratio(sentences, self.ENVIRONMENT_MARKERS),
            "cliche_hit_count": len(cliche_hits),
            "cliche_patterns": sorted({hit.pattern for hit in cliche_hits}),
            "hook_score": self._hook_score(sentences),
        }

    def aggregate(self, metrics_list: list[dict[str, Any]]) -> dict[str, Any]:
        valid_metrics = [metrics for metrics in metrics_list if metrics]
        if not valid_metrics:
            return self._empty_metrics(sample_count=0)

        sample_count = len(valid_metrics)
        char_count = sum(int(metrics.get("char_count") or 0) for metrics in valid_metrics)
        sentence_count = sum(
            int(metrics.get("sentence_count") or 0) for metrics in valid_metrics
        )
        paragraph_count = sum(
            int(metrics.get("paragraph_count") or 0) for metrics in valid_metrics
        )
        cliche_patterns: set[str] = set()
        for metrics in valid_metrics:
            cliche_patterns.update(str(item) for item in metrics.get("cliche_patterns") or [])

        return {
            "sample_count": sample_count,
            "char_count": char_count,
            "sentence_count": sentence_count,
            "paragraph_count": paragraph_count,
            "avg_sentence_length": round(char_count / sentence_count, 2)
            if sentence_count
            else 0.0,
            "avg_paragraph_length": round(char_count / paragraph_count, 2)
            if paragraph_count
            else 0.0,
            "dialogue_ratio": self._weighted_average(valid_metrics, "dialogue_ratio"),
            "action_ratio": self._weighted_average(valid_metrics, "action_ratio"),
            "psychology_ratio": self._weighted_average(valid_metrics, "psychology_ratio"),
            "environment_ratio": self._weighted_average(valid_metrics, "environment_ratio"),
            "cliche_hit_count": sum(
                int(metrics.get("cliche_hit_count") or 0) for metrics in valid_metrics
            ),
            "cliche_patterns": sorted(cliche_patterns),
            "hook_score": self._weighted_average(valid_metrics, "hook_score"),
        }

    def _split_paragraphs(self, text: str) -> list[str]:
        return [
            paragraph.strip()
            for paragraph in self.BLANK_LINE_RE.split(text.strip())
            if paragraph.strip()
        ]

    def _split_sentences(self, text: str) -> list[str]:
        return [
            sentence.strip()
            for sentence in self.SENTENCE_RE.findall(text)
            if sentence.strip()
        ]

    def _dialogue_char_count(self, text: str, sentences: list[str]) -> int:
        quoted_count = sum(len(match.group(1)) for match in self.QUOTED_DIALOGUE_RE.finditer(text))
        marker_count = sum(
            len(sentence)
            for sentence in sentences
            if any(marker in sentence for marker in self.DIALOGUE_MARKERS)
        )
        return max(quoted_count, marker_count)

    def _sentence_ratio(self, sentences: list[str], markers: tuple[str, ...]) -> float:
        if not sentences:
            return 0.0
        count = sum(1 for sentence in sentences if any(marker in sentence for marker in markers))
        return round(count / len(sentences), 4)

    def _hook_score(self, sentences: list[str]) -> float:
        if not sentences:
            return 0.0
        ending = sentences[-1]
        markers = ("？", "?", "忽然", "却", "不是", "门", "人影", "声音")
        return 1.0 if any(marker in ending for marker in markers) else 0.0

    @staticmethod
    def _ratio(part: int, whole: int) -> float:
        return round(part / whole, 4) if whole else 0.0

    @staticmethod
    def _weighted_average(metrics_list: list[dict[str, Any]], key: str) -> float:
        total_weight = sum(int(metrics.get("char_count") or 0) for metrics in metrics_list)
        if total_weight <= 0:
            return 0.0
        total = sum(
            float(metrics.get(key) or 0.0) * int(metrics.get("char_count") or 0)
            for metrics in metrics_list
        )
        return round(total / total_weight, 4)

    @staticmethod
    def _empty_metrics(sample_count: int) -> dict[str, Any]:
        return {
            "sample_count": sample_count,
            "char_count": 0,
            "sentence_count": 0,
            "paragraph_count": 0,
            "avg_sentence_length": 0.0,
            "avg_paragraph_length": 0.0,
            "dialogue_ratio": 0.0,
            "action_ratio": 0.0,
            "psychology_ratio": 0.0,
            "environment_ratio": 0.0,
            "cliche_hit_count": 0,
            "cliche_patterns": [],
            "hook_score": 0.0,
        }
