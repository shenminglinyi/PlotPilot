import asyncio
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from typing import Dict, Any

router = APIRouter()

@router.post("/novels/{novel_id}/setup/generate-launch-contract")
async def mock_generate_launch_contract(novel_id: str, request: Request) -> Dict[str, Any]:
    return {
        "status": "success",
        "message": "Mock Launch Contract Generated Successfully",
        "novel_id": novel_id,
        "contract": {
            "title": "测试小说名称",
            "premise": "这是本地前端交互测试用的假简介",
            "genre": "测试赛道"
        }
    }

@router.post("/outline/artifacts")
async def mock_post_outline_artifacts(request: Request) -> Dict[str, Any]:
    return {
        "status": "success",
        "artifact": {
            "id": "mock_artifact_001",
            "novel_id": "novel-1780805369603",
            "scope_type": "novel",
            "scope_ref": "global",
            "kind": "detail_outline",
            "status": "confirmed",
            "payload": {
                "outline_tree": []
            },
            "source": "mock",
            "source_task_id": "mock",
            "parent_artifact_ids": [],
            "input_fingerprint": "mock",
            "version": 1,
            "created_at": "2026-06-07T15:00:00Z",
            "updated_at": "2026-06-07T15:00:00Z",
            "confirmed_at": "2026-06-07T15:00:00Z"
        }
    }

@router.get("/outline/artifacts")
async def mock_get_outline_artifacts(request: Request) -> Dict[str, Any]:
    """Mock endpoint for getting outline artifacts. Returns rich dummy data."""
    # 获取查询参数，判断是否需要过滤
    return {
        "status": "success",
        "artifacts": [
            {
                "id": "mock_detail_outline_1",
                "novel_id": "novel-1780805369603",
                "scope_type": "novel",
                "scope_ref": "global",
                "kind": "detail_outline",
                "status": "confirmed",
                "payload": {
                    "outline_tree": [
                        {
                            "id": "mock-act-1",
                            "node_type": "act",
                            "title": "第一幕：深海危机",
                            "summary": "主角卷入深海异变的漩涡",
                            "children": [
                                {
                                    "id": "mock-chapter-1",
                                    "node_type": "chapter",
                                    "title": "第一章：深海信号",
                                    "summary": "收到神秘电波",
                                    "chapter_number": 1,
                                    "word_count": 0,
                                    "status": "draft",
                                    "children": [
                                        {
                                            "id": "mock-beat-1",
                                            "node_type": "beat",
                                            "title": "探测仪异响",
                                            "summary": "探测仪发出刺耳警报，数据异常",
                                            "children": []
                                        },
                                        {
                                            "id": "mock-beat-2",
                                            "node_type": "beat",
                                            "title": "破译信号",
                                            "summary": "主角连夜破译，发现是某种古老语言",
                                            "children": []
                                        }
                                    ]
                                },
                                {
                                    "id": "mock-chapter-2",
                                    "node_type": "chapter",
                                    "title": "第二章：迷雾重重",
                                    "summary": "调查队下潜遭遇未知生物",
                                    "chapter_number": 2,
                                    "word_count": 0,
                                    "status": "draft",
                                    "children": []
                                }
                            ]
                        }
                    ]
                },
                "source": "user",
                "source_task_id": "none",
                "parent_artifact_ids": [],
                "input_fingerprint": "mock_fingerprint",
                "version": 1,
                "created_at": "2026-06-07T00:00:00Z",
                "updated_at": "2026-06-07T00:00:00Z",
                "confirmed_at": "2026-06-07T00:00:00Z"
            }
        ]
    }

@router.get("/writing/jobs")
async def mock_writing_jobs(request: Request) -> Dict[str, Any]:
    """Mock endpoint for checking writing jobs status. Returns some fake running jobs."""
    return {
        "status": "success",
        "message": "Mock Jobs Retrieved",
        "jobs": [
            {
                "id": "job-1001",
                "novel_id": "novel-1780805369603",
                "chapter_number": 1,
                "contract_id": "contract-001",
                "status": "writing",
                "manuscript_chapter_id": "",
                "started_at": "2026-06-07T07:00:00Z",
                "completed_at": "",
                "error_message": "",
                "created_at": "2026-06-07T07:00:00Z",
                "updated_at": "2026-06-07T07:15:00Z"
            }
        ],
        "items": []
    }

@router.get("/planning/novels/{novel_id}/chapter-segment-progress")
async def mock_chapter_segment_progress(novel_id: str, request: Request) -> Dict[str, Any]:
    """Mock endpoint for checking chapter segment progress."""
    return {
        "success": True,
        "status": "success",
        "novel_id": novel_id,
        "progress": [
            {
                "source_event_flow_artifact_id": "",
                "id": "seg1",
                "status": "completed",
                "label": "环境渲染",
                "chapter_id": "mock-chapter-1",
                "segment_id": "mock-beat-1"
            },
            {
                "source_event_flow_artifact_id": "",
                "id": "seg2",
                "status": "writing",
                "label": "角色对话",
                "chapter_id": "mock-chapter-1",
                "segment_id": "mock-beat-2"
            }
        ]
    }

@router.get("/novels/{novel_id}/governance/state")
async def mock_governance_state(novel_id: str, request: Request) -> Dict[str, Any]:
    return {
        "contract": {
            "novel_id": novel_id,
            "title_promise": "测试书名承诺：主角必定无敌",
            "core_question": "主角能否在不暴露身份的情况下拯救世界？",
            "theme_anchors": ["隐藏实力", "幕后黑手", "反差感"],
            "forbidden_early_payoffs": ["终极反派的真实身份", "主角师傅的下落"],
            "reveal_budget": {},
            "updated_at": "2026-06-07T00:00:00Z"
        },
        "canonical_storylines": [
            {
                "canonical_id": "line-1",
                "title": "寻找失落遗迹",
                "aliases": ["遗迹主线"],
                "goal": "找到并开启海底神殿",
                "conflict": "竞争对手也在抢夺钥匙",
                "span": {"start_chapter": 1, "end_chapter": None},
                "promise_tags": ["探险", "解密"],
                "status": "active"
            }
        ],
        "open_debts": [
            {
                "debt_id": "debt-1",
                "title": "师傅留下的锦囊",
                "description": "第一章提到师傅留下了一个锦囊，目前尚未打开。",
                "status": "open"
            }
        ],
        "latest_report": None,
        "chapter_budget_preview": {
            "novel_id": novel_id,
            "chapter_number": 1,
            "max_new_storylines": 2,
            "max_debt_closures": 1,
            "allowed_reveal_level": "hint",
            "must_serve_promise_tags": ["探险"],
            "carry_over_debt_ids": ["debt-1"],
            "notes": ["这是 Mock 数据，用于前端布局测试"]
        }
    }

@router.get("/planning/novels/{novel_id}/detail-outline/stream")
@router.get("/planning/novels/{novel_id}/detail-outline/stream/")
async def mock_detail_outline_stream(novel_id: str):
    """Mock SSE stream for detail outline generation."""
    async def event_generator():
        yield 'event: status\ndata: {"status": "starting", "message": "正在连接大模型生成细纲..."}\n\n'
        await asyncio.sleep(0.5)
        
        # 模拟打字效果
        mock_text = "第一幕：深海危机\n\n主角在一次深海勘探任务中，接收到了一段不属于人类频率的神秘电波。这不仅仅是一段电波，这是来自深海古老遗迹的呼唤，它将彻底改变整个漂浮城市的命运，也将彻底揭开主角尘封的记忆和身世之谜。\n"
        for i in range(len(mock_text)):
            # 避开内部的回车，转换成字符串的实际打字效果如果需要
            char = mock_text[i]
            if char == '\n':
                char = '\\n'
            yield f'event: chunk\ndata: {{"text": "{char}"}}\n\n'
            await asyncio.sleep(0.02)
            
        yield 'event: status\ndata: {"status": "saving", "message": "生成完毕，正在保存产物..."}\n\n'
        await asyncio.sleep(0.5)
        
        # 返回正确格式的 DetailOutlineDoneEvent
        yield 'event: done\ndata: {"detail_outline": "第一幕：深海危机\\n\\n主角在一次深海勘探任务中，接收到了一段不属于人类频率的神秘电波。这不仅仅是一段电波，这是来自深海古老遗迹的呼唤，它将彻底改变整个漂浮城市的命运，也将彻底揭开主角尘封的记忆和身世之谜。", "artifact_id": "mock_detail_outline_1", "generation_time": 1.5}\n\n'

    return StreamingResponse(event_generator(), media_type="text/event-stream")

@router.post("/autopilot/{novel_id}/global/start")
async def mock_autopilot_global_start(novel_id: str, request: Request) -> Dict[str, Any]:
    """Mock endpoint for starting the global autopilot."""
    return {
        "success": True,
        "message": "Autopilot started globally (Mock)",
        "run": {
            "run_id": "mock_run_001",
            "novel_id": novel_id,
            "status": "running",
            "started_at": "2026-06-07T00:00:00Z"
        }
    }

@router.post("/novels/{novel_id}/setup/generate-setup-blueprint")
async def mock_generate_setup_blueprint(novel_id: str, request: Request) -> Dict[str, Any]:
    """Mock endpoint for generating setup blueprint (new feature)."""
    return {
        "status": "success",
        "message": "Mock Setup Blueprint Generated",
        "setup_blueprint": {
            "worldview": "这是一个由深海巨兽统治的末日水世界，人类生存在由巨轮拼接而成的漂浮城市废墟上。",
            "storyBackground": "三百年前海平面突然上升，淹没了所有大陆...",
            "mapCurrency": "旧世界遗留的高纯度净水和电子芯片作为主要流通货币",
            "characterDesign": "主角性格冷酷、杀伐果断，但内心深处保留着对旧世界人类文明的向往",
            "powerSystem": "人类通过植入深海巨兽的神经节来获取超能力（基因觉醒）",
            "cheatAbility": "主角拥有一颗可以直接破译古老高维信号的神秘核心（独家金手指）"
        },
        "book_anchor": {
            "core_question": "主角能否解开深海信号背后的真相并重建陆地？",
            "theme_anchors": ["末世求生", "巨兽机甲", "基因进化"],
            "target_chapters": 100
        }
    }


@router.post('/novels/{novel_id}/setup/generate-book-anchor')
async def mock_generate_book_anchor(novel_id: str, request: Request):
    return {
        'status': 'success',
        'book_anchor': {
            'title': '深海之渊：机甲觉醒',
            'genreLabel': '科幻末世',
            'worldPreset': '深海废土',
            'audience': '硬核科幻迷',
            'blurb': '在漂浮城市濒临崩溃的前夕，一名底层的拾荒者意外唤醒了深海中的远古机甲，从此踏上了重塑世界秩序的征途。'
        }
    }

@router.post('/novels/{novel_id}/setup/generate-main-plot-draft')
async def mock_generate_main_plot_draft(novel_id: str, request: Request):
    return {
        'status': 'success',
        'main_plot_draft': '主角从底层拾荒者开始，意外获得金手指后，逐步揭开水世界的阴谋，最终率领幸存者战胜深海巨兽，找到传说中的干涸陆地。',
        'outline_stage_plan': [
            {
                'title': '底层觉醒',
                'stage': '起步',
                'percentage_range': '0%-20%',
                'summary': '主角在贫民窟中苟延残喘，意外融合了深海核心，获得初级超能力，并引起了统治阶级的注意。',
                'story_line': '发现核心 -> 逃避追杀 -> 初显锋芒',
                'growth_line': '从懦弱怕事到敢于反抗',
                'worldbuilding_stage': '展示下层甲板的残酷生存法则',
                'stage_goal': '存活并掌握初级能力',
                'core_conflict': '底层人民与财阀执政官的生存资源争夺',
                'causal_input': '贫民窟遭遇清洗',
                'causal_output': '主角觉醒并逃离',
                'expected_chapters': 20
            },
            {
                'title': '深渊启航',
                'stage': '发展',
                'percentage_range': '20%-100%',
                'summary': '主角组建小队，向深海遗迹发起冲击。',
                'story_line': '组建团队 -> 遭遇海兽 -> 发现真相',
                'growth_line': '领袖气质的觉醒',
                'worldbuilding_stage': '揭开被淹没的旧日世界遗迹',
                'stage_goal': '寻找失落的大陆坐标',
                'core_conflict': '探索队与海洋变异生物的死战',
                'causal_input': '破解旧日密码',
                'causal_output': '抵达最终遗迹',
                'expected_chapters': 80
            }
        ]
    }



@router.post('/planning/novels/{novel_id}/detail-outline/event-flow/stream{path:path}')
async def mock_event_flow_stream(novel_id: str, request: Request, path: str = ''):
    import asyncio
    import json

    async def event_generator():
        yield 'event: status\ndata: {"status": "starting", "message": "准备推演事件流..."}\n\n'
        await asyncio.sleep(0.5)

        yield 'event: status\ndata: {"status": "generating", "message": "正在生成事件..."}\n\n'

        events = [
            {
                'id': 'event_01',
                'title': '废土拾荒',
                'stage': '起步',
                'summary': '主角在下层甲板拾荒，发现神秘机甲残骸',
                'story_line': '发现残骸 -> 遭遇保安 -> 成功逃脱',
                'growth_line': '艰难求生',
                'worldbuilding_stage': '下层贫民窟',
                'stage_goal': '获取生存资源',
                'core_conflict': '拾荒者与帮派争夺',
                'causal_input': '缺水',
                'causal_output': '发现残骸'
            },
            {
                'id': 'event_02',
                'title': '机甲初启',
                'stage': '起步',
                'summary': '主角的血液意外激活了残骸中的核心',
                'story_line': '激活核心 -> 身体异变 -> 掌握初级战力',
                'growth_line': '获得自保之力',
                'worldbuilding_stage': '旧世界科技展露一角',
                'stage_goal': '融合核心',
                'core_conflict': '帮派追杀',
                'causal_input': '残骸启动',
                'causal_output': '获得能力'
            }
        ]

        for e in events:
            yield 'event: event\ndata: {}\n\n'.format(json.dumps(e, ensure_ascii=False))
            yield 'event: chunk\ndata: {{"text": "\n推演事件：{}..."}}\n\n'.format(e['title'])
            await asyncio.sleep(0.8)

        done_data = {'events': events, 'stages': events, 'artifact_id': 'mock_event_flow'}
        yield 'event: done\ndata: {}\n\n'.format(json.dumps(done_data, ensure_ascii=False))

    from fastapi.responses import StreamingResponse
    return StreamingResponse(event_generator(), media_type='text/event-stream')

@router.post('/planning/novels/{novel_id}/chapter-segments/publish')
async def mock_publish_chapter_segment(novel_id: str, request: Request):
    return {
        'success': True,
        'created_nodes': 3,
        'created_acts': 1,
        'created_chapters': 1,
        'published_jobs': [
            {
                'chapter_number': 1,
                'contract_id': 'mock-contract-001',
                'job_id': 'job-1002',
                'created': True
            }
        ],
        'selected_event_ids': ['event_01', 'event_02'],
        'message': '章节发布成功，写作任务已进入调度队列'
    }

@router.post('/planning/novels/{novel_id}/chapter-segments/pending')
async def mock_pending_chapter_segment(novel_id: str, request: Request):
    return {
        'success': True,
        'message': '进度已暂存',
        'saved_event_ids': []
    }
