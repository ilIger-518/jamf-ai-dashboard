"""Tests for app.logging_config — structured JSON stdout logging."""

from __future__ import annotations

import json
import logging
from io import StringIO

import structlog

from app.logging_config import configure_logging


def _redirect_root_handler_to(buf: StringIO) -> None:
    """Point the root logger's StreamHandler at *buf* for log capture."""
    for h in logging.getLogger().handlers:
        if isinstance(h, logging.StreamHandler):
            h.stream = buf


def test_configure_logging_sets_root_log_level() -> None:
    """configure_logging should set the root logger to the requested level."""
    configure_logging(log_level="WARNING")
    assert logging.getLogger().level == logging.WARNING
    # Reset for subsequent tests
    configure_logging(log_level="INFO")


def test_configure_logging_stdlib_outputs_json_to_stdout() -> None:
    """stdlib logging records should be emitted as JSON on the handler stream."""
    configure_logging(log_level="DEBUG")
    buf = StringIO()
    _redirect_root_handler_to(buf)

    logging.getLogger("test.stdlib").info("hello from stdlib")

    output = buf.getvalue().strip()
    assert output, "Expected log output but got nothing"
    record = json.loads(output)
    assert record["event"] == "hello from stdlib"
    assert record["level"] == "info"
    assert "timestamp" in record


def test_configure_logging_structlog_outputs_json() -> None:
    """structlog loggers should emit JSON through the stdlib handler."""
    configure_logging(log_level="DEBUG")
    buf = StringIO()
    _redirect_root_handler_to(buf)

    logger = structlog.get_logger("test.structlog")
    logger.info("hello from structlog", key="value")

    output = buf.getvalue().strip()
    assert output, "Expected structlog output but got nothing"
    record = json.loads(output)
    assert record["event"] == "hello from structlog"
    assert record["key"] == "value"
    assert "timestamp" in record
    assert record["level"] == "info"


def test_configure_logging_noisy_loggers_silenced() -> None:
    """uvicorn.access, httpx, and httpcore should be silenced to WARNING."""
    configure_logging(log_level="DEBUG")
    for name in ("uvicorn.access", "httpx", "httpcore"):
        effective = logging.getLogger(name).level
        assert effective == logging.WARNING, (
            f"Expected {name} to be WARNING, got {logging.getLevelName(effective)}"
        )


def test_configure_logging_accepts_various_levels() -> None:
    """configure_logging should accept common level strings without raising."""
    for level in ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"):
        configure_logging(log_level=level)
        assert logging.getLogger().level == getattr(logging, level)
