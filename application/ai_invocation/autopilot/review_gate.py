"""Autopilot review-gate presentation rules."""
from __future__ import annotations

from typing import Any, Mapping


INVOCATION_WAITING_STATUSES = {
    "awaiting_pre_call_review",
    "awaiting_acceptance",
    "awaiting_commit",
    "generating",
}
INVOCATION_FAILED_STATUSES = {"blocked", "failed", "cancelled"}
PENDING_INVOCATION_STATUSES = INVOCATION_WAITING_STATUSES | INVOCATION_FAILED_STATUSES


def stage_needs_human_review(stage: Any) -> bool:
    return str(stage or "").strip().lower() in {"paused_for_review", "reviewing"}


def review_type_for_operation(operation: str, substep: str = "") -> str:
    op = (operation or "").strip()
    sub = (substep or "").strip()
    if op == "autopilot.macro.plan" or sub == "macro_planning":
        return "macro_plan"
    if op == "autopilot.act.plan" or sub == "act_planning":
        return "act_plan"
    if "audit" in op or sub.startswith("audit_"):
        return "chapter_review"
    if op:
        return "ai_invocation"
    return "manual_review"


def _is_initial_macro_review_context(status: Mapping[str, Any]) -> bool:
    if review_type_for_operation(
        str(status.get("active_invocation_operation") or ""),
        str(status.get("writing_substep") or ""),
    ) != "manual_review":
        return False
    if status.get("macro_structure_ready") is not None:
        return True
    if int(status.get("current_auto_chapters") or 0) != 0:
        return False
    if status.get("current_chapter_number") is not None:
        return False
    try:
        return int(status.get("current_act") or 0) == 0
    except (TypeError, ValueError):
        return False


def review_gate_from_status(status: Mapping[str, Any]) -> dict[str, Any] | None:
    if str(status.get("autopilot_status") or "").strip().lower() in {"stopped", "completed"}:
        return None

    stage = str(status.get("current_stage") or "")
    needs_review = bool(status.get("needs_review")) or stage_needs_human_review(stage)
    active_session = str(status.get("active_invocation_session_id") or "").strip()
    active_status = str(status.get("active_invocation_status") or "").strip()
    operation = str(status.get("active_invocation_operation") or "")
    substep = str(status.get("writing_substep") or "")

    if active_session and (
        status.get("has_active_invocation")
        or status.get("requires_ai_review")
        or active_status in INVOCATION_WAITING_STATUSES
        or active_status in INVOCATION_FAILED_STATUSES
    ):
        gate_type = review_type_for_operation(operation, substep)
        if active_status in INVOCATION_FAILED_STATUSES:
            if gate_type == "macro_plan":
                message = "宏观结构生成或提交失败，尚无可确认的大纲结构。请处理 AI 结果或停止后重新生成。"
                artifact_status = "missing"
            elif gate_type == "act_plan":
                message = "章节规划生成或提交失败，尚无可确认的章节规划。请处理 AI 结果或停止后重新生成。"
                artifact_status = "missing"
            else:
                message = "AI 请求处理失败，当前没有可继续确认的产物。"
                artifact_status = "failed"
            return {
                "type": gate_type,
                "status": "failed",
                "artifact_status": artifact_status,
                "can_resume": False,
                "primary_action": "open_ai_panel",
                "session_id": active_session,
                "operation": operation,
                "node_key": status.get("active_invocation_node_key", ""),
                "error": status.get("autopilot_pause_reason", "") or active_status,
                "message": message,
            }

        if active_status in INVOCATION_WAITING_STATUSES or status.get("requires_ai_review"):
            return {
                "type": gate_type,
                "status": "awaiting_ai_review",
                "artifact_status": "pending",
                "can_resume": False,
                "primary_action": "open_ai_panel",
                "session_id": active_session,
                "operation": operation,
                "node_key": status.get("active_invocation_node_key", ""),
                "message": "AI 请求正在生成、等待审阅、采纳或提交，完成后自动驾驶才能继续。",
            }

    if isinstance(status.get("autopilot_pending_macro_plan"), dict):
        return {
            "type": "macro_plan",
            "status": "persisting",
            "artifact_status": "pending",
            "can_resume": False,
            "primary_action": "wait",
            "message": "宏观结构已提交，正在写入结构树；结构出现后才能确认继续。",
        }

    if not needs_review:
        return None

    if _is_initial_macro_review_context(status):
        if status.get("macro_structure_ready") is False:
            return {
                "type": "macro_plan",
                "status": "persisting",
                "artifact_status": "pending",
                "can_resume": False,
                "primary_action": "wait",
                "message": "宏观结构正在生成或写入结构树，当前还没有可确认的大纲结构。",
            }
        if status.get("macro_structure_ready") is True:
            return {
                "type": "macro_plan",
                "status": "ready",
                "artifact_status": "ready",
                "can_resume": True,
                "primary_action": "resume",
                "action_label": "确认结构，继续",
                "message": "宏观结构已生成，请在结构树核对后继续。",
            }

    if status.get("macro_structure_ready") is False and int(status.get("current_auto_chapters") or 0) == 0:
        return {
            "type": "macro_plan",
            "status": "failed",
            "artifact_status": "missing",
            "can_resume": False,
            "primary_action": "retry_generation",
            "message": "宏观结构尚未生成，当前没有可确认的大纲结构。请重新生成结构树。",
        }

    gate_type = review_type_for_operation(operation, substep)
    if gate_type == "macro_plan":
        message = "宏观结构已生成，请在结构树核对后继续。"
        action_label = "确认结构，继续"
    elif gate_type == "act_plan":
        message = "章节规划已生成，请在结构树核对后继续。"
        action_label = "确认章节规划，继续"
    elif gate_type == "chapter_review":
        message = "章节审阅已完成，请核对审阅结果后继续。"
        action_label = "确认审阅，继续"
    else:
        message = "当前流程等待人工确认，请核对侧栏产物后继续。"
        action_label = "确认后继续"
    return {
        "type": gate_type,
        "status": "ready",
        "artifact_status": "ready",
        "can_resume": True,
        "primary_action": "resume",
        "action_label": action_label,
        "message": message,
    }


def with_review_gate(status: dict[str, Any]) -> dict[str, Any]:
    gate = review_gate_from_status(status)
    if gate:
        status["review_gate"] = gate
    else:
        status.pop("review_gate", None)
    return status


def resume_block_reason_from_status(status: Mapping[str, Any] | None) -> str | None:
    if not status:
        return None
    gate = status.get("review_gate") if isinstance(status.get("review_gate"), dict) else None
    if gate and gate.get("can_resume") is False:
        return str(gate.get("message") or "当前审阅闸门没有可继续的产物")
    active_status = str(status.get("active_invocation_status") or "").strip()
    if status.get("active_invocation_session_id") and active_status in PENDING_INVOCATION_STATUSES:
        return "AI 请求尚未成功提交，不能继续自动驾驶"
    return None
