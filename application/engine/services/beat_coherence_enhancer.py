"""
节拍连贯性增强器

专门用于优化节拍生成过程中的内容连贯性，确保章节内各个节拍之间的情节、场景、人物的连续性。
"""

import logging
import re
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass

from application.engine.services.context_builder import ContextBuilder
from application.engine.dtos.scene_director_dto import SceneDirectorAnalysis

logger = logging.getLogger(__name__)


@dataclass
class BeatContext:
    """节拍上下文信息"""
    characters: List[str]  # 当前出现的角色
    scene: str  # 当前场景
    mood: str  # 当前情绪氛围
    ongoing_actions: List[str]  # 进行中的动作
    unresolved_tensions: List[str]  # 未解决的冲突


@dataclass
class CoherenceIssue:
    """连贯性问题"""
    type: str  # role_change, scene_jump, mood_shift, action_mismatch
    description: str
    severity: str  # low, medium, high
    position: int  # 问题在文本中的位置


class BeatCoherenceEnhancer:
    """节拍连贯性增强器
    
    主要职责：
    1. 分析节拍间的内容连贯性
    2. 检测潜在的连贯性问题
    3. 提供连贯性修复建议
    4. 生成连贯性增强的提示词
    """
    
    def __init__(self):
        # 场景转换关键词 - 用于检测突兀的场景切换
        self.scene_transition_words = [
            '来到', '进入', '走出', '离开', '到达', '前往',
            '转眼间', '与此同时', '就在这时', '突然',
            '另一个地方', '别处'
        ]
        
        # 时间推进关键词
        self.time_progression_words = [
            '过了一会儿', '片刻后', '很快', '随即',
            '与此同时', '就在这个时候', '不久后'
        ]
        
        # 情绪转换关键词
        self.mood_transition_words = [
            '但是', '然而', '突然', '没想到', '意外地',
            '不料', '谁知', '转折', '变化'
        ]
    
    def analyze_beat_context(self, content: str, beat_focus: str) -> BeatContext:
        """分析单个节拍的上下文信息"""
        characters = self._extract_characters(content)
        scene = self._extract_scene(content)
        mood = self._extract_mood(content, beat_focus)
        ongoing_actions = self._extract_ongoing_actions(content)
        unresolved_tensions = self._extract_unresolved_tensions(content)
        
        return BeatContext(
            characters=characters,
            scene=scene,
            mood=mood,
            ongoing_actions=ongoing_actions,
            unresolved_tensions=unresolved_tensions
        )
    
    def check_coherence_between_beats(
        self, 
        previous_content: str, 
        current_content: str,
        previous_context: BeatContext,
        current_context: BeatContext
    ) -> List[CoherenceIssue]:
        """检查两个节拍之间的连贯性"""
        issues = []
        
        # 检查角色一致性
        char_issues = self._check_character_coherence(
            previous_context.characters, current_context.characters,
            previous_content, current_content
        )
        issues.extend(char_issues)
        
        # 检查场景连贯性
        scene_issues = self._check_scene_coherence(
            previous_context.scene, current_context.scene,
            previous_content, current_content
        )
        issues.extend(scene_issues)
        
        # 检查情绪连贯性
        mood_issues = self._check_mood_coherence(
            previous_context.mood, current_context.mood,
            previous_content, current_content
        )
        issues.extend(mood_issues)
        
        # 检查动作连贯性
        action_issues = self._check_action_coherence(
            previous_context.ongoing_actions, current_context.ongoing_actions,
            previous_content, current_content
        )
        issues.extend(action_issues)
        
        return issues
    
    def generate_coherence_instructions(
        self, 
        previous_content: str,
        current_beat_description: str,
        previous_context: BeatContext,
        beat_index: int,
        total_beats: int
    ) -> str:
        """生成连贯性增强指令"""
        instructions = []
        
        # 基本连贯要求
        if beat_index > 0:
            instructions.append(
                f"【连贯性基础要求】\n"
                f"1. 作为本章第{beat_index + 1}/{total_beats}节拍，必须与前面的内容保持连贯\n"
                f"2. 延续上文的叙事节奏和语言风格\n"
            )
        
        # 角色连贯指导
        if previous_context.characters:
            characters_str = '、'.join(previous_context.characters)
            instructions.append(
                f"【角色连贯指导】\n"
                f"1. 已出现的角色：{characters_str}\n"
                f"2. 如果继续描写这些角色，保持其性格特征、说话方式和情绪状态\n"
                f"3. 角色的行为动机应与上文保持一致\n"
            )
        
        # 场景连贯指导
        if previous_context.scene:
            instructions.append(
                f"【场景连贯指导】\n"
                f"1. 当前场景：{previous_context.scene}\n"
                f"2. 如需转换场景，请提供合理的过渡说明\n"
                f"3. 场景内物品、光线、声音等细节要保持一致\n"
            )
        
        # 情绪连贯指导
        if previous_context.mood:
            instructions.append(
                f"【情绪连贯指导】\n"
                f"1. 当前情绪氛围：{previous_context.mood}\n"
                f"2. 情绪变化要循序渐进，避免突兀转变\n"
                f"3. 如果需要进行情绪转折，请提供合理的过渡\n"
            )
        
        # 动作连贯指导
        if previous_context.ongoing_actions:
            actions_str = '、'.join(previous_context.ongoing_actions)
            instructions.append(
                f"【动作连贯指导】\n"
                f"1. 进行中的动作：{actions_str}\n"
                f"2. 优先处理这些未完成的动作或对话\n"
                f"3. 新动作的引入要与当前情节发展相符\n"
            )
        
        # 特殊节拍指导
        if beat_index == 0:
            instructions.append(
                f"【开篇节拍指导】\n"
                f"1. 这是本章的第一个节拍，要为本节焦点做好铺垫\n"
                f"2. 明确交代场景、人物和基本状况\n"
                f"3. 为后续节拍留出合理的情节发展空间\n"
            )
        elif beat_index == total_beats - 1:
            instructions.append(
                f"【结尾节拍指导】\n"
                f"1. 这是本章最后一个节拍，需要提供完整的段落收尾\n"
                f"2. 收束当前情节，给读者阶段性的满足感\n"
                f"3. 可以设置下一章的悬念钩子，但不要开启全新情节\n"
            )
        else:
            instructions.append(
                f"【中间节拍指导】\n"
                f"1. 作为过渡性节拍，要承上启下\n"
                f"2. 既要延续上文情节，又要为后续发展做铺垫\n"
                f"3. 保持情节推进的节奏感\n"
            )
        
        return '\n'.join(instructions)
    
    def generate_transition_text(
        self,
        previous_content: str,
        current_beat_focus: str,
        previous_context: BeatContext
    ) -> Optional[str]:
        """生成过渡文本（如果需要的话）"""
        # 检测是否需要场景过渡
        if self._needs_scene_transition(previous_context.scene, current_beat_focus):
            return self._generate_scene_transition(previous_context.scene, current_beat_focus)
        
        # 检测是否需要情绪过渡
        if self._needs_mood_transition(previous_context.mood, current_beat_focus):
            return self._generate_mood_transition(previous_context.mood, current_beat_focus)
        
        return None
    
    def _extract_characters(self, content: str) -> List[str]:
        """从内容中提取角色"""
        characters = []
        
        # 改进的角色提取：查找可能的专有名词（中文名字通常2-4个字）
        name_patterns = [
            r'([\u4e00-\u9fa5]{2,4})(?=：|说|问|道|喊|叫|答|问道|说道|问道|喝道)',  # 名字后跟对话动词
            r'([\u4e00-\u9fa5]{2,4})(?=走了进来|走了出去|站起身|坐下|进来|出去)',  # 名字后跟动作
            r'([\u4e00-\u9fa5]{2,4})(?=心想|暗想|想到|觉得|认为)',  # 名字后跟心理活动
        ]
        
        for pattern in name_patterns:
            matches = re.findall(pattern, content)
            characters.extend(matches)
        
        # 进一步处理：查找"... 他/她"结构中的名字
        pronoun_pattern = r'([\u4e00-\u9fa5]{2,4})[^，。！？\n]{0,20}[，。！？](?:他|她|它)'
        matches = re.findall(pronoun_pattern, content)
        characters.extend(matches)
        
        # 过滤掉常见非人名词汇
        common_words = ['什么', '怎么', '那个', '这个', '哪里', '时候', '事情', '问题', '情况']
        filtered_characters = [char for char in characters if char not in common_words]
        
        # 去重并返回
        return list(set(filtered_characters))
    
    def _extract_scene(self, content: str) -> str:
        """从内容中提取场景信息"""
        scenes = []
        
        # 常见场景关键词
        scene_keywords = {
            '室内': ['房间', '屋子', '大厅', '房间', '书房', '卧室', '客厅'],
            '室外': ['街道', '广场', '花园', '田野', '山路', '河边', '桥头'],
            '战斗': ['战场', '竞技场', '比武场', '城头', '屋顶'],
            '商业': ['商店', '市场', '商铺', '摊位', '客栈', '酒楼', '茶馆']
        }
        
        for scene_type, keywords in scene_keywords.items():
            for keyword in keywords:
                if keyword in content:
                    scenes.append(scene_type)
                    break
        
        return '、'.join(set(scenes)) if scenes else '未知场景'
    
    def _extract_mood(self, content: str, beat_focus: str) -> str:
        """从内容和节拍焦点中提取情绪氛围"""
        # 根据节拍焦点和关键词判断情绪
        mood_keywords = {
            '紧张': ['紧张', '危机', '危险', '惊恐', '恐惧', '害怕'],
            '激烈': ['激烈', '战斗', '打斗', '冲突', '争执', '愤怒'],
            '温馨': ['温馨', '温暖', '关爱', '温情', '甜蜜', '幸福'],
            '悲伤': ['悲伤', '难过', '痛苦', '绝望', '失落', '哀伤'],
            '悬疑': ['疑惑', '困惑', '神秘', '未知', '谜团', '谜题'],
            '欢快': ['开心', '快乐', '欢喜', '愉快', '兴奋', '高兴']
        }
        
        content_lower = content.lower()
        for mood, keywords in mood_keywords.items():
            if any(keyword in content_lower for keyword in keywords):
                return mood
        
        # 根据节拍焦点推断
        focus_mood_map = {
            'action': '激烈',
            'dialogue': '交流',
            'emotion': '情绪化',
            'suspense': '悬疑',
            'sensory': '平静'
        }
        
        return focus_mood_map.get(beat_focus, '中性')
    
    def _extract_ongoing_actions(self, content: str) -> List[str]:
        """提取进行中的动作"""
        actions = []
        
        # 检测对话进行中
        if '：' in content or '说' in content or '问' in content:
            actions.append('对话进行中')
        
        # 检测动作进行中
        action_keywords = ['正在', '开始', '继续', '接着', '然后']
        for keyword in action_keywords:
            if keyword in content:
                actions.append('动作进行中')
                break
        
        # 检测思考进行中
        if '想' in content or '思考' in content or '考虑' in content:
            actions.append('思考进行中')
        
        return actions if actions else ['正常叙述']
    
    def _extract_unresolved_tensions(self, content: str) -> List[str]:
        """提取未解决的冲突"""
        tensions = []
        
        # 检测疑问句
        if '？' in content or '什么' in content or '怎么' in content:
            tensions.append('存在疑问')
        
        # 检测冲突词汇
        conflict_words = ['但是', '然而', '虽然', '尽管', '矛盾', '冲突']
        if any(word in content for word in conflict_words):
            tensions.append('存在冲突')
        
        # 检测中断词汇
        interruption_words = ['突然', '不料', '意外', '变故']
        if any(word in content for word in interruption_words):
            tensions.append('情节中断')
        
        return tensions
    
    def _check_character_coherence(
        self, 
        prev_chars: List[str], 
        curr_chars: List[str],
        prev_content: str,
        curr_content: str
    ) -> List[CoherenceIssue]:
        """检查角色连贯性"""
        issues = []
        
        # 检查角色消失（重要角色突然不见）
        for char in prev_chars:
            if char not in curr_chars and len(curr_chars) > 0:
                issues.append(CoherenceIssue(
                    type="character_disappearance",
                    description=f"角色'{char}'突然消失，缺乏合理解释",
                    severity="medium",
                    position=0
                ))
        
        return issues
    
    def _check_scene_coherence(
        self, 
        prev_scene: str, 
        curr_scene: str,
        prev_content: str,
        curr_content: str
    ) -> List[CoherenceIssue]:
        """检查场景连贯性"""
        issues = []
        
        # 检查突兀的场景转换
        if prev_scene != curr_scene and prev_scene != '未知场景':
            # 检查是否有过渡词汇
            has_transition = any(
                word in curr_content for word in self.scene_transition_words
            )
            
            if not has_transition:
                issues.append(CoherenceIssue(
                    type="scene_jump",
                    description=f"从'{prev_scene}'到'{curr_scene}'缺乏过渡",
                    severity="high",
                    position=0
                ))
        
        return issues
    
    def _check_mood_coherence(
        self, 
        prev_mood: str, 
        curr_mood: str,
        prev_content: str,
        curr_content: str
    ) -> List[CoherenceIssue]:
        """检查情绪连贯性"""
        issues = []
        
        # 检查情绪突变
        mood_shifts = [
            ('温馨', '激烈'), ('平静', '紧张'),
            ('欢快', '悲伤'), ('紧张', '欢快')
        ]
        
        for shift_from, shift_to in mood_shifts:
            if prev_mood == shift_from and curr_mood == shift_to:
                # 检查是否有情绪过渡词汇
                has_transition = any(
                    word in curr_content for word in self.mood_transition_words
                )
                
                if not has_transition:
                    issues.append(CoherenceIssue(
                        type="mood_shift",
                        description=f"情绪从'{prev_mood}'突变到'{curr_mood}'缺乏过渡",
                        severity="medium",
                        position=0
                    ))
                break
        
        return issues
    
    def _check_action_coherence(
        self, 
        prev_actions: List[str], 
        curr_actions: List[str],
        prev_content: str,
        curr_content: str
    ) -> List[CoherenceIssue]:
        """检查动作连贯性"""
        issues = []
        
        # 检查对话中断
        if '对话进行中' in prev_actions and '对话进行中' not in curr_actions:
            # 应该是对话结束了，检查是否有合理的结束
            if not any(punct in prev_content for punct in ['。', '！', '？', '…']):
                issues.append(CoherenceIssue(
                    type="dialogue_interruption",
                    description="对话突然中断，缺乏自然的结束",
                    severity="high",
                    position=len(prev_content)
                ))
        
        return issues
    
    def _needs_scene_transition(self, prev_scene: str, current_beat_focus: str) -> bool:
        """判断是否需要场景过渡"""
        # 如果节拍焦点暗示了不同的场景类型
        scene_focus_map = {
            'combat': '战斗场景',
            'intimate': '私密场景',
            'public': '公共场景'
        }
        
        return False  # 简化实现
    
    def _needs_mood_transition(self, prev_mood: str, current_beat_focus: str) -> bool:
        """判断是否需要情绪过渡"""
        # 如果节拍焦点暗示了不同的情绪类型
        mood_focus_map = {
            'action': '激烈',
            'emotion': '情绪化',
            'suspense': '悬疑'
        }
        
        return False  # 简化实现
    
    def _generate_scene_transition(self, prev_scene: str, target_focus: str) -> str:
        """生成场景过渡文本"""
        return f"\n\n场景自然地过渡，保持着情节的连贯性。\n\n"
    
    def _generate_mood_transition(self, prev_mood: str, target_focus: str) -> str:
        """生成情绪过渡文本"""
        return f"\n\n情绪逐步转变，为接下来的情节发展做好铺垫。\n\n"