from pathlib import Path

from infrastructure.export.font_environment import ExportFontEnvironmentSettings


def test_export_font_environment_uses_custom_font_first(monkeypatch):
    monkeypatch.setenv("PLOTPILOT_EXPORT_CJK_FONT", "C:/fonts/custom.ttf")
    monkeypatch.setenv("WINDIR", "C:/Windows")

    settings = ExportFontEnvironmentSettings.from_env()

    assert settings.cjk_font_path == "C:/fonts/custom.ttf"
    assert next(settings.cjk_font_paths()) == Path("C:/fonts/custom.ttf")


def test_export_font_environment_windows_candidates():
    settings = ExportFontEnvironmentSettings(
        windows_dir="D:/Windows",
        os_name="nt",
    )

    paths = list(settings.cjk_font_paths())

    assert paths[0] == Path("D:/Windows") / "Fonts" / "msyh.ttf"
    assert Path("D:/Windows") / "Fonts" / "simkai.ttf" in paths


def test_export_font_environment_posix_candidates():
    settings = ExportFontEnvironmentSettings(os_name="posix")

    paths = list(settings.cjk_font_paths())

    assert Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc") in paths
    assert Path("/usr/share/fonts/truetype/wqy/wqy-microhei.ttc") in paths
