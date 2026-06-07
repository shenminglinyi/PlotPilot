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


def test_stats_router_logs_do_not_inline_stats_api_prefix():
    source = Path("interfaces/api/stats/routers/stats.py").read_text(encoding="utf-8")

    assert "/api/stats" not in source
    assert "stats_api_url" in source


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


def test_llm_control_service_uses_environment_settings_object():
    source = Path("application/ai/llm_control_service.py").read_text(encoding="utf-8")

    assert "os.getenv(" not in source
    assert "LLMEnvironmentSettings" in source


def test_application_model_services_use_environment_settings_object():
    paths = [
        Path("application/audit/services/macro_refactor_proposal_service.py"),
        Path("application/audit/services/chapter_review_service.py"),
        Path("application/analyst/services/state_extractor.py"),
        Path("application/engine/services/scene_director_service.py"),
    ]
    offenders = []
    for path in paths:
        source = path.read_text(encoding="utf-8")
        if "os.getenv(" in source:
            offenders.append(str(path))
        assert "LLMEnvironmentSettings" in source

    assert offenders == []


def test_engine_selector_uses_environment_settings_object():
    source = Path("application/engine/dag/daemon_runner.py").read_text(encoding="utf-8")

    assert "os.getenv(" not in source
    assert "DAGEnvironmentSettings" in source


def test_streaming_bus_uses_environment_settings_object():
    source = Path("application/engine/services/streaming_bus.py").read_text(encoding="utf-8")

    assert "os.environ" not in source
    assert "os.getenv(" not in source
    assert "StreamingEnvironmentSettings" in source


def test_export_service_uses_font_environment_settings_object():
    source = Path("application/core/services/export_service.py").read_text(encoding="utf-8")

    assert "PLOTPILOT_EXPORT_CJK_FONT" not in source
    assert "WINDIR" not in source
    assert "os.environ" not in source
    assert "os.getenv(" not in source
    assert "ExportFontEnvironmentSettings" in source


def test_application_paths_uses_data_directory_environment_settings():
    source = Path("application/paths.py").read_text(encoding="utf-8")

    assert "os.environ" not in source
    assert "os.getenv(" not in source
    assert "DataDirectoryEnvironmentSettings" in source


def test_write_dispatch_uses_write_environment_settings():
    source = Path("infrastructure/persistence/database/write_dispatch.py").read_text(encoding="utf-8")

    assert "os.environ" not in source
    assert "os.getenv(" not in source
    assert "SQLiteWriteEnvironmentSettings" in source


def test_process_environment_uses_process_environment_settings():
    source = Path("infrastructure/ai/process_environment.py").read_text(encoding="utf-8")

    assert "os.getenv(" not in source
    assert "ProcessEnvironmentSettings" in source


def test_writing_delegate_uses_story_pipeline_environment_settings():
    source = Path("engine/runtime/writing_delegate.py").read_text(encoding="utf-8")

    assert "os.getenv(" not in source
    assert "StoryPipelineEnvironmentSettings" in source


def test_logging_config_uses_logging_environment_settings():
    source = Path("interfaces/api/middleware/logging_config.py").read_text(encoding="utf-8")

    assert "os.environ.get" not in source
    assert "os.getenv(" not in source
    assert "LoggingEnvironmentSettings" in source


def test_ai_runtime_services_use_environment_settings_objects():
    paths = [
        Path("infrastructure/ai/claude_chapter_summarizer.py"),
        Path("infrastructure/ai/trace_recorder.py"),
    ]
    offenders = []
    for path in paths:
        source = path.read_text(encoding="utf-8")
        if "os.getenv(" in source:
            offenders.append(str(path))

    assert offenders == []
    assert "LLMEnvironmentSettings" in paths[0].read_text(encoding="utf-8")
    assert "TraceEnvironmentSettings" in paths[1].read_text(encoding="utf-8")


def test_backend_settings_delegates_vector_store_environment_parsing():
    source = Path("interfaces/api/settings.py").read_text(encoding="utf-8")

    assert "VECTOR_STORE_" not in source
    assert "QDRANT_" not in source
    assert "VectorStoreEnvironmentSettings" in source


def test_backend_settings_delegates_llm_environment_parsing():
    source = Path("interfaces/api/settings.py").read_text(encoding="utf-8")

    assert "ANTHROPIC_" not in source
    assert "OPENAI_" not in source
    assert "GEMINI_" not in source
    assert "ARK_" not in source
    assert "LLMEnvironmentSettings" in source


def test_api_routes_do_not_read_log_file_env_directly():
    offenders = []
    for path in Path("interfaces/api/v1").rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        if 'os.getenv("LOG_FILE"' in source or "os.getenv('LOG_FILE'" in source:
            offenders.append(str(path))

    assert offenders == []


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
