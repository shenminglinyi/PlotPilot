"""Unified logging configuration module."""

import logging
import os
from typing import Optional

# Valid logging levels for validation
VALID_LOGGING_LEVELS = [
    logging.DEBUG,
    logging.INFO,
    logging.WARNING,
    logging.ERROR,
    logging.CRITICAL
]


class SafeConsoleHandler(logging.StreamHandler):
    """Console handler that degrades gracefully on encoding errors.

    Windows terminals commonly default to legacy encodings such as GBK.
    When log messages contain emoji or other non-representable characters,
    the standard StreamHandler can trigger UnicodeEncodeError while writing
    to stderr/stdout. This handler falls back to an ASCII-safe escaped
    representation instead of crashing the log emission path.
    """

    def emit(self, record: logging.LogRecord) -> None:
        """Emit a record, escaping unsupported characters when needed."""
        try:
            msg = self.format(record)
            stream = self.stream
            try:
                stream.write(msg + self.terminator)
            except UnicodeEncodeError:
                safe_msg = self._escape_for_stream(msg + self.terminator, stream)
                stream.write(safe_msg)
            self.flush()
        except RecursionError:
            raise
        except Exception:
            self.handleError(record)

    @staticmethod
    def _escape_for_stream(text: str, stream) -> str:
        """Convert text to a stream-safe escaped representation."""
        encoding = getattr(stream, "encoding", None) or "utf-8"
        return text.encode(encoding, errors="backslashreplace").decode(encoding)


def _validate_logging_level(level: int) -> None:
    """Validate that the logging level is a valid Python logging level.

    Args:
        level: The logging level to validate

    Raises:
        ValueError: If the logging level is not valid
    """
    if level not in VALID_LOGGING_LEVELS:
        raise ValueError(
            f"Invalid logging level: {level}. "
            f"Valid levels are: {VALID_LOGGING_LEVELS}"
        )


def _validate_log_file(log_file: str) -> None:
    """Validate that the log file path is writable.

    Args:
        log_file: Path to the log file to validate

    Raises:
        ValueError: If the log file path is invalid or not writable
        TypeError: If the log_file parameter is not a string
    """
    if not isinstance(log_file, str):
        raise TypeError(f"log_file must be a string, got {type(log_file).__name__}")

    if not log_file or not log_file.strip():
        raise ValueError("log_file cannot be empty or whitespace")

    try:
        log_dir = os.path.dirname(log_file)
        if log_dir and not os.path.exists(log_dir):
            os.makedirs(log_dir, exist_ok=True)
    except (OSError, IOError) as e:
        raise ValueError(f"Cannot create log directory: {e}")

    try:
        test_handle = open(log_file, 'a')
        test_handle.close()
    except (OSError, IOError, PermissionError) as e:
        raise ValueError(f"Cannot write to log file '{log_file}': {e}")


def setup_logging(
    level: int = logging.INFO,
    log_file: Optional[str] = None,
    format_string: str = "%(asctime)s [%(levelname)s] %(name)s - %(message)s"
) -> None:
    """Configure logging with console and optional file output.

    Args:
        level: Logging level (default: INFO)
        log_file: Optional file path for file logging output
        format_string: Log message format string

    Raises:
        ValueError: If logging level or log file path is invalid
        TypeError: If log_file parameter is not a string when provided
    """
    _validate_logging_level(level)

    root_logger = logging.getLogger()
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    root_logger.setLevel(level)

    console_formatter = logging.Formatter(
        format_string,
        datefmt="%H:%M:%S"
    )

    console_handler = SafeConsoleHandler()
    console_handler.setLevel(level)
    console_handler.setFormatter(console_formatter)
    root_logger.addHandler(console_handler)

    if log_file is not None:
        _validate_log_file(log_file)

        try:
            file_formatter = logging.Formatter(
                format_string,
                datefmt="%Y-%m-%d %H:%M:%S"
            )
            file_handler = logging.FileHandler(log_file, encoding="utf-8")
            file_handler.setLevel(level)
            file_handler.setFormatter(file_formatter)
            root_logger.addHandler(file_handler)

        except (OSError, IOError, PermissionError) as e:
            print(f"WARNING: Failed to setup file logging: {e}")
            print("Logging will continue with console output only.")

    logging.getLogger("uvicorn").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.INFO)
    logging.getLogger("fastapi").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Get a logger instance with the specified name.

    Args:
        name: Logger name, typically __name__ of the calling module

    Returns:
        Logger instance configured with the global settings
    """
    return logging.getLogger(name)
