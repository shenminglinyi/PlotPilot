"""Compatibility wrapper for the legacy error handler import path."""

from interfaces.api.middleware.error_handler import (
    STATUS_CODE_MAP,
    add_error_handlers,
    generic_exception_handler,
    http_exception_handler,
    validation_exception_handler,
)

__all__ = [
    "STATUS_CODE_MAP",
    "add_error_handlers",
    "generic_exception_handler",
    "http_exception_handler",
    "validation_exception_handler",
]

