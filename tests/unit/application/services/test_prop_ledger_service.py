"""道具账本服务测试。"""

from application.analyst.services.prop_ledger_service import PropLedgerService
from infrastructure.persistence.database.connection import DatabaseConnection
from infrastructure.persistence.database.sqlite_prop_ledger_repository import (
    SqlitePropLedgerRepository,
)


def test_prop_ledger_tracks_current_state_after_events(tmp_path):
    db = DatabaseConnection(str(tmp_path / "prop-ledger.db"))
    db.execute(
        "INSERT INTO novels (id, title, slug) VALUES (?, ?, ?)",
        ("novel-1", "测试小说", "novel-1"),
    )
    db.commit()
    service = PropLedgerService(SqlitePropLedgerRepository(db))

    item = service.upsert_item(
        novel_id="novel-1",
        name="青铜钥匙",
        category="钥匙",
        status="未使用",
        current_holder="林晚",
        current_location="旧公寓",
        first_seen_chapter=2,
        last_seen_chapter=2,
        importance="major",
        description="能打开地下档案室的旧钥匙。",
        notes="不要写丢。",
    )
    assert item["name"] == "青铜钥匙"

    event = service.create_event(
        novel_id="novel-1",
        prop_name="青铜钥匙",
        chapter_number=5,
        event_type="transfer",
        holder="周砚",
        location="警局证物柜",
        status="被封存",
        evidence="第5章周砚把钥匙放入证物袋。",
        notes="下一次需要先取出。",
    )

    assert event["prop_name"] == "青铜钥匙"
    overview = service.get_overview("novel-1")
    [current] = overview["items"]
    assert current["current_holder"] == "周砚"
    assert current["current_location"] == "警局证物柜"
    assert current["status"] == "被封存"
    assert current["last_seen_chapter"] == 5
    assert overview["recent_events"][0]["evidence"] == "第5章周砚把钥匙放入证物袋。"


def test_prop_ledger_suggests_events_from_chapter_without_writing(tmp_path):
    db = DatabaseConnection(str(tmp_path / "prop-ledger-suggestions.db"))
    db.execute(
        "INSERT INTO novels (id, title, slug) VALUES (?, ?, ?)",
        ("novel-1", "测试小说", "novel-1"),
    )
    db.commit()
    service = PropLedgerService(SqlitePropLedgerRepository(db))
    service.upsert_item(
        novel_id="novel-1",
        name="青铜钥匙",
        category="钥匙",
        status="未使用",
        current_holder="林晚",
        current_location="旧公寓",
        first_seen_chapter=2,
        last_seen_chapter=2,
        importance="major",
    )

    suggestions = service.suggest_events_from_chapter(
        novel_id="novel-1",
        chapter_number=6,
        content="周砚沉默片刻，把青铜钥匙装进证物袋，锁进警局证物柜。林晚没有再看它。",
    )

    assert suggestions == [
        {
            "prop_name": "青铜钥匙",
            "chapter_number": 6,
            "event_type": "sealed",
            "status": "被封存",
            "holder": "",
            "location": "警局证物柜",
            "evidence": "周砚沉默片刻，把青铜钥匙装进证物袋，锁进警局证物柜。林晚没有再看它。",
            "reason": "正文出现已登记道具，并命中封存/证物相关表达。",
            "confidence": 0.82,
            "is_new_prop": False,
            "category": "钥匙",
            "importance": "major",
        }
    ]

    overview = service.get_overview("novel-1")
    assert overview["recent_events"] == []
    assert overview["items"][0]["status"] == "未使用"


def test_prop_ledger_discovers_new_plot_props_without_ordinary_objects(tmp_path):
    db = DatabaseConnection(str(tmp_path / "prop-ledger-discovery.db"))
    db.execute(
        "INSERT INTO novels (id, title, slug) VALUES (?, ?, ?)",
        ("novel-1", "测试小说", "novel-1"),
    )
    db.commit()
    service = PropLedgerService(SqlitePropLedgerRepository(db))

    suggestions = service.suggest_events_from_chapter(
        novel_id="novel-1",
        chapter_number=8,
        content="她拿起杯子放回桌上，又把染血的录音笔塞进抽屉。门外的脚步声停了。",
    )

    assert suggestions == [
        {
            "prop_name": "染血的录音笔",
            "chapter_number": 8,
            "event_type": "acquire",
            "status": "被取得",
            "holder": "",
            "location": "抽屉",
            "evidence": "她拿起杯子放回桌上，又把染血的录音笔塞进抽屉。",
            "reason": "正文出现疑似关键新道具，并命中取得/带走相关表达。",
            "confidence": 0.62,
            "is_new_prop": True,
            "category": "证物",
            "importance": "major",
        }
    ]

    overview = service.get_overview("novel-1")
    assert overview["items"] == []
