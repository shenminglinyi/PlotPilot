# 卷级推进与故事完结验收

## 问题与行为

原先续幕创建沿用上一幕父卷，而运行时算出的目标卷没有传入；章末达到目标章节数即写入 `completed`。现在把实际正文进度、卷级篇幅预算和证据验收汇入 `NarrativeProgressPolicy`，各运行入口共用同一规则。

- 结构节点是规划，只有状态为 completed 且非空的正文章节才能消耗预算和支持剧情证据。
- 卷预算优先取 `metadata.narrative_progress.chapter_budget`，其次取明确章节范围；缺失时按剩余目标均分，并标注为估算，不解析自然语言卷纲猜数字。
- 达到卷预算后，必达节点必须有本卷正文的有效证据，才可创建下一卷的幕。生成的新幕写入实际选中的父卷，提示词携带其任务与剩余预算，每幕章数不能超出剩余预算。
- 旧目录若已经规划了越界章节，不自动搬卷或改稿，停止继续生成并提示重规划。
- 达到全书目标后停止生成；只有各卷节点、核心冲突、主要人物去向和结局均有有效验收时，才进入 completed。否则为 stopped / paused_for_review，自动批准也不能跳过。
- 原终局没有证据时不会用短期伏笔回收率替代判断；剧情是否足够好仍由作者或审阅者判断。
- 每条验收绑定正文章节修订标识。改稿后旧证据失效，更新篇幅预算不会悄悄续签旧验收。
- StoryPipeline 的叙事阶段从实际完成进度得到，避免“写作中”始终被当成“发展期”。

## 本机隔离验收

后端支持诊断入口 `plotpilot-backend.exe --verify-narrative-progress --db <测试副本> --report <JSON报告>`；源码可用 `python scripts/verify_narrative_progress.py` 配合同样参数运行。入口要求同目录有明确的 `narrative-test-copy.json` 标记，并拒绝原数据库、同文件硬链接及放在生产数据目录中的副本。

验收先在现有长篇副本上检查篇幅已到但故事未验收的暂停行为，再创建独立合成小说检查跨卷和终局。规划回复固定，不构造联网模型；第二、第三项不是把现有稿件声明为已修完。

测试实例不能靠进程名猜测哪些后台属于“残留”。启动时不再全局枚举或结束其他 Python/PlotPilot 进程；受管子进程的停止仅由持有 Process 句柄的 AutopilotDaemonManager.stop() 负责。未知旧进程留给明确的用户操作，不因开启第二个数据目录而被误杀。

## 审阅接口

`GET /api/v1/novels/{novel_id}/structure/progress` 返回 `generation_finished`、`story_finished`、每卷预算及其来源、实际正文章号、未满足项。

`PUT /api/v1/novels/{novel_id}/structure/volumes/{volume_id}/progress` 配置该卷任务并记录验收。提交必须针对同一小说，证据须为已完成非空正文；服务在服务器侧绑定修订标识，客户端不提交该标识。

```json
{
  "chapter_budget": 80,
  "goal": "阶段危机改变人物的认识并引出下一卷选择",
  "milestones": [
    {
      "id": "phase-crisis",
      "description": "阶段危机发生且其后果进入人物选择",
      "required": true,
      "status": "resolved",
      "evidence_chapters": [36, 39, 40]
    }
  ]
}
```

只有末卷可记录 `ending_review`，含 `reviewed_through_chapter`、`core_conflict`、`character_outcomes`、`ending` 和可选 `required_promises`。后三个必填项及承诺都使用里程碑的对象形态，各自提供证据。开放式结尾可用 `open_ending_notes` 解释，但不能自动豁免已经声明必须兑现的承诺。重规划时可用 `ending_review: null` 清除过时终局验收。

仅设置目标章数、生成完毕、在正文出现某个人名，都不会自动写入“已兑现”。接口记录验收后，重新启动自动驾驶时会重新检查；不会为了确认完结而多写一章。

## 已有稿件

不自动重挂已有章节、不改写正文，不把现有“completed”静默改成另一状态。先用只读审计命令保留完整原稿，并生成结构诊断：

```powershell
python scripts/audit_narrative_progress.py --db "C:\path\plotpilot.db" --output "out\narrative-audit" --snapshot
```

随后按实际事件决定压缩重编或扩大篇幅；机械修复不能代替对现有百万字的编辑工作。源数据库不接受该命令写入。
