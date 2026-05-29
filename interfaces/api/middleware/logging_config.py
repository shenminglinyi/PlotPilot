"""Unified, readable logging configuration for PlotPilot."""

from __future__ import annotations

import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Optional


VALID_LOGGING_LEVELS = {
    logging.DEBUG,
    logging.INFO,
    logging.WARNING,
    logging.ERROR,
    logging.CRITICAL,
}

LEVEL_ALIASES = {
    "WARN": "WARNING",
    "FATAL": "CRITICAL",
}

LEVEL_STYLES: Mapping[int, Dict[str, str]] = {
    logging.DEBUG: {"label": "DEBUG", "color": "\033[36m"},
    logging.INFO: {"label": "INFO ", "color": "\033[32m"},
    logging.WARNING: {"label": "WARN ", "color": "\033[33m"},
    logging.ERROR: {"label": "ERROR", "color": "\033[31m"},
    logging.CRITICAL: {"label": "FATAL", "color": "\033[35;1m"},
}

RESET = "\033[0m"
DIM = "\033[2m"

NOISY_LOGGERS = (
    "httpcore",
    "httpcore.http11",
    "httpcore.connection",
    "hpack",
    "hpack.hpack",
    "httpx",
    "anthropic",
    "anthropic._base_client",
)

FRAMEWORK_LOGGERS = (
    "fastapi",
    "uvicorn",
    "uvicorn.error",
)

PLOTPILOT_LOGO = (
    r"  ____  _       _   ____  _ _       _",
    r" |  _ \| | ___ | |_|  _ \(_) | ___ | |_",
    r" | |_) | |/ _ \| __| |_) | | |/ _ \| __|",
    r" |  __/| | (_) | |_|  __/| | | (_) | |_",
    r" |_|   |_|\___/ \__|_|   |_|_|\___/ \__|",
)


class SafeConsoleHandler(logging.StreamHandler):
    """Console handler that degrades gracefully on encoding errors."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
            stream = self.stream
            try:
                stream.write(msg + self.terminator)
            except UnicodeEncodeError:
                stream.write(self._escape_for_stream(msg + self.terminator, stream))
            except ValueError:
                if getattr(stream, "closed", False):
                    return
                raise
            self.flush()
        except RecursionError:
            raise
        except Exception:
            self.handleError(record)

    @staticmethod
    def _escape_for_stream(text: str, stream: Any) -> str:
        encoding = getattr(stream, "encoding", None) or "utf-8"
        return text.encode(encoding, errors="backslashreplace").decode(encoding)


class PrettyFormatter(logging.Formatter):
    """Compact aligned formatter for human-facing console output."""

    def __init__(self, *, use_color: bool = True) -> None:
        super().__init__(datefmt="%H:%M:%S")
        self.use_color = use_color

    def format(self, record: logging.LogRecord) -> str:
        timestamp = self.formatTime(record, self.datefmt)
        style = LEVEL_STYLES.get(record.levelno, LEVEL_STYLES[logging.INFO])
        level = style["label"]
        logger_name = _short_logger_name(record.name)
        message = record.getMessage()

        if self.use_color:
            color = style["color"]
            line = (
                f"{DIM}{timestamp}{RESET} "
                f"{color}{level}{RESET} "
                f"{DIM}{logger_name:<22}{RESET} "
                f"{message}"
            )
        else:
            line = f"{timestamp} {level} {logger_name:<22} {message}"

        if record.exc_info:
            line = f"{line}\n{self.formatException(record.exc_info)}"
        if record.stack_info:
            line = f"{line}\n{self.formatStack(record.stack_info)}"
        return line


class PlainFileFormatter(logging.Formatter):
    """Stable searchable file formatter with location and process details."""

    def __init__(self) -> None:
        super().__init__(datefmt="%Y-%m-%d %H:%M:%S")

    def format(self, record: logging.LogRecord) -> str:
        timestamp = self.formatTime(record, self.datefmt)
        level = LEVEL_STYLES.get(record.levelno, LEVEL_STYLES[logging.INFO])["label"].strip()
        logger_name = _short_logger_name(record.name, max_parts=4)
        location = f"{Path(record.pathname).name}:{record.lineno}"
        line = (
            f"{timestamp}.{int(record.msecs):03d} "
            f"{level:<5} "
            f"pid={record.process:<6} "
            f"{logger_name:<30} "
            f"{location:<24} "
            f"{record.getMessage()}"
        )
        if record.exc_info:
            line = f"{line}\n{self.formatException(record.exc_info)}"
        if record.stack_info:
            line = f"{line}\n{self.formatStack(record.stack_info)}"
        return line


class AccessLogFormatter(logging.Formatter):
    """Readable uvicorn access log formatter."""

    STATUS_COLORS = {
        "2": "\033[32m",
        "3": "\033[36m",
        "4": "\033[33m",
        "5": "\033[31m",
    }

    def __init__(self, *, use_color: bool = True) -> None:
        super().__init__(datefmt="%H:%M:%S")
        self.use_color = use_color

    def format(self, record: logging.LogRecord) -> str:
        timestamp = self.formatTime(record, self.datefmt)
        message = record.getMessage()
        if self.use_color:
            message = self._color_status(message)
            return f"{DIM}{timestamp}{RESET} HTTP  {DIM}{'uvicorn.access':<22}{RESET} {message}"
        return f"{timestamp} HTTP  {'uvicorn.access':<22} {message}"

    def _color_status(self, message: str) -> str:
        parts = message.rsplit(" ", 1)
        if len(parts) != 2 or not parts[1][:1].isdigit():
            return message
        color = self.STATUS_COLORS.get(parts[1][0], "")
        if not color:
            return message
        return f"{parts[0]} {color}{parts[1]}{RESET}"


def parse_log_level(value: int | str | None, default: int = logging.INFO) -> int:
    """Parse LOG_LEVEL-like values into a logging level."""

    if value is None:
        return default
    if isinstance(value, int):
        _validate_logging_level(value)
        return value
    raw = str(value).strip().upper()
    raw = LEVEL_ALIASES.get(raw, raw)
    if raw.isdigit():
        return parse_log_level(int(raw), default=default)
    if raw not in logging._nameToLevel:
        raise ValueError(f"Invalid logging level: {value!r}")
    level = int(logging._nameToLevel[raw])
    _validate_logging_level(level)
    return level


def setup_logging(
    level: int | str = logging.INFO,
    log_file: Optional[str] = None,
    format_string: str | None = None,
) -> None:
    """Configure root logging with polished console output and rotating files.

    ``format_string`` is accepted for backwards compatibility but ignored by the
    pretty formatter. Use ``LOG_COLOR`` and ``LOG_STYLE`` to tune presentation.
    """

    parsed_level = parse_log_level(level)
    use_color = _should_use_color()

    root_logger = logging.getLogger()
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    root_logger.setLevel(parsed_level)

    console_handler = SafeConsoleHandler()
    console_handler.setLevel(parsed_level)
    console_handler.setFormatter(PrettyFormatter(use_color=use_color))
    root_logger.addHandler(console_handler)

    if log_file:
        _add_file_handler(root_logger, log_file, parsed_level)

    _configure_framework_loggers(parsed_level, use_color)
    _quiet_noisy_loggers()


def log_lifecycle_banner(
    logger: logging.Logger,
    *,
    title: str,
    fields: Mapping[str, Any],
    logo: Iterable[str] | None = PLOTPILOT_LOGO,
    level: int = logging.INFO,
    stacklevel: int = 2,
) -> None:
    """Log an aligned lifecycle banner with an optional ASCII logo."""

    logo_lines = tuple(logo or ())
    width = max(
        [
            len(title),
            *(len(line) for line in logo_lines),
            *(len(str(k)) + len(str(v)) + 3 for k, v in fields.items()),
        ],
        default=20,
    )
    border = "-" * min(max(width + 4, 44), 88)
    logger.log(level, border, stacklevel=stacklevel)
    for line in logo_lines:
        logger.log(level, "%s", line, stacklevel=stacklevel)
    logger.log(level, "%s", title, stacklevel=stacklevel)
    for key, value in fields.items():
        logger.log(level, "  %-12s %s", f"{key}:", value, stacklevel=stacklevel)
    logger.log(level, border, stacklevel=stacklevel)


def log_startup_banner(
    logger: logging.Logger,
    *,
    title: str,
    fields: Mapping[str, Any],
    logo: Iterable[str] | None = PLOTPILOT_LOGO,
    level: int = logging.INFO,
) -> None:
    """Log the PlotPilot startup banner."""

    log_lifecycle_banner(
        logger,
        title=title,
        fields=fields,
        logo=logo,
        level=level,
        stacklevel=3,
    )


def get_logger(name: str) -> logging.Logger:
    """Get a logger instance with the specified name."""

    return logging.getLogger(name)


def _validate_logging_level(level: int) -> None:
    if level not in VALID_LOGGING_LEVELS:
        raise ValueError(
            f"Invalid logging level: {level}. "
            f"Valid levels are: {sorted(VALID_LOGGING_LEVELS)}"
        )


def _validate_log_file(log_file: str) -> None:
    if not isinstance(log_file, str):
        raise TypeError(f"log_file must be a string, got {type(log_file).__name__}")
    if not log_file.strip():
        raise ValueError("log_file cannot be empty")
    log_dir = os.path.dirname(log_file)
    if log_dir:
        os.makedirs(log_dir, exist_ok=True)
    with open(log_file, "a", encoding="utf-8"):
        pass


def _add_file_handler(root_logger: logging.Logger, log_file: str, level: int) -> None:
    _validate_log_file(log_file)
    max_bytes = _env_int("LOG_MAX_BYTES", 10 * 1024 * 1024)
    backups = _env_int("LOG_BACKUP_COUNT", 5)
    try:
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=max_bytes,
            backupCount=backups,
            encoding="utf-8",
        )
        file_handler.setLevel(level)
        file_handler.setFormatter(PlainFileFormatter())
        root_logger.addHandler(file_handler)
    except (OSError, IOError, PermissionError) as exc:
        print(f"WARNING: failed to setup file logging: {exc}", file=sys.stderr)


def _configure_framework_loggers(level: int, use_color: bool) -> None:
    for name in FRAMEWORK_LOGGERS:
        logger = logging.getLogger(name)
        logger.handlers.clear()
        logger.propagate = True
        logger.setLevel(level)

    access_logger = logging.getLogger("uvicorn.access")
    access_logger.handlers.clear()
    access_logger.propagate = False
    access_logger.setLevel(level)
    access_handler = SafeConsoleHandler()
    access_handler.setLevel(level)
    access_handler.setFormatter(AccessLogFormatter(use_color=use_color))
    access_logger.addHandler(access_handler)
    for handler in logging.getLogger().handlers:
        if isinstance(handler, RotatingFileHandler):
            access_logger.addHandler(handler)


def _quiet_noisy_loggers() -> None:
    if os.environ.get("DEBUG_HTTP", "").strip().lower() in {"1", "true", "yes"}:
        return
    for name in NOISY_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)


def _short_logger_name(name: str, *, max_parts: int = 3) -> str:
    if name == "root":
        return "root"
    aliases = {
        "interfaces.main": "api.main",
        "uvicorn.error": "uvicorn",
        "uvicorn.access": "access",
    }
    if name in aliases:
        return aliases[name]
    parts = name.split(".")
    if len(parts) <= max_parts:
        short = name
    else:
        short = ".".join([parts[0][0], *parts[-(max_parts - 1):]])
    return short[:30]


def _should_use_color() -> bool:
    raw = os.environ.get("LOG_COLOR", "auto").strip().lower()
    if raw in {"1", "true", "yes", "always"}:
        return True
    if raw in {"0", "false", "no", "never"}:
        return False
    if os.environ.get("NO_COLOR"):
        return False
    return hasattr(sys.stderr, "isatty") and sys.stderr.isatty()


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return max(0, int(raw))
    except ValueError:
        return default
