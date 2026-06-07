import logging

from infrastructure.ai.process_environment import (
    configure_huggingface_process_environment,
)
from infrastructure.ai.process_environment_settings import ProcessEnvironmentSettings


def test_configure_huggingface_process_environment_sets_offline_flags(monkeypatch):
    monkeypatch.delenv("HF_HUB_OFFLINE", raising=False)
    monkeypatch.delenv("TRANSFORMERS_OFFLINE", raising=False)
    monkeypatch.delenv("HF_DATASETS_OFFLINE", raising=False)
    monkeypatch.delenv("DISABLE_SSL_VERIFY", raising=False)

    configure_huggingface_process_environment()

    assert __import__("os").environ["HF_HUB_OFFLINE"] == "1"
    assert __import__("os").environ["TRANSFORMERS_OFFLINE"] == "1"
    assert __import__("os").environ["HF_DATASETS_OFFLINE"] == "1"


def test_configure_huggingface_process_environment_disables_ssl(monkeypatch, caplog):
    monkeypatch.setenv("DISABLE_SSL_VERIFY", "true")
    monkeypatch.delenv("CURL_CA_BUNDLE", raising=False)
    monkeypatch.delenv("REQUESTS_CA_BUNDLE", raising=False)

    with caplog.at_level(logging.WARNING):
        configure_huggingface_process_environment(logging.getLogger(__name__))

    assert __import__("os").environ["CURL_CA_BUNDLE"] == ""
    assert __import__("os").environ["REQUESTS_CA_BUNDLE"] == ""
    assert "SSL certificate verification is DISABLED" in caplog.text


def test_configure_huggingface_process_environment_accepts_injected_settings(monkeypatch):
    monkeypatch.setenv("DISABLE_SSL_VERIFY", "false")
    monkeypatch.delenv("CURL_CA_BUNDLE", raising=False)
    monkeypatch.delenv("REQUESTS_CA_BUNDLE", raising=False)

    configure_huggingface_process_environment(
        settings=ProcessEnvironmentSettings(disable_ssl_verify=True)
    )

    assert __import__("os").environ["CURL_CA_BUNDLE"] == ""
    assert __import__("os").environ["REQUESTS_CA_BUNDLE"] == ""
