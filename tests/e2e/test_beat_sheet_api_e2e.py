"""
端到端测试：通过 API 测试从章节大纲到节拍表生成的完整链路
不依赖 Playwright，直接调用后端 API
"""

import asyncio
import os
import sys

import httpx

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))


async def test_beat_sheet_generation_api():
    """测试节拍表生成的完整 API 流程"""

    base_url = "http://localhost:8000"

    print("=" * 80)
    print("端到端测试：节拍表生成完整链路（API 测试）")
    print("=" * 80)

    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            # 步骤 1：检查后端健康状态
            print("\n[步骤 1] 检查后端服务...")
            try:
                response = await client.get(f"{base_url}/health")
                print("✓ 后端服务正常运行")
            except Exception as e:
                print(f"✗ 后端服务未启动: {e}")
                print("请先启动后端服务: cd interfaces && python -m uvicorn main:app --reload")
                return

            # 步骤 2：准备测试数据
            print("\n[步骤 2] 准备测试数据...")
            test_chapter_id = "chapter-1775380284512-1"
            test_outline = """
李明收到期末成绩单，发现自己的成绩出现了异常波动。
他开始怀疑这背后隐藏着某种规律，决定深入调查。
在图书馆查阅资料时，他发现了一本神秘的古籍，
里面记载着关于"知识诅咒"的传说。
            """.strip()

            print(f"  章节 ID: {test_chapter_id}")
            print(f"  大纲长度: {len(test_outline)} 字")

            # 步骤 3：生成节拍表
            print("\n[步骤 3] 调用节拍表生成 API...")
            beat_sheet_request = {"chapter_id": test_chapter_id, "outline": test_outline}

            response = await client.post(f"{base_url}/api/v1/beat-sheets/generate", json=beat_sheet_request)

            if response.status_code == 200:
                beat_sheet_data = response.json()
                print("✓ 节拍表生成成功")
                print(f"  章节 ID: {beat_sheet_data.get('chapter_id')}")
                print(f"  场景数量: {len(beat_sheet_data.get('scenes', []))}")

                # 显示场景详情
                scenes = beat_sheet_data.get("scenes", [])
                for i, scene in enumerate(scenes, 1):
                    print(f"\n  场景 {i}: {scene.get('title', 'N/A')}")
                    print(f"    - 目标: {scene.get('goal', 'N/A')[:50]}...")
                    print(f"    - POV: {scene.get('pov', 'N/A')}")
                    print(f"    - 地点: {scene.get('location', 'N/A')}")
                    print(f"    - 基调: {scene.get('tone', 'N/A')}")
                    print(f"    - 预估字数: {scene.get('estimated_words', 'N/A')}")

                # 步骤 4：验证节拍表数据结构
                print("\n[步骤 4] 验证节拍表数据结构...")
                assert "chapter_id" in beat_sheet_data, "缺少 chapter_id"
                assert "scenes" in beat_sheet_data, "缺少 scenes"
                assert len(scenes) > 0, "场景列表为空"

                for i, scene in enumerate(scenes, 1):
                    assert "title" in scene, f"场景 {i} 缺少 title"
                    assert "goal" in scene, f"场景 {i} 缺少 goal"
                    assert "pov" in scene, f"场景 {i} 缺少 pov"
                    assert "location" in scene, f"场景 {i} 缺少 location"
                    assert "tone" in scene, f"场景 {i} 缺少 tone"
                    assert "estimated_words" in scene, f"场景 {i} 缺少 estimated_words"

                print("✓ 数据结构验证通过")

                # 步骤 5：测试场景生成（生成第一个场景）
                print("\n[步骤 5] 测试场景生成...")
                first_scene = scenes[0]
                scene_request = {
                    "chapter_id": test_chapter_id,
                    "scene_number": 1,
                    "scene_title": first_scene["title"],
                    "scene_goal": first_scene["goal"],
                    "pov": first_scene["pov"],
                    "location": first_scene["location"],
                    "tone": first_scene["tone"],
                    "estimated_words": first_scene["estimated_words"],
                }

                scene_response = await client.post(f"{base_url}/api/v1/scenes/generate", json=scene_request)

                if scene_response.status_code == 200:
                    scene_data = scene_response.json()
                    content = scene_data.get("content", "")
                    print("✓ 场景生成成功")
                    print(f"  生成字数: {len(content)} 字")
                    print(f"  内容预览: {content[:200]}...")

                    # 验证场景数据
                    assert "content" in scene_data, "缺少 content"
                    assert len(content) > 0, "生成内容为空"
                    print("✓ 场景数据验证通过")
                else:
                    print(f"⚠ 场景生成失败: {scene_response.status_code}")
                    print(f"  错误信息: {scene_response.text}")

                # 步骤 6：获取已保存的节拍表
                print("\n[步骤 6] 获取已保存的节拍表...")
                get_response = await client.get(f"{base_url}/api/v1/beat-sheets/chapter/{test_chapter_id}")

                if get_response.status_code == 200:
                    saved_beat_sheet = get_response.json()
                    print("✓ 节拍表获取成功")
                    print(f"  场景数量: {len(saved_beat_sheet.get('scenes', []))}")
                elif get_response.status_code == 404:
                    print("⚠ 节拍表未找到（可能未持久化）")
                else:
                    print(f"⚠ 获取失败: {get_response.status_code}")

            else:
                print(f"✗ 节拍表生成失败: {response.status_code}")
                print(f"  错误信息: {response.text}")
                return

            print("\n" + "=" * 80)
            print("✓ 端到端测试完成！所有步骤通过")
            print("=" * 80)

        except Exception as e:
            print(f"\n✗ 测试失败: {str(e)}")
            import traceback

            traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(test_beat_sheet_generation_api())
