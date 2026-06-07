from pathlib import Path


def test_main_no_longer_hardcodes_api_router_prefixes():
    source = Path("interfaces/main.py").read_text(encoding="utf-8")

    assert "include_router(" not in source
    assert 'prefix="/api/v1' not in source
    assert "on_event(" not in source


def test_main_does_not_own_daemon_process_implementation():
    source = Path("interfaces/main.py").read_text(encoding="utf-8")

    assert "def _run_daemon_in_process" not in source
    assert "multiprocessing.Process" not in source
    assert "taskkill" not in source


def test_backend_modules_do_not_import_runtime_state_from_main():
    roots = [Path("application"), Path("engine"), Path("interfaces/api"), Path("infrastructure")]
    offenders = []
    for root in roots:
        for path in root.rglob("*.py"):
            source = path.read_text(encoding="utf-8")
            if "from interfaces.main import" in source:
                offenders.append(str(path))

    assert offenders == []


def test_route_prefix_constants_are_centralized():
    source = Path("interfaces/api/routes.py").read_text(encoding="utf-8")

    assert 'prefix="/api/v1' not in source
    assert "API_V1_PREFIX" in source
    assert "NOVELS_API_PREFIX" in source
    assert "STATS_API_PREFIX" in source


def test_api_response_urls_do_not_inline_v1_prefix():
    offenders = []
    for path in Path("interfaces/api/v1").rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        if 'f"/api/v1' in source or "f'/api/v1" in source:
            offenders.append(str(path))

    assert offenders == []


def test_embedding_services_use_environment_settings_object():
    paths = [
        Path("infrastructure/ai/openai_embedding_service.py"),
        Path("infrastructure/ai/local_embedding_service.py"),
        Path("application/ai/embedding_config_service.py"),
    ]
    offenders = []
    for path in paths:
        source = path.read_text(encoding="utf-8")
        if "os.getenv(" in source:
            offenders.append(str(path))

    assert offenders == []


def test_backend_settings_delegates_vector_store_environment_parsing():
    source = Path("interfaces/api/settings.py").read_text(encoding="utf-8")

    assert "VECTOR_STORE_" not in source
    assert "QDRANT_" not in source
    assert "VectorStoreEnvironmentSettings" in source


def test_app_factory_registers_legacy_and_api_routes(tmp_path):
    from interfaces.api.settings import BackendSettings
    from interfaces.main import create_app

    app = create_app(BackendSettings(frontend_dir=tmp_path / "dist"))
    routes = {route.path for route in app.routes}

    assert "/" in routes
    assert "/health" in routes
    assert "/internal/shutdown" in routes
    assert "/api/v1/novels/" in routes
    assert "/api/stats/global" in routes
