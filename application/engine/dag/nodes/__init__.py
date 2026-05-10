"""DAG 节点实现 — V2 扩展版（36 个节点）

分类：
- Context (5): ctx_blueprint, ctx_foreshadow, ctx_voice, ctx_memory, ctx_debt
- Execution (7): exec_planning, exec_writer, exec_beat, exec_scene, gen_chapter_basic, gen_dialogue, gen_scene
- Validation (10): val_style, val_tension, val_anti_ai, val_foreshadow, val_narrative, val_kg_infer,
                    ext_state, ext_style, ext_narrative_sync, ext_summary
- Gateway (4): gw_circuit, gw_review, gw_condition, gw_retry
- World (4): world_bible_all, world_worldbuilding, world_characters, world_locations
- Review (5): review_character, review_timeline, review_storyline, review_foreshadowing, review_improvement
- Anti-AI (6): anti_ai_behavior, anti_ai_allowlist, anti_ai_char_lock, anti_ai_mid_refresh, anti_ai_audit, anti_ai_finale
- Planning (3): planning_beat_sheet, planning_quick_macro, planning_act

CPMS 联动：
- 所有节点通过 cpms_node_key 关联提示词广场
- exec_writer 通过 cpms_sub_keys 自动注入 Anti-AI 子提示词
- INJECT 模式节点返回片段给下游注入
"""
from application.engine.dag.nodes.context_nodes import *  # noqa: F401 F403
from application.engine.dag.nodes.execution_nodes import *  # noqa: F401 F403
from application.engine.dag.nodes.validation_nodes import *  # noqa: F401 F403
from application.engine.dag.nodes.gateway_nodes import *  # noqa: F401 F403
from application.engine.dag.nodes.world_nodes import *  # noqa: F401 F403
from application.engine.dag.nodes.review_nodes import *  # noqa: F401 F403
from application.engine.dag.nodes.anti_ai_nodes import *  # noqa: F401 F403
from application.engine.dag.nodes.planning_nodes import *  # noqa: F401 F403
from application.engine.dag.nodes.gen_supplement_nodes import *  # noqa: F401 F403
from application.engine.dag.nodes.ext_supplement_nodes import *  # noqa: F401 F403
