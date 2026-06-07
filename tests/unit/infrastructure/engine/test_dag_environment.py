from infrastructure.engine.dag_environment import DAGEnvironmentSettings


def test_dag_environment_defaults_to_disabled(monkeypatch):
    monkeypatch.delenv("ENABLE_DAG_ENGINE", raising=False)

    settings = DAGEnvironmentSettings.from_env()

    assert settings.enabled is False


def test_dag_environment_accepts_legacy_truthy_values(monkeypatch):
    for value in ("1", "true", "yes"):
        monkeypatch.setenv("ENABLE_DAG_ENGINE", value)

        assert DAGEnvironmentSettings.from_env().enabled is True


def test_dag_environment_rejects_falsey_values(monkeypatch):
    for value in ("", "0", "false", "no"):
        monkeypatch.setenv("ENABLE_DAG_ENGINE", value)

        assert DAGEnvironmentSettings.from_env().enabled is False
