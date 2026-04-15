"""文风漂移监控服务

支持两种模式：
1. 统计模式（默认）：基于形容词密度、句长等统计特征，零成本
2. LLM 模式：使用 LLM 分析深度风格特征，约 500 token/章

连续 N 章低于阈值时发出告警。
"""
import re
import logging
from typing import TYPE_CHECKING, List, Optional

if TYPE_CHECKING:
    from application.analyst.services.llm_voice_analysis_service import LLMVoiceAnalysisService

logger = logging.getLogger(__name__)

# 连续低分章节数触发告警
DRIFT_ALERT_CONSECUTIVE = 5
# 相似度告警阈值
DRIFT_ALERT_THRESHOLD = 0.75

# 常见形容词集合（与 VoiceFingerprintService 保持一致）
_COMMON_ADJECTIVES = set(
    "美丽漂亮英俊帅气可爱温柔善良聪明勇敢坚强勤奋努力认真仔细小心谨慎"
    "大小高低长短粗细胖瘦快慢冷热新旧好坏多少轻重深浅明暗干湿软硬"
    "红橙黄绿青蓝紫黑白灰粉棕金银"
)


class VoiceDriftService:
    """文风漂移监控服务

    支持统计模式和 LLM 模式：
    - 统计模式：零成本，基于简单的文本统计
    - LLM 模式：约 500 token/章，捕捉深度风格特征
    """

    def __init__(
        self,
        score_repo,
        fingerprint_repo,
        llm_voice_service: Optional["LLMVoiceAnalysisService"] = None,
        use_llm_mode: bool = False,
    ):
        """
        Args:
            score_repo: SqliteChapterStyleScoreRepository
            fingerprint_repo: VoiceFingerprintRepository
            llm_voice_service: LLM 文风分析服务（可选）
            use_llm_mode: 是否使用 LLM 模式（默认 False，使用统计模式）
        """
        self.score_repo = score_repo
        self.fingerprint_repo = fingerprint_repo
        self.llm_voice_service = llm_voice_service
        self.use_llm_mode = use_llm_mode

        # LLM 模式下的基准风格缓存
        self._baseline_cache: dict = {}

    # ------------------------------------------------------------------
    # 公开接口
    # ------------------------------------------------------------------

    async def score_chapter_async(
        self,
        novel_id: str,
        chapter_number: int,
        content: str,
        pov_character_id: Optional[str] = None,
    ) -> dict:
        """异步版本：计算章节文风评分并持久化（支持 LLM 模式）

        Returns:
            包含 chapter_number, similarity_score, drift_alert 的字典
        """
        if self.use_llm_mode and self.llm_voice_service:
            return await self._score_chapter_llm(novel_id, chapter_number, content)
        else:
            return self.score_chapter(novel_id, chapter_number, content, pov_character_id)

    def score_chapter(
        self,
        novel_id: str,
        chapter_number: int,
        content: str,
        pov_character_id: Optional[str] = None,
    ) -> dict:
        """同步版本：统计模式计算章节文风评分并持久化。

        若作者指纹不存在，similarity_score 记为 None。

        Returns:
            包含 chapter_number, similarity_score, drift_alert 的字典
        """
        metrics = self._compute_metrics(content)
        fingerprint = self.fingerprint_repo.get_by_novel(novel_id, pov_character_id)

        if fingerprint and fingerprint.get("sample_count", 0) >= 10:
            similarity = self._cosine_similarity(metrics, fingerprint)
        else:
            similarity = None

        self.score_repo.upsert(
            novel_id=novel_id,
            chapter_number=chapter_number,
            adjective_density=metrics["adjective_density"],
            avg_sentence_length=metrics["avg_sentence_length"],
            sentence_count=metrics["sentence_count"],
            # 无指纹基准时存 0.0（NOT NULL 约束），业务层通过 fingerprint 是否存在来区分
            similarity_score=similarity if similarity is not None else 0.0,
        )

        drift_alert = self._check_drift_alert(novel_id)

        return {
            "chapter_number": chapter_number,
            "metrics": metrics,
            "similarity_score": similarity,
            "drift_alert": drift_alert,
            "mode": "statistics",
        }

    async def _score_chapter_llm(
        self,
        novel_id: str,
        chapter_number: int,
        content: str,
    ) -> dict:
        """LLM 模式：使用 LLM 分析章节风格

        自动建立基准：前 5 章用于建立基准，之后开始检测漂移。
        """
        # 1. 分析当前章节风格
        style_vector = await self.llm_voice_service.analyze_chapter_style(
            novel_id, chapter_number, content
        )

        # 2. 获取或建立基准
        baseline = self._get_or_init_baseline(novel_id)

        # 3. 计算相似度
        if baseline and chapter_number > 5:
            similarity = self.llm_voice_service.compute_drift_score(style_vector, baseline)
        else:
            # 前 5 章用于建立基准，不判漂移
            similarity = None

        # 4. 更新基准（每 5 章重新计算）
        if chapter_number % 5 == 0:
            await self._update_baseline(novel_id)

        # 5. 持久化（兼容现有表结构）
        metrics = {
            "adjective_density": style_vector.get("description_depth", 0.5),
            "avg_sentence_length": style_vector.get("pacing", 0.5) * 50,  # 映射到合理范围
            "sentence_count": content.count("。") + content.count("！") + content.count("？"),
        }

        self.score_repo.upsert(
            novel_id=novel_id,
            chapter_number=chapter_number,
            adjective_density=metrics["adjective_density"],
            avg_sentence_length=metrics["avg_sentence_length"],
            sentence_count=metrics["sentence_count"],
            # 无基准时存 0.0（NOT NULL 约束），业务层通过 fingerprint 是否存在来区分
            similarity_score=similarity if similarity is not None else 0.0,
        )

        drift_alert = self._check_drift_alert(novel_id)

        logger.debug(
            "LLM 文风评分完成 novel=%s ch=%d similarity=%s drift=%s",
            novel_id, chapter_number, similarity, drift_alert
        )

        return {
            "chapter_number": chapter_number,
            "style_vector": style_vector,
            "similarity_score": similarity,
            "drift_alert": drift_alert,
            "mode": "llm",
        }

    def _get_or_init_baseline(self, novel_id: str) -> Optional[dict]:
        """获取或初始化基准风格"""
        if novel_id in self._baseline_cache:
            return self._baseline_cache[novel_id]

        # 从数据库加载历史评分，计算基准
        scores = self.score_repo.list_by_novel(novel_id, limit=10)
        if len(scores) >= 5:
            # 有足够数据，计算简单基准
            style_vectors = []
            for s in scores[:5]:
                vec = {
                    "description_depth": s.get("adjective_density", 0.5),
                    "pacing": (s.get("avg_sentence_length", 25) / 50),  # 反向映射
                }
                style_vectors.append(vec)

            baseline = self.llm_voice_service._compute_simple_baseline(style_vectors)
            self._baseline_cache[novel_id] = baseline
            return baseline

        return None

    async def _update_baseline(self, novel_id: str) -> None:
        """更新基准风格（每 5 章调用一次）"""
        if not self.llm_voice_service:
            return

        scores = self.score_repo.list_by_novel(novel_id, limit=10)
        if len(scores) >= 5:
            # 重新计算基准
            style_vectors = []
            for s in scores:
                vec = {
                    "description_depth": s.get("adjective_density", 0.5),
                    "pacing": (s.get("avg_sentence_length", 25) / 50),
                }
                style_vectors.append(vec)

            baseline = await self.llm_voice_service.compute_baseline(novel_id, style_vectors)
            self._baseline_cache[novel_id] = baseline
            logger.info("基准风格已更新 novel=%s", novel_id)

    def get_drift_report(self, novel_id: str) -> dict:
        """获取漂移报告（全量评分 + 告警状态）。"""
        scores = self.score_repo.list_by_novel(novel_id)
        drift_alert = self._check_drift_alert(novel_id)

        return {
            "novel_id": novel_id,
            "scores": scores,
            "drift_alert": drift_alert,
            "alert_threshold": DRIFT_ALERT_THRESHOLD,
            "alert_consecutive": DRIFT_ALERT_CONSECUTIVE,
            "mode": "llm" if self.use_llm_mode else "statistics",
        }

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_metrics(text: str) -> dict:
        """从章节文本提取与指纹相同维度的统计特征。"""
        if not text:
            return {"adjective_density": 0.0, "avg_sentence_length": 0.0, "sentence_count": 0}

        adj_count = sum(1 for ch in text if ch in _COMMON_ADJECTIVES)
        total_chars = len(text)
        adj_density = adj_count / total_chars if total_chars else 0.0

        sentences = re.split(r"[。！？]", text)
        sentences = [s.strip() for s in sentences if s.strip()]
        sentence_count = len(sentences)
        avg_len = sum(len(s) for s in sentences) / sentence_count if sentence_count else 0.0

        return {
            "adjective_density": round(adj_density, 4),
            "avg_sentence_length": round(avg_len, 2),
            "sentence_count": sentence_count,
        }

    @staticmethod
    def _cosine_similarity(chapter_metrics: dict, fingerprint: dict) -> float:
        """用二维向量近似计算相似度（形容词密度 + 平均句长归一化）。

        归一化方式：以指纹值为参照，计算相对差异后映射到 [0,1]。
        """
        def _relative_closeness(a: float, b: float) -> float:
            """返回 a 与 b 的接近程度 (0~1)，b 为参照基准。"""
            if b == 0:
                return 1.0 if a == 0 else 0.0
            diff = abs(a - b) / b
            return max(0.0, 1.0 - diff)

        adj_sim = _relative_closeness(
            chapter_metrics["adjective_density"],
            fingerprint["adjective_density"],
        )
        len_sim = _relative_closeness(
            chapter_metrics["avg_sentence_length"],
            fingerprint["avg_sentence_length"],
        )
        # 加权平均：两个维度各 50%
        return round((adj_sim + len_sim) / 2, 4)

    def _check_drift_alert(self, novel_id: str) -> bool:
        """检查最近 N 章是否连续低于阈值。

        跳过 similarity_score 为 None 的章节（无指纹基准时不告警）。
        """
        scores = self.score_repo.list_by_novel(novel_id, limit=DRIFT_ALERT_CONSECUTIVE * 2)
        # 过滤掉 None 值（无指纹基准的章节）
        valid_scores = [s for s in scores if s.get("similarity_score") is not None]

        if len(valid_scores) < DRIFT_ALERT_CONSECUTIVE:
            return False

        recent = valid_scores[-DRIFT_ALERT_CONSECUTIVE:]
        return all(s["similarity_score"] < DRIFT_ALERT_THRESHOLD for s in recent)
