"""Compatibility exports for legacy web middleware."""

from .error_handler import (
    STATUS_CODE_MAP,
    add_error_handlers,
    generic_exception_handler,
    http_exception_handler,
    validation_exception_handler,
)
from .logging_config import get_logger, setup_logging

__all__ = [
    "STATUS_CODE_MAP",
    "add_error_handlers",
    "generic_exception_handler",
    "get_logger",
    "http_exception_handler",
    "setup_logging",
    "validation_exception_handler",
]

