"""OpenAI 兼容网关：模型列表请求的 base URL 归一化。"""

import pytest

from interfaces.api.v1.workbench import llm_control
from interfaces.api.v1.workbench.llm_control import (
    ModelListRequest,
    _merge_extra_headers,
    _openai_compatible_models_base,
    list_models,
)


def test_empty_defaults_to_official_v1():
    """空 base URL 应回退到 OpenAI 官方 v1 地址。"""
    assert _openai_compatible_models_base('') == 'https://api.openai.com/v1'


def test_host_only_appends_v1():
    """仅填写网关主机时应自动补齐 /v1 路径。"""
    assert _openai_compatible_models_base('https://api.zhongzhuan.win') == 'https://api.zhongzhuan.win/v1'
    assert _openai_compatible_models_base('https://api.zhongzhuan.win/') == 'https://api.zhongzhuan.win/v1'


def test_preserves_non_root_path():
    """已带非根路径的兼容网关地址应保持原路径。"""
    assert _openai_compatible_models_base('https://ark.cn-beijing.volces.com/api/v3') == (
        'https://ark.cn-beijing.volces.com/api/v3'
    )


def test_explicit_v1_unchanged():
    """显式填写 /v1 时不应重复追加版本路径。"""
    assert _openai_compatible_models_base('https://x.example/v1') == 'https://x.example/v1'


def test_model_list_request_accepts_extra_headers():
    """模型列表请求体应接受额外请求头字段。"""
    payload = ModelListRequest(extra_headers={'User-Agent': 'UA'})

    assert payload.extra_headers == {'User-Agent': 'UA'}


def test_merge_extra_headers_preserves_auth_headers():
    """合并额外请求头时应保护认证头并忽略空键值。"""
    headers = _merge_extra_headers(
        {'Authorization': 'Bearer real-token'},
        {
            'User-Agent': 'UA',
            'Authorization': 'Bearer bad-token',
            '  ': 'ignored',
            'x-empty': '',
        },
    )

    assert headers == {
        'Authorization': 'Bearer real-token',
        'User-Agent': 'UA',
    }


@pytest.mark.asyncio
async def test_list_models_sends_extra_headers(monkeypatch):
    """拉取模型列表时应透传 User-Agent 并继续隔离系统代理。"""
    captured = {}

    class FakeResponse:
        """模拟上游模型列表成功响应。"""

        text = ''
        reason_phrase = 'OK'
        status_code = 200

        def raise_for_status(self):
            """模拟成功响应的状态码检查。"""
            return None

        def json(self):
            """返回 OpenAI 兼容的模型列表 JSON。"""
            return {'data': [{'id': 'test-model', 'owned_by': 'owner'}]}

    class FakeClient:
        """记录 httpx.AsyncClient 初始化参数和 GET 请求参数。"""

        def __init__(self, *args, **kwargs):
            """捕获客户端初始化参数。"""
            captured['client_kwargs'] = kwargs

        async def __aenter__(self):
            """进入异步上下文时返回自身。"""
            return self

        async def __aexit__(self, *args):
            """退出异步上下文时不做额外处理。"""
            return None

        async def get(self, url, headers):
            """捕获请求 URL 和请求头，并返回模拟响应。"""
            captured['url'] = url
            captured['headers'] = headers
            return FakeResponse()

    monkeypatch.setattr(llm_control.httpx, 'AsyncClient', FakeClient)

    result = await list_models(ModelListRequest(
        protocol='openai',
        base_url='https://gateway.example',
        api_key='real-token',
        extra_headers={
            'User-Agent': 'UA',
            'Authorization': 'Bearer bad-token',
        },
    ))

    assert result.count == 1
    assert captured['client_kwargs'].get('trust_env') is False
    assert captured['url'] == 'https://gateway.example/v1/models'
    assert captured['headers'] == {
        'Authorization': 'Bearer real-token',
        'User-Agent': 'UA',
    }
