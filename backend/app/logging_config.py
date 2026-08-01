"""Structured logging configuration for stdout (Docker log driver / Loki compatible).

Call ``configure_logging()`` once at application startup.  All subsequent calls
to either ``structlog.get_logger()`` or the standard ``logging`` module will
produce newline-delimited JSON records on *stdout*, making them trivially
collectable by the Docker JSON-file log driver, Promtail, or any Loki agent.
"""

from __future__ import annotations

import logging
import sys

import structlog


def configure_logging(log_level: str = "INFO") -> None:
    """Configure structlog and the stdlib logging bridge for JSON stdout output.

    Uses the stdlib-as-backend pattern: structlog delegates to the standard
    ``logging`` module so that level filtering, handler routing, and the
    ``ProcessorFormatter`` all go through a single pipeline.

    Parameters
    ----------
    log_level:
        Minimum log level to emit (e.g. ``"DEBUG"``, ``"INFO"``, ``"WARNING"``).
        Defaults to ``"INFO"``.
    """
    level = getattr(logging, log_level.upper(), logging.INFO)

    # ── Shared processor chain ────────────────────────────────────────────────
    # These processors run on every log record regardless of whether it
    # originated from structlog or from the stdlib logging bridge.
    shared_processors: list[structlog.types.Processor] = [
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.ExceptionRenderer(),
    ]

    # ── structlog configuration (stdlib as backend) ───────────────────────────
    # structlog forwards log calls to the standard logging module, which then
    # routes them through the ProcessorFormatter below for final JSON rendering.
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # ── stdlib logging → JSON stdout ─────────────────────────────────────────
    # ProcessorFormatter renders both structlog-originated records and plain
    # stdlib records as JSON so the output stream is uniform.
    formatter = structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.processors.JSONRenderer(),
        ],
        foreign_pre_chain=shared_processors,
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    # Remove any pre-existing handlers to avoid duplicate output.
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(level)

    # Silence noisy third-party loggers that typically flood stdout.
    for noisy in ("uvicorn.access", "httpx", "httpcore"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
