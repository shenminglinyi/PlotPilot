# Story Studio Pipeline Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the phase-one Story Studio Pipeline: chapter contract, scene-package show-don't-tell fields, prompt injection, scene-budget execution, and editorial review `showing` score.

**Architecture:** Extend the existing `AutoNovelGenerationWorkflow` and generation API contracts without adding new database tables. Keep the normal generation button intact: strategy preview returns richer data, generation consumes it through existing `chapter_strategy`, and editorial review adds one score dimension while remaining backward compatible.

**Tech Stack:** Python 3.12, FastAPI, Pydantic, pytest, Vue 3 + TypeScript + Naive UI, existing PP workflow and LLM routing.

---

## Scope

Included:

- `chapter_contract` in strategy preview.
- Scene package fields: `visible_action`, `subtext_dialogue`, `unspoken_emotion`, `object_or_clue_change`.
- A reusable "展示优先写作协议" prompt block.
- Strategy overlay and scene-budget overlay include show-don't-tell constraints.
- Editorial review adds `showing` score.
- Frontend types and review score display support the new fields.

Not included:

- Multi-candidate generation.
- Candidate selector.
- Local reroll.
- Long-draft splitting improvements.
- New persistent tables.

## File Map

Modify:

- `application/workflows/auto_novel_generation_workflow.py`
  - Add show-don't-tell protocol helper.
  - Expand strategy prompt JSON contract.
  - Normalize `chapter_contract` and scene package fields.
  - Inject richer strategy/scene overlays into generation prompts.
  - Add editorial review `showing` score.
- `interfaces/api/v1/engine/generation.py`
  - Add Pydantic response models for chapter contract and scene package fields.
  - Add `showing` to editorial review scores.
- `frontend/src/api/workflow.ts`
  - Add TypeScript fields.
- `frontend/src/components/workbench/WorkArea.vue`
  - Display new `showing` score automatically through existing score grid.
  - Update score label helper.
- `tests/unit/application/workflows/test_auto_novel_generation_workflow.py`
  - Unit tests for normalization, overlays, and editorial score.
- `tests/integration/interfaces/api/v1/test_generation_api.py`
  - API contract tests for strategy preview and editorial review.

Optional docs update if implementation changes user-visible behavior:

- `docs/NOVELPRO_README.md`

---

## Task 1: Backend strategy payload supports chapter contract

**Files:**

- Modify: `tests/unit/application/workflows/test_auto_novel_generation_workflow.py`
- Modify: `application/workflows/auto_novel_generation_workflow.py`

- [ ] **Step 1: Add failing unit test for `chapter_contract` normalization**

Add this test near the existing strategy tests:

```python
def test_normalize_strategy_payload_includes_chapter_contract(self, workflow):
    payload = workflow._normalize_strategy_payload(
        {
            "chapter_contract": {
                "chapter_question": "灰卡为什么还能刷开门禁？",
                "protagonist_want": "白雨翔要确认 774 写卡器是否被截留。",
                "opposition": "许照只交出部分证据。",
                "reader_expectation": "看到两个人从对抗到有限合作。",
                "required_information_change": "签收记录从嫌疑证据变成伪造证据。",
                "required_relationship_change": "白雨翔和许照互相保留但开始交换证据。",
                "ending_question": "操盘者是否借用了内部审计流程？",
                "show_dont_tell_rules": [
                    "不能写白雨翔感到怀疑，只能写他追问和扣住证物。",
                    "对白不能每句完整回答，允许反问和避重就轻。",
                ],
            },
            "scene_plan": [
                {
                    "label": "核对签收单",
                    "task": "逼出 774 的异常入库记录",
                    "resistance": "许照不给完整文件",
                    "info_shift": "扫描件的模糊签名变成疑点",
                    "relationship_shift": "两人从互相试探进入有限合作",
                    "anchor": "证物袋和灰卡划痕",
                    "hook": "签名不属于当前习惯",
                    "target_words": 900,
                    "visible_action": "白雨翔把证物袋封口按住，不让许照立刻收走。",
                    "subtext_dialogue": "表面问流程，实际确认许照掌握多少证据。",
                    "unspoken_emotion": "怀疑和防备不能直说。",
                    "object_or_clue_change": "灰卡从拾获物变成伪造链条证据。",
                }
            ],
            "writing_focus": ["少解释，多用动作和证物推进。"],
        },
        outline="白雨翔追查灰卡。",
        target_word_count=2500,
        word_tolerance_ratio=0.05,
    )

    contract = payload["chapter_contract"]
    assert contract["chapter_question"] == "灰卡为什么还能刷开门禁？"
    assert "扣住证物" in contract["show_dont_tell_rules"][0]

    scene = payload["scene_plan"][0]
    assert scene["visible_action"].startswith("白雨翔把证物袋")
    assert scene["subtext_dialogue"].startswith("表面问流程")
    assert scene["unspoken_emotion"] == "怀疑和防备不能直说。"
    assert scene["object_or_clue_change"].startswith("灰卡从拾获物")
```

- [ ] **Step 2: Run the test and verify it fails**

Run:

```bash
uv run pytest -q tests/unit/application/workflows/test_auto_novel_generation_workflow.py -k "chapter_contract"
```

Expected: fails with missing `chapter_contract` or missing scene fields.

- [ ] **Step 3: Implement strategy normalization**

In `application/workflows/auto_novel_generation_workflow.py`, add helper methods near `_normalize_strategy_payload`:

```python
    @staticmethod
    def _clean_text(value: Any, fallback: str) -> str:
        text = str(value or "").strip()
        return text or fallback

    @staticmethod
    def _clean_text_list(value: Any, fallback: List[str], *, limit: int = 4) -> List[str]:
        if isinstance(value, list):
            cleaned = [str(item).strip() for item in value if str(item).strip()]
            if cleaned:
                return cleaned[:limit]
        return fallback[:limit]
```

Then in `_normalize_strategy_payload`, before `return`, build:

```python
        raw_contract = data.get("chapter_contract") if isinstance(data.get("chapter_contract"), dict) else {}
        chapter_contract = {
            "chapter_question": AutoNovelGenerationWorkflow._clean_text(
                raw_contract.get("chapter_question"),
                "本章的关键问题必须在具体行动中被推进。",
            ),
            "protagonist_want": AutoNovelGenerationWorkflow._clean_text(
                raw_contract.get("protagonist_want"),
                dramatic.get("goal") or outline[:36] or "主角要确认一条关键线索。",
            ),
            "opposition": AutoNovelGenerationWorkflow._clean_text(
                raw_contract.get("opposition"),
                dramatic.get("obstacle") or "有人或流程阻碍主角。",
            ),
            "reader_expectation": AutoNovelGenerationWorkflow._clean_text(
                raw_contract.get("reader_expectation"),
                dramatic.get("reader_expectation") or "读者要看到冲突推进，而不是解释背景。",
            ),
            "required_information_change": AutoNovelGenerationWorkflow._clean_text(
                raw_contract.get("required_information_change"),
                "至少交付一条会改变判断的新信息。",
            ),
            "required_relationship_change": AutoNovelGenerationWorkflow._clean_text(
                raw_contract.get("required_relationship_change"),
                "至少让主要人物的立场或信任关系发生细微变化。",
            ),
            "ending_question": AutoNovelGenerationWorkflow._clean_text(
                raw_contract.get("ending_question"),
                dramatic.get("ending_hook") or "章末留下新的追问。",
            ),
            "show_dont_tell_rules": AutoNovelGenerationWorkflow._clean_text_list(
                raw_contract.get("show_dont_tell_rules"),
                [
                    "不能直接命名复杂情绪，必须写动作、停顿、回避或身体反应。",
                    "不能用总结句跳过冲突过程，必须让读者看到试探和阻力。",
                    "对白不能每句都完整礼貌，允许打断、反问、答非所问。",
                ],
                limit=5,
            ),
        }
```

In each normalized scene dict, add:

```python
                "visible_action": AutoNovelGenerationWorkflow._clean_text(
                    item.get("visible_action"),
                    str(item.get("anchor") or "用一个具体动作承载情绪和信息。"),
                ),
                "subtext_dialogue": AutoNovelGenerationWorkflow._clean_text(
                    item.get("subtext_dialogue"),
                    "对白表面推进事实，底层保留试探、遮掩或误判。",
                ),
                "unspoken_emotion": AutoNovelGenerationWorkflow._clean_text(
                    item.get("unspoken_emotion"),
                    "不要直接命名情绪，用动作和反应表现。",
                ),
                "object_or_clue_change": AutoNovelGenerationWorkflow._clean_text(
                    item.get("object_or_clue_change"),
                    "本场景至少让一个线索、道具或判断发生变化。",
                ),
```

In fallback scenes, add the same four keys with concrete fallback strings.

Finally include `chapter_contract` in the returned dict:

```python
            "chapter_contract": chapter_contract,
```

- [ ] **Step 4: Run the test and verify it passes**

Run:

```bash
uv run pytest -q tests/unit/application/workflows/test_auto_novel_generation_workflow.py -k "chapter_contract"
```

Expected: selected test passes.

- [ ] **Step 5: Commit**

```bash
git add application/workflows/auto_novel_generation_workflow.py tests/unit/application/workflows/test_auto_novel_generation_workflow.py
git commit -m "feat: add chapter contract strategy payload"
```

---

## Task 2: Strategy prompt requests show-don't-tell fields

**Files:**

- Modify: `tests/unit/application/workflows/test_auto_novel_generation_workflow.py`
- Modify: `application/workflows/auto_novel_generation_workflow.py`

- [ ] **Step 1: Add failing unit test for strategy prompt schema**

Add:

```python
def test_build_strategy_prompt_requests_show_dont_tell_contract(self, workflow):
    prompt = workflow._build_strategy_prompt(
        context="CTX",
        outline="白雨翔追查灰卡。",
        target_word_count=2500,
        word_tolerance_ratio=0.05,
    )

    assert "chapter_contract" in prompt.system
    assert "show_dont_tell_rules" in prompt.system
    assert "visible_action" in prompt.system
    assert "subtext_dialogue" in prompt.system
    assert "unspoken_emotion" in prompt.system
    assert "object_or_clue_change" in prompt.system
    assert "少解释，多展示" in prompt.system
```

- [ ] **Step 2: Run the test and verify it fails**

Run:

```bash
uv run pytest -q tests/unit/application/workflows/test_auto_novel_generation_workflow.py -k "strategy_prompt_requests"
```

Expected: fails because prompt schema does not include the new fields.

- [ ] **Step 3: Update `_build_strategy_prompt`**

Replace the JSON structure section inside `_build_strategy_prompt` with a schema containing:

```text
{
  "chapter_contract": {
    "chapter_question": "本章读者最想知道的问题",
    "protagonist_want": "主角最具体想拿到/确认/避免什么",
    "opposition": "谁或什么阻碍他",
    "reader_expectation": "读者期待看到的具体场面",
    "required_information_change": "本章必须交付的信息变化",
    "required_relationship_change": "本章必须发生的人物关系变化",
    "ending_question": "章末留下的追问",
    "show_dont_tell_rules": ["本章禁止直说的情绪/动机/解释，改用动作、停顿、物件、对白表现"]
  },
  "dramatic_task": {
    "goal": "角色这章最具体想拿到/确认/隐瞒什么",
    "obstacle": "谁或什么阻碍他",
    "reader_expectation": "读者这一章最期待看到什么兑现",
    "ending_hook": "章末要留下什么追读钩子"
  },
  "scene_plan": [
    {
      "label": "场景标题",
      "task": "这个场景的任务",
      "resistance": "阻力",
      "info_shift": "新信息或局势变化",
      "relationship_shift": "人物关系变化，没有就写无明显变化",
      "anchor": "一个具体物件/动作/地点锚点",
      "visible_action": "必须出现的具体动作",
      "subtext_dialogue": "对白表面内容和真实意图",
      "unspoken_emotion": "不能直说的情绪",
      "object_or_clue_change": "道具或线索状态变化",
      "hook": "场景结尾钩子",
      "target_words": 800
    }
  ],
  "writing_focus": ["3-4 条执行提醒"]
}
```

Add to hard requirements:

```text
6. 展示优先：少解释，多展示；少总结，多动作和细节；少金句，多具体反应。
7. 不要直接写“复杂情绪”，必须要求正文通过动作、停顿、回避、物件处理来表现。
8. 对话不要每句都完整、礼貌、逻辑闭环；允许打断、反问、避重就轻。
```

- [ ] **Step 4: Run the test and verify it passes**

Run:

```bash
uv run pytest -q tests/unit/application/workflows/test_auto_novel_generation_workflow.py -k "strategy_prompt_requests"
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add application/workflows/auto_novel_generation_workflow.py tests/unit/application/workflows/test_auto_novel_generation_workflow.py
git commit -m "feat: request showing-first strategy fields"
```

---

## Task 3: Generation overlays enforce showing-first execution

**Files:**

- Modify: `tests/unit/application/workflows/test_auto_novel_generation_workflow.py`
- Modify: `application/workflows/auto_novel_generation_workflow.py`

- [ ] **Step 1: Add failing overlay tests**

Add:

```python
def test_build_strategy_overlay_includes_show_dont_tell_contract(self, workflow):
    overlay = workflow._build_strategy_overlay(
        {
            "chapter_contract": {
                "chapter_question": "灰卡是谁写入的？",
                "protagonist_want": "白雨翔要确认写卡器来源。",
                "opposition": "许照只给半份证据。",
                "reader_expectation": "看到两人互相试探。",
                "required_information_change": "伪造签名暴露。",
                "required_relationship_change": "形成有限合作。",
                "ending_question": "谁借用了审计流程？",
                "show_dont_tell_rules": ["不能写他感到怀疑，只能写他扣住证物。"],
            },
            "dramatic_task": {
                "goal": "确认写卡器来源",
                "obstacle": "许照保留证据",
                "reader_expectation": "看到试探",
                "ending_hook": "审计流程异常",
            },
            "scene_plan": [],
            "writing_focus": [],
        }
    )

    assert "章节合同" in overlay
    assert "灰卡是谁写入的" in overlay
    assert "展示优先" in overlay
    assert "扣住证物" in overlay


def test_build_scene_budget_overlay_includes_showing_fields(self, workflow):
    overlay = workflow._build_scene_budget_overlay(
        {
            "label": "核对签收单",
            "task": "确认签名真伪",
            "resistance": "许照不交原件",
            "info_shift": "签名疑点出现",
            "relationship_shift": "有限合作",
            "anchor": "证物袋",
            "visible_action": "白雨翔按住证物袋封口。",
            "subtext_dialogue": "表面问流程，实际逼许照露底。",
            "unspoken_emotion": "怀疑不能直说。",
            "object_or_clue_change": "灰卡变成伪造链条证据。",
            "hook": "审计流程异常",
            "target_words": 800,
            "min_words": 720,
            "max_words": 880,
        }
    )

    assert "白雨翔按住证物袋封口" in overlay
    assert "表面问流程" in overlay
    assert "怀疑不能直说" in overlay
    assert "灰卡变成伪造链条证据" in overlay
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```bash
uv run pytest -q tests/unit/application/workflows/test_auto_novel_generation_workflow.py -k "show_dont_tell_contract or showing_fields"
```

Expected: fails before overlay implementation.

- [ ] **Step 3: Update `_resolve_scene_budget_plan` and `_build_scene_budget_overlay`**

In `_resolve_scene_budget_plan`, copy these keys into each normalized scene:

```python
            visible_action = str(item.get("visible_action") or item.get("anchor") or "用具体动作推进").strip() or "用具体动作推进"
            subtext_dialogue = str(item.get("subtext_dialogue") or "对白必须有试探、遮掩或信息差").strip() or "对白必须有试探、遮掩或信息差"
            unspoken_emotion = str(item.get("unspoken_emotion") or "情绪不能直说").strip() or "情绪不能直说"
            object_or_clue_change = str(item.get("object_or_clue_change") or "线索或道具状态必须变化").strip() or "线索或道具状态必须变化"
```

Add to the scene dict:

```python
                    "visible_action": visible_action,
                    "subtext_dialogue": subtext_dialogue,
                    "unspoken_emotion": unspoken_emotion,
                    "object_or_clue_change": object_or_clue_change,
```

In `_build_scene_budget_overlay`, read these keys and append lines:

```python
        visible_action = str(scene_hint.get("visible_action") or "用具体动作推进").strip() or "用具体动作推进"
        subtext_dialogue = str(scene_hint.get("subtext_dialogue") or "对白保留潜台词").strip() or "对白保留潜台词"
        unspoken_emotion = str(scene_hint.get("unspoken_emotion") or "情绪不能直说").strip() or "情绪不能直说"
        object_or_clue_change = str(scene_hint.get("object_or_clue_change") or "线索或道具状态变化").strip() or "线索或道具状态变化"
```

Add lines in the returned block:

```python
            f"- 可见动作：{visible_action}\n"
            f"- 潜台词对白：{subtext_dialogue}\n"
            f"- 未说出口的情绪：{unspoken_emotion}\n"
            f"- 道具/线索变化：{object_or_clue_change}\n"
```

- [ ] **Step 4: Update `_build_strategy_overlay`**

At the start of `_build_strategy_overlay`, read:

```python
        contract = chapter_strategy.get("chapter_contract") or {}
```

After `lines = ["【本章写作策略（已确认，必须执行）】"]`, add:

```python
        if isinstance(contract, dict) and contract:
            lines.extend([
                "章节合同：",
                f"- 本章问题：{str(contract.get('chapter_question') or '未说明').strip()}",
                f"- 主角想要：{str(contract.get('protagonist_want') or '未说明').strip()}",
                f"- 阻力来源：{str(contract.get('opposition') or '未说明').strip()}",
                f"- 信息变化：{str(contract.get('required_information_change') or '未说明').strip()}",
                f"- 关系变化：{str(contract.get('required_relationship_change') or '未说明').strip()}",
                f"- 章末追问：{str(contract.get('ending_question') or '未说明').strip()}",
                "展示优先：",
            ])
            rules = contract.get("show_dont_tell_rules") if isinstance(contract.get("show_dont_tell_rules"), list) else []
            for rule in rules[:5]:
                text = str(rule or "").strip()
                if text:
                    lines.append(f"- {text}")
```

In the scene line, include `visible_action`, `subtext_dialogue`, and `unspoken_emotion`:

```python
                visible_action = str(scene.get("visible_action") or scene.get("anchor") or "未说明").strip()
                subtext_dialogue = str(scene.get("subtext_dialogue") or "未说明").strip()
                unspoken_emotion = str(scene.get("unspoken_emotion") or "未说明").strip()
                clue_change = str(scene.get("object_or_clue_change") or "未说明").strip()
                lines.append(
                    f"{index}. {title}｜任务：{task}｜阻力：{resistance}｜变化：{info_shift}｜关系：{relation_shift}｜动作：{visible_action}｜潜台词：{subtext_dialogue}｜不直说：{unspoken_emotion}｜线索/道具：{clue_change}｜钩子：{hook}"
                )
```

- [ ] **Step 5: Run tests and verify they pass**

Run:

```bash
uv run pytest -q tests/unit/application/workflows/test_auto_novel_generation_workflow.py -k "show_dont_tell_contract or showing_fields"
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add application/workflows/auto_novel_generation_workflow.py tests/unit/application/workflows/test_auto_novel_generation_workflow.py
git commit -m "feat: inject showing-first scene overlays"
```

---

## Task 4: Editorial review returns `showing` score

**Files:**

- Modify: `tests/unit/application/workflows/test_auto_novel_generation_workflow.py`
- Modify: `application/workflows/auto_novel_generation_workflow.py`
- Modify: `interfaces/api/v1/engine/generation.py`
- Modify: `frontend/src/api/workflow.ts`
- Modify: `frontend/src/components/workbench/WorkArea.vue`

- [ ] **Step 1: Add failing workflow test**

Add:

```python
def test_normalize_editorial_review_payload_includes_showing_score(self, workflow):
    payload = workflow._normalize_editorial_review_payload(
        {
            "summary": "对白有张力，但解释略多。",
            "scores": {
                "opening": 88,
                "conflict": 90,
                "character": 86,
                "dialogue": 84,
                "hook": 92,
                "pacing": 87,
                "showing": 79,
            },
            "strengths": ["证物动作具体。"],
            "problems": ["部分情绪仍被直接命名。"],
            "actions": ["把解释改成动作。"],
            "verdict": "可优化后使用",
        }
    )

    assert payload["scores"]["showing"] == 79
```

- [ ] **Step 2: Run test and verify failure**

Run:

```bash
uv run pytest -q tests/unit/application/workflows/test_auto_novel_generation_workflow.py -k "showing_score"
```

Expected: fails because `showing` is not returned.

- [ ] **Step 3: Update editorial prompt and normalizer**

In `_build_editorial_review_prompt`, update JSON schema scores:

```text
    "showing": 0-100
```

Add scoring rule:

```text
- showing：是否少解释、多展示；情绪是否通过动作/细节/潜台词表现；对白是否避免完整礼貌闭环
```

Add review instruction:

```text
展示优先专项检查：
- 扣解释句过密、总结句替代场景、直接命名情绪。
- 扣客服式完整对白和段尾金句。
- 修改动作必须说明如何把解释改成动作或潜台词。
```

In `_normalize_editorial_review_payload`, add:

```python
                "showing": score_of("showing"),
```

- [ ] **Step 4: Update API response model**

In `interfaces/api/v1/engine/generation.py`, add to `ChapterEditorialReviewScoresResponse`:

```python
    showing: int = Field(0, description="展示优先：少解释、多动作细节、潜台词对白")
```

If current class does not use `Field`, add it consistently with existing import already present.

- [ ] **Step 5: Update frontend types and score label**

In `frontend/src/api/workflow.ts`, add:

```ts
  showing: number
```

to `ChapterEditorialReviewScoresDTO`.

In `frontend/src/components/workbench/WorkArea.vue`, find `editorialScoreLabel`. Add mapping:

```ts
  showing: '展示'
```

If the helper uses a switch, add:

```ts
case 'showing':
  return '展示'
```

- [ ] **Step 6: Run targeted backend tests**

Run:

```bash
uv run pytest -q tests/unit/application/workflows/test_auto_novel_generation_workflow.py -k "showing_score"
```

Expected: PASS.

- [ ] **Step 7: Run frontend type/build check**

Run:

```bash
cd frontend && npm run build
```

Expected: build exits 0.

- [ ] **Step 8: Commit**

```bash
git add application/workflows/auto_novel_generation_workflow.py interfaces/api/v1/engine/generation.py frontend/src/api/workflow.ts frontend/src/components/workbench/WorkArea.vue tests/unit/application/workflows/test_auto_novel_generation_workflow.py
git commit -m "feat: add showing score to editorial review"
```

---

## Task 5: API contract exposes richer strategy preview

**Files:**

- Modify: `tests/integration/interfaces/api/v1/test_generation_api.py`
- Modify: `interfaces/api/v1/engine/generation.py`
- Modify: `frontend/src/api/workflow.ts`

- [ ] **Step 1: Add integration test for response model compatibility**

In `tests/integration/interfaces/api/v1/test_generation_api.py`, add a test near strategy-preview tests:

```python
def test_strategy_preview_returns_chapter_contract_and_showing_scene_fields(self, client, mock_workflow):
    async def strategy_with_showing_fields(*args, **kwargs):
        return {
            "chapter_contract": {
                "chapter_question": "灰卡为什么能刷开门禁？",
                "protagonist_want": "白雨翔要确认写卡器来源。",
                "opposition": "许照只给半份证据。",
                "reader_expectation": "看到两人互相试探。",
                "required_information_change": "签收记录暴露伪造痕迹。",
                "required_relationship_change": "两人形成有限合作。",
                "ending_question": "谁借用了审计流程？",
                "show_dont_tell_rules": ["不能直写怀疑，只写扣住证物。"],
            },
            "dramatic_task": {
                "goal": "确认写卡器来源",
                "obstacle": "许照保留证据",
                "reader_expectation": "看到试探",
                "ending_hook": "审计流程异常",
            },
            "scene_plan": [
                {
                    "label": "核对签收单",
                    "task": "确认签名真伪",
                    "resistance": "许照不交原件",
                    "info_shift": "签名疑点出现",
                    "relationship_shift": "有限合作",
                    "anchor": "证物袋",
                    "visible_action": "白雨翔按住证物袋封口。",
                    "subtext_dialogue": "表面问流程，实际逼许照露底。",
                    "unspoken_emotion": "怀疑不能直说。",
                    "object_or_clue_change": "灰卡变成伪造链条证据。",
                    "hook": "审计流程异常",
                    "target_words": 800,
                }
            ],
            "writing_focus": ["少解释，多展示。"],
        }

    mock_workflow.generate_chapter_strategy = strategy_with_showing_fields
    response = client.post(
        "/api/v1/novels/novel-1/chapters/2/strategy-preview",
        json={"outline": "白雨翔追查灰卡。"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["chapter_contract"]["chapter_question"].startswith("灰卡")
    assert data["scene_plan"][0]["visible_action"].startswith("白雨翔")
```

- [ ] **Step 2: Run test and verify failure**

Run:

```bash
uv run pytest -q tests/integration/interfaces/api/v1/test_generation_api.py -k "strategy_preview_returns_chapter_contract"
```

Expected: fails until response models include new fields.

- [ ] **Step 3: Add Pydantic response models**

In `interfaces/api/v1/engine/generation.py`, add:

```python
class ChapterContractResponse(BaseModel):
    chapter_question: str
    protagonist_want: str
    opposition: str
    reader_expectation: str
    required_information_change: str
    required_relationship_change: str
    ending_question: str
    show_dont_tell_rules: List[str]
```

Extend `ChapterStrategySceneResponse`:

```python
    visible_action: str = ""
    subtext_dialogue: str = ""
    unspoken_emotion: str = ""
    object_or_clue_change: str = ""
```

Extend `ChapterStrategyPreviewResponse`:

```python
    chapter_contract: ChapterContractResponse
```

- [ ] **Step 4: Update frontend DTOs**

In `frontend/src/api/workflow.ts`, add:

```ts
export interface ChapterContractDTO {
  chapter_question: string
  protagonist_want: string
  opposition: string
  reader_expectation: string
  required_information_change: string
  required_relationship_change: string
  ending_question: string
  show_dont_tell_rules: string[]
}
```

Extend `ChapterStrategySceneDTO`:

```ts
  visible_action?: string
  subtext_dialogue?: string
  unspoken_emotion?: string
  object_or_clue_change?: string
```

Extend `ChapterStrategyPreviewDTO`:

```ts
  chapter_contract: ChapterContractDTO
```

- [ ] **Step 5: Run integration test**

Run:

```bash
uv run pytest -q tests/integration/interfaces/api/v1/test_generation_api.py -k "strategy_preview_returns_chapter_contract"
```

Expected: PASS.

- [ ] **Step 6: Run frontend build**

Run:

```bash
cd frontend && npm run build
```

Expected: build exits 0.

- [ ] **Step 7: Commit**

```bash
git add interfaces/api/v1/engine/generation.py frontend/src/api/workflow.ts tests/integration/interfaces/api/v1/test_generation_api.py
git commit -m "feat: expose story studio strategy contract"
```

---

## Task 6: Workbench displays chapter contract and showing score

**Files:**

- Modify: `frontend/src/components/workbench/WorkArea.vue`

- [ ] **Step 1: Add contract preview in strategy panel**

Find where `chapterStrategy` is displayed in the generation modal. Add this block above scene-plan display:

```vue
<n-alert
  v-if="chapterStrategy?.chapter_contract"
  type="info"
  title="章节合同"
  :bordered="false"
  class="chapter-contract-card"
>
  <n-space vertical :size="6">
    <n-text depth="3">本章问题：{{ chapterStrategy.chapter_contract.chapter_question }}</n-text>
    <n-text depth="3">主角想要：{{ chapterStrategy.chapter_contract.protagonist_want }}</n-text>
    <n-text depth="3">阻力来源：{{ chapterStrategy.chapter_contract.opposition }}</n-text>
    <n-text depth="3">信息变化：{{ chapterStrategy.chapter_contract.required_information_change }}</n-text>
    <n-text depth="3">章末追问：{{ chapterStrategy.chapter_contract.ending_question }}</n-text>
    <n-space vertical :size="2">
      <n-text strong depth="2">展示优先</n-text>
      <n-text
        v-for="(rule, index) in chapterStrategy.chapter_contract.show_dont_tell_rules"
        :key="`show-rule-${index}`"
        depth="3"
      >
        - {{ rule }}
      </n-text>
    </n-space>
  </n-space>
</n-alert>
```

- [ ] **Step 2: Extend scene display**

Where scene plan items are rendered, add these labels if present:

```vue
<n-text v-if="scene.visible_action" depth="3">动作：{{ scene.visible_action }}</n-text>
<n-text v-if="scene.subtext_dialogue" depth="3">潜台词：{{ scene.subtext_dialogue }}</n-text>
<n-text v-if="scene.unspoken_emotion" depth="3">不直说：{{ scene.unspoken_emotion }}</n-text>
<n-text v-if="scene.object_or_clue_change" depth="3">线索/道具：{{ scene.object_or_clue_change }}</n-text>
```

- [ ] **Step 3: Add score label fallback**

If `editorialScoreLabel` uses an object map, add:

```ts
showing: '展示',
```

If it uses a switch, add:

```ts
case 'showing':
  return '展示'
```

- [ ] **Step 4: Build frontend**

Run:

```bash
cd frontend && npm run build
```

Expected: build exits 0.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/workbench/WorkArea.vue
git commit -m "feat: show story studio contract in workbench"
```

---

## Task 7: Focused regression and smoke test

**Files:**

- No source changes unless failures identify a narrow bug.

- [ ] **Step 1: Run focused backend tests**

Run:

```bash
uv run pytest -q tests/unit/application/workflows/test_auto_novel_generation_workflow.py -k "chapter_contract or strategy_prompt_requests or show_dont_tell_contract or showing_fields or showing_score"
```

Expected: all selected tests pass.

- [ ] **Step 2: Run focused API tests**

Run:

```bash
uv run pytest -q tests/integration/interfaces/api/v1/test_generation_api.py -k "strategy_preview_returns_chapter_contract or editorial"
```

Expected: selected tests pass.

- [ ] **Step 3: Run frontend build**

Run:

```bash
cd frontend && npm run build
```

Expected: build exits 0.

- [ ] **Step 4: Restart local backend**

Run:

```bash
pkill -f "uvicorn interfaces.main:app" || true
nohup .venv/bin/python -m uvicorn interfaces.main:app --host 127.0.0.1 --port 39101 > /tmp/pp39101.log 2>&1 &
sleep 3
curl -sS -o /dev/null -w '%{http_code}\n' http://127.0.0.1:39101/openapi.json
```

Expected: prints `200`.

- [ ] **Step 5: Smoke strategy preview API**

Run:

```bash
curl -sS -X POST http://127.0.0.1:39101/api/v1/novels/test-novel-web-writing-157db1b8/chapters/2/strategy-preview \
  -H 'Content-Type: application/json' \
  -d '{"outline":"白雨翔追查灰卡，许照拿出矛盾证据。","target_word_count":900,"word_tolerance_percent":8}' \
  | python -m json.tool | sed -n '1,120p'
```

Expected: response contains `chapter_contract`, `show_dont_tell_rules`, and scene fields such as `visible_action`.

- [ ] **Step 6: Commit test/documentation adjustment if needed**

If smoke test reveals no code change, skip commit. If a narrow bug was fixed:

```bash
git add <changed-files>
git commit -m "fix: stabilize story studio phase one smoke"
```

---

## Self-Review

Spec coverage:

- Chapter contract: Task 1, Task 2, Task 5, Task 6.
- Scene package show fields: Task 1, Task 2, Task 3, Task 5, Task 6.
- Prompt injection: Task 2 and Task 3.
- Scene budget execution: Task 3 extends existing budget overlays.
- Editorial `showing` score: Task 4 and Task 6.
- No new database tables: preserved by file map.
- Candidate competition and reroll: intentionally excluded from phase one.

Placeholder scan:

- No reserved empty-slot wording is used in actionable steps.
- Every code-changing task includes concrete snippets and exact commands.

Type consistency:

- Backend uses `chapter_contract`, `show_dont_tell_rules`, `visible_action`, `subtext_dialogue`, `unspoken_emotion`, `object_or_clue_change`, and `showing`.
- Frontend DTOs use the same names.
