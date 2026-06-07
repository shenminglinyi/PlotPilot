from infrastructure.persistence.database.write_environment import (
    SQLiteWriteEnvironmentSettings,
)


def test_sqlite_write_environment_defaults_to_queue(monkeypatch):
    monkeypatch.delenv("PLOTPILOT_ALLOW_DIRECT_SQLITE_WRITES", raising=False)
    monkeypatch.delenv("AITEXT_ALLOW_DIRECT_SQLITE_WRITES", raising=False)

    settings = SQLiteWriteEnvironmentSettings.from_env()

    assert settings.direct_writes is False


def test_sqlite_write_environment_accepts_primary_truthy_values(monkeypatch):
    monkeypatch.delenv("AITEXT_ALLOW_DIRECT_SQLITE_WRITES", raising=False)
    for value in ("1", "true", "yes"):
        monkeypatch.setenv("PLOTPILOT_ALLOW_DIRECT_SQLITE_WRITES", value)

        assert SQLiteWriteEnvironmentSettings.from_env().direct_writes is True


def test_sqlite_write_environment_uses_legacy_when_primary_missing(monkeypatch):
    monkeypatch.delenv("PLOTPILOT_ALLOW_DIRECT_SQLITE_WRITES", raising=False)
    monkeypatch.setenv("AITEXT_ALLOW_DIRECT_SQLITE_WRITES", "yes")

    settings = SQLiteWriteEnvironmentSettings.from_env()

    assert settings.direct_writes is True


def test_sqlite_write_environment_primary_overrides_legacy(monkeypatch):
    monkeypatch.setenv("PLOTPILOT_ALLOW_DIRECT_SQLITE_WRITES", "false")
    monkeypatch.setenv("AITEXT_ALLOW_DIRECT_SQLITE_WRITES", "yes")

    settings = SQLiteWriteEnvironmentSettings.from_env()

    assert settings.direct_writes is False
