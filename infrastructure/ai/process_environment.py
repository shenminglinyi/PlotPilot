"""Process environment bootstrap for local AI dependencies."""
from __future__ import annotations

import logging
import os


def configure_huggingface_process_environment(
    logger: logging.Logger | None = None,
) -> None:
    """Force local/offline HuggingFace behavior before heavy imports."""
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    os.environ["HF_DATASETS_OFFLINE"] = "1"
    if os.getenv("DISABLE_SSL_VERIFY", "false").lower() == "true":
        os.environ["CURL_CA_BUNDLE"] = ""
        os.environ["REQUESTS_CA_BUNDLE"] = ""
        if logger is not None:
            logger.warning(
                "SSL certificate verification is DISABLED via DISABLE_SSL_VERIFY=true"
            )
