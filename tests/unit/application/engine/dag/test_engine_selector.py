from application.engine.dag.daemon_runner import EngineSelector


def test_engine_selector_uses_injected_default():
    selector = EngineSelector(dag_enabled=True)

    assert selector.should_use_dag("novel-1") is True


def test_engine_selector_novel_flag_overrides_default():
    selector = EngineSelector(dag_enabled=False)

    selector.set_novel_flag("novel-1", True)

    assert selector.should_use_dag("novel-1") is True
    assert selector.should_use_dag("novel-2") is False


def test_engine_selector_uses_environment_default(monkeypatch):
    monkeypatch.setenv("ENABLE_DAG_ENGINE", "yes")

    selector = EngineSelector()

    assert selector.should_use_dag("novel-1") is True
