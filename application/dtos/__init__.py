"""兼容旧导入路径：application.dtos.* -> 新分层 DTO 模块。"""

from importlib import import_module
import sys


_MODULE_ALIASES = {
    "bible_dto": "application.world.dtos.bible_dto",
    "generation_result": "application.engine.dtos.generation_result",
    "ghost_annotation": "application.audit.dtos.ghost_annotation",
    "macro_refactor_dto": "application.audit.dtos.macro_refactor_dto",
    "novel_dto": "application.core.dtos.novel_dto",
    "scene_director_dto": "application.engine.dtos.scene_director_dto",
    "writer_block_dto": "application.workbench.dtos.writer_block_dto",
}


for _alias, _target in _MODULE_ALIASES.items():
    sys.modules[f"{__name__}.{_alias}"] = import_module(_target)
