from infrastructure.runtime.logging_environment import LoggingEnvironmentSettings


class _TTY:
    def __init__(self, value: bool):
        self._value = value

    def isatty(self):
        return self._value


def test_logging_environment_defaults(monkeypatch):
    for name in ("DEBUG_HTTP", "LOG_COLOR", "NO_COLOR", "LOG_MAX_BYTES", "LOG_BACKUP_COUNT"):
        monkeypatch.delenv(name, raising=False)

    settings = LoggingEnvironmentSettings.from_env()

    assert settings.debug_http is False
    assert settings.color_mode == "auto"
    assert settings.no_color is False
    assert settings.max_bytes == 10 * 1024 * 1024
    assert settings.backup_count == 5


def test_logging_environment_overrides(monkeypatch):
    monkeypatch.setenv("DEBUG_HTTP", "yes")
    monkeypatch.setenv("LOG_COLOR", "never")
    monkeypatch.setenv("NO_COLOR", "1")
    monkeypatch.setenv("LOG_MAX_BYTES", "2048")
    monkeypatch.setenv("LOG_BACKUP_COUNT", "7")

    settings = LoggingEnvironmentSettings.from_env()

    assert settings.debug_http is True
    assert settings.color_mode == "never"
    assert settings.no_color is True
    assert settings.max_bytes == 2048
    assert settings.backup_count == 7


def test_logging_environment_invalid_ints_fall_back(monkeypatch):
    monkeypatch.setenv("LOG_MAX_BYTES", "bad")
    monkeypatch.setenv("LOG_BACKUP_COUNT", "-2")

    settings = LoggingEnvironmentSettings.from_env()

    assert settings.max_bytes == 10 * 1024 * 1024
    assert settings.backup_count == 0


def test_logging_environment_color_policy():
    assert LoggingEnvironmentSettings(color_mode="always").should_use_color(_TTY(False)) is True
    assert LoggingEnvironmentSettings(color_mode="never").should_use_color(_TTY(True)) is False
    assert LoggingEnvironmentSettings(color_mode="auto", no_color=True).should_use_color(_TTY(True)) is False
    assert LoggingEnvironmentSettings(color_mode="auto").should_use_color(_TTY(True)) is True
