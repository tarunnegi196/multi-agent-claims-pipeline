"""
Centralized logging setup for Plum Claims Engine.

Environment variables:
  LOG_LEVEL   = DEBUG | INFO | WARNING | ERROR   (default: INFO)
  LOG_FORMAT  = pretty | json                    (default: pretty)

Use LOG_FORMAT=json in production / cloud deployments (Render, Railway)
so log aggregators (Datadog, CloudWatch, Papertrail) can parse fields.

Use LOG_FORMAT=pretty locally — colored, human-readable output.
"""
import json
import logging
import sys
import time


class _JsonFormatter(logging.Formatter):
    """Structured JSON one-line-per-event formatter (production/cloud)."""

    def format(self, record: logging.LogRecord) -> str:
        obj: dict = {
            "ts":     time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(record.created)),
            "level":  record.levelname,
            "logger": record.name.replace("app.", ""),
            "msg":    record.getMessage(),
        }
        # Attach structured extras set via logger.info(..., extra={...})
        for key in ("claim_id", "agent", "duration_ms", "model", "doc_type",
                    "method", "status_code", "path", "conf"):
            val = getattr(record, key, None)
            if val is not None:
                obj[key] = val
        if record.exc_info:
            obj["exc"] = self.formatException(record.exc_info)
        return json.dumps(obj, default=str)


class _PrettyFormatter(logging.Formatter):
    """Colored, human-readable formatter for local development."""

    _LEVEL_COLORS = {
        "DEBUG":    "\033[36m",    # cyan
        "INFO":     "\033[32m",    # green
        "WARNING":  "\033[33m",    # yellow
        "ERROR":    "\033[31m",    # red
        "CRITICAL": "\033[35;1m",  # bold magenta
    }
    _RESET  = "\033[0m"
    _DIM    = "\033[2m"
    _BOLD   = "\033[1m"
    _PURPLE = "\033[35m"

    def format(self, record: logging.LogRecord) -> str:
        color = self._LEVEL_COLORS.get(record.levelname, "")
        ts    = time.strftime("%H:%M:%S", time.localtime(record.created))
        name  = record.name.replace("app.", "").replace("providers.", "")
        msg   = record.getMessage()

        # Highlight Gemini calls in purple so they stand out
        if "GEMINI" in msg or "gemini" in record.name:
            color = self._PURPLE

        line = (
            f"{self._DIM}{ts}{self._RESET} "
            f"{color}[{record.levelname:<8}]{self._RESET} "
            f"{self._DIM}{name:<28}{self._RESET} "
            f"{msg}"
        )
        if record.exc_info:
            line += "\n" + self.formatException(record.exc_info)
        return line


def setup_logging(log_level: str = "INFO", log_format: str = "pretty") -> None:
    """Configure root logger. Call once at application startup."""
    level = getattr(logging, log_level.upper(), logging.INFO)

    formatter: logging.Formatter
    if log_format.lower() == "json":
        formatter = _JsonFormatter()
    else:
        formatter = _PrettyFormatter()

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)

    # Silence noisy third-party libraries — they add no value in prod logs
    for noisy in (
        "httpx", "httpcore", "urllib3",
        "google.api_core", "google.auth", "google.generativeai",
        "aiosqlite", "langgraph",
    ):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    # Uvicorn's access log duplicates our middleware — suppress it
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.error").setLevel(logging.INFO)

    logging.getLogger(__name__).info(
        "Logging configured: level=%s format=%s", log_level.upper(), log_format
    )
