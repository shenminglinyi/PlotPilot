"""宏观诊断服务 - 自动扫描 + 结果存储"""
import json
import logging
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
from uuid import uuid4

from application.audit.dtos.macro_refactor_dto import LogicBreakpoint
from application.audit.services.macro_refactor_scanner import MacroRefactorScanner
from infrastructure.persistence.database.connection import DatabaseConnection

logger = logging.getLogger(__name__)

# 约 6 万字触发一次（5~10 万字取中值，与全托管锚点配合）
MACRO_DIAGNOSIS_WORD_INTERVAL = 60_000


def build_silent_context_patch(
    breakpoints: List[LogicBreakpoint],
    trait: str,
) -> str:
    """由断点生成「系统叙事校准」短指令，注入生成 Context 头部；对用户透明、非交互。

    ★ V2 升级：区分 OOC / Breakout / Scar Triggered

    - OOC 断点：注入"强化人设"指令（与原逻辑相同）
    - Breakout 断点：不注入校准，反而注入"保持张力"指令
    - Scar Triggered 断点：注入"延续情绪"指令
    """
    if not breakpoints:
        return ""

    from domain.novel.value_objects.character_state import BreakpointType

    # 分类断点
    ooc_breakpoints = [bp for bp in breakpoints if bp.breakpoint_type == BreakpointType.OOC]
    breakout_breakpoints = [bp for bp in breakpoints if bp.breakpoint_type == BreakpointType.CHARACTER_BREAKOUT]
    scar_breakpoints = [bp for bp in breakpoints if bp.breakpoint_type == BreakpointType.SCAR_TRIGGERED]

    patches = []

    # 1. OOC 断点：强化人设
    if ooc_breakpoints:
        reasons: List[str] = []
        tags_set: set = set()
        for bp in ooc_breakpoints[:8]:
            r = (bp.reason or "").strip()
            if r:
                reasons.append(r)
            for t in bp.tags or []:
                if t:
                    tags_set.add(str(t))
        if reasons:
            tags_str = "、".join(sorted(tags_set)[:8]) if tags_set else (trait or "预设人设")
            reason_part = "；".join(reasons[:3])
            patches.append(
                "【系统叙事校准】注意：" + reason_part
                + "。后续生成须强化「" + tags_str
                + "」所要求的行为倾向，避免继续偏离预设标签。"
            )

    # 2. Breakout 断点：保持张力，不拉回
    for bp in breakout_breakpoints[:3]:
        if bp.breakout_reason:
            patches.append(
                f"【人物突破时刻】{bp.breakout_reason}——这是高光时刻，"
                f"保持情绪张力，不要强行拉回原人设。角色的改变是成长的证明。"
            )

    # 3. Scar Triggered 断点：延续情绪
    for bp in scar_breakpoints[:3]:
        if bp.breakout_reason:
            patches.append(
                f"【伤疤触发】{bp.breakout_reason}——"
                f"此行为是角色伤疤的应激反应，应延续情绪强度，不要立即恢复冷静。"
            )

    return "\n".join(patches)


class MacroDiagnosisResult:
    """宏观诊断结果"""
    
    def __init__(
        self,
        id: str,
        novel_id: str,
        trigger_reason: str,
        trait: str,
        conflict_tags: Optional[List[str]],
        breakpoints: List[LogicBreakpoint],
        status: str = "completed",
        error_message: Optional[str] = None,
        created_at: Optional[datetime] = None
    ):
        self.id = id
        self.novel_id = novel_id
        self.trigger_reason = trigger_reason
        self.trait = trait
        self.conflict_tags = conflict_tags or []
        self.breakpoints = breakpoints
        self.status = status
        self.error_message = error_message
        self.created_at = created_at or datetime.now(timezone.utc)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "novel_id": self.novel_id,
            "trigger_reason": self.trigger_reason,
            "trait": self.trait,
            "conflict_tags": self.conflict_tags,
            "breakpoints": [
                {
                    "event_id": bp.event_id,
                    "chapter": bp.chapter,
                    "reason": bp.reason,
                    "tags": bp.tags
                }
                for bp in self.breakpoints
            ],
            "breakpoint_count": len(self.breakpoints),
            "status": self.status,
            "error_message": self.error_message,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }


class MacroDiagnosisService:
    """宏观诊断服务 - 自动扫描 + 结果存储
    
    职责：
    1. 执行全人设扫描（使用内置规则）
    2. 存储诊断结果到数据库
    3. 提供查询接口获取最新结果
    """
    
    # 默认扫描的人设标签（从内置规则中选取）
    DEFAULT_SCAN_TRAITS = ["冷酷", "理性", "谨慎", "温和"]
    
    def __init__(
        self,
        db: DatabaseConnection,
        scanner: MacroRefactorScanner
    ):
        self.db = db
        self.scanner = scanner
    
    def run_full_diagnosis(
        self,
        novel_id: str,
        trigger_reason: str,
        traits: Optional[List[str]] = None,
        total_words_at_run: int = 0,
    ) -> MacroDiagnosisResult:
        """执行完整诊断（扫描所有内置人设标签）
        
        Args:
            novel_id: 小说 ID
            trigger_reason: 触发原因
            traits: 要扫描的人设标签列表（可选，默认扫描全部内置规则）
        
        Returns:
            MacroDiagnosisResult: 诊断结果
        """
        diagnosis_id = str(uuid4())
        scan_traits = traits or self.DEFAULT_SCAN_TRAITS
        all_breakpoints: List[LogicBreakpoint] = []
        
        try:
            # 对每个人设标签执行扫描
            for trait in scan_traits:
                breakpoints = self.scanner.scan_breakpoints(
                    novel_id=novel_id,
                    trait=trait,
                    conflict_tags=None  # 使用内置规则
                )
                all_breakpoints.extend(breakpoints)
            
            # 创建结果对象
            result = MacroDiagnosisResult(
                id=diagnosis_id,
                novel_id=novel_id,
                trigger_reason=trigger_reason,
                trait=",".join(scan_traits),  # 多标签合并
                conflict_tags=[],
                breakpoints=all_breakpoints,
                status="completed"
            )
            
            # 存储到数据库（含静默 context_patch 与字数锚点）
            self._save_result(result, total_words_at_run=total_words_at_run)
            
            logger.info(
                f"[MacroDiagnosis] 完成诊断 novel={novel_id} "
                f"trigger={trigger_reason} traits={scan_traits} "
                f"breakpoints={len(all_breakpoints)}"
            )
            
            return result
            
        except Exception as e:
            logger.error(f"[MacroDiagnosis] 诊断失败 novel={novel_id}: {e}", exc_info=True)
            
            # 存储失败结果
            result = MacroDiagnosisResult(
                id=diagnosis_id,
                novel_id=novel_id,
                trigger_reason=trigger_reason,
                trait=",".join(scan_traits),
                conflict_tags=[],
                breakpoints=[],
                status="failed",
                error_message=str(e)
            )
            self._save_result(result, total_words_at_run=total_words_at_run)
            
            return result
    
    def run_single_trait_diagnosis(
        self,
        novel_id: str,
        trait: str,
        conflict_tags: Optional[List[str]] = None,
        trigger_reason: str = "manual"
    ) -> MacroDiagnosisResult:
        """执行单人设诊断
        
        Args:
            novel_id: 小说 ID
            trait: 目标人设标签
            conflict_tags: 自定义冲突标签（可选）
            trigger_reason: 触发原因
        
        Returns:
            MacroDiagnosisResult: 诊断结果
        """
        diagnosis_id = str(uuid4())
        
        try:
            breakpoints = self.scanner.scan_breakpoints(
                novel_id=novel_id,
                trait=trait,
                conflict_tags=conflict_tags
            )
            
            result = MacroDiagnosisResult(
                id=diagnosis_id,
                novel_id=novel_id,
                trigger_reason=trigger_reason,
                trait=trait,
                conflict_tags=conflict_tags or [],
                breakpoints=breakpoints,
                status="completed"
            )
            
            self._save_result(result, total_words_at_run=0)
            
            logger.info(
                f"[MacroDiagnosis] 完成单人设诊断 novel={novel_id} "
                f"trait={trait} breakpoints={len(breakpoints)}"
            )
            
            return result
            
        except Exception as e:
            logger.error(f"[MacroDiagnosis] 单人设诊断失败 novel={novel_id}: {e}", exc_info=True)
            
            result = MacroDiagnosisResult(
                id=diagnosis_id,
                novel_id=novel_id,
                trigger_reason=trigger_reason,
                trait=trait,
                conflict_tags=conflict_tags or [],
                breakpoints=[],
                status="failed",
                error_message=str(e)
            )
            self._save_result(result, total_words_at_run=0)
            
            return result
    
    def get_latest_result(self, novel_id: str) -> Optional[Dict[str, Any]]:
        """获取最新的诊断结果
        
        Args:
            novel_id: 小说 ID
        
        Returns:
            最新诊断结果字典，无结果返回 None
        """
        sql = """
            SELECT id, novel_id, trigger_reason, trait, conflict_tags,
                   breakpoints, breakpoint_count, status, resolved, resolved_at, resolved_by,
                   error_message, created_at
            FROM macro_diagnosis_results
            WHERE novel_id = ?
            ORDER BY created_at DESC
            LIMIT 1
        """
        row = self.db.fetch_one(sql, (novel_id,))
        
        if not row:
            return None
        
        return {
            "id": row["id"],
            "novel_id": row["novel_id"],
            "trigger_reason": row["trigger_reason"],
            "trait": row["trait"],
            "conflict_tags": json.loads(row["conflict_tags"]) if row["conflict_tags"] else [],
            "breakpoints": json.loads(row["breakpoints"]) if row["breakpoints"] else [],
            "breakpoint_count": row["breakpoint_count"],
            "status": row["status"],
            "resolved": bool(row["resolved"]),
            "resolved_at": row["resolved_at"],
            "resolved_by": row["resolved_by"],
            "error_message": row["error_message"],
            "created_at": row["created_at"]
        }
    
    def list_results(
        self,
        novel_id: str,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """获取诊断历史列表
        
        Args:
            novel_id: 小说 ID
            limit: 最大返回数量
        
        Returns:
            诊断结果列表
        """
        sql = """
            SELECT id, novel_id, trigger_reason, trait, conflict_tags,
                   breakpoints, breakpoint_count, status, resolved, resolved_at, resolved_by,
                   error_message, created_at
            FROM macro_diagnosis_results
            WHERE novel_id = ?
            ORDER BY created_at DESC
            LIMIT ?
        """
        rows = self.db.fetch_all(sql, (novel_id, limit))
        
        return [
            {
                "id": row["id"],
                "novel_id": row["novel_id"],
                "trigger_reason": row["trigger_reason"],
                "trait": row["trait"],
                "conflict_tags": json.loads(row["conflict_tags"]) if row["conflict_tags"] else [],
                "breakpoints": json.loads(row["breakpoints"]) if row["breakpoints"] else [],
                "breakpoint_count": row["breakpoint_count"],
                "status": row["status"],
                "resolved": bool(row["resolved"]),
                "resolved_at": row["resolved_at"],
                "resolved_by": row["resolved_by"],
                "error_message": row["error_message"],
                "created_at": row["created_at"]
            }
            for row in rows
        ]
    
    def mark_resolved(
        self,
        novel_id: str,
        diagnosis_id: str,
        resolved_by: str = "manual"
    ) -> bool:
        """标记诊断结果为已解决
        
        已解决的诊断结果不会再注入到提示词中。
        
        Args:
            novel_id: 小说 ID
            diagnosis_id: 诊断结果 ID
            resolved_by: 解决方式（'manual' 或 'auto'）
        
        Returns:
            是否成功标记
        """
        try:
            now = datetime.now(timezone.utc).isoformat()
            sql = """
                UPDATE macro_diagnosis_results
                SET resolved = 1, resolved_at = ?, resolved_by = ?
                WHERE id = ? AND novel_id = ?
            """
            self.db.execute(sql, (now, resolved_by, diagnosis_id, novel_id))
            self.db.get_connection().commit()
            
            logger.info(f"[MacroDiagnosis] 标记已解决: diagnosis_id={diagnosis_id}")
            return True
            
        except Exception as e:
            logger.error(f"[MacroDiagnosis] 标记已解决失败: {e}")
            return False
    
    def get_latest_unresolved_result(self, novel_id: str) -> Optional[Dict[str, Any]]:
        """获取最新的未解决诊断结果
        
        用于提示词注入，只返回未解决的诊断结果。
        
        Args:
            novel_id: 小说 ID
        
        Returns:
            最新未解决诊断结果，无结果返回 None
        """
        sql = """
            SELECT id, novel_id, trigger_reason, trait, conflict_tags,
                   breakpoints, breakpoint_count, status, resolved, resolved_at, resolved_by,
                   error_message, created_at
            FROM macro_diagnosis_results
            WHERE novel_id = ? AND resolved = 0 AND status = 'completed'
            ORDER BY created_at DESC
            LIMIT 1
        """
        row = self.db.fetch_one(sql, (novel_id,))
        
        if not row:
            return None
        
        return {
            "id": row["id"],
            "novel_id": row["novel_id"],
            "trigger_reason": row["trigger_reason"],
            "trait": row["trait"],
            "conflict_tags": json.loads(row["conflict_tags"]) if row["conflict_tags"] else [],
            "breakpoints": json.loads(row["breakpoints"]) if row["breakpoints"] else [],
            "breakpoint_count": row["breakpoint_count"],
            "status": row["status"],
            "resolved": bool(row["resolved"]),
            "resolved_at": row["resolved_at"],
            "resolved_by": row["resolved_by"],
            "error_message": row["error_message"],
            "created_at": row["created_at"]
        }
    
    def _save_result(
        self,
        result: MacroDiagnosisResult,
        total_words_at_run: int = 0,
    ) -> None:
        """保存诊断结果到数据库（含静默注入用 context_patch）。"""
        # ★ V2: 保存完整的断点信息（含 breakpoint_type, scar_id, breakout_reason）
        breakpoints_json = json.dumps(
            [bp.to_dict() for bp in result.breakpoints],
            ensure_ascii=False
        )
        conflict_tags_json = json.dumps(result.conflict_tags, ensure_ascii=False)
        context_patch = ""
        if result.status == "completed" and result.breakpoints:
            context_patch = build_silent_context_patch(result.breakpoints, result.trait)
        
        sql = """
            INSERT INTO macro_diagnosis_results
            (id, novel_id, trigger_reason, trait, conflict_tags, breakpoints, breakpoint_count,
             status, error_message, context_patch, total_words_at_run)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        self.db.execute(sql, (
            result.id,
            result.novel_id,
            result.trigger_reason,
            result.trait,
            conflict_tags_json,
            breakpoints_json,
            len(result.breakpoints),
            result.status,
            result.error_message,
            context_patch or None,
            int(max(0, total_words_at_run)),
        ))
        self.db.get_connection().commit()
