"""Manual test script for Voice API"""
import json
import uuid

import pytest

requests = pytest.importorskip("requests")

BASE_URL = "http://localhost:8000/api/v1"


def test_voice_api():
    """手动测试 Voice API"""

    # 1. 创建测试小说
    novel_id = f"test-voice-{uuid.uuid4().hex[:8]}"
    print(f"\n1. 创建测试小说: {novel_id}")

    novel_response = requests.post(
        f"{BASE_URL}/novels",
        json={
            "novel_id": novel_id,
            "title": "文风测试小说",
            "author": "测试作者",
            "target_chapters": 10,
            "premise": "这是一个测试文风收集的小说"
        }
    )
    print(f"   状态码: {novel_response.status_code}")
    print(f"   响应: {json.dumps(novel_response.json(), ensure_ascii=False, indent=2)}")

    if novel_response.status_code != 201:
        print("   ❌ 创建小说失败")
        return

    # 2. 创建文风样本
    print(f"\n2. 创建文风样本")

    sample_data = {
        "ai_original": "夜幕降临，城市的灯光逐渐亮起。街道上行人匆匆，车辆川流不息。",
        "author_refined": "夜色如墨，城市的霓虹灯次第点亮。街头人影匆匆，车流如织。",
        "chapter_number": 1,
        "scene_type": "description"
    }

    sample_response = requests.post(
        f"{BASE_URL}/novels/{novel_id}/voice/samples",
        json=sample_data
    )
    print(f"   状态码: {sample_response.status_code}")
    print(f"   响应: {json.dumps(sample_response.json(), ensure_ascii=False, indent=2)}")

    if sample_response.status_code != 201:
        print("   ❌ 创建样本失败")
        return

    sample_id = sample_response.json()["sample_id"]
    print(f"   ✅ 样本创建成功: {sample_id}")

    # 3. 创建第二个样本
    print(f"\n3. 创建第二个文风样本")

    sample_data_2 = {
        "ai_original": "他说：'我们必须尽快行动。'",
        "author_refined": "'我们得抓紧时间。'他说。",
        "chapter_number": 2,
        "scene_type": "dialogue"
    }

    sample_response_2 = requests.post(
        f"{BASE_URL}/novels/{novel_id}/voice/samples",
        json=sample_data_2
    )
    print(f"   状态码: {sample_response_2.status_code}")
    print(f"   响应: {json.dumps(sample_response_2.json(), ensure_ascii=False, indent=2)}")

    if sample_response_2.status_code == 201:
        sample_id_2 = sample_response_2.json()["sample_id"]
        print(f"   ✅ 样本创建成功: {sample_id_2}")

    # 4. 测试验证
    print(f"\n4. 测试输入验证（空 AI 原文）")

    invalid_data = {
        "ai_original": "",
        "author_refined": "作者改稿",
        "chapter_number": 1,
        "scene_type": "action"
    }

    invalid_response = requests.post(
        f"{BASE_URL}/novels/{novel_id}/voice/samples",
        json=invalid_data
    )
    print(f"   状态码: {invalid_response.status_code}")
    if invalid_response.status_code == 422:
        print(f"   ✅ 验证正常工作")
    else:
        print(f"   ❌ 验证未按预期工作")

    print("\n" + "="*60)
    print("✅ Voice API 测试完成！")
    print("="*60)


if __name__ == "__main__":
    try:
        test_voice_api()
    except requests.exceptions.ConnectionError:
        print("\n❌ 无法连接到后端服务")
        print("请先启动后端: python -m uvicorn interfaces.main:app --reload")
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
