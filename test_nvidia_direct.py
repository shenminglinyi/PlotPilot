import asyncio
import json
import httpx

async def test():
    api_key = "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"
    
    with open(r"C:\Users\我本凡尘ST\Downloads\request-body-gid___axonhub_Request_1308.json", "r", encoding="utf-8") as f:
        request_body = json.load(f)
    
    print("Testing NVIDIA API directly with captured request...")
    print("Format:", list(request_body.keys()))
    print("Model:", request_body.get("model"))
    print("Max tokens:", request_body.get("max_output_tokens"))
    print()
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                "https://integrate.api.nvidia.com/v1/responses",
                json=request_body,
                headers={
                    "Authorization": "Bearer " + api_key,
                    "Content-Type": "application/json",
                    "Accept": "application/json"
                }
            )
            print("Status:", response.status_code)
            print("Response:", response.text[:1000])
    except Exception as e:
        print("Error:", type(e).__name__, str(e))

asyncio.run(test())
