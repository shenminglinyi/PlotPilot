from unittest.mock import AsyncMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.api.v1.blueprint.story_structure import router, get_narrative_progress_service


def client_and_service():
    service=AsyncMock()
    service.get_report.return_value={'generation_finished':True,'story_finished':False,'issues':['缺少终局']}
    service.save_review.return_value={'generation_finished':True,'story_finished':False}
    app=FastAPI()
    app.include_router(router,prefix='/api/v1')
    app.dependency_overrides[get_narrative_progress_service]=lambda:service
    return TestClient(app),service


def test_progress_get_does_not_conflate_budget_with_story_completion():
    client,service=client_and_service()
    response=client.get('/api/v1/novels/n/structure/progress')
    assert response.status_code==200
    assert response.json()['generation_finished'] is True
    assert response.json()['story_finished'] is False


def test_review_routes_serialize_only_submitted_fields():
    client,service=client_and_service()
    response=client.put('/api/v1/novels/n/structure/volumes/v/progress',json={'chapter_budget':80})
    assert response.status_code==200
    service.save_review.assert_awaited_once_with('n','v',{'chapter_budget':80})


def test_invalid_evidence_and_unknown_novel_do_not_mutate_data():
    client,service=client_and_service()
    response=client.put('/api/v1/novels/n/structure/volumes/v/progress',json={
        'milestones':[{'id':'g','description':'结局','status':'resolved','evidence_chapters':[True]}]})
    assert response.status_code==422
    service.save_review.assert_not_awaited()
    service.get_report.side_effect=LookupError('小说不存在')
    assert client.get('/api/v1/novels/other/structure/progress').status_code==404


def test_service_validation_returns_actionable_client_error():
    client,service=client_and_service()
    service.save_review.side_effect=ValueError('不能引用空白章节')
    response=client.put('/api/v1/novels/n/structure/volumes/v/progress',json={'chapter_budget':80})
    assert response.status_code==400
    assert response.json()['detail']=='不能引用空白章节'
