"""Structured logging for Agent Compiler."""

import json
import logging
import re
import sys
from typing import Any

# ---------------------------------------------------------------------------
# Secret redaction
# ---------------------------------------------------------------------------

_SECRET_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"(sk-ant-[A-Za-z0-9\-]{20,})"), "[REDACTED:anthropic]"),
    (re.compile(r"(sk-[A-Za-z0-9]{20,})"), "[REDACTED:openai]"),
    (re.compile(r"(Bearer\s+)[A-Za-z0-9._\-]{20,}"), r"\1[REDACTED:token]"),
    (
        re.compile(
            r"((?:api[_-]?key|token|secret|password)\s*[=:]\s*)[^\s\"\']+",
            re.IGNORECASE,
        ),
        r"\1[REDACTED]",
    ),
]


def redact_secrets(text: str) -> str:
    """Replace known secret patterns with redaction placeholders."""
    for pattern, replacement in _SECRET_PATTERNS:
        text = pattern.sub(replacement, text)
    return text

# Configure basic logging format
LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


class JSONFormatter(logging.Formatter):
    """JSON log formatter for structured logging."""

    def format(self, record: logging.LogRecord) -> str:
        record.msg = redact_secrets(str(record.msg))
        log_data = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        # Add extra fields from adapter
        for key, value in record.__dict__.items():
            if key not in (
                "name", "msg", "args", "created", "filename",
                "funcName", "levelname", "levelno", "lineno",
                "module", "msecs", "pathname", "process",
                "processName", "relativeCreated", "stack_info",
                "thread", "threadName", "exc_info", "exc_text",
                "message",
            ):
                log_data[key] = value

        return json.dumps(log_data, default=str)


class StructuredLogAdapter(logging.LoggerAdapter):
    """Adapter that adds structured context to log messages."""

    def process(self, msg: str, kwargs: Any) -> tuple[str, Any]:
        """Process the log message to include extra context."""
        extra = kwargs.get("extra", {})
        if self.extra:
            extra.update(self.extra)

        # Format extra fields as key=value pairs
        if extra:
            extra_str = " | ".join(f"{k}={v}" for k, v in extra.items())
            msg = f"{msg} | {extra_str}"

        kwargs["extra"] = extra
        return msg, kwargs


def setup_logging(debug: bool = False, json_logs: bool = False) -> None:
    """Set up logging configuration.

    Args:
        debug: Enable debug level logging
        json_logs: Output logs in JSON format
    """
    level = logging.DEBUG if debug else logging.INFO

    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Remove existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Create handler
    handler = logging.StreamHandler(sys.stdout)

    if json_logs:
        handler.setFormatter(JSONFormatter(datefmt=DATE_FORMAT))
    else:
        handler.setFormatter(logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT))

    root_logger.addHandler(handler)

    # Suppress noisy loggers
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("openai").setLevel(logging.WARNING)


def get_logger(name: str, **context: Any) -> StructuredLogAdapter:
    """Get a structured logger with optional context.

    Args:
        name: Logger name (typically __name__)
        **context: Additional context to include in all log messages

    Returns:
        A StructuredLogAdapter instance
    """
    logger = logging.getLogger(name)
    return StructuredLogAdapter(logger, context)


class StepLogger:
    """Logger specifically for run step execution."""

    def __init__(self, run_id: str, step_id: str, node_id: str, node_type: str):
        self.logger = get_logger(
            "agent_compiler.runtime",
            run_id=run_id,
            step_id=step_id,
            node_id=node_id,
            node_type=node_type,
        )

    def step_started(self, input_data: dict[str, Any]) -> None:
        """Log step start."""
        self.logger.info("Step started", extra={"input_keys": list(input_data.keys())})

    def step_completed(self, output_data: dict[str, Any], duration_ms: float) -> None:
        """Log step completion."""
        self.logger.info(
            "Step completed",
            extra={
                "output_keys": list(output_data.keys()) if output_data else [],
                "duration_ms": round(duration_ms, 2),
            },
        )

    def step_failed(self, error: str, duration_ms: float) -> None:
        """Log step failure."""
        self.logger.error(
            "Step failed",
            extra={"error": error, "duration_ms": round(duration_ms, 2)},
        )

    def retrieval_results(self, num_docs: int, avg_score: float) -> None:
        """Log retrieval results."""
        self.logger.info(
            "Retrieval completed",
            extra={"num_docs": num_docs, "avg_score": round(avg_score, 3)},
        )

    def llm_call(self, model: str, tokens: int | None) -> None:
        """Log LLM call."""
        self.logger.info(
            "LLM call completed",
            extra={"model": model, "tokens": tokens},
        )
