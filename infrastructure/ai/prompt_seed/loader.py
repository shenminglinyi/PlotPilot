"""从 prompt_packages 目录加载与旧版 JSON 合并逻辑。"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Tuple

logger = logging.getLogger(__name__)

_AI_DIR = Path(__file__).resolve().parent.parent
PACKAGES_ROOT = _AI_DIR / "prompt_packages"
NODES_DIR = PACKAGES_ROOT / "nodes"
BUNDLE_META_FILE = PACKAGES_ROOT / "bundle_meta.yaml"
_LEGACY_PROMPTS_DIR = _AI_DIR / "prompts"
_LEGACY_GLOB = "prompts_*.json"


def _try_yaml_load(path: Path) -> Dict[str, Any]:
    try:
        import yaml  # type: ignore
    except ImportError as e:
        logger.warning("prompt_seed: PyYAML 不可用，使用受限 YAML 解析器 path=%s", path)
        return _minimal_yaml_load(path.read_text(encoding="utf-8"))
    text = path.read_text(encoding="utf-8")
    data = yaml.safe_load(text)
    return data if isinstance(data, dict) else {}


def _minimal_yaml_load(text: str) -> Dict[str, Any]:
    """Parse the limited YAML subset used by prompt package metadata.

    Supported subset:
    - top-level / nested mappings via indentation
    - lists introduced by ``- ``
    - list items that are scalars or inline mappings
    - scalar strings / booleans / integers / floats / null
    """

    raw_lines = text.splitlines()
    lines: list[tuple[int, str]] = []
    for raw in raw_lines:
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        lines.append((indent, raw[indent:]))
    if not lines:
        return {}

    value, index = _parse_yaml_block(lines, 0, lines[0][0])
    if index != len(lines):
        raise RuntimeError("受限 YAML 解析器未消费全部内容")
    return value if isinstance(value, dict) else {}


def _parse_yaml_block(lines: list[tuple[int, str]], index: int, indent: int) -> tuple[Any, int]:
    if index >= len(lines):
        return {}, index
    current_indent, content = lines[index]
    if current_indent != indent:
        raise RuntimeError(f"YAML 缩进不符合预期: expected={indent} actual={current_indent}")
    if content.startswith("- "):
        return _parse_yaml_list(lines, index, indent)
    return _parse_yaml_dict(lines, index, indent)


def _parse_yaml_dict(lines: list[tuple[int, str]], index: int, indent: int) -> tuple[Dict[str, Any], int]:
    result: Dict[str, Any] = {}
    last_key = ""
    while index < len(lines):
        current_indent, content = lines[index]
        if current_indent < indent:
            break
        if current_indent > indent:
            if last_key and isinstance(result.get(last_key), str):
                result[last_key] = f"{result[last_key]} {content.strip()}".strip()
                index += 1
                continue
            raise RuntimeError(f"YAML 字典出现非法缩进: indent={current_indent} expected={indent}")
        if content.startswith("- "):
            break
        if ":" not in content:
            raise RuntimeError(f"YAML 字典项缺少冒号: {content}")
        key, raw_value = content.split(":", 1)
        key = key.strip()
        raw_value = raw_value.strip()
        index += 1
        if not raw_value:
            if index < len(lines) and lines[index][0] > current_indent:
                value, index = _parse_yaml_block(lines, index, lines[index][0])
            elif index < len(lines) and lines[index][0] == current_indent and lines[index][1].startswith("- "):
                value, index = _parse_yaml_list(lines, index, current_indent)
            else:
                value = ""
        else:
            value = _parse_yaml_scalar(raw_value)
        result[key] = value
        last_key = key
    return result, index


def _parse_yaml_list(lines: list[tuple[int, str]], index: int, indent: int) -> tuple[list[Any], int]:
    result: list[Any] = []
    while index < len(lines):
        current_indent, content = lines[index]
        if current_indent < indent:
            break
        if current_indent > indent:
            raise RuntimeError(f"YAML 列表出现非法缩进: indent={current_indent} expected={indent}")
        if not content.startswith("- "):
            break
        item_content = content[2:].strip()
        index += 1
        inline_match = re.match(r"^([A-Za-z0-9_.-]+)\s*:\s*(.*)$", item_content)
        if not item_content:
            if index < len(lines) and lines[index][0] > current_indent:
                item, index = _parse_yaml_block(lines, index, lines[index][0])
            else:
                item = ""
        elif inline_match:
            key = inline_match.group(1)
            raw_value = inline_match.group(2).strip()
            item: Any
            if raw_value:
                item = {key: _parse_yaml_scalar(raw_value)}
            elif index < len(lines) and lines[index][0] > current_indent:
                nested, index = _parse_yaml_block(lines, index, lines[index][0])
                item = {key: nested}
            else:
                item = {key: ""}
            if (
                index < len(lines)
                and lines[index][0] > current_indent
                and isinstance(item, dict)
                and not (len(item) == 1 and isinstance(next(iter(item.values())), (dict, list)))
            ):
                nested, index = _parse_yaml_block(lines, index, lines[index][0])
                if isinstance(nested, dict):
                    item.update(nested)
                else:
                    raise RuntimeError("YAML 列表内联对象后续块必须是字典")
            result.append(item)
        else:
            result.append(_parse_yaml_scalar(item_content))
    return result, index


def _parse_yaml_scalar(raw_value: str) -> Any:
    value = raw_value.strip()
    if not value:
        return ""
    if value in {"true", "True"}:
        return True
    if value in {"false", "False"}:
        return False
    if value in {"null", "Null", "NULL", "~"}:
        return None
    if (value.startswith("'") and value.endswith("'")) or (value.startswith('"') and value.endswith('"')):
        inner = value[1:-1]
        if value.startswith("'"):
            return inner.replace("''", "'")
        return inner.replace('\\"', '"')
    if re.fullmatch(r"-?\d+", value):
        try:
            return int(value)
        except ValueError:
            return value
    if re.fullmatch(r"-?\d+\.\d+", value):
        try:
            return float(value)
        except ValueError:
            return value
    return value


def load_bundle_meta() -> Dict[str, Any]:
    """读取 bundle_meta.yaml；缺失时返回占位。"""
    if not BUNDLE_META_FILE.is_file():
        meta = {
            "version": "0.0.0",
            "name": "PlotPilot 内置",
            "description": "prompt_packages 缺失 bundle_meta.yaml",
            "author": "PlotPilot Team",
            "engine": "jinja2",
        }
        logger.info(
            "prompt_seed: bundle_meta 缺失，使用占位 version=%s name=%s path=%s",
            meta["version"],
            meta["name"],
            BUNDLE_META_FILE,
        )
        return meta
    meta = _try_yaml_load(BUNDLE_META_FILE)
    logger.info(
        "prompt_seed: bundle_meta loaded version=%s name=%s author=%s path=%s",
        meta.get("version", ""),
        meta.get("name", ""),
        meta.get("author", ""),
        BUNDLE_META_FILE,
    )
    return meta


def load_node_dir(node_dir: Path) -> Dict[str, Any]:
    """加载单个节点目录为与旧种子一致的 dict（含 system / user_template）。"""
    pkg_path = node_dir / "package.yaml"
    if not pkg_path.is_file():
        raise FileNotFoundError(f"缺少 package.yaml: {node_dir}")

    meta = _try_yaml_load(pkg_path)
    node_id = meta.get("id") or node_dir.name

    system_path = node_dir / "system.md"
    user_path = node_dir / "user.md"
    system = system_path.read_text(encoding="utf-8") if system_path.is_file() else ""
    user = user_path.read_text(encoding="utf-8") if user_path.is_file() else ""

    extras_path = node_dir / "extras.json"
    extras: Dict[str, Any] = {}
    if extras_path.is_file():
        extras = json.loads(extras_path.read_text(encoding="utf-8"))
        if not isinstance(extras, dict):
            extras = {}

    record: Dict[str, Any] = {**meta, "id": node_id, "system": system, "user_template": user}
    for k, v in extras.items():
        if k not in record or k.startswith("_"):
            record[k] = v

    vars_list = record.get("variables") or []
    n_vars = len(vars_list) if isinstance(vars_list, list) else 0
    tags = record.get("tags") or []
    tags_repr = ",".join(str(t) for t in tags) if isinstance(tags, list) else str(tags)
    builtin = record.get("builtin", record.get("is_builtin"))
    logger.info(
        "prompt_seed: node dir=%s id=%s name=%s category=%s output_format=%s "
        "source=%s builtin=%s tags=[%s] variables=%d system_chars=%d user_chars=%d extras_keys=%s",
        node_dir.name,
        node_id,
        record.get("name", ""),
        record.get("category", ""),
        record.get("output_format", ""),
        record.get("source", ""),
        builtin,
        tags_repr,
        n_vars,
        len(system),
        len(user),
        sorted(extras.keys()) if extras else [],
    )

    return record


def load_seed_bundle() -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """返回 (合并后的 _meta, prompts 列表)。无节点目录时 prompts 为空。"""
    bundle_meta = load_bundle_meta()
    if not NODES_DIR.is_dir():
        logger.warning("prompt_seed: %s 不存在，种子列表为空", NODES_DIR)
        return bundle_meta, []

    rows: List[Dict[str, Any]] = []
    for child in sorted(NODES_DIR.iterdir(), key=lambda p: p.name):
        if not child.is_dir():
            continue
        if child.name.startswith("."):
            continue
        pkg_path = child / "package.yaml"
        if not pkg_path.is_file():
            logger.warning(
                "prompt_seed: 跳过无效节点目录（缺少 package.yaml）: %s",
                child,
            )
            continue
        try:
            rows.append(load_node_dir(child))
        except Exception as exc:
            logger.error("prompt_seed: 加载提示词包失败 %s: %s", child, exc)
            raise

    rows.sort(key=lambda r: (r.get("sort_order", 10_000), r.get("id", "")))
    logger.info(
        "prompt_seed: bundle loaded nodes=%d ids=%s",
        len(rows),
        [r.get("id", "") for r in rows],
    )
    return bundle_meta, rows


def merge_legacy_json_prompts(prompts_dir: Path | None = None) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """与旧 PromptManager 相同合并规则：defaults 全量 _meta，再 prompts_*.json 覆盖同名 id 并刷新 version。"""
    base = prompts_dir or _LEGACY_PROMPTS_DIR
    all_prompts: Dict[str, Dict[str, Any]] = {}
    merged_meta: Dict[str, Any] = {}

    default_path = base / "prompts_defaults.json"
    if default_path.is_file():
        data = json.loads(default_path.read_text(encoding="utf-8"))
        merged_meta.update(data.get("_meta") or {})
        n_def = 0
        for p in data.get("prompts", []):
            if p.get("id"):
                all_prompts[p["id"]] = p
                n_def += 1
        logger.info(
            "prompt_seed: legacy defaults %s prompts=%d meta_version=%s",
            default_path,
            n_def,
            (data.get("_meta") or {}).get("version", ""),
        )

    if base.is_dir():
        for cat_file in sorted(base.glob(_LEGACY_GLOB)):
            data = json.loads(cat_file.read_text(encoding="utf-8"))
            cat_meta = data.get("_meta", {})
            if cat_meta.get("version"):
                merged_meta["version"] = cat_meta["version"]
            n_cat = 0
            for p in data.get("prompts", []):
                if p.get("id"):
                    all_prompts[p["id"]] = p
                    n_cat += 1
            logger.info(
                "prompt_seed: legacy file %s prompts=%d _meta_version=%s",
                cat_file.name,
                n_cat,
                cat_meta.get("version", ""),
            )

    plist = list(all_prompts.values())
    logger.info(
        "prompt_seed: legacy merge complete total_prompts=%d ids=%s",
        len(plist),
        [p.get("id", "") for p in plist],
    )
    # 与 dict 插入顺序一致（Py3.7+）：先 defaults 顺序，后逐文件覆盖且不改变已有 key 顺序
    return merged_meta, plist
