"""OpenAI 兼容网关：模型列表请求的 base URL 归一化。"""

from interfaces.api.v1.workbench.llm_control import _openai_compatible_models_base


def test_empty_defaults_to_official_v1():
    assert _openai_compatible_models_base('') == 'https://api.openai.com/v1'


def test_host_only_appends_v1():
    assert _openai_compatible_models_base('https://api.zhongzhuan.win') == 'https://api.zhongzhuan.win/v1'
    assert _openai_compatible_models_base('https://api.zhongzhuan.win/') == 'https://api.zhongzhuan.win/v1'


def test_preserves_non_root_path():
    assert _openai_compatible_models_base('https://ark.cn-beijing.volces.com/api/v3') == (
        'https://ark.cn-beijing.volces.com/api/v3'
    )


def test_explicit_v1_unchanged():
    assert _openai_compatible_models_base('https://x.example/v1') == 'https://x.example/v1'
