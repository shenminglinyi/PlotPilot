from pathlib import Path

from infrastructure.runtime.data_directory_environment import (
    DataDirectoryEnvironmentSettings,
)


def test_data_directory_environment_reads_primary_and_legacy(monkeypatch):
    monkeypatch.setenv("PLOTPILOT_PROD_DATA_DIR", "/primary/data")
    monkeypatch.setenv("AITEXT_PROD_DATA_DIR", "/legacy/data")

    settings = DataDirectoryEnvironmentSettings.from_env()

    assert settings.prod_data_dir == "/primary/data"
    assert settings.legacy_prod_data_dir == "/legacy/data"
    assert settings.prod_data_dir_raw == "/primary/data"


def test_data_directory_environment_uses_legacy_when_primary_missing(monkeypatch):
    monkeypatch.delenv("PLOTPILOT_PROD_DATA_DIR", raising=False)
    monkeypatch.setenv("AITEXT_PROD_DATA_DIR", "/legacy/data")

    settings = DataDirectoryEnvironmentSettings.from_env()

    assert settings.prod_data_dir_raw == "/legacy/data"


def test_frozen_fallback_data_dir_windows_uses_appdata():
    settings = DataDirectoryEnvironmentSettings(
        appdata_dir="C:/Users/me/AppData/Roaming",
        platform="win32",
    )

    assert (
        settings.frozen_fallback_data_dir(Path("C:/Users/me"))
        == Path("C:/Users/me/AppData/Roaming") / "com.plotpilot.desktop" / "data"
    )


def test_frozen_fallback_data_dir_posix():
    settings = DataDirectoryEnvironmentSettings(platform="linux")

    assert (
        settings.frozen_fallback_data_dir(Path("/home/me"))
        == Path("/home/me") / ".local" / "share" / "com.plotpilot.desktop" / "data"
    )
