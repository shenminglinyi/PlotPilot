import asyncio
import httpx

async def test_simple():
    api_key = "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"
    
    print("Test 1: Simple Chat Completions request to NVIDIA...")
    
    chat_request = {
        "model": "moonshotai/kimi-k2.5",
        "messages": [
            {"role": "user", "content": "Say hello in one sentence."}
        ],
        "max_tokens": 64,
        "temperature": 0.7
    }
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                "https://integrate.api.nvidia.com/v1/chat/completions",
                json=chat_request,
                headers={
                    "Authorization": "Bearer " + api_key,
                    "Content-Type": "application/json"
                }
            )
            print("Status:", response.status_code)
            print("Response:", response.text[:500])
    except Exception as e:
        print("Error:", type(e).__name__, str(e))
    
    print()
    print("Test 2: Medium request...")
    
    chat_request2 = {
        "model": "moonshotai/kimi-k2.5",
        "messages": [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Write a short story about a programmer who finds a bug in reality. Keep it under 200 words."}
        ],
        "max_tokens": 512,
        "temperature": 0.7
    }
    
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                "https://integrate.api.nvidia.com/v1/chat/completions",
                json=chat_request2,
                headers={
                    "Authorization": "Bearer " + api_key,
                    "Content-Type": "application/json"
                }
            )
            print("Status:", response.status_code)
            print("Response:", response.text[:500])
    except Exception as e:
        print("Error:", type(e).__name__, str(e))

asyncio.run(test_simple())
