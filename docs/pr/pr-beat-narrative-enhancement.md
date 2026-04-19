# PR：分章叙事节拍深度适配

---

## 概览

本次改动解决分章叙事节拍（beat_sections）从「用户输入 → 持久化 → 正文生成」全链路不通的问题。

**涉及文件：** 5 个  
**变更规模：** +88 / -18

| 文件 | 变更类型 |
|---|---|
| `infrastructure/persistence/database/sqlite_knowledge_repository.py` | beat_sections 等字段持久化 |
| `application/engine/services/autopilot_daemon.py` | 注入 knowledge_service，合并 beat_sections 到 outline |
| `scripts/start_daemon.py` | Daemon 构建注入 knowledge_service |
| `interfaces/api/v1/engine/autopilot_routes.py` | 修复当前章节号推断 Bug |
| `frontend/src/components/knowledge/KnowledgePanel.vue` | 修复 addChapter NaN Bug |

---

## 背景与动机

原有实现存在两个断层：

1. **持久化断层**：`chapter_summaries` 表仅保存 `summary`，`beat_sections` / `micro_beats` / `key_events` 等字段写入时被丢弃，用户在分章叙事面板设定的节拍内容保存后即消失。

2. **生成断层**：`AutopilotDaemon` 生成章节时只读取 `outline`，从未读取 `beat_sections`，导致用户设定的节拍对正文生成完全无效。

---

## 变更详情

### 1. `infrastructure/persistence/database/sqlite_knowledge_repository.py`

**`chapter_summaries` 表写入扩展**，补全全部字段的持久化：

```diff
 conn.execute(
     """
-    INSERT INTO chapter_summaries
-    (id, knowledge_id, chapter_number, summary, created_at, updated_at)
-    VALUES (?, ?, ?, ?, ?, ?)
+    INSERT INTO chapter_summaries
+    (id, knowledge_id, chapter_number, summary, key_events, open_threads,
+     consistency_note, beat_sections, micro_beats, sync_status, created_at, updated_at)
+    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
     ON CONFLICT(knowledge_id, chapter_number) DO UPDATE SET
         summary = excluded.summary,
+        key_events        = excluded.key_events,
+        open_threads      = excluded.open_threads,
+        consistency_note  = excluded.consistency_note,
+        beat_sections     = excluded.beat_sections,
+        micro_beats       = excluded.micro_beats,
+        sync_status       = excluded.sync_status,
         updated_at = excluded.updated_at
     """,
-    (summary_id, knowledge_id, cn, chapter.summary, now, now),
+    (
+        summary_id, knowledge_id, cn,
+        chapter.summary or "",
+        getattr(chapter, "key_events", "") or "",
+        getattr(chapter, "open_threads", "") or "",
+        getattr(chapter, "consistency_note", "") or "",
+        beat_sections_json,   # JSON 序列化的 List[str]
+        micro_beats_json,     # JSON 序列化的 List[str]
+        getattr(chapter, "sync_status", "draft") or "draft",
+        now, now,
+    ),
 )
```

---

### 2. `application/engine/services/autopilot_daemon.py`

**新增 `knowledge_service` 可选依赖，生成前自动将 `beat_sections` 前置到 outline：**

```diff
 def __init__(
     self,
     ...
+    knowledge_service=None,
 ):
     ...
+    self.knowledge_service = knowledge_service
```

```diff
 chapter_num = next_chapter_node.number
 outline = next_chapter_node.outline or next_chapter_node.description or next_chapter_node.title

+# 合并分章叙事节拍（beat_sections）到 outline，让 AI 按用户设定的叙事节拍生成
+if self.knowledge_service:
+    try:
+        knowledge = self.knowledge_service.get_knowledge(novel.novel_id.value)
+        chapter_entry = next(
+            (ch for ch in knowledge.chapters if str(ch.chapter_id) == str(chapter_num)),
+            None
+        )
+        if chapter_entry and getattr(chapter_entry, "beat_sections", None):
+            beats_text = "\n".join(str(b) for b in chapter_entry.beat_sections if b)
+            if beats_text.strip():
+                outline = f"【分章叙事节拍】\n{beats_text}\n\n【章节大纲】\n{outline}"
+                logger.info(f"[{novel.novel_id}] 已合并第{chapter_num}章分章叙事节拍（{len(chapter_entry.beat_sections)}条）")
+    except Exception as _e:
+        logger.warning(f"[{novel.novel_id}] 读取分章叙事失败，使用原始大纲：{_e}")
```

---

### 3. `scripts/start_daemon.py`

**Daemon 构建时注入 `knowledge_service`：**

```diff
 return AutopilotDaemon(
     ...
+    knowledge_service=get_knowledge_service(),
 )
```

---

### 4. `interfaces/api/v1/engine/autopilot_routes.py`

**修复当前章节号推断逻辑**（`_resolve_current_chapter_number`，两处均已修复）：

**问题：** 预创建的空壳 draft 章节会被误判为「当前写入中」的章节，导致日志流显示章节号偏大。

```diff
 if drafts:
-    return max(int(c.number) for c in drafts)
+    active = [c for c in drafts if _wc(c) > 0]   # 有内容的 draft
+    if active:
+        return max(int(c.number) for c in active)
+    return min(int(c.number) for c in drafts)     # 全为空壳时取最小（即将写入的下一章）
```

---

### 5. `frontend/src/components/knowledge/KnowledgePanel.vue`

**修复 `addChapter` 中 `chapter_id` 数值计算 Bug：**

**问题：** `chapter_id` 从服务端返回为字符串类型时，`Math.max(...ids)` 接收字符串数组会返回 `NaN`，导致新增章节 ID 变成 `NaN + 1 = NaN`。

```diff
-const ids = data.value.chapters.map(c => c.chapter_id)
+const ids = data.value.chapters.map(c => Number(c.chapter_id)).filter(n => Number.isFinite(n))
```

---

## 影响范围

- **无 Breaking Change**：`knowledge_service` 为可选注入，未注入时静默跳过节拍合并，行为与原版一致
- **数据库**：`chapter_summaries` 表扩展通过 `ON CONFLICT DO UPDATE` 完成，已有行不受影响，新列初始值为空字符串 / NULL
- **前端**：仅修复计算逻辑，UI 无变化

## 测试建议

- [ ] 在分章叙事面板为某章设定 `beat_sections`，保存后重新加载验证持久化
- [ ] 触发 Autopilot 生成该章，检查日志是否出现「已合并第N章分章叙事节拍」
- [ ] 验证正文内容是否按 beat_sections 中的节拍展开
- [ ] 新增章节后确认 `chapter_id` 为正确递增整数
