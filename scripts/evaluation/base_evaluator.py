"""基础评测框架 - 使用项目现有服务

通过依赖注入和现有服务层进行评测，不重新实现LLM调用。
"""

import asyncio
import json
import os
import sys
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
import logging

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


@dataclass
class EvaluationMetric:
    """评测指标"""
    name: str
    score: float  # 0-10 分
    weight: float = 1.0
    details: str = ""
    passed: bool = True

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class EvaluationResult:
    """单次评测结果"""
    test_name: str
    success: bool
    metrics: List[EvaluationMetric] = field(default_factory=list)
    input_data: Dict[str, Any] = field(default_factory=dict)
    output_data: Any = None
    error: Optional[str] = None
    duration_seconds: float = 0.0
    token_usage: Dict[str, int] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    @property
    def weighted_score(self) -> float:
        """计算加权总分"""
        if not self.metrics:
            return 0.0
        total_weight = sum(m.weight for m in self.metrics)
        if total_weight == 0:
            return 0.0
        return sum(m.score * m.weight for m in self.metrics) / total_weight

    @property
    def passed_count(self) -> int:
        """通过的指标数"""
        return sum(1 for m in self.metrics if m.passed)

    @property
    def total_count(self) -> int:
        """总指标数"""
        return len(self.metrics)

    def to_dict(self) -> Dict:
        return {
            "test_name": self.test_name,
            "success": self.success,
            "weighted_score": self.weighted_score,
            "passed_count": self.passed_count,
            "total_count": self.total_count,
            "metrics": [m.to_dict() for m in self.metrics],
            "input_data": self.input_data,
            "output_data": str(self.output_data)[:500] if self.output_data else None,
            "error": self.error,
            "duration_seconds": self.duration_seconds,
            "token_usage": self.token_usage,
            "timestamp": self.timestamp,
        }


@dataclass
class EvaluationReport:
    """评测报告"""
    evaluator_name: str
    total_tests: int
    passed_tests: int
    failed_tests: int
    average_score: float
    results: List[EvaluationResult] = field(default_factory=list)
    summary: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict:
        return {
            "evaluator_name": self.evaluator_name,
            "total_tests": self.total_tests,
            "passed_tests": self.passed_tests,
            "failed_tests": self.failed_tests,
            "average_score": self.average_score,
            "results": [r.to_dict() for r in self.results],
            "summary": self.summary,
            "timestamp": self.timestamp,
        }

    def save(self, path: Path):
        """保存报告到文件"""
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)
        logger.info(f"报告已保存到: {path}")


def create_metric(
    name: str,
    score: float,
    weight: float = 1.0,
    details: str = "",
    threshold: float = 6.0,
) -> EvaluationMetric:
    """创建评测指标的便捷函数"""
    return EvaluationMetric(
        name=name,
        score=score,
        weight=weight,
        details=details,
        passed=score >= threshold,
    )


class BaseEvaluator(ABC):
    """基础评测器 - 使用项目现有服务"""

    def __init__(self):
        self.results: List[EvaluationResult] = []
        self._services = {}

    @property
    @abstractmethod
    def name(self) -> str:
        """评测器名称"""
        pass

    @abstractmethod
    async def run_single_test(self, test_case: Dict[str, Any]) -> EvaluationResult:
        """运行单个测试用例"""
        pass

    @abstractmethod
    def get_test_cases(self) -> List[Dict[str, Any]]:
        """获取测试用例"""
        pass

    def _get_service(self, service_name: str):
        """获取服务实例（延迟加载）"""
        if service_name not in self._services:
            self._services[service_name] = self._create_service(service_name)
        return self._services[service_name]

    def _create_service(self, service_name: str):
        """创建服务实例"""
        from interfaces.api.dependencies import (
            get_novel_repository,
            get_chapter_repository,
            get_bible_repository,
            get_bible_service,
            get_chapter_service,
            get_novel_service,
        )
        from application.blueprint.services.continuous_planning_service import ContinuousPlanningService
        from application.blueprint.services.beat_sheet_service import BeatSheetService
        from application.workflows.auto_novel_generation_workflow import AutoNovelGenerationWorkflow
        from infrastructure.persistence.database.story_node_repository import StoryNodeRepository
        from infrastructure.persistence.database.chapter_element_repository import ChapterElementRepository
        from infrastructure.persistence.database.sqlite_chapter_repository import SqliteChapterRepository
        from infrastructure.ai.providers.anthropic_provider import AnthropicProvider
        from infrastructure.ai.config.settings import Settings
        from infrastructure.persistence.database.connection import get_database
        from application.paths import get_db_path

        if service_name == "llm":
            api_key = os.getenv("ANTHROPIC_API_KEY") or os.getenv("ANTHROPIC_AUTH_TOKEN")
            if not api_key:
                raise ValueError("请设置 ANTHROPIC_API_KEY 环境变量")
            base_url = os.getenv("ANTHROPIC_BASE_URL")
            settings = Settings(api_key=api_key.strip(), base_url=base_url.strip() if base_url else None)
            return AnthropicProvider(settings)

        elif service_name == "novel_repository":
            return get_novel_repository()

        elif service_name == "chapter_repository":
            return get_chapter_repository()

        elif service_name == "bible_repository":
            return get_bible_repository()

        elif service_name == "bible_service":
            return get_bible_service()

        elif service_name == "chapter_service":
            return get_chapter_service()

        elif service_name == "novel_service":
            return get_novel_service()

        elif service_name == "continuous_planning":
            db_path = get_db_path()
            llm = self._get_service("llm")
            return ContinuousPlanningService(
                StoryNodeRepository(db_path),
                ChapterElementRepository(db_path),
                llm,
                self._get_service("bible_service"),
                chapter_repository=SqliteChapterRepository(get_database()),
                novel_repository=self._get_service("novel_repository"),
            )

        elif service_name == "beat_sheet":
            from interfaces.api.dependencies import get_beat_sheet_service
            return get_beat_sheet_service()

        elif service_name == "auto_workflow":
            from interfaces.api.dependencies import get_auto_workflow
            return get_auto_workflow()

        elif service_name == "story_node_repository":
            return StoryNodeRepository(get_db_path())

        else:
            raise ValueError(f"未知的服务: {service_name}")

    async def run_all_tests(self, test_cases: Optional[List[Dict[str, Any]]] = None) -> EvaluationReport:
        """运行所有测试"""
        if test_cases is None:
            test_cases = self.get_test_cases()

        logger.info(f"\n{'='*60}")
        logger.info(f"开始评测: {self.name}")
        logger.info(f"测试用例数: {len(test_cases)}")
        logger.info(f"{'='*60}\n")

        self.results = []
        for i, test_case in enumerate(test_cases, 1):
            logger.info(f"\n--- 测试 {i}/{len(test_cases)}: {test_case.get('name', 'unnamed')} ---")

            try:
                result = await self.run_single_test(test_case)
                self.results.append(result)

                status = "✓ 通过" if result.success else "✗ 失败"
                logger.info(f"结果: {status} (得分: {result.weighted_score:.2f})")

            except Exception as e:
                logger.error(f"测试异常: {e}", exc_info=True)
                error_result = EvaluationResult(
                    test_name=test_case.get('name', 'unnamed'),
                    success=False,
                    error=str(e),
                )
                self.results.append(error_result)

        # 生成报告
        passed = sum(1 for r in self.results if r.success)
        failed = len(self.results) - passed
        avg_score = sum(r.weighted_score for r in self.results) / len(self.results) if self.results else 0

        report = EvaluationReport(
            evaluator_name=self.name,
            total_tests=len(self.results),
            passed_tests=passed,
            failed_tests=failed,
            average_score=avg_score,
            results=self.results,
            summary=self.generate_summary(),
        )

        logger.info(f"\n{'='*60}")
        logger.info(f"评测完成: {self.name}")
        logger.info(f"通过: {passed}/{len(self.results)}, 平均分: {avg_score:.2f}")
        logger.info(f"{'='*60}\n")

        return report

    def generate_summary(self) -> Dict[str, Any]:
        """生成评测摘要"""
        if not self.results:
            return {}

        metric_scores = {}
        for result in self.results:
            for metric in result.metrics:
                if metric.name not in metric_scores:
                    metric_scores[metric.name] = []
                metric_scores[metric.name].append(metric.score)

        return {
            "average_scores_by_metric": {
                name: sum(scores) / len(scores)
                for name, scores in metric_scores.items()
            },
        }

    def save_results(self, output_dir: Path) -> Path:
        """保存评测结果"""
        output_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = output_dir / f"{self.name}_{timestamp}.json"

        report = EvaluationReport(
            evaluator_name=self.name,
            total_tests=len(self.results),
            passed_tests=sum(1 for r in self.results if r.success),
            failed_tests=sum(1 for r in self.results if not r.success),
            average_score=sum(r.weighted_score for r in self.results) / len(self.results) if self.results else 0,
            results=self.results,
            summary=self.generate_summary(),
        )
        report.save(output_path)
        return output_path
