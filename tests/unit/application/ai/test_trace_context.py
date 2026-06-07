from application.ai.trace_context import (
    REDACTED,
    content_hash,
    extract_novel_id,
    preview_value,
)


def test_preview_value_redacts_sensitive_fields_and_truncates_text():
    preview = preview_value(
        {
            "api_key": "sk-secret",
            "chapter_content": "正文" * 500,
            "outline": "短纲",
        },
        max_chars=12,
    )

    assert preview["api_key"] == REDACTED
    assert preview["chapter_content"] == REDACTED
    assert preview["outline"] == "短纲"


def test_content_hash_is_stable_for_mapping_order():
    assert content_hash({"b": 2, "a": 1}) == content_hash({"a": 1, "b": 2})


def test_extract_novel_id_supports_common_keys():
    assert extract_novel_id({"novel_id": "novel-1"}) == "novel-1"
    assert extract_novel_id({"novelId": "novel-2"}) == "novel-2"
