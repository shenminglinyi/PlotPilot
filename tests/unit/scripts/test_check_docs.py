from pathlib import Path

from scripts.check_docs import broken_links, link_path


def test_link_path_ignores_external_urls_and_anchors() -> None:
    assert link_path("https://example.com/docs") is None
    assert link_path("#section") is None
    assert link_path("mailto:maintainer@example.com") is None


def test_link_path_handles_titles_and_encoded_paths() -> None:
    assert link_path('docs/README.md "index"') == "docs/README.md"
    assert link_path("<docs/My%20Guide.md>") == "docs/My Guide.md"


def test_broken_links_reports_only_missing_local_targets(tmp_path: Path) -> None:
    existing = tmp_path / "existing.md"
    existing.write_text("# Existing\n", encoding="utf-8")
    source = tmp_path / "source.md"
    source.write_text(
        "[ok](existing.md)\n[external](https://example.com)\n[missing](missing.md)\n",
        encoding="utf-8",
    )

    assert broken_links(source) == [(3, "missing.md")]
