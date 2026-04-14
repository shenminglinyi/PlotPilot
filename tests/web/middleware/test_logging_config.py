"""Tests for unified logging configuration."""

import io
import logging
import os
import tempfile
from unittest.mock import Mock, patch

import pytest

from interfaces.api.middleware.logging_config import (
    SafeConsoleHandler,
    get_logger,
    setup_logging,
)


@pytest.fixture
def reset_logging():
    """Reset logging configuration before and after each test."""
    root_logger = logging.getLogger()
    handlers = root_logger.handlers[:]
    for handler in handlers:
        root_logger.removeHandler(handler)
    root_logger.setLevel(logging.WARNING)

    yield

    root_logger = logging.getLogger()
    handlers = root_logger.handlers[:]
    for handler in handlers:
        root_logger.removeHandler(handler)
    root_logger.setLevel(logging.WARNING)


class TestSetupLogging:
    """Test suite for setup_logging function."""

    def test_setup_logging_console_only(self, reset_logging):
        """Test logging setup with console output only."""
        setup_logging(level=logging.DEBUG)

        root_logger = logging.getLogger()

        assert root_logger.level == logging.DEBUG

        assert len(root_logger.handlers) == 1
        handler = root_logger.handlers[0]
        assert isinstance(handler, SafeConsoleHandler)
        assert handler.level == logging.DEBUG

        formatter = handler.formatter
        assert formatter is not None
        assert "%(levelname)s" in formatter._fmt
        assert formatter.datefmt == "%H:%M:%S"

    def test_setup_logging_with_file(self, reset_logging):
        """Test logging setup with both console and file output."""
        temp_dir = tempfile.mkdtemp()
        try:
            log_file_path = os.path.join(temp_dir, "test.log")

            setup_logging(level=logging.INFO, log_file=log_file_path)

            root_logger = logging.getLogger()

            assert root_logger.level == logging.INFO
            assert len(root_logger.handlers) == 2

            console_handler = root_logger.handlers[0]
            assert isinstance(console_handler, SafeConsoleHandler)
            assert console_handler.level == logging.INFO

            file_handler = root_logger.handlers[1]
            assert isinstance(file_handler, logging.FileHandler)
            assert file_handler.level == logging.INFO
            assert file_handler.encoding.lower() == "utf-8"

            file_formatter = file_handler.formatter
            assert file_formatter.datefmt == "%Y-%m-%d %H:%M:%S"

            test_logger = get_logger("test")
            test_logger.info("Test message")

            assert os.path.exists(log_file_path)
            with open(log_file_path, "r") as f:
                content = f.read()
                assert "Test message" in content
                assert "[INFO]" in content

            file_handler.close()
            root_logger.removeHandler(file_handler)

        finally:
            import shutil
            import time
            time.sleep(0.1)
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)

    def test_setup_logging_clears_existing_handlers(self, reset_logging):
        """Test that setup_logging clears existing handlers."""
        root_logger = logging.getLogger()
        dummy_handler = logging.StreamHandler()
        root_logger.addHandler(dummy_handler)

        existing_handler_count = len(root_logger.handlers)
        assert existing_handler_count >= 1
        assert dummy_handler in root_logger.handlers

        setup_logging()

        assert len(root_logger.handlers) == 1
        assert root_logger.handlers[0] is not dummy_handler

    def test_setup_logging_sets_third_party_levels(self, reset_logging):
        """Test that third-party library levels are set to WARNING."""
        setup_logging(level=logging.DEBUG)

        uvicorn_logger = logging.getLogger("uvicorn")
        fastapi_logger = logging.getLogger("fastapi")

        assert uvicorn_logger.level == logging.WARNING
        assert fastapi_logger.level == logging.WARNING

    def test_setup_logging_custom_format(self, reset_logging):
        """Test logging setup with custom format string."""
        custom_format = "%(name)s - %(message)s"
        setup_logging(level=logging.INFO, format_string=custom_format)

        root_logger = logging.getLogger()
        handler = root_logger.handlers[0]

        assert handler.formatter._fmt == custom_format

    def test_safe_console_handler_escapes_unencodable_characters(self, reset_logging):
        """Test that console logging does not crash on encoding errors."""

        class GbkConsole(io.StringIO):
            encoding = "gbk"

            def write(self, text):
                if "🚀" in text:
                    idx = text.index("🚀")
                    raise UnicodeEncodeError("gbk", text, idx, idx + 1, "illegal multibyte sequence")
                return super().write(text)

        stream = GbkConsole()
        handler = SafeConsoleHandler(stream)
        handler.setFormatter(logging.Formatter("%(message)s"))

        logger = logging.getLogger("safe_console_test")
        logger.handlers = []
        logger.setLevel(logging.INFO)
        logger.propagate = False
        logger.addHandler(handler)

        logger.info("🚀 backend starting")

        output = stream.getvalue()
        assert "\\U0001f680 backend starting" in output

        logger.removeHandler(handler)


class TestGetLogger:
    """Test suite for get_logger function."""

    def test_get_logger_returns_logger(self, reset_logging):
        """Test that get_logger returns a Logger instance."""
        setup_logging()
        logger = get_logger("test_logger")

        assert isinstance(logger, logging.Logger)
        assert logger.name == "test_logger"

    def test_get_logger_with_different_names(self, reset_logging):
        """Test get_logger with different name patterns."""
        setup_logging()

        logger1 = get_logger("module.submodule")
        logger2 = get_logger("another_module")

        assert logger1.name == "module.submodule"
        assert logger2.name == "another_module"
        assert logger1 is not logger2

    def test_get_logger_respects_root_level(self, reset_logging):
        """Test that loggers respect root logger level."""
        setup_logging(level=logging.ERROR)

        logger = get_logger("test")

        assert logger.getEffectiveLevel() == logging.ERROR

    def test_get_logger_can_log(self, reset_logging):
        """Test that logger can actually log messages."""
        setup_logging(level=logging.INFO)

        logger = get_logger("test_logger")

        log_capture = io.StringIO()
        test_handler = logging.StreamHandler(log_capture)
        test_handler.setLevel(logging.INFO)
        test_handler.setFormatter(logging.Formatter("%(levelname)s - %(message)s"))
        logger.addHandler(test_handler)

        logger.info("Test info message")
        logger.warning("Test warning message")
        logger.error("Test error message")

        log_content = log_capture.getvalue()
        assert "Test info message" in log_content
        assert "Test warning message" in log_content
        assert "Test error message" in log_content

        logger.removeHandler(test_handler)


class TestSetupLoggingErrorHandling:
    """Test suite for setup_logging error handling and validation."""

    def test_invalid_logging_level_raises_error(self, reset_logging):
        """Test that invalid logging level raises ValueError."""
        with pytest.raises(ValueError, match="Invalid logging level"):
            setup_logging(level=999)

    def test_invalid_logging_level_negative(self, reset_logging):
        """Test that negative logging level raises ValueError."""
        with pytest.raises(ValueError, match="Invalid logging level"):
            setup_logging(level=-1)

    def test_invalid_log_file_not_string(self, reset_logging):
        """Test that non-string log_file raises TypeError."""
        with pytest.raises(TypeError, match="log_file must be a string"):
            setup_logging(level=logging.INFO, log_file=123)

    def test_invalid_log_file_empty_string(self, reset_logging):
        """Test that empty string log_file raises ValueError."""
        with pytest.raises(ValueError, match="log_file cannot be empty"):
            setup_logging(level=logging.INFO, log_file="")

    def test_invalid_log_file_whitespace(self, reset_logging):
        """Test that whitespace-only log_file raises ValueError."""
        with pytest.raises(ValueError, match="log_file cannot be empty"):
            setup_logging(level=logging.INFO, log_file="   ")

    def test_setup_logging_continues_with_console_on_file_error(self, reset_logging):
        """Test that setup_logging continues with console if file setup fails."""
        import sys
        from io import StringIO

        temp_dir = tempfile.mkdtemp()

        old_stdout = sys.stdout
        captured_output = StringIO()
        sys.stdout = captured_output

        try:
            valid_path = os.path.join(temp_dir, "test.log")

            with patch("interfaces.api.middleware.logging_config.logging.FileHandler") as mock_file_handler:
                mock_file_handler.side_effect = PermissionError("Permission denied")

                setup_logging(level=logging.INFO, log_file=valid_path)

            root_logger = logging.getLogger()
            assert root_logger.level == logging.INFO
            assert len(root_logger.handlers) == 1
            assert isinstance(root_logger.handlers[0], logging.StreamHandler)

            output = captured_output.getvalue()
            assert "WARNING: Failed to setup file logging" in output
            assert "Logging will continue with console output only" in output

        finally:
            sys.stdout = old_stdout
            import shutil
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)

    def test_valid_logging_levels(self, reset_logging):
        """Test that all valid logging levels work correctly."""
        valid_levels = [
            logging.DEBUG,
            logging.INFO,
            logging.WARNING,
            logging.ERROR,
            logging.CRITICAL,
        ]

        for level in valid_levels:
            setup_logging(level=level)
            root_logger = logging.getLogger()
            assert root_logger.level == level

            for handler in root_logger.handlers[:]:
                root_logger.removeHandler(handler)

    def test_valid_log_file_creates_directory(self, reset_logging):
        """Test that valid log file path creates parent directories if needed."""
        import shutil

        temp_dir = tempfile.mkdtemp()
        try:
            nested_path = os.path.join(temp_dir, "level1", "level2", "test.log")

            setup_logging(level=logging.INFO, log_file=nested_path)

            root_logger = logging.getLogger()
            assert len(root_logger.handlers) == 2

            assert os.path.exists(nested_path)
            assert os.path.isfile(nested_path)

            file_handler = root_logger.handlers[1]
            file_handler.close()
            root_logger.removeHandler(file_handler)

        finally:
            import time
            time.sleep(0.1)
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)

            time.sleep(0.1)  # Give time for file handles to be released
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)
