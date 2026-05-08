"""AOF（Append Only File）崩溃恢复机制

核心设计：
1. 守护进程写作时，每个 chunk 追加写入 .draft 临时文件（无缓冲，fsync 保证落盘）
2. 章节完成后合并入 DB 并删除 .draft 文件
3. 启动时检查残留 .draft 文件，恢复数据到 DB

文件路径：{DATA_DIR}/drafts/{novel_id}_ch{chapter_number}.draft
- 每行一个 chunk，UTF-8 编码
- 无锁 append（操作系统保证 append 原子性）
- 章节完成后删除

性能影响：
- append 操作 ~10μs（远小于 DB 写入的 ~1ms）
- fsync 每 5 秒一次（而非每次 append，平衡安全与性能）
- 不涉及任何 SQLite 锁
"""
import os
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def _draft_dir() -> Path:
    """获取 .draft 文件存储目录"""
    from application.paths import DATA_DIR
    draft_dir = DATA_DIR / "drafts"
    draft_dir.mkdir(parents=True, exist_ok=True)
    return draft_dir


def _draft_path(novel_id: str, chapter_number: int) -> Path:
    """获取指定章节的 .draft 文件路径"""
    return _draft_dir() / f"{novel_id}_ch{chapter_number}.draft"


def append_chunk(novel_id: str, chapter_number: int, chunk: str) -> None:
    """追加写入一个 chunk 到 .draft 文件

    Args:
        novel_id: 小说 ID
        chapter_number: 章节号
        chunk: 增量文字片段
    """
    if not chunk or not chunk.strip():
        return

    path = _draft_path(novel_id, chapter_number)
    try:
        # 'a' 模式：追加写入；encoding='utf-8'；无缓冲（buffering=1 行缓冲）
        with open(path, 'a', encoding='utf-8', buffering=1) as f:
            f.write(chunk)
            # 注意：不每次 fsync，由 _periodic_fsync 定期刷盘
    except Exception as e:
        logger.warning("[AOF] append_chunk 失败: %s (novel=%s, ch=%d): %s",
                       path, novel_id, chapter_number, e)


def read_draft(novel_id: str, chapter_number: int) -> Optional[str]:
    """读取 .draft 文件的完整内容

    Returns:
        文件内容字符串，文件不存在时返回 None
    """
    path = _draft_path(novel_id, chapter_number)
    if not path.exists():
        return None
    try:
        content = path.read_text(encoding='utf-8')
        return content if content.strip() else None
    except Exception as e:
        logger.warning("[AOF] read_draft 失败: %s: %s", path, e)
        return None


def delete_draft(novel_id: str, chapter_number: int) -> None:
    """删除 .draft 文件（章节完成后调用）"""
    path = _draft_path(novel_id, chapter_number)
    if path.exists():
        try:
            path.unlink()
            logger.info("[AOF] 已删除 .draft 文件: %s", path)
        except Exception as e:
            logger.warning("[AOF] 删除 .draft 文件失败: %s: %s", path, e)


def fsync_draft(novel_id: str, chapter_number: int) -> None:
    """强制刷盘（定期调用，如每 5 秒）"""
    path = _draft_path(novel_id, chapter_number)
    if not path.exists():
        return
    try:
        # 打开文件并 fsync
        fd = os.open(str(path), os.O_WRONLY | os.O_APPEND)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    except Exception as e:
        logger.debug("[AOF] fsync 失败（可忽略）: %s: %s", path, e)


def recover_all_drafts() -> int:
    """启动时扫描所有残留 .draft 文件，尝试恢复到 DB

    Returns:
        成功恢复的章节数
    """
    draft_dir = _draft_dir()
    if not draft_dir.exists():
        return 0

    recovered = 0
    for path in draft_dir.glob("*.draft"):
        try:
            # 解析文件名：{novel_id}_ch{chapter_number}.draft
            name = path.stem  # e.g., "novel-123_ch5"
            if "_ch" not in name:
                logger.warning("[AOF] 无法解析 .draft 文件名: %s", path)
                continue

            novel_id, ch_part = name.rsplit("_ch", 1)
            chapter_number = int(ch_part)

            # 读取内容
            content = path.read_text(encoding='utf-8')
            if not content.strip():
                logger.info("[AOF] 空文件，直接删除: %s", path)
                path.unlink()
                continue

            # 写入 DB（使用 chapter repository 的 upsert）
            _recover_draft_to_db(novel_id, chapter_number, content)

            # 恢复成功，删除 .draft 文件
            path.unlink()
            recovered += 1
            logger.info(
                "[AOF] ✅ 已恢复 .draft 到 DB: novel=%s, ch=%d, %d 字",
                novel_id, chapter_number, len(content)
            )

        except Exception as e:
            logger.error("[AOF] 恢复 .draft 失败: %s: %s", path, e)

    if recovered > 0:
        logger.info("[AOF] 共恢复 %d 个章节的草稿数据", recovered)

    return recovered


def _recover_draft_to_db(novel_id: str, chapter_number: int, content: str) -> None:
    """将 .draft 文件内容恢复到 DB"""
    from application.paths import get_db_path
    from domain.novel.value_objects.novel_id import NovelId
    from domain.novel.entities.chapter import Chapter, ChapterStatus
    from infrastructure.persistence.database.sqlite_chapter_repository import SqliteChapterRepository
    from infrastructure.persistence.database.connection import get_database

    db = get_database(get_db_path())
    chapter_repo = SqliteChapterRepository(db)

    novel_id_obj = NovelId(novel_id)
    existing = chapter_repo.get_by_novel_and_number(novel_id_obj, chapter_number)

    if existing:
        # 已有记录：仅当现有内容比 .draft 短时才更新（避免覆盖更完整的数据）
        existing_content = (existing.content or "").strip()
        if len(content) > len(existing_content):
            existing.update_content(content)
            # 保留 draft 状态（不标记为 completed，让守护进程继续处理）
            if existing.status != ChapterStatus.COMPLETED:
                existing.status = ChapterStatus.DRAFT
            chapter_repo.save(existing)
        # else: DB 中的数据更完整，不覆盖
    else:
        # 无记录：创建新章节（draft 状态）
        from infrastructure.persistence.database.story_node_repository import StoryNodeRepository
        story_repo = StoryNodeRepository(get_db_path())

        # 查找对应的故事节点
        title = f"第 {chapter_number} 章（AOF 恢复）"
        outline = ""
        node_id = f"chapter-{novel_id}-{chapter_number}"

        # 尝试从故事树找到章节节点
        try:
            all_nodes = story_repo.get_by_novel_sync(novel_id)
            chapter_nodes = sorted(
                [n for n in all_nodes if n.node_type.value == "chapter"],
                key=lambda n: n.number
            )
            target_node = next((n for n in chapter_nodes if n.number == chapter_number), None)
            if target_node:
                node_id = target_node.id
                title = target_node.title or title
                outline = target_node.outline or ""
        except Exception:
            pass

        chapter = Chapter(
            id=node_id,
            novel_id=novel_id_obj,
            number=chapter_number,
            title=title,
            content=content,
            outline=outline,
            status=ChapterStatus.DRAFT,
        )
        chapter_repo.save(chapter)
