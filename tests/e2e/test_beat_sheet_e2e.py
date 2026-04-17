"""
端到端测试：从章节大纲到节拍表生成的完整链路
使用 Playwright 测试前端和后端的集成
"""
import asyncio
import sys
import os

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from playwright.async_api import async_playwright, expect


async def test_beat_sheet_generation_e2e():
    """测试节拍表生成的完整流程"""

    async with async_playwright() as p:
        # 启动浏览器
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()

        print("=" * 80)
        print("端到端测试：节拍表生成完整链路")
        print("=" * 80)

        try:
            # 步骤 1：访问前端应用
            print("\n[步骤 1] 访问前端应用...")
            await page.goto("http://localhost:5173")
            await page.wait_for_load_state("networkidle")
            print("✓ 前端加载成功")

            # 步骤 2：选择或创建小说
            print("\n[步骤 2] 选择测试小说...")
            # 等待小说列表加载
            await page.wait_for_selector("text=程序员穿越成状元", timeout=10000)
            await page.click("text=程序员穿越成状元")
            await page.wait_for_load_state("networkidle")
            print("✓ 小说选择成功")

            # 步骤 3：导航到章节列表
            print("\n[步骤 3] 导航到章节列表...")
            # 点击树形视图或章节列表
            tree_button = page.locator("text=🌳 树形视图")
            if await tree_button.is_visible():
                await tree_button.click()
                await page.wait_for_timeout(1000)
            print("✓ 章节列表加载成功")

            # 步骤 4：选择第一章
            print("\n[步骤 4] 选择第一章...")
            chapter_selector = "text=第1章" or "text=成绩单上的裂痕"
            await page.wait_for_selector(chapter_selector, timeout=10000)
            await page.click(chapter_selector)
            await page.wait_for_load_state("networkidle")
            print("✓ 章节选择成功")

            # 步骤 5：检查章节大纲是否存在
            print("\n[步骤 5] 检查章节大纲...")
            # 查找大纲输入框或显示区域
            outline_exists = await page.locator("text=大纲").count() > 0
            if outline_exists:
                print("✓ 章节大纲存在")
            else:
                print("⚠ 章节大纲不存在，可能需要先创建大纲")

            # 步骤 6：生成节拍表（通过 API 调用）
            print("\n[步骤 6] 生成节拍表...")
            # 直接调用 API 端点
            response = await page.evaluate("""
                async () => {
                    const response = await fetch('http://localhost:8000/api/v1/beat-sheets/generate', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                        },
                        body: JSON.stringify({
                            chapter_id: 'chapter-1775380284512-1',
                            outline: '李明收到期末成绩单，发现自己的成绩出现了异常波动。他开始怀疑这背后隐藏着某种规律，决定深入调查。'
                        })
                    });
                    return await response.json();
                }
            """)

            print(f"API 响应: {response}")

            if 'scenes' in response:
                print(f"✓ 节拍表生成成功，共 {len(response['scenes'])} 个场景")
                for i, scene in enumerate(response['scenes'], 1):
                    print(f"  场景 {i}: {scene.get('title', 'N/A')}")
                    print(f"    - POV: {scene.get('pov', 'N/A')}")
                    print(f"    - 地点: {scene.get('location', 'N/A')}")
                    print(f"    - 预估字数: {scene.get('estimated_words', 'N/A')}")
            else:
                print(f"✗ 节拍表生成失败: {response}")

            # 步骤 7：验证节拍表数据
            print("\n[步骤 7] 验证节拍表数据...")
            if 'scenes' in response and len(response['scenes']) > 0:
                scene = response['scenes'][0]
                assert 'title' in scene, "场景缺少标题"
                assert 'pov' in scene, "场景缺少 POV"
                assert 'location' in scene, "场景缺少地点"
                assert 'estimated_words' in scene, "场景缺少预估字数"
                print("✓ 节拍表数据结构验证通过")

            # 步骤 8：测试场景生成（可选）
            print("\n[步骤 8] 测试场景生成...")
            if 'scenes' in response and len(response['scenes']) > 0:
                scene_response = await page.evaluate("""
                    async (sceneData) => {
                        const response = await fetch('http://localhost:8000/api/v1/scenes/generate', {
                            method: 'POST',
                            headers: {
                                'Content-Type': 'application/json',
                            },
                            body: JSON.stringify({
                                chapter_id: 'chapter-1775380284512-1',
                                scene_number: 1,
                                scene_title: sceneData.title,
                                scene_goal: sceneData.goal,
                                pov: sceneData.pov,
                                location: sceneData.location,
                                tone: sceneData.tone,
                                estimated_words: sceneData.estimated_words
                            })
                        });
                        return await response.json();
                    }
                """, response['scenes'][0])

                if 'content' in scene_response:
                    content_length = len(scene_response['content'])
                    print(f"✓ 场景生成成功，生成 {content_length} 字")
                else:
                    print(f"⚠ 场景生成失败: {scene_response}")

            print("\n" + "=" * 80)
            print("测试完成！")
            print("=" * 80)

        except Exception as e:
            print(f"\n✗ 测试失败: {str(e)}")
            import traceback
            traceback.print_exc()

        finally:
            # 保持浏览器打开以便查看结果
            print("\n按 Enter 键关闭浏览器...")
            input()
            await browser.close()


if __name__ == "__main__":
    asyncio.run(test_beat_sheet_generation_e2e())
