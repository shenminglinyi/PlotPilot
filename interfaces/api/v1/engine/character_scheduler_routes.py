"""角色调度服务 API

提供角色智能调度接口，用于章节生成时的上下文构建。
这是正式功能，被核心生成流程调用。
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import List, Dict, Optional
import logging
from interfaces.api.dependencies import get_character_narrative_kernel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/character-scheduler", tags=["character-scheduler"])


# ========== 请求/响应模型 ==========

class CharacterInput(BaseModel):
    """角色输入模型"""
    id: str = Field(..., description="角色ID")
    name: str = Field(..., description="角色名称")
    importance: str = Field(..., description="重要性: protagonist/major/minor/background")
    activity_count: int = Field(default=0, description="出场次数")
    last_appearance_chapter: int = Field(default=0, description="最后出场章节")
    mental_state: str = Field(default="NORMAL", description="心理状态")
    mental_state_reason: str = Field(default="", description="心理状态原因")
    verbal_tic: str = Field(default="", description="口头禅")
    idle_behavior: str = Field(default="", description="待机动作")


class ScheduleRequest(BaseModel):
    """调度请求"""
    novel_id: Optional[str] = Field(default=None, description="小说ID；提供后使用 CharacterNarrativeKernel")
    outline: str = Field(..., description="章节大纲")
    characters: List[CharacterInput] = Field(..., description="可用角色列表")
    max_characters: int = Field(default=7, ge=1, le=15, description="最大角色数")
    current_chapter: int = Field(default=1, ge=1, description="当前章节号")
    max_tokens: int = Field(default=5000, ge=500, le=15000, description="Token预算上限")
    mentioned_names: List[str] = Field(default_factory=list, description="大纲中明确提到的角色名")


class CharacterOutput(BaseModel):
    """角色输出模型"""
    id: str
    name: str
    importance: str
    activity_count: int
    mental_state: str
    verbal_tic: str
    idle_behavior: str
    is_mentioned: bool = Field(default=False, description="是否在大纲中提及")
    is_selected: bool = Field(default=False, description="是否被选中")
    is_recently_appeared: bool = Field(default=False, description="是否刚登场")
    reject_reason: Optional[str] = Field(default=None, description="拒绝原因")


class ScheduleResponse(BaseModel):
    """调度响应"""
    selected_characters: List[CharacterOutput]
    rejected_characters: List[CharacterOutput]
    generated_context: str = Field(..., description="生成的上下文Prompt")
    total_tokens: int
    scheduling_log: List[str]


# ========== 核心调度算法 ==========

def _schedule_characters(
    outline: str,
    characters: List[CharacterInput],
    max_characters: int,
    mentioned_names: List[str]
) -> tuple:
    """智能角色调度算法

    策略：
    1. 大纲提及的角色 → 最高优先级
    2. 未提及的角色 → 重要性 > 活动度
    3. 最大限制截断
    """
    # 重要性优先级映射
    importance_priority = {
        "protagonist": 0,
        "major": 1,
        "minor": 2,
        "background": 3
    }

    # 分类：提及的 vs 未提及的
    mentioned_chars = []
    unmentioned_chars = []

    for char in characters:
        is_mentioned = char.name in mentioned_names or char.name in outline
        is_recent = char.activity_count <= 1

        priority = importance_priority.get(char.importance.lower(), 3)

        if is_mentioned:
            mentioned_chars.append((char, is_recent, priority))
        else:
            unmentioned_chars.append((char, is_recent, priority))

    # 排序未提及角色：重要性 > 活动度
    unmentioned_chars.sort(key=lambda x: (
        x[2],  # 重要性优先级
        -x[0].activity_count  # 活动度降序
    ))

    # 合并队列
    queue = mentioned_chars + unmentioned_chars

    # 截断
    selected = queue[:max_characters]
    rejected = queue[max_characters:]

    return selected, rejected


def _generate_context(selected: List[tuple]) -> str:
    """生成角色上下文Prompt"""
    lines = ["【角色设定约束】\n"]

    for char, is_recent, _ in selected:
        lines.append(f"角色：{char.name}\n")
        lines.append(f"描述：{char.importance}\n")
        lines.append(f"心理状态：{char.mental_state}\n")
        if char.mental_state_reason:
            lines.append(f"心理原因：{char.mental_state_reason}\n")
        if char.verbal_tic:
            lines.append(f"口头禅：{char.verbal_tic}\n")
        if char.idle_behavior:
            lines.append(f"待机动作：{char.idle_behavior}\n")

        if is_recent:
            lines.append(f"[连续性约束] {char.name} 刚在上一章出场，需保持人设一致性。\n")

        lines.append("\n")

    return "".join(lines)


# ========== API 端点 ==========

@router.post("/schedule", response_model=ScheduleResponse)
async def schedule_characters(
    request: ScheduleRequest,
    kernel = Depends(get_character_narrative_kernel),
):
    """智能角色调度

    根据章节大纲和角色信息，智能选择合适的角色用于上下文构建。
    这是正式功能，被章节生成流程调用。

    Args:
        request: 包含大纲、角色列表、调度参数

    Returns:
        ScheduleResponse: 选中的角色、生成的上下文
    """
    try:
        logger.info(
            f"角色调度请求: 大纲长度={len(request.outline)}, "
            f"角色数={len(request.characters)}, 最大={request.max_characters}"
        )

        # 新路径：提供 novel_id 时统一走角色叙事内核。
        if request.novel_id:
            plan = kernel.plan_cast(
                novel_id=request.novel_id,
                chapter_number=request.current_chapter,
                outline=request.outline,
                max_characters=request.max_characters,
            )
            selected_outputs = [
                CharacterOutput(
                    id=s.character_id,
                    name=s.name,
                    importance=s.importance,
                    activity_count=0,
                    mental_state="",
                    verbal_tic="",
                    idle_behavior="",
                    is_mentioned=s.name in request.outline or s.name in request.mentioned_names,
                    is_selected=True,
                    is_recently_appeared=s.is_new_suggestion,
                )
                for s in plan.slots
            ]
            estimated_tokens = len(plan.generated_context) // 4
            return ScheduleResponse(
                selected_characters=selected_outputs,
                rejected_characters=[],
                generated_context=plan.generated_context,
                total_tokens=estimated_tokens,
                scheduling_log=plan.scheduling_log + [f"kernel_route=character-scheduler"],
            )

        # 兼容旧调用：未提供 novel_id 时使用请求内角色列表。
        selected, rejected = _schedule_characters(
            outline=request.outline,
            characters=request.characters,
            max_characters=request.max_characters,
            mentioned_names=request.mentioned_names
        )

        # 生成上下文
        context = _generate_context(selected)

        # 构建输出
        selected_outputs = []
        for char, is_recent, _ in selected:
            selected_outputs.append(CharacterOutput(
                id=char.id,
                name=char.name,
                importance=char.importance,
                activity_count=char.activity_count,
                mental_state=char.mental_state,
                verbal_tic=char.verbal_tic,
                idle_behavior=char.idle_behavior,
                is_mentioned=char.name in request.mentioned_names or char.name in request.outline,
                is_selected=True,
                is_recently_appeared=is_recent
            ))

        rejected_outputs = []
        for char, is_recent, _ in rejected:
            rejected_outputs.append(CharacterOutput(
                id=char.id,
                name=char.name,
                importance=char.importance,
                activity_count=char.activity_count,
                mental_state=char.mental_state,
                verbal_tic=char.verbal_tic,
                idle_behavior=char.idle_behavior,
                is_mentioned=char.name in request.mentioned_names or char.name in request.outline,
                is_selected=False,
                is_recently_appeared=is_recent,
                reject_reason=f"超出最大角色数限制({request.max_characters})"
            ))

        # 估算 Token
        estimated_tokens = len(context) // 4  # 粗略估算

        scheduling_log = [
            f"输入角色: {len(request.characters)}",
            f"大纲提及: {len(request.mentioned_names)}",
            f"选中角色: {len(selected)}",
            f"拒绝角色: {len(rejected)}",
            f"估算Token: {estimated_tokens}"
        ]

        logger.info(f"角色调度完成: 选中{len(selected)}个, 拒绝{len(rejected)}个")

        return ScheduleResponse(
            selected_characters=selected_outputs,
            rejected_characters=rejected_outputs,
            generated_context=context,
            total_tokens=estimated_tokens,
            scheduling_log=scheduling_log
        )

    except Exception as e:
        logger.error(f"角色调度失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/quick-test", response_model=ScheduleResponse)
async def quick_test():
    """快速测试接口

    使用预设数据进行快速验证，方便开发和测试。
    """
    preset_request = ScheduleRequest(
        outline="艾达在黑市拍卖会上与林羽相遇，苏晴在一旁观察",
        characters=[
            CharacterInput(
                id="char-001",
                name="林羽",
                importance="protagonist",
                activity_count=50,
                last_appearance_chapter=10,
                mental_state="NORMAL",
                idle_behavior="摸剑柄"
            ),
            CharacterInput(
                id="char-002",
                name="艾达",
                importance="minor",
                activity_count=1,
                last_appearance_chapter=10,
                mental_state="冷漠",
                mental_state_reason="刚失去同伴",
                idle_behavior="擦拭机械臂"
            ),
            CharacterInput(
                id="char-003",
                name="苏晴",
                importance="major",
                activity_count=30,
                last_appearance_chapter=8,
                mental_state="担忧",
                idle_behavior="咬嘴唇"
            ),
        ],
        max_characters=2,
        current_chapter=11,
        max_tokens=5000,
        mentioned_names=["艾达"]
    )

    return await schedule_characters(preset_request)
