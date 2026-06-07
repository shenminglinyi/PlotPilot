from pathlib import Path

from application import paths
from infrastructure.runtime.data_directory_environment import DataDirectoryEnvironmentSettings


def test_prod_data_dir_raw_prefers_primary():
    settings = DataDirectoryEnvironmentSettings(
        prod_data_dir="/primary",
        legacy_prod_data_dir="/legacy",
    )

    assert paths._prod_data_dir_raw(settings) == "/primary"


def test_prod_data_dir_raw_falls_back_to_legacy():
    settings = DataDirectoryEnvironmentSettings(legacy_prod_data_dir="/legacy")

    assert paths._prod_data_dir_raw(settings) == "/legacy"


def test_frozen_fallback_data_dir_delegates_to_environment_settings():
    settings = DataDirectoryEnvironmentSettings(
        appdata_dir="C:/Users/me/AppData/Roaming",
        platform="win32",
    )

    assert (
        paths._frozen_fallback_data_dir(settings)
        == Path("C:/Users/me/AppData/Roaming") / "com.plotpilot.desktop" / "data"
    )
