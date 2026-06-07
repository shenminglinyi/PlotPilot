import logging
from logging.handlers import RotatingFileHandler

from infrastructure.runtime.logging_environment import LoggingEnvironmentSettings
from interfaces.api.middleware import logging_config


def test_should_use_color_uses_injected_environment():
    assert logging_config._should_use_color(LoggingEnvironmentSettings(color_mode="always")) is True
    assert logging_config._should_use_color(LoggingEnvironmentSettings(color_mode="never")) is False


def test_quiet_noisy_loggers_respects_debug_http():
    target = logging.getLogger("httpx")
    target.setLevel(logging.DEBUG)

    logging_config._quiet_noisy_loggers(LoggingEnvironmentSettings(debug_http=False))
    assert target.level == logging.WARNING

    target.setLevel(logging.DEBUG)
    logging_config._quiet_noisy_loggers(LoggingEnvironmentSettings(debug_http=True))
    assert target.level == logging.DEBUG


def test_setup_logging_uses_injected_file_rotation_settings(tmp_path):
    log_file = tmp_path / "plotpilot.log"

    logging_config.setup_logging(
        level=logging.INFO,
        log_file=str(log_file),
        environment=LoggingEnvironmentSettings(
            color_mode="never",
            max_bytes=1234,
            backup_count=2,
        ),
    )

    handlers = [h for h in logging.getLogger().handlers if isinstance(h, RotatingFileHandler)]
    assert handlers
    assert handlers[0].maxBytes == 1234
    assert handlers[0].backupCount == 2
