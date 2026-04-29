"""独立启动选题市场信号自动采集。"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"
os.environ["HF_DATASETS_OFFLINE"] = "1"
if os.getenv("DISABLE_SSL_VERIFY", "false").lower() == "true":
    os.environ["CURL_CA_BUNDLE"] = ""
    os.environ["REQUESTS_CA_BUNDLE"] = ""

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

try:
    from load_env import load_env

    load_env()
except Exception:
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except Exception:
        pass

logger = logging.getLogger(__name__)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run topic market signal collection outside the API process.")
    parser.add_argument("--once", action="store_true", help="run one collection attempt and exit")
    parser.add_argument("--force", action="store_true", help="ignore disabled/not-due settings when used with --once")
    parser.add_argument(
        "--poll-interval",
        type=int,
        default=int(os.getenv("TOPIC_SIGNAL_POLL_INTERVAL_SECONDS", "60") or "60"),
        help="seconds between scheduler checks in daemon mode",
    )
    parser.add_argument(
        "--no-initial-run",
        action="store_true",
        help="wait for the first poll interval before collecting in daemon mode",
    )
    return parser.parse_args(argv)


def configure_logging() -> None:
    from application.paths import AITEXT_ROOT
    from interfaces.api.middleware.logging_config import setup_logging

    log_level = getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO)
    log_file = os.getenv("LOG_FILE", str(AITEXT_ROOT / "logs" / "aitext.log"))
    setup_logging(level=log_level, log_file=log_file)


def build_topic_signal_automation_service(poll_interval_seconds: int = 60):
    from application.topic.services.topic_signal_automation_service import (
        TopicSignalAutomationService,
    )
    from interfaces.api.dependencies import get_topic_idea_service

    return TopicSignalAutomationService(
        get_topic_idea_service(),
        poll_interval_seconds=poll_interval_seconds,
    )


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    configure_logging()
    service = build_topic_signal_automation_service(
        poll_interval_seconds=args.poll_interval,
    )

    if args.once:
        ran = service.run_pending_once(force=args.force)
        logger.info("Topic signal collection once finished; ran=%s", ran)
        return 0

    logger.info(
        "Topic signal collector daemon starting; poll_interval=%ss initial_run=%s",
        args.poll_interval,
        not args.no_initial_run,
    )
    try:
        service.run_forever(run_immediately=not args.no_initial_run)
    except KeyboardInterrupt:
        logger.info("Topic signal collector daemon stopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
