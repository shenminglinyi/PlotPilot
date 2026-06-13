from application.engine.services.chapter_generation_workspace import ChapterGenerationWorkspace


def test_chapter_generation_workspace_preview_is_transient(monkeypatch, tmp_path):
    import application.paths

    monkeypatch.setattr(application.paths, "DATA_DIR", tmp_path)
    workspace = ChapterGenerationWorkspace()

    ref = workspace.begin("novel/1", 3, "run-1")
    workspace.append_preview(ref.novel_id, ref.chapter_number, ref.run_id, "半章正文")

    assert workspace.read_latest_preview("novel/1", 3, "run-1") == "半章正文"

    removed = workspace.discard("novel/1", 3)

    assert removed == 2
    assert workspace.read_latest_preview("novel/1", 3, "run-1") is None

