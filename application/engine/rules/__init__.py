# Anti-AI 规则引擎包
#
# 七层纵深防御体系：
# Layer 1: 正向行为映射 (positive_framing_rules)
# Layer 2: 核心协议 P1-P5 (rule_parser)
# Layer 3: 场景化白名单 (allowlist_manager)
# Layer 4: 角色状态向量 (character_state_vector)
# Layer 5: 上下文配额 (dynamic_state_compressor)
# Layer 6: Token 级拦截 (token_guard, stream_ac_scanner, chunked_buffer_scanner, model_adapter)
# Layer 7: 章后审计 (anti_ai_audit, anti_ai_metrics, anti_ai_learning)

from application.engine.rules.positive_framing_rules import (
    POSITIVE_FRAMING_MAP,
    build_positive_framing_block,
)
from application.engine.rules.allowlist_manager import (
    AllowlistManager,
    AllowlistRule,
    PREDEFINED_ALLOWLIST,
    SCENE_TYPE_LABELS,
    get_allowlist_manager,
)
from application.engine.rules.character_state_vector import (
    VoicePrint,
    NervousHabit,
    ReactionPattern,
    InfoBoundary,
    CharacterStateVector,
    CharacterStateVectorManager,
    get_character_state_vector_manager,
)
from application.engine.rules.rule_parser import (
    RuleParser,
    get_rule_parser,
)
from application.engine.rules.dynamic_state_compressor import (
    DynamicStateCompressor,
    ContextLayer,
    get_dynamic_state_compressor,
)
from application.engine.rules.token_guard import (
    TokenGuard,
    TokenBiasEntry,
    SafeLogitBiasBuilder,
    get_token_guard,
    get_logit_bias_builder,
)
from application.engine.rules.stream_ac_scanner import (
    StreamACScanner,
    StreamScanResult,
    ACNode,
    create_default_scanner,
    get_stream_ac_scanner,
)
from application.engine.rules.chunked_buffer_scanner import (
    ChunkedBufferScanner,
    ChunkResult,
)
from application.engine.rules.model_adapter import (
    ModelAdapter,
    get_model_adapter,
)
from application.engine.rules.mid_generation_refresh import (
    MidGenerationRefresh,
    FinaleEnhancer,
    get_mid_generation_refresh,
    get_finale_enhancer,
)
from application.engine.rules.chapter_generation_protocol import (
    ChapterGenerationProtocol,
    get_chapter_generation_protocol,
)

__all__ = [
    # Layer 1
    "POSITIVE_FRAMING_MAP",
    "build_positive_framing_block",
    # Layer 3
    "AllowlistManager",
    "AllowlistRule",
    "PREDEFINED_ALLOWLIST",
    "SCENE_TYPE_LABELS",
    "get_allowlist_manager",
    # Layer 4
    "VoicePrint",
    "NervousHabit",
    "ReactionPattern",
    "InfoBoundary",
    "CharacterStateVector",
    "CharacterStateVectorManager",
    "get_character_state_vector_manager",
    # Layer 1+2+3
    "RuleParser",
    "get_rule_parser",
    # Layer 5
    "DynamicStateCompressor",
    "ContextLayer",
    "get_dynamic_state_compressor",
    # Layer 6
    "TokenGuard",
    "TokenBiasEntry",
    "SafeLogitBiasBuilder",
    "get_token_guard",
    "get_logit_bias_builder",
    "StreamACScanner",
    "StreamScanResult",
    "ACNode",
    "create_default_scanner",
    "get_stream_ac_scanner",
    "ChunkedBufferScanner",
    "ChunkResult",
    "ModelAdapter",
    "get_model_adapter",
    "MidGenerationRefresh",
    "FinaleEnhancer",
    "get_mid_generation_refresh",
    "get_finale_enhancer",
    # 整合
    "ChapterGenerationProtocol",
    "get_chapter_generation_protocol",
]
