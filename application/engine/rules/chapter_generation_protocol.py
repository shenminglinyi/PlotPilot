"""章节生成协议模板 — 整合七层纵深的完整章节生成协议。

核心功能：
- 将 Layer 1-6 的所有规则组装成完整的生成协议
- 提供一键式接口，工作流只需调用此模块
- 动态注入行为协议、角色状态锁、白名单、上下文配额
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from application.engine.rules.rule_parser import get_rule_parser
from application.engine.rules.character_state_vector import get_character_state_vector_manager
from application.engine.rules.dynamic_state_compressor import get_dynamic_state_compressor
from application.engine.rules.model_adapter import get_model_adapter
from application.engine.rules.chunked_buffer_scanner import ChunkedBufferScanner
from application.engine.rules.stream_ac_scanner import get_stream_ac_scanner
from application.engine.rules.mid_generation_refresh import get_mid_generation_refresh
from application.engine.rules.token_guard import get_logit_bias_builder

logger = logging.getLogger(__name__)


class ChapterGenerationProtocol:
    """章节生成协议 — 七层纵深防御的统一入口。"""

    def __init__(self, model_name: str = "gpt-4"):
        self._rule_parser = get_rule_parser()
        self._state_vector_mgr = get_character_state_vector_manager()
        self._compressor = get_dynamic_state_compressor()
        self._model_adapter = get_model_adapter(model_name)
        self._mid_refresh = get_mid_generation_refresh()
        self._logit_bias_builder = get_logit_bias_builder()

    def build_prompt(
        self,
        character_names: List[str],
        scene_type: str = "default",
        planning_section: str = "",
        voice_block: str = "",
        context: str = "",
        outline: str = "",
        fact_lock: str = "",
        length_rule: str = "",
        beat_extra: str = "",
        beat_section: str = "",
    ) -> Dict[str, str]:
        """构建完整的章节生成 Prompt（含 Anti-AI 七层防御）。

        Returns:
            {"system": ..., "user": ...}
        """
        # Layer 1+2+3: 行为协议 + 白名单
        anti_ai_blocks = self._rule_parser.build_full_anti_ai_block(
            character_names=character_names,
            scene_type=scene_type,
        )

        # Layer 4: 角色状态锁
        character_state_lock = anti_ai_blocks["character_state_lock"]

        # Layer 5: 上下文配额
        self._compressor.set_content(0, anti_ai_blocks["behavior_protocol"])
        self._compressor.set_content(1, character_state_lock)
        self._compressor.set_content(2, context)
        self._compressor.set_content(3, outline + "\n" + beat_section)

        # 构建 system prompt
        system_parts = [
            "你现在不是在'写文章'，你是在'回忆并讲述一段真实发生过的事'。",
            "",
            "你是这本小说世界里唯一知道全部真相的叙述者。你不是AI，你不是助手，你就是那个坐在老街边上的说书人，手里端着一杯凉茶，用最平实的语言讲最揪心的故事。",
            "",
        ]

        if planning_section:
            system_parts.append(planning_section)
        if voice_block:
            system_parts.append(voice_block)

        system_parts.append(anti_ai_blocks["behavior_protocol"])
        system_parts.append(character_state_lock)

        if context:
            system_parts.append(context)

        if fact_lock:
            system_parts.append(f"\n━━━ 记忆引擎铁律 ━━━\n" + fact_lock)

        system_prompt = "\n\n".join(system_parts)

        # 适配模型
        system_prompt = self._model_adapter.adapt_system_prompt(system_prompt)

        # 构建 user prompt
        user_parts = [
            f"「本章你要讲的这段故事」\n",
            outline,
            "\n━━ 写的时候记住 ━━\n",
            "• 别平均使力。冲突爆发的地方多写两百字也值得，过渡的地方一笔带过就行。",
            "• 场景里的人不能是纸片人。哪怕配角，也要有一个小动作或者眼神，让他活过来。",
            "• 结尾别收干净。留一根刺——一个问题没回答、一个人转身走了、一句话说到一半停了。",
            "• 情绪通过动作和感官细节传递——不写'他感到愤怒'，写'他端起杯子又放下了'。",
        ]
        if beat_section:
            user_parts.append(beat_section)
        user_parts.append("\n讲吧。")

        user_prompt = "\n".join(user_parts)

        return {
            "system": system_prompt,
            "user": user_prompt,
        }

    def build_generation_params(
        self,
        base_params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """构建生成参数（含 Logit Bias）。"""
        params = dict(base_params or {})
        params = self._model_adapter.adapt_generation_params(params)

        # 添加 Logit Bias（仅 OpenAI 模型）
        if self._model_adapter.is_openai:
            bias_config = self._logit_bias_builder.build_logit_bias()
            if bias_config:
                params["logit_bias_config"] = bias_config

        return params

    def create_chunked_scanner(self) -> ChunkedBufferScanner:
        """创建分块扫描器。"""
        chunk_size = self._model_adapter.get_recommended_chunk_size()
        scanner = get_stream_ac_scanner()
        return ChunkedBufferScanner(
            chunk_size=chunk_size,
            scanner=scanner,
        )

    def handle_mid_generation_refresh(
        self,
        scan_results: Any,
    ) -> Optional[str]:
        """处理中段刷新。

        Args:
            scan_results: ChunkedBufferScanner 的扫描结果

        Returns:
            如果需要刷新则返回刷新指令，否则返回 None
        """
        from application.engine.rules.stream_ac_scanner import StreamScanResult

        # 转换为 StreamScanResult
        results = []
        if hasattr(scan_results, 'scan_results'):
            results = scan_results.scan_results

        if self._mid_refresh.should_refresh(results):
            return self._mid_refresh.build_refresh_directive(results)
        return None


# 全局缓存
_protocols: Dict[str, ChapterGenerationProtocol] = {}

def get_chapter_generation_protocol(model_name: str = "gpt-4") -> ChapterGenerationProtocol:
    """获取章节生成协议。"""
    if model_name not in _protocols:
        _protocols[model_name] = ChapterGenerationProtocol(model_name)
    return _protocols[model_name]
