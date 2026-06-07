from infrastructure.ai.process_environment_settings import ProcessEnvironmentSettings


def test_process_environment_settings_defaults_to_ssl_enabled(monkeypatch):
    monkeypatch.delenv("DISABLE_SSL_VERIFY", raising=False)

    settings = ProcessEnvironmentSettings.from_env()

    assert settings.disable_ssl_verify is False


def test_process_environment_settings_reads_disable_ssl_verify(monkeypatch):
    monkeypatch.setenv("DISABLE_SSL_VERIFY", "true")

    settings = ProcessEnvironmentSettings.from_env()

    assert settings.disable_ssl_verify is True


def test_process_environment_settings_only_true_disables_ssl(monkeypatch):
    monkeypatch.setenv("DISABLE_SSL_VERIFY", "yes")

    settings = ProcessEnvironmentSettings.from_env()

    assert settings.disable_ssl_verify is False
