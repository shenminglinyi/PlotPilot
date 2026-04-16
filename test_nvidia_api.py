"""
NVIDIA API 直接测试脚本
使用捕获的请求体直接测试 NVIDIA 官方 API
"""
import asyncio
import json
import os
from pathlib import Path

import httpx

# NVIDIA 官方 API 端点
NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"

async def test_nvidia_api():
    """测试 NVIDIA API"""
    
    # 从环境变量获取 API Key
    api_key = os.getenv("NVIDIA_API_KEY")
    if not api_key:
        print("❌ 未找到 NVIDIA_API_KEY 环境变量")
        print("请设置: set NVIDIA_API_KEY=your_api_key_here")
        return
    
    # 读取捕获的请求体
    request_body_path = Path(r"C:\Users\我本凡尘ST\Downloads\request-body-gid___axonhub_Request_1308.json")
    if not request_body_path.exists():
        print(f"❌ 请求体文件不存在: {request_body_path}")
        return
    
    with open(request_body_path, "r", encoding="utf-8") as f:
        request_body = json.load(f)
    
    print("=" * 60)
    print("NVIDIA API 直接测试")
    print("=" * 60)
    print(f"请求体格式: {list(request_body.keys())}")
    print(f"模型: {request_body.get('model', 'N/A')}")
    print(f"max_output_tokens: {request_body.get('max_output_tokens', 'N/A')}")
    print()
    
    # 测试 1: 使用原始请求体（Responses API 格式）
    print("📤 测试 1: Responses API 格式 (/v1/responses)")
    print("-" * 60)
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{NVIDIA_BASE_URL}/responses",
                json=request_body,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json"
                }
            )
            print(f"状态码: {response.status_code}")
            print(f"响应头: {dict(response.headers)}")
            print(f"响应体: {response.text[:500]}")
    except Exception as e:
        print(f"❌ 错误: {e}")
    
    print()
    
    # 测试 2: 转换为 Chat Completions 格式
    print("📤 测试 2: Chat Completions API 格式 (/v1/chat/completions)")
    print("-" * 60)
    
    # 转换请求体格式
    chat_request = {
        "model": request_body.get("model"),
        "messages": [
            {
                "role": "system",
                "content": request_body.get("instructions", "")
            },
            {
                "role": "user",
                "content": request_body.get("input", [{}])[0].get("content", "")
            }
        ],
        "max_tokens": request_body.get("max_output_tokens", 12288),
        "temperature": request_body.get("temperature", 0.7)
    }
    
    print(f"转换后格式: {list(chat_request.keys())}")
    print(f"messages 数量: {len(chat_request['messages'])}")
    print(f"system 内容长度: {len(chat_request['messages'][0]['content'])}")
    print(f"user 内容长度: {len(chat_request['messages'][1]['content'])}")
    print()
    
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                f"{NVIDIA_BASE_URL}/chat/completions",
                json=chat_request,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json"
                }
            )
            print(f"状态码: {response.status_code}")
            print(f"响应体: {response.text[:500]}")
    except Exception as e:
        print(f"❌ 错误: {e}")

if __name__ == "__main__":
    asyncio.run(test_nvidia_api())
