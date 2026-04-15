"""兼容旧导入路径：application.services.* -> 新分层 service 模块。"""

from importlib import import_module
import sys


_MODULE_ALIASES = {
    "ai_generation_service": "application.engine.services.ai_generation_service",
    "bible_location_triple_sync": "application.world.services.bible_location_triple_sync",
    "bible_service": "application.world.services.bible_service",
    "chapter_indexing_service": "application.analyst.services.chapter_indexing_service",
    "chapter_service": "application.core.services.chapter_service",
    "character_indexer": "application.analyst.services.character_indexer",
    "cliche_scanner": "application.audit.services.cliche_scanner",
    "conflict_detection_service": "application.audit.services.conflict_detection_service",
    "context_builder": "application.engine.services.context_builder",
    "hosted_write_service": "application.engine.services.hosted_write_service",
    "indexing_service": "application.analyst.services.indexing_service",
    "macro_merge_engine": "application.audit.services.macro_merge_engine",
    "macro_refactor_proposal_service": "application.audit.services.macro_refactor_proposal_service",
    "macro_refactor_scanner": "application.audit.services.macro_refactor_scanner",
    "mutation_applier": "application.audit.services.mutation_applier",
    "narrative_entity_state_service": "application.analyst.services.narrative_entity_state_service",
    "novel_service": "application.core.services.novel_service",
    "scene_director_service": "application.engine.services.scene_director_service",
    "state_extractor": "application.analyst.services.state_extractor",
    "state_updater": "application.analyst.services.state_updater",
    "style_constraint_builder": "application.engine.services.style_constraint_builder",
    "subtext_matching_service": "application.analyst.services.subtext_matching_service",
    "tension_analyzer": "application.analyst.services.tension_analyzer",
    "trigger_keyword_catalog": "application.engine.services.trigger_keyword_catalog",
    "voice_drift_service": "application.analyst.services.voice_drift_service",
    "voice_fingerprint_service": "application.analyst.services.voice_fingerprint_service",
    "voice_sample_service": "application.analyst.services.voice_sample_service",
}


for _alias, _target in _MODULE_ALIASES.items():
    sys.modules[f"{__name__}.{_alias}"] = import_module(_target)
