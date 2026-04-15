"""测试 qwen3.5 思考过程是否被正确关闭

运行前确保 .env 中已配置：
- LLM_PROVIDER=openai
- LLM_DISABLE_REASONING=true
- OPENAI_BASE_URL、OPENAI_API_KEY、OPENAI_MODEL

运行方式：
    pytest tests/integration/infrastructure/ai/test_qwen_thinking_disabled.py -v -s
"""
import asyncio
import os
import re
from pathlib import Path

import pytest
from dotenv import load_dotenv

from domain.ai.services.llm_service import GenerationConfig
from domain.ai.value_objects.prompt import Prompt
from infrastructure.ai.config.settings import Settings
from infrastructure.ai.providers.openai_provider import OpenAIProvider


def _repo_root() -> Path:
    p = Path(__file__).resolve()
    for parent in [p, *p.parents]:
        if (parent / "pytest.ini").is_file():
            return parent
    return p.parent


load_dotenv(_repo_root() / ".env")


THINKING_PATTERNS = [
    re.compile(r"<think>.*?</think>", re.IGNORECASE | re.DOTALL),
    re.compile(r"<<think>>.*?<</think>>", re.IGNORECASE | re.DOTALL),
    re.compile(r"<think>.*?</think>", re.IGNORECASE | re.DOTALL),
    re.compile(r"\[思考\].*?\[/思考\]", re.IGNORECASE | re.DOTALL),
    re.compile(r"\[thinking\].*?\[/thinking\]", re.IGNORECASE | re.DOTALL),
]


def has_thinking_content(text: str) -> tuple[bool, list[str]]:
    """检查文本中是否包含思考过程
    
    Args:
        text: 要检查的文本
        
    Returns:
        (是否包含思考内容, 匹配到的思考内容列表)
    """
    if not text:
        return False, []
    
    matches = []
    for pattern in THINKING_PATTERNS:
        found = pattern.findall(text)
        if found:
            matches.extend(found)
    
    return len(matches) > 0, matches


@pytest.mark.integration
@pytest.mark.asyncio
async def test_qwen_thinking_disabled():
    """测试 qwen3.5 调用后是否包含思考过程
    
    验证点：
    1. LLM_DISABLE_REASONING 必须为 true
    2. API 响应中不应包含思考标签
    3. 响应内容应该是干净的输出
    """
    # 检查必要的环境变量
    provider_type = os.getenv("LLM_PROVIDER", "").lower()
    if provider_type != "openai":
        pytest.skip(f"跳过测试：LLM_PROVIDER={provider_type}，需要 openai")
    
    disable_reasoning = os.getenv("LLM_DISABLE_REASONING", "").lower()
    if disable_reasoning not in ("1", "true", "yes"):
        pytest.fail("请在 .env 中设置 LLM_DISABLE_REASONING=true")
    
    base_url = os.getenv("OPENAI_BASE_URL")
    api_key = os.getenv("OPENAI_API_KEY")
    model = os.getenv("OPENAI_MODEL")
    
    if not base_url or not api_key or not model:
        pytest.skip("跳过测试：缺少 OPENAI_BASE_URL、OPENAI_API_KEY 或 OPENAI_MODEL 配置")
    
    if "qwen" not in model.lower():
        # 如果不是 qwen 模型，仍然可以测试，但给出警告
        print(f"\n⚠️  警告：当前模型 {model} 不是 qwen，但仍然会测试思考过程过滤")
    
    print(f"\n📋 测试配置:")
    print(f"   - LLM Provider: {provider_type}")
    print(f"   - Disable Reasoning: {disable_reasoning}")
    print(f"   - Base URL: {base_url}")
    print(f"   - Model: {model}")
    
    # 创建 LLM Provider
    settings = Settings(
        api_key=api_key,
        base_url=base_url
    )
    provider = OpenAIProvider(settings)
    
    # 构造测试提示
    prompt = Prompt(
        system="你是一个助手，请直接回答问题，不要输出任何思考过程。",
        user="请简单回答：1+1等于几？只输出答案，不要解释。"
    )
    
    config = GenerationConfig(
        model=model,
        temperature=0.1,  # 低温度以获得确定性输出
        max_tokens=256
    )
    
    print(f"\n🚀 调用 LLM API...")
    
    # 调用 API
    try:
        result = await provider.generate(prompt, config)
    except Exception as e:
        pytest.fail(f"LLM API 调用失败: {e}")
    
    content = result.content
    
    print(f"\n📝 响应内容:")
    print(f"   {content[:500]}")  # 打印前 500 字符
    print(f"\n📊 Token 使用:")
    print(f"   - Input: {result.token_usage.input_tokens}")
    print(f"   - Output: {result.token_usage.output_tokens}")
    
    # 检查是否包含思考内容
    has_thinking, thinking_matches = has_thinking_content(content)
    
    print(f"\n✅ 检查结果:")
    if has_thinking:
        print(f"   ❌ 发现思考过程内容！")
        print(f"   匹配到的思考内容数量: {len(thinking_matches)}")
        for i, match in enumerate(thinking_matches[:3], 1):  # 只显示前 3 个
            preview = match[:100] + "..." if len(match) > 100 else match
            print(f"   {i}. {preview}")
        
        pytest.fail(
            f"响应中包含思考过程内容！发现 {len(thinking_matches)} 个思考标签。"
            f"请检查 LLM_DISABLE_REASONING 配置是否正确。"
        )
    else:
        print(f"   ✅ 未发现思考过程内容")
        print(f"   响应内容干净，思考过程已成功关闭")
    
    # 额外检查：内容应该是简洁的答案
    content_clean = content.strip()
    print(f"\n📏 内容长度检查:")
    print(f"   - 字符数: {len(content_clean)}")
    print(f"   - 行数: {len(content_clean.splitlines())}")
    
    # 对于简单问题，响应应该比较简短
    if len(content_clean) > 500:
        print(f"   ⚠️  警告：响应内容较长，可能包含额外信息")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_qwen_thinking_disabled_with_complex_prompt():
    """使用复杂提示测试思考过程关闭
    
    使用更容易触发思考的复杂问题来验证
    """
    # 检查必要的环境变量
    provider_type = os.getenv("LLM_PROVIDER", "").lower()
    if provider_type != "openai":
        pytest.skip(f"跳过测试：LLM_PROVIDER={provider_type}，需要 openai")
    
    disable_reasoning = os.getenv("LLM_DISABLE_REASONING", "").lower()
    if disable_reasoning not in ("1", "true", "yes"):
        pytest.fail("请在 .env 中设置 LLM_DISABLE_REASONING=true")
    
    base_url = os.getenv("OPENAI_BASE_URL")
    api_key = os.getenv("OPENAI_API_KEY")
    model = os.getenv("OPENAI_MODEL")
    
    if not base_url or not api_key or not model:
        pytest.skip("跳过测试：缺少必要配置")
    
    print(f"\n📋 测试配置（复杂提示）:")
    print(f"   - Model: {model}")
    print(f"   - Disable Reasoning: {disable_reasoning}")
    
    # 创建 LLM Provider
    settings = Settings(
        api_key=api_key,
        base_url=base_url
    )
    provider = OpenAIProvider(settings)
    
    # 构造更容易触发思考的复杂提示
    prompt = Prompt(
        system="""你是一个小说创作助手。请严格按照以下要求输出：
1. 只输出 JSON 格式的内容
2. 不要包含任何思考过程
3. 不要使用任何 markdown 格式
4. 直接输出 JSON 对象""",
        user="""请为以下场景生成一个简短的故事大纲（JSON格式）：
{
  "genre": "科幻",
  "theme": "时间旅行",
  "characters": ["主角", "导师", "反派"],
  "acts": 3
}

只输出 JSON，不要其他内容。"""
    )
    
    config = GenerationConfig(
        model=model,
        temperature=0.2,
        max_tokens=512
    )
    
    print(f"\n🚀 调用 LLM API（复杂提示）...")
    
    try:
        result = await provider.generate(prompt, config)
    except Exception as e:
        pytest.fail(f"LLM API 调用失败: {e}")
    
    content = result.content
    
    print(f"\n📝 响应内容（前 300 字符）:")
    print(f"   {content[:300]}")
    
    # 检查是否包含思考内容
    has_thinking, thinking_matches = has_thinking_content(content)
    
    print(f"\n✅ 检查结果:")
    if has_thinking:
        print(f"   ❌ 发现思考过程内容！")
        print(f"   匹配到的思考内容数量: {len(thinking_matches)}")
        pytest.fail(
            f"复杂提示下响应中仍包含思考过程内容！"
            f"发现 {len(thinking_matches)} 个思考标签。"
        )
    else:
        print(f"   ✅ 未发现思考过程内容")
        print(f"   复杂提示下思考过程也已成功关闭")
    
    # 检查响应是否以 JSON 开头（验证是否干净）
    content_stripped = content.strip()
    if content_stripped.startswith("{") or content_stripped.startswith("["):
        print(f"   ✅ 响应以 JSON 格式开始，内容干净")
    else:
        print(f"   ⚠️  响应不是以 JSON 开始，可能包含前缀内容")
        print(f"   前 50 字符: {content_stripped[:50]}")


if __name__ == "__main__":
    # 允许直接运行此文件
    asyncio.run(test_qwen_thinking_disabled())
