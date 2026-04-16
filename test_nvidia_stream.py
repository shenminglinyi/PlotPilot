import asyncio
import json
import httpx

async def test_nvidia_streaming():
    api_key = "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"
    
    with open(r"C:\Users\我本凡尘ST\Downloads\request-body-gid___axonhub_Request_1308.json", "r", encoding="utf-8") as f:
        request_body = json.load(f)
    
    print("=" * 60)
    print("NVIDIA API Streaming Test (官方推荐方式)")
    print("=" * 60)
    print(f"Model: {request_body.get('model')}")
    print(f"Instructions length: {len(request_body.get('instructions', ''))}")
    print(f"Input length: {len(request_body.get('input', [{}])[0].get('content', ''))}")
    print()
    
    # Convert to Chat Completions format with streaming (as NVIDIA recommends)
    chat_request = {
        "model": request_body.get("model"),
        "messages": [
            {"role": "system", "content": request_body.get("instructions", "")},
            {"role": "user", "content": request_body.get("input", [{}])[0].get("content", "")}
        ],
        "max_tokens": 16384,
        "temperature": request_body.get("temperature", 0.7),
        "stream": True
    }
    
    print("Testing with STREAMING mode (stream=True)...")
    print(f"Request keys: {list(chat_request.keys())}")
    print()
    
    try:
        async with httpx.AsyncClient(timeout=300.0) as client:
            async with client.stream(
                "POST",
                "https://integrate.api.nvidia.com/v1/chat/completions",
                json=chat_request,
                headers={
                    "Authorization": "Bearer " + api_key,
                    "Content-Type": "application/json",
                    "Accept": "text/event-stream"
                }
            ) as response:
                print(f"Status: {response.status_code}")
                
                if response.status_code != 200:
                    print(f"Error body: {await response.aread()}")
                    return
                
                # Count chunks and collect content
                chunk_count = 0
                first_chunk_time = None
                import time
                start_time = time.time()
                
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        data = line[6:]  # Remove "data: " prefix
                        if data == "[DONE]":
                            print(f"\n[DONE] received at {time.time() - start_time:.2f}s")
                            break
                        
                        chunk_count += 1
                        if chunk_count == 1:
                            first_chunk_time = time.time() - start_time
                            print(f"First chunk at {first_chunk_time:.2f}s")
                        
                        # Parse and show first few chunks
                        if chunk_count <= 3:
                            try:
                                chunk_data = json.loads(data)
                                choices = chunk_data.get("choices", [])
                                if choices:
                                    delta = choices[0].get("delta", {})
                                    content = delta.get("content", "")
                                    print(f"Chunk {chunk_count}: {repr(content[:50])}")
                            except:
                                pass
                
                print(f"\nTotal chunks: {chunk_count}")
                print(f"Total time: {time.time() - start_time:.2f}s")
                
    except Exception as e:
        print(f"Error: {type(e).__name__}: {e}")

if __name__ == "__main__":
    asyncio.run(test_nvidia_streaming())
