from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List


class PatchConflictError(Exception):
    pass


class EvolutionOverrideService:
    def __init__(self, snapshot_repository: Any):
        self.snapshot_repository = snapshot_repository

    def apply_overrides(
        self,
        novel_id: str,
        chapter_number: int,
        patches: List[Dict[str, Any]],
        branch_id: str = "main",
    ) -> Dict[str, Any]:
        snapshot = self.snapshot_repository.get_by_chapter(novel_id, branch_id, chapter_number)
        if snapshot is None:
            raise ValueError("snapshot_not_found")
        try:
            ending = self.apply_patch(snapshot.machine_state.to_dict(), patches)
        except PatchConflictError as exc:
            self.snapshot_repository.mark_blocked(
                snapshot.snapshot_id,
                [{"conflict_type": "PATCH_CONFLICT", "level": "blocking", "message": str(exc)}],
            )
            raise

        merged = list(snapshot.human_override_patches or []) + list(patches or [])
        self.snapshot_repository.update_overrides(snapshot.snapshot_id, merged, ending)
        return self.snapshot_repository.get_by_id(snapshot.snapshot_id).to_dict()

    def apply_patch(self, document: Dict[str, Any], patches: List[Dict[str, Any]]) -> Dict[str, Any]:
        target = deepcopy(document)
        for patch in patches or []:
            op = patch.get("op")
            path = patch.get("path")
            if op not in {"add", "replace", "remove"}:
                raise PatchConflictError(f"unsupported patch op: {op}")
            if not isinstance(path, str) or not path.startswith("/"):
                raise PatchConflictError(f"invalid patch path: {path}")
            parent, key = self._resolve_parent(target, path)
            if isinstance(parent, list):
                idx = self._parse_index(key, len(parent), allow_end=(op == "add"))
                if op == "remove":
                    parent.pop(idx)
                elif op == "replace":
                    parent[idx] = patch.get("value")
                else:
                    parent.insert(idx, patch.get("value"))
            elif isinstance(parent, dict):
                if op in {"replace", "remove"} and key not in parent:
                    raise PatchConflictError(f"patch path missing: {path}")
                if op == "remove":
                    parent.pop(key)
                else:
                    parent[key] = patch.get("value")
            else:
                raise PatchConflictError(f"patch parent is not mutable: {path}")
        return target

    def _resolve_parent(self, document: Any, path: str):
        parts = [self._unescape(p) for p in path.strip("/").split("/") if p != ""]
        if not parts:
            raise PatchConflictError("cannot patch document root")
        cur = document
        for part in parts[:-1]:
            if isinstance(cur, dict) and part in cur:
                cur = cur[part]
            elif isinstance(cur, list):
                cur = cur[self._parse_index(part, len(cur))]
            else:
                raise PatchConflictError(f"patch path missing: {path}")
        return cur, parts[-1]

    @staticmethod
    def _unescape(part: str) -> str:
        return part.replace("~1", "/").replace("~0", "~")

    @staticmethod
    def _parse_index(value: str, length: int, allow_end: bool = False) -> int:
        if allow_end and value == "-":
            return length
        try:
            idx = int(value)
        except ValueError as exc:
            raise PatchConflictError(f"invalid list index: {value}") from exc
        if idx < 0 or idx >= length + (1 if allow_end else 0):
            raise PatchConflictError(f"list index out of range: {value}")
        return idx
