import asyncio
import json
import httpx

async def test_chat_completions_long_timeout():
    api_key = "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"
    
    with open(r"C:\Users\我本凡尘ST\Downloads\request-body-gid___axonhub_Request_1308.json", "r", encoding="utf-8") as f:
        request_body = json.load(f)
    
    print("Testing NVIDIA API with Chat Completions format (300s timeout)...")
    
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
        "max_tokens": 16384,
        "temperature": request_body.get("temperature", 0.7)
    }
    
    print("Format:", list(chat_request.keys()))
    print("Model:", chat_request.get("model"))
    print("Max tokens:", chat_request.get("max_tokens"))
    print("Messages count:", len(chat_request["messages"]))
    print()
    
    try:
        async with httpx.AsyncClient(timeout=300.0) as client:
            response = await client.post(
                "https://integrate.api.nvidia.com/v1/chat/completions",
                json=chat_request,
                headers={
                    "Authorization": "Bearer " + api_key,
                    "Content-Type": "application/json",
                    "Accept": "application/json"
                }
            )
            print("Status:", response.status_code)
            resp_text = response.text
            if len(resp_text) > 1500:
                print("Response (first 1500 chars):", resp_text[:1500])
                print("... (truncated)")
            else:
                print("Response:", resp_text)
    except Exception as e:
        print("Error:", type(e).__name__, str(e))

asyncio.run(test_chat_completions_long_timeout())
