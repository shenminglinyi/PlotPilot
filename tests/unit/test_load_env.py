import os
from pathlib import Path

from load_env import load_env


def test_load_env_clears_inherited_proxy_vars_when_env_file_has_no_proxy_settings(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("FOO=bar\n", encoding="utf-8")

    for key in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
        monkeypatch.setenv(key, f"value-for-{key}")
    monkeypatch.delenv("NO_PROXY", raising=False)
    monkeypatch.delenv("no_proxy", raising=False)

    loaded = load_env(env_file)

    assert loaded == env_file
    assert os.getenv("FOO") == "bar"
    for key in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
        assert os.getenv(key) is None
    assert os.getenv("NO_PROXY") == "127.0.0.1,localhost"
    assert os.getenv("no_proxy") == "127.0.0.1,localhost"


def test_load_env_keeps_only_proxy_values_explicitly_defined_in_env_file(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "HTTPS_PROXY=http://proxy.example:7890",
                "ALL_PROXY=socks5://proxy.example:1080",
                "NO_PROXY=example.com,localhost",
            ]
        ),
        encoding="utf-8",
    )

    monkeypatch.setenv("HTTP_PROXY", "http://inherited:8888")
    monkeypatch.setenv("HTTPS_PROXY", "http://inherited:9999")
    monkeypatch.setenv("ALL_PROXY", "socks5://inherited:1080")
    monkeypatch.setenv("http_proxy", "http://lower-inherited:8888")
    monkeypatch.setenv("https_proxy", "http://lower-inherited:9999")
    monkeypatch.setenv("all_proxy", "socks5://lower-inherited:1080")

    load_env(env_file)

    assert os.getenv("HTTP_PROXY") is None
    assert os.getenv("http_proxy") is None
    assert os.getenv("HTTPS_PROXY") == "http://proxy.example:7890"
    assert os.getenv("https_proxy") == "http://proxy.example:7890"
    assert os.getenv("ALL_PROXY") == "socks5://proxy.example:1080"
    assert os.getenv("all_proxy") == "socks5://proxy.example:1080"
    assert os.getenv("NO_PROXY") == "example.com,localhost"
    assert os.getenv("no_proxy") == "example.com,localhost"
