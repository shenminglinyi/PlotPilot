from enum import Enum


class StorylineRole(Enum):
    """故事线结构角色 —— 描述这条线在叙事架构中的位置。"""
    MAIN = "main"   # 主线：主人公的核心目标与冲突，全书骨架
    SUB  = "sub"    # 支线：服务/延迟/反衬主线，最终需汇流
    DARK = "dark"   # 暗线：隐含因果链；读者在汇流章节才意识到
