"""写作手法知识库 API 测试。"""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from application.style_bible.services.style_profile_service import StyleProfileService
from application.style_bible.services.style_prompt_overlay_service import (
    StylePromptOverlayService,
)
from infrastructure.persistence.database.connection import DatabaseConnection
from infrastructure.persistence.database.sqlite_style_bible_repository import (
    SqliteStyleBibleRepository,
)
from interfaces.api.v1 import style_bible


def _client(tmp_path):
    db = DatabaseConnection(str(tmp_path / "style-bible-api.db"))
    repo = SqliteStyleBibleRepository(db)
    app = FastAPI()
    app.include_router(style_bible.router, prefix="/api/v1")
    app.dependency_overrides[style_bible.get_style_bible_repository] = lambda: repo
    app.dependency_overrides[style_bible.get_style_profile_service] = lambda: StyleProfileService(repo)
    app.dependency_overrides[style_bible.get_style_prompt_overlay_service] = lambda: StylePromptOverlayService(repo)
    return TestClient(app)


def test_style_bible_api_imports_sample_and_lists_it(tmp_path):
    client = _client(tmp_path)

    response = client.post(
        "/api/v1/style-bible/samples",
        json={
            "title": "雨夜样本",
            "content": "第1章 雨夜\n\n雨落在窗上。\n\n“你来了？”他低声问。",
            "novel_id": "novel-1",
            "allowed_for_generation": True,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["sample"]["title"] == "雨夜样本"
    assert body["sample"]["allowed_for_generation"] is True
    assert body["chunks"][0]["metrics"]["avg_sentence_length"] > 0

    list_response = client.get("/api/v1/style-bible/samples", params={"novel_id": "novel-1"})
    assert list_response.status_code == 200
    assert list_response.json()[0]["title"] == "雨夜样本"


def test_style_bible_api_generates_profile_updates_card_and_previews_overlay(tmp_path):
    client = _client(tmp_path)
    sample_response = client.post(
        "/api/v1/style-bible/samples",
        json={
            "title": "悬疑样本",
            "content": "林晚推开门。空气仿佛凝固。\n\n“你来了？”他低声问。",
            "novel_id": "novel-1",
            "scene_type": "悬疑",
            "allowed_for_generation": True,
        },
    )
    sample_id = sample_response.json()["sample"]["id"]

    profile_response = client.post(
        "/api/v1/style-bible/profiles",
        json={
            "novel_id": "novel-1",
            "name": "克制悬疑",
            "sample_ids": [sample_id],
        },
    )

    assert profile_response.status_code == 200
    profile_body = profile_response.json()
    profile_id = profile_body["profile"]["id"]
    card_id = profile_body["cards"][0]["id"]
    assert profile_body["cards"]

    patch_response = client.patch(
        f"/api/v1/style-bible/cards/{card_id}",
        json={"prompt_instruction": "每段都要产生一个可见变化。", "enabled": True},
    )

    assert patch_response.status_code == 200
    assert patch_response.json()["prompt_instruction"] == "每段都要产生一个可见变化。"

    overlay_response = client.post(
        "/api/v1/style-bible/overlay/preview",
        json={
            "novel_id": "novel-1",
            "style_profile_id": profile_id,
            "scene_type": "悬疑",
        },
    )

    assert overlay_response.status_code == 200
    assert "【写作手法库】" in overlay_response.json()["prompt"]
    assert "不复刻样本文字" in overlay_response.json()["prompt"]


def test_style_bible_api_returns_404_for_missing_profile(tmp_path):
    client = _client(tmp_path)

    response = client.get("/api/v1/style-bible/profiles/missing")

    assert response.status_code == 404
